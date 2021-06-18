
class PriceUnavailableException(Exception):
    pass


class EntryCrossedException(Exception):
    def __init__(self, price):
        self.price = price


class InsufficientQuantityException(Exception):
    def __init__(self, alloc_q, alloc_funds, est_q, est_funds):
        self.alloc_q = alloc_q
        self.alloc_funds = alloc_funds
        self.est_q = est_q
        self.est_funds = est_funds


class CloseTradeException(Exception):
    def __init__(self, tag, coin=None):
        self.tag = tag
        self.coin = coin.upper() if coin else None
