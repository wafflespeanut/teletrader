import asyncio
import math
import json
import uuid
import re
import time
import traceback

from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException
from cachetools import TTLCache

from .errors import EntryCrossedException, PriceUnavailableException
from .logger import DEFAULT_LOGGER as logging
from .signal import Signal, CHANNELS
from .user_stream import UserStream

WAIT_ORDER_EXPIRY = 24 * 60 * 60
NEW_ORDER_TIMEOUT = 5 * 60
ORDER_WATCH_INTERVAL = 5 * 60
MAX_TARGETS = 5
SIGNAL_SYMBOL_TTL = 20 * 60


class OrderType:
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TP_MARKET = "TAKE_PROFIT_MARKET"


class UserEventType:
    AccountUpdate = "ACCOUNT_UPDATE"
    AccountConfigUpdate = "ACCOUNT_CONFIG_UPDATE"
    OrderTradeUpdate = "ORDER_TRADE_UPDATE"


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
        self.order_queue = asyncio.Queue()
        self.sig_cache = TTLCache(maxsize=100, ttl=20)
        self.balance = 0

    async def init(self, api_key, api_secret, state={}, test=False, loop=None):
        self.state = state
        self.client = await AsyncClient.create(
            api_key=api_key, api_secret=api_secret, testnet=test, loop=loop)
        self.manager = BinanceSocketManager(self.client, loop=loop)
        self.user_stream = UserStream(api_key, api_secret, test=test)
        if not self.state.get("streams"):
            self.state["streams"] = []
        if not self.state.get("orders"):
            self.state["orders"] = {}
        await self._gather_orders()
        await self._watch_orders()
        await self._subscribe_futures_user()
        resp = await self.client.futures_exchange_info()
        for info in resp["symbols"]:
            self.symbols[info["symbol"]] = info
        resp = await self.client.futures_account_balance()
        for item in resp:
            if item["asset"] == "USDT":
                self.balance = float(item["balance"])
        logging.info(f"Account balance: {self.balance} USDT", on="blue")

    def get_signal(self, chat_id: int, text: str) -> Signal:
        for ch in CHANNELS:
            if ch.chan_id != chat_id:
                continue
            return ch.parse(text)

    async def queue_signal(self, signal: Signal):
        await self.order_queue.put(signal)

    async def close_trades(self, tag, coin=None):
        if coin is None:
            logging.info(f"Attempting to close all trades associated with channel {tag}", on="yellow")
        else:
            logging.info(f"Attempting to close {coin} trades associated with channel {tag}", on="yellow")
        async with self.olock:
            removed = []
            for order_id, order in self.state["orders"].values():
                if order.get("tag") != tag:
                    continue
                if coin is not None and order["sym"] != f"{coin}USDT":
                    continue
                children = [] + order["t_ord"]
                if order.get("s_ord"):
                    children.append(order["s_ord"])
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
                    logging.info(f"Closed position for {order}, resp: {resp}", on="yellow")
                except Exception as err:
                    logging.error(f"Failed to close position for {order_id}, err: {err}")
            for oid in removed:
                self.state["orders"].pop(oid, None)

    async def _gather_orders(self):
        async def _gatherer():
            logging.info("Waiting for orders to be queued...")
            while True:
                signal = await self.order_queue.get()
                if not re.search(r"^[A-Z0-9]+$", signal.coin):
                    logging.info(f"Unknown symbol {signal.coin} in signal", on="yellow")
                    continue
                for i in range(3):
                    if i > 0:
                        await self._unregister_order(signal)
                    try:
                        registered = await self._register_order_for_signal(signal)
                        if registered:
                            await self._place_order(signal)
                        else:
                            logging.info("Ignoring signal because order exists for symbol", on="yellow")
                        break
                    except PriceUnavailableException:
                        logging.info(f"Price unavailable for {signal.coin}", on="yellow")
                    except EntryCrossedException as err:
                        logging.info(f"Price went too fast ({err.price}) for signal {signal}", on="yellow")
                    except Exception as err:
                        logging.error(f"Failed to place order: {traceback.format_exc()} {err}")
                        await self._unregister_order(signal)  # unknown error - don't block symbols from future signals
                        break
                    await asyncio.sleep(5)

        asyncio.ensure_future(_gatherer())

    async def _place_order(self, signal: Signal):
        order_id = OrderID.wait() if signal.wait_entry else OrderID.market()
        await self._subscribe_futures(signal.coin)
        for _ in range(10):
            if self.prices.get(signal.coin) is not None:
                break
            logging.info(f"Waiting for {signal.coin} price to be available")
            await asyncio.sleep(1)
        if self.prices.get(signal.coin) is None:
            raise PriceUnavailableException()

        symbol = f"{signal.coin}USDT"
        logging.info(f"Modifying leverage to {signal.leverage}x for {symbol}", color="green")
        await self.client.futures_change_leverage(symbol=symbol, leverage=signal.leverage)
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

        if (signal.is_long and price > signal.max_entry) or (signal.is_short and price < signal.max_entry):
            raise EntryCrossedException(price)

        if signal.wait_entry:
            if (signal.is_long and price < signal.entry) or (signal.is_short and price > signal.entry):
                params["type"] = OrderType.STOP
                params["stopPrice"] = self._round_price(symbol, signal.entry)
                params["price"] = self._round_price(symbol, signal.max_entry)
            else:
                logging.info(f"Switching to market order for {signal.coin} as wait price has reached")

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
                    "crt": int(time.time()),
                    "t_ord": [],
                    "t_q": [],
                }
                logging.info(f"Created order {order_id} for signal: {signal}, "
                             f"params: {json.dumps(params)}, resp: {resp}")
            except Exception as err:
                if isinstance(err, BinanceAPIException) and err.code == -2021:
                    raise EntryCrossedException(self.prices[signal.coin])
                logging.error(f"Failed to create order for signal {signal}: {err}, "
                              f"params: {json.dumps(params)}")

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

        remaining = quantity = odata["qty"]
        for i, tgt in enumerate(targets):
            quantity *= 0.5
            async with self.olock:
                tgt_order_id = OrderID.target()
                params = {
                    "symbol": symbol,
                    "type": OrderType.LIMIT,
                    "timeInForce": "GTC",
                    "side": "SELL" if odata["side"] == "BUY" else "BUY",
                    "newClientOrderId": tgt_order_id,
                    "price": self._round_price(symbol, tgt),
                }
                if i < len(odata["tgt"]) - 1:
                    params["quantity"] = self._round_qty(symbol, quantity)
                else:  # Don't close position (as it'll affect other orders)
                    params["quantity"] = self._round_qty(symbol, remaining)
                try:
                    resp = await self.client.futures_create_order(**params)
                    odata["t_ord"].append(tgt_order_id)
                    odata["t_q"].append(params["quantity"])
                    self.state["orders"][tgt_order_id] = {"parent": order_id}
                    remaining -= params["quantity"]  # Deduct after placing successful order
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
                        data = msg
                        event = msg['e']
                        if event == UserEventType.AccountUpdate:
                            data = msg["a"]
                        elif event == UserEventType.OrderTradeUpdate:
                            data = msg["o"]
                        elif event == UserEventType.AccountConfigUpdate:
                            data = msg.get("ac", msg.get("ai"))
                        logging.info(f"{event}: {data}")
                        await self._handle_event(msg)
                    except Exception as err:
                        logging.exception(f"Failed to handle event {msg}: {err}")

        asyncio.ensure_future(_handler())

    async def _handle_event(self, msg: dict):
        if msg["e"] == UserEventType.AccountUpdate:
            for info in msg["a"]["B"]:
                if info["a"] == "USDT":
                    self.balance = float(info["cw"])
                    logging.info(f"Account balance: {self.balance} USDT", on="blue")
        elif msg["e"] == UserEventType.OrderTradeUpdate:
            info = msg["o"]
            order_id = info["c"]
            if info["X"] == "FILLED":
                # We might get duplicated data when we switch connections, so do some checks
                async with self.olock:
                    o = self.state["orders"].get(order_id)
                    if o is None:
                        logging.warning(f"Received order {order_id} but missing in state")
                        return
                if OrderID.is_wait(order_id) or OrderID.is_market(order_id):
                    entry = float(info["ap"])
                    logging.info(f"Placing TP/SL orders for fulfilled order {order_id} (entry: {entry})", on="green")
                    async with self.olock:
                        self.state["orders"][order_id]["ent"] = entry
                    await self._place_collection_orders(order_id)
                elif OrderID.is_stop_loss(order_id):
                    async with self.olock:
                        logging.info(f"Order {order_id} hit stop loss. Removing TP orders...", on="red")
                        sl = self.state["orders"].pop(order_id)
                        parent = self.state["orders"].pop(sl["parent"])
                        for oid in parent["t_ord"]:
                            self.state["orders"].pop(oid, None)  # It might not exist
                            await self._cancel_order(oid, parent["sym"])
                elif OrderID.is_target(order_id):
                    logging.info(f"TP order {order_id} hit.", color="green")
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
                logging.warning(f"Couldn't find TP order {tp_id} in parent {parent}", color="red")
                new_price, quantity = parent["ent"], parent["qty"]
            elif tp_id == targets[-1]:
                logging.info(f"All TP orders hit. Removing parent {parent}")
                parent = self.state.pop(tp["parent"])
                self.state.pop(parent["s_ord"])
                await self._cancel_order(parent["s_ord"], parent["sym"])
                return
            else:
                idx = targets.index(tp_id)
                new_price, quantity = parent["ent"], sum(parent["t_q"][(idx + 1):])

        await self._place_sl_order(tp["parent"], new_price, quantity)

    async def _place_sl_order(self, parent_id: str, new_price=None, quantity=None):
        async with self.olock:
            odata = self.state["orders"][parent_id]
            symbol = odata["sym"]
            sl_order_id = OrderID.stop_loss()
            if odata.get("s_ord") is not None:
                logging.info(f"Moving SL order for {parent_id} to new price {new_price}")
                await self._cancel_order(odata["s_ord"], symbol)
            params = {
                "symbol": symbol,
                "side": "SELL" if odata["side"] == "BUY" else "BUY",
                "type": OrderType.STOP_MARKET,
                "newClientOrderId": sl_order_id,
                "stopPrice": self._round_price(symbol, new_price if new_price is not None else odata["sl"]),
                "quantity": self._round_qty(symbol, (quantity if quantity is not None else odata["qty"])),
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
                                    logging.info(f"Removing orphan {oid}", color="yellow")
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
                                # Remove parent if it's old and none of the child orders exist
                                if (time.time() - odata["crt"]) < NEW_ORDER_TIMEOUT:
                                    continue
                                cids = ([odata["s_ord"]] if odata.get("s_ord") else []) + odata["t_ord"]
                                if not all(open_orders.get(i) is None for i in cids):
                                    continue
                            removed.append(oid)
                    for oid in removed:
                        logging.warning(f"Removing outdated order {oid}", color="yellow")
                        self.state["orders"].pop(oid)

                async with self.slock:
                    redundant = set(self.state["streams"]).difference(open_symbols)
                    if redundant:
                        logging.warning(f"Resetting price streams to {open_symbols}", color="yellow")
                        self.state["streams"] = open_symbols
                await self._subscribe_futures(resub=redundant)
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
                        if now < (order["crt"] + WAIT_ORDER_EXPIRY):
                            continue
                        logging.warning(f"Wait order {order_id} has expired. Removing...", on="yellow")
                        removed.append(order_id)
                        await self._cancel_order(order_id, order["sym"])
                    for order_id in removed:
                        self.state["orders"].pop(order_id)
                await asyncio.sleep(ORDER_WATCH_INTERVAL)

        asyncio.ensure_future(_watcher())

    async def _subscribe_futures(self, coin: str = None, resub=False):
        async with self.slock:
            num_streams = len(set(self.state["streams"]))
            resub = resub or (self.price_streamer is None)
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
            if not resub or not symbols:
                return

        async def _streamer():
            subs = list(map(lambda s: s.lower() + "usdt@aggTrade", symbols))
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

        self.price_streamer = asyncio.ensure_future(_streamer())

    async def _cancel_order(self, oid: str, symbol: str):
        try:
            resp = await self.client.futures_cancel_order(symbol=symbol, origClientOrderId=oid)
            logging.info(f"Cancelled order {oid}: {resp}")
        except Exception as err:
            logging.error(f"Failed to cancel order {oid}: {err}")

    async def _register_order_for_signal(self, signal: Signal):
        async with self.olock:
            self.sig_cache.expire()
            # Same provider can't give signal for same symbol within 20 seconds
            key = f"{signal.coin}_{signal.tag}"
            if self.sig_cache.get(key) is not None:
                return False
            for odata in self.state["orders"].values():
                # Check whether a matching order exists and is live
                if odata.get("sym") != f"{signal.coin}USDT" or odata.get("parent") is not None:
                    continue
                is_buy = odata["sl"] < odata["ent"]
                if (signal.is_short and is_buy) or (signal.is_long and not is_buy):
                    logging.warning(f"Ignoring discrepant signal for {signal.coin}", on="red")
                    return False
            self.sig_cache[key] = ()
            return True

    async def _unregister_order(self, signal: Signal):
        async with self.olock:
            self.sig_cache.pop(f"{signal.coin}_{signal.tag}", None)

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
