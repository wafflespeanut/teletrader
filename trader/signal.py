import math
import re

from .errors import CloseTradeException
from .logger import DEFAULT_LOGGER as logging


def extract_numbers(line: str, symbol=""):
    res = list(map(float, re.findall(r'(\d+(?:\.\d+)?)', line.replace(",", "."))))
    if re.search(r"\d+", symbol):
        res.pop(0)
    return res


def extract_symbol(line: str, prefix="#", suffix="usdt"):
    return re.search((prefix if prefix else "") + r"([a-z0-9]+)(\/|\|)?[ ]*?" + (suffix if suffix else ""), line)


def extract_optional_number(line: str):
    res = re.search(r"(\d+(?:\.\d+)?)", line.replace(",", "."))
    return float(res[1]) if res else None


class Signal:
    MIN_PRECISION = 6
    MIN_LEVERAGE = 5
    DEFAULT_LEVERAGE = 10
    DEFAULT_STOP = 0.08
    DEFAULT_RISK = 0.01

    def __init__(self, coin, entries, targets, sl=None, leverage=None, risk_factor=1, tag=None):
        self.coin = coin.upper()
        self.entries = sorted(entries)
        self.sl = sl
        self.targets = targets
        self.leverage = max(leverage if leverage else self.DEFAULT_LEVERAGE, self.MIN_LEVERAGE)
        self.tag = tag
        self.fraction = 0
        self.risk = self.DEFAULT_RISK * risk_factor
        prev = self.entries[0]
        for t in self.targets:
            assert (t > prev if self.is_long else t < prev)
            prev = t
        if self.sl:
            assert self.sl < self.entries[0] if self.is_long else self.sl > self.entries[-1]

    @classmethod
    def parse(cls, chat_id: int, text: str):
        ch = CHANNELS.get(chat_id)
        if not ch:
            return
        sig = ch.parse(text.lower())
        return sig

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
        self.entries = list(map(lambda i: i * self.factor(i, price), self.entries))
        self.entries.sort()
        self.targets = list(map(lambda i: i * self.factor(i, price), self.targets))
        self.wait_entry = (self.is_long and price < self.entries[0]) or (self.is_short and price > self.entries[-1])
        if self.wait_entry:
            self.entry = self.entries[0] if self.is_long else self.entries[-1]
        else:
            self.entry = self.entries[-1] if self.is_long else self.entries[0]
        if self.sl is None:
            self.sl = (self.entry * (1 - self.DEFAULT_STOP)) if self.is_long else (
                self.entry * (1 + self.DEFAULT_STOP))
            logging.warning(f"Setting {self.sl} as stop loss for {self.coin}: "
                            f"{self.entry} - {self.DEFAULT_STOP * 100}%")
        else:
            self.sl *= self.factor(self.sl, price)
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
                f"e: {self.entries}, sl: {self.sl}, targets: {self.targets})")


class BAW:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text
        c, er, sl, t, lv = [None] * 5
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
            if "leverage" in line:
                lv = extract_optional_number(line)
                lv = int(lv) if lv else None
        assert c and er and sl and t
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


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
        return Signal(c, [e], t, sl, tag=cls.__name__)


class BFP2:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        c, e, sl, t, lv = [None] * 5
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
                e = extract_optional_number(line.split("usdt")[-1])
            if "buy" in line:
                e = extract_optional_number(line.split("usdt")[-1])
            if "target" in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                lv = extract_numbers(line) or None
                if lv:
                    lv = int(lv[-1])
        assert c and e and sl and t
        return Signal(c, [e], t, sl, leverage=lv, tag=cls.__name__)


class BFS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        c, e, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "short" in line or "long" in line:
                e = extract_optional_number(line)
            if "take profit" in line:
                t = extract_numbers(line)
            if "stoploss" in line:
                sl = extract_optional_number(line)
        assert c and e and sl and t
        return Signal(c, [e], t, sl, tag=cls.__name__)


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
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
                er = extract_numbers(line, symbol=c)
            if "target" in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


