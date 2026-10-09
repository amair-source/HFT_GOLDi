import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from hft_scan import features, days

SYMBOL = "GOLDi"
SPREAD = 26
POINT = 0.01
INIT = 4.05
SESS = (7, 20)
MAX_SPREAD = 45


def simulate(d, sig, a, sl_a, tp_a, be_atr, trail_atr):
    n = d.n
    c, h, l, o = d.c, d.h, d.l, d.o
    equity = INIT
    pos = None
    st = {}
    trades = []
    for i in range(60, n - 1):
        if pos is not None:
            closed = None
            if pos["side"] == 1:
                if l[i] <= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif h[i] >= pos["tp"]:
                    closed = ("tp", pos["tp"])
            else:
                if h[i] >= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif l[i] <= pos["tp"]:
                    closed = ("tp", pos["tp"])
            if closed is None and not (SESS[0] <= d.hour(i) < SESS[1]):
                closed = ("eod", c[i])
            if closed is not None:
                pnl = (closed[1] - pos["entry"]) / POINT * POINT * pos["side"]
                equity += pnl
                trades.append((closed[0], pnl))
                pos = None
            elif np.isfinite(a[i]):
                if pos["side"] == 1:
                    ns = pos["sl"]
                    prof = c[i] - pos["entry"]
                    if be_atr >= 0 and prof >= be_atr * a[i]:
                        ns = max(ns, pos["entry"])
                    if trail_atr > 0 and prof >= trail_atr * a[i]:
                        ns = max(ns, c[i] - trail_atr * a[i])
                    pos["sl"] = ns
                else:
                    ns = pos["sl"]
                    prof = pos["entry"] - c[i]
                    if be_atr >= 0 and prof >= be_atr * a[i]:
                        ns = min(ns, pos["entry"])
                    if trail_atr > 0 and prof >= trail_atr * a[i]:
                        ns = min(ns, c[i] + trail_atr * a[i])
                    pos["sl"] = ns
        if pos is None:
            if not (SESS[0] <= d.hour(i + 1) < SESS[1]):
                continue
            if d.sp[i + 1] > MAX_SPREAD:
                continue
            s = sig(i, st)
            if s == 0 or not (np.isfinite(a[i]) and a[i] > 0):
                continue
            sl_d = max(round(sl_a * a[i] / POINT), 1) * POINT
            tp_d = max(round(tp_a * a[i] / POINT), 1) * POINT
            entry = o[i + 1] + d.sp[i + 1] * POINT * s
            pos = dict(side=s, entry=entry, sl=entry - s * sl_d, tp=entry + s * tp_d)
    if pos is not None:
        pnl = (c[-1] - pos["entry"]) / POINT * POINT * pos["side"]
        equity += pnl
        trades.append(("end", pnl))
    wins = [x[1] for x in trades if x[1] > 0]
    losses = [x[1] for x in trades if x[1] <= 0]
    aw = sum(wins) / max(len(wins), 1)
    al = sum(losses) / max(len(losses), 1)
    gross_w = sum(wins)
    gross_l = -sum(losses)
    return dict(final=equity, n=len(trades), win=100 * len(wins) / max(len(trades), 1),
                aw=aw, al=al, pf=(gross_w / gross_l if gross_l > 0 else 999),
                rr=(aw / -al if al < 0 else 999))


def atrfloor_sig(f, o, ratio=1.0):
    c, e50, rr7, a = f["c"], f["e50"], f["rr7"], f["a"]
    n = len(c)
    med = np.full(n, np.nan)
    for i in range(50, n):
        med[i] = np.median(a[i - 50:i + 1])

    def sig(i, st):
        if not (np.isfinite(e50[i]) and np.isfinite(rr7[i]) and np.isfinite(a[i])
                and np.isfinite(e50[i - 1]) and np.isfinite(med[i])):
            return 0
        if a[i] < ratio * med[i]:
            return 0
        up = e50[i] > e50[i - 1]
        dn = e50[i] < e50[i - 1]
        dist = c[i] - e50[i]
        if c[i] > e50[i] and up and dist <= 0.4 * a[i] and rr7[i] < 70:
            return 1
        if c[i] < e50[i] and dn and -dist <= 0.4 * a[i] and rr7[i] > 30:
            return -1
        return 0
    return sig


def run(rates, label, sl_a, tp_a, be_atr, trail_atr):
    cut = int(len(rates) * 0.6)
    r = {}
    for sname, rs in (("tr", rates[:cut]), ("te", rates[cut:])):
        d, f = features(rs)
        d.sp[:] = SPREAD
        r[sname] = simulate(d, atrfloor_sig(f, d.o), f["a"], sl_a, tp_a, be_atr, trail_atr)
    tr, te = r["tr"], r["te"]
    print("%-30s tr$%7.2f te$%7.2f | te win%4.1f aw%5.2f al%6.2f PF%4.2f R:R%4.2f n%4d" %
          (label, tr["final"], te["final"], te["win"], te["aw"], te["al"], te["pf"], te["rr"], te["n"]))


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    print("bars %d, %.0f days" % (len(rates), days(rates)))
    print("--- baseline (SL2.0 TP2.25, BE1.0 trail1.5) ---")
    run(rates, "base", 2.0, 2.25, 1.0, 1.5)
    print("--- widen TP (keep trailing) ---")
    for tp in (3.0, 4.0, 5.0):
        run(rates, "TP%.1f" % tp, 2.0, tp, 1.0, 1.5)
    print("--- no fixed BE, wider chandelier trail ---")
    for tr in (2.0, 2.5, 3.0):
        run(rates, "noBE trail%.1f" % tr, 2.0, 4.0, -1, tr)
    print("--- no trail at all (pure SL/TP) ---")
    for tp in (2.25, 3.0, 4.0):
        run(rates, "noexit TP%.1f" % tp, 2.0, tp, -1, 0)
    print("--- tighter SL ---")
    for sl in (1.5, 1.75):
        run(rates, "SL%.2f TP3" % sl, sl, 3.0, -1, 2.0)
    mt5.shutdown()


if __name__ == "__main__":
    main()
