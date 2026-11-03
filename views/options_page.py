"""Options: which option to buy for the current signal, the live option chain (OI, PCR, max pain) and the
option's own chart. Live data from Angel One when connected; otherwise a pasted Groww chain or an estimate."""
import dataclasses
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import angel
import chart
import core
import data
import indicators
import journal
import options
import ui
from ui import ACCENT, DOWN, MUTED, UP, WARN
from views import common
from views.common import LINE_COLORS, run_every

P = core.prefs()
SEL = core.selection()
RUN_EVERY = run_every(P)
UP_TXT, DOWN_TXT = ui.up_txt(), ui.down_txt()
auto, is_open = P.live, core.market()[0]
quote, live_feed_port = core.quote, core.feed_port
capital, risk_pct = P.capital, P.risk_pct
_B = core.brokers()
ANGEL, ANGEL_ERR, GROWW, GROWW_ERR = _B.angel, _B.angel_err, _B.groww, _B.groww_err


def bind(c):
    """Expose the analysed underlying under the names the option code below uses."""
    global symbol, ticker, ltp, last, res, sl_atr, target_atr, grade_key, strat_name, params, SWING_DAYS
    symbol, ticker, ltp, last, res = c.symbol, c.ticker, c.ltp, c.last, c.res
    sl_atr, target_atr, grade_key, strat_name, params = c.sl_atr, c.target_atr, c.grade_key, c.strat_name, c.params
    SWING_DAYS = c.swing_days


# ---------------------------------------------------------------- options
PASTED_FILE = options.CACHE.parent / "pasted_chain.csv"


@st.cache_data(ttl=2, show_spinner=False)
def angel_chain(und, expiry, spot):
    return options.from_angel(ANGEL, und, expiry, spot)


@st.cache_data(ttl=5, show_spinner=False)
def groww_chain(und, exch, expiry):
    return options.from_groww(GROWW, und, exch, expiry)


def pretty_expiry(e):
    d = pd.Timestamp(e)
    left = (d.date() - datetime.now(data.IST).date()).days
    return f"{d.day} {d:%b} " + ("(today)" if left == 0 else f"({left}d)")


def fmt_oi(v):
    return "—" if pd.isna(v) else f"{v / 1e5:,.1f}L" if abs(v) >= 1e5 else f"{v:,.0f}"


def underlying_signal():
    """(kind 'CE'/'PE'/None, label, idx_stop, idx_target) from the current strategy on the underlying."""
    atr_v = float(last.ATR)
    t = res.open_trade
    if res.pending in ("BUY", "SELL"):
        d = 1 if res.pending == "BUY" else -1
        return ("CE" if d == 1 else "PE", res.pending, ltp - d * (sl_atr or 2.0) * atr_v,
                ltp + d * target_atr * atr_v if target_atr else None)
    if t and res.pending != "EXIT":
        d = 1 if t.side == "LONG" else -1
        stop = t.stop if abs(t.stop) < 1e12 else ltp - d * 2 * atr_v
        return ("CE" if d == 1 else "PE", "HOLD " + t.side, stop, t.target if abs(t.target) < 1e12 else None)
    return None, ("EXIT" if res.pending == "EXIT" else "WAIT"), None, None


