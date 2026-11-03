"""First-run setup: four questions, then the app is ready."""
import streamlit as st

import core
import ui

P = core.prefs()

left, mid, right = st.columns([1, 2.2, 1])
with mid:
    st.markdown("<div style='text-align:center;margin-top:10px'><div style='font-size:46px'>📈</div>"
                "<h1 style='margin:6px 0 4px'>Welcome to Trade Signals</h1>"
                "<div class='muted' style='font-size:16px'>Clear BUY / SELL signals for the Indian market — tested on years of "
                "data, with the exact steps to follow on Groww.</div></div>", unsafe_allow_html=True)
    st.write("")
    st.markdown(ui.grid([
        ui.tile("1 · Signals", "BUY · SELL · WAIT", "for your watchlist, every day"),
        ui.tile("2 · Plan", "Stop & target", "quantity sized to your risk"),
        ui.tile("3 · Proof", "Tested first", "only trusted when it worked before"),
    ]), unsafe_allow_html=True)
    st.write("")
    with st.form("setup", border=True):
        st.markdown("##### Set up in 30 seconds")
        name = st.text_input("Your name (optional)", P.name, placeholder="e.g. Nikhil")
        capital = st.number_input("How much money will you trade with? (₹)", 1_000, 1_000_000_000, int(P.capital), 10_000,
                                  help="Used only to work out how many shares to buy. It never leaves your computer.")
        risk = st.select_slider("How much are you OK losing on ONE trade, if it goes wrong?",
                                options=[0.5, 1.0, 1.5, 2.0, 3.0], value=P.risk_pct,
                                format_func=lambda v: f"{v:g}% of capital",
                                help="Professionals risk 1–2%. The app sizes every trade so a stop-loss costs about this much.")
        style = st.radio("How do you want to trade?", ["Swing", "Intraday"], index=0 if P.style == "Swing" else 1,
                         captions=["Hold for days to weeks — checked once a day. Recommended: this is what held up in testing.",
                                   "Buy and sell the same day. Needs you at the screen; much harder to profit after charges."])
        kinds = st.multiselect("What do you want signals for?", list(core.WATCHLIST_PRESETS),
                               default=["Index options", "Large-cap stocks"],
                               help="This builds your starting watchlist — you can change it any time in Settings.")
        simple = st.toggle("Keep it simple (plain words, fewer numbers)", value=not P.pro,
                           help="Turn off for Pro view: strategy choice, indicators and full backtests.")
        go = st.form_submit_button("Start", type="primary", icon=":material/rocket_launch:", width="stretch")
    st.caption("Signals are based on past price patterns. They are not investment advice, and past results don't guarantee "
               "future ones. Practise with paper trades first.")

if go:
    wl = []
    for k in kinds or ["Index options"]:
        wl += [s for s in core.WATCHLIST_PRESETS[k] if s not in wl]
    core.update_prefs(name=name.strip(), capital=float(capital), risk_pct=float(risk), style=style,
                      mode="simple" if simple else "pro", watchlist=wl, onboarded=True)
    st.session_state.pop("sel", None)
    st.session_state.pop("board", None)
    st.rerun()
