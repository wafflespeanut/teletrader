import asyncio
import json
import math
import threading
import time
from contextlib import asynccontextmanager

import janus
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException
from cachetools import TTLCache
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import \
    BinanceWebSocketApiManager

from . import (FuturesExchangeClient, Order, OrderCancelEvent,
               OrderFillEvent, OrderRequest, OrderType)
from ..errors import (EntryCrossedException, InsufficientMarginException,
                      PriceUnavailableException)
from ..logger import DEFAULT_LOGGER as logging


class UserEventType:
    AccountUpdate = "ACCOUNT_UPDATE"
    AccountConfigUpdate = "ACCOUNT_CONFIG_UPDATE"
    OrderTradeUpdate = "ORDER_TRADE_UPDATE"


class BinanceUserStream:
    def __init__(self, api_key, api_secret, test=False):
        self.test = test
        self.key = api_key
        self.secret = api_secret
        self._queue = janus.Queue()
        threading.Thread(target=self._start, daemon=True).start()

    @asynccontextmanager
    async def message(self):
        try:
            msg = await self._queue.async_q.get()
            yield msg
        finally:
            self._queue.async_q.task_done()

    def _start(self):
        self.exchange = "binance.com-futures" + ("-testnet" if self.test else "")
        self.manager = BinanceWebSocketApiManager(exchange=self.exchange)
        self.manager.create_stream(
            "arr", "!userData", api_key=self.key, api_secret=self.secret)

        logging.info("Spawning listener for futures user data")
        while True:
            buf = self.manager.pop_stream_data_from_stream_buffer()
            if not buf:
                time.sleep(0.05)
                continue
            try:
                msg = json.loads(buf)
                self._queue.sync_q.put(msg)
            except Exception as err:
                logging.error(f"Failed to decode message {buf}: {err}")


class BinanceFuturesClient(FuturesExchangeClient):
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.balance = 0
        self.symbols: dict = {}
        self._inner: AsyncClient = None
        self._ustream = None

        async def _empty(*_args):
            pass

        # event handlers
        self._bal_upd_hdr = _empty
        self._ord_fill_hdr = _empty
        self._ord_cancel_hdr = _empty

        # Ticker price stream subscription
        self.prices = TTLCache(maxsize=1000, ttl=10)  # 10 secs timeout for ticker prices

    async def init(self, test=False, loop=None):
        self._ustream = BinanceUserStream(self.api_key, self.api_secret, test=test)
        self._inner = await AsyncClient.create(
            api_key=self.api_key, api_secret=self.api_secret, testnet=test, loop=loop)
        self._manager = BinanceSocketManager(self._inner, loop=loop)
        self._subscribe_user_events()
        resp = await self._inner.futures_exchange_info()
        for info in resp["symbols"]:
            if info["contractType"] == "PERPETUAL":
                self.symbols[info["symbol"]] = info
        self._subscribe_futures_symbol_prices()
        resp = await self._inner.futures_account_balance()
        for item in resp:
            if item["asset"] == "USDT":
                self.balance = float(item["balance"])

    async def create_order(self, req: OrderRequest):
        try:
            params = {
                "symbol": req.symbol,
                "side": req.side,
                "positionSide": req.position_side,
                "type": req.otype,
                "quantity": req.quantity,
            }
            if req.otype == OrderType.LIMIT:
                params["price"] = req.price
                params["timeInForce"] = "GTC"
            elif req.otype == OrderType.STOP:
                params["stopPrice"] = req.stop_price
                params["price"] = req.limit_price
            resp = await self._inner.futures_create_order(**params)
            return Order(resp["orderId"], resp)
        except Exception as err:
            if isinstance(err, BinanceAPIException):
                if err.code == -2021:
                    raise EntryCrossedException(req.price)
                elif err.code == -2019:
                    raise InsufficientMarginException()
            raise err

    async def get_symbol_price(self, symbol):
        symbol = symbol.upper()
        price = self.prices.get(symbol)
        if price is None:
            try:
                resp = None
                logging.warn(f"Live price not found for {symbol}")
                resp = await self._inner.futures_symbol_ticker(symbol=symbol)
                price = float(resp["price"])
            except Exception as err:
                logging.error(f"Failed to get price for {symbol}: {err} (resp: {resp})")
        if price is None:
            raise PriceUnavailableException()
        return price

    async def change_leverage(self, symbol: str, leverage: int):
        await self.client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def normalize_price(self, symbol, price):
        info = self.symbols[symbol]
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                return round(price, int(round(math.log(1 / float(f["tickSize"]), 10), 0)))
        return price

    def normalize_quantity(self, symbol, qty):
        info = self.symbols[symbol]
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return round(qty, int(round(math.log(1 / float(f["minQty"]), 10), 0)))
        return qty

    def register_account_balance_update(self, call):
        self._bal_upd_hdr = call

    def register_order_fill_update(self, call):
        self._ord_fill_hdr = call

    def register_order_cancel_update(self, call):
        self._ord_cancel_hdr = call

    def _subscribe_user_events(self):
        async def _handler():
            while True:
                async with self._ustream.message() as msg:
                    try:
                        data = msg
                        event = msg["e"]
                        if event == UserEventType.AccountUpdate:
                            data = msg["a"]
                        elif event == UserEventType.OrderTradeUpdate:
                            data = msg["o"]
                        elif event == UserEventType.AccountConfigUpdate:
                            data = msg.get("ac", msg.get("ai"))
                        logging.debug(f"{event}: {data}")
                        await self._handle_event(msg)
                    except Exception as err:
                        logging.exception(f"Failed to handle event {msg}: {err}")

        asyncio.ensure_future(_handler())

    async def _handle_event(self, msg: dict):
        if msg["e"] == UserEventType.AccountUpdate:
            for info in msg["a"]["B"]:
                if info["a"] == "USDT":
                    self.balance = float(info["cw"])
                    await self._bal_upd_hdr(self.balance)
        elif msg["e"] == UserEventType.OrderTradeUpdate:
            info = msg["o"]
            order_id, price, quantity = info["i"], float(info["ap"]), float(info["q"])
            if info["X"] == "FILLED":
                await self._ord_fill_hdr(OrderFillEvent(order_id, price, quantity))
            if info["X"] == "CANCELED":
                await self._ord_cancel_hdr(OrderCancelEvent(order_id))

    def _subscribe_futures_symbol_prices(self):
        symbols = list(self.symbols.keys())

        async def _streamer():
            subs = list(map(lambda s: f"{s.lower()}@aggTrade", symbols))
            logging.info(f"Spawning listener for {len(symbols)} symbol(s): {symbols}",
                         color="magenta")
            async with self._manager.futures_multiplex_socket(subs) as stream:
                while True:
                    msg = await stream.recv()
                    if msg is None:
                        logging.warning("Received 'null' in price stream", color="red")
                        continue
                    try:
                        symbol = msg["stream"].split("@")[0].upper()
                        self.prices[symbol.upper()] = float(msg["data"]["p"])
                    except Exception as err:
                        logging.error(f"Failed to get price for {msg['stream']}: {err}")

        asyncio.ensure_future(_streamer())
