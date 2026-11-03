"""Chart: one instrument in detail — live chart, the signal, what to do, and why."""
import streamlit as st

import core
import journal
import options
import ui
from views import common
from views.common import CHART_H, run_every

P = core.prefs()
sel = core.selection()
RUN = run_every(P)

# ---------------------------------------------------------------- toolbar
cols = st.columns([2.3, 2.1, 1.7, 1] if P.pro else [2.6, 2.4, 1], vertical_alignment="center")
with cols[0]:
    picked = common.symbol_picker(sel.symbol)
if picked != sel.symbol:
    core.select(picked, exchange="NSE")
    st.rerun()
with cols[1]:
    common.timeframe_picker(sel)
if P.pro:
    with cols[2]:
        common.strategy_controls(sel)
with cols[-1]:
    watching = sel.symbol in P.watchlist
    if st.button("Watching" if watching else "Watch", icon=":material/star:" if watching else ":material/star_border:",
                 width="stretch", help="Add to / remove from your Home watchlist"):
        core.update_prefs(watchlist=[s for s in P.watchlist if s != sel.symbol] if watching else P.watchlist + [sel.symbol])
        st.rerun()

c, S = None, None


def compute():
    """Analysis (cached per candle) + live price -> the signal. Called by every live section."""
    global c, S
    with st.spinner(f"Analysing {sel.symbol}…"):
        c = core.build(sel, P)
    if c is None:
        st.error(f"No price data for **{sel.symbol}**. Check the symbol — use the NSE name, e.g. TATAPOWER.")
        st.stop()
    S = core.signal(c)
    common.chart_live(c, P)   # keeps the chart's live updates flowing when opened online


compute()


# ---------------------------------------------------------------- header (refreshes itself)
@st.fragment(run_every=RUN)
def header():
    compute()
    today = c.today
    day_hi = max(float(c.raw["High"][today].max()), c.ltp)
    day_lo = min(float(c.raw["Low"][today].min()), c.ltp)
    vol = float(c.raw["Volume"][today].sum())
    name = core.name_of(c.symbol)
    trend_word = {"UP": "Daily trend up", "DOWN": "Daily trend down", "SIDEWAYS": "Daily trend sideways"}[c.daily_trend]
    trend_col = ui.color({"UP": "up", "DOWN": "down"}.get(c.daily_trend, "muted"))
    lvl, ckey, _ = S["confidence"]
    style = "Swing · daily candles" if c.interval == "1d" else f"Intraday · {core.TF_SHORT[c.interval]} candles"
    src = c.source + (" · live ticks" if core.ANGEL() and c.is_open else "")
    st.markdown(
        f"<div class='hero2'><div class='hl'><div class='sym'>{ui.esc(c.symbol)}</div>"
        f"<div class='sub'>{ui.esc(name if name != c.symbol else '')}{' · ' if name != c.symbol else ''}{style} · {ui.esc(src)}</div>"
        f"<div class='pills'>{ui.pill(trend_word, trend_col)}{common.conf_badge(lvl, ckey)}</div></div>"
        f"<div class='hr'>" + ui.grid([
            ui.tile("Price", f"₹{c.ltp:,.2f}", f"<span style='color:{ui.signed_color(c.chg)}'>{c.chg:+,.2f} ({c.chg_pct:+.2f}%)</span>"),
            f"<div class='tile'>{ui.range_bar(day_lo, day_hi, c.ltp)}</div>",
            ui.tile("Open · Prev close", f"₹{float(c.raw['Open'][today].iloc[0]):,.0f}", f"prev ₹{c.prev_close:,.2f}"),
            ui.tile("Typical move" if not P.pro else "ATR", f"₹{c.last.ATR:,.2f}", f"{float(c.last.ATR) / c.ltp * 100:.2f}% per candle"),
            ui.tile("Volume", f"{vol / 1e5:,.1f} L" if vol else "—", "today" if vol else "n/a for indices"),
        ]) + "</div></div>", unsafe_allow_html=True)
    if (hs := core.history_status(c.ticker, c.interval)):
        st.caption(f"⏳ Getting 2 years of {c.interval} history from Angel One ({hs}) — using Yahoo's 60 days until it's ready.")


header()


# ---------------------------------------------------------------- signal (refreshes itself)
@st.fragment(run_every=RUN)
def signal_section():
    compute()
    st.markdown(common.signal_card_html(c, S, P, countdown=core.candle_countdown(c)), unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    with b1:
        common.paper_button(c, S)
    with b2:
        if S["kind"] in ("BUY", "SHORT", "HOLD"):
            common.bought_button(c, S)
    if options.underlying_for(c.symbol, c.ticker) and S["kind"] in ("BUY", "SHORT", "HOLD"):
        if st.button(f"See the option to buy for {c.symbol}", icon=":material/stacked_line_chart:", width="stretch", type="tertiary"):
            st.switch_page("views/options_page.py")
    with st.expander("Why this signal — checklist & track record", expanded=P.pro, icon=":material/help:"):
        st.markdown(f"<div class='chips'>{common.checklist_html(c)}</div>"
                    f"<div class='msg'>{common.record_html(c)}</div>"
                    + (f"<div class='note' style='margin-top:8px'>{ui.esc(c.strat.evidence)}</div>" if P.pro else ""),
                    unsafe_allow_html=True)
    # paper / real trades on this symbol close themselves at stop / target
    trades = [t for t in journal.load_trades() if t["status"] == "OPEN" and t["ticker"] == c.ticker]
    for t in journal.auto_close({c.ticker: c.ltp} if trades else {}):
        st.toast(f"{t['symbol']}: {t['exit_reason']} reached — trade closed", icon="📒")
    # a new signal -> one full refresh (chart markers, desktop alert, beep)
    seen = st.session_state.setdefault("last_verdict", {})
    prev = seen.get(c.alert_key)
    seen[c.alert_key] = S["verdict"]
    if prev and prev != S["verdict"] and st.session_state.get("_frag_run"):
        st.session_state["pending_toast"] = f"{c.symbol}: {prev} → {S['verdict']}"
        st.rerun(scope="app")
    st.session_state["_frag_run"] = True


st.session_state["_frag_run"] = False
if (msg := st.session_state.pop("pending_toast", None)):
    st.toast(msg, icon="🔔")

col_chart, col_sig = st.columns([1.8, 1], gap="medium")
with col_sig:   # first, so the chart knows the current signal for alerts
    signal_section()
with col_chart:
    st.iframe(common.chart_html(c, S, P), height=CHART_H + 5)
    st.caption("Hover for the price at any time · scroll to zoom, drag to pan · ▲ BUY / ▼ SHORT = past signals, "
               "● = exits with their result · 🔔 (top right of the chart) turns on desktop alerts.")
