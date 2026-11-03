"""Options: contracts & expiries (Groww's public instrument list), option chain (Groww API, a chain pasted
from the Groww page, or a Black-Scholes estimate), OI analytics, and an option trade plan built from the
underlying's signal."""
import io
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from data import IST

INSTRUMENT_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"
CACHE = Path(__file__).parent / ".cache" / "options_contracts.csv"
STOCKS_CACHE = Path(__file__).parent / ".cache" / "nse_stocks.csv"
CACHE_MAX_AGE = 12 * 3600

# app index name -> (option underlying symbol, exchange)
INDEX_UNDERLYING = {"NIFTY 50": ("NIFTY", "NSE"), "BANK NIFTY": ("BANKNIFTY", "NSE"),
                    "NIFTY FIN SERVICE": ("FINNIFTY", "NSE"), "SENSEX": ("SENSEX", "BSE")}
# Yahoo ticker -> Groww "EXCHANGE_SYMBOL" for the underlying's live price
GROWW_SPOT = {"^NSEI": "NSE_NIFTY", "^NSEBANK": "NSE_BANKNIFTY", "^BSESN": "BSE_SENSEX",
              "NIFTY_FIN_SERVICE.NS": "NSE_FINNIFTY"}
CHAIN_COLS = ["strike", "ce_ltp", "ce_change", "ce_oi", "ce_oi_change", "ce_volume", "ce_iv", "ce_delta",
              "pe_ltp", "pe_change", "pe_oi", "pe_oi_change", "pe_volume", "pe_iv", "pe_delta"]


# ---------------------------------------------------------------- contracts
_lock = threading.Lock()
_loaded_at = 0.0
_all: pd.DataFrame | None = None
_by_und: dict[tuple[str, str], pd.DataFrame] = {}


def contracts() -> pd.DataFrame:
    """All listed CE/PE contracts. Downloaded at most every 12 h, read from disk once, then kept in memory
    and indexed by (underlying, exchange) so lookups take microseconds instead of re-reading 11 MB."""
    global _all, _by_und, _loaded_at
    with _lock:
        if _all is not None and time.time() - _loaded_at < CACHE_MAX_AGE:
            return _all
        if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_MAX_AGE:
            df = pd.read_csv(CACHE)
        else:
            df = _download_master()
        _by_und = {k: g.reset_index(drop=True) for k, g in df.groupby(["underlying_symbol", "exchange"])}
        _all, _loaded_at = df, time.time()
        return df


def _download_master() -> pd.DataFrame:
    """Groww's instrument list -> option contracts (returned + cached) and NSE stocks with names (cached)."""
    cols = ["exchange", "trading_symbol", "groww_symbol", "name", "instrument_type", "segment", "series",
            "underlying_symbol", "expiry_date", "strike_price", "lot_size"]
    full = pd.read_csv(INSTRUMENT_URL, usecols=cols, low_memory=False)
    CACHE.parent.mkdir(exist_ok=True)
    eq = full[(full.exchange == "NSE") & (full.instrument_type == "EQ") & full.series.isin(["EQ", "BE"])]
    eq[["trading_symbol", "name"]].drop_duplicates("trading_symbol").to_csv(STOCKS_CACHE, index=False)
    df = full[full.instrument_type.isin(["CE", "PE"])][["exchange", "trading_symbol", "groww_symbol", "instrument_type",
                                                        "underlying_symbol", "expiry_date", "strike_price", "lot_size"]]
    df.to_csv(CACHE, index=False)
    return df


_stocks: pd.DataFrame | None = None


def stocks() -> pd.DataFrame:
    """NSE stocks / ETFs with company names (symbol, name) for search."""
    global _stocks
    if _stocks is None or not STOCKS_CACHE.exists():
        if not STOCKS_CACHE.exists() or time.time() - STOCKS_CACHE.stat().st_mtime > 7 * 86400:
            with _lock:
                _download_master()
        _stocks = pd.read_csv(STOCKS_CACHE).dropna()
    return _stocks


