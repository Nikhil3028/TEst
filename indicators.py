"""Technical indicators computed on an OHLCV DataFrame (columns: Open, High, Low, Close, Volume)."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["Close"].shift()
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return mid + k * sd, mid, mid - k * sd


def vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP that resets every trading day."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    day = df.index.date
    pv = (tp * df["Volume"]).groupby(day).cumsum()
    vol = df["Volume"].groupby(day).cumsum().replace(0, np.nan)
    return (pv / vol).fillna(tp)


def supertrend(df: pd.DataFrame, n=10, mult=3.0):
    """Returns (supertrend line, direction) where direction is +1 (up) or -1 (down)."""
    a = atr(df, n).to_numpy()
    hl2 = ((df["High"] + df["Low"]) / 2).to_numpy()
    close = df["Close"].to_numpy()
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    direction = np.ones(len(df))
    line = np.full(len(df), np.nan)
    for i in range(1, len(df)):
        fu[i] = upper[i] if (upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if close[i] > fu[i - 1]:
            direction[i] = 1
        elif close[i] < fl[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
        line[i] = fl[i] if direction[i] == 1 else fu[i]
    return pd.Series(line, df.index), pd.Series(direction, df.index)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Trend strength (0-100); below ~20 the market is ranging."""
    up, dn = df["High"].diff(), -df["Low"].diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), df.index)
    a = atr(df, n)
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def add_context(df: pd.DataFrame, daily: pd.DataFrame | None) -> pd.DataFrame:
    """Daily-trend and opening-range columns used by the intraday strategies.

    D_up / D_dn use *yesterday's* daily close vs EMA20 vs SMA50, so they are known at 9:15.
    ORH / ORL are the high / low of the first 15 minutes (9:15-9:30)."""
    df = df.copy()
    if daily is not None and len(daily) > 50:
        dl = pd.DataFrame({"Close": daily["Close"], "EMA20": ema(daily["Close"], 20),
                           "SMA50": daily["Close"].rolling(50).mean()}).shift(1)
        dl.index = dl.index.date
        m = dl[~dl.index.duplicated(keep="last")].reindex(df.index.date)
        df["D_up"] = ((m.Close > m.EMA20) & (m.EMA20 > m.SMA50)).to_numpy()
        df["D_dn"] = ((m.Close < m.EMA20) & (m.EMA20 < m.SMA50)).to_numpy()
    else:
        df["D_up"] = df["D_dn"] = False
    day = df.index.date
    t = pd.Series(df.index.time, df.index)
    opening = df[(t < pd.Timestamp("09:30").time()).to_numpy()]
    df["ORH"] = opening["High"].groupby(opening.index.date).max().reindex(day).to_numpy()
    df["ORL"] = opening["Low"].groupby(opening.index.date).min().reindex(day).to_numpy()
    df["After_OR"] = (t >= pd.Timestamp("09:30").time()).to_numpy()
    df["Morning"] = (t < pd.Timestamp("12:00").time()).to_numpy()
    return df


def add_all(df: pd.DataFrame, fast=9, slow=21, trend=50, st_period=10, st_mult=3.0) -> pd.DataFrame:
    df = df.copy()
    c = df["Close"]
    df["EMA_fast"] = ema(c, fast)
    df["EMA_slow"] = ema(c, slow)
    df["EMA_trend"] = ema(c, trend)
    df["RSI"] = rsi(c)
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = macd(c)
    df["ATR"] = atr(df)
    df["BB_up"], df["BB_mid"], df["BB_low"] = bollinger(c)
    df["VWAP"] = vwap(df)
    df["ST"], df["ST_dir"] = supertrend(df, st_period, st_mult)
    df["Vol_avg"] = df["Volume"].rolling(20).mean()
    df["SMA200"] = c.rolling(200).mean()
    df["SMA5"] = c.rolling(5).mean()
    df["RSI2"] = rsi(c, 2)
    df["ADX"] = adx(df)
    df["DC_hi20"] = df["High"].rolling(20).max().shift()
    df["DC_lo10"] = df["Low"].rolling(10).min().shift()
    return df
