"""Angel One SmartAPI connection (market data only): TOTP login, a WebSocket tick stream for live prices,
and option-chain snapshots (LTP, OI, volume, Greeks).  No orders are ever placed from here."""
import json
import threading
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from datetime import time as dtime

from data import IST, market_status

SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
SCRIP_CACHE = Path(__file__).parent / ".cache" / "angel_scrip.json"
# Yahoo ticker -> (Angel exchange segment, token) for the indices
INDEX_TOKENS = {"^NSEI": ("NSE", "99926000"), "^NSEBANK": ("NSE", "99926009"), "NIFTY_FIN_SERVICE.NS": ("NSE", "99926037"),
                "^BSESN": ("BSE", "99919000"), "^INDIAVIX": ("NSE", "99926017"), "^CNXIT": ("NSE", "99926008")}
HIST_DIR = Path(__file__).parent / ".cache" / "candles"
HIST_DAYS = {"1m": 30, "5m": 365, "15m": 730, "1h": 730}     # how much intraday history to keep per symbol
HIST_CHUNK = {"1m": 29, "5m": 95, "15m": 190, "1h": 380}     # Angel's max days per candle request
WS_EXCH = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4}  # SmartWebSocketV2 exchangeType codes


# ---------------------------------------------------------------- instrument master
_master: pd.DataFrame | None = None
_opts: dict[tuple[str, str], pd.DataFrame] = {}   # (underlying, expiry) -> option contracts
_eq: dict[str, str] = {}                           # NSE equity symbol -> token
_master_lock = threading.Lock()


def master() -> pd.DataFrame:
    """Angel's instrument list (token, symbol, name, expiry, strike, lot, segment), cached on disk for 12 h
    and indexed in memory for fast lookups."""
    global _master, _opts, _eq
    if _master is not None:
        return _master
    with _master_lock:
        if _master is not None:
            return _master
        if not SCRIP_CACHE.exists() or time.time() - SCRIP_CACHE.stat().st_mtime > 12 * 3600:
            SCRIP_CACHE.parent.mkdir(exist_ok=True)
            with urllib.request.urlopen(SCRIP_URL, timeout=60) as r:
                SCRIP_CACHE.write_bytes(r.read())
        df = pd.DataFrame(json.loads(SCRIP_CACHE.read_text()))
        df["strike"] = pd.to_numeric(df.strike, errors="coerce") / 100
        df["lotsize"] = pd.to_numeric(df.lotsize, errors="coerce")
        df["expiry_date"] = pd.to_datetime(df.expiry, format="%d%b%Y", errors="coerce").dt.strftime("%Y-%m-%d")
        df["kind"] = np.where(df.symbol.str.endswith("CE"), "CE", np.where(df.symbol.str.endswith("PE"), "PE", ""))
        o = df[df.instrumenttype.isin(["OPTIDX", "OPTSTK"])]
        _opts = {k: g.reset_index(drop=True) for k, g in o.groupby(["name", "expiry_date"])}
        eq = df[(df.exch_seg == "NSE") & df.symbol.str.endswith("-EQ")]
        _eq = dict(zip(eq.symbol.str[:-3], eq.token.astype(str)))
        _master = df
        return df


def options_of(underlying: str, expiry: str) -> pd.DataFrame:
    master()
    return _opts.get((underlying, expiry), pd.DataFrame(columns=["token", "symbol", "strike", "kind", "exch_seg", "lotsize"]))


def spot_token(yahoo_ticker: str) -> tuple[str, str] | None:
    if yahoo_ticker in INDEX_TOKENS:
        return INDEX_TOKENS[yahoo_ticker]
    if yahoo_ticker.endswith(".NS"):
        master()
        tok = _eq.get(yahoo_ticker[:-3])
        if tok:
            return "NSE", tok
    return None


def option_rows(underlying: str, expiry: str, spot: float, n_strikes: int = 12) -> pd.DataFrame:
    """CE+PE contracts of one expiry, the n strikes either side of spot."""
    o = options_of(underlying, expiry)
    ks = np.sort(o.strike.unique())
    if not len(ks):
        return o
    i = int(np.abs(ks - spot).argmin())
    keep = ks[max(i - n_strikes, 0): i + n_strikes + 1]
    return o[o.strike.isin(keep)]


class _Limiter:
    """Spaces out calls to one Angel endpoint (its history API refuses bursts)."""
    def __init__(self, gap: float):
        self.gap, self.t, self.lock = gap, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            dt = self.t + self.gap - time.time()
            if dt > 0:
                time.sleep(dt)
            self.t = time.time()


