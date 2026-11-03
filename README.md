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
- `livefeed.py` – live chart updates: its own port on this computer / WiFi, a file Streamlit serves when online
- `journal.py` – trades journal (`paper_trades.json`)
- `store.py` – where settings and trades are saved: files here, or a private GitHub Gist when online
- `ui.py` – design system (theme-aware components)

Your settings live in `profile.json`; broker keys in `.streamlit/secrets.toml` — never share or commit either.

## Use it on your phone
**At home (same WiFi):** start the app on the laptop and open the *Network URL* it prints (e.g. `http://192.168.x.x:8501`)
on the phone.

**Anywhere, free — Streamlit Community Cloud** (keep it private: only you can open it):
1. Push this folder to GitHub. `.gitignore` keeps `secrets.toml`, your trades and your settings out of it.
2. [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub → **Create app** → deploy from GitHub → your
   repository, branch `main`, main file `app.py` → **Advanced settings**: Python 3.12, and paste your secrets
   (see `.streamlit/secrets.toml.example`) → **Deploy**.
3. The app's **Settings → Sharing → Who can view this app → Only specific people can view this app** → add your own email.
   (Apps from a public repository start out public — this step matters: your trades and settings are in the app.)
4. Keep your settings and trades when the app restarts: create a *secret* gist at [gist.github.com](https://gist.github.com)
   with any file in it, a token at [github.com/settings/tokens](https://github.com/settings/tokens) (classic, only the
   `gist` scope), and put both under `[storage]` in the app's Secrets.
5. On the phone: open the app's link → browser menu → **Add to Home screen**.

Online, the chart's live price updates every 2–3 s (on your laptop: every tick, via `livefeed.py`'s own port; online
that port can't be reached, so the chart reads a small file the app serves from `static/feed/`). The app sleeps after
12 hours without visits — open it and press the wake-up button. Use one Angel One login at a time: running the laptop
copy and the online copy together can disconnect each other's live ticks.

Signals are based on past price patterns. Not investment advice; past results don't guarantee future ones.