class BSS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "open short" in text or "open long" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, suffix=None)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "target" in line:
                t = extract_numbers(line)
            if "stoploss" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, tag=cls.__name__)


class BUSA:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert re.search(r"/usdt ((x[0-9]+)|([0-9]+x))", text)
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
                if re.search(r"\d+", c):
                    er.pop(0)
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
            c = None
            res = extract_symbol(text, prefix="close ", suffix=None)
            if res:
                c = res[1]
                if c.endswith("usdt"):
                    c = c[:-4]
                elif c.endswith("usd"):
                    raise AssertionError
            raise CloseTradeException(cls.__name__, c)

        assert "leverage" in text
        c, er, sl, t = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix="")
            if res:
                c = res[1]
                er = extract_numbers(line, symbol=c)
            if "target" in line:
                t = extract_numbers(line)
            if "stop" in line:
                sl = float(line.split(" ")[-1])
        assert c and er and sl and t
        return Signal(c, er, t, sl, tag=cls.__name__)


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


class CC:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert ("long" in text or "short" in text) and re.search(r"\dx", text)
        t = []
        c, er, sl, lv = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
                lv = int(extract_numbers(line)[-1])
            if "entry" in line:
                er = extract_numbers(line)
            if "tp" in line:
                t.append(extract_numbers(line)[-1])
            if "s/l" in line:
                sl = extract_optional_number(line)
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class CCC:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        er = []
        c, t, sl, lv = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            elif "short" in line or "long" in line:
                res = extract_symbol(line, prefix=None, suffix=None)
                c = res[1]
            if "entry" in line:
                if re.search(r"entry [0-9][^0-9]", line):
                    er.append(extract_numbers(line)[1])
                else:
                    er = extract_numbers(line)
            if "target" in line:
                t = extract_numbers(line)[:3]
            if "stop" in line:
                sl = extract_numbers(line)[-1]
            if "leverage" in line:
                lv = int(extract_numbers(line)[-1])
        assert er and c and t and sl
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


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
        lines = [line for line in map(str.strip, text.split("\n")) if line]
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if ("buy" in line or "entry" in line) and not er:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(lines[i + 1])
            if "stoploss" in line:
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t[:5], sl, leverage=20, tag=cls.__name__)


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
        return Signal(c, er, t, sl, risk_factor=0.5, tag=cls.__name__)


class CS(CM):
    pass


class CY:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "stop " in text.split("\n")[0]:
            res = extract_symbol(text, prefix=None)
            raise CloseTradeException(cls.__name__, res[1])

        assert "leverage" in text
        t = []
        c, er, sl = [None] * 3
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "buy" in line:
                er = extract_numbers(line)
            if "sell" in line:
                t = extract_numbers(line)
            if "target" in line:
                res = extract_numbers(line)
                if len(res) > 1:
                    t.append(res[-1])
            if "stop" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                lv = extract_optional_number(line)
                lv = int(lv) if lv else None
        assert c and er and sl and t
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class EBS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        t = []
        c, e, lev = [None] * 3
        lines = [line for line in map(str.strip, text.split("\n")) if line]
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
        return Signal(c, [e], t, leverage=lev, risk_factor=0.5, tag=cls.__name__)


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
        return Signal(c, er, t[:5], sl, leverage=20, tag=cls.__name__)


class FXVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        for ch in [CCS, FWP, MCVIP, PBF]:
            try:
                sig = ch.parse(text)
                sig.tag = cls.__name__
                return sig
            except CloseTradeException as err:
                err.tag = cls.__name__
                raise err
            except Exception:
                pass

        c, er, sl, lv = [None] * 4
        assert "leverage" in text
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
            if "entry" in line:
                er = extract_numbers(line)
            if "target " in line:
                t = extract_numbers(line)
            if "stop loss" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                lv = int(extract_numbers(line)[-1])
        assert c and er and sl and t
        return Signal(c, er, t, sl, leverage=lv, risk_factor=0.5, tag=cls.__name__)


