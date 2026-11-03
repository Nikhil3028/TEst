"""The app's brain: preferences, broker connections, market data, analysis, Auto strategy selection and the
signal for one instrument. Pages (views/*.py) only lay things out — everything they show comes from here,
so the Home cards and the Chart page always agree."""
import json
import re
import time
from dataclasses import asdict, astuple, dataclass, field, fields
from datetime import datetime
from html import escape
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

import angel
import data
import indicators
import journal
import livefeed
import options
import strategy

HERE = Path(__file__).parent
PROFILE_FILE = HERE / "profile.json"
AUTO = "Auto"
STEP_SECS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
TF_LABEL = {v[0]: k for k, v in data.INTERVALS.items()}
TF_SHORT = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1D"}
STYLE_INTERVALS = {"Swing": ["1d"], "Intraday": ["15m", "5m"]}
INDEX_ETF = {"NIFTY 50": "NIFTYBEES", "BANK NIFTY": "BANKBEES"}
SHORT_NAME = {"Swing · Trend with safety buffer": "Trend + buffer", "Swing · Golden cross": "Golden cross",
              "Swing · Momentum (6/12-month)": "Momentum", "Swing · Breakout + trend filter": "Breakout + filter",
              "Swing · Trend (200-day average)": "200-day trend", "Swing · Breakout (20-day high)": "20-day breakout",
              "Swing · Dip-buy in uptrend (RSI-2)": "Dip-buy", "Intraday · Opening-range breakout + daily trend": "Opening range",
              "Indicator score (EMA/RSI/MACD/Supertrend)": "Indicator score"}
DEFAULT_WATCHLIST = ["NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTYBEES", "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY",
                     "TCS", "SBIN", "BHARTIARTL", "ITC", "LT", "AXISBANK", "BAJFINANCE"]
WATCHLIST_PRESETS = {
    "Index options": ["NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTY FIN SERVICE"],
    "Index ETFs": ["NIFTYBEES", "BANKBEES", "JUNIORBEES"],
    "Large-cap stocks": ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "BHARTIARTL", "ITC", "LT", "AXISBANK"],
}


# ---------------------------------------------------------------- preferences (profile.json)
@dataclass
class Prefs:
    name: str = ""
    capital: float = 100_000
    risk_pct: float = 1.0
    style: str = "Swing"            # Swing | Intraday
    mode: str = "simple"            # simple | pro
    watchlist: list = field(default_factory=lambda: list(DEFAULT_WATCHLIST))
    refresh: int = 10               # seconds between live refreshes while the market is open
    live: bool = True
    closed_only: bool = True        # decide signals on completed candles only
    cost_intraday: float = 0.03     # % per side
    cost_delivery: float = 0.10
    fast: int = 9
    slow: int = 21
    trend: int = 50
    st_p: int = 10
    st_m: float = 3.0
    onboarded: bool = False

    @property
    def ind(self) -> tuple:
        return (self.fast, self.slow, self.trend, self.st_p, self.st_m)

    @property
    def pro(self) -> bool:
        return self.mode == "pro"


def _load_prefs() -> Prefs:
    raw = {}
    try:
        raw = json.loads(PROFILE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        wl = journal.load_watchlist()   # migrate the old watchlist file
        if wl != journal.DEFAULT_WATCHLIST:
            raw["watchlist"] = wl
    known = {f.name for f in fields(Prefs)}
    return Prefs(**{k: v for k, v in raw.items() if k in known})


def prefs() -> Prefs:
    if "prefs" not in st.session_state:
        st.session_state["prefs"] = _load_prefs()
    return st.session_state["prefs"]


def save_prefs(p: Prefs):
    st.session_state["prefs"] = p
    tmp = PROFILE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(p), indent=2))
    tmp.replace(PROFILE_FILE)


def update_prefs(**kw):
    p = prefs()
    for k, v in kw.items():
        setattr(p, k, v)
    save_prefs(p)


# ---------------------------------------------------------------- broker connections
def _secrets(section: str, keys: tuple) -> dict:
    try:
        cfg = dict(st.secrets.get(section, {}))
        if not cfg and all(k in st.secrets for k in keys[:2]):
            cfg = {k: st.secrets[k] for k in keys if k in st.secrets}
        return cfg
    except Exception:  # noqa: BLE001 — no secrets file
        return {}


@st.cache_resource(ttl=8 * 3600, show_spinner="Connecting to Angel One…")
def _angel(cfg_items: tuple):
    return angel.connect(dict(cfg_items))


@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def _groww(cfg_items: tuple):
    return options.connect_groww(dict(cfg_items))


FEED_BASE = __import__("os").environ.get("FEED_BASE", "")   # e.g. "/feed" when a reverse proxy serves the live feed


@st.cache_resource
def feed_port() -> int:
    return livefeed.start()


_BROKERS: list = [0.0, None]   # (time, namespace) — reused for a few seconds; the connections themselves are cached


def brokers() -> SimpleNamespace:
    """Angel One / Groww API connections (made once, shared by all pages) + their errors."""
    if _BROKERS[1] is not None and time.time() - _BROKERS[0] < 5:
        return _BROKERS[1]
    b = SimpleNamespace(angel=None, angel_err=None, groww=None, groww_err=None)
    if (cfg := _secrets("angelone", ("api_key", "totp_secret", "client_id", "mpin"))):
        try:
            b.angel = _angel(tuple(sorted(cfg.items())))
        except Exception as e:  # noqa: BLE001
            b.angel_err = str(e)
    cfg = _secrets("groww", ("totp_token", "totp_secret"))
    if cfg and ("totp_token" in cfg or "api_key" in cfg or "access_token" in cfg):
        try:
            b.groww = _groww(tuple(sorted(cfg.items())))
        except Exception as e:  # noqa: BLE001
            b.groww_err = str(e)
    a = b.angel
    livefeed.LTP_OVERRIDE = (lambda tk: live_ltp(tk)) if (a or b.groww) else None
    livefeed.TICK_SOURCE = a.tick if a else None
    livefeed.TOKEN_TICKS = a.tick_token if a else None
    livefeed.TOKEN_BARS = a.candles if a else None
    livefeed.STATUS = (lambda: {"connected": a.connected, "subscribed": len(a.subscribed), "error": a.last_error}) if a else None
    _BROKERS[:] = [time.time(), b]
    return b


