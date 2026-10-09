import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data
from sweep_gold import simulate

MAX_SPREAD = 45
SESS = (7, 20)


def features(rates):
    d = Data(rates)
    d.off = 2
    c, h, l = d.c, d.h, d.l
    rr7 = rsi(c, 7)
    rr14 = rsi(c, 14)
    e20 = ema(c, 20)
    e50 = ema(c, 50)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)
    return d, dict(rr7=rr7, rr14=rr14, e20=e20, e50=e50, a=a, mid=mid, c=c)


def pb_sig(rr, trend, lo, hi):
    def sig(i, st):
        if not np.isfinite(rr[i]) or not np.isfinite(trend[i]):
            return 0
        if c0[i] > trend[i] and rr[i - 1] < lo and rr[i] >= lo:
            return 1
        if c0[i] < trend[i] and rr[i - 1] > hi and rr[i] <= hi:
            return -1
        return 0
    return sig


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M5, 0, 99000)
    cut = int(len(rates) * 0.6)
    segs = [("FULL", rates), ("TRAIN60", rates[:cut]), ("TEST40", rates[cut:])]
    combos = []
    for per in ("rr7", "rr14"):
        for trend_key in ("e20", "e50"):
            for lo, hi in ((30, 70), (35, 65)):
                for sl_a in (1.75, 2.0, 2.5):
                    for tp_a in (1.5, 2.25, 3.0):
                        combos.append((f"pb_{per}_{trend_key}({lo},{hi}) sl{sl_a} tp{tp_a}", per, trend_key, lo, hi, sl_a, tp_a))

    out = {}
    for sname, rates_seg in segs:
        d, f = features(rates_seg)
        global c0
        c0 = f["c"]
        rows = []
        for (name, per, tk, lo, hi, sl_a, tp_a) in combos:
            sig = pb_sig(f[per], f[tk], lo, hi)
            r = simulate(d, sig, f["a"], f["mid"], sl_a, tp_a, "atr")
            rows.append((name, r))
        out[sname] = rows
        print(f"{sname}: {d.n} bars")

    # rank on TRAIN, show those on TEST
    tr = sorted(out["TRAIN60"], key=lambda x: -x[1]["final"])
    te_map = {n: r for n, r in out["TEST40"]}
    fu_map = {n: r for n, r in out["FULL"]}
    print(f"\n{'combo':40} {'trFin':>7} {'teN':>4} {'teFin':>7} {'tePts':>7} {'fullFin':>8}")
    for name, rtr in tr[:10]:
        rte = te_map[name]
        rfu = fu_map[name]
        print(f"{name:40} {rtr['final']:7.2f} {rte['n']:4d} {rte['final']:7.2f} {rte['net_pts']:7.0f} {rfu['final']:8.2f}")
    print("\nBottom 3 on TRAIN:")
    for name, rtr in tr[-3:]:
        rte = te_map[name]
        print(f"{name:40} {rtr['final']:7.2f} {rte['n']:4d} {rte['final']:7.2f} {rte['net_pts']:7.0f}")


if __name__ == "__main__":
    main()
