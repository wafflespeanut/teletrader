import math
import re

from .errors import CloseTradeException


def extract_numbers(line: str):
    return list(map(float, re.findall(r'(\d+(?:\.\d+)?)', line.replace(",", "."))))


def extract_symbol(line: str, prefix="#", suffix="usdt"):
    return re.search((prefix if prefix else "") + r"([a-z0-9]+)(\/|\|)?" + (suffix if suffix else ""), line)


def extract_optional_number(line: str):
    res = re.search(r"(\d+(?:\.\d+)?)", line.replace(",", "."))
    return float(res[1]) if res else None


class Signal:
    MIN_PRECISION = 6
    DEFAULT_STOP = 0.2

    def __init__(self, coin, entries, targets, sl=None, fraction=0.03, leverage=10, tag=None):
        self.coin = coin.upper()
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
        if self.sl:
            assert self.sl < self.entries[0] if self.is_long else self.sl > self.entries[-1]

    @classmethod
    def parse(cls, chat_id: int, text: str):
        ch = CHANNELS.get(chat_id)
        if ch:
            return ch.parse(text.lower())

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
        return (f"{self.tag}: {self.coin} x{self.leverage} ({self.fraction * 100}%, "
                f"e: {self.entries}, sl: {self.sl}, targets: {self.targets})")


class BAW:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text
        c, er, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_numbers(line)[-1]
        assert c and er and sl and t
        return Signal(c, er, t, sl, tag=cls.__name__)


class BFP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        c, e, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
                e = extract_optional_number(line.split("usdt")[-1])
            if "entry point" in line:
                e = extract_optional_number(line)
            if "targets" in line:
                t = extract_numbers(line)
            if re.search(r"^stop.*(loss)", line):
                sl = extract_optional_number(line)
        assert c and e and sl and t
        return Signal(c, [e], t, sl, fraction=0.04, tag=cls.__name__)


class BPS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "exit trade" in text:
            c = None
            for line in text.split("\n"):
                res = extract_symbol(line)
                if res:
                    c = res[1]
            raise CloseTradeException(cls.__name__, c)

        assert "binance futures" in text
        assert "leverage" in text
        c, e, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
                e = extract_optional_number(line.split("usdt")[-1])
            if "target" in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and e and t and sl
        return Signal(c, [e], t, sl, tag=cls.__name__)


class BUSA:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert re.search(r"/usdt x[0-9]+", text)
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "now" in line or "entry" in line:
                er = extract_numbers(line)
            if re.search(r"target.*\d.*:", line):
                t.append(extract_numbers(line)[-1])
            elif "target" in line:
                t = extract_numbers(line)
            if "stop" in line:
                sl = extract_optional_number(line)
        assert c and er and t
        return Signal(c, er, t, sl, tag=cls.__name__)


class BVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        t = []
        c, er, sl, lev = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(line)
            if "leverage" in line:
                lev = int(extract_optional_number(line))
            if "stop" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl and lev
        return Signal(c, er, t, sl, leverage=lev, tag=cls.__name__)


class C:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "close " in text:
            raise CloseTradeException(cls.__name__, text.split(" ")[-1])

        assert "leverage" in text
        c, er, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix="")
            if res:
                c = res[1]
                er = extract_numbers(line.split("usdt")[-1])
            if "target" in line:
                t = extract_numbers(line)
            if "stop" in line:
                sl = float(line.split(" ")[-1])
        assert c and er and sl and t
        return Signal(c, er, t, sl, fraction=0.04, tag=cls.__name__)


class CB:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "futures" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(line)
            if "stoploss" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


class CCS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "futures" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "long" in line or "short" in line:
                er = extract_numbers(line)
            if "take profit" in line:
                t = extract_numbers(line)
            if "sl" in line:
                sl = extract_optional_number(line)
        assert c and er and t  # It's fine if SL is not there
        return Signal(c, er, t, sl, tag=cls.__name__)


class CEP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        c, er, sl, t = [None] * 4
        lines = list(map(str.strip, text.replace("\n\n", "\n").split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "buy" in line and not er:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(lines[i + 1])
            if "stoploss" in line:
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t[:5], sl, fraction=0.02, leverage=20, tag=cls.__name__)


class CM:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "target" in line:
                t.append(extract_numbers(line)[-1])
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t, sl, tag=cls.__name__)


