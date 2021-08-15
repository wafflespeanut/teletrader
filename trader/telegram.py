import asyncio

from telethon import TelegramClient, events
from telethon.tl.custom import Message

from . import FuturesTrader
from .errors import CloseTradeException, MoveStopLossException, ModifyTargetsException
from .logger import DEFAULT_LOGGER as logging
from .signal import CHANNELS, Signal, RESULTS_CHANNEL


class TeleTrader(TelegramClient):
    def __init__(self, api_id, api_hash, session=None, state={}, loop=None):
        self.state = state
        self.trader = FuturesTrader()
        self.trader.results_handler = self._post_result
        super().__init__(session, api_id, api_hash, loop=loop)
        if session is None:
            logging.info("Setting test server")
            self.session.set_dc(2, "149.154.167.40", 443)
        if not self.state.get("config"):
            self.state["config"] = {}
        self.lock = asyncio.Lock()

    async def init(self, api_key, api_secret):
        logging.info("Initializing telegram client")
        await self.connect()
        user_auth = await self.is_user_authorized()
        if not user_auth:
            logging.info("User is not authorized")
        await self.start()
        logging.info("Initializing binance trader")
        await self.trader.init(api_key, api_secret, state=self.state, loop=self.loop)

    async def run(self):
        self.add_event_handler(self._handler, events.NewMessage)
        try:
            await self.run_until_disconnected()
        finally:
            await self.disconnect()

    async def _post_result(self, message: str):
        try:
            await self.send_message(RESULTS_CHANNEL, message)
        except Exception:
            logging.exception("Failed to send result")

    async def _handler(self, event: Message):
        sig, tag = None, None
        if event.chat_id == RESULTS_CHANNEL:
            try:
                await self._handle_command(event.text)
            except AssertionError:
                pass
            except Exception as err:
                logging.exception(f"Ignoring command due to parse failure: {err}")
        try:
            if CHANNELS.get(event.chat_id):
                tag = CHANNELS[event.chat_id].__name__
            async with self.lock:
                sig = Signal.parse(event.chat_id, event.text,
                                   risk_factor=self.state["config"].get("rf"))
        # except MoveStopLossException as err:
        #     pass
        # except ModifyTargetsException as err:
        #     pass
        except CloseTradeException as err:
            coin = err.coin
            reply = await event.get_reply_message()
            if reply is not None:
                try:
                    parent = Signal.parse(event.chat_id, reply.text)
                    coin = parent.coin
                except AssertionError:
                    logging.info(f"Ignoring previous message from {tag} as requirements are not met", color="white")
                    return
                except Exception:
                    logging.exception(f"Unable to parse previous message as signal:\n{reply.text}")
                    return
            logging.info(f"Received message for closing {coin if coin else 'all'} "
                         f"trades from {err.tag}: {event.text}", color="red")
            await self.trader.close_trades(err.tag, coin)
        except AssertionError:
            logging.info(f"Ignoring message from {tag} as requirements are not met:\n{event.text}", color="white")
        except Exception:
            logging.exception(f"Ignoring message from {tag} due to parse failure:\n{event.text}")

        if sig is None:
            return

        logging.info(f"Received signal {sig}", color="cyan")
        await self.trader.queue_signal(sig)

    async def _handle_command(self, text: str):
        assert text.startswith("set ")
        args = text.split(" ")
        if args[0] == "set":
            if args[1] == "risk":
                factor = float(args[2])
                async with self.lock:
                    if factor > 0:
                        self.state["config"]["rf"] = factor
                        await self._post_result(f"Risk is now set to {factor * Signal.DEFAULT_RISK * 100}%")
                    else:
                        self.state["config"].pop("rf", None)
                        await self._post_result("Risk is now reset to default")
            elif args[1] == "rr":
                rr = float(args[2])
                async with self.lock:
                    if rr > 0:
                        self.state["config"]["rr"] = rr
                        await self._post_result(f"RR is now set to {rr}")
                    else:
                        self.state["config"].pop("rr", None)
                        await self._post_result("RR is now reset to default")
