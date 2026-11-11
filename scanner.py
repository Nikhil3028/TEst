"""Market scan: looks beyond the watchlist for today's best swing setups.

Once per trading day (after the 3:30 PM close, or the first time the app is opened that day) every stock of the chosen
index — NIFTY 50 / 100 / 200 — is analysed in the background exactly like a watchlist stock: Auto picks the strategy,
the walk-forward check grades it, and the signal is read off the last completed daily candle.

What is shown are the stocks where a BUY has just triggered, or is close, AND the method passed its test on years it
was never tuned on — ranked by that unseen-years result. It is a shortlist of the best-tested setups, not a promise:
a good record makes a profit more likely, never certain.
"""
import dataclasses
import io
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import core
import data
import store

UNIVERSES = {"NIFTY 50": "nifty50", "NIFTY 100": "nifty100", "NIFTY 200": "nifty200"}
OFF = "Off"
FILE = store.HERE / ".cache" / "scan.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
FRESH_BARS = 3        # a BUY that triggered up to this many candles ago still counts as new…
FRESH_MOVE = 2.0      # …while the price is within this % of the entry (not chasing, and not already going wrong)
NEAR_PCT = 2.0        # "close to a BUY": the trigger level is at most this % above the price
TRUSTED = ("High", "Medium")


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _constituents(slug: str) -> list[str]:
    raw = urllib.request.urlopen(urllib.request.Request(
        f"https://nsearchives.nseindia.com/content/indices/ind_{slug}list.csv", headers=UA), timeout=12).read()
    syms = pd.read_csv(io.BytesIO(raw))["Symbol"].astype(str).str.strip().tolist()
    if len(syms) < 20:
        raise ValueError("index list looks wrong")
    return syms


def constituents(universe: str) -> list[str]:
    """Stocks of the index, from NSE; the built-in popular list if NSE can't be reached."""
    try:
        return _constituents(UNIVERSES[universe])
    except Exception:  # noqa: BLE001
        return list(data.POPULAR)


def asof() -> str:
    """The trading day the scan belongs to: it rolls over at 3:40 PM, once the daily candle is complete."""
    return (datetime.now(data.IST) - timedelta(hours=15, minutes=40)).strftime("%Y-%m-%d")


@st.cache_resource
def _state() -> dict:
    return {"key": None, "rows": {}, "total": 0, "done": 0, "running": False, "lock": threading.Lock()}


def _row(sym: str, P) -> dict | None:
    c = core.build(core.Sel(symbol=sym, interval="1d"), P)
    if c is None:
        return None
    S = core.signal(c)
    a = c.AUTO_INFO or {}
    te = a.get("test") or {}
    per_year = None
    if te.get("trades"):
        yrs = max((te["to"] - te["from"]).days / 365.25, 0.5)
        per_year = ((1 + te["ret"] / 100) ** (1 / yrs) - 1) * 100 if te["ret"] > -100 else -100.0
    t = c.res.open_trade
    closes = c.raw["Close"].tail(90)
    row = {"symbol": c.symbol, "name": core.name_of(sym), "ltp": round(c.ltp, 2), "chg_pct": round(c.chg_pct, 2),
           "kind": S["kind"], "verdict": S["verdict"], "headline": S["headline"], "conf": list(S["confidence"]),
           "strat": core.SHORT_NAME.get(c.strat_name, c.strat_name), "per_year": per_year, "pf": te.get("pf"),
           "trades": te.get("trades", 0), "spark": [round(float(x), 2) for x in closes],
           "stop": S.get("stop"), "trigger": list(S["trigger"]) if S.get("trigger") else None, "entry": None}
    if t is not None and t.side == "LONG":
        row["entry"] = {"price": round(t.entry, 2), "date": f"{t.entry_time:%d %b}",
                        "bars": int((c.df.index > t.entry_time).sum())}
    return row


def _run(key: tuple, syms: list[str], P):
    s = _state()
    for sym in syms:
        if s["key"] != key:      # settings changed: a newer scan took over
            return
        try:
            row = _row(sym, P)
        except Exception:  # noqa: BLE001 — one bad symbol must not stop the scan
            row = None
        with s["lock"]:
            if s["key"] != key:
                return
            if row:
                s["rows"][sym] = row
            s["done"] += 1
        time.sleep(0.15)         # leave the processor to the pages people are looking at
    with s["lock"]:
        s["running"] = False
        try:
            FILE.parent.mkdir(exist_ok=True)
            FILE.write_text(json.dumps({"key": list(key), "rows": s["rows"], "at": datetime.now(data.IST).isoformat()}))
        except Exception:  # noqa: BLE001 — the saved copy only speeds up the next start
            pass


def ensure(P) -> dict:
    """Start today's scan if it hasn't run yet (or load it from disk) and return its progress:
    {'rows': {symbol: row}, 'done', 'total', 'running', 'universe'}."""
    s = _state()
    key = (asof(), P.scan, P.cost_delivery, *P.ind, core.LIB_VERSION)
    with s["lock"]:
        if s["key"] != key:
            saved = None
            try:
                saved = json.loads(FILE.read_text())
            except Exception:  # noqa: BLE001 — no saved scan yet
                pass
            if saved and tuple(saved.get("key", ())) == key:
                s.update(key=key, rows=saved["rows"], total=len(saved["rows"]), done=len(saved["rows"]), running=False)
            else:
                syms = constituents(P.scan)
                s.update(key=key, rows={}, total=len(syms), done=0, running=True)
                P2 = dataclasses.replace(P, news=False, closed_only=True)   # news isn't fetched for 100+ stocks
                threading.Thread(target=_run, args=(key, syms, P2), daemon=True, name="market-scan").start()
        return {"rows": dict(s["rows"]), "done": s["done"], "total": s["total"], "running": s["running"], "universe": P.scan}


def picks(rows: dict) -> dict:
    """{'new': [...], 'near': [...]} — rows that pass the unseen-years test, best record first.

    new  = BUY on the last candle, or a BUY from the last few candles whose price is still at the entry;
    near = waiting, with the BUY level within a couple of percent."""
    new, near = [], []
    for r in rows.values():
        if r["conf"][0] not in TRUSTED or (r["per_year"] or 0) <= 0:
            continue
        e = r.get("entry")
        if r["kind"] == "BUY":
            new.append({**r, "badge": "BUY", "line": r["headline"]})
        elif r["kind"] == "HOLD" and e and e["bars"] <= FRESH_BARS \
                and abs(move := (r["ltp"] / e["price"] - 1) * 100) <= FRESH_MOVE and (r["stop"] is None or r["ltp"] > r["stop"]):
            new.append({**r, "badge": "BUY", "line": f"Triggered {e['date']} at ₹{e['price']:,.2f} · now {move:+.1f}% — "
                                                      "still near the entry price"})
        elif r["kind"] == "WAIT" and r["trigger"] and r["trigger"][0].startswith("Buy") and r["trigger"][1]:
            dist = (r["trigger"][1] / r["ltp"] - 1) * 100
            if 0 < dist <= NEAR_PCT:
                near.append({**r, "badge": "NEAR BUY", "dist": dist,
                             "line": f"Turns BUY on a close above ₹{r['trigger'][1]:,.2f} — {dist:.1f}% away"})
    rank = lambda r: (TRUSTED.index(r["conf"][0]), -(r["per_year"] or 0))   # noqa: E731
    return {"new": sorted(new, key=rank), "near": sorted(near, key=lambda r: (TRUSTED.index(r["conf"][0]), r["dist"]))}
