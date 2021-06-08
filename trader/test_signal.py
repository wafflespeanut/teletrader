import unittest

from .errors import CloseTradeException
from .signal import (BAW, BFP, BPS, BUSA, BVIP, CB, CCS, CEP, CM, EBS, FWP, FXVIP,
                     KBV, MCVIP, MVIP, PTS, RM, TCA, VIPCS, WB, Signal)


class TestSignal(unittest.TestCase):
    def _assert_signal(self, cls, text, sig):
        s = cls.parse(text.lower())
        self.assertEqual(s.coin, sig.coin)
        self.assertEqual(s.entries, sig.entries)
        self.assertEqual(s.sl, sig.sl)
        self.assertEqual(s.targets, sig.targets)
        self.assertEqual(s.fraction, sig.fraction)
        self.assertEqual(s.leverage, sig.leverage)
        self.assertEqual(s.tag, cls.__name__)


class TestBFP(TestSignal):
    def test_1(self):
        self._assert_signal(
            BFP, """Binance Futures  Signal
Long/Buy #1INCH/USDT 3.2605
Targets 3.2735 - 3.2865 - 3.3061 - 3.3420 - 3.3909
Stoploss 3.1626
Leverage 5-10x
By (@BFP)
👆🏼👆🏼This is an Early signal. Buy #LINK when it comes around the entry price and maintain the stop loss """
            """- Just Trade with 3 to 5% of Total funds""",
            Signal("1INCH", [3.2605], [3.2735, 3.2865, 3.3061, 3.342, 3.3909], 3.1626, 0.04, 10))

    def test_2(self):
        self._assert_signal(
            BFP, """Binance Future Signal
👇🏻👇🏻Early Signal - (IMPORTANT) This Trade should only be made, when the market price touches the  ENTRY POINT
Long/Buy #BLZ/USDT ️
Entry Point - 28390
Targets: 28500 - 28615 - 28730 - 28950 - 29525
Leverage - 10x
Stop Loss - 26970
By (@BFP)
✅✅Maintain the stop loss & Just Trade with 3 to 5% of Total funds""",
            Signal("BLZ", [28390], [28500, 28615, 28730, 28950, 29525], 26970, 0.04, 10))

    def test_3(self):
        self._assert_signal(
            BFP, """Binance Future Signal
👇🏻Early Signal - (IMPORTANT) This Trade should only be made, when the market price touches the  ENTRY POINT

Short/Sell #ALICE/USDT ️

Entry Point - 5.930

Targets: 5.905 - 5.885 - 5.855 - 5.815 - 5.690
Leverage - 10x
Stop Loss - 6.290
By (@BFP)
✅✅Maintain the stop loss & Just Trade with 3 to 5% of Total funds""",
            Signal("ALICE", [5.93], [5.905, 5.885, 5.855, 5.815, 5.69], 6.29, 0.04, 10))

    def test_4(self):
        self._assert_signal(
            BFP, """Binance Future Signal
👇🏻👇🏻Early Signal - (IMPORTANT) This Trade should only be made, when the market price touches the  ENTRY POINT

Long/Buy #SAND/USDT ️

Entry Point - 35145

Targets: 35285 - 35425 - 35565 - 35845 - 36550
Leverage - 10x
Stop Loss - 33030
By (@BFP)
✅✅Maintain the stop loss & Just Trade with 3 to 5% of Total funds""",
            Signal("SAND", [35145], [35285, 35425, 35565, 35845, 36550], 33030, 0.04, 10))


