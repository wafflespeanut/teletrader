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
    def __init__(self, symbol, side, quantity, position_side):
        self.symbol = symbol
        self.side = side
        self.otype = OrderType.MARKET
        self.position_side = position_side
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


class Order:
    def __init__(self, order_id, response=None):
        self.order_id = order_id
        self.response = response


class OrderFillEvent:
    def __init__(self, order_id, symbol, price):
        self.order_id = order_id
        self.price = price
        self.symbol = symbol


class AccountBalanceEvent:
    def __init__(self, balance):
        self.balance = balance


class OrderCancelEvent:
    def __init__(self, order_id):
        self.order_id = order_id


class FuturesExchangeClient:
    async def init(self, api_key, api_secret, loop=None):
        raise NotImplementedError

    async def create_order(self, order: OrderRequest) -> Order:
        raise NotImplementedError

    # NOTE: Symbol is a representation of base and quote asset. Different exchanges
    # have different repr, hence ensure that we're passing `signal.symbol`
    async def get_symbol_price(self, symbol: str) -> float:
        raise NotImplementedError

    async def change_leverage(self, symbol: str, leverage: int) -> None:
        raise NotImplementedError

    def normalize_price(self, symbol: str, price: float) -> float:
        raise NotImplementedError

    def normalize_quantity(self, symbol: str, quantity: float) -> float:
        raise NotImplementedError

    def register_account_balance_update(
            self, callback: Callable[[float], Awaitable[None]]) -> None:
        raise NotImplementedError

    def register_order_fill_update(
            self, callback: Callable[[OrderFillEvent], Awaitable[None]]) -> None:
        raise NotImplementedError

    def register_order_cancel_update(
            self, callback: Callable[[OrderCancelEvent], Awaitable[None]]) -> None:
        raise NotImplementedError
