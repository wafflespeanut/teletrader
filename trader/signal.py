import math
import re


class CloseTradeException(Exception):
    def __init__(self, tag, coin=None):
        self.tag = tag
        self.coin = coin


class Signal:
    MIN_PRECISION = 6

    def __init__(self, coin, entry, sl, targets, fraction=0.03, leverage=10, wait_entry=False, tag=None):
        self.coin = coin
        self.entry = entry
        self.sl = sl
        self.targets = targets
        self.fraction = fraction
        self.leverage = leverage
        self.wait_entry = wait_entry
        self.tag = tag

    @property
    def is_long(self):
        return self.sl < self.entry

    @property
    def is_short(self):
        return not self.is_long

    @property
    def max_entry(self):
        # 20% offset b/w entry and first target
        return self.entry + (self.targets[0] - self.entry) * 0.2

    def autocorrect(self, price):
        self.entry *= self._factor(self.entry, price)
        self.sl *= self._factor(self.sl, price)
        self.targets = list(
            map(lambda i: i * self._factor(i, price), self.targets))

    def _factor(self, sig_p, mark_p):
        # Fix for prices which are human-readable at times when we'll find lack of some precision
        minima = math.inf
        factor = 1
        for i in range(self.MIN_PRECISION + 1):
            f = 1 / (10 ** (self.MIN_PRECISION - i))
            dist = abs(sig_p * f - mark_p) / mark_p
            if dist < minima:
                minima = dist
                factor = f
            else:
                break
        return factor

    def __repr__(self):
        return (f"{self.coin} x{self.leverage} ({self.fraction * 100}%, "
                f"e: {self.entry}, sl: {self.sl}, targets: {self.targets})")


class BFP:
    chan_id = -1001418856446

    @classmethod
    def parse(cls, text: str) -> Signal:
        if "Close " in text:
            if text == "Close all trades":
                raise CloseTradeException(cls.__name__)
            elif "/USDT" in text:
                coin = text.split("/")[0].split("#")[-1]
                raise CloseTradeException(cls.__name__, coin)

        c, e, sl, t = [None] * 4
        for line in text.split("\n"):
            if "/USDT" in line:
                other = line.split("#")[1]
                c = other.split("/")[0]
                try:
                    e = float(line.split(" ")[-1])
                except Exception:
                    pass
            elif "Entry Point" in line:
                e = float(line.split(" ")[-1])
            elif "Targets" in line:
                t = line.split(" ")
                t = list(map(float, [t[1], t[3], t[5], t[7], t[9]]))
            elif re.search(r"[Ss]top.*(loss)?", line):
                try:
                    sl = float(line.split(" ")[-1])
                except Exception:
                    pass
        assert c and e and sl and t
        return Signal(c, e, sl, t, fraction=0.08, wait_entry=True, tag=cls.__name__)


class MVIP:
    chan_id = -1001196181927

    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "Leverage" in text
        text = text.replace("\n\n", "\n")
        lines = text.split("\n")
        assert "USDT" in lines[0]
        assert "Entry Zone" in lines[1]
        coin = lines[0].split("/")[0].split("#")[-1]
        entry = float(lines[2].split(" - ")[-1])
        t = list(map(lambda l: float(l.split(" ")[-1]), lines[4:7]))
        sl = float(lines[9].split(" ")[-1])
        return Signal(coin, entry, sl, t, tag=cls.__name__)


CHANNELS = [BFP, MVIP]
