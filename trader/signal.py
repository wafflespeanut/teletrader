import math
import re

from .errors import CloseTradeException


def extract_numbers(line: str):
    return list(map(float, re.findall(r'(\d+(?:\.\d+)?)', line)))


class Signal:
    MIN_PRECISION = 6
    DEFAULT_STOP = 0.2

    def __init__(self, coin, entries, targets, sl=None, fraction=0.03, leverage=10, tag=None):
        self.coin = coin
        self.entries = sorted(entries)
        self.sl = sl
        self.targets = targets
        self.fraction = fraction
        self.leverage = leverage
        self.tag = tag
        prev = self.entries[0]
        for t in self.targets:
            assert (t > prev if self.is_long else t < prev)
            prev = t

    @property
    def is_long(self):
        return self.targets[0] > self.entries[0]

    @property
    def is_short(self):
        return not self.is_long

    @property
    def max_entry(self):
        # 20% offset b/w entry and first target
        return self.entry + (self.targets[0] - self.entry) * 0.2

    def correct(self, price):
        self.entries = list(map(lambda i: i * self._factor(i, price), self.entries))
        self.entries.sort()
        self.targets = list(map(lambda i: i * self._factor(i, price), self.targets))
        self.wait_entry = (self.is_long and price < self.entries[0]) or (self.is_short and price > self.entries[-1])
        if self.wait_entry:
            self.entry = self.entries[0] if self.is_long else self.entries[-1]
        else:
            self.entry = self.entries[-1] if self.is_long else self.entries[0]
        if self.sl is None:
            self.sl = (self.entry * (1 - self.DEFAULT_STOP)) if self.is_long else (
                self.entry * (1 + self.DEFAULT_STOP))
        else:
            self.sl *= self._factor(self.sl, price)

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
                f"e: {self.entries}, sl: {self.sl}, targets: {self.targets})")


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
        return Signal(c, [e], t, sl, fraction=0.05, leverage=20, tag=cls.__name__)


class BPS:
    chan_id = -1001397582022

    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "Binance Futures" in text
        assert "everage" in text
        c, e, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            if "/USDT" in line:
                c = line.split("/")[0].split("#")[-1].strip()
                e = float(line.split("@")[-1].strip())
            if "Target" in line:
                t = extract_numbers(line)
            if "Stop Loss" in line:
                sl = float(line.split("-")[-1].strip())
        assert c and e and t and sl
        return Signal(c, [e], t, sl, tag=cls.__name__)


class CCS:
    chan_id = -1001498099485

    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "FUTURES" in text
        text = text.replace("\n\n", "\n")
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            if "USDT" in line:
                c = line.split(" ")[0].replace("#", "").replace("USDT", "")
            if "LONG" in line or "SHORT" in line:
                er = line.split(":")[-1].strip().split("-")
            if "TAKE PROFIT" in line:
                t = extract_numbers(line)
            if "SL" in line:
                sl = float(line.split(":")[-1].strip())
        assert c and er and t  # It's fine if SL is not there
        er = list(map(lambda i: float(i.strip()), er))
        return Signal(c, er, t, sl, leverage=20, tag=cls.__name__)


class FWP:
    chan_id = -1001304374569

    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "LEVERAGE" in text or "FUTURES" in text
        text = text.replace("\n\n", "\n")
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            if "USDT" in line:
                c = line.replace("/", "").replace("#", "").replace("USDT", "")
            if "BUY" in line and not er:
                er = line.split(":")[-1].replace("$", "").split("-")
            if "TARGET " in line:
                t.append(float(re.search(r'TARGET.*: (\d+(?:\.\d+)?)', line)[1]))
            if "STOP LOSS" in line:
                sl = float(line.split(":")[-1].replace("$", "").strip())
        assert c and er and sl and t
        t = t[:5]  # Limit to 5 targets
        er = list(map(lambda i: float(i.strip()), er))
        return Signal(c, er, t, sl, fraction=0.02, leverage=20, tag=cls.__name__)


class MCVIP:
    chan_id = -1001330855662

    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "Leverage" in text
        c, er, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            if "USDT" in line:
                c = line.split(" ")[0].replace("USDT", "").replace("/", "")
                er = extract_numbers(line)
            if "Target" in line:
                t = extract_numbers(line)
            if "Stop" in line:
                sl = float(line.split(" ")[-1])
        assert c and er and sl and t
        return Signal(c, er, t, sl, fraction=0.05, leverage=20, tag=cls.__name__)


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
            if "⚡️" in line and "USDT" in line:
                c = line.split("/")[0].split(" ")[-1]
                c = c.replace("#", "").replace("USDT", "")
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
        er = list(map(lambda i: float(i.strip()), er))
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class TCA:
    chan_id = -1001239897393

    @classmethod
    def parse(cls, text: str) -> Signal:
        if "Close position" in text:
            coin = text.split("\n")[1].split(" ")[0]
            raise CloseTradeException(cls.__name__, coin)

        assert "everage" in text
        c, er, t, sl, lev = [None] * 5
        for line in map(str.strip, text.split("\n")):
            if "/USDT" in line:
                c = line.split("/")[0].split(":")[-1].strip()
            if "Entry" in line:
                er = map(str.strip, line.split(":")[-1].split("-"))
            if "Target" in line:
                t = extract_numbers(line)
            if "Stop loss" in line:
                sl = float(line.split(":")[-1].strip())
            if "everage" in line:
                lev = int(line.split(":")[-1].replace("x", "").strip())
        assert c and er and t and sl and lev
        er = list(map(float, er))
        return Signal(c, er, t, sl, leverage=lev, tag=cls.__name__)


CHANNELS = [BFP, BPS, CCS, FWP, MCVIP, MVIP, TCA]
