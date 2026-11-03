"""Trades: your paper (practice) and real trades, with live P&L. Stops and targets close them automatically."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import data
import journal
import ui
from views.common import LINE_COLORS, run_every

P = core.prefs()
ui.page_header("Trades", "Paper trades to practise, real trades you placed on Groww — tracked live, closed at your stop or target.")

kind_view = st.segmented_control("Show", ["All", "Real", "Paper"], default="All", key="trade_kind",
                                 label_visibility="collapsed") or "All"


def kind_of(t) -> str:
    return "Real" if t.get("kind") == "real" else "Paper"


@st.fragment(run_every=run_every(P))
def trades_view():
    trades = [t for t in journal.load_trades() if kind_view == "All" or kind_of(t) == kind_view]
    open_t = [t for t in trades if t["status"] == "OPEN"]
    closed_t = [t for t in trades if t["status"] == "CLOSED"]
    prices = {t["ticker"]: px for t in open_t if (px := core.trade_price(t)) is not None}
    for t in journal.auto_close(prices):
        st.toast(f"{t['symbol']}: {t['exit_reason']} reached — trade closed", icon="📒")
    unreal = sum(journal.pnl(t, prices.get(t["ticker"]))[0] for t in open_t)
    real = sum(journal.pnl(t, None)[0] for t in closed_t)
    wins = sum(1 for t in closed_t if journal.pnl(t, None)[0] > 0)
    st.markdown(ui.grid([
        ui.tile("Open trades", f"{len(open_t)}"),
        ui.tile("Open P&L", f"₹{unreal:+,.0f}", "if you closed now", ui.signed_color(unreal)),
        ui.tile("Booked P&L", f"₹{real:+,.0f}", f"{len(closed_t)} closed trades", ui.signed_color(real)),
        ui.tile("Win rate", f"{wins / len(closed_t) * 100:.0f}%" if closed_t else "—", "of closed trades"),
    ]), unsafe_allow_html=True)
    st.write("")
    st.markdown("### Open trades")
    if not open_t:
        ui.empty_state("📝", "No open trades",
                       "On the Chart page, use <b>Paper-trade</b> to practise a signal, or <b>I bought this</b> to track a real one.")
    for t in open_t:
        px = prices.get(t["ticker"])
        rs, pc = journal.pnl(t, px)
        with st.container(border=True):
            c = st.columns([1.6, 0.9, 1, 1, 1, 1, 1.2, 0.9], vertical_alignment="center")
            c[0].markdown(f"**{t['symbol']}** &nbsp;{ui.pill(kind_of(t), ui.ACCENT if kind_of(t) == 'Real' else ui.MUTED)}  \n"
                          f"<span class='note'>{t['entry_time']} · {ui.esc(t['strategy'])}</span>", unsafe_allow_html=True)
            c[1].markdown(f"<span style='color:{ui.up_txt() if t['side'] == 'LONG' else ui.down_txt()}'>"
                          f"<b>{'Bought' if t['side'] == 'LONG' else 'Short'}</b></span>  \n{t['qty']:,} qty", unsafe_allow_html=True)
            c[2].markdown(f"<span class='note'>Entry</span>  \n**₹{t['entry']:,.2f}**", unsafe_allow_html=True)
            c[3].markdown(f"<span class='note'>Now</span>  \n**₹{px:,.2f}**" if px else "<span class='note'>Now</span>  \n—",
                          unsafe_allow_html=True)
            c[4].markdown(f"<span class='note'>Stop</span>  \n<span style='color:{ui.down_txt()}'>"
                          f"{'₹' + format(t['stop'], ',.2f') if t['stop'] else '—'}</span>", unsafe_allow_html=True)
            c[5].markdown(f"<span class='note'>Target</span>  \n<span style='color:{ui.up_txt()}'>"
                          f"{'₹' + format(t['target'], ',.2f') if t['target'] else '—'}</span>", unsafe_allow_html=True)
            c[6].markdown(f"<span class='note'>P&L</span>  \n<span style='color:{ui.signed_color(rs)}'><b>₹{rs:+,.0f}</b> "
                          f"({pc:+.2f}%)</span>", unsafe_allow_html=True)
            if c[7].button("Close", key=f"close-{t['id']}", disabled=px is None, width="stretch",
                           help="Close at the current price (for a real trade: after you sold on Groww)"):
                journal.close_trade(t["id"], px, "Manual")
                st.rerun()

    st.markdown("### Closed trades")
    if not closed_t:
        st.markdown("<div class='note'>Closed trades will appear here. Stops and targets close automatically while the app "
                    "is open, using the latest price.</div>", unsafe_allow_html=True)
        return
    ct = pd.DataFrame([{"Symbol": t["symbol"], "Type": kind_of(t), "Side": t["side"], "Qty": t["qty"], "Entry ₹": t["entry"],
                        "Exit ₹": t["exit"], "P&L ₹": round(journal.pnl(t, None)[0], 2), "P&L %": round(journal.pnl(t, None)[1], 2),
                        "Opened": t["entry_time"], "Closed": t["exit_time"], "Reason": t["exit_reason"], "Strategy": t["strategy"]}
                       for t in reversed(closed_t)])
    st.dataframe(ct.style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["P&L ₹", "P&L %"])
                 .format({"P&L ₹": "{:+,.2f}", "P&L %": "{:+.2f}", "Entry ₹": "{:,.2f}", "Exit ₹": "{:,.2f}"}),
                 width="stretch", hide_index=True)
    cum = ct.iloc[::-1]["P&L ₹"].cumsum().reset_index(drop=True)
    if len(cum) >= 2:
        fig = go.Figure(go.Scatter(x=list(range(1, len(cum) + 1)), y=cum, mode="lines+markers", name="Total P&L",
                                   line=dict(color=LINE_COLORS[0], width=2), marker=dict(size=8)))
        fig.update_layout(**ui.plotly_layout(280, title=dict(text="Total P&L ₹ after each closed trade", font=dict(size=13)),
                                             xaxis=dict(title="Trade #", showgrid=False, dtick=1),
                                             yaxis=dict(gridcolor=ui.GRID, side="right")))
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


trades_view()

st.write("")
with st.expander("Add a trade by hand", icon=":material/add:"):
    sel = core.selection()
    with st.form("add_trade"):
        f1, f2, f3, f4 = st.columns(4)
        f_kind = f1.selectbox("Type", ["Paper", "Real"], help="Real = a trade you placed on Groww")
        f_sym = f2.text_input("Symbol", sel.symbol)
        f_side = f3.selectbox("Side", ["LONG", "SHORT"], format_func={"LONG": "Bought", "SHORT": "Sold short"}.get)
        f_qty = f4.number_input("Quantity", 1, 10_000_000, 1)
        f5, f6, f7 = st.columns(3)
        f_entry = f5.number_input("Entry price ₹", 0.0, 1e8, 0.0)
        f_stop = f6.number_input("Stop-loss ₹ (0 = none)", 0.0, 1e8, 0.0)
        f_tgt = f7.number_input("Target ₹ (0 = none)", 0.0, 1e8, 0.0)
        if st.form_submit_button("Add trade", type="primary", icon=":material/add:"):
            if f_entry <= 0 or not f_sym.strip():
                st.error("Enter a symbol and the entry price.")
            else:
                journal.add_trade(f_sym.strip().upper(), data.to_yahoo(f_sym), f_side, f_qty, f_entry, f_stop or None,
                                  f_tgt or None, "Manual", kind="real" if f_kind == "Real" else "paper")
                st.rerun()

trades_all = journal.load_trades()
if trades_all:
    with st.expander("Delete a trade", icon=":material/delete:"):
        pick = st.selectbox("Trade", [f"{t['id']} · {t['symbol']} {t['side']} {t['entry_time']}" for t in trades_all])
        if st.button("Delete", type="secondary", icon=":material/delete:"):
            journal.delete_trade(pick.split(" · ")[0])
            st.rerun()
