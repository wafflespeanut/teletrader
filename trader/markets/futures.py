import asyncio
import traceback
from typing import Awaitable, Callable

from ..errors import (EntryCrossedException, InsufficientMarginException,
                      InsufficientQuantityException, PriceUnavailableException)
from ..clients import (FuturesExchangeClient, OrderSide, OrderPositionSide,
                       OrderRequest, OrderFillEvent, OrderCancelEvent)
from ..logger import DEFAULT_LOGGER as logging
from ..messages import Message
from ..signal import Signal
from ..storage import Storage
from ..utils import get_tag

PRICE_SLIPPAGE = 1.2  # skip order if funds allocated exceeds estimation by this much


class FuturesTrader:
    def __init__(self, client: FuturesExchangeClient, storage: Storage):
        self.client = client
        self.storage = storage
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

            async def _process(signal):
                while True:
                    pos = await self.storage.get_position(signal.tag)
                    if pos is None:  # Ensure that we don't have a position with the same tag
                        break
                    signal.tag = get_tag()

                try:
                    return await self._place_order(signal)
                except PriceUnavailableException:
                    logging.info(f"Price unavailable for {signal.symbol}", color="red")
                    await self._publish_message(
                        Message.error(signal.tag, "Couldn't get price for symbol"))
                except EntryCrossedException as err:
                    logging.info(
                        f"Price went too fast ({err.price}) for signal {signal}", color="yellow")
                    await self._publish_message(
                        Message.error(signal.tag, "Price went too fast for signal"))
                except InsufficientMarginException:
                    await self._publish_message(Message.no_margin(signal.asset))
                except InsufficientQuantityException as err:
                    logging.info(
                        f"Allocated ${round(err.alloc_funds, 2)} for {err.alloc_q} {signal.coin} "
                        f"but requires ${round(err.est_funds, 2)} for {err.est_q} {signal.coin}",
                        color="red")
                    await self._publish_message(
                        Message.error(signal.tag, "Cannot allocate required quantity for position"))
                except Exception as err:
                    logging.error(f"Failed to place order: {traceback.format_exc()} {err}")
                    await self._publish_message(
                        Message.error(signal.tag, "Unexpected error occurred while placing order"))

            while True:
                signal = await self.order_queue.get()
                asyncio.ensure_future(_process(signal))

        asyncio.ensure_future(_gatherer())

    async def _place_order(self, signal: Signal):
        asyncio.ensure_future(self.client.change_leverage(signal.symbol, signal.leverage))
        price = await self.client.get_symbol_price(signal.symbol)
        signal.correct(price)
        side = OrderSide.BUY if signal.is_long else OrderSide.SELL
        pos = OrderPositionSide.LONG if signal.is_long else OrderPositionSide.SHORT
        alloc_funds = self.client.balance * signal.fraction
        alloc_q = alloc_funds / (price / signal.leverage)
        logging.info(f"Corrected signal: {signal}", color="cyan")
        qty = self.client.normalize_quantity(signal.symbol, alloc_q)
        est_funds = qty * signal.entry / signal.leverage
        if (est_funds / alloc_funds) > PRICE_SLIPPAGE:
            raise InsufficientQuantityException(alloc_q, alloc_funds, qty, est_funds)

        req = OrderRequest(signal.symbol, side, qty, pos)
        if signal.is_market_order:
            logging.info(f"Placing market order for {signal.coin} @ {signal.entry}")
        else:
            logging.info(f"Placing limit order for {signal.coin} @ {signal.entry}")
            req.limit(self.client.normalize_price(signal.symbol, signal.entry))

        order = await self.client.create_order(req)
        logging.info(f"Created order {order.order_id} ({signal}): {order.response}")

    async def _publish_message(self, msg: str):
        if self._msg_handler is None:
            return
        await self._msg_handler(msg)
