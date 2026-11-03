"""Signal scoring, trade simulation (backtest) and the live recommendation.

The same state machine drives the chart markers, the backtest and the "what to do now"
card, so what you see on past candles is exactly how the live signal is generated.
"""
from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd


@dataclass
class Params:
    buy_score: int = 4          # score needed to enter (max 6)
    exit_score: int = 0         # exit a long when score falls to this or below
    sl_atr: float = 1.5         # stop-loss distance in ATRs
    target_atr: float = 3.0     # target distance in ATRs
    trail_supertrend: bool = True
    allow_short: bool = False   # shorting is intraday-only in Indian cash market
    intraday: bool = True       # no new entries after 15:00, square off at 15:15 IST
    cost_pct: float = 0.05      # brokerage + STT + charges per side, in %
    rsi_overbought: float = 75
    rsi_oversold: float = 25
    # settings of the swing trend families (ignored by the other strategies)
    ma_len: int = 200           # trend: moving-average length in days
    band: float = 0.0           # trend: buy when the close is this fraction ABOVE the average
    exit_band: float = 0.0      # trend: sell only when the close is this fraction BELOW the average
    fast_len: int = 50          # golden cross: fast / slow averages
    slow_len: int = 200
    lookback: int = 252         # momentum: compare with the price this many trading days ago
    entry_len: int = 55         # breakout: buy a close above the highest high of this many days
    exit_len: int = 20          # breakout: sell a close below the lowest low of this many days
    trend_filter: bool = True   # breakout: only while above the 200-day average


NO_ENTRY_AFTER = time(15, 0)
SQUARE_OFF_AT = time(15, 15)


def score(df: pd.DataFrame, use_vwap: bool) -> pd.Series:
    """Bullish/bearish confluence from -6 to +6."""
    s = (
        np.sign(df["EMA_fast"] - df["EMA_slow"])
        + np.sign(df["Close"] - df["EMA_trend"])
        + df["ST_dir"]
        + np.sign(df["MACD_hist"])
        + np.where(df["RSI"] > 55, 1, np.where(df["RSI"] < 45, -1, 0))
    )
    if use_vwap:
        s = s + np.sign(df["Close"] - df["VWAP"])
    return s.astype(int)


def reasons(row: pd.Series, use_vwap: bool) -> list[tuple[str, bool | None]]:
    """Human-readable checklist for the latest candle: (text, bullish?)."""
    r = [
        (f"EMA fast {'above' if row.EMA_fast > row.EMA_slow else 'below'} EMA slow", row.EMA_fast > row.EMA_slow),
        (f"Price {'above' if row.Close > row.EMA_trend else 'below'} trend EMA", row.Close > row.EMA_trend),
        (f"Supertrend {'UP' if row.ST_dir > 0 else 'DOWN'}", row.ST_dir > 0),
        (f"MACD histogram {'positive' if row.MACD_hist > 0 else 'negative'}", row.MACD_hist > 0),
        (f"RSI {row.RSI:.1f}", True if row.RSI > 55 else False if row.RSI < 45 else None),
    ]
    if use_vwap:
        r.append((f"Price {'above' if row.Close > row.VWAP else 'below'} VWAP", row.Close > row.VWAP))
    if use_vwap and not np.isnan(row.Vol_avg):
        r.append((f"Volume {row.Volume / max(row.Vol_avg, 1):.1f}x average", None))
    return [(txt, None if b is None else bool(b)) for txt, b in r]


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pct(self) -> float:
        if self.exit is None:
            return np.nan
        raw = (self.exit / self.entry - 1) * (1 if self.side == "LONG" else -1)
        return raw * 100


@dataclass
class Result:
    trades: list[Trade] = field(default_factory=list)
    open_trade: Trade | None = None
    pending: str | None = None   # "BUY"/"SELL"/"EXIT" signalled on the last candle, to act on next open
    equity: pd.Series | None = None


