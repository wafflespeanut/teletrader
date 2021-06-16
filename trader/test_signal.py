import unittest

from .errors import CloseTradeException
from .signal import (BAW, BFP, BFP2, BPS, BUSA, BVIP, C, CB, CC, CCC, CCS, CEP, CM, CS, CY, EBS, FWP, FXVIP,
                     HBTCV, KBV, KCE, KSP, LVIP, MCVIP, MVIP, PBF, PHVIP, PVIP, RM, RWS, SLVIP, SS, TCA, VIPBB,
                     VIPCS, WB, YCP, Signal)


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
            Signal("1INCH", [3.2605], [3.2735, 3.2865, 3.3061, 3.342, 3.3909], 3.1626))

    def test_2(self):
        s = Signal("BLZ", [28390], [28500, 28615, 28730, 28950, 29525], 26970)
        self._assert_signal(
            BFP, """Binance Future Signal
👇🏻👇🏻Early Signal - (IMPORTANT) This Trade should only be made, when the market price touches the  ENTRY POINT
Long/Buy #BLZ/USDT ️
Entry Point - 28390
Targets: 28500 - 28615 - 28730 - 28950 - 29525
Leverage - 10x
Stop Loss - 26970
By (@BFP)
✅✅Maintain the stop loss & Just Trade with 3 to 5% of Total funds""", s)
        s.correct(0.0283)
        self.assertAlmostEqual(s.entries[0], 0.02839)
        for e1, e2 in zip(s.targets, [0.0285, 0.028615, 0.02873, 0.02895, 0.029525]):
            self.assertAlmostEqual(e1, e2)
        self.assertAlmostEqual(s.sl, 0.02697)

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
            Signal("ALICE", [5.93], [5.905, 5.885, 5.855, 5.815, 5.69], 6.29))

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
            Signal("SAND", [35145], [35285, 35425, 35565, 35845, 36550], 33030))


class TestBPS(TestSignal):
    def test_1(self):
        self._assert_signal(
            BPS, """Binance Futures/Bitmex/Bybit/Bitseven Signal# 1325
Get into Long #1INCH/USDT @ 1.76
Leverage – 10x
Target - 1.77-1.78-1.81-1.86
Stop Loss - 1.68""", Signal("1INCH", [1.76], [1.77, 1.78, 1.81, 1.86], 1.68))

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
Stop 35680""", Signal("BTC", [36705, 36200], [37000, 37400, 38000, 38500], 35680))

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
Stop 3.799""", Signal("1INCH", [4.0009], [4.0169, 4.034, 4.0503, 4.082, 4.162], 3.799))


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

1) 312,80""", Signal("BNB", [390.5, 391], [394.91, 410.55, 430.10], 312.8, 0.01, 10))

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
1) 1.400""", Signal("CTK", [1.5, 1.501], [1.56, 1.65, 1.75], 1.4, 0.01, 20))

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
1) 170""", Signal("LTC", [174, 175], [176, 178], 170, 0.01, 20))

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
1) 21.4""", Signal("LINK", [0], []))

    def test_9(self):
        self._assert_signal(MVIP, """⚡️⚡️ # ETC / USDT ⚡️⚡️

Entry Zone:
  58.10 - 58.20

Take-Profit Targets:
1) 58.78
2) 59.36
3) 59.94

Leverage×50

Stop Targets:
1) 55.29""", Signal("ETC", [58.1, 58.2], [58.78, 59.36, 59.94], 55.29, 0.01, 20))


class TestTCA(TestSignal):
    def test_1(self):
        self._assert_signal(
            TCA, """Asset: EOS/USDT
Position: #LONG
Entry: 5.850 - 5.950
Targets: 6.000 - 6.100 - 6.300 - 6.500
Stop loss: 5.600
Leverage: 75x""", Signal("EOS", [5.85, 5.95], [6, 6.1, 6.3, 6.5], 5.6, 0.02, 20))

    def test_2(self):
        self._assert_signal(
            TCA, """Leverage Trading Signal
Pair: BTC/USDT #LONG
Leverage: cross 100x (not more than 3-4% balance)
Targets : 39000 - 39500 - 40000 - 41800
Entry : 38500 - 38700
SL: 37300""", Signal("BTC", [38500, 38700], [39000, 39500, 40000, 41800], 37300, 0.02, 20))

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
            Signal("BAL", [26.36, 27.36], [28.06, 29, 34, 50, 65], 25.289))