@st.fragment(run_every=RUN_EVERY)
def option_tab():
    """Re-runs on its own while the market is open so premiums and OI stay live."""
    bind(core.build(OSEL, P))
    try:
        und = options.underlying_for(symbol.upper(), ticker)
    except Exception as e:  # noqa: BLE001 — instrument list download failed
        st.error(f"Couldn't load the list of option contracts: {e}")
        return
    if not und:
        st.info(f"No options are listed for **{symbol.upper()}**. Options trade on NIFTY, BANK NIFTY, FIN NIFTY, SENSEX "
                "and about 200 F&O stocks (e.g. RELIANCE, HDFCBANK, SBIN). Pick one of those above.")
        return
    u, exch = und
    exps = options.expiries(u, exch)
    if not exps:
        st.warning("No upcoming expiries found.")
        return

    sources = (["Angel One (live)"] if ANGEL else []) + (["Groww API (live)"] if GROWW else []) + ["Pasted from Groww", "Estimate (India VIX)"]
    pasted_text = st.session_state.get("pasted_text") or (PASTED_FILE.read_text() if PASTED_FILE.exists() else "")
    c1, c2, c3 = st.columns([1.3, 2.2, 1])
    expiry = c1.selectbox("Expiry", exps[:10], index=options.default_expiry(exps, SWING_DAYS), format_func=pretty_expiry, key=f"exp-{u}-{SWING_DAYS}")
    pasted_for = pasted_text.split("underlying=", 1)[1].split(",", 1)[0].strip().upper() if "underlying=" in pasted_text else ""
    default_src = sources[0] if (ANGEL or GROWW) else ("Pasted from Groww" if pasted_for == u else "Estimate (India VIX)")
    src = c2.segmented_control("Option prices from", sources, key=f"src-{u}",
                              default=None if f"src-{u}" in st.session_state else default_src) or default_src
    lot = options.lot_size(u, exch, expiry)
    c3.markdown(ui.tile("Lot size", f"{lot:,}", f"{u} · {exch}"), unsafe_allow_html=True)

    chain, spot = None, ltp
    try:
        if src.startswith("Angel"):
            chain = angel_chain(u, expiry, ltp)
        elif src.startswith("Groww"):
            chain = groww_chain(u, exch, expiry)
            spot = chain.spot if pd.notna(chain.spot) else ltp
        elif src.startswith("Pasted"):
            if pasted_text:
                chain = options.from_csv(pasted_text)
                if chain.underlying and chain.underlying != u:
                    st.warning(f"The pasted chain is for **{chain.underlying}**, not {u}. Paste a new one below.")
                    chain = None
                elif chain.expiry and chain.expiry != expiry:
                    st.warning(f"The pasted chain is for expiry **{chain.expiry}** — select that expiry or paste a new one.")
                    chain = None
        else:
            vq = quote("^INDIAVIX")
            iv = vq[0] if vq else 15.0
            ks = [k for k in options.strikes(u, exch, expiry) if abs(k / ltp - 1) < 0.06]
            chain = options.estimate(u, expiry, ltp, iv, ks)
    except Exception as e:  # noqa: BLE001
        st.error(f"Couldn't get the option chain: {e}")

    if expiry == datetime.now(data.IST).date().isoformat():
        st.warning("⚠️ **Expiry day.** Premiums of this expiry lose value very fast (especially after 1 PM) and can go to zero. "
                   "Beginners should trade the next expiry.")

    if chain is None or chain.table.empty:
        st.info("No option prices yet. Paste a chain from the Groww page below, switch to **Estimate**, or connect the Groww API.")
    else:
        an = options.analytics(chain, spot)
        kind, label, idx_stop, idx_tgt = underlying_signal()
        live_note = {"angel": f"Live from Angel One · {chain.as_of}", "groww": f"Live from Groww API · {chain.as_of}", "pasted": f"Pasted snapshot · captured {chain.as_of}",
                     "estimate": f"Estimated (Black-Scholes from India VIX) · {chain.as_of}"}[chain.source]

        # ---- option signal
        tiles, msg, paper_opt = [], "", None
        if kind:
            pl = options.plan(chain, kind, spot, idx_stop, idx_tgt, lot, capital, risk_pct)
            name = options.display_name(u, expiry, an["atm"], kind)
            if grade_key == "bad":
                verdict, color = "SKIP", MUTED
                msg = (f"The {strat_name} signal on {symbol.upper()} says <b>{label}</b>, but this strategy hasn't worked on this "
                       "chart in the past — skipping is safer.")
            else:
                verdict = ("BUY " if label in ("BUY", "SELL") else "HOLD ") + name
                color = UP_TXT if kind == "CE" else DOWN_TXT
                msg = (f"{symbol.upper()} signal: <b>{label}</b> ({ui.esc(strat_name)}) → "
                       f"{'buy a CALL (profits if it rises)' if kind == 'CE' else 'buy a PUT (profits if it falls)'}.")
                bd = an.get("bias_dir", 0)
                if bd and bd != (1 if kind == "CE" else -1):
                    msg += f"<br>⚠️ Option-chain OI disagrees: <b>{an['bias']}</b> (PCR {an['pcr']:.2f}). Consider skipping or half size."
                elif bd:
                    msg += f"<br>✅ OI agrees: {an['bias']} (PCR {an['pcr']:.2f})."
            if pl and grade_key != "bad":
                buy_now = label in ("BUY", "SELL")
                if buy_now and pl["lots"] == 0:
                    first = (f"<b>Skip this option trade</b> — even 1 lot of {name} risks more than your {risk_pct}% limit. "
                             "Use the stock / ETF plan on the main card instead, or trade smaller instruments.")
                elif buy_now:
                    first = f"<b>BUY {name}</b> now at about <b>₹{pl['premium']:,.2f}</b> — {pl['lots']} lot(s) = {pl['qty']:,} qty."
                else:
                    first = f"Bought <b>{name}</b> on the earlier signal? <b>Keep holding.</b> Didn't buy? Don't chase — wait for the next signal."
                o_steps = [first] if buy_now and pl["lots"] == 0 else [first,
                           f"Place a <b>stop-loss SELL order at ₹{pl['stop']:,.2f}</b> on Groww right after buying.",
                           f"<b>SELL to book profit at ₹{pl['target']:,.2f}</b> — or earlier if the {symbol.upper()} card turns SELL.",
                           ("Intraday: SELL by 3:15 PM." if params.intraday else
                            "Swing trade: hold until the card says SELL, but exit at least 3 days before this option's expiry "
                            "(time decay speeds up at the end).")]
                if not params.intraday:
                    msg += ("<br>ℹ️ Swing signals last days to weeks, and options lose value every day — the app picks an expiry "
                            "3+ weeks away. The ETF / stock is simpler for swing trades.")
                msg += f"<div class='steps'><div class='l'>What to do now</div><ol>{''.join(f'<li>{x}</li>' for x in o_steps)}</ol></div>"
            if pl and grade_key != "bad" and label in ("BUY", "SELL") and pl["lots"] > 0 and ANGEL:
                tok = angel.option_token(u, expiry, pl["strike"], kind)
                if tok:
                    paper_opt = {"name": name, "ticker": f"OPT:{tok[0]}:{tok[1]}", "qty": pl["qty"], "entry": pl["premium"],
                                 "stop": pl["stop"], "target": pl["target"]}
            if pl:
                c = options.contract(u, exch, expiry, pl["strike"], kind)
                lots_txt = f"{pl['lots']} lot{'s' if pl['lots'] != 1 else ''}"
                tiles = [ui.tile("Premium ≈" if chain.source == "estimate" else "Premium", f"₹{pl['premium']:,.2f}", f"delta {pl['delta']:.2f}"),
                         ui.tile("Stop-loss", f"₹{pl['stop']:,.2f}", f"{(pl['stop'] / pl['premium'] - 1) * 100:+.0f}%", DOWN_TXT),
                         ui.tile("Target", f"₹{pl['target']:,.2f}", f"{(pl['target'] / pl['premium'] - 1) * 100:+.0f}%", UP_TXT),
                         ui.tile("Quantity", lots_txt, f"{pl['qty']:,} qty · ₹{pl['cost']:,.0f}")]
                one_lot_risk = (pl["premium"] - pl["stop"]) * lot
                if pl["lots"] == 0:
                    msg += (f"<br>⚠️ Even 1 lot risks <b>₹{one_lot_risk:,.0f}</b> ({one_lot_risk / capital * 100:.1f}% of your capital, "
                            f"needs ₹{pl['premium'] * lot:,.0f}) — above your {risk_pct}% risk limit. Skip, or raise capital/risk knowingly.")
                else:
                    tiles.append(ui.tile("Max loss", f"₹{pl['max_loss']:,.0f}", f"{pl['max_loss'] / capital * 100:.1f}% of capital"))
                if c:
                    msg += f"<br>Search on Groww: <b>{ui.esc(name)}</b> · symbol <code>{ui.esc(c['trading_symbol'])}</code>"
                msg += (f"<br><span class='note'>Stop/target are premium levels ≈ the {symbol.upper()} stop "
                        f"₹{idx_stop:,.2f} × delta. Exit the option when {symbol.upper()} hits its stop, whichever comes first.</span>")
        else:
            verdict, color = ("SELL your options (exit)" if label == "EXIT" else "WAIT"), (WARN if label == "EXIT" else MUTED)
            msg = (f"{symbol.upper()} signal is <b>{label}</b> ({ui.esc(strat_name)}). "
                   + ("Exit any option bought on the last signal." if label == "EXIT" else
                      "No option trade now — a BUY signal means buy a CALL, a SHORT signal means buy a PUT."))
            row = chain.table[chain.table.strike == an["atm"]]
            if len(row):
                r0 = row.iloc[0]
                tiles = [ui.tile(f"{an['atm']:g} CE", f"₹{r0.ce_ltp:,.2f}" if pd.notna(r0.ce_ltp) else "—", "at-the-money call"),
                         ui.tile(f"{an['atm']:g} PE", f"₹{r0.pe_ltp:,.2f}" if pd.notna(r0.pe_ltp) else "—", "at-the-money put")]
        st.markdown(f"<div class='card' style='border-color:{color}88;box-shadow:inset 4px 0 0 {color};margin-top:6px'>"
                    f"<h4>Option signal · {ui.esc(live_note)}</h4><div class='verdict' style='color:{color};font-size:30px'>{ui.esc(verdict)}</div>"
                    f"{ui.grid(tiles) if tiles else ''}<div class='msg'>{msg}</div></div>", unsafe_allow_html=True)
        if paper_opt and st.button(f"📝 Paper-trade {paper_opt['name']} ({paper_opt['qty']:,} qty @ ₹{paper_opt['entry']:,.2f})",
                                   type="primary", key=f"ppt-{paper_opt['ticker']}"):
            journal.add_trade(paper_opt["name"], paper_opt["ticker"], "LONG", paper_opt["qty"], paper_opt["entry"],
                              paper_opt["stop"], paper_opt["target"], f"{strat_name} (option)")
            st.toast(f"Paper trade added: {paper_opt['name']} × {paper_opt['qty']:,}", icon="📝")
        for n in chain.notes:
            st.caption("ℹ️ " + n)
        st.write("")

        # ---- OI analytics
        at = [ui.tile("Spot", f"₹{spot:,.2f}"), ui.tile("ATM strike", f"{an['atm']:g}")]
        if "pcr" in an:
            at += [ui.tile("PCR (OI)", f"{an['pcr']:.2f}", an["bias"], UP_TXT if an["bias_dir"] > 0 else DOWN_TXT if an["bias_dir"] < 0 else None),
                   ui.tile("Max pain", f"{an['max_pain']:g}", "expiry magnet level"),
                   ui.tile("Support", f"{an['support']:g}", "highest put OI", UP_TXT),
                   ui.tile("Resistance", f"{an['resistance']:g}", "highest call OI", DOWN_TXT)]
        if pd.notna(an.get("atm_iv", np.nan)):
            at.append(ui.tile("ATM IV", f"{an['atm_iv']:.1f}%"))
        st.markdown(ui.grid(at), unsafe_allow_html=True)
        if "pcr" not in an:
            st.caption("PCR, max pain and support/resistance need open-interest data — available with the Groww API or a pasted chain.")

        # ---- chain table (Groww layout: calls | strike | puts)
        t = chain.table
        i_atm = int((t.strike - spot).abs().argmin())
        view = t.iloc[max(i_atm - 10, 0): i_atm + 11]
        tbl = pd.DataFrame({
            "CE OI": view.ce_oi / 1e5, "CE OI chg": view.ce_oi_change.map(fmt_oi),
            "CE Δ": view.ce_delta.map(lambda v: "—" if pd.isna(v) else f"{v:.2f}"),
            "CE LTP": view.ce_ltp.map(lambda v: "—" if pd.isna(v) else f"{v:,.2f}"),
            "Strike": view.strike.map(lambda v: f"{v:g}"),
            "PE LTP": view.pe_ltp.map(lambda v: "—" if pd.isna(v) else f"{v:,.2f}"),
            "PE Δ": view.pe_delta.map(lambda v: "—" if pd.isna(v) else f"{v:.2f}"),
            "PE OI chg": view.pe_oi_change.map(fmt_oi), "PE OI": view.pe_oi / 1e5,
        }).reset_index(drop=True)
        tbl = tbl[[c for c in tbl.columns if not ((tbl[c] == "—").all() or tbl[c].isna().all())]]
        oi_max = float(np.nanmax(tbl[[c for c in ("CE OI", "PE OI") if c in tbl]].to_numpy())) if {"CE OI", "PE OI"} & set(tbl) else 0
        oi_cfg = {c: st.column_config.ProgressColumn(c, format="%.1fL", min_value=0, max_value=max(oi_max, 1e-9))
                  for c in ("CE OI", "PE OI") if c in tbl}
        strikes_v = view.strike.to_numpy()

        def shade(row):
            k = strikes_v[row.name]
            out = []
            for col in row.index:
                css = ""
                if col.startswith("CE") and k < spot or col.startswith("PE") and k > spot:
                    css = "background-color: rgba(250,178,25,0.07)"   # in-the-money
                if col == "Strike":
                    css = "font-weight:700; text-align:center"
                if k == an["atm"]:
                    css += "; background-color: rgba(57,135,229,0.22); font-weight:700"
                out.append(css)
            return out
        st.markdown(f"##### Option chain · {pretty_expiry(expiry)}")
        ev = st.dataframe(tbl.style.apply(shade, axis=1), width="stretch", hide_index=True, height=min(38 * len(tbl) + 40, 820),
                          column_config=oi_cfg, on_select="rerun", selection_mode="single-row", key=f"chain_sel-{u}-{expiry}")
        sel = ev.selection.rows
        if sel and st.session_state.get("chain_handled") != (u, expiry, sel[0]):
            st.session_state["chain_handled"] = (u, expiry, sel[0])
            st.session_state["pending"] = {f"ocs-{u}-{expiry}": float(strikes_v[sel[0]])}
            st.rerun(scope="app")
        st.caption("Blue row = at-the-money · shaded = in-the-money · bars = open interest (L = lakh) · click a row to chart that strike")

        if chain.has_oi:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=view.strike, y=view.ce_oi, name="Call OI (resistance)", marker_color=DOWN))
            fig.add_trace(go.Bar(x=view.strike, y=view.pe_oi, name="Put OI (support)", marker_color=UP))
            fig.add_vline(x=spot, line=dict(color=ACCENT, dash="dot"), annotation_text=f"Spot {spot:,.0f}", annotation_font_color=ACCENT)
            fig.update_layout(**ui.plotly_layout(320, barmode="group", bargap=0.25, legend=dict(orientation="h", y=1.1),
                                                 hovermode="x unified", xaxis=dict(title="Strike", showgrid=False),
                                                 yaxis=dict(gridcolor=ui.GRID, side="right")))
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

    # ---- data sources
    with st.expander("📋 Paste an option chain from the Groww page (via the Claude browser extension)"):
        st.markdown("Open the option chain on Groww, run the extraction prompt in the Claude extension, then paste its CSV here.")
        txt = st.text_area("Option chain CSV", pasted_text, height=180, key="paste_box",
                           placeholder="#underlying=NIFTY,spot=23610,expiry=2026-11-09,captured_at=...\nstrike,ce_ltp,...")
        if st.button("Use this chain", type="primary"):
            try:
                ch = options.from_csv(txt)
                st.session_state["pasted_text"] = txt
                PASTED_FILE.parent.mkdir(exist_ok=True)
                PASTED_FILE.write_text(txt)
                pend = {f"src-{u}": "Pasted from Groww"}
                if ch.expiry in exps:
                    pend[f"exp-{u}-{SWING_DAYS}"] = ch.expiry
                st.session_state["pending"] = pend
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Couldn't read that CSV: {e}")
    with st.expander("🔌 Connect Angel One (free) for live ticks & option chain" + (" — ✅ connected" if ANGEL else "")):
        if ANGEL_ERR:
            st.error(f"Angel One login failed: {ANGEL_ERR}")
        if ANGEL and ANGEL.last_error:
            st.caption(f"Last stream message: {ANGEL.last_error}")
        st.markdown(f"""
Create the file `{(core.HERE / '.streamlit' / 'secrets.toml')}` with:
```toml
[angelone]
api_key = "your-smartapi-key"
client_id = "A123456"
mpin = "1234"
totp_secret = "YOUR-TOTP-TEXT-KEY"
```
then restart the app. Used for market data only — the app never places orders. Keep this file private.
""")
    with st.expander("🔌 Connect the Groww API for live option prices" + (" — ✅ connected" if GROWW else "")):
        if GROWW_ERR:
            st.error(f"Groww login failed: {GROWW_ERR}")
        st.markdown(f"""
With a Groww **Trading API subscription** the option chain, Greeks and the index price come live from Groww.

1. On Groww open **Groww Cloud → API Keys** and create a **TOTP token** (it doesn't need daily approval). Copy the *token* and the *secret*.
2. Create the file `{(core.HERE / '.streamlit' / 'secrets.toml')}` with:
```toml
[groww]
totp_token = "paste-your-totp-token"
totp_secret = "paste-your-totp-secret"
```
3. Restart the app. This file stays on your computer — never share it or upload it anywhere.
""")


