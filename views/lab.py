"""Strategy Lab: the numbers behind the signals — backtest, compare strategies, scan the watchlist."""
import pandas as pd
import streamlit as st

import core
import strategy
import ui
from views import common

P = core.prefs()
sel = core.selection()
ui.page_header("Strategy Lab", "Backtests, strategy comparisons and watchlist scans — every number after charges, "
               "entries at the next candle's open (no peeking ahead).")

t1, t2, t3 = st.columns([2.4, 2.2, 2], vertical_alignment="center")
with t1:
    picked = common.symbol_picker(sel.symbol, key="lab-search")
with t2:
    common.timeframe_picker(sel, key="lab-tf")
with t3:
    common.strategy_controls(sel, key="lab")
if picked != sel.symbol:
    core.select(picked, exchange="NSE")
    st.rerun()

with st.spinner(f"Backtesting {sel.symbol}…"):
    c = core.build(sel, P)
if c is None:
    st.error(f"No price data for {sel.symbol}.")
    st.stop()
SIGNAL_WORD = {"BUY": "🟢 BUY", "SELL": "🔴 SHORT", "EXIT": "🟠 SELL", "HOLD LONG": "🟢 HOLD", "HOLD SHORT": "🔴 HOLD SHORT", "WAIT": "⚪ WAIT"}

tab_bt, tab_cmp, tab_scan = st.tabs(["Backtest", "Compare strategies", "Scan watchlist"], key="lab_view", on_change="rerun")

# ---------------------------------------------------------------- backtest
with tab_bt:
    if tab_bt.open:
        bt = c.bt
        st.markdown(f"#### {c.strat_name} on {c.symbol}")
        lvl, ckey, why = core.confidence(c)
        st.markdown(f"<div class='note'>{c.tf_label} candles · {c.df.index[0]:%d %b %Y} → {c.df.index[-1]:%d %b %Y} "
                    f"({len(c.df):,} candles, {ui.esc(c.source)})</div><div style='margin:10px 0'>"
                    f"{common.conf_badge(lvl, ckey)} <span class='note'>&nbsp;{ui.esc(why)}</span></div>",
                    unsafe_allow_html=True)
        ret, bh = bt["Strategy return %"], bt["Buy & hold %"]
        st.markdown(ui.grid([
            ui.tile("Strategy return", f"{ret:+.2f}%", "", ui.signed_color(ret)),
            ui.tile("Buy & hold", f"{bh:+.2f}%", "", ui.signed_color(bh)),
            ui.tile("Trades", f"{bt['Trades']}"),
            ui.tile("Win rate", f"{bt['Win rate %']}%"),
            ui.tile("Average win", f"{bt['Avg win %']:+.2f}%", "", ui.up_txt()),
            ui.tile("Average loss", f"{bt['Avg loss %']:+.2f}%", "", ui.down_txt()),
            ui.tile("Profit factor", f"{bt['Profit factor']}", "wins ÷ losses"),
            ui.tile("Worst fall", f"{bt['Max drawdown %']:.2f}%", "max drawdown", ui.down_txt()),
        ]), unsafe_allow_html=True)
        if c.AUTO_INFO:
            a = c.AUTO_INFO
            fmt = "%b %Y" if c.interval == "1d" else "%d %b %y"
            st.markdown("##### Walk-forward check — 3 periods the picker never saw")
            st.dataframe(pd.DataFrame([{"Period": f"{f['from']:{fmt}} – {f['to']:{fmt}}",
                                        "Picked": f["strategy"] or "nothing qualified", "Trades": f["trades"],
                                        "Return %": f["ret"], "Win %": f["win"], "Profit factor": f["pf"]} for f in a["folds"]])
                         .style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["Return %"])
                         .format({"Return %": "{:+.1f}", "Win %": "{:.0f}", "Profit factor": "{:.2f}"}),
                         width="stretch", hide_index=True)
            if P.pro and len(a["table"]):
                with st.expander(f"Top settings found ({a['tested']} tested over the whole history)"):
                    st.dataframe(a["table"], width="stretch", hide_index=True)
        if bt["Trades"]:
            st.markdown("##### Equity curve — return %")
            st.plotly_chart(common.equity_figure(c), width="stretch", config={"displaylogo": False})
            common.monthly_heatmap(c.res.equity)
            tl = pd.DataFrame([{
                "Side": t.side, "Entry": t.entry_time.strftime("%d %b %y %H:%M"), "Entry ₹": round(t.entry, 2),
                "Exit": t.exit_time.strftime("%d %b %y %H:%M"), "Exit ₹": round(t.exit, 2),
                "P&L %": round(t.pnl_pct - 2 * c.cost, 2), "Reason": t.reason,
            } for t in reversed(c.res.trades)])
            st.markdown("##### Every trade")
            st.dataframe(tl.style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["P&L %"])
                         .format({"P&L %": "{:+.2f}", "Entry ₹": "{:,.2f}", "Exit ₹": "{:,.2f}"}),
                         width="stretch", hide_index=True, height=360)
            span_days = (c.df.index[-1] - c.df.index[0]).days
            if c.intraday_tf and span_days < 180:
                st.info(f"This intraday backtest covers only {span_days} days ({c.source}) — a small sample. "
                        + ("Angel One's 2-year history is downloading and will be used automatically."
                           if core.ANGEL() else "Connect Angel One (Settings) to backtest on 2 years of intraday data."))
        else:
            ui.empty_state("🧪", "No trades in this period", "This strategy didn't trigger on this chart.")

