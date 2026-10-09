import MetaTrader5 as mt5

TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def connect():
    if not mt5.initialize(path=TERMINAL):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    if mt5.account_info() is None:
        raise RuntimeError("Not logged in — log in via the MT5 terminal window")
    return True


def account():
    a = mt5.account_info()
    return None if a is None else {
        "login": a.login, "server": a.server, "balance": a.balance,
        "equity": a.equity, "margin_free": a.margin_free,
        "leverage": a.leverage, "trade_allowed": a.trade_allowed,
    }


def positions():
    return [{
        "ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == 0 else "SELL",
        "volume": p.volume, "price_open": p.price_open, "sl": p.sl, "tp": p.tp,
        "profit": p.profit, "swap": p.swap,
    } for p in mt5.positions_get() or []]


def price(symbol):
    if not mt5.symbol_select(symbol, True):
        raise ValueError(f"Unknown symbol: {symbol}")
    t = mt5.symbol_info_tick(symbol)
    return {"symbol": symbol, "bid": t.bid, "ask": t.ask, "time": t.time}


def _filling(symbol):
    s = mt5.symbol_info(symbol)
    m = s.filling_mode if s else 0
    if m & 1:
        return mt5.ORDER_FILLING_FOK
    if m & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def market_order(symbol, side, volume, sl=None, tp=None, comment=""):
    """side: 'buy' or 'sell'"""
    if not mt5.symbol_select(symbol, True):
        raise ValueError(f"Unknown symbol: {symbol}")
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    tick = mt5.symbol_info_tick(symbol)
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    price_ = tick.ask if side == "buy" else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price_,
        "deviation": 20,
        "magic": 234000,
        "comment": comment or "py",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling(symbol),
    }
    if sl is not None:
        request["sl"] = float(sl)
    if tp is not None:
        request["tp"] = float(tp)
    result = mt5.order_send(request)
    if result is None:
        raise RuntimeError(f"order_send failed: {mt5.last_error()}")
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"order rejected: {result.retcode} {result.comment}")
    return {"ticket": result.order, "price": result.price, "volume": result.volume}


def close_position(ticket):
    p = mt5.positions_get(ticket=ticket)
    if not p:
        raise ValueError(f"No position {ticket}")
    p = p[0]
    tick = mt5.symbol_info_tick(p.symbol)
    side = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    price_ = tick.bid if p.type == 0 else tick.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": p.ticket,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": side,
        "price": price_,
        "deviation": 20,
        "magic": 234000,
        "comment": "close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling(p.symbol),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"close failed: {result} / {mt5.last_error()}")
    return {"closed_ticket": p.ticket, "price": result.price}


def close_all():
    return [close_position(p.ticket) for p in (mt5.positions_get() or [])]


def history(days=7):
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=days)
    deals = mt5.history_deals_get(start, end) or []
    return [{
        "time": d.time, "symbol": d.symbol, "volume": d.volume,
        "price": d.price, "profit": d.profit, "comment": d.comment,
    } for d in deals]


if __name__ == "__main__":
    connect()
    print("account :", account())
    print("positions:", positions())
