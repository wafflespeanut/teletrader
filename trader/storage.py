import logging as std_logging
import json
import os
from typing import List

from databases import Database

from .logger import DEFAULT_LOGGER as logging

std_logging.getLogger("databases").propagate = False

SCRIPTS = {}
migration_path = "/" + os.path.join(*(__file__.split(os.sep)[:-2] + ["migrations"]))
for name in os.listdir(migration_path):
    with open(os.path.join(migration_path, name)) as fd:
        SCRIPTS[name] = fd.read()


class Storage:
    async def init(self):
        pass

    async def register_new_position(self, order_id: str, exchange_id: int, price: float, quantity: float,
                                    targets: List[float], stop_loss: float):
        pass

    async def change_targets(self, order_id: str, exchange_id: str, price: float, )


class Postgres(Storage):
    def __init__(self, url: str):
        self._db = Database(url)

    async def init(self):
        await self._db.connect()
        await self._init_migration()
        await self._migrate()

    async def register_position(self, order_id: str, exchange_id: int, price: float, quantity: float,
                                targets: List[float], stop_loss: float):
        async with self._db as conn:
            await conn.execute("""
                insert into orders
                (order_id, exchange_id, price, quantity, order_type)
                values
                (:order_id, :exchange_id, :price, :quantity, 'INIT')
            """, values={
                "order_id": order_id,
                "exchange_id": exchange_id,
                "price": price,
                "quantity": quantity,
            })

    async def _init_migration(self):
        res = await self._db.fetch_one(
            "select count(1) from pg_catalog.pg_tables t where t.tablename = 'trade_migration'")
        if not res or not res["count"]:
            await self._db.execute("""
                CREATE TABLE trade_migration (
                    id serial,
                    name varchar,
                    update_date timestamp not null default current_timestamp
                )
            """)

    async def _migrate(self):
        async with self._db.transaction():
            applied = await self._db.fetch_all("""
                select name from trade_migration order by id
            """)
            applied = [r["name"] for r in applied]
            for name, script in SCRIPTS.items():
                if name in applied:
                    continue
                logging.info(f"Executing migration {name}")
                for part in script.split(";"):
                    await self._db.execute(part)
                await self._db.execute("""
                    insert into trade_migration (name) values (:name)
                """, values={"name": name})