class TestWB(TestSignal):
    def test_1(self):
        self._assert_signal(
            WB, """#SKLUSDT FUTURE Call
#LONG
BUY Order:- 0.38000-0.38500

Sell :- 0.38700-0.39000-0.39300-0.395000-0.4000

Use 10X Leverage

STOP LOSS:- 0.25000""",
            Signal("SKL", [0.38, 0.385], [0.387, 0.39, 0.393, 0.395, 0.4], 0.25))


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
            Signal("BTC", [38500, 38980], [39265, 39700, 40100, 40500, 41000], 36430))


class TestVIPCS(TestSignal):
    def test_1(self):
        self._assert_signal(
            VIPCS, """➡️ SHORT LINKUSDT | Binance

❇️ Buy: 27.00000000

☑️ Target 1: 22.95000000 (15%)

☑️ Target 2: 18.90000000 (30%)

☑️ Target 3: 14.85000000 (45%)

⛔️ Stoploss: 31.05000000  (-15%)

💫 Leverage : 10x""", Signal("LINK", [27], [22.95, 18.9, 14.85], 31.05, 0.03, 10))

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

Published By: @V""", Signal("LINK", [27], [24, 21.6, 18.9, 14, 11], 29.7, 0.03, 10))

    def test_3(self):
        coin = None
        try:
            self._assert_signal(
                VIPCS, """[In reply to Vip CoinSignals]
Close TRB""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "TRB")

    def test_4(self):
        self._assert_signal(
            VIPCS, """➡️ SHORT BTCUSDT | Binance

❇️ Entry : 36700.00000000

☑️ Target 1: 31195.00000000 (15%)

☑️ Target 2: 25690.00000000 (30%)

☑️ Target 3: 20185.00000000 (45%)

⛔️ Stoploss: 42205.00000000  (-15%)

💫 Leverage : 5x - 10x""", Signal("BTC", [36700], [31195, 25690, 20185], 42205, 0.03, 10))


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


#Crypto ✅""", Signal("ETH", [2700, 2660, 2630], [2600, 2560, 2510, 2460, 2400], 2850, 0.02, 20))


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


https://www.tradingview.com/""", Signal("LTC", [162, 165], [168, 173, 179, 183, 193], 159)
        )


class TestCS(TestSignal):
    def test_1(self):
        self._assert_signal(
            CS, """Binance Futures  Call ‼️

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
            Signal("ANKR", [0.10352, 0.10745], [0.10951, 0.12, 0.15, 0.18, 0.21], 0.10164)
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

#     def test_4(self):
#         self._assert_signal(
#             BUSA, """$BNB Short Entry : 366$ - 368$ x10 😎

# Target : 345$ - 340$

# SL : 378$

# Enjoy!!""", Signal("SFP", [366, 368], [345, 340], 378))


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

by @CRR""", Signal("ETH", [2679], [2666.48, 2648.69], fraction=0.02, leverage=20))

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

by @CTT""", Signal("BTC", [36160], [35959, 35672], fraction=0.02, leverage=20))


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

    def test_3(self):
        self._assert_signal(
            KBV, """#B&BF

#BZRX/USDT ️
#LONG
BUY LIMIT: 3000

SELL:
3012 - 3024 - 3036 - 3060 - 3120

Leverage - 10x

❗️STOP LOSS : 2850.

by @CRR""", Signal("BZRX", [3000], [3012, 3024, 3036, 3060, 3120], 2850))


class TestBVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            BVIP, """1INCHUSDT LONG 0.324-0.30
Targets 0.348-0.365
Leverage 4x
Stop 0.292

by @CRR""", Signal("1INCH", [0.324, 0.3], [0.348, 0.365], 0.292, leverage=4))

    def test_2(self):
        self._assert_signal(
            BVIP, """LTCUSDT LONG 182-176
Targets 186-191-196-205
Leverage 15x
stop 162

by @CRR""", Signal("LTC", [182, 176], [186, 191, 196, 205], 162, leverage=15))


class TestPBF(TestSignal):
    def test_1(self):
        self._assert_signal(
            PBF, """Binance Future
OCEANUSDT ❗️LONG
Entry Price       0,582800
Leverage :  cross (×20)
Target :  0,592709
Stop loss :  0,57137
Capital invested :  2%

by @CRR""", Signal("OCEAN", [0.5828], [0.592709], 0.57137, 0.02, 20))


