import asyncio
import os
import unittest

from .storage import Storage

storage = Storage(os.environ["DB_URL"])


class TestPersistence(unittest.TestCase):
    def setUp(self):
        asyncio.run(storage.init())

    def test_migration(self):
        pass