def ANGEL():
    return brokers().angel


def live_ltp(tk: str) -> float | None:
    """Real-time price from a connected broker (Angel One tick stream first, then Groww)."""
    b = brokers()
    if b.angel and (px := b.angel.ltp(tk)):
        return px
    if b.groww:
        return options.groww_ltp(b.groww, tk)
    return None


# ---------------------------------------------------------------- market data
def market() -> tuple[bool, str]:
    return data.market_status()


def candle_key(interval: str, closed_only: bool = True) -> str:
    """Changes only when a new candle can exist, so data is downloaded once per candle instead of every refresh."""
    now = datetime.now(data.IST)
    if not market()[0]:
        return f"closed-{now:%Y-%m-%d-%H}"
    if interval == "1d":
        return f"{now:%Y-%m-%d}" + ("" if closed_only else f"-{now.hour}-{now.minute // 5}")
    lag = 3 if ANGEL() else 20  # give the source a moment to publish the candle that just closed
    secs = (now - now.replace(hour=9, minute=15, second=0, microsecond=0)).total_seconds() - lag
    return f"{now:%Y-%m-%d}-{int(secs // STEP_SECS[interval])}"


@st.cache_data(ttl=6 * 3600, max_entries=160, show_spinner=False)
def _load(ticker, interval, period, key, broker, start_download=True):
    """Candles for one chart. With Angel One connected, intraday charts use up to 2 years of Angel history
    (downloaded once in the background); until that's ready, and otherwise, Yahoo Finance."""
    a = ANGEL() if broker else None
    if a and interval in STEP_SECS:
        tok = angel.spot_token(ticker)
        if tok:
            try:
                h = a.history(tok[0], tok[1], interval, start_download=start_download)
                if h is not None and len(h) > 200:
                    h = h.copy()
                    h.attrs["source"] = "Angel One"
                    return h
            except Exception:  # noqa: BLE001 — fall back to Yahoo
                pass
    df = data.fetch(ticker, interval, period)
    df.attrs["source"] = "Yahoo Finance"
    return df


def period_for(interval: str) -> str:
    return data.INTERVALS[TF_LABEL[interval]][1]


def load(ticker, interval, closed_only=True, start_download=True):
    return _load(ticker, interval, period_for(interval), candle_key(interval, closed_only), bool(ANGEL()), start_download)


def prefetch(tickers: list[str], interval: str, P: "Prefs", start_download: bool = True):
    """Download several charts' candles at once (it's network time, so 8 in parallel), filling the normal cache —
    the Home page uses this so its first check of the day doesn't wait for one download after another."""
    from concurrent.futures import ThreadPoolExecutor
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()

    def one(tk):
        import threading
        add_script_run_ctx(threading.current_thread(), ctx)   # lets the threads use the page's cache
        try:
            load(tk, interval, P.closed_only, start_download)
            if interval != "1d":
                load_daily(tk)
        except Exception:  # noqa: BLE001 — that symbol will show its own error later
            pass

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, tickers))


def history_status(ticker, interval) -> str | None:
    """Text for the UI while long history is still downloading."""
    a = ANGEL()
    if not a or interval not in STEP_SECS:
        return None
    tok = angel.spot_token(ticker)
    job = a.hist_jobs.get((tok[0], tok[1], interval)) if tok else None
    return job if job and not job.startswith("done") else None


@st.cache_data(ttl=3600, show_spinner=False)
def load_daily(ticker):
    return data.fetch(ticker, "1d", "2y")


def quote(ticker):
    """(last price, % change vs previous close) or None — live ticks from Angel One when connected."""
    a = ANGEL()
    if a and market()[0] and (q := a.quote(ticker)):
        return q
    return _yahoo_quote(ticker)


@st.cache_data(ttl=20, show_spinner=False)
def _yahoo_quote(ticker):
    d = data.fetch(ticker, "1d", "5d")
    if len(d) < 2:
        return None
    return float(d.Close.iloc[-1]), float((d.Close.iloc[-1] / d.Close.iloc[-2] - 1) * 100)


def drop_live_candle(df, interval, closed_only=True):
    if closed_only and len(df) and not data.is_candle_complete(df.index[-1], interval):
        return df.iloc[:-1], df.iloc[-1]
    return df, None


def prepare(df, daily, use_vwap, interval, ind):
    fast, slow, trend, st_p, st_m = ind
    df = indicators.add_all(df, fast, slow, trend, st_p, st_m)
    df = indicators.add_context(df, daily if interval != "1d" else None)
    df["Score"] = strategy.score(df, use_vwap)
    warm = 200 if interval == "1d" and len(df) > 500 else max(trend, 30)
    return df.iloc[warm:] if len(df) > warm + 60 else df


@st.cache_resource
def _analysis_store() -> dict:
    """Process-wide cache (survives reruns): same chart + settings + candle -> same analysis."""
    return {}


def analyse(ticker, interval, strat, params, P: Prefs, start_download=True):
    """Load data, compute indicators and run the strategy; None if there is no data. Cached per candle."""
    store = _analysis_store()
    key = (ticker, interval, strat.name, astuple(params), P.ind, P.closed_only,
           candle_key(interval, P.closed_only), bool(ANGEL()), start_download)
    if key in store:
        return store[key]
    raw = load(ticker, interval, P.closed_only, start_download)
    out = None
    if not raw.empty:
        daily = load_daily(ticker) if interval != "1d" else None
        sig_raw, live = drop_live_candle(raw, interval, P.closed_only)
        uv = interval != "1d" and not ticker.startswith("^")  # indices have no volume
        df = prepare(sig_raw, daily, uv, interval, P.ind)
        sig = strat.signals(df, params)
        out = (df, live, raw, strategy.run(df, params, sig), sig, uv, daily)
    if len(store) > 96:
        store.pop(next(iter(store)))
    store[key] = out
    return out


def signal_of(r) -> str:
    return r.pending or ("HOLD " + r.open_trade.side if r.open_trade else "WAIT")


