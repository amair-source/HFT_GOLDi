import numpy as np
from datetime import datetime

import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data
from sweep_gold import simulate

WINDOWS = [
    ("W1 2025-09", datetime(2025, 9, 1)),
    ("W2 2026-01", datetime(2026, 1, 15)),
    ("W3 2026-06 (in-sample)", datetime(2026, 6, 29)),
]


def run_window(start):
    r1 = mt5.copy_rates_from("GOLDi", mt5.TIMEFRAME_M1, start, 99000)
    if r1 is None or len(r1) < 5000:
        return None
    d = Data(r1)
    d.off = 2  # server offset fixed (Data() can't infer it from old bars)
    c, h, l = d.c, d.h, d.l
    r5 = mt5.copy_rates_from("GOLDi", mt5.TIMEFRAME_M5, start, 99000)
    if r5 is None:
        return None
    t5 = r5["time"]
    e5 = ema(r5["close"], 20)
    j = np.clip(np.searchsorted(t5, d.tm, side="right") - 2, 0, len(t5) - 1)
    trend5 = e5[j]
    up5 = c > trend5
    dn5 = c < trend5
    rr = rsi(c, 7)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)

    def sig(i, st):
        if not np.isfinite(rr[i]) or not np.isfinite(trend5[i]):
            return 0
        if up5[i] and rr[i - 1] < 30 and rr[i] >= 30:
            return 1
        if dn5[i] and rr[i - 1] > 70 and rr[i] <= 70:
            return -1
        return 0

    out = {}
    for sl_a, tp_a in ((2.0, 1.5), (2.0, 2.25), (2.5, 2.25)):
        r = simulate(d, sig, a, mid, sl_a, tp_a, "atr")
        out[(sl_a, tp_a)] = r
    days = (d.tm[-1] - d.tm[0]) / 86400
    return d, out, days


def main():
    t.connect()
    for name, start in WINDOWS:
        res = run_window(start)
        if res is None:
            print(f"{name}: NO DATA {mt5.last_error()}")
            continue
        d, out, days = res
        print(f"{name}: bars={d.n} days~{days:.0f} {datetime.fromtimestamp(d.tm[0]).date()} -> {datetime.fromtimestamp(d.tm[-1]).date()}")
        for (sl_a, tp_a), r in out.items():
            print(f"   sl{sl_a} tp{tp_a}: N={r['n']:4d} win={r['win']:5.1f} final={r['final']:7.2f} netpts={r['net_pts']:7.0f}")


if __name__ == "__main__":
    main()
