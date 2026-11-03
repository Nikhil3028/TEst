"""Live updates for the charts, so they change in place without reloading the page.

On this computer / your WiFi: a tiny HTTP server on its own port —  GET /bars?ticker=^NSEI&interval=15m  ->
{"bars": [...], "ltp": ..., "ts": ...}  and  /stream  (every tick pushed as it arrives).
Opened through a public address (Streamlit Community Cloud, a tunnel) that port can't be reached, so the same answer
plus the latest tick is written to static/feed/<name>.json every few seconds instead; Streamlit serves that file
itself (server.enableStaticServing) and the chart polls it through the app's own address."""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import data

IST_OFFSET = 19800  # same shift the chart uses so timestamps read as IST
_cache: dict = {}
_lock = threading.Lock()
LTP_OVERRIDE = None  # optional callable(ticker) -> float | None, e.g. a broker's real-time LTP
TICK_SOURCE = None   # optional callable(ticker) -> (price, arrival_time) | None, for the push stream
STATUS = None        # optional callable() -> dict, for /status diagnostics
TOKEN_TICKS = None   # optional callable(segment, token) -> (price, arrival_time) | None  (option contracts)
TOKEN_BARS = None    # optional callable(segment, token, interval) -> DataFrame of OHLCV candles


def latest_bars(ticker: str, interval: str, n: int = 30, max_age: float = 1.0) -> dict:
    key = (ticker, interval)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
    df = data.fetch(ticker, interval, "5d" if interval == "1d" else "1d")
    bars = [{"time": int(ts.timestamp()) + IST_OFFSET, "open": round(float(o), 2), "high": round(float(h), 2),
             "low": round(float(lo), 2), "close": round(float(c), 2), "volume": float(v)}
            for ts, o, h, lo, c, v in zip(df.index[-n:], df.Open[-n:], df.High[-n:], df.Low[-n:], df.Close[-n:], df.Volume[-n:])]
    if bars and LTP_OVERRIDE:
        try:
            px = LTP_OVERRIDE(ticker)
            if px:
                b = bars[-1]
                b["close"], b["high"], b["low"] = px, max(b["high"], px), min(b["low"], px)
        except Exception:  # noqa: BLE001 — fall back to the Yahoo price
            pass
    out = {"bars": bars, "ltp": bars[-1]["close"] if bars else None, "ts": time.time()}
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def token_bars(seg: str, token: str, interval: str, n: int = 30) -> dict:
    key = (seg, token, interval)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < 30:  # Angel's history API is rate-limited; live ticks fill the gaps
            return hit[1]
    try:
        df = TOKEN_BARS(seg, token, interval) if TOKEN_BARS else None
    except Exception:  # noqa: BLE001 — rate limited: serve the last good answer
        if hit:
            return hit[1]
        raise
    bars = [] if df is None or df.empty else [
        {"time": int(ts.timestamp()) + IST_OFFSET, "open": float(o), "high": float(h), "low": float(lo), "close": float(c), "volume": float(v)}
        for ts, o, h, lo, c, v in zip(df.index[-n:], df.Open[-n:], df.High[-n:], df.Low[-n:], df.Close[-n:], df.Volume[-n:])]
    out = {"bars": bars, "ltp": bars[-1]["close"] if bars else None, "ts": time.time()}
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def _tick_json(get) -> dict | None:
    try:
        t = get()
    except Exception:  # noqa: BLE001 — no tick source / not subscribed yet
        return None
    return {"ltp": t[0], "t": int(t[1]) + IST_OFFSET, "ts": t[1]} if t else None


# ---------------------------------------------------------------- file feed (public address / cloud)
FEED_DIR = Path(__file__).parent / "static" / "feed"
FEED_URL = "app/static/feed"      # where Streamlit serves FEED_DIR, relative to the app's own address
_jobs: dict[str, dict] = {}       # file name -> {produce, every, until, at}
_writer_on = False


def _write_loop():
    for old in FEED_DIR.glob("*.json"):   # files left by an earlier run would show stale prices for a moment
        if time.time() - old.stat().st_mtime > 600:
            old.unlink(missing_ok=True)
    while True:
        try:
            now = time.time()
            with _lock:
                for name in [n for n, j in _jobs.items() if now > j["until"]]:
                    del _jobs[name]   # nobody has shown this chart for a while
                due = [(n, j) for n, j in _jobs.items() if now - j["at"] >= j["every"]]
                for _, j in due:
                    j["at"] = now
            for name, j in due:
                try:
                    body = json.dumps(j["produce"]())
                except Exception:  # noqa: BLE001 — data hiccup: the chart keeps the last good file
                    continue
                tmp = FEED_DIR / f"{name}.json.tmp"
                tmp.write_text(body)
                tmp.replace(FEED_DIR / f"{name}.json")   # atomic: the browser never reads half a file
        except Exception:  # noqa: BLE001 — never let the writer die
            pass
        time.sleep(0.2)