# ---------------------------------------------------------------- Auto: pick the best strategy for this chart
STOPS = [dict(sl_atr=0, trail_supertrend=False), dict(sl_atr=3.0, trail_supertrend=False), dict(sl_atr=0, trail_supertrend=True)]
SIGNAL_KEYS = ("buy_score", "ma_len", "band", "exit_band", "fast_len", "slow_len", "lookback", "entry_len", "exit_len",
               "trend_filter")   # settings that change the entry/exit signals (the rest are stops)


def param_grid(s):
    """Settings Auto tries for one strategy (small on purpose: more choices = more chance of a lucky pick)."""
    if s.signals is strategy.trend_buffer_signals:
        sym = [dict(ma_len=n, band=b, exit_band=b, **st_) for n in (100, 150, 200) for b in (0.0, 0.01, 0.02, 0.03) for st_ in STOPS]
        deep = [dict(ma_len=n, band=0.0, exit_band=x, sl_atr=0, trail_supertrend=False)
                for n in (100, 150, 200) for x in (0.05, 0.08, 0.10, 0.15)]
        return sym + deep
    if s.signals is strategy.golden_cross_signals:
        return [dict(fast_len=f, slow_len=sl_, **st_) for f, sl_ in ((50, 200), (20, 100), (50, 150)) for st_ in STOPS]
    if s.signals is strategy.momentum_signals:
        return [dict(lookback=n, **st_) for n in (126, 252) for st_ in STOPS]
    if s.signals is strategy.breakout_filter_signals:
        return [dict(entry_len=e, exit_len=x, trend_filter=f, **st_) for e in (20, 55) for x in (10, 20) for f in (False, True)
                for st_ in STOPS]
    if s.signals is strategy.orb_trend_signals:
        return [dict(sl_atr=a, target_atr=b, trail_supertrend=c, buy_score=4)
                for a in (1.0, 1.5, 2.0) for b in (0, 2, 3) for c in (False, True)]
    if s.signals is strategy.score_signals:
        return [dict(sl_atr=a, target_atr=b, trail_supertrend=c, buy_score=d)
                for a in (1.0, 1.5, 2.0) for b in (0, 3) for c in (False, True) for d in (3, 4, 5)]
    return [dict(sl_atr=a, target_atr=0, trail_supertrend=c, buy_score=4) for a in (0, 2.0, 3.0) for c in (False, True)]


FOLDS = (0.5, 0.65, 0.8, 1.0)  # walk-forward: choose on [0, a), test on [a, b) for each consecutive pair
LIB_VERSION = 2   # bump when strategies or grids change, so Auto's daily disk cache is rebuilt


