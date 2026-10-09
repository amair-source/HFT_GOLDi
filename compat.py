import MetaTrader5 as mt5

if not mt5.initialize():
    print("INIT FAIL", mt5.last_error())
    raise SystemExit(1)

a = mt5.account_info()
t = mt5.terminal_info()
print("==== ACCOUNT ====")
print("login %s | server %s | type %s | currency %s" %
      (a.login, a.server, "DEMO" if a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else
       "REAL/CONTEST" if a.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL else "?",
       a.currency))
print("balance %.2f | equity %.2f | leverage 1:%d | margin_free %.2f" %
      (a.balance, a.equity, a.leverage, a.margin_free))
print("trade_allowed(account) %s | trade_expert %s" % (a.trade_allowed, a.trade_expert))
print("margin_mode %s | so_mode %s | so_call %s so_stopout %s" %
      (a.margin_mode, a.margin_so_mode, a.margin_so_call, a.margin_so_so))
print("expert_allowed %s | trade_allowed(terminal) %s | connected %s" %
      (t.trade_allowed, t.trade_allowed, t.connected))

print("\n==== SYMBOL SEARCH ====")
cands = ["XAUUSD", "GOLD", "GOLDi", "XAUUSDm", "XAUUSD.", "GOLD.", "XAUUSD_i"]
found = []
for name in cands:
    si = mt5.symbol_info(name)
    if si is not None:
        found.append(name)
print("present:", found if found else "NONE of the candidates")
allgold = [s.name for s in (mt5.symbols_get() or []) if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
print("all gold-like symbols:", allgold)

for name in found:
    si = mt5.symbol_info(name)
    si = mt5.symbol_info(name)
    print("\n---- %s ----" % name)
    print("visible %s | trade_mode %s | exemode %s" %
          (si.visible, si.trade_mode, si.trade_exemode))
    print("digits %d | point %.5f | tick_size %.5f | tick_value %.5f | contract %.2f" %
          (si.digits, si.point, si.trade_tick_size, si.trade_tick_value, si.trade_contract_size))
    print("vol min %.2f max %.2f step %.2f" % (si.volume_min, si.volume_max, si.volume_step))
    print("stops_level %d pts | freeze_level %d pts" % (si.trade_stops_level, si.trade_freeze_level))
    print("filling_mode %d (bit1=FOK bit2=IOC)" % si.filling_mode)
    print("spread %d pts | margin_initial %.4f | bid %.3f ask %.3f" %
          (si.spread, si.margin_initial, si.bid, si.ask))
    om = si.order_mode
    print("order_mode: market%s limit%s stop%s stoplimit%s" %
          (bool(om & 1), bool(om & 2), bool(om & 4), bool(om & 8)))

print("\n==== CURRENT EXPOSURE ====")
ps = mt5.positions_get() or []
print("open positions: %d" % len(ps))
for p in ps:
    print("  #%d %s %s %.2f @ %.3f sl %.3f tp %.3f magic %d profit %.2f" %
          (p.ticket, p.symbol, "BUY" if p.type == 0 else "SELL", p.volume, p.price_open,
           p.sl, p.tp, p.magic, p.profit))
os = mt5.orders_get() or []
print("pending orders: %d" % len(os))

print("\n==== VERDICT ====")
print("EA fills with FOK first, then IOC -> symbol filling_mode must include FOK or IOC")
print("EA sends SL/TP with orders -> stops_level distance will be respected by EA (ATR based)")
mt5.shutdown()
