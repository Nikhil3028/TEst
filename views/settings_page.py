"""Settings: profile & risk, watchlist, live updates & alerts, data connections, advanced. Saved in profile.json."""
from pathlib import Path

import streamlit as st

import angel
import core
import store
import ui

P = core.prefs()
B = core.brokers()
ui.page_header("Settings", f"Your settings and trades are saved on {store.backend()}.")
if store.temporary():
    st.warning(store.TEMPORARY_NOTE, icon=":material/warning:")

tab_p, tab_w, tab_l, tab_d, tab_a = st.tabs(["Profile & risk", "Watchlist", "Live updates & alerts", "Data connections", "Advanced"])

with tab_p:
    with st.form("profile"):
        name = st.text_input("Your name", P.name)
        a, b = st.columns(2)
        capital = a.number_input("Trading capital (₹)", 1_000, 1_000_000_000, int(P.capital), 10_000,
                                 help="Used only to size each trade. Saved privately with your settings.")
        risk = b.select_slider("Risk per trade", options=[0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0], value=P.risk_pct,
                               format_func=lambda v: f"{v:g}%",
                               help="How much of your capital one losing trade may cost. 1–2% is the professional norm.")
        st.caption(f"With these settings one stopped-out trade costs about **₹{P.capital * P.risk_pct / 100:,.0f}** "
                   "(updates after you save).")
        style = st.radio("Trading style", ["Swing", "Intraday"], index=0 if P.style == "Swing" else 1, horizontal=True,
                         captions=["days to weeks · recommended", "same day · harder after charges"])
        mode = st.radio("View", ["simple", "pro"], index=0 if not P.pro else 1, horizontal=True,
                        format_func={"simple": "Simple — plain words", "pro": "Pro — strategies, indicators, full numbers"}.get)
        if st.form_submit_button("Save", type="primary", icon=":material/save:"):
            changed_style = style != P.style
            core.update_prefs(name=name.strip(), capital=float(capital), risk_pct=float(risk), style=style, mode=mode)
            if changed_style:
                core.selection().interval = core.STYLE_INTERVALS[style][0]
            st.session_state.pop("board", None)
            st.toast("Saved", icon="✅")
            st.rerun()

with tab_w:
    u = core.universe()
    label_of = dict(zip(u.symbol, u.label))
    sym_of = dict(zip(u.label, u.symbol))
    current = [label_of.get(s, s) for s in P.watchlist]
    choices = list(u.label) + [x for x in current if x not in label_of.values()]   # keep symbols added by hand
    picked = st.multiselect("Your watchlist (shown on Home, in this order)", choices, default=current,
                            placeholder="Search stocks or indices…", help="Type a symbol or company name to add it.")
    st.caption("Quick add:")
    cols = st.columns(len(core.WATCHLIST_PRESETS))
    for col, (k, syms) in zip(cols, core.WATCHLIST_PRESETS.items()):
        if col.button(f"+ {k}", width="stretch", key=f"preset-{k}"):
            core.update_prefs(watchlist=P.watchlist + [s for s in syms if s not in P.watchlist])
            st.session_state.pop("board", None)
            st.rerun()
    new = [sym_of.get(x, x) for x in picked]
    if new != P.watchlist and st.button("Save watchlist", type="primary", icon=":material/save:"):
        core.update_prefs(watchlist=new)
        st.session_state.pop("board", None)
        st.toast("Watchlist saved", icon="⭐")
        st.rerun()

with tab_l:
    live = st.toggle("Live updates while the market is open", P.live,
                     help="Prices, signals and the option chain refresh by themselves — no page reloads.")
    refresh = st.select_slider("Refresh signals every", options=[5, 10, 15, 30, 60], value=P.refresh,
                               format_func=lambda s: f"{s} seconds", disabled=not live)
    closed = st.toggle("Decide signals only on completed candles (recommended)", P.closed_only,
                       help="Stops signals that appear and then vanish halfway through a candle.")
    if (live, refresh, closed) != (P.live, P.refresh, P.closed_only):
        core.update_prefs(live=live, refresh=refresh, closed_only=closed)
        st.rerun()
    st.markdown("##### Alerts")
    st.markdown("""
- **On screen:** a pop-up appears whenever a signal changes (Home page and Chart page).
- **Desktop notifications:** on the Chart page, click the **🔕** bell at the top right of the chart once and allow
  notifications — you'll then get a notification and a beep even when this tab is in the background.
- **Light / dark theme:** open the **⋮** menu (top right of the page) → *Settings* → *Choose app theme*.
""")