def _summary(pnls: list[float]) -> dict:
    """Net % P&L per trade -> compounded return, profit factor, win rate."""
    if not pnls:
        return {"trades": 0, "ret": 0.0, "pf": 0.0, "win": 0.0}
    a = np.array(pnls)
    wins, losses = a[a > 0], a[a <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() else (float("inf") if len(wins) else 0.0)
    return {"trades": len(a), "ret": round((np.prod(1 + a / 100) - 1) * 100, 2), "pf": round(float(pf), 2),
            "win": round(len(wins) / len(a) * 100, 1)}


@st.cache_data(show_spinner=False, persist="disk")
def auto_pick(ticker, interval, style, cost_pct, ind, closed_only, day_key, source, version=LIB_VERSION):
    """Walk-forward selection. Every strategy × stop/target/trail setting is backtested once over the whole
    history (the engine is causal, so any prefix of that run equals a run that stopped there). Then for each
    of 3 periods the most profitable setting *on data before the period* is chosen and scored *on the period*.
    Those 3 unseen results decide pass/fail; the live setting is the best one over all history.
    Cached on disk per day (`day_key`) and data source."""
    raw = load(ticker, interval, closed_only)
    if raw.empty:
        return None
    daily = load_daily(ticker) if interval != "1d" else None
    sig_raw, _ = drop_live_candle(raw, interval, closed_only)
    df = prepare(sig_raw, daily, interval != "1d" and not ticker.startswith("^"), interval, ind)
    if len(df) < 200:
        return None
    intra = interval != "1d"
    min_train, min_oos = (10, 10) if intra else (8, 8)
    combos, sig_cache = [], {}
    for s in strategy.STRATEGIES.values():
        if interval not in s.intervals or (style == "Swing") != (interval == "1d"):
            continue
        for g in param_grid(s):
            p = strategy.Params(**g, allow_short=intra, intraday=intra and s.style == "Intraday", cost_pct=cost_pct)
            sk = (s.name,) + tuple(g.get(k) for k in SIGNAL_KEYS)
            if sk not in sig_cache:
                sig_cache[sk] = s.signals(df, p)
            r = strategy.run(df, p, sig_cache[sk])
            trades = [(t.entry_time, t.exit_time, t.pnl_pct - 2 * cost_pct) for t in r.trades]
            combos.append({"strategy": s.name, **g, "trades": trades})
    if not combos:
        return None

    def eligible(sm):
        return sm["trades"] >= min_train and sm["ret"] > 0 and sm["pf"] >= 1.2

    cuts = [df.index[int(len(df) * f)] for f in FOLDS[:-1]] + [df.index[-1]]
    folds, oos_pnls = [], []
    for k in range(len(cuts) - 1):
        a, b, is_last = cuts[k], cuts[k + 1], k == len(cuts) - 2
        scored = [(sm["ret"], i) for i, c in enumerate(combos)
                  if eligible(sm := _summary([x[2] for x in c["trades"] if x[1] < a]))]
        if not scored:
            folds.append({"from": a, "to": b, "strategy": None, **_summary([])})
            continue
        best = combos[max(scored)[1]]
        test = [x[2] for x in best["trades"] if a <= x[0] and (is_last or x[0] < b)]
        oos_pnls += test
        folds.append({"from": a, "to": b, "strategy": best["strategy"], **_summary(test)})

    full = [(_summary([x[2] for x in c["trades"]]), c) for c in combos]
    ok = [(sm, c) for sm, c in full if eligible(sm)]
    sm, best = max(ok or full, key=lambda x: x[0]["ret"])
    oos = _summary(oos_pnls)
    traded = [f for f in folds if f["trades"]]
    passed = (bool(ok) and oos["trades"] >= min_oos and oos["ret"] > 0 and oos["pf"] >= 1.1
              and sum(f["ret"] > 0 for f in traded) >= 2)
    span_days = (df.index[-1] - df.index[0]).days
    top = sorted(ok or full, key=lambda x: -x[0]["ret"])[:8]
    table = pd.DataFrame([{"strategy": c["strategy"], "settings": setting_text(c),
                           "trades": s_["trades"], "return %": s_["ret"], "profit factor": s_["pf"], "win %": s_["win"]}
                          for s_, c in top])
    return {"strategy": best["strategy"],
            "params": {k: v for k, v in best.items() if k not in ("strategy", "trades")},
            "train": {**sm, "from": df.index[0], "to": df.index[-1]},
            "test": {**oos, "from": cuts[0], "to": df.index[-1]},
            "folds": folds, "passed": passed, "any_ok": bool(ok), "tested": len(combos), "table": table,
            "low_conf": span_days < 180, "recent_neg": bool(folds and folds[-1]["strategy"] and folds[-1]["ret"] < 0),
            "bars": len(df), "span": (df.index[0], df.index[-1])}


def setting_text(g: dict, strategy_name: str | None = None) -> str:
    """Short human description of one Auto setting, e.g. '150-day avg, sell 8% below'."""
    parts = []
    if "ma_len" in g:
        parts.append(f"{g['ma_len']}-day avg" + (f" ±{g['band']:.0%}" if g.get("band") and g.get("band") == g.get("exit_band")
                                                  else f", sell {g['exit_band']:.0%} below" if g.get("exit_band") else ""))
    if "fast_len" in g:
        parts.append(f"{g['fast_len']}/{g['slow_len']}-day averages")
    if "lookback" in g:
        parts.append(f"{round(g['lookback'] / 21)}-month momentum")
    if "entry_len" in g:
        parts.append(f"{g['entry_len']}-day high / {g['exit_len']}-day low" + (", above 200-day avg" if g.get("trend_filter") else ""))
    if "buy_score" in g and (strategy_name or g.get("strategy", "")).startswith("Indicator score"):
        parts.append(f"score ≥ {g['buy_score']}")
    if g.get("sl_atr"):
        parts.append(f"stop {g['sl_atr']:g}×ATR")
    if g.get("target_atr"):
        parts.append(f"target {g['target_atr']:g}×ATR")
    if g.get("trail_supertrend"):
        parts.append("trailing stop")
    return ", ".join(parts) or "default"


# ---------------------------------------------------------------- instruments & search
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def universe() -> pd.DataFrame:
    """Everything the search box offers: indices first, then all NSE stocks / ETFs with names."""
    rows = [{"symbol": k, "name": {"NIFTY 50": "Nifty 50 index", "BANK NIFTY": "Nifty Bank index", "SENSEX": "BSE Sensex",
                                   "NIFTY IT": "Nifty IT index", "NIFTY FIN SERVICE": "Nifty Financial Services"}.get(k, k),
             "kind": "Index"} for k in data.INDICES]
    try:
        s = options.stocks()
        rows += [{"symbol": r.trading_symbol, "name": r.name, "kind": "Stock"} for r in s.itertuples()]
    except Exception:  # noqa: BLE001 — offline: fall back to the popular list
        rows += [{"symbol": x, "name": x, "kind": "Stock"} for x in data.POPULAR]
    u = pd.DataFrame(rows).drop_duplicates("symbol")
    u["label"] = np.where(u.name.str.upper() == u.symbol, u.symbol, u.symbol + " · " + u.name)
    return u.reset_index(drop=True)


def name_of(symbol: str) -> str:
    u = universe()
    hit = u[u.symbol == symbol.upper()]
    return hit.name.iloc[0] if len(hit) else symbol.upper()


# ---------------------------------------------------------------- selection (what the Chart / Options pages show)
@dataclass
class Sel:
    symbol: str = "NIFTY 50"
    exchange: str = "NSE"
    interval: str = "1d"
    strategy: str = AUTO
    sl_atr: float | None = None       # manual-strategy overrides (Pro mode)
    target_atr: float | None = None
    trail: bool | None = None
    buy_score: int = 4
    allow_short: bool | None = None


def selection() -> Sel:
    if "sel" not in st.session_state:
        P = prefs()
        st.session_state["sel"] = Sel(interval=STYLE_INTERVALS[P.style][0])
    return st.session_state["sel"]


def select(symbol: str, **kw):
    s = selection()
    s.symbol = symbol.upper()
    for k, v in kw.items():
        setattr(s, k, v)


# ---------------------------------------------------------------- one instrument, fully analysed
def build(sel: Sel, P: Prefs, start_download: bool = True) -> SimpleNamespace | None:
    """Everything the pages need about one instrument: data, strategy (Auto or manual), backtest, live price."""
    is_open, status = market()
    interval = sel.interval
    intraday_tf = interval != "1d"
    tf_label = TF_LABEL[interval]
    ticker = data.to_yahoo(sel.symbol, sel.exchange)
    cost = P.cost_intraday if intraday_tf else P.cost_delivery
    auto_mode = sel.strategy == AUTO
    AUTO_INFO = None
    if auto_mode:
        style = "Intraday" if intraday_tf else "Swing"
        src = load(ticker, interval, P.closed_only, start_download).attrs.get("source")
        AUTO_INFO = auto_pick(ticker, interval, style, cost, P.ind, P.closed_only,
                              datetime.now(data.IST).strftime("%Y-%m-%d"), src, LIB_VERSION)
        name = AUTO_INFO["strategy"] if AUTO_INFO else ("Intraday · Opening-range breakout + daily trend" if intraday_tf
                                                         else "Swing · Trend (200-day average)")
        strat = strategy.STRATEGIES[name]
        ap = dict(AUTO_INFO["params"]) if AUTO_INFO else {"sl_atr": strat.sl_atr, "target_atr": strat.target_atr,
                                                           "trail_supertrend": strat.trail, **strat.defaults}
        sl_atr, target_atr = ap.get("sl_atr", 0), ap.get("target_atr", 0)
        trail, buy_score = ap.get("trail_supertrend", False), ap.get("buy_score", 4)
        extra = {k: v for k, v in ap.items() if k in SIGNAL_KEYS and k != "buy_score"}
        allow_short = intraday_tf
    else:
        strat = strategy.STRATEGIES[sel.strategy]
        sl_atr = strat.sl_atr if sel.sl_atr is None else sel.sl_atr
        target_atr = strat.target_atr if sel.target_atr is None else sel.target_atr
        trail = strat.trail if sel.trail is None else sel.trail
        buy_score = sel.buy_score
        allow_short = (strat.style == "Intraday" and strat.signals is not strategy.score_signals) \
            if sel.allow_short is None else sel.allow_short
        extra = dict(strat.defaults)
    params = strategy.Params(buy_score=buy_score, sl_atr=sl_atr, target_atr=target_atr, trail_supertrend=trail,
                             allow_short=allow_short and intraday_tf, intraday=(strat.style == "Intraday" and intraday_tf),
                             cost_pct=cost, **extra)
    out = analyse(ticker, interval, strat, params, P, start_download)
    if out is None:
        return None
    df, live_bar, raw, res, sig, use_vwap, daily = out
    last = df.iloc[-1]
    ltp = float(raw["Close"].iloc[-1])
    if is_open:
        try:
            px = live_ltp(ticker) if (ANGEL() or brokers().groww) else livefeed.latest_bars(ticker, interval).get("ltp")
            ltp = float(px or ltp)
        except Exception:  # noqa: BLE001 — keep the candle close
            pass
    today = raw.index.date == raw.index[-1].date()
    prev = raw["Close"][~today]
    prev_close = float(prev.iloc[-1]) if len(prev) else float(raw["Open"].iloc[0])
    store = _analysis_store()
    rk = ("rel", id(res))
    if rk not in store:   # reliability = 3 more backtests: once per analysis, not once per refresh
        store[rk] = (strategy.reliability(res, df, cost, params, sig), strategy.stats(res, df, cost))
    (grade, grade_key, halves), bt = store[rk]
    if AUTO_INFO:  # in Auto mode the honest grade is the walk-forward check
        grade, grade_key = (("Passed the unseen-data check", "good") if AUTO_INFO["passed"] else
                            ("No strategy passed on this chart", "bad"))
    # daily trend: as of yesterday's close on intraday charts (what the ORB filter uses), latest close on daily
    dsrc = daily if daily is not None else raw
    dctx = pd.DataFrame({"c": dsrc.Close, "e20": indicators.ema(dsrc.Close, 20), "s50": dsrc.Close.rolling(50).mean()})
    if daily is not None:
        dctx = dctx[dctx.index.date < raw.index[-1].date()]
    dl = dctx.iloc[-1]
    daily_trend = "UP" if dl.c > dl.e20 > dl.s50 else "DOWN" if dl.c < dl.e20 < dl.s50 else "SIDEWAYS"
    return SimpleNamespace(
        symbol=sel.symbol.upper(), exchange=sel.exchange, ticker=ticker, interval=interval, tf_label=tf_label,
        intraday_tf=intraday_tf, is_open=is_open, status=status, auto_mode=auto_mode, AUTO_INFO=AUTO_INFO,
        strat=strat, strat_name=strat.name, is_score=strat.signals is strategy.score_signals, params=params,
        sl_atr=sl_atr, target_atr=target_atr, trail=trail, buy_score=buy_score, allow_short=allow_short, cost=cost,
        swing_days=21 if strat.style == "Swing" or not intraday_tf else 1,
        df=df, live_bar=live_bar, raw=raw, res=res, sig=sig, use_vwap=use_vwap, daily=daily, last=last, ltp=ltp,
        today=today, prev_close=prev_close, chg=ltp - prev_close, chg_pct=(ltp / prev_close - 1) * 100,
        grade=grade, grade_key=grade_key, halves=halves, bt=bt, daily_trend=daily_trend,
        alert_key=f"{ticker}-{interval}-{strat.name}", capital=P.capital, risk_pct=P.risk_pct,
        source=raw.attrs.get("source", "Yahoo Finance"))


# ---------------------------------------------------------------- the signal, in plain words
def qty_for(c, entry, stop) -> int:
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return 0
    return int(min(c.capital * c.risk_pct / 100 / risk_per_share, c.capital / entry))


def wait_info(c) -> tuple[str, str | None, float | None]:
    """Why there's no trade, plus the price level that would trigger one."""
    last, strat, params = c.last, c.strat, c.params
    if params.intraday and last.name.time() >= strategy.NO_ENTRY_AFTER:
        return "No new intraday trades after 3:00 PM. Plan for tomorrow.", None, None
    if strat.signals is strategy.orb_trend_signals:
        if c.daily_trend == "SIDEWAYS":
            return ("The daily trend is sideways — this strategy only trades with a clear daily trend. "
                    "No trade today is a valid decision."), None, None
        if not last.Morning:
            return "Breakouts are only taken before 12:00 noon. Wait for tomorrow's opening range.", None, None
        if c.daily_trend == "UP":
            return "Daily trend is UP — waiting for a candle to close above the opening-range high.", "Buy above", float(last.ORH)
        return "Daily trend is DOWN — waiting for a candle to close below the opening-range low.", "Short below", float(last.ORL)
    if strat.levels is not None:
        lv = {k: float(v.iloc[-1]) for k, v in strat.levels(c.df, params).items()}
        if strat.signals is strategy.trend_buffer_signals:
            ma = lv[f"{params.ma_len}-day average"]
            buy = lv.get("Buy level", ma)
            if c.ltp > buy:
                return (f"The price is above its {params.ma_len}-day average — the signal turns BUY when today's candle closes "
                        "above it."), "Buy above", buy
            return (f"The price is below its {params.ma_len}-day average. Buy when it closes back above it."), "Buy above", buy
        if strat.signals is strategy.golden_cross_signals:
            return (f"The {params.fast_len}-day average is below the {params.slow_len}-day — no uptrend yet. This turns BUY "
                    "by itself when it crosses above."), None, None
        if strat.signals is strategy.momentum_signals:
            ref = lv[f"Price {round(params.lookback / 21)} months ago"]
            return (f"The price is lower than {round(params.lookback / 21)} months ago. Buy when it closes above that level."), \
                "Buy above", ref
        if strat.signals is strategy.breakout_filter_signals:
            if params.trend_filter and last.Close < last.SMA200:
                return "Below the 200-day average — breakouts only count in an uptrend.", "Uptrend above", float(last.SMA200)
            return f"Waiting for a close at a new {params.entry_len}-day high.", "Buy above", lv[f"{params.entry_len}-day high"]
    if strat.signals is strategy.trend200_signals:
        return "The price is below its 200-day average. Stay out until it closes above it.", "Buy above", float(last.SMA200)
    if strat.signals is strategy.donchian_signals:
        return "Waiting for a close at a new 20-day high.", "Buy above", float(last.DC_hi20)
    if strat.signals is strategy.rsi2_signals:
        if last.Close < last.SMA200:
            return "Below the 200-day average — no dip-buys in a downtrend.", "Uptrend above", float(last.SMA200)
        return f"In an uptrend; waiting for a sharp dip (RSI-2 is {last.RSI2:.0f}, needs below 10).", None, None
    need = max(c.buy_score - int(last.Score), 0)
    if need == 0 and last.RSI >= params.rsi_overbought:
        return (f"Indicators are bullish, but the price is overbought (RSI {last.RSI:.0f}) — "
                "waiting for a pullback before buying."), None, None
    return f"Not enough confirmations yet ({need} more needed for a BUY).", None, None


def key_levels(c, exclude=None) -> list[tuple]:
    """(label, value, sub, colour) for the price levels the strategy is watching."""
    last, strat = c.last, c.strat
    lv = []
    if strat.levels is not None:
        lv = [(k, float(v.iloc[-1])) for k, v in strat.levels(c.df, c.params).items()]
    elif strat.signals is strategy.orb_trend_signals:
        lv = [("Opening-range high", last.ORH), ("Opening-range low", last.ORL)]
    elif strat.signals is strategy.trend200_signals:
        lv = [("200-day average", last.SMA200)]
    elif strat.signals is strategy.donchian_signals:
        lv = [("20-day high", last.DC_hi20), ("10-day low", last.DC_lo10)]
    elif strat.signals is strategy.rsi2_signals:
        lv = [("200-day average", last.SMA200), ("5-day average", last.SMA5)]
    out = [(n, f"₹{v:,.2f}", f"{(v / c.ltp - 1) * 100:+.2f}% from here", None)
           for n, v in lv if pd.notna(v) and (exclude is None or abs(v - exclude) > 1e-9)]
    if c.is_score:
        out.append(("Indicator score", f"{int(last.Score):+d}", f"needs {c.buy_score} to buy", None))
    elif strat.signals is strategy.rsi2_signals:
        out.append(("RSI-2", f"{last.RSI2:.0f}", "buy zone below 10", None))
    return out


def exit_text(c) -> str:
    """The exit rule of the strategy in use, with its actual numbers."""
    s, p = c.strat, c.params
    if s.levels is not None:
        lv = {k: float(v.iloc[-1]) for k, v in s.levels(c.df, p).items()}
        if s.signals is strategy.trend_buffer_signals:
            lvl = lv.get("Exit level", lv[f"{p.ma_len}-day average"])
            return (f"sell when a day closes below ₹{lvl:,.2f}" + (f" ({p.exit_band:.0%} under the {p.ma_len}-day average)"
                                                                    if p.exit_band else f" (the {p.ma_len}-day average)"))
        if s.signals is strategy.golden_cross_signals:
            return f"sell when the {p.fast_len}-day average falls below the {p.slow_len}-day average"
        if s.signals is strategy.momentum_signals:
            return f"sell when the price closes below its level {round(p.lookback / 21)} months ago (now ₹{lv[next(iter(lv))]:,.2f})"
        if s.signals is strategy.breakout_filter_signals:
            return f"sell when a day closes below ₹{lv[f'{p.exit_len}-day low']:,.2f} (the {p.exit_len}-day low)"
    return s.exit_rule[0].lower() + s.exit_rule[1:].rstrip(".")


def option_hint(c, kind: str) -> str | None:
    """Groww-style name of the option to buy for this signal (CE for BUY, PE for SHORT)."""
    try:
        und = options.underlying_for(c.symbol, c.ticker)
        if not und:
            return None
        exps = options.expiries(*und)
        e = exps[options.default_expiry(exps, c.swing_days)]
        ks = options.strikes(*und, e)
        k = float(ks[abs(ks - c.ltp).argmin()])
        return options.display_name(und[0], e, k, kind)
    except Exception:  # noqa: BLE001 — the hint is optional
        return None


def confidence(c) -> tuple[str, str, str]:
    """(level, colour key, reason) — how much to trust signals on this chart."""
    a = c.AUTO_INFO
    if a:
        te = a["test"]
        if not a["any_ok"]:
            return "Not proven", "down", "No setting made money on this chart's history."
        if not a["passed"]:
            return "Not proven", "down", f"Failed the test on 3 periods it never saw ({te['ret']:+.1f}%)."
        if a["low_conf"]:
            return "Low", "warn", "Passed, but tested on under 6 months of data."
        if a["recent_neg"]:
            return "Medium", "warn", f"Made {te['ret']:+.1f}% on {te['trades']} unseen trades, but the latest period lost money."
        return "High", "up", f"Made {te['ret']:+.1f}% on {te['trades']} trades it was never tuned on."
    return {"good": ("Medium", "up", c.grade), "warn": ("Low", "warn", c.grade)}.get(
        c.grade_key, ("Not proven", "down", c.grade))


def signal(c) -> dict:
    """The decision for one instrument, ready to show: verdict, colour, plan numbers, steps, one-line headline."""
    last, res, ltp = c.last, c.res, c.ltp
    atr_v = float(last.ATR)
    t = res.open_trade
    sym = escape(c.symbol)
    exit_rule = escape(exit_text(c))
    index = c.ticker.startswith("^")
    out = dict(kind="WAIT", verdict="WAIT", color="muted", msg="", steps=[], plan=[], headline="", can_paper=False,
               side=None, stop=None, target=None, qty=0, entry=None, option=None, trigger=None)
    if res.pending in ("BUY", "SELL"):
        d = 1 if res.pending == "BUY" else -1
        stop = ltp - d * (c.sl_atr or 2.0) * atr_v
        target = ltp + d * c.target_atr * atr_v if c.target_atr else None
        q = qty_for(c, ltp, stop)
        opt = option_hint(c, "CE" if d == 1 else "PE")
        steps = []
        if d == 1 and index:
            etf = INDEX_ETF.get(c.symbol)
            steps.append(f"{sym} itself can't be bought — <b>BUY the option {escape(opt or '')}</b> (see 🎯 Options)"
                         + (f" or the ETF <b>{etf}</b>" if etf else "") + ".")
        elif d == 1:
            steps.append(f"<b>BUY {sym}</b> now at about <b>₹{ltp:,.2f}</b> — <b>{q:,} qty</b>"
                         + (f", or the option <b>{escape(opt)}</b> (see 🎯 Options)" if opt else "") + ".")
        elif index:
            steps.append(f"<b>BUY the put option {escape(opt or '')}</b> — it gains when {sym} falls (see 🎯 Options). "
                         "An index can't be shorted directly.")
        else:
            steps.append((f"<b>BUY {escape(opt)}</b> (a put — gains when {sym} falls), or " if opt else "")
                         + f"<b>SHORT {sym}</b> (sell first, intraday only) at about ₹{ltp:,.2f} — {q:,} qty.")
        if index:
            steps.append(f"Exit level: if {sym} reaches <b>₹{stop:,.2f}</b>, get out. Put the stop-loss on the option's "
                         "premium — the exact price is on the 🎯 Options page.")
        else:
            steps.append(f"Straight after, place a <b>stop-loss order at ₹{stop:,.2f}</b>. That caps your loss at about "
                         f"<b>₹{q * abs(ltp - stop):,.0f}</b>.")
        steps.append(f"<b>SELL to book profit at ₹{target:,.2f}</b> (place it as a target order)." if target else
                     f"No fixed target — let the profit run. <b>SELL when this signal says SELL</b> ({exit_rule}).")
        if c.trail:
            steps.append("As the price moves your way, <b>raise your stop-loss</b> to the new level shown here (trailing stop).")
        if c.params.intraday:
            steps.append("Intraday: <b>SELL everything by 3:15 PM</b>, even if neither stop nor target was hit.")
        out.update(kind="BUY" if d == 1 else "SHORT", verdict="BUY" if d == 1 else "SHORT", color="up" if d == 1 else "down",
                   msg="Fresh signal on the last completed candle.", steps=steps, side="LONG" if d == 1 else "SHORT",
                   stop=stop, target=target, qty=q, entry=ltp, option=opt,
                   headline=(f"Buy ~₹{ltp:,.2f} · stop ₹{stop:,.2f}" if d == 1 else f"Falling — buy PUT / short · stop ₹{stop:,.2f}"),
                   plan=[("Entry ≈", f"₹{ltp:,.2f}", "", None),
                         ("Stop-loss" if c.sl_atr else "Emergency stop", f"₹{stop:,.2f}", f"{abs(ltp - stop) / ltp * 100:.2f}% away", "down"),
                         ("Target", f"₹{target:,.2f}" if target else "Let it run", f"{abs(target - ltp) / ltp * 100:.2f}% away" if target else "until SELL", "up"),
                         ("Quantity", f"{q:,}", f"≈ ₹{q * ltp:,.0f}", None),
                         ("Max loss", f"₹{q * abs(ltp - stop):,.0f}", f"{c.risk_pct:g}% of capital", None)],
                   can_paper=c.grade_key != "bad" and q > 0)
        if c.grade_key == "bad":
            out.update(kind="SKIP", verdict="SKIP", color="muted", plan=[], can_paper=False,
                       msg=f"A {res.pending} signal fired, but <b>this strategy has not made money on this chart</b> — skipping is safer.",
                       steps=["<b>Don't trade this one.</b> Signals on this chart haven't been reliable.",
                              "Check another stock — the Home page shows which ones pass the test."],
                       headline="Signal fired, but not reliable here")
    elif res.pending == "EXIT" and t:
        pnl = (ltp / t.entry - 1) * 100 * (1 if t.side == "LONG" else -1)
        out.update(kind="SELL", verdict="SELL (exit)" if t.side == "LONG" else "BUY BACK", color="warn",
                   msg=f"Exit signal for the {t.side.lower()} taken at ₹{t.entry:,.2f} on {t.entry_time:%d %b %H:%M}.",
                   steps=[(f"<b>SELL your {sym}</b> (or the call option you bought) now" if t.side == "LONG" else
                           f"<b>Buy back your short {sym}</b> (or SELL the put option you bought) now")
                          + f" — the exit rule triggered. Result ≈ <b>{pnl:+.2f}%</b>.",
                          "Then cancel your stop-loss / target orders so they don't fire later.",
                          "Wait for the next BUY before entering again."],
                   headline=f"Exit now · {pnl:+.1f}% on this trade",
                   plan=[("Entry", f"₹{t.entry:,.2f}", "", None), ("Now", f"₹{ltp:,.2f}", "", None),
                         ("Result", f"{pnl:+.2f}%", "", "up" if pnl > 0 else "down")])
    elif t:
        pnl = (ltp / t.entry - 1) * 100 * (1 if t.side == "LONG" else -1)
        steps = [f"Bought at about ₹{t.entry:,.2f}? <b>Keep holding — don't sell yet</b> ({pnl:+.2f}% so far)."]
        has_stop, has_tgt = abs(t.stop) < 1e12, abs(t.target) < 1e12
        if has_stop:
            steps.append(f"Keep your stop-loss at <b>₹{t.stop:,.2f}</b>" + (" — raise it to this level if yours is lower." if c.trail else "."))
        steps.append(f"<b>SELL at ₹{t.target:,.2f}</b> (target), or when this signal turns SELL." if has_tgt
                     else f"<b>SELL when this signal turns SELL</b> ({exit_rule}).")
        if c.params.intraday:
            steps.append("Intraday: SELL by 3:15 PM at the latest.")
        steps.append("Didn't buy? <b>Don't chase it now</b> — wait for the next fresh BUY.")
        plan = [("Entry", f"₹{t.entry:,.2f}", f"{t.entry_time:%d %b}", None),
                ("Result so far", f"{pnl:+.2f}%", "", "up" if pnl > 0 else "down")]
        if has_stop:
            plan.append(("Stop-loss", f"₹{t.stop:,.2f}", "", "down"))
        if has_tgt:
            plan.append(("Target", f"₹{t.target:,.2f}", "", "up"))
        out.update(kind="HOLD", verdict="HOLD" if t.side == "LONG" else "HOLD SHORT", color="up" if t.side == "LONG" else "down",
                   msg=f"The strategy has been in this {t.side.lower()} since {t.entry_time:%d %b %H:%M}.", steps=steps, plan=plan,
                   stop=t.stop if has_stop else None,
                   headline=f"Holding since {t.entry_time:%d %b} · {pnl:+.1f}%" + (f" · stop ₹{t.stop:,.0f}" if has_stop else ""))
    else:
        msg, trig_label, trig = wait_info(c)
        steps = ["<b>Do nothing now</b> — there is no trade setup."]
        has_trig = trig is not None and pd.notna(trig)
        if has_trig:
            steps.append(f"{escape(trig_label)} <b>₹{trig:,.2f}</b> is the level to watch — this signal turns "
                         f"{'SHORT' if 'Short' in trig_label else 'BUY'} by itself (with a beep) when it triggers.")
        steps.append("Already holding something from an earlier signal? Keep following its stop-loss.")
        plan = [("Price now", f"₹{ltp:,.2f}", "", None)]
        if has_trig:
            plan.append((trig_label, f"₹{trig:,.2f}", f"{(trig / ltp - 1) * 100:+.2f}% from here", "accent"))
        plan += key_levels(c, exclude=trig)
        out.update(msg=msg, steps=steps, plan=plan, trigger=(trig_label, trig) if has_trig else None,
                   headline=(f"{trig_label} ₹{trig:,.2f} ({(trig / ltp - 1) * 100:+.1f}%)" if has_trig
                             else re.sub(r"\s*—.*", "", msg)[:70]))
    if out["kind"] == "HOLD" and c.grade_key == "bad":
        # you'd never have entered: the BUY was shown as SKIP — so don't tell anyone to "hold" an untrusted position
        out.update(kind="SKIP", verdict="SKIP", color="muted", plan=[], stop=None,
                   msg="This strategy is in a trade here, but it <b>hasn't made money on this chart</b> — so there's no reliable signal.",
                   steps=["<b>No trade.</b> Signals on this chart haven't been reliable.",
                          "Check another stock — the Home page shows which ones pass the test."],
                   headline="No reliable signal on this stock")
    if c.params.intraday and not c.is_open and out["kind"] in ("WAIT", "SKIP"):
        out["headline"] = "Market closed — checked again from 9:15 AM"
    out["note"] = re.sub(r"<[^>]+>", "", out["steps"][0]) if out["steps"] else ""
    out["confidence"] = confidence(c)
    return out


def candle_countdown(c) -> str:
    """When the current candle closes — signals are only decided on completed candles."""
    if not c.is_open:
        return ""
    now = datetime.now(data.IST)
    if c.interval == "1d":
        return "Daily signals are decided at the 3:30 PM close."
    step = STEP_SECS[c.interval]
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    nxt = start + pd.Timedelta(seconds=(int((now - start).total_seconds() // step) + 1) * step)
    left = int((nxt - now).total_seconds())
    return f"This {TF_SHORT[c.interval]} candle closes at <b>{nxt:%H:%M}</b> (in {left // 60}m {left % 60:02d}s) — the signal is re-checked then."


def trade_price(t: dict) -> float | None:
    """Latest price for a journal entry: options via Angel ticks (ticker 'OPT:seg:token'), others via quote()."""
    tk = t["ticker"]
    if tk.startswith("OPT:"):
        a = ANGEL()
        if not a:
            return None
        _, seg, tok = tk.split(":")
        tick = a.tick_token(seg, tok)
        return tick[0] if tick else None
    q = quote(tk)
    return q[0] if q else None


def market_mood() -> dict:
    """NIFTY's daily trend, India VIX and today's move — for the Home page."""
    out = {}
    d = load_daily("^NSEI")
    if len(d) > 60:
        e20, s50 = indicators.ema(d.Close, 20).iloc[-1], d.Close.rolling(50).mean().iloc[-1]
        cl = d.Close.iloc[-1]
        out["trend"] = "UP" if cl > e20 > s50 else "DOWN" if cl < e20 < s50 else "SIDEWAYS"
        out["vs200"] = (cl / d.Close.rolling(200).mean().iloc[-1] - 1) * 100 if len(d) > 200 else None
    if (q := quote("^NSEI")):
        out["nifty"] = q
    if (v := quote("^INDIAVIX")):
        lvl = v[0]
        out["vix"] = (lvl, "Calm" if lvl < 13 else "Normal" if lvl < 18 else "Nervous" if lvl < 24 else "Fearful")
    return out


def greeting() -> str:
    h = datetime.now(data.IST).hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def market_clock() -> str:
    """'Market open · closes in 2h 05m' / 'Market closed · opens Mon 9:15 AM'."""
    now = datetime.now(data.IST)
    is_open, status = market()
    if is_open:
        close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        m = int((close - now).total_seconds() // 60)
        return f"Market open · closes in {m // 60}h {m % 60:02d}m"
    nxt = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if now >= nxt:
        nxt += pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += pd.Timedelta(days=1)
    when = "today" if nxt.date() == now.date() else ("tomorrow" if (nxt.date() - now.date()).days == 1 else f"{nxt:%a}")
    return f"{status} · opens {when} 9:15 AM"
