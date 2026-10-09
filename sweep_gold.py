import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timezone

import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data

SYMBOL = "GOLDi"
POINT = 0.01
MAX_SPREAD = 45
SESS = (7, 20)
BE_ATR, TRAIL_ATR = 1.0, 1.5
INIT = 4.05


def simulate(d, sig, a, mid, sl_a, tp_a, mode, sl_extra=0.0, tp_extra=0.0):
    n = d.n
    c, h, l, o = d.c, d.h, d.l, d.o
    equity = INIT
    pos = None
    st = {}
    trades = []
    warm = 60
    for i in range(warm, n - 1):
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
                pnl = (closed[1] - pos["entry"]) / 0.01 * 0.01 * pos["side"]
                equity += pnl
                trades.append((closed[0], pnl))
                pos = None
            elif np.isfinite(a[i]):
                if pos["side"] == 1:
                    ns = pos["sl"]
                    prof = c[i] - pos["entry"]
                    if prof >= BE_ATR * a[i]:
                        ns = max(ns, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        ns = max(ns, c[i] - TRAIL_ATR * a[i])
                    pos["sl"] = ns
                else:
                    ns = pos["sl"]
                    prof = pos["entry"] - c[i]
                    if prof >= BE_ATR * a[i]:
                        ns = min(ns, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        ns = min(ns, c[i] + TRAIL_ATR * a[i])
                    pos["sl"] = ns

        if pos is None:
            if not (SESS[0] <= d.hour(i + 1) < SESS[1]):
                continue
            if d.sp[i + 1] > MAX_SPREAD:
                continue
            s = sig(i, st)
            if s == 0:
                continue
            if not (np.isfinite(a[i]) and a[i] > 0):
                continue
            sl_d = max(round((sl_a * a[i] + sl_extra) / POINT), 1) * POINT
            if mode == "atr":
                tp_d = max(round((tp_a * a[i] + tp_extra) / POINT), 1) * POINT
            entry = o[i + 1] + d.sp[i + 1] * POINT * s
            if mode == "midbb":
                tp_p = mid[i + 1]
                if not np.isfinite(tp_p) or (s == 1 and tp_p <= entry + POINT) or (s == -1 and tp_p >= entry - POINT):
                    continue
            else:
                tp_p = entry + s * tp_d
            pos = dict(side=s, entry=entry, sl=entry - s * sl_d, tp=tp_p)

    if pos is not None:
        pnl = (c[-1] - pos["entry"]) / 0.01 * 0.01 * pos["side"]
        equity += pnl
        trades.append(("end", pnl))

    wins = [x for x in trades if x[1] > 0]
    sls = sum(1 for x in trades if x[0] == "sl")
    tps = sum(1 for x in trades if x[0] == "tp")
    eods = sum(1 for x in trades if x[0] == "eod")
    return dict(n=len(trades), win=100 * len(wins) / max(len(trades), 1), final=equity,
                net_pts=(equity - INIT) / 0.01, sl=sls, tp=tps, eod=eods)


def main():
    t.connect()
    r1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 99000)
    d = Data(r1)
    c, h, l = d.c, d.h, d.l
    n = d.n
    ef, es = ema(c, 9), ema(c, 21)
    r7, r14 = rsi(c, 7), rsi(c, 14)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)
    c5 = None

    # M5 trend mapping
    r5 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    t5 = r5["time"]
    e5 = ema(r5["close"], 20)
    j = np.clip(np.searchsorted(t5, d.tm, side="right") - 2, 0, len(t5) - 1)
    trend5 = e5[j]
    up5 = c > trend5
    dn5 = c < trend5

    results = []

    # Family A: pullback in M5 trend with RSI
    for per in (7, 14):
        rr = rsi(c, per)
        for lo_th, hi_th in ((35, 65), (30, 70), (40, 60)):
            def sig(i, st, rr=rr, lo_th=lo_th, hi_th=hi_th):
                if not np.isfinite(rr[i]) or not np.isfinite(trend5[i]):
                    return 0
                if up5[i] and rr[i - 1] < lo_th and rr[i] >= lo_th:
                    return 1
                if dn5[i] and rr[i - 1] > hi_th and rr[i] <= hi_th:
                    return -1
                return 0
            for sl_a in (1.0, 1.5, 2.0):
                for tp_a in (1.5, 2.25, 3.0):
                    res = simulate(d, sig, a, mid, sl_a, tp_a, "atr")
                    results.append((f"pullback rsi{per}({lo_th},{hi_th}) sl{sl_a} tp{tp_a}", res))

    # Family B: bb revert in M5 trend
    sd = np.full(n, np.nan)
    for i in range(19, n):
        sd[i] = np.std(c[i - 19:i + 1], ddof=0)
    blo, bhi = mid - 2 * sd, mid + 2 * sd

    def sig_bbt(i, st):
        if not np.isfinite(blo[i]):
            return 0
        if c[i] < blo[i] and up5[i]:
            return 1
        if c[i] > bhi[i] and dn5[i]:
            return -1
        return 0

    for sl_a in (0.75, 1.0, 1.5):
        res = simulate(d, sig_bbt, a, mid, sl_a, 0, "midbb")
        results.append((f"bb_revert_m5 sl{sl_a} tpmid", res))

    # Family C: orb15 variants
    def make_orb(rng):
        def sig(i, st):
            dd = d.day(i)
            if st.get("day") != dd:
                st["day"] = dd
                st["start"] = None
                st["entered"] = False
            if st.get("start") is None and d.hour(i) == SESS[0] and d.tm[i] % 3600 < 60:
                st["start"] = i
            s0 = st.get("start")
            if s0 is None or i < s0 + rng or st["entered"]:
                return 0
            if i == s0 + rng:
                st["hi"] = np.max(h[s0:i + 1])
                st["lo"] = np.min(l[s0:i + 1])
                return 0
            if "hi" in st and c[i] > st["hi"]:
                st["entered"] = True
                return 1
            if "hi" in st and c[i] < st["lo"]:
                st["entered"] = True
                return -1
            return 0
        return sig

    for rng in (10, 15, 30):
        for sl_a in (1.0, 1.5):
            for tp_a in (1.5, 2.25):
                res = simulate(d, make_orb(rng), a, mid, sl_a, tp_a, "atr")
                results.append((f"orb{rng} sl{sl_a} tp{tp_a}", res))

    # ATR-scaled + fixed extra SL (spread buffer variant) for best family later
    results.sort(key=lambda x: -x[1]["final"])
    print(f"{'combo':40} {'N':>4} {'win%':>5} {'final$':>7} {'net_pts':>8} {'SL/TP/EOD':>10}")
    for name, r in results[:25]:
        print(f"{name:40} {r['n']:4d} {r['win']:5.1f} {r['final']:7.2f} {r['net_pts']:8.0f} {r['sl']:3d}/{r['tp']:3d}/{r['eod']:3d}")
    print("...")
    for name, r in results[-3:]:
        print(f"{name:40} {r['n']:4d} {r['win']:5.1f} {r['final']:7.2f} {r['net_pts']:8.0f} {r['sl']:3d}/{r['tp']:3d}/{r['eod']:3d}")


if __name__ == "__main__":
    main()
