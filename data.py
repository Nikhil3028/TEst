"""Market data for NSE/BSE via Yahoo Finance (free; NSE quotes are near real-time, may lag ~1 min)."""
import time as _time
import warnings
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*inplace.*")

IST = ZoneInfo("Asia/Kolkata")

INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT",
    "NIFTY FIN SERVICE": "NIFTY_FIN_SERVICE.NS",
}

POPULAR = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "BHARTIARTL", "ITC",
    "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI", "TMPV",
    "SUNPHARMA", "M&M", "TITAN", "ADANIENT", "ONGC", "NTPC", "POWERGRID", "WIPRO",
    "HCLTECH", "TATASTEEL", "ETERNAL", "IRFC", "SUZLON", "YESBANK", "IDEA",
]

# Yahoo limits how far back each interval goes
INTERVALS = {
    "1 minute": ("1m", "5d"),
    "5 minutes": ("5m", "60d"),
    "15 minutes": ("15m", "60d"),
    "1 hour": ("1h", "1y"),
    "1 day": ("1d", "max"),
}


def to_yahoo(symbol: str, exchange: str = "NSE") -> str:
    """'RELIANCE' -> 'RELIANCE.NS'; index names and already-qualified tickers pass through."""
    s = symbol.strip().upper()
    if s in INDICES:
        return INDICES[s]
    if s.startswith("^") or s.endswith((".NS", ".BO")):
        return s
    return s + (".BO" if exchange == "BSE" else ".NS")


def fetch(ticker: str, interval: str, period: str, retries: int = 2) -> pd.DataFrame:
    """OHLCV candles in IST. Yahoo sometimes answers a valid symbol with nothing ("possibly delisted") or errors
    for a moment, so empty / failed answers are retried a couple of times before giving up."""
    df = pd.DataFrame()
    for attempt in range(retries + 1):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        except Exception:  # noqa: BLE001 — network / Yahoo hiccup
            df = pd.DataFrame()
        if not df.empty:
            break
        if attempt < retries:
            _time.sleep(1.5 * (attempt + 1))
    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([], tz=IST))
    df = _repair_spikes(df[["Open", "High", "Low", "Close", "Volume"]].dropna())
    df.index = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize(IST)
    return df


def _repair_spikes(df: pd.DataFrame) -> pd.DataFrame:
    """Yahoo sometimes records a few candles at 1/10th (or 10x) the real price. Rescale any candle
    that is more than 3x away from the median of its neighbours."""
    if len(df) < 5:
        return df
    med = df["Close"].rolling(7, center=True, min_periods=3).median()
    ratio = med / df["Close"]
    bad = (ratio > 3) | (ratio < 1 / 3)
    if bad.any():
        df = df.copy()
        f = ratio[bad].round(0).where(ratio[bad] > 1, 1 / (1 / ratio[bad]).round(0))
        df.loc[bad, ["Open", "High", "Low", "Close"]] = df.loc[bad, ["Open", "High", "Low", "Close"]].mul(f, axis=0)
    return df


def market_status(now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False, "Market closed (weekend)"
    t = now.time()
    if time(9, 0) <= t < time(9, 15):
        return False, "Pre-open session"
    if time(9, 15) <= t <= time(15, 30):
        return True, "Market OPEN"
    return False, "Market closed"


def is_candle_complete(last_ts: pd.Timestamp, interval: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(IST)
    step = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(interval)
    if step is None:  # daily
        return not market_status(now)[0] or last_ts.date() < now.date()
    return last_ts + pd.Timedelta(minutes=step) <= now
