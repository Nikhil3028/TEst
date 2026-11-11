"""Momentum portfolio: hold the strongest stocks of the market, re-pick them once a month.

Why it exists: the per-stock timing signals protect against crashes but, in testing, made less than simply holding.
Choosing WHICH stocks to hold did better — on 2010-2026 data the strongest 20 of the 200 most-traded stocks beat
holding all 200 in both halves of the period (see `backtest`). It is also how NSE's own momentum indices work.

The rule (fixed in advance, the same one the backtest uses):
  1. Universe: of today's NIFTY 500 stocks, the 200 most traded at that date with a full year of prices.
  2. Score: 6-month and 12-month return, each divided by the stock's volatility, standardised and averaged.
  3. Hold the top N in equal amounts. Re-rank after each month's last close; trade on the next trading day.

Honest limits, shown wherever the numbers are: the pool is TODAY's NIFTY 500, so companies that were delisted are
missing and past results are flattered; falls of 35-45% happened; some years (2025) it lost while the index rose.
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

import data
import scanner
import store

UNIVERSE_N = 200
COST = 0.0015            # per side: charges 0.10% + slippage 0.05%
BT_START = "2010-01-01"
BT_FILE = store.HERE / ".cache" / "momentum_bt.json"
FILE = "portfolio.json"


def pool() -> list[str]:
    try:
        return scanner._constituents("nifty500")
    except Exception:  # noqa: BLE001 — NSE unreachable: the scan's index is better than nothing
        return scanner.constituents("NIFTY 200")


def _download(syms: list[str], period: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dividend- and split-adjusted closes and volumes, one column per symbol."""
    closes, vols = [], []
    for i in range(0, len(syms), 100):
        d = yf.download([s + ".NS" for s in syms[i:i + 100]], period=period, interval="1d", auto_adjust=True,
                        progress=False, threads=8, group_by="column")
        closes.append(d["Close"])
        vols.append(d["Volume"])
    px, vol = pd.concat(closes, axis=1), pd.concat(vols, axis=1)
    for f in (px, vol):
        f.columns = [c.replace(".NS", "") for c in f.columns]
        f.index = pd.DatetimeIndex(f.index).tz_localize(None)
    return px.sort_index(), vol.sort_index()


def _prepare(px: pd.DataFrame, vol: pd.DataFrame) -> dict:
    """Clean the prices and pre-compute what the ranking needs."""
    px = px.loc[:, px.notna().sum() >= 260]
    listed = px.notna().sum(axis=1)
    px = px[listed >= 0.6 * listed.rolling(60, min_periods=1).max()]     # drop stray rows (holiday / special sessions)
    vol = vol.reindex(index=px.index, columns=px.columns)
    ret = px.pct_change(fill_method=None)
    ret = ret.mask(ret.abs() > 0.45, 0.0)                                 # a 45% day is a data error, not a trade
    adj = (1 + ret.fillna(0)).cumprod().where(px.notna())
    return {"px": px, "adj": adj, "tv": (px * vol).rolling(126, min_periods=100).median(),
            "sd": ret.rolling(252, min_periods=200).std() * np.sqrt(252)}


def _scores(D: dict, i: int) -> pd.DataFrame:
    """Ranked table for bar position i: score, 6- and 12-month return, for the point-in-time universe."""
    adj = D["adj"]
    ok = adj.iloc[i - 252:i + 1].notna().sum() >= 245                    # a full year of prices
    member = D["tv"].iloc[i].where(ok).rank(ascending=False) <= UNIVERSE_N
    p0 = adj.iloc[i]
    r6, r12 = p0 / adj.iloc[i - 126] - 1, p0 / adj.iloc[i - 252] - 1
    a, b = (r6 / D["sd"].iloc[i]).where(member), (r12 / D["sd"].iloc[i]).where(member)
    score = ((a - a.mean()) / a.std() + (b - b.mean()) / b.std()) / 2
    out = pd.DataFrame({"score": score, "r6": r6 * 100, "r12": r12 * 100, "price": D["px"].iloc[i]}).dropna(subset=["score"])
    return out.sort_values("score", ascending=False)


# ---------------------------------------------------------------- today's ranking
@st.cache_data(ttl=20 * 3600, show_spinner=False, persist="disk")
def ranking(day: str) -> pd.DataFrame:
    """The universe ranked as of the last close: symbol index; score, r6, r12, price, rank. `day` keys the cache."""
    D = _prepare(*_download(pool(), "2y"))
    t = _scores(D, len(D["adj"]) - 1)
    t["rank"] = range(1, len(t) + 1)
    t.attrs["asof"] = D["adj"].index[-1].strftime("%d %b %Y")
    return t