with tab_d:
    st.markdown("##### Angel One — live ticks, live option chain, 2 years of intraday history (free)")
    if B.angel:
        a = B.angel
        st.success(f"Connected · tick stream {'live' if a.connected else 'connecting…'} · {len(a.subscribed)} instruments subscribed",
                   icon=":material/check_circle:")
        cached = sorted(Path(angel.HIST_DIR).glob("*.pkl")) if Path(angel.HIST_DIR).exists() else []
        if cached:
            st.caption(f"Intraday history cached for {len(cached)} chart(s) · "
                       f"{sum(p.stat().st_size for p in cached) / 1e6:.1f} MB in .cache/candles")
        jobs = {k: v for k, v in a.hist_jobs.items() if not v.startswith("done")}
        if jobs:
            st.caption("Downloading: " + ", ".join(f"{k[1]} {k[2]} ({v})" for k, v in jobs.items()))
        if a.last_error:
            st.caption(f"Last message from Angel One: {a.last_error}")
    elif B.angel_err:
        st.error(f"Angel One login failed: {B.angel_err}", icon=":material/error:")
    else:
        st.info("Not connected — prices come from Yahoo Finance (about 10 seconds late, 60 days of intraday history).",
                icon=":material/info:")
    with st.expander("How to connect Angel One"):
        st.markdown(f"""
1. Open a free Angel One account, then create an app at **smartapi.angelone.in** → *My Apps* (type *Trading APIs*;
   any website as redirect URL, e.g. `https://www.google.com`; your current internet IP as the static IP).
2. Turn on TOTP at **smartapi.angelone.in/enable-totp** and copy the text key under the QR code.
3. Create `{core.HERE / '.streamlit' / 'secrets.toml'}` containing:
```toml
[angelone]
api_key = "your-smartapi-key"
client_id = "A123456"
mpin = "1234"
totp_secret = "YOUR-TOTP-TEXT-KEY"
```
4. Restart the app. The app only reads market data — it never places orders. Keep this file private.

**Using the online version (Streamlit Community Cloud)?** Paste the same lines into the app's **Settings → Secrets**
on share.streamlit.io instead of creating the file.
""")
    st.markdown("##### Groww Trade API (paid) — live option chain")
    if B.groww:
        st.success("Connected", icon=":material/check_circle:")
    elif B.groww_err:
        st.error(f"Groww login failed: {B.groww_err}")
    else:
        st.caption("Not connected (optional). Add a `[groww]` section with `totp_token` and `totp_secret` to secrets.toml.")

with tab_a:
    st.markdown("##### Charges used in every backtest")
    a, b = st.columns(2)
    ci = a.number_input("Intraday, % per side", 0.0, 1.0, P.cost_intraday, 0.01)
    cd = b.number_input("Delivery / swing, % per side", 0.0, 1.0, P.cost_delivery, 0.01)
    st.markdown("##### Indicator settings" + ("" if P.pro else " (Pro)"))
    cols = st.columns(5)
    fast = cols[0].number_input("EMA fast", 3, 50, P.fast)
    slow = cols[1].number_input("EMA slow", 5, 100, P.slow)
    trend = cols[2].number_input("EMA trend", 20, 300, P.trend)
    st_p = cols[3].number_input("Supertrend period", 5, 30, P.st_p)
    st_m = cols[4].number_input("Supertrend mult", 1.0, 6.0, float(P.st_m), 0.5)
    if st.button("Save advanced settings", icon=":material/save:"):
        core.update_prefs(cost_intraday=ci, cost_delivery=cd, fast=fast, slow=slow, trend=trend, st_p=st_p, st_m=st_m)
        st.session_state.pop("board", None)
        st.toast("Saved", icon="✅")
        st.rerun()
    st.divider()
    if st.button("Run the welcome setup again", icon=":material/restart_alt:"):
        core.update_prefs(onboarded=False)
        st.rerun()