class TestBPS(TestSignal):
    def test_1(self):
        self._assert_signal(
            BPS, """Binance Futures/Bitmex/Bybit/Bitseven Signal# 1325
Get into Long #1INCH/USDT @ 1.76
Leverage – 10x
Target - 1.77-1.78-1.81-1.86
Stop Loss - 1.68""", Signal("1INCH", [1.76], [1.77, 1.78, 1.81, 1.86], 1.68, 0.03, 10))

    def test_2(self):
        coin = None
        try:
            self._assert_signal(
                BPS, """(in reply to Bitmex Premium Signals)
> Binance Futures/Bitmex/Bybit/Bitseven Signal# 1327
> Get into Long #LTC/USDT @ 174…
Exit trade with minor loss""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "LTC")


class TestCCS(TestSignal):
    def test_1(self):
        self._assert_signal(
            CCS, """📊 FUTURES (BINANCE)

#ALGOUSDT

LONG Below : 1.038

MAX 👉5x-7x LEVERAGE Hold

TAKE PROFIT:1.065+""", Signal("ALGO", [1.038], [1.065], leverage=10))

    def test_2(self):
        self._assert_signal(
            CCS, """📊 FUTURES (BINANCE)

#FLMUSDT

LONG Below : 0.5820-0.5750

MAX 👉5x-7x LEVERAGE Hold

TAKE PROFIT: 0.6055|0.6330+""", Signal("FLM", [0.582, 0.575], [0.6055, 0.633], leverage=10))

    def test_3(self):
        self._assert_signal(
            CCS, """📊 FUTURES (BINANCE)

#TRBUSDT

LONG Below : 62.00

MAX 👉5x-7x LEVERAGE Hold

TAKE PROFIT: 64.20|65.10|69.10+

SL: 58.85""", Signal("TRB", [62], [64.2, 65.1, 69.1], 58.85, leverage=10))


class TestFWP(TestSignal):
    def test_1(self):
        self._assert_signal(
            FWP, """#DOGEUSDT #LONG

BUY : 0.3400$- 0.3650$
TAKE PROFIT:
TARGET 1 : 0.3850$
TARGET 2 : 0.4000$
TARGET 3 : 0.4140$
TARGET 4 : 0.4300$
TARGET 5 : 0.4400$
TARGET 6 : 0.4500$
TARGET 7  : 0.4600$
TARGET 8  : 0.4700$

❗️STOL LOSS : 0.28$

Use 2% Fund Only

LEVERAGE:  10X-20X (CROSS)

BUY & HOLD ✅""", Signal("DOGE", [0.34, 0.365], [0.385, 0.4, 0.414, 0.43, 0.44], 0.28, 0.02, 20))

    def test_2(self):
        self._assert_signal(
            FWP, """#ONT/USDT #LONG
(BINANCE FUTURES )
BUY : 2.25$- 2.38$
TAKE PROFIT:
TARGET 1 : 2.52$
TARGET 2 : 2.60$
TARGET 3 : 2.67$
TARGET 4 : 2.73$
TARGET 5 : 2.80$
TARGET 6 : 2.88$
TARGET 7 : 2.98$

❗️STOL LOSS :2.15$

Use 2% Fund Only ❗️

LEV :  10X-20X (CROSS)

BUY & HOLD ✅""", Signal("ONT", [2.25, 2.38], [2.52, 2.6, 2.67, 2.73, 2.8], 2.15, 0.02, 20))


class TestMCVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            MCVIP, """BTCUSDT LONG 36705-36200
Target 37000-37400-38000-38500
Leverage 10x
Stop 35680""", Signal("BTC", [36705, 36200], [37000, 37400, 38000, 38500], 35680, 0.04, 10))

    def test_2(self):
        self.assertRaises(
            AssertionError,
            self._assert_signal,
            MCVIP, """ETHUSDT Buy 2580-2626
Targets 2800-3050-3300
Stop 2333""", None)

    def test_3(self):
        coin = None
        try:
            self._assert_signal(
                MCVIP, """Close algo""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "ALGO")

    def test_4(self):
        self._assert_signal(
            MCVIP, """1INCH/USDT ️ Long above 4.0009
Targets: 4.0169 - 4.034- 4.0503 - 4.082- 4.162
Leverage 10x
Stop 3.799""", Signal("1INCH", [4.0009], [4.0169, 4.034, 4.0503, 4.082, 4.162], 3.799, 0.04, 10))


class TestMVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            MVIP, """⚡️⚡️ #BNB/USDT⚡️⚡️

Entry Zone :
390,50 - 391,00
Take-Profit Targets:

1) 394,91
2) 410,55
3) 430,10

Leverage ×10

Stop Targets:

1) 312,80""", Signal("BNB", [390.5, 391], [394.91, 410.55, 430.10], 312.8, 0.03, 10))

    def test_2(self):
        self._assert_signal(
            MVIP, """⚡️⚡️ #CTK/USDT ⚡️⚡️

Entry Zone:
1.500 - 1.501

Take-Profit Targets:
1) 1.560
2) 1.650
3) 1.750

Levrage ×50

Stop Targets:
1) 1.400""", Signal("CTK", [1.5, 1.501], [1.56, 1.65, 1.75], 1.4, 0.03, 50))

    def test_3(self):
        self.assertRaises(
            AssertionError,
            self._assert_signal,
            MVIP, """⚡️⚡️ #HNT/USDT ⚡️⚡️

Entry Zone:
16,0000 - 16,0700

Take-Profit Targets:

1) 19,2840
2) 24,0700
3) 32,0700

Stop Targets:

1) 15,7486""", None)

    def test_4(self):
        self._assert_signal(MVIP, """⚡️⚡️ #LTC/USDT⚡️⚡️

Entry Zone:
174 - 175

Take-Profit Targets:

1) 176
2) 178

Leverage : ×50

Stop Targets:
1) 170""", Signal("LTC", [174, 175], [176, 178], 170, 0.03, 50))

    def test_5(self):
        self.assertRaises(AssertionError, self._assert_signal, MVIP, """[In reply to 👑 MVIP 👑]
Close second trade when first tp hit 🎯""", None)

    def test_6(self):
        coin = None
        try:
            self._assert_signal(
                MVIP, """[In reply to 👑 MVIP 👑]
Close #BTC/USDT""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "BTC")

    def test_7(self):
        coin = "UNKNOWN"
        try:
            self._assert_signal(
                MVIP, """🛑 Close all trades  🛑""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, None)

    def test_8(self):
        self.assertRaises(AssertionError, self._assert_signal, MVIP, """⚡️⚡️ #LINK/USDT⚡️⚡️

Entry Zone:
22.7 - 22.8

Take-Profit Targets:

1) 23.2
2) 23.7
3) 24.1

Leverage ×10

Stop Targets:
1) 21.4""", Signal("LINK", [22.7, 22.8], [23.2, 23.7, 24.1]))


class TestTCA(TestSignal):
    def test_1(self):
        self._assert_signal(
            TCA, """Asset: EOS/USDT
Position: #LONG
Entry: 5.850 - 5.950
Targets: 6.000 - 6.100 - 6.300 - 6.500
Stop loss: 5.600
Leverage: 75x""", Signal("EOS", [5.85, 5.95], [6, 6.1, 6.3, 6.5], 5.6, 0.03, 75))

    def test_2(self):
        self._assert_signal(
            TCA, """Leverage Trading Signal
Pair: BTC/USDT #LONG
Leverage: cross 100x (not more than 3-4% balance)
Targets : 39000 - 39500 - 40000 - 41800
Entry : 38500 - 38700
SL: 37300""", Signal("BTC", [38500, 38700], [39000, 39500, 40000, 41800], 37300, 0.03, 100))

    def test_3(self):
        coin = None
        try:
            self._assert_signal(
                TCA, """Close position
BTC by 35091
Profit is +300%""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "BTC")

    def test_4(self):
        coin = "UNKNOWN"
        try:
            self._assert_signal(
                TCA, """Closing all positions. Leaving the market""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, None)

    def test_5(self):
        coin = "UNKNOWN"
        try:
            self._assert_signal(
                TCA, """Closing eth at entry""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "ETH")


class TestCB(TestSignal):
    def test_1(self):
        self._assert_signal(
            CB, """#BAL|USDT (Binance Futures)

LONG (Place A Bid)
Lvg. : 5x - 10x

Entry  : 26.36$ - 27.36$
Targets :  28.06$ - 29$ - 34$ - 50$ - 65$

StopLoss : 25.289$

https://www.tradingview.com/""",
            Signal("BAL", [26.36, 27.36], [28.06, 29, 34, 50, 65], 25.289, 0.03, 10))


class TestWB(TestSignal):
    def test_1(self):
        self._assert_signal(
            WB, """#SKLUSDT FUTURE Call
#LONG
BUY Order:- 0.38000-0.38500

Sell :- 0.38700-0.39000-0.39300-0.395000-0.4000

Use 10X Leverage

STOP LOSS:- 0.25000""",
            Signal("SKL", [0.38, 0.385], [0.387, 0.39, 0.393, 0.395, 0.4], 0.25, 0.03, 10))


