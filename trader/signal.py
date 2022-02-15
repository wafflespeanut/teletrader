import math
import re

from .errors import (CloseTradeException, ModifyRiskException,
                     MoveStopLossException, ModifyTargetsException)


CHANNEL_BINANCE_USDT_FUTURES = -1001271281417


def extract_optional_number(line: str):
    res = re.search(r"(\.?\d+(?:\.\d+)?)", line.replace(",", "."))
    return float(res[1]) if res else None


class Signal:
    MIN_PRECISION = 6
    MIN_LEV = 20  # for sufficient margin
    DEFAULT_LEV = 20
    DEFAULT_RISK = 0.01
    DEFAULT_RISK_FACTOR = 1

    def __init__(self, asset, quote, sl, is_long=True, stop_percent=False, entry=None,
                 targets=[], leverage=None, risk_factor=None, soft_sl=False,
                 percent_targets=False, force_limit=False, tag=None):
        self.asset = asset.upper()
        self.quote = quote.upper()
        self.sl = sl
        self.is_long = is_long
        self.is_sl_percent = stop_percent
        self.entry = entry
        self.targets = targets
        self.leverage = max(leverage if leverage else self.DEFAULT_LEV, self.MIN_LEV)
        self.risk = self.DEFAULT_RISK * \
            (risk_factor if risk_factor else self.DEFAULT_RISK_FACTOR)
        self.soft_sl = soft_sl
        self.percent_targets = percent_targets
        self.force_limit_order = force_limit
        self.tag = tag
        self.fraction = 0

    @property
    def risk_factor(self):
        return self.risk / self.DEFAULT_RISK

    @property
    def is_short(self):
        return not self.is_long

    @risk_factor.setter
    def risk_factor(self, factor):
        self.risk = self.DEFAULT_RISK * factor

    @classmethod
    def parse(cls, chat_id: int, text: str, risk_factor=None):
        ch = CHANNELS.get(chat_id)
        if not ch:
            return
        sig = ch.parse(text)
        if risk_factor is not None and risk_factor > 0:
            sig.risk_factor = sig.risk_factor + risk_factor  # maintain per-signal bias
        return sig

    @property
    def symbol(self):
        return f"{self.coin}{self.quote}"

    def correct(self, price):
        if self.entry is None:
            self.entry = price
        else:
            self.entry *= self.factor(self.entry, price)
        self.sl *= self.factor(self.sl, price)
        if self.percent_targets:
            diff = self.entry - self.sl
            self.targets = list(map(lambda i: self.entry + diff * i / 100, self.targets))
        self.targets = list(
            map(lambda i: round(i * self.factor(i, price), 10), self.targets))
        self.wait_entry = (self.is_long and price < self.entry) or (
            self.is_short and price > self.entry)
        percent = self.entry / self.sl
        percent = percent - 1 if self.is_long else 1 - percent
        self.fraction = self.risk / (percent * self.leverage)

    def factor(self, sig_p, mark_p):
        # Fix for prices which are human-readable at times when we'll find lack of
        # some precision (i.e., 0.000578 is given as 0.578
        minima = math.inf
        factor = 1
        for i in range(self.MIN_PRECISION * 2):
            f = 1 / (10 ** (self.MIN_PRECISION - i))
            dist = abs(sig_p * f - mark_p) / mark_p
            if dist < minima:
                minima = dist
                factor = f
            else:
                break
        return factor

    def __repr__(self):
        return (f"{self.tag}: {self.coin} x{self.leverage} "
                f"({round(self.fraction * 100, 2)}%, "
                f"e: {self.entry}, sl: {self.sl}, targets: {self.targets})")


class FuturesParser:
    def __init__(self, quote):
        self.quote = quote

    def parse(self, text: str) -> Signal:
        if "cancel " in text or "close " in text:
            raise CloseTradeException(tag=text.split(" ")[1].lower())

        sig, tag, parts = [None] * 3
        if text.startswith("long") or text.startswith("short"):
            parts = text.split(" ")
            is_long = parts.pop(0) == "long"
            sig = Signal(parts.pop(0), self.quote, 0, is_long=is_long)
            res = extract_optional_number(parts[0])
            if res:
                parts.pop(0)
                sig.entry = res
        if text.startswith("change"):
            parts = text.split(" ")[1:]
            tag = parts.pop(0)
        assert parts
        if parts[0] == "r":
            parts.pop(0)
            assert (parts[0].startswith("+") or parts[0].startswith("-")) \
                and parts[0].endswith("%")
            risk = float(parts.pop(0)[:-1])
            entry = None
            if parts:
                assert parts.pop(0) == "@"
                entry = extract_optional_number(parts.pop(0))
            raise ModifyRiskException(tag, risk, entry)
        if parts[0] == "sl":
            parts.pop(0)
            res = extract_optional_number(parts.pop(0))
            if sig is None:
                raise MoveStopLossException(tag, res)
            assert res
            sig.sl = res
        if parts and parts[0] == "soft":
            sig.soft_sl = True
            parts.pop(0)
        if parts and parts[0] == "tp":
            parts.pop(0)
            targets = []
            is_percent = False
            while parts:
                res = extract_optional_number(parts[0])
                if not res:
                    break
                if parts[0].endswith("%") and not is_percent:
                    is_percent = True
                parts.pop(0)
                targets.append(res)
            targets = sorted(targets)
            if sig is None:
                raise ModifyTargetsException(tag, targets, is_percent=is_percent)
            assert targets
            sig.targets = targets
            sig.percent_targets = is_percent
        if len(parts) > 1 and parts[0] == "risk":
            parts.pop(0)
            sig.risk_factor = float(parts.pop(0))
        if "force" in parts:
            sig.force_limit_order = True
            assert sig.entry
        return sig


CHANNELS = {
    CHANNEL_BINANCE_USDT_FUTURES: FuturesParser("USDT"),
}