def _sub(underlying: str, exchange: str) -> pd.DataFrame:
    contracts()
    return _by_und.get((underlying, exchange), _EMPTY)


_EMPTY = pd.DataFrame(columns=["exchange", "trading_symbol", "groww_symbol", "instrument_type", "underlying_symbol",
                               "expiry_date", "strike_price", "lot_size"])


def underlying_for(app_symbol: str, yahoo_ticker: str) -> tuple[str, str] | None:
    """(underlying, exchange) if this index/stock has listed options."""
    if app_symbol in INDEX_UNDERLYING:
        return INDEX_UNDERLYING[app_symbol]
    if yahoo_ticker.endswith(".NS") and len(_sub(yahoo_ticker[:-3], "NSE")):
        return yahoo_ticker[:-3], "NSE"
    return None


def expiries(underlying: str, exchange: str) -> list[str]:
    today = datetime.now(IST).date().isoformat()
    e = _sub(underlying, exchange).expiry_date
    return sorted(e[e >= today].unique())


def default_expiry(exps: list[str], min_days: int = 1) -> int:
    """Index of the expiry to suggest: the nearest at least `min_days` away (never expiry day itself).
    Swing trades use min_days≈21 so time decay doesn't eat the move."""
    today = datetime.now(IST).date()
    for i, e in enumerate(exps):
        if (date.fromisoformat(e) - today).days >= max(min_days, 1):
            return i
    return len(exps) - 1


def lot_size(underlying: str, exchange: str, expiry: str) -> int:
    c = _sub(underlying, exchange)
    m = c[c.expiry_date == expiry]
    return int(m.lot_size.iloc[0]) if len(m) else 1


def contract(underlying: str, exchange: str, expiry: str, strike: float, kind: str) -> dict | None:
    c = _sub(underlying, exchange)
    m = c[(c.expiry_date == expiry) & (c.instrument_type == kind) & (np.isclose(c.strike_price, strike))]
    return m.iloc[0].to_dict() if len(m) else None


def strikes(underlying: str, exchange: str, expiry: str) -> np.ndarray:
    c = _sub(underlying, exchange)
    return np.sort(c[c.expiry_date == expiry].strike_price.unique())


def display_name(underlying: str, expiry: str, strike: float, kind: str) -> str:
    """Groww-style name, e.g. 'NIFTY 3 Nov 23600 CE'."""
    d = date.fromisoformat(expiry)
    return f"{underlying} {d.day} {d:%b} {strike:g} {kind}"


# ---------------------------------------------------------------- chain
@dataclass
class Chain:
    underlying: str
    expiry: str
    spot: float
    table: pd.DataFrame  # CHAIN_COLS
    source: str          # "groww" | "pasted" | "estimate"
    as_of: str
    notes: list = field(default_factory=list)

    @property
    def has_oi(self) -> bool:
        return self.table[["ce_oi", "pe_oi"]].notna().any().all()


def from_groww(groww, underlying: str, exchange: str, expiry: str) -> Chain:
    resp = groww.get_option_chain(exchange=exchange, underlying=underlying, expiry_date=expiry)
    rows = []
    for k, side in resp.get("strikes", {}).items():
        r = {"strike": float(k)}
        for kind in ("CE", "PE"):
            o = side.get(kind) or {}
            g = o.get("greeks") or {}
            p = kind.lower()
            r.update({f"{p}_ltp": o.get("ltp"), f"{p}_oi": o.get("open_interest"), f"{p}_volume": o.get("volume"),
                      f"{p}_iv": g.get("iv"), f"{p}_delta": g.get("delta")})
        rows.append(r)
    t = pd.DataFrame(rows).reindex(columns=CHAIN_COLS).sort_values("strike").reset_index(drop=True)
    return Chain(underlying, expiry, float(resp.get("underlying_ltp") or np.nan), t, "groww",
                 datetime.now(IST).strftime("%d %b %H:%M:%S"))


