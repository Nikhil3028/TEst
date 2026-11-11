"""News and events for one instrument: recent headlines with a good / bad reading, and upcoming results dates.

Free sources, no key needed: Google News (RSS) for headlines, Yahoo Finance for the results calendar.

Old headlines can't be downloaded for free, so — unlike every strategy in this app — the news reading has NOT been
backtested. It is shown as context and as a caution on fresh signals; it never changes a tested signal by itself.
"""
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

import yfinance as yf

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
MAX_AGE_DAYS = 7
INDEX_QUERY = {"NIFTY 50": "Nifty 50", "BANK NIFTY": "Bank Nifty", "SENSEX": "Sensex",
               "NIFTY IT": "Nifty IT", "NIFTY FIN SERVICE": "Nifty Financial Services"}

# Words and phrases that move a headline's score. Phrases are matched first, so "profit falls" counts once, as bad.
GOOD = {
    "profit rises": 2, "profit jumps": 2, "profit surges": 2, "profit up": 2, "profit grows": 2, "beats estimates": 2,
    "beats expectations": 2, "record high": 2, "all-time high": 2, "52-week high": 2, "order win": 2, "wins order": 2,
    "bags order": 2, "target raised": 2, "raises target": 2, "upper circuit": 2, "strong results": 2, "debt free": 2,
    "upgrade": 2, "upgrades": 2, "upgraded": 2, "outperform": 1.5, "overweight": 1.5, "buyback": 1.5, "bonus issue": 1.5,
    "surge": 1.5, "surges": 1.5, "soars": 1.5, "rally": 1.5, "rallies": 1.5, "jumps": 1.5, "zooms": 1.5, "spikes": 1,
    "gains": 1, "gain": 1, "rises": 1, "climbs": 1, "advances": 1, "rebound": 1, "rebounds": 1, "recovers": 1,
    "bullish": 1.5, "breakout": 1, "upside": 1, "buy": 0.7, "accumulate": 1, "dividend": 0.7, "approval": 1,
    "approves": 0.7, "wins": 1, "bags": 1, "expansion": 0.7, "growth": 0.7, "strong": 0.7, "robust": 0.7, "beats": 1.5,
    "tops": 0.7, "record": 0.7, "partnership": 0.5, "acquires": 0.5, "launches": 0.3, "stake buy": 0.7,
}
BAD = {
    "profit falls": 2, "profit drops": 2, "profit declines": 2, "profit slumps": 2, "profit down": 2, "profit dips": 2,
    "net loss": 2, "misses estimates": 2, "misses expectations": 2, "52-week low": 2, "record low": 2, "lower circuit": 2,
    "target cut": 2, "cuts target": 2, "weak results": 2, "show cause": 2, "tax notice": 1.5, "gst notice": 1.5,
    "stake sale": 1, "block deal": 0.5, "pledged shares": 1.5, "pledge": 1,
    "downgrade": 2, "downgrades": 2, "downgraded": 2, "underperform": 1.5, "underweight": 1.5, "fraud": 2.5, "scam": 2.5,
    "default": 2, "defaults": 2, "insolvency": 2.5, "bankruptcy": 2.5, "raid": 2, "raids": 2, "probe": 1.5,
    "investigation": 1.5, "penalty": 1.5, "fine": 1, "fined": 1.5, "ban": 1.5, "banned": 1.5, "lawsuit": 1.5,
    "resigns": 1.5, "resignation": 1.5, "crash": 2, "crashes": 2, "plunge": 2, "plunges": 2, "tumbles": 1.5,
    "slumps": 1.5, "slump": 1.5, "tanks": 1.5, "sinks": 1.5, "slides": 1, "slips": 1, "falls": 1, "drops": 1,
    "declines": 1, "dips": 0.7, "sheds": 1, "loses": 1, "loss": 1, "losses": 1, "selloff": 1.5, "sell-off": 1.5,
    "bearish": 1.5, "breakdown": 1, "downside": 1, "sell": 0.7, "weak": 0.7, "miss": 1, "misses": 1.5, "cuts": 0.7,
    "warning": 1, "warns": 1, "concern": 0.7, "concerns": 0.7, "pressure": 0.7, "layoffs": 1, "recall": 1,
    "strike": 0.7, "shutdown": 1, "delay": 0.5, "delays": 0.5, "outage": 1,
}
NEGATORS = ("not ", "no ", "won't ", "unlikely to ", "fails to ", "denies ")
# pages that are price tickers / charts / generic lists, not news about the company
JUNK = re.compile(r"share price(?: today)?[,:]? (?:stock price|live|nse|bse)|stock price.*live|interactive stock chart|"
                  r"price target & |stock quote|historical prices|option chain|live updates?:? .*share price|"
                  r"share price live|share price today live|stock price, news|share price$|stock price$|"
                  r"top gainers & losers|outlook for the week", re.I)
