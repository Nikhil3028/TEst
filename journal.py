"""Trades journal (paper + real) and the old watchlist file. Saved through store.py: next to the app, or in a
private GitHub Gist when that's configured (cloud hosting)."""
import uuid
from datetime import datetime

import store
from data import IST

TRADES_FILE = "paper_trades.json"
WATCHLIST_FILE = "watchlist.json"

DEFAULT_WATCHLIST = ["NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTYBEES", "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY",
                     "TCS", "SBIN", "BHARTIARTL", "ITC", "LT", "AXISBANK", "TMPV", "BAJFINANCE", "MARUTI"]


def _read(name: str, default):
    return store.read(name, default)


def _write(name: str, obj):
    store.write(name, obj)


def load_trades() -> list[dict]:
    return _read(TRADES_FILE, [])


def add_trade(symbol, ticker, side, qty, entry, stop, target, strategy, note="", kind="paper") -> dict:
    """kind: 'paper' (practice) or 'real' (a trade you actually placed on Groww, tracked here)."""
    t = {"id": uuid.uuid4().hex[:8], "kind": kind, "symbol": symbol, "ticker": ticker, "side": side, "qty": int(qty),
         "entry": round(float(entry), 2), "stop": round(float(stop), 2) if stop else None,
         "target": round(float(target), 2) if target else None, "strategy": strategy, "note": note,
         "entry_time": datetime.now(IST).strftime("%Y-%m-%d %H:%M"), "status": "OPEN",
         "exit": None, "exit_time": None, "exit_reason": None}
    trades = load_trades()
    trades.append(t)
    _write(TRADES_FILE, trades)
    return t


def close_trade(trade_id: str, price: float, reason: str = "Manual"):
    trades = load_trades()
    for t in trades:
        if t["id"] == trade_id and t["status"] == "OPEN":
            t.update(status="CLOSED", exit=round(float(price), 2), exit_reason=reason,
                     exit_time=datetime.now(IST).strftime("%Y-%m-%d %H:%M"))
    _write(TRADES_FILE, trades)


def delete_trade(trade_id: str):
    _write(TRADES_FILE, [t for t in load_trades() if t["id"] != trade_id])


def auto_close(prices: dict[str, float]) -> list[dict]:
    """Close open paper trades whose stop-loss or target has been crossed by the latest price."""
    closed = []
    for t in load_trades():
        px = prices.get(t["ticker"])
        if t["status"] != "OPEN" or px is None:
            continue
        long = t["side"] == "LONG"
        if t["stop"] and (px <= t["stop"] if long else px >= t["stop"]):
            close_trade(t["id"], t["stop"], "Stop-loss")
            closed.append({**t, "exit_reason": "Stop-loss"})
        elif t["target"] and (px >= t["target"] if long else px <= t["target"]):
            close_trade(t["id"], t["target"], "Target")
            closed.append({**t, "exit_reason": "Target"})
    return closed


def pnl(t: dict, price: float | None) -> tuple[float, float]:
    """(₹ P&L, % P&L) at `price` (or at the exit price for closed trades)."""
    px = t["exit"] if t["status"] == "CLOSED" else price
    if px is None:
        return 0.0, 0.0
    d = 1 if t["side"] == "LONG" else -1
    return d * (px - t["entry"]) * t["qty"], d * (px / t["entry"] - 1) * 100


def load_watchlist() -> list[str]:
    return _read(WATCHLIST_FILE, DEFAULT_WATCHLIST)


def save_watchlist(names: list[str]):
    _write(WATCHLIST_FILE, names)