# ---------------------------------------------------------------- compare
with tab_cmp:
    if tab_cmp.open:
        st.markdown(f"#### Which strategy works best on {c.symbol}?")
        st.markdown("<div class='note'>Backtests every strategy with its default settings, after charges. "
                    "Click a row to use that strategy.</div>", unsafe_allow_html=True)
        if st.button(f"Compare strategies on {c.symbol}", type="primary", icon=":material/play_arrow:"):
            rows = []
            with st.spinner("Backtesting every strategy…"):
                for s in strategy.STRATEGIES.values():
                    for iv in s.intervals:
                        if iv in ("1m", "1h"):
                            continue
                        intra = s.style == "Intraday" and iv != "1d"
                        pr = strategy.Params(sl_atr=s.sl_atr, target_atr=s.target_atr, trail_supertrend=s.trail,
                                             allow_short=intra and s.signals is not strategy.score_signals, intraday=intra,
                                             cost_pct=P.cost_intraday if iv != "1d" else P.cost_delivery, **s.defaults)
                        o = core.analyse(c.ticker, iv, s, pr, P)
                        if o is None:
                            continue
                        d_, _, _, r_, sg_, _, _ = o
                        st_ = strategy.stats(r_, d_, pr.cost_pct)
                        g, gk, _ = strategy.reliability(r_, d_, pr.cost_pct, pr, sg_)
                        yrs = (d_.index[-1] - d_.index[0]).days / 365.25
                        sig_now = core.signal_of(r_)
                        rows.append({"Strategy": s.name, "Timeframe": core.TF_LABEL[iv], "_iv": iv, "Verdict": g,
                                     "Signal now": SIGNAL_WORD.get(sig_now, sig_now), "_g": {"good": 0, "warn": 1, "bad": 2}[gk],
                                     "Trades": st_["Trades"], "Win %": st_["Win rate %"], "Return %": st_["Strategy return %"],
                                     "Profit factor": st_["Profit factor"], "Worst fall %": st_["Max drawdown %"],
                                     "Tested over": f"{yrs:.0f} yrs" if yrs >= 1 else f"{yrs * 12:.0f} months"})
            tbl = pd.DataFrame(rows).sort_values(["_g", "Profit factor"], ascending=[True, False]).drop(columns="_g").reset_index(drop=True)
            st.session_state["cmp"] = {"ticker": c.ticker, "tbl": tbl, "ver": st.session_state.get("cmp", {}).get("ver", 0) + 1}
        cmp = st.session_state.get("cmp")
        if cmp and cmp["ticker"] == c.ticker:
            show = cmp["tbl"].drop(columns="_iv")
            ev = st.dataframe(show.style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["Return %"])
                              .format({"Return %": "{:+.2f}", "Worst fall %": "{:.2f}"}),
                              width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="cmp_tbl")
            pick = ev.selection.rows
            if pick and st.session_state.get("cmp_handled") != (cmp["ver"], pick[0]):
                st.session_state["cmp_handled"] = (cmp["ver"], pick[0])
                row = cmp["tbl"].iloc[pick[0]]
                sel.strategy, sel.interval = row.Strategy, row._iv
                sel.sl_atr = sel.target_atr = sel.trail = sel.allow_short = None
                st.rerun()

