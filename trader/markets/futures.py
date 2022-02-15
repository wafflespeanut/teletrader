import asyncio
from typing import Awaitable, Callable

from ..errors import EntryCrossedException, InsufficientQuantityException, PriceUnavailableException
from ..clients import FuturesExchangeClient, OrderSide, OrderPositionSide, OrderRequest, OrderFillEvent, OrderCancelEvent
from ..logger import DEFAULT_LOGGER as logging
from ..messages import Message
from ..signal import Signal
from ..storage import Storage
from ..utils import NamedLock


class FuturesTrader:
    def __init__(self, client: FuturesExchangeClient, storage: Storage):
        self.client = client
        self.storage = storage
        self.sym_lock = NamedLock()
        self.order_queue = asyncio.Queue()
        self._msg_handler = None

    async def init(self, loop=None):
        logging.info("Initializing storage")
        await self.storage.init()
        logging.info("Initializing futures client")
        await self.client.init(loop=loop)
        logging.info(f"Account balance: {self.client.balance} USDT", on="blue")

    def register_message_handler(self, handler: Callable[[str], Awaitable[None]]):
        self._msg_handler = handler

    async def queue_signal(self, signal: Signal):
        await self.order_queue.put(signal)

    def _gather_orders(self):
        async def _gatherer():
            logging.info("Waiting for orders to be queued...")
            while True:
                signal = await self.order_queue.get()
                if self.symbols.get(signal.symbol) is None:
                    logging.info(f"Unknown symbol {signal.symbol} in signal", color="yellow")
                    continue
                try:
                    return await self._place_order(signal)
                except PriceUnavailableException:
                    logging.info(f"Price unavailable for {signal.coin}", color="red")
                    await self._publish_message(Message.error(signal.tag, "Couldn't get price for symbol"))

    async def _place_order(self, signal: Signal):
        price = await self.client.get_symbol_price(signal.symbol)
        signal.correct(price)
        side = OrderSide.BUY if signal.is_long else OrderSide.SELL
        asyncio.ensure_future(self.client.change_leverage(signal.symbol, signal.leverage))
        alloc_funds = self.client.balance * signal.fraction

    async def _publish_message(self, msg: str):
        if self._msg_handler is None:
            return
        await self._msg_handler(msg)
