import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, rsi, atr, Data
import sweep_gold as sg
from sweep_gold import simulate

SESS = (7, 20)
MAX_SPREAD_PTS = 45


def features(rates, off=2):
    d = Data(rates)
    d.off = off
    c, h, l = d.c, d.h, d.l
    return d, dict(
        rr7=rsi(c, 7), rr14=rsi(c, 14),
        e20=ema(c, 20), e50=ema(c, 50),
        a=atr(h, l, c, 14), c=c,
    )


def pb_sig(c0, rr, trend, lo, hi):
    def sig(i, st):
        if not np.isfinite(rr[i]) or not np.isfinite(trend[i]):
            return 0
        if c0[i] > trend[i] and rr[i - 1] < lo and rr[i] >= lo:
            return 1
        if c0[i] < trend[i] and rr[i - 1] > hi and rr[i] <= hi:
            return -1
        return 0
    return sig


def days(rates):
    return (rates["time"][-1] - rates["time"][0]) / 86400.0


def run(tf, label, spread_pts, combos, rates=None):
    if rates is None:
        rates = mt5.copy_rates_from_pos("XAUUSD", tf, 0, 99000)
    cut = int(len(rates) * 0.6)
    segs = [("FULL", rates), ("TRAIN", rates[:cut]), ("TEST", rates[cut:])]
    sg.SESS = SESS
    sg.MAX_SPREAD = MAX_SPREAD_PTS
    out = {}
    for sname, rs in segs:
        d, f = features(rs)
        d.sp[:] = spread_pts          # force live-realistic spread (demo history says 0)
        rows = []
        for (name, per, tk, lo, hi, sl_a, tp_a) in combos:
            sig = pb_sig(f["c"], f[per], f[tk], lo, hi)
            r = simulate(d, sig, f["a"], None, sl_a, tp_a, "atr")
            r["tpd"] = r["n"] / days(rs)
            rows.append((name, r))
        out[sname] = rows
    print(f"\n=== {label} spread={spread_pts}pts ({days(rates):.0f} days) ===")
    tr = sorted(out["TRAIN"], key=lambda x: -x[1]["final"])
    te = {n: r for n, r in out["TEST"]}
    fu = {n: r for n, r in out["FULL"]}
    print(f"{'combo':34} {'tr$':>7} {'te$':>7} {'teN':>4} {'td/d':>5} {'full$':>8} {'fd/d':>5}")
    both = 0
    for name, r1 in tr:
        r2, r3 = te[name], fu[name]
        ok = r1["final"] > 0 and r2["final"] > 0
        both += ok
        print(f"{name:34} {r1['final']:7.2f} {r2['final']:7.2f} {r2['n']:4d} "
              f"{r2['tpd']:5.2f} {r3['final']:8.2f} {r3['tpd']:5.2f}{'  *' if ok else ''}")
    print(f"positive on BOTH train+test: {both}/{len(tr)}")


def main():
    t.connect()
    combos = []
    for per in ("rr7", "rr14"):
        for tk in ("e20", "e50"):
            for sl_a in (2.0, 2.5):
                for tp_a in (2.25, 3.0):
                    combos.append((f"pb_{per}_{tk} sl{sl_a} tp{tp_a}",
                                   per, tk, 30, 70, sl_a, tp_a))
    for tf, label in ((mt5.TIMEFRAME_M1, "M1"), (mt5.TIMEFRAME_M15, "M15")):
        for sp in (26, 13):
            run(tf, label, sp, combos)
    # sanity: does the known winner reproduce on demo XAUUSD M5 data?
    run(mt5.TIMEFRAME_M5, "M5 sanity", 26, [c for c in combos if c[0] == "pb_rr7_e50 sl2.5 tp2.25"])


if __name__ == "__main__":
    main()
