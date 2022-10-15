import unittest

from .errors import (CloseTradeException, ModifyRiskException,
                     MoveStopLossException, ModifyTargetsException)
from .signal import CHANNELS, BINANCE_USDT_FUTURES, Signal


USDT_FUTURES_PARSER = CHANNELS[BINANCE_USDT_FUTURES]


class TestSignal(unittest.TestCase):
    def _assert_signal(self, cls, text, sig):
        s = cls.parse(text)
        self.assertEqual(s.asset, sig.asset)
        self.assertEqual(s.quote, sig.quote)
        self.assertEqual(s.entry, sig.entry)
        self.assertEqual(s.is_long, sig.is_long)
        self.assertEqual(s.sl, sig.sl)
        self.assertEqual(s.targets, sig.targets)
        self.assertEqual(s.leverage, sig.leverage)
        self.assertEqual(s.risk, sig.risk)
        self.assertEqual(s.tag, sig.tag)
        self.assertEqual(s.is_long, sig.is_long)
        self.assertEqual(s.percent_targets, sig.percent_targets)


class TestUSDT_FUTURES_PARSER(TestSignal):
    def test_1(self):
        # Long AKRO at market price with SL @ $0.05
        self._assert_signal(USDT_FUTURES_PARSER, "long akro sl 0.05",
                            Signal("AKRO", "USDT", is_long=True, sl=0.05))

    def test_2(self):
        # Long CHR at $0.25 with SL @ $0.23 and targets $0.27, $0.29
        self._assert_signal(
            USDT_FUTURES_PARSER, "l chr 0.25 sl 0.23 tp 0.27 0.29",
            Signal("CHR", "USDT", 0.23, is_long=True, entry=0.25, targets=[0.27, 0.29]))

    def test_3(self):
        # Cancel/Close order/position tagged "my_tag"
        tag = None
        try:
            self._assert_signal(USDT_FUTURES_PARSER, """cancel my_tag""", None)
        except CloseTradeException as exp:
            tag = exp.tag
        self.assertEqual(tag, "my_tag")

    def test_4(self):
        # Change existing/queued order/position's SL to $25.45
        tag, sl = None, None
        try:
            self._assert_signal(USDT_FUTURES_PARSER, """change my_tag sl 25.45""", None)
        except MoveStopLossException as err:
            tag, sl = err.tag, err.price
        self.assertEqual(tag, "my_tag")
        self.assertEqual(sl, 25.45)

    def test_5(self):
        # Change existing/queued order/position's TP to $25, $30, $34
        tag, tgts = None, None
        try:
            self._assert_signal(
                USDT_FUTURES_PARSER, """change my_tag tp 25 30 34""", None)
        except ModifyTargetsException as err:
            tag, tgts = err.tag, err.targets
        self.assertEqual(tag, "my_tag")
        self.assertEqual(tgts, [25, 30, 34])

    def test_6(self):
        # Long DYDX at market price with SL @ $20.4 and targets at 75% and 150%
        # relative to entry and SL
        s = Signal("DYDX", "USDT", 20.4, targets=[75, 150],
                   is_long=True, percent_targets=True)
        self._assert_signal(USDT_FUTURES_PARSER, """long dydx sl 20.4 tp 75% 150%""", s)
        s.correct(20.573)
        self.assertEqual(s.entry, 20.573)
        self.assertEqual(s.targets, [20.70275, 20.8325])

    def test_7(self):
        # Short ATOM at $32.7 with SL @ $32.73 and targets 50% and 75%
        # relative to entry and SL
        s = Signal("ATOM", "USDT", 32.73, entry=32.7, targets=[50, 75], is_long=False,
                   percent_targets=True)
        self._assert_signal(
            USDT_FUTURES_PARSER, "s atom 32.7 sl 32.73 tp 50% 75% force", s)
        s.correct(34)
        self.assertEqual(s.targets, [32.685, 32.6775])

    def test_8(self):
        # Add another 0.5% risk to an existing/queued order/position
        tag, risk, entry = [None] * 3
        try:
            self._assert_signal(USDT_FUTURES_PARSER, """change my_tag r +0.5%""", None)
        except ModifyRiskException as err:
            tag, risk, entry = err.tag, err.risk_factor, err.entry
        self.assertEqual(tag, "my_tag")
        self.assertEqual(risk, 0.5)
        self.assertIsNone(entry)

    def test_9(self):
        # Deduct 0.5% risk from an existing/queued order/position when price reaches $15.7
        tag, risk, entry = [None] * 3
        try:
            self._assert_signal(
                USDT_FUTURES_PARSER, """change my_tag r -0.5% @ 15.7""", None)
        except ModifyRiskException as err:
            tag, risk, entry = err.tag, err.risk_factor, err.entry
        self.assertEqual(tag, "my_tag")
        self.assertEqual(risk, -0.5)
        self.assertEqual(entry, 15.7)
