import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from hft_scan import features, days
import sweep_gold as sg
from sweep_gold import simulate

SYMBOL = "GOLDi"
SPREAD = 26


def make_sig(f, o, zone, rsi_band, need_candle, atr_floor_ratio):
    c, e50, rr7, a = f["c"], f["e50"], f["rr7"], f["a"]
    n = len(c)
    med = np.full(n, np.nan)
    for i in range(50, n):
        med[i] = np.median(a[i - 50:i + 1])

    def sig(i, st):
        if not (np.isfinite(e50[i]) and np.isfinite(rr7[i]) and np.isfinite(a[i])):
            return 0
        if not (np.isfinite(e50[i - 1]) and np.isfinite(med[i])):
            return 0
        if a[i] < atr_floor_ratio * med[i]:
            return 0
        up = e50[i] > e50[i - 1]
        dn = e50[i] < e50[i - 1]
        dist = c[i] - e50[i]
        if c[i] > e50[i] and up and dist <= zone * a[i]:
            if rsi_band and not (45 <= rr7[i] <= 70):
                return 0
            elif not rsi_band and rr7[i] >= 70:
                return 0
            if need_candle and c[i] <= o[i]:
                return 0
            return 1
        if c[i] < e50[i] and dn and -dist <= zone * a[i]:
            if rsi_band and not (30 <= rr7[i] <= 55):
                return 0
            elif not rsi_band and rr7[i] <= 30:
                return 0
            if need_candle and c[i] >= o[i]:
                return 0
            return -1
        return 0
    return sig


def run(rates, label, **kw):
    cut = int(len(rates) * 0.6)
    sg.SESS = (7, 20)
    sg.MAX_SPREAD = 45
    out = []
    for sname, rs in (("TRAIN", rates[:cut]), ("TEST", rates[cut:])):
        d, f = features(rs)
        d.sp[:] = SPREAD
        r = simulate(d, make_sig(f, d.o, **kw), f["a"], None, 2.0, 2.25, "atr")
        out.append((sname, r, days(rs)))
    tr, te = out[0][1], out[1][1]
    trd = out[0][2]
    ted = out[1][2]
    netpt_tr = (tr["final"] - sg.INIT) / 0.01
    netpt_te = (te["final"] - sg.INIT) / 0.01
    print("%-38s tr$%8.2f te$%8.2f | tr %5.1f%% n%4d  te %5.1f%% n%4d | te/pt %6.2f" %
          (label, tr["final"], te["final"], tr["win"], tr["n"], te["win"], te["n"],
           (te["final"] - sg.INIT) / max(te["n"], 1)))
    return te["final"]


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    print("bars %d over %.0f days, spread %d" % (len(rates), days(rates), SPREAD))
    base = dict(zone=0.4, rsi_band=False, need_candle=False, atr_floor_ratio=0.0)
    print("--- baseline ---")
    run(rates, "base zone0.4", **base)
    print("--- tighter zone ---")
    for z in (0.3, 0.2):
        run(rates, "zone%.1f" % z, **{**base, "zone": z})
    print("--- + RSI mid-band ---")
    run(rates, "rsi_band", **{**base, "rsi_band": True})
    run(rates, "rsi_band zone0.3", **{**base, "rsi_band": True, "zone": 0.3})
    print("--- + candle confirmation ---")
    run(rates, "candle", **{**base, "need_candle": True})
    run(rates, "candle zone0.3", **{**base, "need_candle": True, "zone": 0.3})
    print("--- + ATR floor ---")
    for fr in (0.6, 0.8, 1.0):
        run(rates, "atrfloor%.1f" % fr, **{**base, "atr_floor_ratio": fr})
    run(rates, "atrfloor0.8 zone0.3", **{**base, "atr_floor_ratio": 0.8, "zone": 0.3})
    run(rates, "atrfloor0.8 candle", **{**base, "atr_floor_ratio": 0.8, "need_candle": True})
    mt5.shutdown()


if __name__ == "__main__":
    main()