def from_angel(feed, underlying: str, expiry: str, spot: float) -> Chain:
    import angel
    t = feed.chain_table(underlying, expiry, spot).reindex(columns=CHAIN_COLS)
    t = t.apply(pd.to_numeric, errors="coerce").sort_values("strike").reset_index(drop=True)
    return Chain(underlying, expiry, spot, t, "angel", angel.as_of())


def from_csv(text: str) -> Chain:
    """Parse the CSV produced by the browser-extension prompt (first line '#underlying=..,spot=..,...')."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip() and not ln.strip().startswith("```")]
    meta = {}
    if lines and lines[0].lstrip().startswith("#"):
        for part in lines.pop(0).lstrip("# ").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                meta[k.strip().lower()] = v.strip()
    t = pd.read_csv(io.StringIO("\n".join(lines)))
    t.columns = [c.strip().lower() for c in t.columns]
    if "strike" not in t.columns:
        raise ValueError("CSV needs a 'strike' column (use the prompt's exact header row).")
    t = t.reindex(columns=CHAIN_COLS).apply(pd.to_numeric, errors="coerce").dropna(subset=["strike"])
    t = t.sort_values("strike").reset_index(drop=True)
    spot = float(meta.get("spot", "nan").replace(",", "") or "nan")
    return Chain(meta.get("underlying", "").upper(), meta.get("expiry", ""), spot, t, "pasted",
                 meta.get("captured_at", "unknown time"))


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def estimate(underlying: str, expiry: str, spot: float, iv_pct: float, strike_list, rate=0.065) -> Chain:
    """Black-Scholes prices & deltas from an implied volatility (e.g. India VIX). No OI."""
    exp_dt = datetime.combine(date.fromisoformat(expiry), datetime.min.time()).replace(hour=15, minute=30, tzinfo=IST)
    t_years = max((exp_dt - datetime.now(IST)).total_seconds(), 600) / (365 * 86400)
    sig = iv_pct / 100
    rows = []
    for k in strike_list:
        d1 = (math.log(spot / k) + (rate + sig * sig / 2) * t_years) / (sig * math.sqrt(t_years))
        d2 = d1 - sig * math.sqrt(t_years)
        disc = math.exp(-rate * t_years)
        ce = spot * _ncdf(d1) - k * disc * _ncdf(d2)
        pe = k * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        rows.append({"strike": k, "ce_ltp": round(max(ce, 0.05), 2), "pe_ltp": round(max(pe, 0.05), 2),
                     "ce_delta": round(_ncdf(d1), 3), "pe_delta": round(_ncdf(d1) - 1, 3), "ce_iv": iv_pct, "pe_iv": iv_pct})
    t = pd.DataFrame(rows).reindex(columns=CHAIN_COLS)
    return Chain(underlying, expiry, spot, t, "estimate", datetime.now(IST).strftime("%d %b %H:%M:%S"),
                 [f"Premiums are estimates (Black-Scholes, IV {iv_pct:.1f}%) — not live prices. Check Groww before ordering."])


# ---------------------------------------------------------------- analytics
def atm_strike(chain: Chain, spot: float) -> float:
    s = chain.table.strike
    return float(s.iloc[(s - spot).abs().argmin()])


def analytics(chain: Chain, spot: float) -> dict:
    t = chain.table
    out = {"atm": atm_strike(chain, spot)}
    if chain.has_oi:
        ce_oi, pe_oi = t.ce_oi.fillna(0), t.pe_oi.fillna(0)
        out["pcr"] = pe_oi.sum() / ce_oi.sum() if ce_oi.sum() else np.nan
        k = t.strike.to_numpy()
        pain = [(ce_oi * np.maximum(0, s - k)).sum() + (pe_oi * np.maximum(0, k - s)).sum() for s in k]
        out["max_pain"] = float(k[int(np.argmin(pain))])
        out["resistance"] = float(t.strike[ce_oi.idxmax()])   # heaviest call writing
        out["support"] = float(t.strike[pe_oi.idxmax()])      # heaviest put writing
        pcr = out["pcr"]
        out["bias"] = ("Bullish — put writers dominate" if pcr >= 1.2 else
                       "Bearish — call writers dominate" if pcr <= 0.8 else "Neutral / range-bound")
        out["bias_dir"] = 1 if pcr >= 1.2 else -1 if pcr <= 0.8 else 0
    atm_row = t[t.strike == out["atm"]]
    if len(atm_row):
        ivs = atm_row[["ce_iv", "pe_iv"]].iloc[0].dropna()
        out["atm_iv"] = float(ivs.mean()) if len(ivs) else np.nan
    return out


def plan(chain: Chain, kind: str, spot: float, idx_stop: float | None, idx_target: float | None,
         lot: int, capital: float, risk_pct: float, strike: float | None = None) -> dict | None:
    """Option trade plan for buying `kind` (CE/PE). Premium stop/target come from the underlying's
    stop/target scaled by the option's delta (≈ how much the premium moves per ₹1 of the index)."""
    k = strike if strike is not None else atm_strike(chain, spot)
    row = chain.table[chain.table.strike == k]
    if not len(row):
        return None
    row = row.iloc[0]
    p = kind.lower()
    prem = row[f"{p}_ltp"]
    if pd.isna(prem) or prem <= 0:
        return None
    delta = abs(row[f"{p}_delta"]) if pd.notna(row[f"{p}_delta"]) and row[f"{p}_delta"] != 0 else 0.5
    move_stop = abs(spot - idx_stop) if idx_stop else 0.004 * spot
    stop = max(prem - delta * move_stop, prem * 0.5)          # never risk more than half the premium
    move_tgt = abs(idx_target - spot) if idx_target else 2 * move_stop
    target = prem + delta * move_tgt
    if not idx_target:
        target = min(target, prem * 2)  # no fixed target on the underlying: book at most +100% on the option
    risk_per_lot = (prem - stop) * lot
    lots = int(min(capital * risk_pct / 100 / risk_per_lot if risk_per_lot > 0 else 0, capital / (prem * lot)))
    return {"strike": k, "kind": kind, "premium": float(prem), "delta": float(delta), "stop": round(float(stop), 2),
            "target": round(float(target), 2), "lots": lots, "qty": lots * lot, "lot": lot,
            "cost": lots * lot * float(prem), "max_loss": lots * risk_per_lot}