# ---------------------------------------------------------------- scanner
with tab_scan:
    if tab_scan.open:
        st.markdown(f"#### Scan your watchlist with {('Auto' if c.auto_mode else c.strat_name)} · {c.tf_label}")
        st.markdown("<div class='note'>Edit the watchlist in Settings. Click a row to open its chart.</div>", unsafe_allow_html=True)
        if st.button(f"Scan {len(P.watchlist)} symbols", type="primary", icon=":material/radar:"):
            rows = []
            prog = st.progress(0.0, text="Downloading prices…")
            core.prefetch([core.data.to_yahoo(x) for x in P.watchlist], sel.interval, P, start_download=False)
            for n, name in enumerate(P.watchlist):
                prog.progress((n + 1) / len(P.watchlist), text=f"Scanning {name}…")
                try:
                    s2 = core.Sel(symbol=name, interval=sel.interval, strategy=sel.strategy, sl_atr=sel.sl_atr,
                                  target_atr=sel.target_atr, trail=sel.trail, buy_score=sel.buy_score, allow_short=sel.allow_short)
                    cc = core.build(s2, P, start_download=False)   # no mass history downloads
                    if cc is None:
                        rows.append({"Symbol": name, "Signal": "no data", "_o": 9})
                        continue
                    S = core.signal(cc)
                    lvl = S["confidence"][0]
                    rows.append({"Symbol": name, "Signal": S["verdict"], "Confidence": lvl, "Price ₹": round(cc.ltp, 2),
                                 "Day %": round(cc.chg_pct, 2), "Plan": S["headline"], "Past return %": cc.bt["Strategy return %"],
                                 "_o": {"BUY": 0, "SHORT": 0, "SELL": 1, "HOLD": 2, "WAIT": 3, "SKIP": 4}.get(S["kind"], 5)})
                except Exception as e:  # noqa: BLE001 — one bad symbol shouldn't stop the scan
                    rows.append({"Symbol": name, "Signal": f"error: {e}", "_o": 9})
            prog.empty()
            tbl = pd.DataFrame(rows).sort_values("_o").drop(columns="_o").reset_index(drop=True)
            st.session_state["scan"] = {"tbl": tbl, "ver": st.session_state.get("scan", {}).get("ver", 0) + 1,
                                        "when": common.now_ist().strftime("%H:%M:%S")}
        scan = st.session_state.get("scan")
        if scan:
            st.caption(f"Scanned at {scan['when']} IST")
            sty = scan["tbl"].style
            for col in ("Day %", "Past return %"):
                if col in scan["tbl"]:
                    sty = sty.map(lambda v: f"color:{ui.signed_color(v)}" if isinstance(v, (int, float)) and pd.notna(v) else "", subset=[col])
            ev = st.dataframe(sty.format({"Day %": "{:+.2f}", "Past return %": "{:+.1f}", "Price ₹": "{:,.2f}"}, na_rep="—"),
                              width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="scan_tbl")
            pick = ev.selection.rows
            if pick and st.session_state.get("scan_handled") != (scan["ver"], pick[0]):
                st.session_state["scan_handled"] = (scan["ver"], pick[0])
                common.open_chart(scan["tbl"].iloc[pick[0]].Symbol)
