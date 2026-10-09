import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data
from sweep_gold import simulate

t.connect()
r1 = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M1, 0, 99000)
d = Data(r1)
c, h, l = d.c, d.h, d.l
r5 = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M5, 0, 99000)
t5 = r5["time"]
e5 = ema(r5["close"], 20)
j = np.clip(np.searchsorted(t5, d.tm, side="right") - 2, 0, len(t5) - 1)
trend5 = e5[j]
up5 = c > trend5
dn5 = c < trend5
rr = rsi(c, 7)
a = atr(h, l, c, 14)
mid = sma(c, 20)


def sig(i, st):
    if not np.isfinite(rr[i]) or not np.isfinite(trend5[i]):
        return 0
    if up5[i] and rr[i - 1] < 30 and rr[i] >= 30:
        return 1
    if dn5[i] and rr[i - 1] > 70 and rr[i] <= 70:
        return -1
    return 0


print("rsi7(30,70) pullback_m5 family:")
for sl_a in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5):
    for tp_a in (1.5, 2.25, 3.0):
        r = simulate(d, sig, a, mid, sl_a, tp_a, "atr")
        print(f"  sl{sl_a:<5} tp{tp_a:<5} N={r['n']:4d} win={r['win']:5.1f} final={r['final']:7.2f} netpts={r['net_pts']:7.0f} SL/TP/EOD={r['sl']}/{r['tp']}/{r['eod']}")
