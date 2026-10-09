import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"

if not mt5.initialize(path=TERMINAL):
    print("initialize failed:", mt5.last_error())
    raise SystemExit(1)

info = mt5.account_info()
if info is None:
    print("Not logged in. Last error:", mt5.last_error())
    print("Log in via File > Login to Trade Account in the MT5 window, then rerun.")
else:
    print("CONNECTED")
    print(f"  Login     : {info.login}")
    print(f"  Server    : {info.server}")
    print(f"  Name      : {info.name}")
    print(f"  Company   : {info.company}")
    print(f"  Currency  : {info.currency}")
    print(f"  Balance   : {info.balance}")
    print(f"  Equity    : {info.equity}")
    print(f"  Leverage  : 1:{info.leverage}")
    print(f"  Trade allowed: {info.trade_allowed}")
