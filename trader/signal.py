import math
import re

from .errors import CloseTradeException


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
        c, e, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
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
        return Signal(c, e, sl, t, fraction=0.05, leverage=20, wait_entry=True, tag=cls.__name__)


class BPS:
    chan_id = -1001397582022

    @classmethod
    def parse(cls, text: str) -> Signal:
        pass


class TCA:
    chan_id = -1001239897393

    @classmethod
    def parse(cls, text: str) -> Signal:
        pass


class MCVIP:
    chan_id = -1001330855662

    @classmethod
    def parse(cls, text: str) -> Signal:
        pass


class MVIP:
    chan_id = -1001196181927

    @classmethod
    def parse(cls, text: str) -> Signal:
        if "Close " in text:
            if "/USDT" in text:
                coin = text.split("/")[0].split(" ")[-1]
                if coin.startswith("#"):
                    coin = coin.replace("#", "")
                raise CloseTradeException(cls.__name__, coin)
            raise CloseTradeException(cls.__name__)

        assert "rage" in text
        text = text.replace("\n\n", "\n").replace("\n\n", "\n")
        c, er, sl, lv, t = [None] * 5
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            if "/USDT" in line:
                c = line.split("/")[0].split(" ")[-1]
                if c.startswith("#"):
                    c = c.replace("#", "")
            if "Entry" in line:
                er = lines[i + 1].replace(",", "").split("-")
            if "Take-Profit" in line:
                t = list(map(lambda l: float(l.replace(",", "").split(" ")[-1]), lines[(i + 1):(i + 4)]))
            if "rage" in line:
                m = re.search(r'(?i)lev.?rage.+?([0-9]+)', lines[i])
                lv = int(m[1])
            if "Stop" in line:
                sl = float(lines[i + 1].replace(",", "").split(" ")[-1])
        assert c and er and sl and lv and t
        e = float(er[-1].strip())
        if sl > e:
            e = float(er[0].strip())
        return Signal(c, e, sl, t, leverage=lv, tag=cls.__name__)


CHANNELS = [BFP, MVIP]
