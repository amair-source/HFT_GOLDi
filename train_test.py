import numpy as np
import MetaTrader5 as mt5
import mt5_trade as t
from tourney_gold import ema, sma, rsi, atr, Data
from sweep_gold import simulate


def make_features(rates, m5_full):
    d = Data(rates)
    d.off = 2
    c, h, l = d.c, d.h, d.l
    t5 = m5_full["time"]
    e5 = ema(m5_full["close"], 20)
    j = np.clip(np.searchsorted(t5, d.tm, side="right") - 2, 0, len(t5) - 1)
    trend5 = e5[j]
    up5 = c > trend5
    dn5 = c < trend5
    rr7 = rsi(c, 7)
    rr14 = rsi(c, 14)
    a = atr(h, l, c, 14)
    mid = sma(c, 20)
    sd = np.full(d.n, np.nan)
    for i in range(19, d.n):
        sd[i] = np.std(c[i - 19:i + 1], ddof=0)
    blo, bhi = mid - 2 * sd, mid + 2 * sd
    return d, dict(up5=up5, dn5=dn5, rr7=rr7, rr14=rr14, a=a, mid=mid, blo=blo, bhi=bhi)


def pullback_factory(rr, up5, dn5, lo_th, hi_th):
    def sig(i, st):
        if not np.isfinite(rr[i]) or not np.isfinite(up5[i]) if isinstance(up5, np.ndarray) else False:
            return 0
        if up5[i] and rr[i - 1] < lo_th and rr[i] >= lo_th:
            return 1
        if dn5[i] and rr[i - 1] > hi_th and rr[i] <= hi_th:
            return -1
        return 0
    return sig


def main():
    t.connect()
    rates = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M1, 0, 99000)
    m5 = mt5.copy_rates_from_pos("GOLDi", mt5.TIMEFRAME_M5, 0, 99000)
    cut = int(len(rates) * 0.6)
    train_rates, test_rates = rates[:cut], rates[cut:]

    d_tr, f_tr = make_features(train_rates, m5)
    d_te, f_te = make_features(test_rates, m5)

    combos = []
    # families: pullback x {rsi7/14} x thresholds x sl x tp ; bb_m5 sl variants
    for per_key in ("rr7", "rr14"):
        rr = f_tr[per_key]
        for lo_th, hi_th in ((30, 70), (35, 65), (40, 60)):
            def sig(i, st, rr=rr, up5=f_tr["up5"], dn5=f_tr["dn5"], lo_th=lo_th, hi_th=hi_th):
                if not np.isfinite(rr[i]) or not np.isfinite(up5[i]):
                    return 0
                if up5[i] and rr[i - 1] < lo_th and rr[i] >= lo_th:
                    return 1
                if dn5[i] and rr[i - 1] > hi_th and rr[i] <= hi_th:
                    return -1
                return 0
            for sl_a in (1.75, 2.0, 2.5):
                for tp_a in (1.5, 2.25, 3.0):
                    combos.append((f"pullback_{per_key}({lo_th},{hi_th}) sl{sl_a} tp{tp_a}", sig, sl_a, tp_a, "atr"))

    def sig_bbt(i, st, f=f_tr, c=d_tr.c):
        if not np.isfinite(f["blo"][i]):
            return 0
        if c[i] < f["blo"][i] and f["up5"][i]:
            return 1
        if c[i] > f["bhi"][i] and f["dn5"][i]:
            return -1
        return 0

    for sl_a in (1.0, 1.5, 2.0):
        combos.append((f"bb_revert_m5 sl{sl_a}", sig_bbt, sl_a, 0, "midbb"))

    print(f"TRAIN: {d_tr.n} bars / TEST: {d_te.n} bars")
    train_res = []
    for name, sig, sl_a, tp_a, mode in combos:
        r = simulate(d_tr, sig, f_tr["a"], f_tr["mid"], sl_a, tp_a, mode)
        train_res.append((name, sig, sl_a, tp_a, mode, r))
    train_res.sort(key=lambda x: -x[5]["final"])

    print("\nTop 8 on TRAIN -> evaluated on TEST (fixed params):")
    print(f"{'combo':42} {'trN':>4} {'trFin':>7} | {'teN':>4} {'teWin':>5} {'teFin':>7} {'tePts':>7}")
    for name, sig, sl_a, tp_a, mode, rtr in train_res[:8]:
        # rebuild same signal logic on test features
        if name.startswith("pullback"):
            per_key = "rr7" if "rr7" in name else "rr14"
            lo_th = int(name.split("(")[1].split(",")[0])
            hi_th = int(name.split(",")[1].split(")")[0])

            def sig_te(i, st, rr=f_te[per_key], up5=f_te["up5"], dn5=f_te["dn5"], lo_th=lo_th, hi_th=hi_th):
                if not np.isfinite(rr[i]) or not np.isfinite(up5[i]):
                    return 0
                if up5[i] and rr[i - 1] < lo_th and rr[i] >= lo_th:
                    return 1
                if dn5[i] and rr[i - 1] > hi_th and rr[i] <= hi_th:
                    return -1
                return 0
        else:
            def sig_te(i, st, f=f_te, d=d_te):
                if not np.isfinite(f["blo"][i]):
                    return 0
                c = d.c
                if c[i] < f["blo"][i] and f["up5"][i]:
                    return 1
                if c[i] > f["bhi"][i] and f["dn5"][i]:
                    return -1
                return 0
        rte = simulate(d_te, sig_te, f_te["a"], f_te["mid"], sl_a, tp_a, mode)
        print(f"{name:42} {rtr['n']:4d} {rtr['final']:7.2f} | {rte['n']:4d} {rte['win']:5.1f} {rte['final']:7.2f} {rte['net_pts']:7.0f}")


if __name__ == "__main__":
    main()
