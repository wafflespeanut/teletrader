import asyncio
import math
import json
import uuid
import time
import traceback

from cachetools import TTLCache

from .errors import EntryCrossedException, InsufficientQuantityException, PriceUnavailableException
from .logger import DEFAULT_LOGGER as logging
from .signal import Signal
from .utils import NamedLock

WAIT_ORDER_EXPIRY = 24 * 60 * 60
NEW_ORDER_TIMEOUT = 5 * 60
ORDER_WATCH_INTERVAL = 2 * 60
ORDER_MAX_RETRIES = 10
ORDER_RETRY_SLEEP = 5
PRICE_SLIPPAGE = 1.5  # skip order if funds allocated exceeds estimation by this much
MAX_TARGETS = 10
DEFAULT_RR = 0.4


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
        # cache to disallow orders with same symbol, entry and first TP for 12 hours
        self.sig_cache = TTLCache(maxsize=1000, ttl=12 * 3600)
        self.balance = 0
        self.results_handler = None
        self.ocount = 0

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
            logging.info(f"Attempting to close all trades tagged {tag}", color="yellow")
        else:
            logging.info(f"Attempting to close {coin} trades tagged {tag}", color="yellow")
        async with self.olock:
            removed = []
            for order_id, order in self.state["orders"].items():
                otag = order.get("tag")
                if not otag:
                    continue
                otag = otag.lower()
                if otag.split("-")[0] != tag.lower() and otag != tag.lower():
                    continue
                if coin is not None and order["sym"] != f"{coin}USDT":
                    continue
                children = [] + order["t_ord"]
                if order.get("s_ord"):
                    children.append(order["s_ord"])
                removed.append(order_id)
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

                if signal.tag:
                    signal.tag += f"-{self.ocount}"
                else:
                    signal.tag = f"{signal.coin.lower()}-{self.ocount}"
                self.ocount += 1

                async def _process(signal):
                    if signal.is_partial:
                        await self._place_partial_order(signal)
                        return

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
                        await self.results_handler(Trade.skipped(
                            signal.tag, "BUY" if signal.is_long else "SELL", signal.coin))

                asyncio.ensure_future(_process(signal))

        asyncio.ensure_future(_gatherer())

    async def _place_partial_order(self, signal: Signal):
        self._change_leverage(signal)
        # TODO

    async def _place_order(self, signal: Signal):
        await self._subscribe_futures(signal.coin)
        for _ in range(10):
            if self.prices.get(signal.coin) is not None:
                break
            logging.info(f"Waiting for {signal.coin} price to be available")
            await asyncio.sleep(1)
        if self.prices.get(signal.coin) is None:
            raise PriceUnavailableException()

        price = self.prices[signal.coin]
        signal.correct(price)
        side = "BUY" if signal.is_long else "SELL"
        if signal.risk_reward < self.state["config"].get("rr", DEFAULT_RR):
            await self.results_handler(Trade.low_rr(signal.tag, side, signal.coin, signal.risk_reward))
            return

        self._change_leverage(signal)
        alloc_funds = self.balance * signal.fraction
        quantity = alloc_funds / (price / signal.leverage)
        logging.info(f"Corrected signal: {signal}", color="cyan")
        symbol = f"{signal.coin}USDT"
        qty = self._round_qty(symbol, quantity)
        est_funds = qty * signal.entry / signal.leverage
        if (est_funds / alloc_funds) > PRICE_SLIPPAGE:
            raise InsufficientQuantityException(quantity, alloc_funds, qty, est_funds)

        order_id = OrderID.wait()
        params = {
            "symbol": symbol,
            "positionSide": "LONG" if signal.is_long else "SHORT",
            "side": side,
            "type": OrderType.MARKET,
            "newClientOrderId": order_id,
            "quantity": qty,
        }

        if (signal.force_limit_order and
            ((signal.is_long and price > signal.entry) or (signal.is_short and price < signal.entry))) or \
                ((signal.is_long and price > signal.max_entry) or (signal.is_short and price < signal.max_entry)):
            logging.info(f"Placing limit order for {signal.coin} (price @ {price}, entry @ {signal.entry})")
            params["type"] = OrderType.LIMIT
            params["price"] = self._round_price(symbol, signal.entry)
            params["timeInForce"] = "GTC"
        elif signal.force_limit_order or signal.wait_entry:
            logging.info(f"Placing stop limit order for {signal.coin} (price @ {price}, entry @ {signal.entry})")
            params["type"] = OrderType.STOP
            params["stopPrice"] = self._round_price(symbol, signal.entry)
            params["price"] = self._round_price(symbol, signal.max_entry)
        else:
            params["newClientOrderId"] = order_id = OrderID.market()
            logging.info(f"Placing market order for {signal.coin} (price @ {price}, entry @ {signal.entry}")

        async with self.olock:  # Lock only for interacting with orders
            try:
                resp = await self.client.futures_create_order(**params)
                self.state["orders"][order_id] = {
                    "id": resp["orderId"],
                    "qty": float(resp["origQty"]),
                    "sym": symbol,
                    "side": params["side"],
                    "ent": signal.entry if (signal.force_limit_order or signal.wait_entry) else price,
                    "sl": signal.sl,
                    "tgt": signal.targets,
                    "rr": signal.risk_reward,
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
                if isinstance(err, BinanceAPIException):
                    if err.code == -2021:
                        raise EntryCrossedException(price)
                    elif err.code == -2019:
                        await self.results_handler(Trade.no_margin(signal))

    async def _place_collection_orders(self, order_id):
        await self._place_sl_order(order_id)
        async with self.olock:
            odata = self.state["orders"][order_id]
            await self.results_handler(Trade.entry(
                odata["tag"], odata["sym"], odata["ent"], odata["qty"],
                odata["lev"], odata["side"], odata["sl"], odata["rr"]))
            if odata.get("t_ord"):
                logging.warning(f"TP order(s) already exist for parent {order_id}")
                return

            targets = odata["tgt"][:MAX_TARGETS]
            remaining = odata["qty"]
            for i, tgt in enumerate(targets):
                quantity = (odata["qty"] * 0.8) / len(targets)
                # NOTE: Leaving 20% for moon/gulag
                # if i == len(targets) - 1:
                #     quantity = remaining
                quantity = self._round_qty(odata["sym"], quantity)
                # NOTE: Don't close position (as it'll affect other orders)
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

            new_price = parent["ent"]  # SL to entry
            quantity = parent["qty"] - sum(parent["t_q"])  # allocated for moon
            if tp_id == targets[-1]:
                logging.info(f"All TP orders hit for parent {parent}")
                for oid in parent["t_ord"]:
                    self.state["orders"].pop(oid, None)  # It might not exist
            else:
                quantity += sum(parent["t_q"][(idx + 1):])

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

    async def _cancel_order(self, oid: str, symbol: str):
        try:
            resp = await self.client.futures_cancel_order(symbol=symbol, origClientOrderId=oid)
            logging.info(f"Cancelled order {oid}: {resp}")
        except Exception as err:
            logging.error(f"Failed to cancel order {oid}: {err}")
