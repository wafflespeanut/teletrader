import asyncio
import math
import json
import logging
import uuid
import time

from binance import AsyncClient, BinanceSocketManager
from cachetools import TTLCache

from .user_stream import UserStream
from .signal import Signal, CHANNELS

STREAM_RECONNECT_INTERVAL = 6 * 60 * 60
WAIT_ORDER_EXPIRY = 24 * 60 * 60
ORDER_WATCH_INTERVAL = 5 * 60
MAX_TARGETS = 5


class OrderType:
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TP_MARKET = "TAKE_PROFIT_MARKET"


class OrderID:
    PrefixStopLoss = "stop-"
    PrefixTarget = "trgt-"
    PrefixWait = "wait-"
    PrefixMarket = "mrkt-"

    @classmethod
    def random(cls, prefix: str):
        i = str(uuid.uuid4())
        return prefix + i[len(prefix):]

    @classmethod
    def stop_loss(cls):
        return cls.random(cls.PrefixStopLoss)

    @classmethod
    def target(cls):
        return cls.random(cls.PrefixTarget)

    @classmethod
    def wait(cls):
        return cls.random(cls.PrefixWait)

    @classmethod
    def market(cls):
        return cls.random(cls.PrefixMarket)

    @classmethod
    def is_stop_loss(cls, i: str):
        return i.startswith(cls.PrefixStopLoss)

    @classmethod
    def is_wait(cls, i: str):
        return i.startswith(cls.PrefixWait)

    @classmethod
    def is_market(cls, i: str):
        return i.startswith(cls.PrefixMarket)

    @classmethod
    def is_target(cls, i: str):
        return i.startswith(cls.PrefixTarget)


