import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timezone

import mt5_trade as t

SYMBOL = "GOLDi"
RISK_PCT = 2.0
MAX_EFF_RISK_PCT = 15.0
MIN_SL_PTS = 40
ALLOW_MIN_LOT = True
MAX_POS = 1
MAX_DAILY_PCT = 15.0
MAX_DD_PCT = 40.0
TARGET_MULT = 10.0
MAX_SPREAD_PTS = 45
START_HOUR, END_HOUR = 7, 20
EMA_F, EMA_S = 9, 21
RSI_N, RSI_LVL = 7, 50.0
ATR_N = 14
SL_ATR, TP_ATR = 1.5, 2.25
BE_ATR, TRAIL_ATR = 1.0, 1.0
INIT_EQUITY = 4.05


def ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty_like(x)
    out[:n] = np.nan
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def wilder(x, n):
    out = np.empty_like(x)
    out[:n] = np.nan
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = np.clip(d, 0, None)
    dn = np.clip(-d, 0, None)
    au, ad = wilder(up, n), wilder(dn, n)
    rs = np.where(ad > 0, au / ad, 100.0)
    return 100.0 - 100.0 / (1.0 + rs)


def atr(h, l, c, n):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    return wilder(tr, n)


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 99000)
    if rates is None:
        print("no rates:", mt5.last_error())
        return
    n = len(rates)
    o, h, l, c = rates["open"], rates["high"], rates["low"], rates["close"]
    spread = rates["spread"].astype(float)
    times = rates["time"]
    point = 0.01
    now = datetime.now(timezone.utc).timestamp()
    offset_h = int(round((times[-1] - now) / 3600.0))
    print(f"bars={n} first={datetime.utcfromtimestamp(times[0])} last={datetime.utcfromtimestamp(times[-1])} server_offset~{offset_h}h")

    ef, es = ema(c, EMA_F), ema(c, EMA_S)
    r = rsi(c, RSI_N)
    a = atr(h, l, c, ATR_N)

    def hour(i):
        return int(((times[i] + offset_h * 3600) % 86400) // 3600)

    def day(i):
        return int((times[i] + offset_h * 3600) // 86400)

    def lots_and_sl(sl_dist, equity):
        per_lot_pt = (point / 0.01) * 1.0
        sl_pts = sl_dist / point
        loss_lot = sl_pts * per_lot_pt
        lots = (equity * RISK_PCT / 100.0) / loss_lot if loss_lot > 0 else 0
        if lots < 0.01:
            if not ALLOW_MIN_LOT:
                return 0.0, sl_dist
            lots = 0.01
            max_sl_pts = (equity * MAX_EFF_RISK_PCT / 100.0) / (0.01 * per_lot_pt)
            if max_sl_pts < MIN_SL_PTS:
                return 0.0, sl_dist
            if sl_dist > max_sl_pts * point:
                sl_dist = max_sl_pts * point
        else:
            lots = np.floor(lots / 0.01 + 1e-9) * 0.01
        return float(lots), sl_dist

    equity = INIT_EQUITY
    base = equity
    day_start = equity
    cur_day = day(0)
    day_halted = perm_halted = False
    pos = None  # dict(side, entry, sl, tp, lots, sig_bar)
    trades = []
    max_eq = equity
    max_dd = 0.0
    halt_reason = ""

    warm = max(EMA_S, ATR_N + 1, RSI_N) + 2
    for i in range(warm, n - 1):
        d = day(i)
        if d != cur_day:
            cur_day = d
            day_start = equity
            day_halted = False

        # manage open position on bar i (executed using bar i high/low)
        if pos is not None:
            closed = None
            if pos["side"] == "buy":
                if l[i] <= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif h[i] >= pos["tp"]:
                    closed = ("tp", pos["tp"])
            else:
                if h[i] >= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif l[i] <= pos["tp"]:
                    closed = ("tp", pos["tp"])
            if closed is None and not (START_HOUR <= hour(i) < END_HOUR):
                closed = ("eod", c[i])
            if closed is not None:
                _, px = closed
                pnl = (px - pos["entry"]) / 0.01 * 1.0 * pos["lots"]
                if pos["side"] == "sell":
                    pnl = -pnl
                equity += pnl
                trades.append((pos["side"], closed[0], pnl, equity))
                pos = None
            elif a[i] == a[i]:  # trailing at bar close (approx of tick trailing)
                if pos["side"] == "buy":
                    prof = c[i] - pos["entry"]
                    new_sl = pos["sl"]
                    if prof >= BE_ATR * a[i]:
                        new_sl = max(new_sl, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        new_sl = max(new_sl, c[i] - TRAIL_ATR * a[i])
                    pos["sl"] = new_sl
                else:
                    prof = pos["entry"] - c[i]
                    new_sl = pos["sl"]
                    if prof >= BE_ATR * a[i]:
                        new_sl = min(new_sl, pos["entry"])
                    if prof >= TRAIL_ATR * a[i]:
                        new_sl = min(new_sl, c[i] + TRAIL_ATR * a[i])
                    pos["sl"] = new_sl

        max_eq = max(max_eq, equity)
        max_dd = max(max_dd, (max_eq - equity) / max_eq)

        if pos is None:
            if equity >= base * TARGET_MULT:
                halt_reason = f"TARGET {TARGET_MULT}x reached at bar {i}"
                break
            if equity <= base * (1 - MAX_DD_PCT / 100.0):
                halt_reason = f"MAX DRAWDOWN halted at bar {i}"
                break
            if equity <= day_start * (1 - MAX_DAILY_PCT / 100.0):
                day_halted = True
            if day_halted:
                continue
            if not (START_HOUR <= hour(i + 1) < END_HOUR):
                continue
            if spread[i + 1] > MAX_SPREAD_PTS:
                continue

            # signal on closed bar i
            if not (np.isfinite(ef[i]) and np.isfinite(es[i]) and np.isfinite(r[i]) and np.isfinite(a[i])):
                continue
            cross_up = ef[i - 1] <= es[i - 1] and ef[i] > es[i]
            cross_dn = ef[i - 1] >= es[i - 1] and ef[i] < es[i]
            buy = cross_up and r[i] > RSI_LVL
            sell = cross_dn and r[i] < RSI_LVL
            if not (buy or sell):
                continue

            sl_dist = max(round(SL_ATR * a[i] / point), 1) * point
            tp_dist = max(round(TP_ATR * a[i] / point), 1) * point
            lots, sl_dist = lots_and_sl(sl_dist, equity)
            if lots <= 0:
                continue
            tp_dist = tp_dist * (sl_dist / (max(round(SL_ATR * a[i] / point), 1) * point))
            sp = spread[i + 1] * point
            entry = o[i + 1] + sp if buy else o[i + 1] - sp
            if buy:
                pos = {"side": "buy", "entry": entry, "sl": entry - sl_dist, "tp": entry + tp_dist, "lots": lots}
            else:
                pos = {"side": "sell", "entry": entry, "sl": entry + sl_dist, "tp": entry - tp_dist, "lots": lots}

    if pos is not None:
        pnl = (c[-1] - pos["entry"]) / 0.01 * pos["lots"]
        if pos["side"] == "sell":
            pnl = -pnl
        equity += pnl
        trades.append((pos["side"], "end", pnl, equity))
        pos = None

    wins = [x for x in trades if x[2] > 0]
    print(f"\n=== {SYMBOL} M1 backtest ({datetime.utcfromtimestamp(times[0]).date()} .. {datetime.utcfromtimestamp(times[-1]).date()}) ===")
    print(f"trades={len(trades)} wins={len(wins)} winrate={100*len(wins)/max(len(trades),1):.1f}%")
    print(f"final equity={equity:.2} ({equity/INIT_EQUITY:.2f}x) maxDD={100*max_dd:.1f}%")
    print("halt:", halt_reason or "ran full history")
    if trades:
        sls = [x for x in trades if x[1] == "sl"]
        tps = [x for x in trades if x[1] == "tp"]
        eods = [x for x in trades if x[1] == "eod"]
        print(f"exits: SL={len(sls)} TP={len(tps)} EOD={len(eods)}")
        print(f"gross win={sum(x[2] for x in wins):.2f} gross loss={sum(x[2] for x in trades if x[2]<=0):.2f}")
        print("first 5:", [(x[0], x[1], round(x[2], 2)) for x in trades[:5]])
        print("last 5 :", [(x[0], x[1], round(x[2], 2)) for x in trades[-5:]])


if __name__ == "__main__":
    main()
