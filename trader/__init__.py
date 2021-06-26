import asyncio
import math
import json
import uuid
import time
import traceback

from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException
from cachetools import TTLCache

from .errors import EntryCrossedException, InsufficientQuantityException, PriceUnavailableException
from .logger import DEFAULT_LOGGER as logging
from .signal import Signal
from .user_stream import UserStream
from .utils import NamedLock

WAIT_ORDER_EXPIRY = 24 * 60 * 60
NEW_ORDER_TIMEOUT = 5 * 60
ORDER_WATCH_INTERVAL = 2 * 60
ORDER_MAX_RETRIES = 10
ORDER_RETRY_SLEEP = 5
PRICE_SLIPPAGE = 1.5  # skip order if funds allocated exceeds estimation by this much
MAX_TARGETS = 5


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


class Trade:
    @classmethod
    def entry(cls, tag, coin, entry, quantity, leverage, side):
        fund = quantity * entry / leverage
        return (f"📣 {tag}: {side} {quantity} {coin} x{leverage} @ ${round(entry, 5)}\n"
                f"💰 ${round(fund, 2)}")

    @classmethod
    def target(cls, tag, coin, entry, q_entry, leverage, target, q_target, is_long, is_sl=False):
        side = "SELL" if is_long else "BUY"
        initial = q_target * entry
        final = q_target * target
        profit = final - initial
        if not is_long:
            profit = -profit
        percent = profit / (initial / leverage)
        if profit > 0:
            s = "🤑"
            msg = f"✅ Profits: ${round(profit, 3)} ({round(percent * 100, 2)}%)"
        elif is_sl and q_target < q_entry:
            s = "⚠️"
            msg = "🟠 Stopped at entry after taking profits"
        else:
            s = "‼️"
            msg = f"🛑 Loss: ${round(profit, 3)} ({round(percent * 100, 2)}%)"
        return (f"{s} {tag}: {side} {q_target} {coin} x{leverage} @ {round(target, 5)}\n{msg}")