@st.cache_data(ttl=60, show_spinner=False)
def option_candles(seg, token, iv):
    return ANGEL.candles(seg, token, iv)


def option_chart_section():
    """Groww-style chart of one option contract's premium, with live ticks."""
    try:
        und = options.underlying_for(symbol.upper(), ticker)
    except Exception:  # noqa: BLE001
        return
    if not und:
        return
    u, exch = und
    st.markdown("#### 📈 Option chart")
    if not ANGEL:
        st.info("Option charts need live data — connect Angel One (see the 🔌 section above).")
        return
    exps = options.expiries(u, exch)
    expiry = st.session_state.get(f"exp-{u}-{SWING_DAYS}") or exps[options.default_expiry(exps, SWING_DAYS)]
    ks = np.sort(angel.options_of(u, expiry).strike.unique())
    if not len(ks):
        st.warning("No contracts found for this expiry.")
        return
    i_atm = int(np.abs(ks - ltp).argmin())
    near = [float(k) for k in ks[max(i_atm - 15, 0): i_atm + 16]]
    atm = float(ks[i_atm])
    kind_sig, label, idx_stop, idx_tgt = underlying_signal()
    c1, c2, c3 = st.columns([1.4, 1, 1.6])
    skey = f"ocs-{u}-{expiry}"
    if st.session_state.get(skey) not in near:
        st.session_state.pop(skey, None)
    k = c1.selectbox("Strike", near, index=near.index(atm), key=skey,
                     format_func=lambda x: f"{x:g}" + ("  (ATM)" if x == atm else ""))
    kind = c2.segmented_control("Type", ["CE", "PE"], default=kind_sig or "CE", key=f"ock-{u}") or (kind_sig or "CE")
    iv = c3.segmented_control("Candles", ["1m", "5m", "15m", "1h"], default="5m", key="oci") or "5m"
    tok = angel.option_token(u, expiry, k, kind)
    if not tok:
        st.warning("Contract not found.")
        return
    seg, token, _ = tok
    name = options.display_name(u, expiry, k, kind)
    try:
        raw_o = option_candles(seg, token, iv)
    except Exception as e:  # noqa: BLE001
        busy = "exceeding" in str(e) or "rate" in str(e).lower()
        st.warning(f"Angel One is limiting how often history can be downloaded — the {name} chart will load on the next refresh."
                   if busy else f"Couldn't load candles for {name}: {e}")
        return
    if raw_o.empty:
        st.info(f"No trades yet in {name}." + (f" ({ANGEL.last_error})" if ANGEL.last_error else ""))
        return
    od = indicators.add_all(raw_o)
    days = od.index.date
    prev = od.Close[days < days[-1]]
    prev_close_o = float(prev.iloc[-1]) if len(prev) else float(od.Open.iloc[0])

    # entry / stop / target lines when this is the contract the signal points to
    lines = []
    if kind_sig == kind and grade_key != "bad":
        delta = ANGEL.greeks(u, expiry).get((k, kind), {}).get("delta")
        row = {"strike": k, f"{kind.lower()}_ltp": float(od.Close.iloc[-1]), f"{kind.lower()}_delta": delta}
        one = options.Chain(u, expiry, ltp, pd.DataFrame([row]).reindex(columns=options.CHAIN_COLS), "angel", "")
        pl = options.plan(one, kind, ltp, idx_stop, idx_tgt, options.lot_size(u, exch, expiry), capital, risk_pct, strike=k)
        if pl:
            lines = [{"price": round(pl["premium"], 2), "color": ACCENT, "title": "Entry"},
                     {"price": pl["stop"], "color": DOWN, "title": "SL"},
                     {"price": pl["target"], "color": UP, "title": "Target"}]
    st.markdown(f"<div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:4px 0 6px'>"
                f"<span style='font-size:20px;font-weight:700'>{ui.esc(name)}</span>"
                f"{ui.pill(label if kind_sig == kind else 'No signal on this contract', UP_TXT if kind_sig == kind else MUTED)}"
                f"<span class='note'>{ui.esc(tok[2])}</span></div>", unsafe_allow_html=True)
    port = live_feed_port()
    html = chart.build_html(
        od, symbol=name, intraday=True, prev_close=prev_close_o,
        overlays=[{"name": "EMA 9", "col": "EMA_fast", "color": LINE_COLORS[0]},
                  {"name": "EMA 21", "col": "EMA_slow", "color": LINE_COLORS[1]},
                  {"name": "VWAP", "col": "VWAP", "color": "#d55181"}],
        default_overlays=["VWAP", "EMA 9"],
        panes=[{"name": "RSI", "lines": [{"col": "RSI", "color": LINE_COLORS[1]}], "levels": [70, 30]},
               {"name": "MACD", "hist": "MACD_hist", "lines": [{"col": "MACD", "color": LINE_COLORS[0]}, {"col": "MACD_signal", "color": LINE_COLORS[2]}]}],
        markers=[], price_lines=lines, up=UP, down=DOWN, accent=ACCENT, bg="transparent", store_key="tsi-opt-", height=600,
        live={"url": f"/bars?seg={seg}&token={token}&interval={iv}", "every": 5,
              "stream": f"/stream?seg={seg}&token={token}",
              "ivSec": {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[iv], "port": port, "base": core.FEED_BASE}
        if auto and is_open else None)
    st.iframe(html, height=605)
    st.caption("Premium chart from Angel One · live ticks while the market is open · dashed lines = entry / stop / target "
               "when the current signal points to this contract. Click a row in the chain above to chart that strike.")



# ---------------------------------------------------------------- page
ui.page_header("Options", "The option to buy for the current signal, the live option chain and the option's own chart.")
und_all = common.options_underlyings()
start = SEL.symbol if SEL.symbol in und_all else "NIFTY 50"   # no options on this one -> show NIFTY, keep the Chart as is
OSEL = dataclasses.replace(SEL, symbol=start)
t1, t2 = st.columns([2.6, 2.4], vertical_alignment="center")
with t1:
    picked = common.symbol_picker(start, key="opt-search", options_only=True)
with t2:
    common.timeframe_picker(SEL, key="opt-tf")
if picked != start:   # the user picked another underlying here -> the Chart page follows
    core.select(picked, exchange="NSE")
    st.rerun()
with st.spinner(f"Analysing {start}…"):
    _c = core.build(OSEL, P)
if SEL.symbol != start:
    st.caption(f"{SEL.symbol} has no options, so this shows {start}. Pick another underlying above.")
if _c is None:
    st.error(f"No price data for {start}.")
    st.stop()
bind(_c)
option_tab()
option_chart_section()
