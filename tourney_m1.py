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


def main():
    t.connect()
    r1 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 99000)
    r5 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    d = Data(r1)
    c, h, l, o = d.c, d.h, d.l, d.o
    n = d.n
    print(f"M1 bars={n} {datetime.fromtimestamp(d.tm[0], timezone.utc)} -> {datetime.fromtimestamp(d.tm[-1], timezone.utc)} off={d.off}h")

    # M1 indicators
    ef, es = ema(c, 9), ema(c, 21)
    r7, r14 = rsi(c, 7), rsi(c, 14)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)
    sd = np.full(n, np.nan)
    for i in range(19, n):
        sd[i] = np.std(c[i - 19:i + 1], ddof=0)
    blo, bhi = mid - 2 * sd, mid + 2 * sd
    hh = np.full(n, np.nan)
    ll = np.full(n, np.nan)
    for i in range(20, n):
        hh[i] = np.max(h[i - 19:i + 1])
        ll[i] = np.min(l[i - 19:i + 1])

    # M5 trend: EMA20 of last closed M5 bar, mapped to each M1 bar
    c5 = r5["close"]
    t5 = r5["time"]
    e5 = ema(c5, 20)
    j = np.searchsorted(t5, d.tm, side="right") - 1  # forming M5 index
    j = np.clip(j - 1, 0, len(t5) - 1)               # last closed M5
    trend5 = e5[j]
    trend_up5 = c > trend5
    trend_dn5 = c < trend5

    def cross_up(i):
        return ef[i - 1] <= es[i - 1] and ef[i] > es[i]

    def cross_dn(i):
        return ef[i - 1] >= es[i - 1] and ef[i] < es[i]

    def s_ema_cross(i, st):
        if cross_up(i) and r7[i] > 50:
            return 1
        if cross_dn(i) and r7[i] < 50:
            return -1
        return 0

    def s_trend_cross(i, st):
        if cross_up(i) and trend_up5[i]:
            return 1
        if cross_dn(i) and trend_dn5[i]:
            return -1
        return 0

    def s_bb_revert(i, st):
        if not np.isfinite(blo[i]):
            return 0
        if c[i] < blo[i]:
            return 1
        if c[i] > bhi[i]:
            return -1
        return 0

    def s_bb_trend(i, st):
        if not np.isfinite(blo[i]):
            return 0
        if c[i] < blo[i] and trend_up5[i]:
            return 1
        if c[i] > bhi[i] and trend_dn5[i]:
            return -1
        return 0

    def s_pullback(i, st):
        if not np.isfinite(r14[i]) or not np.isfinite(trend5[i]):
            return 0
        if trend_up5[i] and r14[i - 1] < 35 and r14[i] >= 35:
            return 1
        if trend_dn5[i] and r14[i - 1] > 65 and r14[i] <= 65:
            return -1
        return 0

    def s_donchian(i, st):
        if not np.isfinite(hh[i]) or not np.isfinite(a[i]):
            return 0
        if c[i] > hh[i - 1]:
            return 1
        if c[i] < ll[i - 1]:
            return -1
        return 0

    def s_orb15(i, st):
        dd = d.day(i)
        if st.get("day") != dd:
            st["day"] = dd
            st["start"] = None
            st["entered"] = False
        if st.get("start") is None and d.hour(i) == SESS[0] and d.tm[i] % 3600 < 60:
            st["start"] = i
        s0 = st.get("start")
        if s0 is None or i < s0 + 15 or st["entered"]:
            return 0
        if i == s0 + 15:
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

    strats = [
        ("ema_cross", s_ema_cross, 1.5, 2.25, "atr"),
        ("trend_cross_m5", s_trend_cross, 1.5, 2.25, "atr"),
        ("bb_revert", s_bb_revert, 1.5, None, "midbb"),
        ("bb_revert_m5", s_bb_trend, 1.5, None, "midbb"),
        ("pullback_m5", s_pullback, 1.5, 2.25, "atr"),
        ("donchian20", s_donchian, 2.0, 4.0, "atr"),
        ("orb15", s_orb15, 1.5, 2.25, "atr"),
    ]

    warm = 60
    results = []
    for name, fn, sl_a, tp_a, mode in strats:
        equity = INIT
        pos = None
        st = {}
        trades = []
        max_eq = equity
        max_dd = 0.0
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

            max_eq = max(max_eq, equity)
            max_dd = max(max_dd, (max_eq - equity) / max_eq)

            if pos is None:
                if not (SESS[0] <= d.hour(i + 1) < SESS[1]):
                    continue
                if d.sp[i + 1] > MAX_SPREAD:
                    continue
                s = fn(i, st)
                if s == 0:
                    continue
                if not (np.isfinite(a[i]) and a[i] > 0):
                    continue
                sl_d = max(round(sl_a * a[i] / POINT), 1) * POINT
                if mode == "atr":
                    tp_d = max(round(tp_a * a[i] / POINT), 1) * POINT
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
        results.append(dict(name=name, n=len(trades), win=100 * len(wins) / max(len(trades), 1),
                            final=equity, dd=100 * max_dd, sl=sls, tp=tps, eod=eods,
                            net_pts=(equity - INIT) / 0.01))

    results.sort(key=lambda x: -x["final"])
    print(f"\n{'strategy':16} {'N':>4} {'win%':>5} {'final$':>7} {'net_pts':>8} {'maxDD%':>6} {'SL/TP/EOD':>10}")
    for r in results:
        print(f"{r['name']:16} {r['n']:4d} {r['win']:5.1f} {r['final']:7.2f} {r['net_pts']:8.0f} {r['dd']:6.1f} {r['sl']:3d}/{r['tp']:3d}/{r['eod']:3d}")


if __name__ == "__main__":
    main()