class EBS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        t = []
        c, e, lev = [None] * 3
        lines = list(map(str.strip, text.replace("\n\n", "\n").split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "leverage" in line:
                lev = int(extract_optional_number(line))
            if "entry" in line:
                e = extract_numbers(lines[i + 1])[-1]
            if "target" in line:
                t.append(extract_numbers(line)[-1])
        assert c and e and t and lev
        return Signal(c, [e], t, leverage=lev, tag=cls.__name__)


class FWP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text or "futures" in text
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "buy" in line and not er:
                er = extract_numbers(line)
            if "target " in line:
                t.append(extract_numbers(line)[-1])
            if re.search(r"sto..loss", line):
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t[:5], sl, fraction=0.02, leverage=20, tag=cls.__name__)


class FXVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        for ch in [CCS, FWP, MCVIP, PBF]:
            try:
                sig = ch.parse(text)
                sig.tag = cls.__name__
                return sig
            except Exception:
                pass
        raise AssertionError


class KBV:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        t = []
        c, er, sl = [None] * 3
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "sell" in line:
                t = extract_numbers(lines[i + 1])
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


class MCVIP(C):
    pass


class MVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "close " in text and " when " not in text:
            if "/usdt" in text:
                coin = text.split("/")[0].split(" ")[-1]
                if coin.startswith("#"):
                    coin = coin.replace("#", "")
                raise CloseTradeException(cls.__name__, coin)
            raise CloseTradeException(cls.__name__)

        assert "levrage" in text or "leverage" in text
        t = []
        c, er, sl, lv = [None] * 4
        lines = list(map(str.strip, text.replace("\n\n", "\n").split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res and "⚡️" in line:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(lines[i + 1])
            if "take-profit" in line:
                j = i + 1
                while True:
                    n = extract_numbers(lines[j])
                    if len(n) < 2:
                        break
                    t.append(n[-1])
                    j += 1
            if "rage" in line:
                lv = int(extract_optional_number(line))
            if "stop" in line:
                n = extract_numbers(lines[i + 1])
                sl = float(n[-1])
        assert c and er and sl and lv and t
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class PBF:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance future" in text
        assert "leverage" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line.replace(",", "."))
            if "target" in line:
                t = extract_numbers(line.replace(",", "."))
            if "stop loss" in line:
                sl = extract_optional_number(line.replace(",", "."))
        assert c and er and t
        return Signal(c, er, t, sl, fraction=0.02, leverage=20, tag=cls.__name__)


class PTS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "target" in line:
                t.append(extract_numbers(line)[-1])
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t, sl, tag=cls.__name__)


class RM:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text
        t = []
        c, er, sl = [None] * 3
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if "⚡️" in line and res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(lines[i + 1])
            if "profit target" in line:
                j = i + 1
                while True:
                    n = extract_numbers(lines[j])
                    if len(n) < 2:
                        break
                    t.append(n[1])
                    j += 1
            if "stop target" in line:
                sl = extract_numbers(lines[i + 1])[1]
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


class TCA:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "close position" in text:
            coin = text.split("\n")[1].split(" ")[0]
            raise CloseTradeException(cls.__name__, coin)
        elif "closing all position" in text:
            raise CloseTradeException(cls.__name__)
        close_match = re.search(r"(?:close|closing) ([a-z0-9]+)", text)
        if close_match:
            coin = close_match[1]
            raise CloseTradeException(cls.__name__, coin)

        assert "leverage" in text
        c, er, t, sl, lev = [None] * 5
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(line)
            if "stop loss" in line or "sl" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                n = extract_optional_number(line)
                if n:
                    lev = int(n)
        assert c and er and t and sl and lev
        return Signal(c, er, t, sl, leverage=lev, tag=cls.__name__)


class VIPCS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "close " in text:
            coin = text.split("\n")[-1].split(" ")[-1]
            raise CloseTradeException(cls.__name__, coin)

        t = []
        c, e, sl = [None] * 3
        assert "leverage" in text
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line, prefix=("#" if "⚡" in line else None))
            if res:
                c = res[1]
            if "buy" in line:
                e = extract_optional_number(line)
            elif "entry target" in line:
                e = extract_numbers(lines[i + 1])[-1]
            if "take-profit target" in line:
                j = i + 1
                while True:
                    n = extract_numbers(lines[j])
                    if len(n) < 2:
                        break
                    t.append(n[-1])
                    j += 1
            elif "target " in line:
                res = extract_numbers(line)
                t.append(res[1])
            if "stoploss" in line:
                sl = extract_optional_number(line)
            elif "stop target" in line:
                sl = extract_numbers(lines[i + 1])[-1]
        assert c and e and t and sl
        return Signal(c, [e], t, sl, fraction=0.05, tag=cls.__name__)


class WB:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "future call" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "buy" in line:
                er = extract_numbers(line)
            if "sell" in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


CHANNELS = {
    -1001293741800: BAW,
    -1001418856446: BFP,
    -1001397582022: BPS,
    -1001297791129: BUSA,
    -1001276380825: BVIP,
    -1001190501437: C,
    -1001298917999: CB,
    -1001498099485: CCS,
    -1001475802140: CCS,
    -1001312576400: CEP,
    -1001286357956: CEP,
    -1001390568202: CM,
    -1001332814834: EBS,
    -1001304374569: FWP,
    -1001342941479: FXVIP,
    -1001368285182: PBF,
    -1001361758531: FWP,
    -1001245250001: KBV,
    -1001330855662: MCVIP,
    -1001196181927: MVIP,
    -1001147998012: PTS,
    -1001422693443: RM,
    -1001274400840: RM,
    -1001239897393: TCA,
    -1001225455045: VIPCS,
    -1001434920650: WB,
}