class HBTCV:
    @classmethod
    def parse(cls, text: str) -> Signal:
        try:
            sig = CEP.parse(text)
            assert "✅" not in text
            sig.tag = cls.__name__
            return sig
        except CloseTradeException as err:
            err.tag = cls.__name__
            raise err
        except Exception:
            pass

        assert "binance futures" in text
        t, er = [], []
        c, sl, lv = [None] * 3
        lines = [line for line in map(str.strip, text.split("\n")) if line]
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line:
                if re.search(r"entry \d", line):
                    er.append(extract_numbers(line)[1])
                else:
                    er = extract_numbers(lines[i + 1])
                    if "1)" in lines[i + 1]:
                        er.pop(0)
                    if "%" in lines[i + 1]:
                        er.pop()
            if not t and "profit target" in line:
                j = i + 1
                while True:
                    assert "✅" not in lines[j]
                    n = extract_numbers(lines[j])
                    if len(n) < 2:
                        break
                    t.append(n[1])
                    j += 1
            elif not t and "targets" in line:
                assert "✅" not in line
                t = extract_numbers(line)
            if "stop target" in line:
                sl = extract_numbers(lines[i + 1])[1]
            if "stoploss" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                lv = extract_numbers(line)[-1]
                lv = int(lv) if lv else None
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class KBV:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "lev" in text
        t = []
        c, er, sl, lv = [None] * 4
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry" in line or "buy" in line:
                er = extract_numbers(line)
            if "sell" in line or re.search(r"take.profit", line):
                t = extract_numbers(lines[i + 1])
            if "stop loss" in line:
                sl = extract_optional_number(line)
            if "lev" in line:
                lv = int(extract_numbers(line)[-1])
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class KCE:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert re.search(r"/usdt.*x[0-9]+", text)
        t, er = [], []
        c, sl = [None] * 2
        lines = list(map(str.strip, text.split("\n")))
        for i, line in enumerate(lines):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
                if "buy" in line:
                    er = extract_numbers(line, symbol=c)
                    if f"x{int(er[-1])}" in line:
                        er.pop()
            if "entry" in line or "now" in line:
                er.extend(extract_numbers(line))
            if "target" in line:
                res = extract_numbers(line)
                if re.search(r"target \d", line):
                    res.pop(0)
                t.extend(res)
            if "sl" in line or "stop" in line:
                sl = extract_optional_number(line)
        assert c and er and t
        return Signal(c, er, t, sl, tag=cls.__name__)


class KSP(HBTCV):
    pass


class LVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "lev" in text
        c, er, t, sl, lv = [None] * 5
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "buy" in line and "fund" not in line:
                er = extract_numbers(line.replace(",", "."))
            if "target" in line:
                t = extract_numbers(line.replace(",", "."))
                t = t[:5]
            if "stop" in line:
                sl = extract_optional_number(line)
            if "lev" in line:
                lv = int(extract_numbers(line)[-1])
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


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
        lines = [line for line in map(str.strip, text.split("\n")) if line]
        for i, line in enumerate(lines):
            if "⚡️" in line:
                line = line.replace(" ", "")
                res = extract_symbol(line)
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
        return Signal(c, er, t, sl, leverage=lv, risk_factor=0.2, tag=cls.__name__)


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
        return Signal(c, er, t, sl, leverage=20, tag=cls.__name__)


class PHVIP(KSP):
    pass


class PVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        t = []
        c, er, sl, lv = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None, suffix="-usdt")
            if res:
                c = res[1]
            if "buy" in line:
                er = extract_numbers(line)
            if "target" in line:
                t.append(extract_numbers(line)[-1])
            if "leverage" in line:
                lv = int(extract_numbers(line)[-1])
            if "stop" in line:
                sl = extract_optional_number(line)
        assert c and er and sl and t
        return Signal(c, er, t, sl, leverage=lv, risk_factor=0.5, tag=cls.__name__)


class RM(HBTCV):
    pass