def score_signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Entry/exit flags for the original 'indicator confluence' score strategy."""
    sc, rsi, std = df["Score"], df["RSI"], df["ST_dir"]
    return pd.DataFrame({
        "long_entry": (sc >= p.buy_score) & (rsi < p.rsi_overbought),
        "long_exit": (sc <= p.exit_score) | (std < 0),
        "short_entry": (sc <= -p.buy_score) & (rsi > p.rsi_oversold),
        "short_exit": (sc >= -p.exit_score) | (std > 0),
    }, index=df.index)


def run(df: pd.DataFrame, p: Params, sig: pd.DataFrame | None = None) -> Result:
    """Signals are computed on a candle's close and executed at the NEXT candle's open
    (no look-ahead). Stops/targets are checked against each candle's high/low.

    `sig` holds boolean columns long_entry/long_exit/short_entry/short_exit; it defaults
    to the score strategy. sl_atr / target_atr of 0 disable that stop / target.

    The loop works on plain Python lists and integer day/minute arrays (several times faster
    than indexing numpy/pandas per candle) — Auto mode runs it hundreds of times."""
    if sig is None:
        sig = score_signals(df, p)
    n = len(df)
    le, lx, se, sx = (sig[k].fillna(False).to_numpy(bool).tolist() for k in ("long_entry", "long_exit", "short_entry", "short_exit"))
    o, h, l, c = (df[k].to_numpy(float).tolist() for k in ("Open", "High", "Low", "Close"))
    a, st, std = (df[k].to_numpy(float).tolist() for k in ("ATR", "ST", "ST_dir"))
    idx = df.index
    # local minutes since epoch via integer maths (pandas' tz-aware .hour/.normalize() cost ~100 ms here)
    off = int(idx[0].utcoffset().total_seconds() // 60) if n and idx.tz is not None else 0
    mins = idx.asi8 // 60_000_000_000 + off
    tmin = (mins % 1440).tolist()          # minutes since local midnight
    day = (mins // 1440).tolist()          # one integer per local trading day
    sq_off = SQUARE_OFF_AT.hour * 60 + SQUARE_OFF_AT.minute
    no_entry = NO_ENTRY_AFTER.hour * 60 + NO_ENTRY_AFTER.minute
    intraday, allow_short, trail = p.intraday, p.allow_short, p.trail_supertrend
    sl_atr, target_atr, cost2 = p.sl_atr, p.target_atr, 2 * p.cost_pct / 100
    inf = float("inf")

    res = Result()
    trades = res.trades
    pos: Trade | None = None
    long_pos = False
    pending: str | None = None
    equity = [1.0] * n
    eq = 1.0

    def close_pos(i, price, why):
        nonlocal pos, eq
        pos.exit_time, pos.exit, pos.reason = idx[i], price, why
        eq *= 1 + pos.pnl_pct / 100 - cost2
        trades.append(pos)
        pos = None

    for i in range(n):
        # 1) execute what the previous candle signalled, at this candle's open
        if pending and i > 0:
            if pending == "EXIT":
                if pos:
                    close_pos(i, o[i], "Signal exit")
            elif pos is None and not (intraday and day[i] != day[i - 1]):
                long_pos = pending == "BUY"
                d = 1 if long_pos else -1
                stop = o[i] - d * sl_atr * a[i - 1] if sl_atr else -d * inf
                target = o[i] + d * target_atr * a[i - 1] if target_atr else d * inf
                pos = Trade("LONG" if long_pos else "SHORT", idx[i], o[i], stop, target)
            pending = None

        if pos is not None:
            # 2) stop / target hit inside this candle (stop assumed first if both — conservative)
            if long_pos:
                if l[i] <= pos.stop:
                    close_pos(i, min(o[i], pos.stop), "Stop-loss")
                elif h[i] >= pos.target:
                    close_pos(i, max(o[i], pos.target), "Target")
            else:
                if h[i] >= pos.stop:
                    close_pos(i, max(o[i], pos.stop), "Stop-loss")
                elif l[i] <= pos.target:
                    close_pos(i, min(o[i], pos.target), "Target")

            # 3) intraday square-off
            if pos is not None and intraday:
                last_of_day = i == n - 1 or day[i + 1] != day[i]
                if tmin[i] >= sq_off or (last_of_day and i < n - 1):
                    close_pos(i, c[i], "Intraday square-off")

            # 4) trail stop along supertrend
            if pos is not None and trail and st[i] == st[i]:   # x == x is False only for NaN
                if long_pos and std[i] > 0:
                    pos.stop = max(pos.stop, st[i])
                elif not long_pos and std[i] < 0:
                    pos.stop = min(pos.stop, st[i])

        # 5) new signal on this candle's close
        if pos is None:
            if not (intraday and tmin[i] >= no_entry):
                if le[i]:
                    pending = "BUY"
                elif allow_short and se[i]:
                    pending = "SELL"
        elif (long_pos and lx[i]) or (not long_pos and sx[i]):
            pending = "EXIT"

        # mark-to-market equity
        if pos is not None:
            equity[i] = eq * (1 + (c[i] / pos.entry - 1)) if long_pos else eq * (1 - (c[i] / pos.entry - 1))
        else:
            equity[i] = eq

    res.open_trade = pos
    res.pending = pending
    res.equity = pd.Series(equity, idx)
    return res


def stats(res: Result, df: pd.DataFrame, cost_pct: float = 0.0) -> dict:
    """Trade stats net of charges (cost_pct on each side)."""
    t = res.trades
    pnl = np.array([x.pnl_pct - 2 * cost_pct for x in t]) if t else np.array([])
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    eq = res.equity
    dd = (eq / eq.cummax() - 1).min() * 100 if eq is not None else 0
    return {
        "Trades": len(t),
        "Win rate %": round(len(wins) / len(t) * 100, 1) if t else 0,
        "Strategy return %": round((eq.iloc[-1] - 1) * 100, 2),
        "Buy & hold %": round((df["Close"].iloc[-1] / df["Open"].iloc[0] - 1) * 100, 2),
        "Avg win %": round(wins.mean(), 2) if len(wins) else 0,
        "Avg loss %": round(losses.mean(), 2) if len(losses) else 0,
        "Profit factor": round(wins.sum() / abs(losses.sum()), 2) if len(losses) and losses.sum() else float("inf") if len(wins) else 0,
        "Max drawdown %": round(dd, 2),
    }


# ---------------------------------------------------------------- strategy library
def _sig(le, lx, se=None, sx=None) -> pd.DataFrame:
    none = pd.Series(False, le.index)
    return pd.DataFrame({"long_entry": le, "long_exit": lx,
                         "short_entry": none if se is None else se, "short_exit": none if sx is None else sx})


def orb_trend_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Break of the 9:15-9:30 range, only in the direction of the daily trend, before noon.
    Held until stop-loss or 3:15 square-off."""
    window = d["After_OR"] & d["Morning"]
    never = pd.Series(False, d.index)
    return _sig(window & d["D_up"] & (d["Close"] > d["ORH"]), never,
                window & d["D_dn"] & (d["Close"] < d["ORL"]), never)


