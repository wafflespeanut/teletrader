from typing import Awaitable, Callable


class OrderType:
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TP_MARKET = "TAKE_PROFIT_MARKET"


class OrderSide:
    BUY = "BUY"
    SELL = "SELL"


class OrderPositionSide:
    LONG = "LONG"
    SHORT = "SHORT"


class OrderRequest:
    def __init__(self, symbol, side, client_id, quantity, position_side):
        self.symbol = symbol
        self.side = side
        self.otype = OrderType.MARKET
        self.position_side = position_side
        self.client_id = client_id
        self.quantity = quantity
        self.price = None
        self.stop_price = None

    def limit(self, price):
        self.price = price
        self.otype = OrderType.LIMIT

    def stop_limit(self, stop_price, limit_price):
        self.otype = OrderType.STOP
        self.stop_price = stop_price
        self.limit_price = limit_price


class OrderFillEvent:
    def __init__(self, order_id, client_id, price):
        self.order_id = order_id
        self.client_id = client_id
        self.price = price


class OrderCancelEvent:
    def __init__(self, order_id, client_id):
        self.order_id = order_id
        self.client_id = client_id


class FuturesExchangeClient:
    async def init(self, api_key, api_secret, loop=None):
        raise NotImplementedError

    async def create_order(self, order: OrderRequest):
        raise NotImplementedError

    async def get_symbol_price(self, symbol: str):
        raise NotImplementedError

    async def change_leverage(self, symbol: str, leverage: int):
        raise NotImplementedError

    def normalize_price(self, symbol: str, price: float):
        raise NotImplementedError

    def normalize_quantity(self, symbol: str, quantity: float):
        raise NotImplementedError

    def register_account_balance_update(self, callback: Callable[[float], Awaitable[None]]):
        raise NotImplementedError

    def register_order_fill_update(self, callback: Callable[[OrderFillEvent], Awaitable[None]]):
        raise NotImplementedError

    def register_order_cancel_update(self, callback: Callable[[OrderCancelEvent], Awaitable[None]]):
        raise NotImplementedError
