import json
import os
import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Message
from telethon import utils


class TeleTrader(TelegramClient):
    def __init__(self, api_id, api_hash, session=None, state_path=None, loop=None):
        self.state = {}
        self.state_path = state_path
        if state_path is not None and os.path.exists(state_path):
            with open(state_path) as fd:
                self.state = json.load(fd)

        super().__init__(session, api_id, api_hash, loop=loop)
        if session is None:
            logging.info("Setting test server")
            self.session.set_dc(2, "149.154.167.40", 443)

        self.loop.run_until_complete(self.connect())
        user_auth = self.loop.run_until_complete(self.is_user_authorized())
        if not user_auth:
            logging.info("User is not authorized")
        self.start()

    async def run(self):
        self.add_event_handler(self.message_handler, events.NewMessage)
        try:
            await self.run_until_disconnected()
        finally:
            await self.disconnect()
            with open(self.state_path, "w") as fd:
                json.dump(self.state, fd)

    async def message_handler(self, event: Message):
        chat = await event.get_chat()
        print(f"Message from {utils.get_display_name(chat)} (ID: {event.chat_id}):\n{event.text}")