def trend200_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    return _sig(d["Close"] > d["SMA200"], d["Close"] < d["SMA200"])


def donchian_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    return _sig(d["Close"] > d["DC_hi20"], d["Close"] < d["DC_lo10"])


def rsi2_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    return _sig((d["Close"] > d["SMA200"]) & (d["RSI2"] < 10), d["Close"] > d["SMA5"])


def trend_buffer_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Invested above the average (+ optional entry band); out only when the close falls exit_band below it.
    A wide exit_band = 'stay invested unless there's a deep downtrend' — far fewer false exits."""
    ma = d["Close"].rolling(p.ma_len).mean()
    return _sig(d["Close"] > ma * (1 + p.band), d["Close"] < ma * (1 - p.exit_band))


def golden_cross_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    fast, slow = d["Close"].rolling(p.fast_len).mean(), d["Close"].rolling(p.slow_len).mean()
    return _sig(fast > slow, fast < slow)


def momentum_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Absolute (time-series) momentum: invested while the price is above its level `lookback` days ago."""
    roc = d["Close"].pct_change(p.lookback)
    return _sig(roc > 0, roc < 0)


def breakout_filter_signals(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    hi = d["High"].rolling(p.entry_len).max().shift()
    lo = d["Low"].rolling(p.exit_len).min().shift()
    up = d["Close"] > d["SMA200"] if p.trend_filter else True
    return _sig((d["Close"] > hi) & up, d["Close"] < lo)


def trend_buffer_levels(d: pd.DataFrame, p: Params) -> dict:
    ma = d["Close"].rolling(p.ma_len).mean()
    out = {f"{p.ma_len}-day average": ma}
    if p.band:
        out["Buy level"] = ma * (1 + p.band)
    if p.exit_band:
        out["Exit level"] = ma * (1 - p.exit_band)
    return out


def golden_cross_levels(d: pd.DataFrame, p: Params) -> dict:
    return {f"{p.fast_len}-day average": d["Close"].rolling(p.fast_len).mean(),
            f"{p.slow_len}-day average": d["Close"].rolling(p.slow_len).mean()}


def momentum_levels(d: pd.DataFrame, p: Params) -> dict:
    return {f"Price {round(p.lookback / 21)} months ago": d["Close"].shift(p.lookback)}


def breakout_filter_levels(d: pd.DataFrame, p: Params) -> dict:
    out = {f"{p.entry_len}-day high": d["High"].rolling(p.entry_len).max().shift(),
           f"{p.exit_len}-day low": d["Low"].rolling(p.exit_len).min().shift()}
    if p.trend_filter:
        out["200-day average"] = d["SMA200"]
    return out


@dataclass
class Strategy:
    name: str
    style: str                  # "Intraday" or "Swing"
    intervals: tuple[str, ...]  # timeframes it was tested on
    signals: object
    sl_atr: float
    target_atr: float
    trail: bool
    exit_rule: str
    summary: str
    evidence: str
    levels: object = None       # (df, params) -> {name: series} — price lines the strategy trades on
    defaults: dict = field(default_factory=dict)   # its own settings when used by hand (Pro / Compare)


STRATEGIES = {s.name: s for s in [
    Strategy("Swing · Trend with safety buffer", "Swing", ("1d",), trend_buffer_signals, 0, 0, False,
             "Sell only when the day closes a set % below the trend average.",
             "Stay invested while the price is above its 100/150/200-day average, and sell only when it falls a set "
             "% below it — fewer false exits, still out before deep crashes.",
             "Best in testing. With this and the other new trend strategies, Auto made a median 6.2%/yr on years it was "
             "never tuned on (18 instruments; the old set: 3.0%/yr). NIFTY: 5.9%/yr with a −17% worst fall (holding: 9.6%/yr, −38%).",
             trend_buffer_levels, {"ma_len": 150, "band": 0.0, "exit_band": 0.08}),
    Strategy("Swing · Golden cross", "Swing", ("1d",), golden_cross_signals, 0, 0, False,
             "Sell when the fast average falls below the slow one.",
             "Invested while the 50-day average is above the 200-day (or 20/100, 50/150) — a slow, low-turnover trend signal.",
             "Walk-forward on 18 instruments: median profit factor 2.3, profitable on 15/18, about 20 trades per decade.",
             golden_cross_levels, {"fast_len": 50, "slow_len": 200}),
    Strategy("Swing · Momentum (6/12-month)", "Swing", ("1d",), momentum_signals, 0, 0, False,
             "Sell when the price falls below its level 6 or 12 months ago.",
             "Invested while the price is higher than it was 6 or 12 months ago (absolute momentum).",
             "Walk-forward: profitable on all 18 instruments tested, median +68% over the unseen years.",
             momentum_levels, {"lookback": 252}),
    Strategy("Swing · Breakout + trend filter", "Swing", ("1d",), breakout_filter_signals, 0, 0, False,
             "Sell on a close below the recent low.",
             "Buy a close at a new 20- or 55-day high while above the 200-day average; sell on a 10- or 20-day low.",
             "Walk-forward: median +44% over the unseen years, profitable on 13/18 instruments.",
             breakout_filter_levels, {"entry_len": 55, "exit_len": 20, "trend_filter": True}),
    Strategy("Swing · Trend (200-day average)", "Swing", ("1d",), trend200_signals, 0, 0, False,
             "Exit when the day closes below the 200-day average.",
             "Stay invested while the price is above its 200-day average; step aside below it.",
             "18-28 yrs NIFTY / BANK NIFTY / SENSEX: profitable in both halves of history, profit factor 2.3-3.9, "
             "invested only part of the time. Makes less than plain holding in a bull market but sits out big crashes."),
    Strategy("Swing · Breakout (20-day high)", "Swing", ("1d",), donchian_signals, 0, 0, False,
             "Exit when the day closes below the lowest low of the last 10 days.",
             "Buy when the price closes at a new 20-day high; sell on a 10-day low (classic Donchian / turtle rule).",
             "Profitable on every index in both halves of history, profit factor 1.4-3.1."),
    Strategy("Swing · Dip-buy in uptrend (RSI-2)", "Swing", ("1d",), rsi2_signals, 0, 0, False,
             "Exit when the day closes above its 5-day average (usually 2-5 days later).",
             "In a long-term uptrend (above 200-day average) buy sharp 1-3 day dips (RSI-2 below 10).",
             "Wins ~63-65% of trades on NIFTY / SENSEX over 18-28 yrs. Failed on BANK NIFTY in the last 7 yrs."),
    Strategy("Intraday · Opening-range breakout + daily trend", "Intraday", ("5m", "15m"), orb_trend_signals, 1.5, 0, False,
             "Stop-loss 1.5 ATR; otherwise hold until 3:15 PM square-off.",
             "Mark the 9:15-9:30 high/low. Before noon, BUY a break above it if the daily trend is up; "
             "SHORT a break below it if the daily trend is down.",
             "Looked good on 60 days of data, but over 2 years of 15-min data (Angel One) it lost money after costs on "
             "NIFTY (−6%), BANK NIFTY (−1%) and SENSEX (−4%) even with the best settings in hindsight. Unproven."),
    Strategy("Indicator score (EMA/RSI/MACD/Supertrend)", "Intraday", ("1m", "5m", "15m", "1h", "1d"), score_signals, 1.5, 3, True,
             "Exit on stop-loss, target, or when the score turns negative / Supertrend flips.",
             "The original confluence score from 6 indicators.",
             "Over 2 years of 15-min data it lost 18–23% on NIFTY, BANK NIFTY and SENSEX after charges. "
             "On daily charts it does better."),
]}


def reliability(res: Result, df: pd.DataFrame, cost_pct: float, p: Params, sig: pd.DataFrame) -> tuple[str, str, dict]:
    """Grade how well the strategy has worked on THIS chart: (label, colour-key, half-period returns)."""
    s = stats(res, df, cost_pct)
    mid = df.index[len(df) // 2]
    halves = {}
    for name, sl in (("1st half", slice(None, mid)), ("2nd half", slice(mid, None))):
        if len(df.loc[sl]) > 30:
            halves[name] = stats(run(df.loc[sl], p, sig.loc[sl]), df.loc[sl], cost_pct)["Strategy return %"]
    both_ok = len(halves) == 2 and all(v > 0 for v in halves.values())
    pf = s["Profit factor"]
    if s["Trades"] < 8:
        return "⚠️ Too few past trades to judge", "warn", halves
    if s["Strategy return %"] > 0 and pf >= 1.3 and both_ok:
        return "✅ Has worked well on this chart", "good", halves
    if s["Strategy return %"] > 0 and pf >= 1.05:
        return "⚠️ Weak / inconsistent edge here", "warn", halves
    return "❌ Has NOT worked on this chart — avoid", "bad", halves
