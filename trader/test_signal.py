import unittest

from .errors import CloseTradeException, MoveStopLossException, ModifyTargetsException
from .signal import (MAIN, Signal)


class TestSignal(unittest.TestCase):
    def _assert_signal(self, cls, text, sig, risk_factor=None):
        s = cls.parse(Signal.sanitized(text))
        self.assertEqual(s.coin, sig.coin)
        self.assertEqual(s.entry, sig.entry)
        self.assertEqual(s.is_long, sig.is_long)
        self.assertEqual(s.sl, sig.sl)
        self.assertEqual(s.targets, sig.targets)
        self.assertEqual(s.leverage, sig.leverage)
        self.assertEqual(s.risk, sig.risk)
        self.assertEqual(s.force_limit_order, sig.force_limit_order)
        self.assertEqual(s.tag, sig.tag if cls == MAIN else cls.__name__)
        self.assertEqual(s.is_long, sig.is_long)
        self.assertEqual(s.percent_targets, sig.percent_targets)
        self.assertEqual(s.force_limit_order, sig.force_limit_order)


class TestMAIN(TestSignal):
    def test_1(self):
        self._assert_signal(MAIN, "long akro sl 0.05", Signal("AKRO", is_long=True, sl=0.05))

    def test_2(self):
        self._assert_signal(MAIN, "long chr 0.25 sl 0.23 tp 0.27 0.29",
                            Signal("CHR", 0.23, 0.25, [0.27, 0.29], is_long=True))

    def test_3(self):
        tag = None
        try:
            self._assert_signal(MAIN, """cancel my_tag""", None)
        except CloseTradeException as exp:
            tag = exp.tag
        self.assertEqual(tag, "my_tag")

    def test_4(self):
        tag, sl = None, None
        try:
            self._assert_signal(MAIN, """change my_tag sl 25.45""", None)
        except MoveStopLossException as err:
            tag, sl = err.tag, err.price
        self.assertEqual(tag, "my_tag")
        self.assertEqual(sl, 25.45)

    def test_5(self):
        tag, tgts = None, None
        try:
            self._assert_signal(MAIN, """change my_tag tp 25 30 34""", None)
        except ModifyTargetsException as err:
            tag, tgts = err.tag, err.targets
        self.assertEqual(tag, "my_tag")
        self.assertEqual(tgts, [25, 30, 34])

    def test_6(self):
        s = Signal("DYDX", 20.4, targets=[75, 150], is_long=True, percent_targets=True)
        self._assert_signal(MAIN, """long dydx sl 20.4 tp 75% 150%""", s)
        s.correct(20.573)
        self.assertEqual(s.entry, 20.573)
        self.assertEqual(s.targets, [20.70275, 20.8325])

    def test_7(self):
        s = Signal("ATOM", 32.73, targets=[50, 75], is_long=False, percent_targets=True, force_limit=True)
        self._assert_signal(MAIN, "short atom sl 32.73 tp 50% 75% force", s)
        s.correct(32.7)
        self.assertEqual(s.targets, [32.685, 32.6775])
