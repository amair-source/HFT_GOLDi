import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from hft_scan import features, days
import sweep_gold as sg
from sweep_gold import simulate

SYMBOL = "GOLDi"
SPREAD_PTS = 26


def trend_sig(c0, e50):
    def sig(i, st):
        if not np.isfinite(e50[i]):
            return 0
        if c0[i] > e50[i]:
            return 1
        if c0[i] < e50[i]:
            return -1
        return 0
    return sig


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    print("bars %d over %.0f days" % (len(rates), days(rates)))
    cut = int(len(rates) * 0.6)
    segs = [("TRAIN", rates[:cut]), ("TEST", rates[cut:]), ("FULL", rates)]
    sg.SESS = (7, 20)
    sg.MAX_SPREAD = 45
    print("%6s %8s %8s %8s %8s %8s" % ("SLxATR", "tr$", "te$", "full$", "teN", "teWin%"))
    for sl_a in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5):
        vals = {}
        for sname, rs in segs:
            d, f = features(rs)
            d.sp[:] = SPREAD_PTS
            sig = trend_sig(f["c"], f["e50"])
            r = simulate(d, sig, f["a"], None, sl_a, 2.25, "atr")
            vals[sname] = r
        tr, te, fu = vals["TRAIN"], vals["TEST"], vals["FULL"]
        print("%6.2f %8.2f %8.2f %8.2f %8d %8.1f" %
              (sl_a, tr["final"], te["final"], fu["final"], te["n"], te["win"]))
    mt5.shutdown()


if __name__ == "__main__":
    main()
