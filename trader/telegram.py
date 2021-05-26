import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Message

from . import FuturesTrader


class TeleTrader(TelegramClient):
    def __init__(self, api_id, api_hash, session=None, state={}, loop=None):
        self.state = state or {}
        self.trader = FuturesTrader()
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

    async def _handler(self, event: Message):
        logging.info(f"New message (chat ID: {event.chat_id}):\n{event.text}")
        signal = self.trader.get_signal(event.chat_id, event.text)
        if not signal:
            return
        await self.trader.place_order(signal)
