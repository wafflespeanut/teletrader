import asyncio
import json
import logging
import os

from trader.telegram import TeleTrader
from trader import Signal, FuturesTrader

# API_ID = int(os.getenv("API_ID"))
# API_HASH = os.getenv("API_HASH")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SESSION_PATH = os.getenv("SESSION_PATH")
STATE_PATH = os.getenv("STATE_PATH")

# fine to use this logger in async - not looking for performance
logging.getLogger().setLevel(logging.INFO)
loop = asyncio.get_event_loop()
# client = TeleTrader(API_ID, API_HASH, SESSION_PATH, STATE_PATH, loop=loop)
# loop.run_until_complete(client.run())

state = {}
if STATE_PATH is not None and os.path.exists(STATE_PATH):
    with open(STATE_PATH) as fd:
        state = json.load(fd)


async def main():
    t = FuturesTrader()
    await t.init(API_KEY, API_SECRET, state=state, test=True, loop=loop)
    await t.place_order(Signal("BTC", 39793.5, 39792, [40000, 41000, 41500], wait_entry=True))
    await asyncio.sleep(3600)

try:
    loop.run_until_complete(main())
finally:
    if STATE_PATH is not None:
        with open(STATE_PATH, "w") as fd:
            json.dump(state, fd, indent=2)
