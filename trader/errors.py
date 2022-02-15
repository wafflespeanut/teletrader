
class PriceUnavailableException(Exception):
    pass


class EntryCrossedException(Exception):
    def __init__(self, price):
        self.price = price


class InsufficientMarginException(Exception):
    pass


class InsufficientQuantityException(Exception):
    def __init__(self, alloc_q, alloc_funds, est_q, est_funds):
        self.alloc_q = alloc_q
        self.alloc_funds = alloc_funds
        self.est_q = est_q
        self.est_funds = est_funds


# ----- Command-related exceptions ----

class CloseTradeException(Exception):
    def __init__(self, tag, coin=None):
        self.tag = tag
        self.coin = coin.upper() if coin else None


class ModifyRiskException(Exception):
    def __init__(self, tag, risk_factor=None, entry=None):
        self.tag = tag
        self.risk_factor = risk_factor
        self.entry = entry


class MoveStopLossException(Exception):
    def __init__(self, tag, price):
        self.tag = tag
        self.price = price


class ModifyTargetsException(Exception):
    def __init__(self, tag, targets, is_percent=False):
        self.tag = tag
        self.targets = targets
        self.is_percent = is_percent