class TestFXVIP(TestSignal):
    def test_1(self):
        self._assert_signal(
            FXVIP, """Binance Future
DGBUSDT ❗️LONG
Entry Price       0,062400
Leverage :  cross (×20)
Target :  0,063649
Stop loss :  UPDATE
Capital invested :  2%

by @CRR""", Signal("DGB", [0.0624], [0.063649], None, 0.02, 20))

    def test_2(self):
        self._assert_signal(
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

by @CRR""", Signal("ICP", [82, 88.2], [93, 95.5, 98, 101, 104], 80, 0.02, 20))

    def test_3(self):
        self._assert_signal(
            FXVIP, """1INCH/USDT ️ Long above 14.024
Targets: 14.074 - 14.129- 14.199 - 14.31 - 14.6
Leverage 10x
Stop 13.324

by @CRR""", Signal("1INCH", [14.024], [14.074, 14.129, 14.199, 14.31, 14.6], 13.324))

    def test_4(self):
        self._assert_signal(
            FXVIP, """📊 FUTURES (BINANCE)

#BELUSDT

LONG Below : 1.65

MAX 👉5x-7x LEVERAGE Hold

TAKE PROFIT: 1.70|1.76|1.85+

by @CRR""", Signal("BEL", [1.65], [1.7, 1.76, 1.85]))

    def test_5(self):
        self._assert_signal(
            FXVIP, """AAVEUSDT | LONG |

ENTRY 305 - 285

TARGET 395 - 450 - 530

STOP LOSS 254

LEVERAGE 3–10X

by @CRR""", Signal("AAVE", [305, 285], [395, 450, 530], 254, leverage=10))


class TestBAW(TestSignal):
    def test_1(self):
        self._assert_signal(
            BAW, """Long ETH/USDT

Entry 2475 / 2425

Targets 2526 / 2571 / 2613 / 2675 / 2731

Stop loss : 2290

Leverage cross x8

Exchange : Binance Futures

by @CRR""", Signal("ETH", [2475, 2425], [2526, 2571, 2613, 2675, 2731], 2290, leverage=8))


class TestHBTCV(TestSignal):
    def test_1(self):
        self._assert_signal(
            HBTCV, """⚡️⚡️ #ETH/USDT ⚡️⚡️

Client: Binance Futures
Trade Type: Regular (SHORT)
Leverage: Isolated (5.0X)

Entry Zone:
2460- 2478

Take-Profit Targets:
1) 2430 - 20%
2) 2409- 20%
3) 2380 - 20%
4) 2345 - 20%
5) 2250- 20%

Stop Targets:
1) 2630 - 100.0%

by @CRR""", Signal("ETH", [2460, 2478], [2430, 2409, 2380, 2345, 2250], 2630, 0.02, 5))

    def test_2(self):
        self.assertRaises(
            AssertionError,
            self._assert_signal,
            HBTCV,
            """⚡️⚡️ #ETH/USDT ⚡️⚡️

Client: Binance Futures
Trade Type: Regular (SHORT)
Leverage: Isolated (10.0X)

Entry Zone:
2460- 2478

Take-Profit Targets:
1) 2430 - 20%✅
2) 2409- 20%✅
3) 2380 - 20%✅😎
4) 2345 - 20%
5) 2250- 20%

Stop Targets:
1) 2630 - 100.0%

by @CRR""", None)

    def test_3(self):
        self.assertRaises(
            AssertionError,
            self._assert_signal,
            HBTCV,
            """#ETH USDT

📍 SHORT

Leverage : 10x 20x (cross)

📍Use 2% of Total Account

ENTRY  : 2700 - 2660 - 2630

 Targets ::

2600✅ - 2560✅😎 - 2510 - 2460 - 2400 - 2300 - 2200 - 2100

🔻 StopLoss : 2900 (daily close)

by @CRR""", None)

    def test_4(self):
        self._assert_signal(
            HBTCV, """#ETH USDT

📍 SHORT

Leverage : 10x 20x (cross)

📍Use 2% of Total Account

ENTRY  : 2700 - 2660 - 2630

 Targets ::

2600 - 2560 - 2510 - 2460 - 2400 - 2300 - 2200 - 2100

🔻 StopLoss : 2900 (daily close)

by @CRR""", Signal("ETH", [2700, 2660, 2630], [2600, 2560, 2510, 2460, 2400], 2900, 0.02, 20))

    def test_5(self):
        self._assert_signal(
            HBTCV, """#BINANCE FUTURES $LTC


#LTC/USDT (Long)

🛒Entry 1 - 159.80 (30%)

🛒Entry 2 - 153 (30%)

🛒Entry 3 - 147 (40%)

