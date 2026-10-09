# HFT_GOLDi — WARNING: DO NOT USE

> ## ⚠️ DO NOT USE THIS EXPERT ADVISOR / DO NOT TRADE THIS CODE
>
> **This is a highly risky, experimental, and unfinished trading system.
> Running it on a live account can and probably will lose you money.**
>
> - It uses **martingale / averaging-down** — losing trades are doubled down, so a
>   single bad streak can produce large, fast losses.
> - It is **not** a real high-frequency strategy; the name is aspirational. It trades
>   a retail MT5 feed where the spread is wide and the "edge" is thin.
> - It was **never validated in a controlled, long-term, out-of-sample study.** Backtests
>   shown in the code are **in-sample-ish, overfit-prone, and assume spreads/fills that
>   may not exist.** Past results do not indicate future results.
> - It **manages trades you place manually** and **closes them on trend flips** — it can
>   close your positions without asking.
> - It is provided **for educational and research purposes only.**

## Disclaimers

- **Not financial advice.** Nothing here is a recommendation to buy or sell anything.
- **No warranty** of any kind, express or implied. No guarantee it will even compile,
  connect, execute, or do anything correctly.
- **You are solely responsible** for any use, any account, and any losses.
- Trading leveraged instruments (gold, CFDs, forex) carries a **high risk of losing
  all of your capital** and is not suitable for everyone.
- The author(s) accept **no liability** for any direct or indirect loss arising from
  the use of this software.
- Market data, broker execution, spreads, slippage, and liquidity can differ wildly
  between brokers and over time. **Test only on a demo account, if at all.**
- This repository may include code generated with the assistance of AI. Review it
  yourself before doing anything with it.

**If you do not fully understand this code, do not run it. If you do understand it,
you still probably should not run it.**

---

## Contents

| File | Purpose |
|---|---|
| `HFT_GOLDi.mq5` | The MetaTrader 5 Expert Advisor (MQL5). |
| `mt5_trade.py` | Thin Python wrapper over the MetaTrader5 package (connect, market orders, trailing helpers). |
| `mt5_connect.py` | Minimal connect-and-print-account-info helper. |
| `sweep_gold.py` | Backtest engine + parameter sweep (MQL5-style simulation in Python). |
| `tourney_gold.py` | Indicators (EMA/SMA/RSI/ATR) + `Data` container + simulation tournament. |
| `hft_scan.py` | Timeframe scan (M1/M15/M5) with train/test split. |
| `m5_freq.py` | M5 entry-frequency study. |
| `m5_long.py`, `tourney_m1.py` | Additional M1/M5 experiments. |
| `limit_trail.py` | Limit-entry + buffer-trailing study. |
| `backtest_gold.py`, `train_test.py`, `split_test.py`, `oos_test.py`, `sl_profile.py` | Research utilities. |
| `sl_check.py` | Stop-loss sensitivity sweep. |
| `compat.py` | Broker/symbol compatibility check. |

## Strategy sketch (for the curious)

- M5 EMA50 trend direction, optional RSI / EMA-slope / pullback-zone confluence.
- ATR-based SL/TP on every entry.
- Spread-aware trailing stop (buffer widens when spread is high).
- Averaging ("martingale") legs, shared max-open-trades pool.
- Can adopt and manage manually-opened trades.

## Sell / bottom line

Do not deploy this. It exists to show what a risky retail gold scalper looks like and
to document why most of them are a bad idea.
