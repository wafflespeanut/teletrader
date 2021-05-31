
class PriceUnavailableException(Exception):
    pass


class EntryCrossedException(Exception):
    def __init__(self, price):
        self.price = price


class CloseTradeException(Exception):
    def __init__(self, tag, coin=None):
        self.tag = tag
        self.coin = coin