🎯Targets - 164.5 - 170 - 188 - 205 - 230

Stoploss - 145

Leverage - 3-4x

by @CRR""", Signal("LTC", [159.8, 153, 147], [164.5, 170, 188, 205, 230], 145, 0.02, 5))

    def test_6(self):
        self.assertRaises(
            AssertionError,
            self._assert_signal,
            HBTCV, """#BINANCE FUTURES $LTC


#LTC/USDT (Long)

🛒Entry 1 - 159.80 (30%)

🛒Entry 2 - 153 (30%)

🛒Entry 3 - 147 (40%)

🎯Targets - 164.5 ✅😎- 170 - 188 - 205 - 230

Stoploss - 145  (daily close)

Leverage - 3-4x

by @CRR""", None)


class TestCY(TestSignal):
    def test_1(self):
        self._assert_signal(CY, """ICP/USDT
Leverage 10X
Buy 57 to 58
Sell  63
Stop 51

by @CRR""", Signal("ICP", [57, 58], [63], 51))

    def test_2(self):
        self._assert_signal(CY, """MTL/USDT
Leverage 15X
Buy 2.0510 to 2.1070
Sell  2.20
Stop 1.95

by @CRR""", Signal("MTL", [2.051, 2.107], [2.2], 1.95, 0.02, 15))

    def test_3(self):
        coin = None
        try:
            self._assert_signal(
                CY, """Stop DOGEUSDT

by @CRR""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "DOGE")


class TestKCE(TestSignal):
    def test_1(self):
        self._assert_signal(KCE, """BZRX/USDT x10 “SHORT” signal

Entry : 0.303 - 0.305

Target : 0.285$ - 0.28$

No stoploss

by @CRR""", Signal("BZRX", [0.303, 0.305], [0.285, 0.28]))

    def test_2(self):
        self._assert_signal(KCE, """AKRO/USDT x10

Entry : 0.022$ - 0.0225$

Target : 0.024$ - 0.026$

SL : 0.02$

Enjoy!!

by @CRR""", Signal("AKRO", [0.022, 0.0225], [0.024, 0.026], 0.02))

    def test_3(self):
        self._assert_signal(KCE, """1INCH/USDT buy setup : 0.327$ - 0.33$ x10

Target : 0.34$ - 0.36$ - 0.38$

SL : 0.3$

by @CRR""", Signal("1INCH", [0.327, 0.33], [0.34, 0.36, 0.38], 0.3))

    def test_4(self):
        self._assert_signal(KCE, """NKN/USDT x10

Now : 0.33$

Target 1 : 0.35$
Target 2 : 0.38$
Target 3 : 0.4$

Enjoy!!

by @CRR""", Signal("NKN", [0.33], [0.35, 0.38, 0.4]))

    def test_5(self):
        self._assert_signal(KCE, """BTS/USDT x10 “SHORT”

Now : 0.0555$

Target : 0.052$ - 0.05$

0.06$ can be stop

by @CRR""", Signal("BTS", [0.0555], [0.052, 0.05], 0.06))


class TestRWS(TestSignal):
    def test_1(self):
        self._assert_signal(RWS, """Enter Long 📈

ETH/USDT 2420

Leverage x5

Targets :

🎯 2470
🎯 2515
🎯 2580
🎯 2650

Stop loss 🔴 2364

by @CRR""", Signal("ETH", [2420], [2470, 2515, 2580, 2650], 2364, 0.01, 5))

    def test_2(self):
        self._assert_signal(RWS, """⚡️⚡️ #ETH/USDT ⚡️⚡️
Exchanges: Binance Futures
Signal Type: Regular (Short)
Leverage: Isolated (10.0X)

Entry Targets:
1) 2370 - 50.0% ✅
2) 2400 - 50.0% ✅

Take-Profit Targets:
1) 2310
2) 2275
3) 2210
4) 2110
5) 1990

Stop Targets:
1) 2411

Published By: @Adam

by @CRR""", Signal("ETH", [2370], [2310, 2275, 2210, 2110, 1990], 2411, 0.02))

    def test_3(self):
        coin = None
        try:
            self._assert_signal(
                RWS, """[In reply to RWS]
Close ETH/USDT

by @CRR""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "ETH")


class TestSS(TestSignal):
    def test_1(self):
        self._assert_signal(SS, """#BTCUSDT

#SHORT 35100-37260

Close 33660 31500 29700 27000

Stop 37980

Lev 3X""", Signal("BTC", [35100, 37260], [33660, 31500, 29700, 27000], 37980))


class TestSLVIP(TestSignal):
    def test_1(self):
        self._assert_signal(SLVIP, """#BNB_USDT Scalp Long!!

 Entry Zone:350 & 320

Sell Zone:353-357-365-380-400

StopLoss : 1H Candle Close Under 300

Lev: Cross With 50-75X

Exchange : Binance Futures

by @CRR""", Signal("BNB", [350, 320], [353, 357, 365, 380, 400], 300, 0.02, 20))


class TestCCC(TestSignal):
    def test_1(self):
        self._assert_signal(CCC, """#BINANCEFUTURES $LTC

https://www.tradingview.com/

#LTC/USDT (Long)

🛒Entry 1 - 159.80 (30%) (Filled)

🛒Entry 2 - 153 (30%)

🛒Entry 3 - 147 (40%)

🎯Targets - 164.5 - 170 - 188 - 205 - 230

Stoploss - 145

Leverage - 3-4x

@Forex_Tradings)""", Signal("LTC", [159.8, 153, 147], [164.5, 170, 188], 145, leverage=5))

    def test_2(self):
        self._assert_signal(CCC, """[ Photo ]
