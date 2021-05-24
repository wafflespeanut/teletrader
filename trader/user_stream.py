import json
import logging
import threading
import time
from contextlib import asynccontextmanager

import janus
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager


class UserStream:
    def __init__(self, api_key, api_secret, test=False, switch_interval_secs=3600):
        self.test = test
        self.key = api_key
        self.secret = api_secret
        self.updated_at = time.time()
        self.interval = switch_interval_secs
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
        # Switch interval should be less than 24 hours for accurate reception
        # because binance expires streams around 24 hours
        self.manager = BinanceWebSocketApiManager(
            exchange="binance.com-futures" + ("-testnet" if self.test else ""))
        self.stream_id = self.manager.create_stream(
            "arr", "!userData", api_key=self.key, api_secret=self.secret)

        logging.info("Spawning listener for futures user data")
        while True:
            now = time.time()
            if now > self.updated_at + self.interval:
                logging.info("Replaced old user stream with new stream")
                self.stream_id = self.manager.replace_stream(
                    self.stream_id, "arr", "!userData",
                    new_api_key=self.key, new_api_secret=self.secret)
                self.updated_at = now
            buf = self.manager.pop_stream_data_from_stream_buffer()
            if buf is False:
                time.sleep(0.01)
            else:
                try:
                    msg = json.loads(buf)
                    self._queue.sync_q.put(msg)
                except Exception as err:
                    logging.error(f"Failed to decode message {buf}: {err}")