_PATS = [(re.compile(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])"), w, sign)
         for table, sign in ((GOOD, 1), (BAD, -1)) for k, w in sorted(table.items(), key=lambda kv: -len(kv[0]))]


def score_headline(title: str) -> float:
    """-1 (clearly bad) … +1 (clearly good) for one headline; 0 when it says nothing either way."""
    t = " " + title.lower() + " "
    total = 0.0
    for pat, w, sign in _PATS:
        for m in pat.finditer(t):
            neg = any(t[max(0, m.start() - 14):m.start()].endswith(n) for n in NEGATORS)
            total += w * sign * (-1 if neg else 1)
        t = pat.sub(" · ", t)   # a matched phrase is used up, so its words aren't counted again
    return max(-1.0, min(1.0, total / 2))


FIN = re.compile(r"\b(stocks?|shares?|results|profit|revenue|earnings|q[1-4]|sensex|nifty|nse|bse|crore|rs\.?|brokerages?|"
                 r"investors?|dividend|target|market cap|ipo|order|stake)\b|₹", re.I)
GENERIC = {"state", "bank", "india", "indian", "tata", "adani", "bajaj", "hdfc", "icici", "power", "steel", "oil", "life",
           "general", "national", "united", "union", "central", "bharat", "hindustan", "idea", "info", "max", "page"}


def _query(symbol: str, name: str) -> tuple[str, object]:
    """Search text + a test saying whether a headline is really about this instrument."""
    if symbol in INDEX_QUERY:
        q = INDEX_QUERY[symbol]
        return f'"{q}"', lambda t: q.lower() in t.lower()
    full = re.sub(r"\s+", " ", re.sub(r"\b(limited|ltd)\b\.?|[.,]", " ", name or "", flags=re.I)).strip()
    if not full or full.upper() == symbol:
        full = ""
    first = full.split(" ")[0] if full else ""
    first_ok = len(first) > 4 and first.lower() not in GENERIC
    sym_pat = re.compile(r"(?<![\w&])" + re.escape(symbol) + r"(?![\w&])")   # the ticker in capitals, as a whole word
    first_pat = re.compile(r"\b" + re.escape(first) + r"\b", re.I) if first_ok else None

    def about(t: str) -> bool:
        if full and full.lower() in t.lower():
            return True
        if sym_pat.search(t) and (len(symbol) > 3 or FIN.search(t)):
            return symbol.lower() not in GENERIC or bool(FIN.search(t))
        return bool(first_pat and first_pat.search(t) and FIN.search(t))

    parts = ([f'"{full}"'] if full else []) + [f'"{symbol} share"', f'"{symbol} stock"'] + ([f'"{first} shares"'] if first_ok else [])
    return " OR ".join(parts), about