class FuturesTrader:
    def __init__(self):
        self.client: AsyncClient = None
        self.state: dict = None
        self.prices: dict = {}
        self.symbols: dict = {}
        self.price_streamer = None
        self.clocks = NamedLock()
        self.olock = asyncio.Lock()  # lock to place only one order at a time
        self.slock = asyncio.Lock()  # lock for stream subscriptions
        self.order_queue = asyncio.Queue()
        # cache to disallow orders with same symbol, entry and first TP for 10 mins
        self.sig_cache = TTLCache(maxsize=100, ttl=600)
        self.balance = 0
        self.results_handler = None

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

    async def queue_signal(self, signal: Signal):
        await self.order_queue.put(signal)

    async def close_trades(self, tag, coin=None):
        if coin is None:
            logging.info(f"Attempting to close all trades associated with channel {tag}", color="yellow")
        else:
            logging.info(f"Attempting to close {coin} trades associated with channel {tag}", color="yellow")
        async with self.olock:
            removed = []
            for order_id, order in self.state["orders"].items():
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
                quantity = 0
                for tid, q in zip(order["t_ord"], order["t_q"]):
                    if not self.state["orders"].get(tid, {}).get("filled"):
                        quantity += q
                try:
                    if quantity > 0:
                        resp = await self.client.futures_create_order(
                            symbol=order["sym"],
                            positionSide="LONG" if order["side"] == "BUY" else "SHORT",
                            side="SELL" if order["side"] == "BUY" else "BUY",
                            type=OrderType.MARKET,
                            quantity=self._round_qty(order["sym"], quantity),
                        )
                    else:
                        resp = await self.client.futures_cancel_order(
                            symbol=order["sym"],
                            origClientOrderId=order_id,
                        )
                    logging.info(f"Closed position for order {order}, resp: {resp}", color="yellow")
                except Exception as err:
                    logging.error(f"Failed to close position for order {order}, err: {err}")
            for oid in removed:
                self.state["orders"].pop(oid, None)
            if not removed:
                logging.info(f"Didn't find any matching positions for {tag} to close", color="yellow")

    async def _gather_orders(self):
        async def _gatherer():
            logging.info("Waiting for orders to be queued...")
            while True:
                signal = await self.order_queue.get()
                if self.symbols.get(f"{signal.coin}USDT") is None:
                    logging.info(f"Unknown symbol {signal.coin} in signal", color="yellow")
                    continue

                async def _process(signal):
                    # Process one order at a time for each symbol
                    async with self.clocks.lock(signal.coin):
                        registered = await self._register_order_for_signal(signal)
                        if not registered:
                            logging.info(f"Ignoring signal from {signal.tag} because order exists "
                                         f"for {signal.coin}", color="yellow")
                            return
                        for i in range(ORDER_MAX_RETRIES):
                            try:
                                await self._place_order(signal)
                                return
                            except PriceUnavailableException:
                                logging.info(f"Price unavailable for {signal.coin}", color="red")
                            except EntryCrossedException as err:
                                logging.info(f"Price went too fast ({err.price}) for signal {signal}", color="yellow")
                            except InsufficientQuantityException as err:
                                logging.info(
                                    f"Allocated ${round(err.alloc_funds, 2)} for {err.alloc_q} {signal.coin} "
                                    f"but requires ${round(err.est_funds, 2)} for {err.est_q} {signal.coin}",
                                    color="red")
                            except Exception as err:
                                logging.error(f"Failed to place order: {traceback.format_exc()} {err}")
                                break  # unknown error - don't block future signals
                            if i < ORDER_MAX_RETRIES - 1:
                                await asyncio.sleep(ORDER_RETRY_SLEEP)
                        await self._unregister_order(signal)

                asyncio.ensure_future(_process(signal))

        asyncio.ensure_future(_gatherer())

    async def _place_order(self, signal: Signal):
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
        signal.correct(price)
        alloc_funds = self.balance * signal.fraction
        quantity = alloc_funds / (price / signal.leverage)
        logging.info(f"Corrected signal: {signal}", color="cyan")
        qty = self._round_qty(symbol, quantity)
        est_funds = qty * signal.entry / signal.leverage
        if (est_funds / alloc_funds) > PRICE_SLIPPAGE:
            raise InsufficientQuantityException(quantity, alloc_funds, qty, est_funds)

        order_id = OrderID.wait() if signal.wait_entry else OrderID.market()
        params = {
            "symbol": symbol,
            "positionSide": "LONG" if signal.is_long else "SHORT",
            "side": "BUY" if signal.is_long else "SELL",
            "type": OrderType.MARKET,
            "quantity": qty,
            "newClientOrderId": order_id,
        }

        if (signal.is_long and price > signal.max_entry) or (signal.is_short and price < signal.max_entry):
            raise EntryCrossedException(price)

        if signal.wait_entry:
            logging.info(f"Placing stop limit order for {signal.coin} (price @ {price}, entry @ {signal.entry})")
            params["type"] = OrderType.STOP
            params["stopPrice"] = self._round_price(symbol, signal.entry)
            params["price"] = self._round_price(symbol, signal.max_entry)
        else:
            logging.info(f"Placing market order for {signal.coin} (price @ {price}, entry @ {signal.entry}")

        async with self.olock:  # Lock only for interacting with orders
            try:
                resp = await self.client.futures_create_order(**params)
                self.state["orders"][order_id] = {
                    "id": resp["orderId"],
                    "qty": float(resp["origQty"]),
                    "sym": symbol,
                    "side": params["side"],
                    "ent": signal.entry if signal.wait_entry else price,
                    "sl": signal.sl,
                    "tgt": signal.targets,
                    "fnd": alloc_funds,
                    "lev": signal.leverage,
                    "tag": signal.tag,
                    "crt": int(time.time()),
                    "t_ord": [],
                    "t_q": [],
                }
                logging.info(f"Created order {order_id} for signal: {signal}, "
                             f"params: {json.dumps(params)}, resp: {resp}")
            except Exception as err:
                logging.error(f"Failed to create order for signal {signal}: {err}, "
                              f"params: {json.dumps(params)}")
                if isinstance(err, BinanceAPIException) and err.code == -2021:
                    raise EntryCrossedException(price)

    async def _place_collection_orders(self, order_id):
        await self._place_sl_order(order_id)
        async with self.olock:
            odata = self.state["orders"][order_id]
            await self.results_handler(Trade.entry(
                odata["tag"], odata["sym"], odata["ent"], odata["qty"], odata["lev"], odata["side"]))
            if odata.get("t_ord"):
                logging.warning(f"TP order(s) already exist for parent {order_id}")
                return

            targets = odata["tgt"][:MAX_TARGETS]
            remaining = quantity = odata["qty"]
            for i, tgt in enumerate(targets):
                quantity *= 0.5
                # NOTE: Don't close position (as it'll affect other orders)
                if i == len(targets) - 1:
                    quantity = self._round_qty(odata["sym"], remaining)
                else:
                    quantity = self._round_qty(odata["sym"], quantity)
                tgt_order_id = await self._create_target_order(
                    order_id, odata["sym"], odata["side"], tgt, quantity)
                if tgt_order_id is None:
                    continue
                odata["t_ord"].append(tgt_order_id)
                odata["t_q"].append(quantity)
                self.state["orders"][tgt_order_id] = {
                    "parent": order_id,
                    "filled": False,
                }
                remaining -= quantity

    async def _create_target_order(self, order_id, symbol, side, tgt_price, rounded_qty):
        tgt_order_id = OrderID.target()
        params = {
            "symbol": symbol,
            "type": OrderType.LIMIT,
            "timeInForce": "GTC",
            "positionSide": "LONG" if side == "BUY" else "SHORT",
            "side": "SELL" if side == "BUY" else "BUY",
            "newClientOrderId": tgt_order_id,
            "price": self._round_price(symbol, tgt_price),
            "quantity": rounded_qty,
        }
        try:
            resp = await self.client.futures_create_order(**params)
            logging.info(f"Created limit order {tgt_order_id} for parent {order_id}, "
                         f"resp: {resp}, params: {json.dumps(params)}")
            return tgt_order_id
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
            async with self.olock:
                o = self.state["orders"].get(order_id)
                if o is None:
                    logging.warning(f"Received order {order_id} but missing in state")
                    return
            if info["X"] == "FILLED":
                if OrderID.is_wait(order_id) or OrderID.is_market(order_id):
                    entry = float(info["ap"])
                    logging.info(f"Placing TP/SL orders for fulfilled order {order_id} (entry: {entry})", color="green")
                    async with self.olock:
                        self.state["orders"][order_id]["ent"] = entry
                    await self._place_collection_orders(order_id)
                elif OrderID.is_stop_loss(order_id):
                    async with self.olock:
                        logging.info(f"Order {order_id} hit stop loss. Removing TP orders...", color="red")
                        sl = self.state["orders"].pop(order_id)
                        parent = self.state["orders"].pop(sl["parent"])
                        for oid in parent["t_ord"]:
                            self.state["orders"].pop(oid, None)  # It might not exist
                            await self._cancel_order(oid, parent["sym"])
                        await self.results_handler(
                            Trade.target(parent["tag"], parent["sym"], parent["ent"], parent["qty"],
                                         parent["lev"], float(info["ap"]), float(info["q"]),
                                         is_long=parent["side"] == "BUY", is_sl=True))
                elif OrderID.is_target(order_id):
                    logging.info(f"TP order {order_id} hit.", color="green")
                    await self._move_stop_loss(order_id)

    async def _move_stop_loss(self, tp_id: str):
        async with self.olock:
            tp = self.state["orders"][tp_id]
            tp["filled"] = True
            parent = self.state["orders"][tp["parent"]]
            targets = parent["t_ord"]
            if tp_id not in targets:
                if parent.get("s_ord") is None:
                    logging.warning(f"SL doesn't exist for order {parent}")
                    return
                logging.warning(f"Couldn't find TP order {tp_id} in parent {parent}, closing trade", color="red")
                await self.close_trades(parent["tag"], parent["sym"].replace("USDT", ""))
                return

            idx = targets.index(tp_id)
            await self.results_handler(
                Trade.target(parent["tag"], parent["sym"], parent["ent"], parent["qty"],
                             parent["lev"], parent["tgt"][idx], parent["t_q"][idx],
                             is_long=parent["side"] == "BUY"))

            if tp_id == targets[-1]:
                logging.info(f"All TP orders hit. Removing parent {parent}")
                parent = self.state["orders"].pop(tp["parent"])
                for oid in parent["t_ord"]:
                    self.state["orders"].pop(oid, None)  # It might not exist
                self.state["orders"].pop(parent["s_ord"])
                await self._cancel_order(parent["s_ord"], parent["sym"])
                return
            else:
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
                "positionSide": "LONG" if odata["side"] == "BUY" else "SHORT",
                "side": "SELL" if odata["side"] == "BUY" else "BUY",
                "type": OrderType.STOP_MARKET,
                "newClientOrderId": sl_order_id,
                "stopPrice": self._round_price(symbol, new_price if new_price is not None else odata["sl"]),
                "quantity": self._round_qty(symbol, (quantity if quantity is not None else odata["qty"])),
            }
            for _ in range(2):
                try:
                    resp = await self.client.futures_create_order(**params)
                    odata["s_ord"] = sl_order_id
                    self.state["orders"][sl_order_id] = {
                        "parent": parent_id,
                        "filled": False,
                    }
                    logging.info(f"Created SL order {sl_order_id} for parent {parent_id}, "
                                 f"resp: {resp}, params: {json.dumps(params)}")
                    break
                except Exception as err:
                    logging.error(f"Failed to create SL order for parent {parent_id}: {err}, "
                                  f"params: {json.dumps(params)}")
                    if isinstance(err, BinanceAPIException) and err.code == -2021:  # price is around SL now
                        logging.info(f"Placing market order for parent {parent_id} "
                                     "after attempt to create SL order", color="yellow")
                        params.pop("stopPrice")
                        params["type"] = OrderType.MARKET

    async def _watch_orders(self):
        async def _watcher():
            while True:
                try:
                    open_symbols = await self._expire_outdated_orders_and_get_open_symbols()
                except Exception as err:
                    logging.exception(f"Failed to expire outdated orders: {err}")
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
                        logging.warning(f"Wait order {order_id} has expired. Removing...", color="yellow")
                        removed.append(order_id)
                        await self._cancel_order(order_id, order["sym"])
                    for order_id in removed:
                        self.state["orders"].pop(order_id)
                await asyncio.sleep(ORDER_WATCH_INTERVAL)

        asyncio.ensure_future(_watcher())

    async def _expire_outdated_orders_and_get_open_symbols(self):
        open_symbols = []
        open_orders, positions = {}, {}
        sl_orders = []
        async with self.olock:
            resp = await self.client.futures_account()
            for pos in resp["positions"]:
                amount, side = float(pos["positionAmt"]), pos["positionSide"]
                if side == "BOTH" or amount == 0:
                    continue
                positions[pos["symbol"] + side] = amount
            resp = await self.client.futures_get_open_orders()
            for order in resp:
                open_orders[order["clientOrderId"]] = order
            logging.info(f"Checking {len(open_orders)} orders for {len(positions)} positions: {positions}")
            for oid, order in open_orders.items():
                odata = self.state["orders"].get(oid)
                if OrderID.is_market(oid) or OrderID.is_wait(oid):
                    open_symbols.append(order["symbol"][:-4])
                elif odata and (OrderID.is_target(oid) or OrderID.is_stop_loss(oid)):
                    odata["filled"] = False

            removed = []
            for oid, odata in list(self.state["orders"].items()):
                if (OrderID.is_target(oid) or OrderID.is_stop_loss(oid)):
                    if self.state["orders"].get(odata["parent"]) is None:
                        logging.warning(f"Order {oid} is now an orphan. Flagging for removal")
                        removed.append(oid)
                if not (OrderID.is_wait(oid) or OrderID.is_market(oid)):
                    continue
                if open_orders.get(oid) is not None:  # only filled orders
                    continue
                if (time.time() - odata["crt"]) < NEW_ORDER_TIMEOUT:  # must be old
                    continue
                if odata.get("s_ord") is None:  # must have stop loss order
                    continue
                side = "LONG" if odata["side"] == "BUY" else "SHORT"
                if not positions.get(odata["sym"] + side):
                    logging.warning(f"Order {oid} missing in open positions. Flagging for removal")
                    removed.append(oid)
                    continue
                children = [odata["s_ord"]] + odata["t_ord"]
                for cid in children:
                    if open_orders.get(cid) is not None:  # ignore open orders
                        continue
                    is_filled = False
                    try:
                        cdata = await self.client.futures_get_order(
                            symbol=odata["sym"], origClientOrderId=cid)
                        is_filled = cdata["status"] == "FILLED"
                    except Exception as err:
                        logging.warning(f"Error fetching order {cid} for parent {odata}: {err}")
                    if is_filled:
                        self.state["orders"][cid] = {
                            "parent": oid,
                            "filled": True,
                        }
                    else:
                        logging.info(f"Missing order {cid} detected for parent {oid}", color="yellow")
                        self.state["orders"].pop(cid, None)
                order_hit = []
                for i in range(len(children)):
                    cdata = self.state["orders"].get(children[i])
                    order_hit.append(cdata["filled"] if cdata else False)
                    if cdata is not None:
                        continue
                    if i == 0:
                        sl_orders.append({"id": oid})
                        continue
                    tgt_id = await self._create_target_order(
                        oid, odata["sym"], odata["side"], odata["tgt"][i - 1], odata["t_q"][i - 1])
                    if tgt_id is not None:
                        odata["t_ord"][i - 1] = tgt_id
                        self.state["orders"][tgt_id] = {
                            "parent": oid,
                            "filled": False,
                        }
                if order_hit[0] or all(order_hit[1:]):  # All TPs or SL hit
                    removed.append(oid)

            for oid in removed:
                logging.warning(f"Removing outdated order {oid}", color="yellow")
                parent = self.state["orders"].pop(oid, None)
                if not (OrderID.is_wait(oid) or OrderID.is_market(oid)):
                    continue
                if parent is None:
                    continue
                sym = parent["sym"]
                for cid in [parent["s_ord"]] + parent["t_ord"]:
                    logging.warning(f"Removing outdated child {cid}", color="yellow")
                    c = self.state["orders"].pop(cid, None)
                    if c and not c["filled"]:
                        await self._cancel_order(cid, sym)

            for o in sl_orders:
                oid = o["id"]
                for i, tid in enumerate(self.state["orders"][oid]["t_ord"]):
                    if self.state["orders"][tid]["filled"]:
                        o["tp"] = tid
                        break

        for o in sl_orders:
            if o.get("tp"):
                await self._move_stop_loss(o["tp"])
            else:
                await self._place_sl_order(o["id"])

        return open_symbols

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
            key = self._cache_key(signal)
            if self.sig_cache.get(key) is not None:
                return False
            self.sig_cache[key] = ()
            return True

    async def _unregister_order(self, signal: Signal):
        async with self.olock:
            self.sig_cache.pop(self._cache_key(signal), None)

    def _cache_key(self, signal: Signal):
        return f"{signal.coin}_{signal.targets[0]}"  # coin and first target for filter

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
