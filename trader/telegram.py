from telethon import TelegramClient, events
from telethon.tl.custom import Message

from . import FuturesTrader
from .errors import CloseTradeException
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
        try:
            if CHANNELS.get(event.chat_id):
                tag = CHANNELS[event.chat_id].__name__
            sig = Signal.parse(event.chat_id, event.text)
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
                    logging.exception(f"Unable to parse previous message >>> {reply.text} <<< as signal")
                    return
            logging.info(f"Received message for closing {coin if coin else 'all'} "
                         f"trades from {err.tag}: {event.text}", color="red")
            await self.trader.close_trades(err.tag, coin)
        except AssertionError:
            logging.info(f"Ignoring message from {tag} as requirements are not met", color="white")
        except Exception:
            logging.exception(f"Ignoring message from {tag} due to parse failure: {event.text}")

        if sig is None:
            return

        logging.info(f"Received signal {sig}", color="cyan")
        await self.trader.queue_signal(sig)
