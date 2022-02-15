import asyncio
import json
from typing import List

from .logger import DEFAULT_LOGGER as logging


class Position:
    def __init__(self, symbol: str, entry: float, sl: float, quantity: float):
        self.symbol = symbol
        self.entry = entry
        self.quantity = quantity
        self.targets: List[float] = []
        self.sl = sl
        self.target_orders = []
        self.sl_order = None


class Storage:
    def __enter__(self):
        raise NotImplementedError

    def __exit__(self, exc_type, exc, tb):
        raise NotImplementedError

    async def register_position(self, order_id: int, symbol: str, price: float, quantity: float,
                                targets: List[float], sl: float, is_soft: bool = False):
        raise NotImplementedError

    async def get_position(self, order_id: str) -> Position:
        raise NotImplementedError

    async def set_target_order(self, parent_id: str, idx: int, order_id: str):
        raise NotImplementedError

    async def set_sl_order(self, parent_id: str, order_id: str):
        raise NotImplementedError

    async def set_position_entry(self, order_id: str, price: float):
        raise NotImplementedError

    async def set_targets(self, order_id: str, targets: List[float]):
        raise NotImplementedError

    async def set_sl(self, order_id: str, sl: float):
        raise NotImplementedError


class PersistentDict(Storage):
    def __init__(self, path: str):
        self._lock = asyncio.Lock()
        self._state = {}
        self.path = path

    def __enter__(self):
        with open(self.path, "r") as fd:
            self._state = json.load(fd)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        with open(self.path, "w") as fd:
            json.dump(self._state, fd)
