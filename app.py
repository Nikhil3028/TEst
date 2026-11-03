"""Trade Signals India — entry point: theme, broker connections, first-run setup, navigation and the live
market strip shown on every page. The pages live in views/, the logic in core.py.

Run:  .venv/bin/streamlit run app.py
"""
from datetime import datetime

import streamlit as st

import core
import data
import ui
from views.common import run_every

st.set_page_config(page_title="Trade Signals", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
ui.inject_css()

# a click somewhere (a scanner row, a chain row…) can ask for widget values to be set before widgets are drawn
for k, v in (st.session_state.pop("pending", None) or {}).items():
    st.session_state[k] = v

P = core.prefs()
core.brokers()
core.feed_port()

PAGES = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/chart_page.py", title="Chart", icon=":material/candlestick_chart:", url_path="chart"),
    st.Page("views/options_page.py", title="Options", icon=":material/stacked_line_chart:", url_path="options"),
    st.Page("views/trades_page.py", title="Trades", icon=":material/account_balance_wallet:", url_path="trades"),
    st.Page("views/lab.py", title="Strategy Lab", icon=":material/science:", url_path="lab"),
    st.Page("views/settings_page.py", title="Settings", icon=":material/settings:", url_path="settings"),
    st.Page("views/help_page.py", title="Help", icon=":material/help:", url_path="help"),
]


@st.fragment(run_every=run_every(P))
def market_strip():
    is_open, status = core.market()
    quotes = []
    for name in ("NIFTY 50", "BANK NIFTY", "SENSEX", "NIFTY FIN SERVICE", "NIFTY IT"):
        if (q := core.quote(data.INDICES[name])):
            quotes.append((name.replace(" SERVICE", ""), *q))
    if (v := core.quote("^INDIAVIX")):
        quotes.append(("INDIA VIX", *v))
    st.markdown(ui.market_strip(quotes, is_open, status, datetime.now(data.IST).strftime("%H:%M:%S")),
                unsafe_allow_html=True)


if not P.onboarded:
    pg = st.navigation([st.Page("views/welcome.py", title="Welcome", icon=":material/waving_hand:", default=True)],
                       position="hidden")
else:
    pg = st.navigation(PAGES, position="top")
    market_strip()
pg.run()
