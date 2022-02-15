import asyncio
import json
import logging
import os
import signal

from trader.logger import DEFAULT_LOGGER
from trader.telegram import TeleTrader

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_PATH = os.getenv("SESSION_PATH")
STATE_PATH = os.getenv("STATE_PATH")
TEST = os.getenv("TEST")

# fine to use this logger in async - not looking for performance
DEFAULT_LOGGER.setLevel(logging.INFO)
loop = asyncio.get_event_loop()

state = {}
if STATE_PATH is not None and os.path.exists(STATE_PATH):
    with open(STATE_PATH) as fd:
        state = json.load(fd)


async def main():
    client = TeleTrader(API_ID, API_HASH, session=SESSION_PATH, state=state, loop=loop)
    await client.init(API_KEY, API_SECRET)
    try:
        await client.run()
    except asyncio.CancelledError:
        pass

try:
    task = asyncio.ensure_future(main())
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    loop.run_until_complete(task)
finally:
    if STATE_PATH is not None:
        with open(STATE_PATH, "w") as fd:
            json.dump(state, fd, indent=2)