BTC scalp short

Entry 35200-36000

stop 36300

Leverage 3x

Target 33500

#CCC

by @CRR""", Signal("BTC", [35200, 36000], [33500], 36300, leverage=5))

    def test_3(self):
        self._assert_signal(CCC, """[ Photo ]
DOGE short 😱

Entry now between 0.303 - 0.31

stop 🛑 close 4hr above 0.313 or 0.33 manually

Targets 0.295 - 0.267 - 0.22 🎯

Leverage 3x

#CCC

by @CRR""", Signal("DOGE", [0.303, 0.31], [0.295, 0.267, 0.22], 0.33, leverage=5))

    def test_4(self):
        self._assert_signal(CCC, """[ Photo ]
THETA short

Entry between cmp 8.8 USDT to 9.5 USDT

stop 🛑 if close 4hr above 10$

leverage up to 3x

Targets are 🎯 8.4 - 8 - 7.7 - 6.3 and bonus target wick down to 3.1 to 4.5 zone

#CCC bearish season hunter

by @CRR""", Signal("THETA", [8.8, 9.5], [8.4, 8, 7.7], 10, leverage=5))


class TestKSP(TestSignal):
    def test_1(self):
        self._assert_signal(KSP, """⚡️⚡️ #BTC/USDT ⚡️⚡️
Exchanges: Binance Futures
Signal Type: Regular (Long)
Leverage: Isolated (5.0X)

Entry Targets:
39477.31 - 37555.60

Take-Profit Targets:
1) 41131.68 - 10.0%
2) 43082.27 - 25.0%
3) 44924.49 - 40.0%
4) 47200.18 - 10.0%
5) 51209.72 - 5.0%
6) 53485.41 - 5.0%
7) 56000.00 - 5.0%

Stop Targets:
1) 35171.54""", Signal("BTC", [39477.31, 37555.6],
                       [41131.68, 43082.27, 44924.49, 47200.18, 51209.72, 53485.41, 56000],
                       35171.54, leverage=5))


class TestBFP2(TestSignal):
    def test_1(self):
        self._assert_signal(BFP2, """Long/Buy #1INCHUSDT $0.0070
Target $0.0077-$0.0085-$0.0099+
Stop Loss Use Below $0.0055
Leverage Use Only 3x-5x ✈️

by @CRR""", Signal("1INCH", [0.007], [0.0077, 0.0085, 0.0099], 0.0055, leverage=5))


class TestVIPBB(TestSignal):
    def test_1(self):
        s = Signal("BTC", [37.1, 36.3], [38, 39, 41.4, 42.2], 34.4, leverage=25)
        self._assert_signal(VIPBB, """#BTC/USDT
LONG
Buy Setup:  37.1-36.3

SELL:
38K - 39K - 41.4 - 42.2K

LEV : 5X - 10X - 25X

❗️STOP LOSS : 34.4

by @CRR""", s)
        s.correct(36000)
        self.assertEqual(s.entries, [36300, 37100])
        self.assertEqual(s.targets, [38000, 39000, 41400, 42200])
        self.assertEqual(s.sl, 34400)

    def test_2(self):
        self._assert_signal(VIPBB, """#BTC/USDT
#LONG
BUY : 39850 - 40300

Take-Profit Targets:
40900 - 41300 - 41600 - 42000 - 42300