class FuturesTrader:
    def __init__(self):
        self.client: AsyncClient = None
        self.state: dict = None
        self.prices: dict = {}
        self.symbols: dict = {}
        self.price_streamer = None
        self.olock = asyncio.Lock()  # lock to place only one order at a time
        self.slock = asyncio.Lock()  # lock for stream subscriptions
        self.sig_cache = TTLCache(maxsize=10000, ttl=60)
        self.balance = 0

    async def init(self, api_key, api_secret, state={}, test=False, loop=None):
        self.state = state
        self.client = await AsyncClient.create(
            api_key=api_key, api_secret=api_secret, testnet=test, loop=loop)
        self.manager = BinanceSocketManager(self.client, loop=loop)
        self.user_stream = UserStream(
            api_key, api_secret, test=test, switch_interval_secs=STREAM_RECONNECT_INTERVAL)
        if not self.state.get("streams"):
            self.state["streams"] = []
        if not self.state.get("orders"):
            self.state["orders"] = {}
        await self._watch_orders()
        await self._subscribe_futures_user()
        await self._subscribe_futures()
        resp = await self.client.futures_exchange_info()
        for info in resp["symbols"]:
            self.symbols[info["symbol"]] = info
        resp = await self.client.futures_account_balance()
        for item in resp:
            if item["asset"] == "USDT":
                self.balance = float(item["balance"])
        logging.info(f"Account balance: {self.balance} USDT")

    def get_signal(self, chat_id: int, text: str) -> Signal:
        for ch in CHANNELS:
            if ch.chan_id != chat_id:
                continue
            return ch.parse(text)

    async def place_order(self, signal: Signal):
        self.sig_cache.expire()
        if self.sig_cache.get(str(signal)) is not None:
            logging.info("Ignoring signal because it exists in cache")
            return

        await self._subscribe_futures(signal.coin)
        for _ in range(10):
            if self.prices.get(signal.coin) is not None:
                break
            logging.info(f"Waiting for {signal.coin} price to be available")
            await asyncio.sleep(1)
        if self.prices.get(signal.coin) is None:
            logging.warning(f"Ignoring signal {signal} because price is unavailable")
            return

        symbol = f"{signal.coin}USDT"
        logging.info(f"Modifying leverage to {signal.leverage}x for {symbol}")
        await self.client.futures_change_leverage(symbol=symbol, leverage=signal.leverage)
        order_id = OrderID.wait() if signal.wait_entry else OrderID.market()
        self.sig_cache[str(signal)] = order_id
        price = self.prices[signal.coin]
        quantity = (self.balance * signal.fraction) / (price / signal.leverage)
        signal.autocorrect(price)
        params = {
            "symbol": symbol,
            "side": "BUY" if signal.is_long else "SELL",
            "type": OrderType.MARKET,
            "quantity": self._round_qty(symbol, quantity),
            "newClientOrderId": order_id,
        }

        if signal.wait_entry:  # stop limit if we can wait for entry
            params["type"] = OrderType.STOP
            params["stopPrice"] = self._round_price(symbol, signal.entry)
            params["price"] = self._round_price(symbol, signal.max_entry)
        elif (signal.is_long and price > signal.max_entry) or (signal.is_short and price < signal.max_entry):
            logging.warning(f"Price went too fast to place order for signal {signal}")
            return

        async with self.olock:  # Lock only for interacting with orders
            try:
                resp = await self.client.futures_create_order(**params)
                self.state["orders"][order_id] = {
                    "id": resp["orderId"],
                    "qty": float(resp["origQty"]),
                    "sym": symbol,
                    "side": params["side"],
                    "ent": signal.entry,
                    "sl": signal.sl,
                    "tgt": signal.targets,
                    "frc": signal.fraction,
                    "lev": signal.leverage,
                    "tag": signal.tag,
                    "exp": int(time.time()) + WAIT_ORDER_EXPIRY,  # 1 day expiry by default
                    "t_ord": [],
                }
                logging.info(f"Created order {order_id} for signal: {signal}, "
                             f"params: {json.dumps(params)}, resp: {resp}")
            except Exception as err:
                logging.error(f"Failed to create order for signal {signal}: {err}, "
                              f"params: {json.dumps(params)}")

        if not signal.wait_entry:  # Place SL and limit orders for market order
            await self._place_collection_orders(order_id)

    async def close_trades(self, tag, coin=None):
        if coin is None:
            logging.info(f"Attempting to close all trades associated with channel {tag}")
        else:
            logging.info(f"Attempting to close {coin} trades associated with channel {tag}")
        async with self.olock:
            removed = []
            for order_id, order in self.state["orders"].values():
                if order.get("tag") != tag:
                    continue
                if coin is not None and order["sym"] != f"{coin}USDT":
                    continue
                children = [order["s_ord"]] + order["t_ord"]
                removed += children
                for oid in children:
                    await self._cancel_order(oid, order["sym"])
                try:
                    resp = await self.client.futures_create_order(
                        symbol=order["sym"],
                        side="SELL" if order["side"] == "BUY" else "BUY",
                        type=OrderType.MARKET,
                        closePosition=True,
                    )
                    logging.info(f"Closed position for {order}, resp: {resp}")
                except Exception as err:
                    logging.error(f"Failed to close position for {order_id}, err: {err}")
            for oid in removed:
                self.state["orders"].pop(oid, None)

    async def _place_collection_orders(self, order_id):
        await self._place_sl_order(order_id)

        targets = []
        async with self.olock:
            odata = self.state["orders"][order_id]
            symbol = odata["sym"]
            targets = odata["tgt"][:MAX_TARGETS]
            if odata.get("t_ord"):
                logging.warning(f"TP order(s) already exist for parent {order_id}")
                return

        quantity = odata["qty"]
        for i, tgt in enumerate(targets):
            quantity *= 0.5
            async with self.olock:
                tgt_order_id = OrderID.target()
                params = {
                    "symbol": symbol,
                    "side": "SELL" if odata["side"] == "BUY" else "BUY",
                    "newClientOrderId": tgt_order_id,
                }
                if i < len(odata["tgt"]) - 1:
                    params["type"] = OrderType.LIMIT
                    params["timeInForce"] = "GTC"
                    params["quantity"] = self._round_qty(symbol, quantity)
                    params["price"] = self._round_price(symbol, tgt)
                else:  # Close position with final target as TP
                    params["type"] = OrderType.TP_MARKET
                    params["stopPrice"] = self._round_price(symbol, tgt)
                    params["closePosition"] = True
                try:
                    resp = await self.client.futures_create_order(**params)
                    odata["t_ord"].append(tgt_order_id)
                    self.state["orders"][tgt_order_id] = {"parent": order_id}
                    logging.info(f"Created limit order {tgt_order_id} for parent {order_id}, "
                                 f"resp: {resp}, params: {json.dumps(params)}")
                except Exception as err:
                    logging.error(f"Failed to create target order for parent {order_id}: {err}, "
                                  f"params: {json.dumps(params)}")

    async def _subscribe_futures_user(self):
        async def _handler():
            while True:
                async with self.user_stream.message() as msg:
                    try:
                        logging.info(msg)
                        await self._handle_event(msg)
                    except Exception as err:
                        logging.exception(f"Failed to handle event {msg}: {err}")

        asyncio.ensure_future(_handler())

    async def _handle_event(self, msg: dict):
        if msg["e"] == "ACCOUNT_UPDATE":
            for info in msg["a"]["B"]:
                if info["a"] == "USDT":
                    self.balance = float(info["cw"])
                    logging.info(f"Current balance: {self.balance}")
        elif msg["e"] == "ORDER_TRADE_UPDATE":
            info = msg["o"]
            order_id = info["c"]
            if info["X"] == "FILLED":
                # We might get duplicated data when we switch connections, so do some checks
                async with self.olock:
                    o = self.state["orders"].get(order_id)
                    if o is None:
                        logging.warning(f"Received order {order_id} but missing in state")
                        return
                if OrderID.is_wait(order_id):
                    entry = float(info["ap"])
                    logging.info(f"Placing TP/SL orders for fulfilled order {order_id} (entry: {entry})")
                    async with self.olock:
                        self.state["orders"][order_id]["ent"] = entry
                    await self._place_collection_orders(order_id)
                elif OrderID.is_stop_loss(order_id):
                    async with self.olock:
                        logging.info(f"Order {order_id} hit stop loss. Removing TP orders...")
                        sl = self.state["orders"].pop(order_id)
                        parent = self.state["orders"].pop(sl["parent"])
                        for oid in parent["t_ord"]:
                            self.state["orders"].pop(oid, None)  # It might not exist
                            await self._cancel_order(oid, parent["sym"])
                elif OrderID.is_target(order_id):
                    logging.info(f"TP order {order_id} hit. Moving stop loss...")
                    await self._move_stop_loss(order_id)

    async def _move_stop_loss(self, tp_id: str):
        async with self.olock:
            tp = self.state["orders"].pop(tp_id)
            parent = self.state["orders"][tp["parent"]]
            targets = parent["t_ord"]
            if tp_id not in targets:
                if parent.get("s_ord") is None:
                    logging.warning(f"SL doesn't exist for order {parent}")
                    return
                logging.warning(f"Couldn't find TP order {tp_id} in parent {parent}")
                new_price = parent["ent"]
            elif tp_id == targets[-1]:
                logging.info(f"All TP orders hit. Removing parent {parent}")
                parent = self.state.pop(tp["parent"])
                self.state.pop(parent["s_ord"])
                await self._cancel_order(parent["s_ord"], parent["sym"])
                return
            else:
                idx = targets.index(tp_id)
                new_price = parent["ent"] if idx == 0 else parent["tgt"][idx - 1]

        await self._place_sl_order(tp["parent"], new_price)

    async def _place_sl_order(self, parent_id: str, new_price=None):
        async with self.olock:
            odata = self.state["orders"][parent_id]
            symbol = odata["sym"]
            sl_order_id = OrderID.stop_loss()
            if odata.get("s_ord") is not None:
                if new_price is None:
                    logging.warning(f"SL order already exists for parent {parent_id}")
                    return
                logging.info(f"Moving SL order for {parent_id} to new price {new_price}")
                await self._cancel_order(odata["s_ord"], symbol)
            params = {
                "symbol": symbol,
                "side": "SELL" if odata["side"] == "BUY" else "BUY",
                "type": OrderType.STOP_MARKET,
                "newClientOrderId": sl_order_id,
                "stopPrice": self._round_price(symbol, new_price if new_price is not None else odata["sl"]),
                "closePosition": True,
            }
            try:
                resp = await self.client.futures_create_order(**params)
                odata["s_ord"] = sl_order_id
                self.state["orders"][sl_order_id] = {
                    "parent": parent_id,
                }
                logging.info(f"Created SL order {sl_order_id} for parent {parent_id}, "
                             f"resp: {resp}, params: {json.dumps(params)}")
            except Exception as err:
                logging.error(f"Failed to create SL order for parent {parent_id}: {err}, "
                              f"params: {json.dumps(params)}")

    async def _watch_orders(self):
        async def _watcher():
            while True:
                open_symbols = []
                open_orders = {}
                async with self.olock:
                    resp = await self.client.futures_get_open_orders()
                    for order in resp:
                        open_orders[order["clientOrderId"]] = order
                    logging.info(f"Checking {len(open_orders)} orders...")
                    for oid, order in open_orders.items():
                        odata = self.state["orders"].get(oid)
                        if OrderID.is_stop_loss(oid) or OrderID.is_target(oid):
                            if odata is not None:
                                parent = self.state["orders"].get(odata.get("parent"))
                                if parent is None:
                                    logging.info(f"Removing orphan {oid}")
                                    self.state["orders"].pop(oid)
                                    odata = None
                            if odata is None:
                                await self._cancel_order(oid, order["symbol"])
                                continue
                        elif OrderID.is_market(oid) or OrderID.is_wait(oid):
                            open_symbols.append(order["symbol"][:-4])
                    removed = []
                    for oid, odata in self.state["orders"].items():
                        if open_orders.get(oid) is None:
                            if OrderID.is_market(oid) or OrderID.is_wait(oid):
                                # Ignore if wait/market order has open SL
                                if open_orders.get(odata["s_ord"]) is not None:
                                    continue
                            removed.append(oid)
                    for oid in removed:
                        logging.info(f"Removing outdated order {oid}")
                        self.state["orders"].pop(oid)

                async with self.slock:
                    redundant = set(self.state["streams"]).difference(open_symbols)
                    if redundant:
                        logging.info(f"Resetting price streams to {open_symbols}")
                        self.state["streams"] = open_symbols
                        self.price_streamer = None
                        await self._subscribe_futures()
                        for sym in redundant:
                            self.prices.pop(f"{sym}USDT", None)

                now = time.time()
                async with self.olock:
                    removed = []
                    for order_id, order in self.state["orders"].items():
                        if not OrderID.is_wait(order_id):
                            continue
                        if order.get("t_ord"):
                            continue
                        if now < order["exp"]:
                            continue
                        logging.info(f"Wait order {order_id} has expired. Removing...")
                        removed.append(order_id)
                        await self._cancel_order(order_id, order["sym"])
                    for order_id in removed:
                        self.state["orders"].pop(order_id)
                await asyncio.sleep(ORDER_WATCH_INTERVAL)

        asyncio.ensure_future(_watcher())

    async def _subscribe_futures(self, coin: str = None):
        async with self.slock:
            num_streams = len(set(self.state["streams"]))
            resub = self.price_streamer is None
            if coin is not None:
                coin = coin.upper()
                # We should have duplicates because it should be possible to long/short
                # on top of an existing long/short.
                self.state["streams"].append(coin)

            if num_streams != len(set(self.state["streams"])):
                resub = True

            if resub and self.price_streamer is not None:
                logging.info("Cancelling ongoing ws stream for resubscribing")
                self.price_streamer.cancel()

            symbols = set(self.state["streams"])
            if not symbols:
                return

        async def _streamer():
            subs = list(map(lambda s: s.lower() + "usdt@aggTrade", symbols))
            logging.info(f"Spawning listener for {len(symbols)} symbol(s): {symbols}")
            async with self.manager.futures_multiplex_socket(subs) as stream:
                while True:
                    msg = await stream.recv()
                    if msg is None:
                        logging.warning("Received 'null' in price stream")
                        continue
                    try:
                        symbol = msg["stream"].split("@")[0][:-4].upper()
                        self.prices[symbol.upper()] = float(msg["data"]["p"])
                    except Exception as err:
                        logging.error(f"Failed to get price for {msg['stream']}: {err}")

        self.price_streamer = asyncio.ensure_future(_streamer())

    async def _cancel_order(self, oid: str, symbol: str):
        try:
            resp = await self.client.futures_cancel_order(symbol=symbol, origClientOrderId=oid)
            logging.info(f"Cancelled order {oid}: {resp}")
        except Exception as err:
            logging.error(f"Failed to cancel order {oid}: {err}")

    # MARK: Rouding for min quantity and min price for symbols

    def _round_price(self, symbol: str, price: float):
        info = self.symbols[symbol]
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                return round(price, int(round(math.log(1 / float(f["tickSize"]), 10), 0)))
        return price

    def _round_qty(self, symbol: str, qty: float):
        info = self.symbols[symbol]
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return round(qty, int(round(math.log(1 / float(f["minQty"]), 10), 0)))
        return qty