# ---------------------------------------------------------------- Groww API
def connect_groww(cfg: dict):
    """GrowwAPI client from a secrets dict: either totp_token+totp_secret (no daily approval) or
    api_key+api_secret (needs daily approval on Groww). Returns None if not configured."""
    if not cfg:
        return None
    from growwapi import GrowwAPI
    if cfg.get("totp_token") and cfg.get("totp_secret"):
        import pyotp
        token = GrowwAPI.get_access_token(api_key=cfg["totp_token"], totp=pyotp.TOTP(cfg["totp_secret"]).now())
    elif cfg.get("api_key") and cfg.get("api_secret"):
        token = GrowwAPI.get_access_token(api_key=cfg["api_key"], secret=cfg["api_secret"])
    elif cfg.get("access_token"):
        token = cfg["access_token"]
    else:
        return None
    return GrowwAPI(token)


def groww_ltp(groww, yahoo_ticker: str) -> float | None:
    sym = GROWW_SPOT.get(yahoo_ticker) or (f"NSE_{yahoo_ticker[:-3]}" if yahoo_ticker.endswith(".NS") else None)
    if not sym:
        return None
    r = groww.get_ltp(exchange_trading_symbols=(sym,), segment=groww.SEGMENT_CASH)
    v = r.get(sym) if isinstance(r, dict) else None
    return float(v) if v else None
