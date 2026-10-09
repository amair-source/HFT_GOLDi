import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data
from sweep_gold import simulate


def prep(rates, off=2):
    d = Data(rates)
    d.off = off
    c, h, l = d.c, d.h, d.l
    return d


def get_trend(d, start):
    r5 = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M5, 0, 99000)
    t5 = r5["time"]
    e5 = ema(r5["close"], 20)
    j = np.clip(np.searchsorted(t5, d.tm, side="right") - 2, 0, len(t5) - 1)
    trend5 = e5[j]
    c = d.c
    rr = rsi(c, 7)
    a = atr(d.h, d.l, c, 14)
    mid = sma(c, 20)

    def sig(i, st):
        if not np.isfinite(rr[i]) or not np.isfinite(trend5[i]):
            return 0
        if c[i] > trend5[i] and rr[i - 1] < 30 and rr[i] >= 30:
            return 1
        if c[i] < trend5[i] and rr[i - 1] > 70 and rr[i] <= 70:
            return -1
        return 0

    return sig, a, mid


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M1, 0, 99000)
    cut = int(len(rates) * 0.6)
    for label, seg in (("TRAIN 60%", rates[:cut]), ("TEST 40%", rates[cut:])):
        d = prep(seg)
        sig, a, mid = get_trend(d, None)
        print(f"{label}: {d.n} bars")
        for sl_a, tp_a in ((2.0, 1.5), (2.0, 2.25), (2.5, 2.25)):
            r = simulate(d, sig, a, mid, sl_a, tp_a, "atr")
            print(f"   sl{sl_a} tp{tp_a}: N={r['n']:4d} win={r['win']:5.1f} final={r['final']:7.2f} netpts={r['net_pts']:7.0f} SL/TP/EOD={r['sl']}/{r['tp']}/{r['eod']}")


if __name__ == "__main__":
    main()
