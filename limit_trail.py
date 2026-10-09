import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
import sweep_gold as sg
from tourney_gold import Data, rsi, ema, atr
from hft_scan import features, pb_sig, days

WARM = 60


def simulate_lt(d, sig, a, buffer_usd, activate_atr, use_tp, tp_a=2.25, sl_a=2.5):
    """Limit entry at signal close + fixed-buffer trailing SL.
    activate_atr: 0 = trail from entry, else trail starts after profit >= activate_atr*ATR
    (initial SL = entry - sl_a*ATR until activation).  use_tp: ATR target or None."""
    c, h, l, o = d.c, d.h, d.l, d.o
    equity, pos, pending, trades = sg.INIT, None, None, []
    fills = signals = 0
    for i in range(WARM, d.n - 1):
        hour_now = d.hour(i)
        in_sess_now = sg.SESS[0] <= hour_now < sg.SESS[1]

        # pending limit: expires outside session
        if pending is not None and not in_sess_now:
            pending = None

        # manage open position
        if pos is not None:
            closed = None
            if pos["side"] == 1:
                if l[i] <= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif use_tp and h[i] >= pos["tp"]:
                    closed = ("tp", pos["tp"])
            else:
                if h[i] >= pos["sl"]:
                    closed = ("sl", pos["sl"])
                elif use_tp and l[i] <= pos["tp"]:
                    closed = ("tp", pos["tp"])
            if closed is None and not in_sess_now:
                closed = ("eod", c[i])
            if closed is not None:
                pnl = (closed[1] - pos["entry"]) * pos["side"]
                equity += pnl
                trades.append((closed[0], pnl))
                pos = None
            else:
                # fixed-buffer trail (ratchet), evaluated on close
                if pos["side"] == 1:
                    if activate_atr <= 0 or (c[i] - pos["entry"]) >= activate_atr * a[i]:
                        pos["sl"] = max(pos["sl"], c[i] - buffer_usd)
                else:
                    if activate_atr <= 0 or (pos["entry"] - c[i]) >= activate_atr * a[i]:
                        pos["sl"] = min(pos["sl"], c[i] + buffer_usd)

        # fill pending limit (conservative: same-bar adverse checked next loop pass
        # via entry-at-limit then immediate exit checks below)
        if pending is not None and pos is None and in_sess_now:
            fside = pending["side"]
            hit = (l[i] <= pending["px"]) if fside == 1 else (h[i] >= pending["px"])
            if hit:
                fills += 1
                entry = pending["px"]
                sl = entry - sl_a * a[i] if activate_atr > 0 else entry - buffer_usd
                if activate_atr <= 0:
                    sl = entry - buffer_usd if fside == 1 else entry + buffer_usd
                else:
                    sl = entry - sl_a * a[i] if fside == 1 else entry + sl_a * a[i]
                tp = entry + tp_a * a[i] if fside == 1 else entry - tp_a * a[i]
                pos = dict(side=fside, entry=entry, sl=sl, tp=tp)
                pending = None
                # conservative same-bar stop touch
                if fside == 1 and l[i] <= sl:
                    pnl = (sl - entry)
                    equity += pnl; trades.append(("sl", pnl)); pos = None
                elif fside == -1 and h[i] >= sl:
                    pnl = (entry - sl)
                    equity += pnl; trades.append(("sl", pnl)); pos = None

        # new signal -> place limit (only if flat and no pending)
        if pos is None and pending is None and in_sess_now and i + 1 < d.n:
            if not (sg.SESS[0] <= d.hour(i + 1) < sg.SESS[1]):
                pass
            elif d.sp[i + 1] > sg.MAX_SPREAD:
                pass
            else:
                s = sig(i, {})
                if s != 0 and np.isfinite(a[i]) and a[i] > 0:
                    signals += 1
                    px = c[i]
                    # limit must rest on correct side of the market at placement
                    if s == 1 and px < o[i + 1]:
                        pending = dict(side=1, px=px)
                    elif s == -1 and px > o[i + 1]:
                        pending = dict(side=-1, px=px)
    return dict(final=equity, n=len(trades), fills=fills, signals=signals,
                wins=sum(1 for k, p in trades if p > 0))


def run(label, rates, buffers, acts, tps):
    cut = int(len(rates) * 0.6)
    segs = [("TRAIN", rates[:cut]), ("TEST", rates[cut:]), ("FULL", rates)]
    print(f"\n=== {label} ===")
    print(f"{'config':34} {'tr$':>7} {'te$':>7} {'teN':>4} {'fill%':>5} {'full$':>8} {'fN':>4} {'f/d':>5}")
    for buf, act, use_tp in buffers:
        results = {}
        for sname, rs in segs:
            d, f = features(rs)
            d.sp[:] = 26
            sig = pb_sig(f["c"], f["rr7"], f["e50"], 30, 70)
            r = simulate_lt(d, sig, f["a"], buf, act, use_tp)
            r["tpd"] = r["n"] / days(rs)
            results[sname] = r
        tr, te, fu = results["TRAIN"], results["TEST"], results["FULL"]
        name = f"buf{'$%.2f' % buf} act{act or 'now'} tp{'2.25' if use_tp else 'none'}"
        star = "*" if (tr["final"] > 0 and te["final"] > 0 and fu["tpd"] > 0.2) else " "
        fillpct = 100 * fu["fills"] / max(fu["signals"], 1)
        print(f"{name:34} {tr['final']:7.2f} {te['final']:7.2f} {te['n']:4d} {fillpct:5.0f} "
              f"{fu['final']:8.2f} {fu['n']:4d} {fu['tpd']:5.2f} {star}")


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M5, 0, 99000)
    grid = [(buf, act, tp)
            for buf in (1.00, 0.10)
            for act in (0.0, 1.0)
            for tp in (True, False)]
    run("M5 limit+buffer-trail (spread 26 gate)", rates, grid, None, None)


if __name__ == "__main__":
    main()
