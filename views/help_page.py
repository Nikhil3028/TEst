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

#### Best setups today (Home)
Besides your watchlist, the app checks every stock of an index (NIFTY 100 by default — change it in Settings → Watchlist)
once a day and shows two short lists: **Buy now** (a BUY just triggered and the price is still at the entry) and
**Close to a buy** (the BUY level is within 2%). Only stocks where the method passed its test on unseen years are
shown, best record first. It's a shortlist, not a guarantee — open the chart, read the plan, use the stop-loss.

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
| **Target** | The price where you take your profit — shown with every BUY, so you can place the sell order straight away. If the trend is still up after it sells, a new BUY appears. |
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
| **News this week** | A reading of the last 7 days' headlines: Positive · Negative · Mixed · Neutral · Quiet. Context only. |
| **Results date** | The day the company reports its quarterly numbers. Prices can jump past a stop-loss that day. |
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

#### Selling at a target, or waiting for the SELL signal?
Tested on 4 indices + 24 large-cap stocks, unseen years. The target is a multiple of the stock's typical daily move (ATR):

| When to take profit | Per year (median) | Trades won | Stocks better / worse than no target |
|---|---|---|---|
| No target — wait for the SELL signal | 4.0% | 34% | — |
| Target at 4 typical moves | 7.3% | 71% | 20 / 6 |
| Target at 6 | 7.2% | 57% | 17 / 7 |
| Target at 10 | 6.4% | 52% | 19 / 7 |
| Target at 15 | 6.7% | 43% | 15 / 9 |

Booking profit at a target and buying again while the trend holds did better than holding on for the SELL signal,
at every distance tried. The app uses **3 typical moves** on every swing strategy (6.6% a year on the same test), so
every swing BUY comes with a target price you can place as a sell order immediately.

#### Adding the wider market to the signals — tested, not used
Would the signals do better if they also looked at things beyond the stock's own price? Tested on 4 indices + 24
large-cap stocks, on unseen years, by allowing a BUY only when the extra condition was true:

| Extra condition for a BUY | Per year (median, unseen years) | Stocks better / worse |
|---|---|---|
| **None (today's signals)** | **6.4%** | — |
| NIFTY above its 200-day average | 5.5% | 9 / 16 |
| NIFTY not in a downtrend | 6.0% | 9 / 8 |
| India VIX below 25 | 5.3% | 6 / 18 |
| India VIX not spiking | 6.5% | 7 / 7 |
| US market (S&P 500) above its 200-day average | 5.8% | 10 / 14 |
| Rupee not falling sharply | 6.3% | 8 / 12 |
| Stock stronger than NIFTY over 6 months | 6.1% | 8 / 15 |

None of them helped — a stock's own trend already carries most of this information, and the filters mostly made the
signals late. So they are **not** part of the signal.

#### News and results dates — shown, but not part of the signal
Old headlines can't be downloaded for free, so news could not be tested on past years like everything else here.
The app therefore shows this week's headlines and the next results date as **context and warnings** on a signal
(for example *“Results are due tomorrow”*), and never changes BUY / SELL because of them. The good / bad reading is
made from the words in each headline and can be wrong — read the headline itself.

To change that, the app now **keeps every headline it sees** (folder `news_archive`, on your computer), with the time it
was published and the time the app first saw it. After about a year there will be enough to test whether news
improves the signals — and only then would it be allowed to change one. Open the app at least once a week so no
headlines are missed (Google News goes back 7 days).

#### Choosing stocks instead of timing them — the momentum portfolio
The catch above — holding beat every timing rule — pointed to a different question: not *when* to hold a stock, but
*which* stocks to hold. Tested monthly from 2010 to 2026 on the 200 most-traded stocks, with charges:

| | Per year | 2010–18 · 2018–26 | Worst fall |
|---|---|---|---|
| **Strongest 20, re-picked monthly** | **+31%** | +35% · +27% | −39% |
| Strongest 10 | +30% | +37% · +24% | −51% |
| Strongest 20, in cash while NIFTY is below its 200-day average | +25% | +29% · +22% | −25% |
| Holding all 200 | +17% | +16% · +18% | −44% |
| NIFTY 200 index | +11% | +10% · +12% | −38% |

It beat holding in both halves, in every variant tried (24 of 24). **But the numbers are flattered:** the test can
only pick from companies that are in the NIFTY 500 *today*, so the failures of the past are missing — the real edge
will be much smaller than the table. It also fell as hard as the market, and lost money in 2025 while the index rose.
It lives on the **Portfolio** page, with the full test and its limits.

#### Intraday — 2 years of 15-min data, NIFTY / BANK NIFTY / SENSEX
No simple intraday rule (8 tested) made money after charges — not even the best settings in hindsight. That's why
the app recommends **Swing**.
""")

with tab_limits:
    st.markdown("""
- **Data:** with Angel One connected, live ticks (~1 s), the live option chain and 2 years of intraday history.
  Without it, Yahoo Finance (~10 s delay, 60 days of intraday history).
- **Past results don't guarantee future ones.** Recent years were weaker than earlier ones for most strategies.
- **Online version** (Streamlit Community Cloud): the chart's live price updates every 2–3 seconds instead of every
  tick, and the app falls asleep after 12 hours without visits — open it and press the wake-up button (about a minute).
- **Always confirm the price on Groww** before you place an order.
- Risk 1–2% of your capital per trade, and practise with paper trades first.
- This app is a tool for your own decisions. It is **not SEBI-registered investment advice**.
""")
