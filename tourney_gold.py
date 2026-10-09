import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timezone

import mt5_trade as t

SYMBOL = "GOLDi"
POINT = 0.01
RISK_PCT = 2.0
MAX_EFF = 20.0
MIN_SL_PTS = 40
MAX_DAILY = 20.0
MAX_DD = 40.0
TARGET = 10.0
MAX_SPREAD = 45
Sess = (7, 20)
BE_ATR, TRAIL_ATR = 1.0, 1.5
INIT = 4.05


def ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty(len(x))
    out[:n] = np.nan
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x, n):
    out = np.full(len(x), np.nan)
    cs = np.cumsum(np.insert(x, 0, 0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def wilder(x, n):
    out = np.empty(len(x))
    out[:n] = np.nan
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    au = wilder(np.clip(d, 0, None), n)
    ad = wilder(np.clip(-d, 0, None), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(ad > 0, au / ad, 100.0)
    rs = np.where(np.isfinite(rs), rs, 100.0)
    return 100.0 - 100.0 / (1.0 + rs)


def atr(h, l, c, n):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    return wilder(tr, n)


class Data:
    def __init__(self, rates):
        self.o, self.h, self.l, self.c = rates["open"], rates["high"], rates["low"], rates["close"]
        self.sp = rates["spread"].astype(float)
        self.tm = rates["time"]
        now = datetime.now(timezone.utc).timestamp()
        self.off = int(round((self.tm[-1] - now) / 3600.0))
        self.n = len(rates)

    def hour(self, i):
        return int(((self.tm[i] + self.off * 3600) % 86400) // 3600)

    def day(self, i):
        return int((self.tm[i] + self.off * 3600) // 86400)


def build_signals(d, c, h, l):
    ef, es = ema(c, 9), ema(c, 21)
    e50, e200, e89 = ema(c, 50), ema(c, 200), ema(c, 89)
    r7, r14 = rsi(c, 7), rsi(c, 14)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)
    sd = np.full(len(c), np.nan)
    for i in range(19, len(c)):
        sd[i] = np.std(c[i - 19:i + 1], ddof=0)
    lo, hi = mid - 2 * sd, mid + 2 * sd
    hh20 = np.full(len(c), np.nan)
    ll20 = np.full(len(c), np.nan)
    for i in range(20, len(c)):
        hh20[i] = np.max(h[i - 19:i + 1])
        ll20[i] = np.min(l[i - 19:i + 1])
    return dict(ef=ef, es=es, e50=e50, e200=e200, e89=e89, r7=r7, r14=r14,
                a=a, mid=mid, lo=lo, hi=hi, hh=hh20, ll=ll20)


def make_strats(ind, d):
    ef, es, e50, e200, e89 = ind["ef"], ind["es"], ind["e50"], ind["e200"], ind["e89"]
    r7, r14, a = ind["r7"], ind["r14"], ind["a"]
    mid, lo, hi, hh, ll = ind["mid"], ind["lo"], ind["hi"], ind["hh"], ind["ll"]
    c, h, l = d.c, d.h, d.l

    def cross_ok(i, arr1, arr2):
        return (arr1[i - 1] <= arr2[i - 1] and arr1[i] > arr2[i]) or (arr1[i - 1] >= arr2[i - 1] and arr1[i] < arr2[i])

    def s_ema_cross(i, st):
        if not cross_ok(i, ef, es):
            return 0
        return 1 if ef[i] > es[i] and r7[i] > 50 else (-1 if ef[i] < es[i] and r7[i] < 50 else 0)

    def s_trend_cross(i, st):
        if not np.isfinite(e50[i]):
            return 0
        if ef[i - 1] <= es[i - 1] and ef[i] > es[i] and c[i] > e50[i]:
            return 1
        if ef[i - 1] >= es[i - 1] and ef[i] < es[i] and c[i] < e50[i]:
            return -1
        return 0

    def s_bb_revert(i, st):
        if not np.isfinite(lo[i]):
            return 0
        if c[i] < lo[i]:
            return 1
        if c[i] > hi[i]:
            return -1
        return 0

    def s_bb_trend(i, st):
        if not np.isfinite(lo[i]) or not np.isfinite(e200[i]):
            return 0
        if c[i] < lo[i] and c[i] > e200[i]:
            return 1
        if c[i] > hi[i] and c[i] < e200[i]:
            return -1
        return 0

    def s_pullback(i, st):
        if not np.isfinite(e89[i]) or not np.isfinite(r14[i]):
            return 0
        if c[i] > e89[i] and r14[i - 1] < 40 and r14[i] >= 40:
            return 1
        if c[i] < e89[i] and r14[i - 1] > 60 and r14[i] <= 60:
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

    def s_orb(i, st):
        dd = d.day(i)
        if st.get("day") != dd:
            st["day"] = dd
            st["start"] = None
            st["entered"] = False
        if st.get("start") is None and d.hour(i) == Sess[0]:
            st["start"] = i
        s0 = st.get("start")
        if s0 is None or i < s0 + 5 or st["entered"]:
            return 0
        if i == s0 + 5:
            st["hi"] = np.max(h[s0:i + 1])
            st["lo"] = np.min(l[s0:i + 1])
            return 0
        if c[i] > st["hi"]:
            st["entered"] = True
            return 1
        if c[i] < st["lo"]:
            st["entered"] = True
            return -1
        return 0

    return [
        ("ema_cross(base)", s_ema_cross, 1.5, 2.25, "atr"),
        ("trend_cross", s_trend_cross, 1.5, 2.25, "atr"),
        ("bb_revert", s_bb_revert, 1.5, None, "midbb"),
        ("bb_trend", s_bb_trend, 1.5, None, "midbb"),
        ("pullback_rsi", s_pullback, 1.5, 2.25, "atr"),
        ("donchian20", s_donchian, 2.0, 4.0, "atr"),
        ("orb30", s_orb, 1.5, 2.25, "atr"),
    ]


def run(d, ind, name, sigfn, sl_atr, tp_atr, exit_mode, eval_mode=True):
    c, h, l = d.c, d.h, d.l
    a, mid = ind["a"], ind["mid"]
    equity = INIT
    base = INIT
    day_start = equity
    cur_day = d.day(0)
    day_halt = False
    pos = None
    st = {}
    trades = []
    max_eq = equity
    max_dd = 0.0
    halt = ""
    warm = 205

    for i in range(warm, d.n - 1):
        dd = d.day(i)
        if dd != cur_day:
            cur_day = dd
            day_start = equity
            day_halt = False

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
            if closed is None and not (Sess[0] <= d.hour(i) < Sess[1]):
                closed = ("eod", c[i])
            if closed is not None:
                pnl = (closed[1] - pos["entry"]) / 0.01 * pos["lots"] * pos["side"]
                equity += pnl
                trades.append((pos["side"], closed[0], pnl, equity))
                pos = None
            elif np.isfinite(a[i]):
                if pos["side"] == 1:
                    prof = c[i] - pos["entry"]
                    ns = pos["sl"]
                    if prof >= BE_ATR * a[i]:
                        ns = max(ns, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        ns = max(ns, c[i] - TRAIL_ATR * a[i])
                    pos["sl"] = ns
                else:
                    prof = pos["entry"] - c[i]
                    ns = pos["sl"]
                    if prof >= BE_ATR * a[i]:
                        ns = min(ns, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        ns = min(ns, c[i] + TRAIL_ATR * a[i])
                    pos["sl"] = ns

        max_eq = max(max_eq, equity)
        max_dd = max(max_dd, (max_eq - equity) / max_eq)

        if pos is None:
            if not eval_mode:
                if equity >= base * TARGET:
                    halt = "TARGET 10x"
                    break
                if equity <= base * (1 - MAX_DD / 100):
                    halt = "MAX DD floor"
                    break
            if equity <= day_start * (1 - MAX_DAILY / 100):
                day_halt = True
            if day_halt:
                continue
            if not (Sess[0] <= d.hour(i + 1) < Sess[1]):
                continue
            if d.sp[i + 1] > MAX_SPREAD:
                continue
            s = sigfn(i, st)
            if s == 0:
                continue
            if not (np.isfinite(a[i]) and a[i] > 0):
                continue
            if not eval_mode:
                sl_d = max(round(sl_atr * a[i] / POINT), 1) * POINT
                if tp_atr is not None:
                    tp_d = max(round(tp_atr * a[i] / POINT), 1) * POINT
                per_lot_pt = 1.0
                sl_pts = sl_d / POINT
                lots = (equity * RISK_PCT / 100) / (sl_pts * per_lot_pt)
                if lots < 0.01:
                    lots = 0.01
                    max_sl_pts = (equity * MAX_EFF / 100) / (0.01 * per_lot_pt)
                    if max_sl_pts < MIN_SL_PTS:
                        continue
                    if sl_d > max_sl_pts * POINT:
                        ratio = (max_sl_pts * POINT) / sl_d
                        sl_d = max_sl_pts * POINT
                        if tp_atr is not None:
                            tp_d = tp_d * ratio
                else:
                    lots = np.floor(lots / 0.01 + 1e-9) * 0.01
            else:
                lots = 0.01
                sl_d = max(round(sl_atr * a[i] / POINT), 1) * POINT
                if tp_atr is not None:
                    tp_d = max(round(tp_atr * a[i] / POINT), 1) * POINT
                max_sl_pts = (equity * MAX_EFF / 100) / 0.01
                if max_sl_pts < MIN_SL_PTS:
                    continue
                if sl_d > max_sl_pts * POINT:
                    ratio = (max_sl_pts * POINT) / sl_d
                    sl_d = max_sl_pts * POINT
                    if tp_atr is not None:
                        tp_d = tp_d * ratio
            entry = d.o[i + 1] + d.sp[i + 1] * POINT * s
            if exit_mode == "midbb":
                tp_p = mid[i + 1]
                if not np.isfinite(tp_p) or (s == 1 and tp_p <= entry) or (s == -1 and tp_p >= entry):
                    continue
            else:
                tp_p = entry + s * tp_d
            sl_p = entry - s * sl_d
            pos = dict(side=s, entry=entry, sl=sl_p, tp=tp_p, lots=float(lots))

    if pos is not None:
        pnl = (c[-1] - pos["entry"]) / 0.01 * pos["lots"] * pos["side"]
        equity += pnl
        trades.append((pos["side"], "end", pnl, equity))

    wins = [x for x in trades if x[2] > 0]
    sls = sum(1 for x in trades if x[1] == "sl")
    tps = sum(1 for x in trades if x[1] == "tp")
    eods = sum(1 for x in trades if x[1] == "eod")
    return dict(name=name, trades=len(trades), win=100 * len(wins) / max(len(trades), 1),
                final=equity, mult=equity / INIT, dd=100 * max_dd, sl=sls, tp=tps, eod=eods,
                halt=halt or "full", pnl=equity - INIT)


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 99000)
    d = Data(rates)
    print(f"M5 bars={d.n} {datetime.fromtimestamp(d.tm[0], timezone.utc).date()} -> {datetime.fromtimestamp(d.tm[-1], timezone.utc).date()} server_off={d.off}h")
    ind = build_signals(d, d.c, d.h, d.l)
    results = []
    for name, fn, sl_atr, tp_atr, mode in make_strats(ind, d):
        r = run(d, ind, name, fn, sl_atr, tp_atr, mode)
        results.append(r)
    results.sort(key=lambda x: -x["final"])
    print(f"\n{'strategy':16} {'trades':>6} {'win%':>5} {'final$':>7} {'mult':>6} {'maxDD%':>6} {'SL/TP/EOD':>10}  halt")
    for r in results:
        print(f"{r['name']:16} {r['trades']:6d} {r['win']:5.1f} {r['final']:7.2f} {r['mult']:5.2f}x {r['dd']:6.1f} {r['sl']:3d}/{r['tp']:3d}/{r['eod']:3d}   {r['halt']}")


if __name__ == "__main__":
    main()