class RWS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        if "close " in text:
            res = extract_symbol(text, prefix=None)
            raise CloseTradeException(cls.__name__, res[1] if res else None)

        assert "leverage" in text
        try:
            sig = RM.parse(text)
            sig.tag = cls.__name__
            return sig
        except CloseTradeException as err:
            err.tag = cls.__name__
            raise err
        except Exception:
            pass

        t = []
        c, er, sl, lev = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, prefix=None)
            if res:
                c = res[1]
                er = extract_numbers(line, symbol=c)
            if "🎯" in line:
                t.append(extract_numbers(line)[-1])
            if "stop loss" in line:
                sl = extract_optional_number(line)
            if "leverage" in line:
                lev = extract_optional_number(line)
                lev = int(lev) if lev else None
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=lev, tag=cls.__name__)


class SLVIP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "binance futures" in text or "open short" in text or "open long" in text
        c, er, t, sl, lv = [None] * 5
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line, suffix="_usdt" if "_usdt" in line else "/usdt")
            if res:
                c = res[1]
            if "entry zone" in line or "open short" in line or "open long" in line:
                er = extract_numbers(line)
            if "sell zone" in line or "target" in line:
                t = extract_numbers(line)
            if "stop" in line:
                sl = extract_numbers(line)[-1]
            if "lev" in line:
                lv = int(extract_numbers(line)[-1])
        assert c and er and t and sl and lv
        return Signal(c, er, t, sl, leverage=lv, tag=cls.__name__)


class SS:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert ("#short" in text or "#long" in text) and "lev" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "#short" in line or "#long" in line:
                er = extract_numbers(line)
            if "close" in line:
                t = extract_numbers(line)
            if "stop" in line:
                sl = extract_numbers(line)[-1]
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


class VIPBB(KBV):
    pass


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
            if "buy" in line or "entry" in line:
                e = extract_optional_number(line)
            if "entry target" in line:
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
        return Signal(c, [e], t, sl, tag=cls.__name__)


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


class YCP:
    @classmethod
    def parse(cls, text: str) -> Signal:
        assert "leverage" in text
        c, er, t, sl = [None] * 4
        for line in map(str.strip, text.split("\n")):
            res = extract_symbol(line)
            if res:
                c = res[1]
            if "entry zone" in line:
                er = extract_numbers(line)
            if "targets" in line:
                t = extract_numbers(line)
            if "stop-loss" in line:
                sl = extract_numbers(line)[0]
        assert c and er and t and sl
        return Signal(c, er, t, sl, leverage=5, tag=cls.__name__)


CHANNELS = {
    -1001293741800: BAW,
    -1001418856446: BFP,
    -1001447775833: BFP2,
    -1001145827997: BFS,
    -1001397582022: BPS,
    -1001273049293: BPS,
    -1001365009067: BSS,
    -1001262300473: BUSA,
    -1001276380825: BVIP,
    -1001190501437: C,
    -1001298917999: CB,
    -1001407454871: CC,
    -1001287944622: CCC,
    -1001445041500: CCC,
    -1001498099485: CCS,
    -1001475802140: CCS,
    -1001312576400: CEP,
    -1001286357956: CEP,
    -1001390568202: CM,
    -1001147998012: CS,
    -1001324222809: CY,
    -1001332814834: EBS,
    -1001304374569: FWP,
    -1001342941479: FXVIP,
    -1001361758531: FWP,
    -1001284771688: HBTCV,
    -1001245250001: KBV,
    -1001455150678: KCE,
    -1001214337237: KSP,
    -1001332251855: LVIP,
    -1001330855662: MCVIP,
    # -1001196181927: MVIP,
    -1001368285182: PBF,
    -1001436013269: PHVIP,
    -1001309017279: PVIP,
    -1001422693443: RM,
    -1001274400840: RM,
    -1001409491832: RWS,
    -1001437242794: SLVIP,
    -1001268297640: SS,
    -1001287312554: SS,
    -1001239897393: TCA,
    -1001437351757: TCA,
    -1001130702368: VIPBB,
    -1001275757686: VIPBB,
    -1001225455045: VIPCS,
    -1001434920650: WB,
    -1001482194573: YCP,
    -1001470298343: YCP,
}
