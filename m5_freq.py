import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import Data, rsi, ema, atr
import sweep_gold as sg
from sweep_gold import simulate

from hft_scan import features, pb_sig, days

COMBOS = []
for per in ("rr7", "rr14"):
    for sl_a in (2.0, 2.5):
        for tp_a in (2.25, 3.0):
            COMBOS.append((f"{per} sl{sl_a} tp{tp_a}", per, "e50", 0, 0, sl_a, tp_a))


def run(label, rates, thresh, spread_pts, sess):
    cut = int(len(rates) * 0.6)
    segs = [("TRAIN", rates[:cut]), ("TEST", rates[cut:]), ("FULL", rates)]
    sg.SESS = sess
    sg.MAX_SPREAD = 45
    out = {}
    for sname, rs in segs:
        d, f = features(rs)
        d.sp[:] = spread_pts
        rows = []
        for (name, per, tk, _lo, _hi, sl_a, tp_a) in COMBOS:
            sig = pb_sig(f["c"], f[per], f[tk], thresh, 100 - thresh)
            r = simulate(d, sig, f["a"], None, sl_a, tp_a, "atr")
            r["tpd"] = r["n"] / days(rs)
            rows.append((name, r))
        out[sname] = rows
    te = dict(out["TEST"])
    fu = dict(out["FULL"])
    print(f"\n=== {label} | thresh {thresh}/{100-thresh} | sp {spread_pts} | sess {sess} ===")
    print(f"{'combo':20} {'tr$':>7} {'te$':>7} {'te/d':>5} {'full$':>8} {'f/d':>5}")
    best = None
    for name, r1 in sorted(out["TRAIN"], key=lambda x: -x[1]["final"]):
        r2, r3 = te[name], fu[name]
        star = "*" if (r1["final"] > 0 and r2["final"] > 0) else " "
        print(f"{name:20} {r1['final']:7.2f} {r2['final']:7.2f} {r2['tpd']:5.2f} {r3['final']:8.2f} {r3['tpd']:5.2f} {star}")
        if r1["final"] > 0 and r2["final"] > 0:
            if best is None or r2["final"] > best[1]:
                best = (name, r2["final"], r3["final"], r3["tpd"])
    return best


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M5, 0, 99000)
    results = {}
    results["base sp26 sess7-20 th30"] = run("base", rates, 30, 26, (7, 20))
    results["th35 sp26 sess7-20"]      = run("th35", rates, 35, 26, (7, 20))
    results["th40 sp26 sess7-20"]      = run("th40", rates, 40, 26, (7, 20))
    results["th30 sp26 sess7-23"]      = run("sess723", rates, 30, 26, (7, 23))
    results["th30 sp13 sess7-23"]      = run("sp13+723", rates, 30, 13, (7, 23))
    results["th30 sp0 sess7-20 LIMIT*"]= run("limit-upper", rates, 30, 0, (7, 20))
    print("\n=== SUMMARY (configurations positive on BOTH train+test) ===")
    for k, v in results.items():
        print(f"{k:32} {str(v):>60}")


if __name__ == "__main__":
    main()