class TestRM(TestSignal):
    def test_1(self):
        self._assert_signal(
            RM, """⚡️⚡️ #BTC/USDT ⚡️⚡️

Client: Binance Futures
Trade Type: Regular (LONG)
Leverage: Isolated (10.0X)

Entry Zone:
38500 - 38980

Take-Profit Targets:
1) 39265 - 20%
2) 39700 - 20%
3) 40100 - 20%
4) 40500 - 20%
5) 41000 - 20%

Stop Targets:
1) 36430 - 100.0%

Risk level 8/10
Published By:
provided by : @CVIP""",
            Signal("BTC", [38500, 38980], [39265, 39700, 40100, 40500, 41000], 36430, 0.03, 10))


class TestVIPCS(TestSignal):
    def test_1(self):
        self._assert_signal(
            VIPCS, """➡️ SHORT LINKUSDT | Binance

❇️ Buy: 27.00000000

☑️ Target 1: 22.95000000 (15%)

☑️ Target 2: 18.90000000 (30%)

☑️ Target 3: 14.85000000 (45%)

⛔️ Stoploss: 31.05000000  (-15%)

💫 Leverage : 10x""", Signal("LINK", [27], [22.95, 18.9, 14.85], 31.05, 0.05, 10))

    def test_2(self):
        self._assert_signal(
            VIPCS, """⚡⚡ #LINK/USDT ⚡⚡
Exchanges: Binance Futures
Signal Type: Regular (Short)
Leverage: Isolated (10.0X)

Entry Targets:
1) 27 ✅

Take-Profit Targets:
1) 24
2) 21.6
3) 18.9
4) 14
5) 11

Stop Targets:
1) 29.7

Published By: @V""", Signal("LINK", [27], [24, 21.6, 18.9, 14, 11], 29.7, 0.05))


class TestCEP(TestSignal):
    def test_1(self):
        self._assert_signal(
            CEP, """#ETHUSDT

📍 SHORT

Leverage : 20x

📍Use 2% of Total Account

Buy : 2700 - 2660 - 2630

Sell Targets ::

2600 - 2560 - 2510 - 2460 - 2400 - 2300 - 2200 - 2100

🔻 StopLoss : 2850


#Crypto ✅""", Signal("ETH", [2700, 2660, 2630], [2600, 2560, 2510, 2460, 2400], 2850, 0.02, 20)
        )


class TestCM(TestSignal):
    def test_1(self):
        self._assert_signal(
            CM, """Binance Futures  Call ‼️

#LTCUSDT  PERP
⬆️Long  Call

❇️ Entry :  162$ - 165$

Target 1 : 168$
Target 2 : 173$
Target 3 : 179$
Target 4 : 183$
Target 5 : 193$

➡️Leverage   :  5x - 10x
⛔️Stop Loss  :  159$

Use Only 2-5% Of Your Total Portfolio


https://www.tradingview.com/""", Signal("LTC", [162, 165], [168, 173, 179, 183, 193], 159, 0.03, 10)
        )


class TestPTS(TestSignal):
    def test_1(self):
        self._assert_signal(
            PTS, """Binance Futures  Call ‼️

#ANKRUSDT  PERP
⬆️Long  Call

❇️ Entry :  0.10352$ - 0.10745$

Target 1 : 0.10951$
Target 2 : 0.12$
Target 3 : 0.15$
Target 4 : 0.18$
Target 5 : 0.21$

➡️Leverage   :  5x - 10x
⛔️Stop Loss  :  0.10164$

Use Only 2-5% Of Your Total Portfolio

https://www.tradingview.com/""",
            Signal("ANKR", [0.10352, 0.10745], [0.10951, 0.12, 0.15, 0.18, 0.21], 0.10164, 0.03, 10)
        )


class TestBUSA(TestSignal):
    def test_1(self):
        self._assert_signal(
            BUSA, """BTS/USDT x10 “SHORT”

Now : 0.0555$

Target : 0.052$ - 0.05$

0.06$ can be stop""", Signal("BTS", [0.0555], [0.052, 0.05], 0.06)
        )

    def test_2(self):
        self._assert_signal(
            BUSA, """NKN/USDT x10

Now : 0.387$

Target : 0.4$ - 0.42$

Enjoy!!""", Signal("NKN", [0.387], [0.4, 0.42])
        )

    def test_3(self):
        self._assert_signal(
            BUSA, """Blockchain Signal !!

SFP/USDT x10 “LONG”

Entry : 1.185$ - 1.19$

Target 1 : 1.25$
Target 2 : 1.4$
Target 3 : 1.6$

Enjoy!!""", Signal("SFP", [1.185, 1.19], [1.25, 1.4, 1.6]))


