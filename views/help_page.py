"""Help: how to use the app, a plain-language glossary, what the research found, and the limits."""
import streamlit as st

import ui

ui.page_header("Help", "How to use Trade Signals with Groww, what every word means, and what the testing found.")

tab_start, tab_words, tab_research, tab_limits = st.tabs(["Quick start", "Glossary", "What the testing found", "Data & limits"])

with tab_start:
    st.markdown("""
#### Your daily routine (5 minutes)
1. **Open Home.** Your watchlist is checked automatically. Cards are sorted so the ones that need action come first.
2. **BUY card?** Click **Open**. The Chart page shows the exact plan: price, **stop-loss**, target and **quantity**.
   Trust **High** / **Medium** confidence; skip **Not proven**.
3. **Place it on Groww.** Buy the quantity shown, then immediately add a **Stop-loss** (or GTT) order at the stop price.
4. **Track it.** Click **I bought this** (real trade) or **Paper-trade** (practice). The Trades page shows your live P&L and
   closes the trade when the stop-loss or target is hit.
5. **SELL card?** Sell on Groww, then cancel any leftover stop-loss / target orders.

#### For index options (NIFTY, BANK NIFTY, SENSEX)
An index can't be bought directly. A **BUY** means *buy a CALL (CE)*, a **SHORT** means *buy a PUT (PE)*.
The **Options** page names the exact contract, its premium, a stop-loss and target on the premium, and how many lots fit
your risk — and says *skip* when even one lot is too risky for your capital.

#### Alerts
Click the **🔕** bell at the top right of the chart once and allow notifications. From then on you get a desktop
notification and a beep when the signal changes — even with the tab in the background.
""")

with tab_words:
    st.markdown("""
| Word | What it means |
|---|---|
| **BUY** | A new setup just appeared — enter now. |
| **SHORT** | The price is expected to fall. For indices: buy a PUT option. |
| **HOLD** | The strategy is already in a trade. If you're in, stay in; if not, don't chase it. |
| **SELL (exit)** | Time to get out of what you bought. |
| **WAIT** | Nothing to do. The card shows the price that would trigger the next BUY. |
| **SKIP** | A signal fired, but this method hasn't worked on this stock — safer to ignore. |
| **Stop-loss** | The price where you accept being wrong and get out. Always place it right after buying. |
| **Target** | The price where you take your profit. Some strategies have none and exit on a SELL signal instead. |
| **Trailing stop** | A stop-loss that moves up as the price rises, locking in profit. |
| **Risk per trade** | How much one losing trade may cost you. The app sizes every trade to that. |
| **Confidence** | How well the method worked on this stock on periods it was **never tuned on**: High · Medium · Low · Not proven. |
| **Walk-forward test** | Choose the best setting using only older data, then check it on the next, unseen period — three times. |
| **Swing / Intraday** | Swing = hold for days to weeks (daily candles). Intraday = buy and sell the same day. |
| **Candle** | One bar of the chart: open, high, low and close for that time (15 min, 1 day…). |
| **Typical move (ATR)** | How much the price usually moves in one candle. Stops and targets are set as multiples of it. |
| **Option chain** | All strike prices of an option expiry with their premiums. |
| **CE / PE** | Call option (gains when the price rises) / Put option (gains when it falls). |
| **OI · PCR** | Open interest = open option contracts. PCR = put OI ÷ call OI; above 1 leans bullish, below 0.8 bearish. |
| **Max pain** | The strike where option buyers lose the most at expiry — prices often drift towards it. |
| **India VIX** | The market's fear gauge. Low = calm, high = nervous. |
""")

with tab_research:
    st.markdown("""
Every strategy was backtested on real NSE / BSE data — buying at the next candle's open, paying charges — and judged
only on **years it was never tuned on** (walk-forward: pick the best setting on older data, test it on the next period, 3 times).

#### Swing (daily) — 3 indices + 15 large-cap stocks, 18–30 years each
| Strategy set | Per year (median, unseen years) | Worst fall (median) |
|---|---|---|
| **Today's Auto: trend + buffer, golden cross, momentum, breakout + filter, plus the originals** | **6.2%** | −38% |
| The original four strategies only | 3.0% | −39% |
| Simply holding | 11.8% | −50% |

| Index | Auto (new) | Original Auto | Holding |
|---|---|---|---|
| NIFTY 50 | **5.9%/yr · −17% worst fall** | 3.1%/yr · −24% | 9.6%/yr · −38% |
| BANK NIFTY | **3.2%/yr · −18%** | 1.0%/yr · −28% | 9.3%/yr · −48% |
| SENSEX | **6.2%/yr · −27%** | 2.8%/yr · −20% | 10.9%/yr · −38% |

- **What worked:** trend-following with a *safety buffer* (sell only when the price falls a set % below its average),
  golden cross, 6/12-month momentum, breakouts with a trend filter.
- **What didn't:** short-term dip-buying (RSI-2 variants, IBS, double-7s) and the turn-of-the-month effect — not used.
- **The honest catch:** in India's long bull market, simply holding made more money than any timing rule. The signals'
  value is mostly *protection* — on the indices they roughly halved the worst falls. On single stocks protection is
  less reliable (e.g. SUNPHARMA fell further with the strategy than holding).

#### Intraday — 2 years of 15-min data, NIFTY / BANK NIFTY / SENSEX
No simple intraday rule (8 tested) made money after charges — not even the best settings in hindsight. That's why
the app recommends **Swing**.
""")

with tab_limits:
    st.markdown("""
- **Data:** with Angel One connected, live ticks (~1 s), the live option chain and 2 years of intraday history.
  Without it, Yahoo Finance (~10 s delay, 60 days of intraday history).
- **Past results don't guarantee future ones.** Recent years were weaker than earlier ones for most strategies.
- **Always confirm the price on Groww** before you place an order.
- Risk 1–2% of your capital per trade, and practise with paper trades first.
- This app is a tool for your own decisions. It is **not SEBI-registered investment advice**.
""")