def _publish(name: str, produce, every: float, ttl: float) -> str:
    global _writer_on
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    if not _writer_on:
        FEED_DIR.mkdir(parents=True, exist_ok=True)   # OSError -> the caller falls back to the feed port
    with _lock:
        old = _jobs.get(name)
        _jobs[name] = {"produce": produce, "every": every, "until": time.time() + ttl, "at": old["at"] if old else 0.0}
        start, _writer_on = not _writer_on, True
    if start:
        threading.Thread(target=_write_loop, daemon=True, name="feed-files").start()
    return f"{FEED_URL}/{name}.json"


def publish_ticker(ticker: str, interval: str, every: float, ttl: float = 150) -> str:
    """Keep a file with the latest candles + tick of `ticker` fresh every `every` s, for `ttl` s after the last call
    (the Chart page calls again on every refresh while it's open). Returns its address relative to the app."""
    def produce():
        out = dict(latest_bars(ticker, interval, max_age=5 if TICK_SOURCE else max(every - 0.5, 1)))
        out["tick"] = _tick_json(lambda: TICK_SOURCE(ticker)) if TICK_SOURCE else None
        return out
    return _publish(f"{ticker}_{interval}", produce, every, ttl)


def publish_token(seg: str, token: str, interval: str, every: float, ttl: float = 900) -> str:
    """The same for an option contract (Angel One)."""
    def produce():
        out = dict(token_bars(seg, token, interval))
        out["tick"] = _tick_json(lambda: TOKEN_TICKS(seg, token)) if TOKEN_TICKS else None
        return out
    return _publish(f"opt_{seg}_{token}_{interval}", produce, every, ttl)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/stream":
            if "token" in q and TOKEN_TICKS:
                seg, tok = q["seg"][0], q["token"][0]
                return self._stream(None, lambda: TOKEN_TICKS(seg, tok))
            return self._stream(q["ticker"][0])
        if u.path == "/status":
            body = json.dumps(STATUS() if STATUS else {}, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            if u.path != "/bars":
                raise ValueError("not found")
            if "token" in q:
                body, code = json.dumps(token_bars(q["seg"][0], q["token"][0], q.get("interval", ["5m"])[0])), 200
            else:
                body, code = json.dumps(latest_bars(q["ticker"][0], q.get("interval", ["15m"])[0])), 200
        except Exception as e:  # noqa: BLE001
            body, code = json.dumps({"error": str(e)}), 400
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())

    def _stream(self, ticker: str | None, source=None):
        """Server-Sent Events: push every new tick to the browser as soon as it arrives (~0.1 s)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        last_ts, idle = None, 0.0
        try:
            get = source or (lambda: TICK_SOURCE(ticker) if TICK_SOURCE else None)
            while True:
                t = get()
                if t and t[1] != last_ts:
                    last_ts = t[1]
                    msg = json.dumps({"ltp": t[0], "t": int(t[1]) + IST_OFFSET, "ts": t[1]})
                    self.wfile.write(f"data: {msg}\n\n".encode())
                    self.wfile.flush()
                    idle = 0.0
                elif idle > 15:  # keep-alive comment so proxies/browsers don't drop the connection
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    idle = 0.0
                time.sleep(0.05)
                idle += 0.05
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser tab closed or chart reloaded

    def log_message(self, *args):  # keep the terminal quiet
        pass


def start(port: int = 8765, host: str | None = None) -> int:
    """Start the server in a background thread; returns the port actually used."""
    for p in range(port, port + 20):
        try:
            # 0.0.0.0 so a phone on the same WiFi can reach it; set LIVEFEED_HOST=127.0.0.1 to keep it local-only
            srv = ThreadingHTTPServer((host or os.environ.get("LIVEFEED_HOST", "0.0.0.0"), p), _Handler)
        except OSError:
            continue
        srv.daemon_threads = True  # open push streams must not keep the app alive
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return p
    raise RuntimeError("no free port for the live feed")
