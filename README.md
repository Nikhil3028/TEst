# Trade Signals India

Clear BUY / SELL / HOLD / WAIT signals for NSE & BSE — tested on years of data, with the exact steps to follow on Groww.

## Start
```bash
cd ~/Desktop/TP
.venv/bin/streamlit run app.py
```
Opens at http://localhost:8501. The first launch asks four quick questions (capital, risk per trade, style, what you
trade). First time on a new machine: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

## Pages
| Page | What it's for |
|---|---|
| **Home** | Today's signals for your watchlist (sorted: act now → holding → waiting), market mood, your open trades |
| **Chart** | One stock / index: live chart, the signal, *What to do now*, confidence, why — plus Paper-trade / I bought this |
| **Options** | The option to buy for the signal, live option chain (OI, PCR, max pain), the option's own chart |
| **Trades** | Paper and real trades with live P&L; stops and targets close them automatically |
| **Strategy Lab** | Backtests, walk-forward results, strategy comparison, watchlist scan |
| **Settings** | Profile & risk, watchlist, live updates & alerts, data connections, advanced |
| **Help** | Quick start, glossary, what the testing found, limitations |

Light / dark theme: ⋮ menu → Settings → Choose app theme.

## Code
- `app.py` – entry point: theme, connections, first-run setup, navigation, live market strip
- `core.py` – the brain: preferences, data, analysis, Auto (walk-forward) strategy selection, the signal for any instrument
- `views/` – one file per page (+ `common.py` shared rendering)
- `strategy.py` – strategies, backtest engine, reliability grading
- `indicators.py` – EMA, RSI, MACD, ATR, Bollinger, VWAP, Supertrend, ADX, opening range
- `data.py` – Yahoo Finance data, market hours (IST)
- `angel.py` – Angel One SmartAPI: login, tick stream, option chain, 2-year intraday history cache
- `options.py` – contracts, expiries, lot sizes, option chains, OI analytics, option trade plans
- `chart.py` – Groww-style chart (TradingView Lightweight Charts), live ticks, desktop alerts, light/dark aware
- `livefeed.py` – local feed the chart streams ticks from
- `journal.py` – trades journal (`paper_trades.json`)
- `ui.py` – design system (theme-aware components)

Your settings live in `profile.json`; broker keys in `.streamlit/secrets.toml` — never share or commit either.

Signals are based on past price patterns. Not investment advice; past results don't guarantee future ones.