def target(rank: pd.DataFrame, n: int, capital: float) -> pd.DataFrame:
    """The N stocks to hold in equal amounts. A stock too expensive for even one share in its slot is skipped
    and the next-ranked one takes its place."""
    slot = capital / n
    rows = []
    for sym, r in rank.iterrows():
        qty = int(slot // r.price)
        if qty >= 1:
            rows.append({"symbol": sym, "rank": int(r["rank"]), "price": float(r.price), "qty": qty,
                         "value": qty * float(r.price), "r6": float(r.r6), "r12": float(r.r12)})
        if len(rows) == n:
            break
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the portfolio being followed
def load() -> dict | None:
    return store.read(FILE, None)


def save(tgt: pd.DataFrame, n: int, kind: str):
    now = datetime.now(data.IST)
    old = load() or {}
    store.write(FILE, {"n": n, "kind": kind, "started": old.get("started") or f"{now:%Y-%m-%d}",
                       "rebalanced": f"{now:%Y-%m-%d}",
                       "holdings": [{"symbol": r.symbol, "qty": int(r.qty), "price": round(r.price, 2)} for r in tgt.itertuples()]})


def clear():
    store.write(FILE, None)


def due(pf: dict) -> bool:
    """A new calendar month has started since the last rebalance."""
    return datetime.now(data.IST).strftime("%Y-%m") > pf["rebalanced"][:7]


def orders(pf: dict | None, tgt: pd.DataFrame) -> dict:
    """What to do to move from the saved holdings to the target: {'sell': [...], 'buy': [...], 'keep': [...]}."""
    have = {h["symbol"]: h for h in (pf or {}).get("holdings", [])}
    want = {r.symbol: r for r in tgt.itertuples()}
    return {"sell": [have[s] for s in have if s not in want],
            "buy": [{"symbol": s, "qty": int(r.qty), "price": r.price} for s, r in want.items() if s not in have],
            "keep": [have[s] for s in have if s in want]}


# ---------------------------------------------------------------- backtest
def _stats(c: pd.Series) -> dict:
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    yearly = c.groupby(c.index.year).last().pct_change().dropna()
    return {"cagr": float(((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1) * 100), "dd": float((c / c.cummax() - 1).min() * 100),
            "worst_year": float(yearly.min() * 100) if len(yearly) else 0.0,
            "worst_year_at": int(yearly.idxmin()) if len(yearly) else 0}


def _simulate(D: dict, n: int | None, market_ok: pd.Series | None = None) -> pd.Series:
    """Daily value of the portfolio. n=None holds the whole universe in equal amounts (the benchmark).
    Ranked at each month's last close, traded at the next day's close, charges on what changes."""
    adj, days = D["adj"], D["adj"].index
    ends = pd.Series(days, days).groupby([days.year, days.month]).last()
    rb = [days.get_loc(d) for d in ends if d >= pd.Timestamp(BT_START) and days.get_loc(d) + 1 < len(days)]
    eq, held, parts = 1.0, set(), []
    for k, i in enumerate(rb):
        i0 = i + 1
        i1 = rb[k + 1] + 1 if k + 1 < len(rb) else len(days) - 1
        if i1 <= i0 or i < 260:
            continue
        table = _scores(D, i)
        pick = list(table.index if n is None else table.index[:n])
        if market_ok is not None and not bool(market_ok.asof(days[i])):
            pick = []
        slots = len(pick) if n is None else n
        w = 1.0 / max(slots, 1)
        new = set(pick)
        eq *= 1 - (0.02 if n is None else (len(new - held) + len(held - new)) * w) * COST
        if pick:
            seg = adj[pick].iloc[i0:i1 + 1]
            v = eq * ((seg / seg.iloc[0]).ffill().fillna(1.0).sum(axis=1) * w + (1 - len(pick) * w))
        else:
            v = pd.Series(eq, index=days[i0:i1 + 1])
        parts.append(v.iloc[1:] if parts else v)
        eq, held = float(v.iloc[-1]), new
    return pd.concat(parts)


def backtest(force: bool = False) -> dict | None:
    """Results since 2010 for top-10 and top-20, with and without the market filter, against holding the whole
    universe and against the NIFTY 200 index. Downloads ~500 full price histories (about 3 minutes), so the result
    is kept on disk for 30 days. Returns the saved result, or None if there is none and force is False."""
    if not force:
        try:
            saved = json.loads(BT_FILE.read_text())
            if (datetime.now() - datetime.fromisoformat(saved["at"])).days < 30:
                return saved
        except Exception:  # noqa: BLE001 — never run, or unreadable
            pass
        return None
    D = _prepare(*_download(pool(), "max"))
    for k in D:
        D[k] = D[k].loc["2004-01-01":]
    idx = yf.download(["^NSEI", "^CNX200"], period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    idx.index = pd.DatetimeIndex(idx.index).tz_localize(None)
    nifty = idx["^NSEI"].dropna()
    market_ok = nifty > nifty.rolling(200).mean()
    curves = {"Hold all 200": _simulate(D, None), "Top 10": _simulate(D, 10), "Top 20": _simulate(D, 20),
              "Top 10 + market filter": _simulate(D, 10, market_ok), "Top 20 + market filter": _simulate(D, 20, market_ok)}
    start = curves["Top 20"].index[0]
    n200 = idx["^CNX200"].dropna().loc[start:]
    curves["NIFTY 200 index"] = n200 / n200.iloc[0]
    mid = pd.Timestamp("2018-06-30")
    out = {"at": datetime.now().isoformat(timespec="seconds"), "from": f"{start:%b %Y}", "to": f"{D['adj'].index[-1]:%b %Y}",
           "stats": {}, "curves": {}, "years": {}}
    for name, c in curves.items():
        out["stats"][name] = {**_stats(c), "first": _stats(c.loc[:mid])["cagr"], "second": _stats(c.loc[mid:])["cagr"]}
        m = c.groupby([c.index.year, c.index.month]).last()
        out["curves"][name] = {"x": [f"{y}-{mo:02d}-28" for y, mo in m.index], "y": [round(float(v), 4) for v in m]}
        yearly = (c.groupby(c.index.year).last().pct_change() * 100).dropna()
        out["years"][name] = {str(int(y)): round(float(v), 1) for y, v in yearly.items()}
    BT_FILE.parent.mkdir(exist_ok=True)
    BT_FILE.write_text(json.dumps(out))
    return out
