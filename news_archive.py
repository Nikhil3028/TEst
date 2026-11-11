"""Keeps every headline the app sees, so that one day news can be tested like the price strategies are.

Old headlines can't be downloaded for free — but they can be collected. Each time the app fetches news for a symbol
(at most every 30 minutes) the headlines are added to `news_archive/YYYY-MM.json`, one file per month of publication.
Google News answers with the last 7 days, so opening the app about once a week is enough to miss nothing.

Each record keeps when the headline was published AND when this app first saw it (`seen`): a future backtest must only
use a headline from `seen` onwards, otherwise it would be trading on news before it was known.

Saved on this computer only (not on Streamlit Community Cloud, whose disk is wiped on restarts).
To collect without opening the app, run it on a schedule:   .venv/bin/python news_archive.py
"""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone

import store

DIR = store.HERE / "news_archive"
_lock = threading.Lock()


def enabled() -> bool:
    return not store.ON_CLOUD


def _id(symbol: str, title: str) -> str:
    return hashlib.sha1(f"{symbol}|{re.sub(r'[^a-z0-9]+', '', title.lower())}".encode()).hexdigest()[:16]


def _read(path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def save(symbol: str, items: list[dict]) -> int:
    """Add headlines (as returned by news.headlines) to the archive; ones already saved are left untouched.
    Returns how many were new. A month file that exists but can't be read raises, rather than being overwritten."""
    if not items or not enabled():
        return 0
    seen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_month: dict[str, dict] = {}
    for h in items:
        rec = {"s": symbol, "t": h["title"], "src": h["source"], "pub": h["when"].astimezone(timezone.utc).isoformat(timespec="seconds"),
               "seen": seen, "sc": round(float(h["score"]), 2)}
        by_month.setdefault(f"{h['when'].astimezone(timezone.utc):%Y-%m}", {})[_id(symbol, h["title"])] = rec
    added = 0
    with _lock:
        DIR.mkdir(exist_ok=True)
        for month, recs in by_month.items():
            path = DIR / f"{month}.json"
            have = _read(path)
            new = {k: v for k, v in recs.items() if k not in have}
            if new:
                have.update(new)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(have, ensure_ascii=False, separators=(",", ":")))
                tmp.replace(path)
                added += len(new)
    return added


def load():
    """The whole archive as a DataFrame: symbol, title, source, published, seen (both UTC), score. For future testing."""
    import pandas as pd
    rows = [r for p in sorted(DIR.glob("*.json")) for r in _read(p).values()] if DIR.exists() else []
    df = pd.DataFrame(rows, columns=["s", "t", "src", "pub", "seen", "sc"]).rename(
        columns={"s": "symbol", "t": "title", "src": "source", "pub": "published", "sc": "score"})
    for c in ("published", "seen"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df.sort_values("published").reset_index(drop=True)


def stats() -> dict:
    """{'count', 'symbols', 'since' (date of the first collection), 'days' (days with at least one collection)}."""
    df = load()
    if df.empty:
        return {"count": 0, "symbols": 0, "since": None, "days": 0}
    return {"count": len(df), "symbols": df.symbol.nunique(), "since": df.seen.min().date(),
            "days": df.seen.dt.date.nunique()}


if __name__ == "__main__":   # scheduled collection for the watchlist, without opening the app
    import logging
    logging.disable(logging.CRITICAL)
    import core
    import data
    import news
    wl = (store.read("profile.json", None) or {}).get("watchlist") or core.DEFAULT_WATCHLIST
    total = 0
    for sym in wl:
        n = save(sym.upper(), news.headlines(sym.upper(), core.name_of(sym), limit=news.ARCHIVE_LIMIT))
        total += n
        print(f"{sym:<20} +{n}")
    s = stats()
    print(f"{total} new · {s['count']:,} headlines saved for {s['symbols']} symbols since {s['since']}")