def _frame(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close", "Volume"])
    df.index = pd.to_datetime(df.pop("t")).dt.tz_convert(IST)
    return df.astype(float)


# ---------------------------------------------------------------- session + tick stream
class AngelFeed:
    def __init__(self, api_key: str, client_id: str, mpin: str, totp_secret: str):
        import pyotp
        from SmartApi import SmartConnect
        self.api_key, self.client_id = api_key, client_id
        self.api = SmartConnect(api_key=api_key)
        sess = self.api.generateSession(client_id, mpin, pyotp.TOTP(totp_secret).now())
        if not sess or not sess.get("status"):
            raise RuntimeError((sess or {}).get("message") or "Angel One login failed")
        self.jwt = sess["data"]["jwtToken"]
        self.feed_token = self.api.getfeedToken()
        self.ticks: dict[str, dict] = {}       # token -> latest tick
        self.subscribed: set[tuple[str, str]] = set()
        self.connected = False
        self.last_error = ""
        self._lock = threading.Lock()
        self._greeks: dict = {}
        self._hist_lim, self._quote_lim = _Limiter(2.6), _Limiter(1.05)
        self._hist: dict[tuple, pd.DataFrame] = {}     # (seg, token, interval) -> candles
        self.hist_jobs: dict[tuple, str] = {}          # background downloads: key -> status text
        self._topped: dict[tuple, float] = {}          # last top-up time per key
        self._interactive = 0                          # interactive history requests waiting (they go first)
        self._start_ws()

    # -- websocket
    def _start_ws(self):
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        ws = SmartWebSocketV2(self.jwt, self.api_key, self.client_id, self.feed_token, max_retry_attempt=5)

        def on_open(_):
            self.connected = True
            if self.subscribed:
                self._send(list(self.subscribed))

        def on_data(_, msg):
            tok = str(msg.get("token", ""))
            tick = {"ltp": msg.get("last_traded_price", 0) / 100, "ts": time.time()}
            if "open_interest" in msg:
                tick["oi"] = msg["open_interest"]
            if "volume_trade_for_the_day" in msg:
                tick["volume"] = msg["volume_trade_for_the_day"]
            if msg.get("closed_price"):
                tick["close"] = msg["closed_price"] / 100   # previous day's close
            with self._lock:
                self.ticks.setdefault(tok, {}).update(tick)

        def on_error(*a):
            self.last_error = str(a[-1]) if a else "websocket error"

        def on_close(*_):
            self.connected = False

        ws.on_open, ws.on_data, ws.on_error, ws.on_close = on_open, on_data, on_error, on_close
        self.ws = ws
        threading.Thread(target=ws.connect, daemon=True).start()

    def _send(self, pairs):
        by_ex: dict[int, list] = {}
        for seg, tok in pairs:
            by_ex.setdefault(WS_EXCH[seg], []).append(tok)
        lst = [{"exchangeType": ex, "tokens": toks} for ex, toks in by_ex.items()]
        try:
            self.ws.subscribe("tsignals", 3, lst)   # 3 = SNAP_QUOTE: LTP + volume + OI
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)

    def subscribe(self, pairs):
        new = [p for p in pairs if p not in self.subscribed]
        if new:
            self.subscribed.update(new)
            if self.connected:
                self._send(new)

    def tick(self, yahoo_ticker: str) -> tuple[float, float] | None:
        """(last price, arrival time) of the latest tick, subscribing on first use."""
        st = spot_token(yahoo_ticker)
        if not st:
            return None
        self.subscribe([st])
        t = self.ticks.get(st[1])
        return (t["ltp"], t["ts"]) if t and t.get("ltp", 0) > 0 else None

    def quote(self, yahoo_ticker: str) -> tuple[float, float] | None:
        """(last price, % change vs previous close) from the tick stream."""
        st = spot_token(yahoo_ticker)
        if not st:
            return None
        self.subscribe([st])
        t = self.ticks.get(st[1]) or {}
        if t.get("ltp", 0) > 0 and t.get("close"):
            return t["ltp"], (t["ltp"] / t["close"] - 1) * 100
        return None

    def ltp(self, yahoo_ticker: str, max_age: float = 15) -> float | None:
        st = spot_token(yahoo_ticker)
        if not st:
            return None
        self.subscribe([st])
        t = self.ticks.get(st[1])
        return t["ltp"] if t and time.time() - t["ts"] < max_age and t["ltp"] > 0 else None

    def tick_token(self, seg: str, token: str) -> tuple[float, float] | None:
        self.subscribe([(seg, token)])
        t = self.ticks.get(token)
        return (t["ltp"], t["ts"]) if t and t.get("ltp", 0) > 0 else None

    def _candle_call(self, seg: str, token: str, interval: str, frm: datetime, to: datetime, retries: int = 3,
                     background: bool = False) -> list:
        """One history request, paced by the shared limiter and retried if Angel says we're too fast.
        Interactive callers use retries=1 so the page never waits long; background downloads are patient."""
        params = {"exchange": seg, "symboltoken": token, "interval": CANDLE_INTERVAL[interval][0],
                  "fromdate": frm.strftime("%Y-%m-%d %H:%M"), "todate": to.strftime("%Y-%m-%d %H:%M")}
        for attempt in range(retries + 1):
            if background:      # let interactive requests go first
                while self._interactive > 0:
                    time.sleep(0.2)
            else:
                self._interactive += 1
            try:
                self._hist_lim.wait()
            finally:
                if not background:
                    self._interactive -= 1
            try:
                r = self.api.getCandleData(dict(params))
            except Exception as e:  # noqa: BLE001 — SDK raises on Angel's plain-text rate-limit reply
                if "exceeding" in str(e) and attempt < retries:
                    time.sleep(1.5 if retries <= 1 else 3 * (attempt + 1))
                    continue
                raise
            if r and not r.get("status", True) and "exceed" in str(r.get("message", "")).lower() and attempt < retries:
                time.sleep(1.5 if retries <= 1 else 3 * (attempt + 1))
                continue
            if r and not r.get("status", True):
                self.last_error = f"candles: {r.get('message')}"
            return (r or {}).get("data") or []
        return []

    def candles(self, seg: str, token: str, interval: str) -> pd.DataFrame:
        """Recent OHLCV candles for any instrument (used for option premium charts)."""
        now = datetime.now(IST)
        return _frame(self._candle_call(seg, token, interval, now - pd.Timedelta(days=CANDLE_INTERVAL[interval][1]), now,
                                        retries=1))

    # -- long intraday history (disk-cached, so backtests can use years instead of Yahoo's 60 days)
    def history(self, seg: str, token: str, interval: str, start_download: bool = True) -> pd.DataFrame | None:
        """Up to HIST_DAYS of candles. The first call starts a background download and returns None;
        later calls return the cached candles topped up with anything new. With start_download=False
        (e.g. the scanner) it only uses history already on disk."""
        key = (seg, token, interval)
        path = HIST_DIR / f"{seg}_{token}_{interval}.pkl"
        df = self._hist.get(key)
        if df is None and path.exists():
            df = pd.read_pickle(path)
        if df is None:
            if start_download and key not in self.hist_jobs:
                self.hist_jobs[key] = "queued"
                threading.Thread(target=self._download, args=(key, path), daemon=True).start()
            return None
        step = pd.Timedelta(CANDLE_INTERVAL_SECS[interval], "s")
        now = datetime.now(IST)
        if len(df) and self._needs_topup(key, df.index[-1], step, now):  # re-fetch the last two candles onwards
            self._topped[key] = time.time()
            try:
                new = _frame(self._candle_call(seg, token, interval, df.index[-1] - 2 * step, now, retries=1))
                if len(new):
                    df = pd.concat([df[df.index < new.index[0]], new])
                    df.to_pickle(path)
            except Exception as e:  # noqa: BLE001 — keep serving what we have
                self.last_error = f"history top-up: {e}"
        self._hist[key] = df
        return df

    def _needs_topup(self, key, last_bar, step, now) -> bool:
        """A new candle can exist only after the last one's end, and only during or after a session we haven't seen."""
        if now - last_bar <= step or time.time() - self._topped.get(key, 0) < min(step.total_seconds(), 120):
            return False
        is_open, _ = market_status(now)
        session_done = last_bar.date() == now.date() and last_bar.time() >= dtime(15, 15)
        weekend_gap = now.weekday() >= 5 and (now.date() - last_bar.date()).days <= 2 and last_bar.weekday() == 4
        return is_open or not (session_done or weekend_gap or now.time() < dtime(9, 15) and
                               (now.date() - last_bar.date()).days <= 1)

    def _download(self, key, path):
        seg, token, interval = key
        try:
            now = datetime.now(IST)
            start = now - pd.Timedelta(days=HIST_DAYS[interval])
            chunks, to, n = [], now, 0
            total = -(-HIST_DAYS[interval] // HIST_CHUNK[interval])
            while to > start:
                frm = max(start, to - pd.Timedelta(days=HIST_CHUNK[interval]))
                n += 1
                self.hist_jobs[key] = f"downloading {n}/{total}"
                chunks.append(_frame(self._candle_call(seg, token, interval, frm, to, background=True)))
                to = frm
            df = pd.concat([c for c in chunks if len(c)]).sort_index()
            df = df[~df.index.duplicated(keep="last")]
            HIST_DIR.mkdir(parents=True, exist_ok=True)
            df.to_pickle(path)
            self._hist[key] = df
            self.hist_jobs[key] = f"done ({len(df):,} candles)"
        except Exception as e:  # noqa: BLE001
            self.hist_jobs[key] = f"failed: {e}"

    # -- option chain
    def _snapshot(self, rows: pd.DataFrame) -> dict:
        """REST snapshot (LTP, OI, volume) for up to 50 tokens per request — fills gaps before ticks arrive."""
        out = {}
        for seg in rows.exch_seg.unique():
            toks = rows[rows.exch_seg == seg].token.astype(str).tolist()
            for i in range(0, len(toks), 50):
                self._quote_lim.wait()
                r = self.api.getMarketData("FULL", {seg: toks[i:i + 50]})
                for f in ((r or {}).get("data") or {}).get("fetched", []):
                    out[str(f.get("symbolToken"))] = {"ltp": f.get("ltp"), "oi": f.get("opnInterest"),
                                                      "volume": f.get("tradeVolume"), "ts": time.time()}
        return out

    def greeks(self, underlying: str, expiry: str) -> dict:
        key = (underlying, expiry)
        hit = self._greeks.get(key)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        out = {}
        try:
            self._quote_lim.wait()
            r = self.api.optionGreek({"name": underlying, "expirydate": date.fromisoformat(expiry).strftime("%d%b%Y").upper()})
            for g in (r or {}).get("data") or []:
                k = (float(g.get("strikePrice", 0)), g.get("optionType"))
                out[k] = {"delta": float(g.get("delta", "nan")), "iv": float(g.get("impliedVolatility", "nan"))}
        except Exception as e:  # noqa: BLE001 — greeks are optional
            self.last_error = f"greeks: {e}"
        self._greeks[key] = (time.time(), out)
        return out

    def chain_table(self, underlying: str, expiry: str, spot: float) -> pd.DataFrame:
        rows = option_rows(underlying, expiry, spot)
        if rows.empty:
            return pd.DataFrame()
        self.subscribe([(s, str(t)) for s, t in zip(rows.exch_seg, rows.token)])
        with self._lock:
            ticks = {t: dict(v) for t, v in self.ticks.items()}
        missing = rows[[str(t) not in ticks or "oi" not in ticks[str(t)] for t in rows.token]]
        if len(missing):
            snap = self._snapshot(missing)
            with self._lock:
                for t, v in snap.items():
                    self.ticks.setdefault(t, {}).update({k: x for k, x in v.items() if x is not None})
                ticks = {t: dict(v) for t, v in self.ticks.items()}
        g = self.greeks(underlying, expiry)
        recs = {}
        for _, r in rows.iterrows():
            tk = ticks.get(str(r.token), {})
            p = r.kind.lower()
            rec = recs.setdefault(r.strike, {"strike": r.strike})
            rec.update({f"{p}_ltp": tk.get("ltp"), f"{p}_oi": tk.get("oi"), f"{p}_volume": tk.get("volume"),
                        f"{p}_delta": g.get((r.strike, r.kind), {}).get("delta"), f"{p}_iv": g.get((r.strike, r.kind), {}).get("iv")})
        return pd.DataFrame(sorted(recs.values(), key=lambda x: x["strike"]))


def option_token(underlying: str, expiry: str, strike: float, kind: str) -> tuple[str, str, str] | None:
    """(segment, token, symbol) of one option contract."""
    o = options_of(underlying, expiry)
    hit = o[(o.kind == kind) & np.isclose(o.strike, strike)]
    if not len(hit):
        return None
    r = hit.iloc[0]
    return r.exch_seg, str(r.token), r.symbol


CANDLE_INTERVAL = {"1m": ("ONE_MINUTE", 5), "5m": ("FIVE_MINUTE", 20), "15m": ("FIFTEEN_MINUTE", 45),
                   "1h": ("ONE_HOUR", 90), "1d": ("ONE_DAY", 365)}   # interval -> (Angel name, days of recent candles)
CANDLE_INTERVAL_SECS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


def connect(cfg: dict) -> AngelFeed | None:
    need = ("api_key", "client_id", "mpin", "totp_secret")
    if not cfg or not all(cfg.get(k) for k in need):
        return None
    return AngelFeed(*(str(cfg[k]).strip() for k in need))


def as_of() -> str:
    return datetime.now(IST).strftime("%d %b %H:%M:%S")