def headlines(symbol: str, name: str = "", limit: int = 12) -> list[dict]:
    """Recent headlines, newest first: {title, source, link, when (UTC), age_h, score}. [] when the feed can't be read."""
    q, about = _query(symbol.upper(), name)
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{q} when:{MAX_AGE_DAYS}d")
           + "&hl=en-IN&gl=IN&ceid=IN:en")
    try:
        xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8).read()
        items = ET.fromstring(xml).findall(".//item")
    except Exception:  # noqa: BLE001 — offline / blocked: the app works without news
        return []
    now = datetime.now(timezone.utc)
    out, seen = [], set()
    for it in items:
        src = (it.findtext("source") or "").strip()
        title = (it.findtext("title") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        key = re.sub(r"[^a-z0-9]+", "", title.lower())[:60]
        if not title or key in seen or JUNK.search(title) or not about(title):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:  # noqa: BLE001
            continue
        age_h = (now - when).total_seconds() / 3600
        if age_h > MAX_AGE_DAYS * 24 or age_h < -1:
            continue
        seen.add(key)
        out.append({"title": title, "source": src, "link": it.findtext("link") or "", "when": when,
                    "age_h": max(age_h, 0.0), "score": score_headline(title)})
    out.sort(key=lambda h: h["age_h"])
    return out[:limit]


def sentiment(items: list[dict]) -> dict:
    """One reading from the headlines: fresher ones count more (half as much every 2 days)."""
    scored = [h for h in items if h["score"]]
    if len(items) < 2:
        return {"label": "Quiet", "key": "muted", "score": 0.0, "pos": 0, "neg": 0, "n": len(items),
                "text": "Hardly any news this week."}
    w = [0.5 ** (h["age_h"] / 48) for h in items]
    s = sum(h["score"] * x for h, x in zip(items, w)) / sum(w)
    pos, neg = sum(h["score"] > 0 for h in scored), sum(h["score"] < 0 for h in scored)
    if s >= 0.15 and pos >= 2 and pos >= 2 * neg:
        label, key = "Positive", "up"
    elif s <= -0.15 and neg >= 2 and neg >= 2 * pos:
        label, key = "Negative", "down"
    elif pos + neg >= 3 and min(pos, neg) >= 1:
        label, key = "Mixed", "warn"
    else:
        label, key = "Neutral", "muted"
    return {"label": label, "key": key, "score": round(s, 2), "pos": int(pos), "neg": int(neg), "n": len(items),
            "text": f"{pos} good and {neg} bad of {len(items)} headlines this week."}


def events(ticker: str, today: date | None = None) -> dict:
    """Upcoming company dates from Yahoo: {'results': date, 'results_in': days, 'ex_dividend': date, ...}. {} for indices."""
    if ticker.startswith("^"):
        return {}
    today = today or date.today()
    try:
        cal = yf.Ticker(ticker).calendar or {}
    except Exception:  # noqa: BLE001 — Yahoo hiccup: no event info
        return {}
    out = {}
    ed = cal.get("Earnings Date") or []
    ed = [d for d in (ed if isinstance(ed, (list, tuple)) else [ed]) if isinstance(d, date) and d >= today]
    if ed:
        out["results"], out["results_in"] = min(ed), (min(ed) - today).days
    xd = cal.get("Ex-Dividend Date")
    if isinstance(xd, date) and xd >= today:
        out["ex_dividend"], out["ex_dividend_in"] = xd, (xd - today).days
    return out


ARCHIVE_LIMIT = 60       # headlines per symbol handed to the archive (the pages show the first 12)
RESULTS_SOON_DAYS = 5   # calendar days: a results day can gap the price past any stop-loss


def read(symbol: str, ticker: str, name: str = "") -> dict:
    """Everything the pages show: headlines, the sentiment reading, events and the cautions that follow from them."""
    more = headlines(symbol, name, limit=ARCHIVE_LIMIT)
    items = more[:12]
    ev = {} if symbol.upper() in INDEX_QUERY else events(ticker)
    sent = sentiment(items)
    cautions = []
    if "results_in" in ev and ev["results_in"] <= RESULTS_SOON_DAYS:
        n = ev["results_in"]
        when = "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days ({ev['results']:%d %b})"
        cautions.append(("results", f"Results are due {when}. The price can jump past a stop-loss on results day — "
                                    "many traders wait until after."))
    if sent["label"] == "Negative":
        cautions.append(("bad_news", f"This week's news is mostly negative ({sent['neg']} bad of {sent['n']} headlines). "
                                     "Read them before buying."))
    return {"items": items, "sentiment": sent, "events": ev, "cautions": cautions, "more": more}
