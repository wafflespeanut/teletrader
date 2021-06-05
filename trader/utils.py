import asyncio
from contextlib import asynccontextmanager

from .logger import DEFAULT_LOGGER as logging


class NamedLock:
    def __init__(self):
        self._l = asyncio.Lock()
        self._locks = {}

    @asynccontextmanager
    async def lock(self, name):
        async with self._l:
            if name not in self._locks:
                self._locks[name] = asyncio.Lock()
            lock = self._locks[name]
        try:
            await lock.acquire()
            logging.info(f"Acquiring lock for {name}", color="magenta")
            yield
        finally:
            logging.info(f"Releasing lock for {name}", color="magenta")
            lock.release()
