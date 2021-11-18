import math
import re

from .errors import CloseTradeException, MoveStopLossException, ModifyTargetsException


COMMAND_CHANNEL = -1001271281417


def extract_numbers(line: str, symbol=""):
    res = list(map(float, re.findall(r'(\.?\d+(?:\.\d+)?)', line.replace(",", ".").replace(". ", "."))))
    if re.search(r"\d+", symbol):
        res.pop(0)
    return res


def extract_symbol(line: str, prefix="#", suffix="usdt"):
    return re.search((prefix if prefix else "") + r"([a-z0-9]+)[ ]*(\/|\|)?[ ]*?" + (suffix if suffix else ""), line)


def extract_optional_number(line: str):
    res = re.search(r"(\.?\d+(?:\.\d+)?)", line.replace(",", "."))
    return float(res[1]) if res else None


class Signal:
    MIN_PRECISION = 6
    MIN_LEVERAGE = 20  # so that I have sufficient margin
    DEFAULT_LEVERAGE = 20
    DEFAULT_STOP = 0.08
    DEFAULT_RISK = 0.01
    DEFAULT_RISK_FACTOR = 1

    def __init__(self, coin, sl, entry=None, targets=[], leverage=None, risk_factor=None,
                 is_long=None, percent_targets=False, force_limit=False, stop_percent=False, tag=None):
        self.coin = coin.upper()
        self.entry = entry
        self.percent_targets = percent_targets
        self.sl = sl
        self.stop_pct = stop_percent if stop_percent else self.DEFAULT_STOP
        self.targets = targets
        self.leverage = max(leverage if leverage else self.DEFAULT_LEVERAGE, self.MIN_LEVERAGE)
        self.tag = tag
        self.fraction = 0
        self.risk = self.DEFAULT_RISK * (risk_factor if risk_factor else self.DEFAULT_RISK_FACTOR)
        self.force_limit_order = force_limit
        self._is_long = is_long
        if self.is_partial:
            return
        prev = self.entry
        for t in self.targets:
            assert (t > prev if self.is_long else t < prev)
            prev = t

    @classmethod
    def sanitized(cls, text: str) -> str:
        return text.lower().replace("__", "").replace("**", "").replace("\ufeff", "")

    @classmethod
    def parse(cls, chat_id: int, text: str, risk_factor=None):
        ch = CHANNELS.get(chat_id)
        if not ch:
            return
        sig = ch.parse(cls.sanitized(text))
        if risk_factor is not None and risk_factor > 0:
            sig.risk_factor = (sig.risk / cls.DEFAULT_RISK) * risk_factor  # maintain per-channel risk bias
        return sig

    @property
    def is_partial(self):
        return self._is_long is not None

    @property
    def is_long(self):
        if self.is_partial:
            return self._is_long
        return self.sl < self.entry

    @property
    def is_short(self):
        return not self.is_long

    @property
    def symbol(self):
        return f"{self.coin}USDT"

    @property
    def risk_factor(self):
        return self.risk / self.DEFAULT_RISK

    @risk_factor.setter
    def risk_factor(self, factor):
        self.risk = self.DEFAULT_RISK * factor

    @property
    def risk_reward(self):
        return abs((self.targets[-1] - self.entry) / (self.entry - self.sl))

    @property
    def max_entry(self):
        # 5% offset b/w entry and first target
        return self.entry + (self.targets[0] - self.entry) * 0.05

    def correct(self, price):
        if self.is_partial and self.entry is None:
            self.entry = price
        else:
            self.entry *= self.factor(self.entry, price)
        self.sl *= self.factor(self.sl, price)
        if self.percent_targets:
            diff = self.entry - self.sl
            self.targets = list(map(lambda i: self.entry + diff * i / 100, self.targets))
        self.targets = list(map(lambda i: round(i * self.factor(i, price), 10), self.targets))
        self.wait_entry = (self.is_long and price < self.entry) or (self.is_short and price > self.entry)
        percent = self.entry / self.sl
        percent = percent - 1 if self.is_long else 1 - percent
        self.fraction = self.risk / (percent * self.leverage)

    def factor(self, sig_p, mark_p):
        # Fix for prices which are human-readable at times when we'll find lack of some precision
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
        return (f"{self.tag}: {self.coin} x{self.leverage} ({round(self.fraction * 100, 2)}%, "
                f"e: {self.entry}, sl: {self.sl}, targets: {self.targets})")


class MAIN:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "cancel " in text or "close " in text:
            raise CloseTradeException(tag=text.split(" ")[1].lower())

        sig, tag, parts = [None] * 3
        if text.startswith("long") or text.startswith("short"):
            parts = text.split(" ")
            is_long = parts.pop(0) == "long"
            sig = Signal(parts.pop(0), 0, is_long=is_long)
            res = extract_optional_number(parts[0])
            if res:
                parts.pop(0)
                sig.entry = res
        if text.startswith("change"):
            parts = text.split(" ")[1:]
            tag = parts.pop(0)
        assert parts
        if parts[0] == "sl":
            parts.pop(0)
            res = extract_optional_number(parts.pop(0))
            if sig is None:
                raise MoveStopLossException(tag, res)
            assert res
            sig.sl = res
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
        if "force" in parts:
            sig.force_limit_order = True
        return sig


CHANNELS = {
    COMMAND_CHANNEL: MAIN,
}
