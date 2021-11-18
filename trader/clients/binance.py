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
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager

from . import FuturesExchangeClient
from ..errors import EntryCrossedException, InsufficientMarginException, PriceUnavailableException
from ..logger import DEFAULT_LOGGER as logging


class UserEventType:
    AccountUpdate = "ACCOUNT_UPDATE"
    AccountConfigUpdate = "ACCOUNT_CONFIG_UPDATE"
    OrderTradeUpdate = "ORDER_TRADE_UPDATE"


class OrderRequest:
    def __init__(self, symbol, side, client_id, quantity, position_side):
        self._params = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side,
            "type": OrderType.MARKET,
            "newClientOrderId": client_id,
            "quantity": quantity,
        }

    def limit(self, price):
        self._params["type"] = OrderType.LIMIT
        self._params["price"] = price
        self._params["timeInForce"] = "GTC"

    def stop_limit(self, stop_price, limit_price):
        self._params["type"] = OrderType.STOP
        self._params["stopPrice"] = stop_price
        self._params["price"] = limit_price


class BinanceFuturesClient(FuturesExchangeClient):
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.balance = 0
        self.symbols: dict = {}
        self._inner: AsyncClient = None
        self._ustream = None

        # Ticker price stream subscription
        self.prices = TTLCache(maxsize=1000, ttl=10)  # 10 secs timeout for ticker prices
        self.p_streamer = None
        self.p_streams = set()
        self.p_lock = asyncio.Lock()

    async def init(self, test=False, loop=None):
        self._ustream = BinanceUserStream(self.api_key, self.api_secret, test=test)
        self.client = await AsyncClient.create(
            api_key=self.api_key, api_secret=self.api_secret, testnet=test, loop=loop)
        self.manager = BinanceSocketManager(self.client, loop=loop)
        resp = await self.client.futures_exchange_info()
        for info in resp["symbols"]:
            self.symbols[info["symbol"]] = info
        resp = await self.client.futures_account_balance()
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
                "newClientOrderId": req.client_id,
                "quantity": req.quantity,
            }
            if req.otype == OrderType.LIMIT:
                params["price"] = req.price
                params["timeInForce"] = "GTC"
            elif req.otype == OrderType.STOP:
                params["stopPrice"] = req.stop_price
                params["price"] = req.limit_price
            resp = await self._inner.futures_create_order(**params)
        except Exception as err:
            logging.error(f"Failed to create order: {err}, params: {json.dumps(params)}")
            if isinstance(err, BinanceAPIException):
                if err.code == -2021:
                    raise EntryCrossedException(req.price)
                elif err.code == -2019:
                    raise InsufficientMarginException()

    async def get_symbol_price(self, symbol):
        symbol = symbol.upper()
        await self._subscribe_futures_symbol_price(symbol)
        price = self.prices.get(symbol)
        if price is None:
            try:
                resp = None
                resp = await self._inner.futures_symbol_ticker(symbol=symbol)
                price = float(resp["price"])
            except Exception as err:
                logging.error(f"Failed to fetch price for {symbol}: {err} (response: {resp})")
        if price is None:
            raise PriceUnavailableException()
        return price

    async def change_leverage(self, symbol: str, leverage: int):
        logging.info(f"Modifying leverage to {leverage}x for {symbol}", color="green")
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

    async def _subscribe_futures_symbol_price(self, symbol):
        async with self.p_lock:
            symbol = symbol.upper()
            num_streams = len(self.p_streams)
            self.p_streams.add(symbol)
            if num_streams != len(self.p_streams) and self.p_streams is not None:
                logging.info("Cancelling ongoing ws stream for resubscribing")
                self.p_streamer.cancel()
            else:
                return

        async def _streamer():
            symbols = list(self.p_streams)
            subs = list(map(lambda s: f"{s.lower()}@aggTrade", symbols))
            logging.info(f"Spawning listener for {len(symbols)} symbol(s): {symbols}", color="magenta")
            async with self.manager.futures_multiplex_socket(subs) as stream:
                while True:
                    msg = await stream.recv()
                    if msg is None:
                        logging.warning("Received 'null' in price stream", color="red")
                        continue
                    try:
                        symbol = msg["stream"].split("@")[0][:-4].upper()
                        self.prices[symbol.upper()] = float(msg["data"]["p"])
                    except Exception as err:
                        logging.error(f"Failed to get price for {msg['stream']}: {err}")

        self.p_streamer = asyncio.ensure_future(_streamer())


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
        self.manager.create_stream("arr", "!userData", api_key=self.key, api_secret=self.secret)

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
