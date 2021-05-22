import asyncio
import logging
import os

from trader.telegram import TeleTrader

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_PATH = os.getenv("SESSION_PATH")
STATE_PATH = os.getenv("STATE_PATH")

# fine to use this logger in async - not looking for performance
logging.getLogger().setLevel(logging.INFO)
loop = asyncio.get_event_loop()
client = TeleTrader(API_ID, API_HASH, SESSION_PATH, STATE_PATH, loop=loop)
loop.run_until_complete(client.run())