LEV : 5X - 10X - 20X

❗️STOP LOSS : 38600$

by @CRR""", Signal("BTC", [39850, 40300], [40900, 41300, 41600, 42000, 42300], 38600, leverage=20))


class TestPVIP(TestSignal):
    def test_1(self):
        self._assert_signal(PVIP, """#Bybit Call

ETH-USDT

BUY LONG: 2460-2480$

LEVERAGE:4x

TARGET 1: 2600$
TARGET 2: 2780$
TARGET 3: 2900$

Stop-loss: 2300$

Use 5-6% Balance)

by @CRR""", Signal("ETH", [2460, 2480], [2600, 2780, 2900], 2300, 0.04, 5))


class TestPHVIP(TestSignal):
    def test_1(self):
        self._assert_signal(PHVIP, """⚡️⚡️ #ADA/USDT ⚡️⚡️
Exchanges: Binance Futures
Signal Type: Regular (Long)
Leverage: Isolated (5.0X)

Entry Targets:
1.7332 - 1.6057

Take-Profit Targets:
1) 1.8380 - 10.0%
2) 1.9514 - 25.0%
3) 2.1134 - 40.0%
4) 2.3241 - 10.0%
5) 2.5132 - 5.0%
6) 2.6750 - 5.0%
7) 2.8319 - 5.0%

Stop Targets:
1) 1.4490

by @CRR""", Signal("ADA", [1.7332, 1.6057], [1.838, 1.9514, 2.1134, 2.3241, 2.5132, 2.675, 2.8319], 1.449, leverage=5))


class TestCC(TestSignal):
    def test_1(self):
        self._assert_signal(CC, """[ Photo ]
CCS

📈 LONG #ETHUSDT 5X

Entry: 2550 - 2560

TP 1: 2620
TP 2: 2720
TP 3: 2860

S/L: 2450""", Signal("ETH", [2550, 2560], [2620, 2720, 2860], 2450, leverage=5))

    def test_2(self):
        self._assert_signal(CC, """CCS

📈 LONG #FLMUSDT 10X

Entry: now 0.545 🚀

TP 1: 0.573
TP 2: 0.602
TP 3: 0.645

S/L: 0.5200""", Signal("FLM", [0.545], [0.573, 0.602, 0.645], 0.52, leverage=10))


class TestC(TestSignal):
    def test_1(self):
        coin = None
        try:
            self._assert_signal(
                C, """[In reply to Crypto #CRR]
Close BTCUSDT

by @CRR""", None)
        except CloseTradeException as exp:
            coin = exp.coin
        self.assertEqual(coin, "BTC")


class TestYCP(TestSignal):
    def test_1(self):
        self._assert_signal(YCP, """Long #IOSTUSDT

Risk level - High

Entry Zone: 0.0280-0.0295

Targets: 0.031-0.034-0.037-0.042-0.045

Leverage - 3x strictly

Put only 5% of your portfolio in this trade

Close: You may keep closing 10-15% of your open positions at each target.

Overall stop-loss - Overall stoploss at 0.025. You may move position stop-loss to trade entry price

Current rate - 0.0292""", Signal("IOST", [0.028, 0.0295], [0.031, 0.034, 0.037, 0.042, 0.045], 0.025, 0.03, 5))


class TestLVIP(TestSignal):
    def test_1(self):
        self._assert_signal(LVIP, """ICXUSDT  IN 4 HOURS 👀👀‼️

#ICX/USDT ON #BINANCE

BUY :- 0.98-0.99-1.0138

TARGET:1.03-1.07-1.09-1.13-1.18-1.21-1.25-1.29++

STOP 🛑:- 0.91

LEV :- 2X/3X

USE 1% FUND RISKY CALL‼️

by @CRR""", Signal("ICX", [0.98, 0.99, 1.0138], [1.03, 1.07, 1.09, 1.13, 1.18], 0.91, 0.02, 5))

    def test_2(self):
        self._assert_signal(LVIP, """https://www.tradingview.com/

#DOT/USDT‼️‼️

#DOT/USDT 👀👀

BUY :- 22-23-24.09

TARGET:-25.20-25.50-25.90-26.30-26.90-27.30-27.80-28.30-28.90++

STOP 🛑:-20

LEV :- 2X

PLACE ORDER .‼️..USE 3%-5% FUND 👀

by @CRR""", Signal("DOT", [22, 23, 24.09], [25.2, 25.5, 25.9, 26.3, 26.9], 20, 0.02, 5))