class TestEBS(TestSignal):
    def test_1(self):
        self._assert_signal(
            EBS, """#EXCHANGE: Binance(spot)/ Evolve
Leverage: 50x

 #ETH/USDT

Scalp Setup

Short Entry:
  2679.00

Target 1 - 2666.48
Target 2 - 2648.69

by @CRR""", Signal("ETH", [2679], [2666.48, 2648.69], leverage=50))

    def test_2(self):
        self._assert_signal(
            EBS, """#EXCHANGE: Binance(spot)/ Evolve
Leverage: 32

 #BTC/USDT

Scalp Setup

Short Entry:
  36160

Target 1 - 35959
Target 2 - 35672

by @CTT""", Signal("BTC", [36160], [35959, 35672], leverage=32))


class TestKBV(TestSignal):
    def test_1(self):
        self._assert_signal(
            KBV, """#B&BF

#ONT/USDT ️
#SHORT
Entry LIMIT: 1.0665

SELL:
1.0620 - 1.0580 - 1.0535 - 1.0450 - 1.0240

Leverage - 10x

❗️STOP LOSS : 1.120

by @CRR""", Signal("ONT", [1.0665], [1.062, 1.058, 1.0535, 1.045, 1.024], 1.12))

    def test_2(self):
        self._assert_signal(
            KBV, """#B&BF

#SNX/USDT ️
#SHORT
Entry LIMIT: 11.40

SELL:
11.300 - 11.255 - 11.205 - 11.120
11.890

Leverage - 10x

❗️STOP LOSS : 12$

by @CRR""", Signal("SNX", [11.4], [11.3, 11.255, 11.205, 11.12], 12))


class TestBVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            BVIP, """CVCUSDT LONG 0.324-0.30
Targets 0.348-0.365
Leverage 4x
Stop 0.292

by @CRR""", Signal("CVC", [0.324, 0.3], [0.348, 0.365], 0.292, leverage=4))

    def test_2(self):
        self._assert_signal(
            BVIP, """LTCUSDT LONG 182-176
Targets 186-191-196-205
Leverage 15x
stop 162

by @CRR""", Signal("LTC", [182, 176], [186, 191, 196, 205], 162, leverage=15))


class TestFXVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            FXVIP, """Binance Future
OCEANUSDT ❗️LONG
Entry Price       0,582800
Leverage :  cross (×20)
Target :  0,592709
Stop loss :  0,57137
Capital invested :  2%

by @CRR""", Signal("OCEAN", [0.5828], [0.592709], 0.57137, 0.02, 20))

    def test_2(self):
        self.assertRaises(
            Exception,
            self._assert_signal,
            FXVIP, """#ICP/USDT #LONG
(BINANCE FUTURES )
BUY : 82$- 88.2$

TAKE PROFIT:
TARGET 1 : 93.00$
TARGET 2 : 95.50$
TARGET 3 : 98.00$
TARGET 4 : 101.0$
TARGET 5 : 104.0$
TARGET 6 : 108.0$

❗️STOP LOSS :80$

Use 2% Fund Only ❗️

LEV :  10X-20X (CROSS)

BUY & HOLD ✅

by @CRR""", None)

    def test_3(self):
        self.assertRaises(
            Exception,
            self._assert_signal,
            FXVIP, """HNT/USDT ️ Long above 14.024
Targets: 14.074 - 14.129- 14.199 - 14.31 - 14.6
Leverage 10x
Stop 13.324

by @CRR""", None)


class TestBAW(TestSignal):
    def test_1(self):
        self._assert_signal(
            BAW, """Long ETH/USDT

Entry 2475 / 2425

Targets 2526 / 2571 / 2613 / 2675 / 2731

Stop loss : 2290

Leverage cross x8

Exchange : Binance Futures

by @CRR""", Signal("ETH", [2475, 2425], [2526, 2571, 2613, 2675, 2731], 2290))
