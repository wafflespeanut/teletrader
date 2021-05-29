import json
import logging
import threading
import time
from contextlib import asynccontextmanager

import janus
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager


class UserStream:
    def __init__(self, api_key, api_secret, test=False):
        self.test = test
        self.key = api_key
        self.secret = api_secret
        self._queue = janus.Queue()
        threading.Thread(target=self._start, daemon=True).start()

    @asynccontextmanager
    async def message(self):
        try:
            msg = await self._queue.async_q.get()
            yield msg
        finally:
            self._queue.async_q.task_done()

    def _start(self):
        self.exchange = "binance.com-futures" + ("-testnet" if self.test else "")
        self.manager = BinanceWebSocketApiManager(exchange=self.exchange)
        self.manager.create_stream("arr", "!userData", api_key=self.key, api_secret=self.secret)

        logging.info("Spawning listener for futures user data")
        while True:
            buf = self.manager.pop_stream_data_from_stream_buffer()
            if not buf:
                time.sleep(0.05)
                continue
            try:
                msg = json.loads(buf)
                self._queue.sync_q.put(msg)
            except Exception as err:
                logging.error(f"Failed to decode message {buf}: {err}")
