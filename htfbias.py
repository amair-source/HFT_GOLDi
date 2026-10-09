import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from hft_scan import features, days, ema
import rr_sweep as rr
from rr_sweep import simulate, atrfloor_sig

SYMBOL = "GOLDi"
SPREAD = 26


def load_bias(tf, period):
    h1 = mt5.copy_rates_from_pos(SYMBOL, tf, 0, 4000)
    hc = h1["close"]
    he = ema(hc, period)
    hT = h1["time"]
    return hT, hc, he


def bias_index(ratesTime, hT, hc, he):
    idx = np.searchsorted(hT, ratesTime, side="right") - 1
    idx = np.clip(idx, 0, len(hT) - 1)
    return np.where(hc[idx] > he[idx], 1, np.where(hc[idx] < he[idx], -1, 0))


def sig_with_bias(f, bias, ratio=1.0):
    base = atrfloor_sig(f, None, ratio)
    def sig(i, st):
        s = base(i, st)
        if s == 0 or bias[i] == 0:
            return 0
        if s == 1 and bias[i] != 1:
            return 0
        if s == -1 and bias[i] != -1:
            return 0
        return s
    return sig


def run(rates, label, tf, period):
    cut = int(len(rates) * 0.6)
    hT, hc, he = load_bias(tf, period)
    out = []
    for sname, rs in (("tr", rates[:cut]), ("te", rates[cut:])):
        d, f = features(rs)
        d.sp[:] = SPREAD
        bias = bias_index(rs["time"], hT, hc, he)
        r = simulate(d, sig_with_bias(f, bias), f["a"], 2.0, 4.0, 1.0, 1.5)
        out.append((sname, r))
    tr, te = out[0][1], out[1][1]
    print("%-26s tr$%7.2f te$%7.2f | te win%4.1f aw%5.2f al%6.2f PF%4.2f n%4d" %
          (label, tr["final"], te["final"], te["win"], te["aw"], te["al"], te["pf"], te["n"]))


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    print("--- no bias (atrfloor + SL2 TP4 chandelier) ---")
    cut = int(len(rates) * 0.6)
    for sname, rs in (("tr", rates[:cut]), ("te", rates[cut:])):
        d, f = features(rs)
        d.sp[:] = SPREAD
        r = simulate(d, atrfloor_sig(f, d.o), f["a"], 2.0, 4.0, 1.0, 1.5)
        print("%s: final %7.2f win %4.1f aw %5.2f al %6.2f PF %4.2f n %4d" %
              (sname, r["final"], r["win"], r["aw"], r["al"], r["pf"], r["n"]))
    print("--- HTF bias gate ---")
    for tf, name in ((mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_H1, "H1"), (mt5.TIMEFRAME_H4, "H4")):
        for per in (20, 50, 100):
            run(rates, "%s EMA%d bias" % (name, per), tf, per)
    mt5.shutdown()


if __name__ == "__main__":
    main()