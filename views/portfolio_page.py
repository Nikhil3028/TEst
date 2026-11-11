"""Portfolio: the momentum portfolio — the strongest stocks of the market, re-picked once a month."""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import data
import momentum
import scanner
import ui

P = core.prefs()
ui.page_header("Momentum portfolio", "Hold the strongest stocks of the market in equal amounts and re-pick them once a month — "
               "a different approach from the BUY / SELL signals, and the one that did best in testing.")

with st.spinner("Ranking the 200 most-traded stocks — about a minute, once a day…"):
    try:
        rk = momentum.ranking(scanner.asof())
    except Exception as e:  # noqa: BLE001 — Yahoo / NSE unreachable
        st.error(f"Couldn't download prices for the ranking just now ({str(e)[:120]}). Try again in a few minutes.")
        st.stop()

pf = momentum.load()
bt = momentum.backtest()
if pf:
    n = pf["n"]
else:
    n = st.segmented_control("Stocks to hold", [10, 20], default=10 if P.capital < 300_000 else 20,
                             format_func=lambda k: f"Top {k}", key="mom_n",
                             help="20 is steadier (in testing its worst fall was smaller); 10 needs less money per stock.") or 10
tgt = momentum.target(rk, n, P.capital)
name_of = dict(zip(core.universe().symbol, core.universe().name))

# ---------------------------------------------------------------- what the testing found
key = f"Top {n}"
if bt:
    s, h, ix = bt["stats"][key], bt["stats"]["Hold all 200"], bt["stats"]["NIFTY 200 index"]
    st.markdown(ui.stats([
        ui.tile(f"Top {n}, in testing", f"{s['cagr']:+.0f}% a year", f"{bt['from']} – {bt['to']}, after charges · flattered, see below", ui.up_txt()),
        ui.tile("Holding all 200 instead", f"{h['cagr']:+.0f}% a year", f"NIFTY 200 index: {ix['cagr']:+.0f}%"),
        ui.tile("Both halves of the test", f"{s['first']:+.0f}% · {s['second']:+.0f}%", "2010–18 · 2018–26, a year"),
        ui.tile("Worst fall", f"{s['dd']:.0f}%", f"worst year {s['worst_year']:+.0f}% ({s['worst_year_at']})", ui.down_txt()),
    ]), unsafe_allow_html=True)
else:
    st.markdown(ui.stats([ui.tile("Test results", "Not run on this computer yet",
                                  "Open “How it was tested” below and run it (about 3 minutes).")]), unsafe_allow_html=True)
st.markdown(ui.callout(
    "Read this before using it. The test picks from today's NIFTY 500 companies, so firms that failed and were delisted "
    "are missing — the past numbers above are flattered and the future will be lower. The portfolio fell "
    "35–50% at its worst, and in 2025 it lost money while the index rose. Use money you can leave alone for years."),
    unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- this month's portfolio
od = momentum.orders(pf, tgt)
now = datetime.now(data.IST)
nxt = (pd.Timestamp(now.date()).replace(day=1) + pd.offsets.MonthBegin(1)).strftime("%B")
if not pf:
    status = "Not started — this is the list to buy today."
elif momentum.due(pf):
    status = f"<b style='color:{ui.color('warn')}'>A new month has started — time to re-pick.</b> Last done {pf['rebalanced']}."
else:
    status = f"Following since {pf['started']} ({pf['kind']}). Next re-pick: first trading day of {nxt}."
st.markdown(ui.section(f"The strongest {n} right now", f"Ranked on the close of {rk.attrs.get('asof', '')} · "
                       f"₹{P.capital / n:,.0f} per stock from your ₹{P.capital:,.0f} · {status}"), unsafe_allow_html=True)

held = {h["symbol"] for h in (pf or {}).get("holdings", [])}
show = pd.DataFrame({
    "Rank": tgt["rank"], "Stock": tgt.symbol, "Company": tgt.symbol.map(lambda x: name_of.get(x, x)),
    "Do": tgt.symbol.map(lambda x: "Keep" if x in held else "Buy"), "Price ₹": tgt.price, "Qty": tgt.qty,
    "Amount ₹": tgt.value, "6 months %": tgt.r6, "12 months %": tgt.r12})
st.dataframe(show.style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["6 months %", "12 months %"])
             .map(lambda v: f"color:{ui.up_txt()};font-weight:600" if v == "Buy" else "", subset=["Do"])
             .format({"Price ₹": "{:,.2f}", "Amount ₹": "{:,.0f}", "6 months %": "{:+.0f}", "12 months %": "{:+.0f}"}),
             width="stretch", hide_index=True, height=38 * len(show) + 40)
if od["sell"]:
    st.markdown("<div class='msg'><b>Sell first</b> — no longer in the top " + str(n) + ": "
                + " · ".join(f"{ui.esc(h['symbol'])} ({h['qty']:,} qty)" for h in od["sell"]) + "</div>", unsafe_allow_html=True)
skipped = [s for s in rk.index[:tgt["rank"].max() if len(tgt) else 0] if s not in set(tgt.symbol)]
if skipped:
    st.caption(f"Skipped because one share costs more than ₹{P.capital / n:,.0f}: {', '.join(skipped)}.")

b1, b2, b3 = st.columns(3)
if not pf:
    if b1.button("Start as a paper portfolio", icon=":material/edit_note:", width="stretch", type="primary"):
        momentum.save(tgt, n, "paper")
        st.rerun()
    if b2.button("I bought these — track it", icon=":material/add_task:", width="stretch"):
        momentum.save(tgt, n, "real")
        st.rerun()
else:
    changed = bool(od["sell"] or od["buy"])
    if b1.button("I've re-picked — save this list", icon=":material/published_with_changes:", width="stretch",
                 type="primary" if momentum.due(pf) else "secondary", disabled=not changed and not momentum.due(pf)):
        momentum.save(tgt, n, pf["kind"])
        st.rerun()
    if b3.button("Stop following", icon=":material/close:", width="stretch", type="tertiary"):
        momentum.clear()
        st.rerun()
    if not momentum.due(pf) and changed:
        st.caption("The ranking moves every day, but the tested rule only trades once a month — changing more often adds "
                   "charges without a tested benefit.")

# ---------------------------------------------------------------- holdings
if pf and pf.get("holdings"):
    st.write("")
    rows, cost, value = [], 0.0, 0.0
    for h in pf["holdings"]:
        px = float(rk.price[h["symbol"]]) if h["symbol"] in rk.index else ((core.quote(data.to_yahoo(h["symbol"])) or [h["price"]])[0])
        cost += h["qty"] * h["price"]
        value += h["qty"] * px
        rows.append({"Stock": h["symbol"], "Qty": h["qty"], "Bought at ₹": h["price"], "Now ₹": px,
                     "P&L ₹": h["qty"] * (px - h["price"]), "P&L %": (px / h["price"] - 1) * 100})
    st.markdown(ui.section("What you hold", f"{pf['kind'].capitalize()} portfolio · last re-picked {pf['rebalanced']} · prices "
                           "from the last close"), unsafe_allow_html=True)
    st.markdown(ui.grid([ui.tile("Invested", f"₹{cost:,.0f}"), ui.tile("Worth now", f"₹{value:,.0f}"),
                         ui.tile("P&L", f"₹{value - cost:+,.0f}", f"{(value / cost - 1) * 100:+.2f}%" if cost else "",
                                 ui.signed_color(value - cost))]), unsafe_allow_html=True)
    hd = pd.DataFrame(rows)
    st.dataframe(hd.style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["P&L ₹", "P&L %"])
                 .format({"Bought at ₹": "{:,.2f}", "Now ₹": "{:,.2f}", "P&L ₹": "{:+,.0f}", "P&L %": "{:+.2f}"}),
                 width="stretch", hide_index=True)

# ---------------------------------------------------------------- the evidence
st.write("")
with st.expander("How it was tested — and what it can't tell you", icon=":material/science:", expanded=not bt):
    st.markdown("""
**The rule.** Take the 200 most-traded stocks. Score each by its 6- and 12-month return divided by how jumpy it is.
Hold the top 10 or 20 in equal amounts. Re-rank after each month's last close and trade the next day.
The rule was fixed before the test and is the same one NSE's momentum indices are built on.

**The test.** Every month since 2010, using only prices known at the time, with 0.15% charged on every buy and sell.
""")
    if bt:
        st.caption("Each line shows what ₹1 grew to. The vertical scale is logarithmic, so equal distances are equal % gains.")
        fig = go.Figure()
        for nm, col, w in ((key, ui.color("accent"), 2.2), ("Hold all 200", "#c98500", 1.6), ("NIFTY 200 index", ui.MUTED, 1.4)):
            c = bt["curves"][nm]
            fig.add_trace(go.Scatter(x=c["x"], y=c["y"], name=nm, mode="lines", line=dict(color=col, width=w),
                                     hovertemplate="%{x|%b %Y}: ₹%{y:.2f}<extra>" + nm + "</extra>"))
        fig.update_layout(**ui.plotly_layout(340, legend=dict(orientation="h", y=1.12), hovermode="x unified",
                                             xaxis=dict(gridcolor=ui.GRID),
                                             yaxis=dict(type="log", gridcolor=ui.GRID, side="right", tickprefix="₹")))
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
        tbl = pd.DataFrame({nm: bt["stats"][nm] for nm in bt["stats"]}).T[["cagr", "first", "second", "dd", "worst_year"]]
        tbl.columns = ["Per year %", "2010–18 %", "2018–26 %", "Worst fall %", "Worst year %"]
        st.dataframe(tbl.style.format("{:+.1f}"), width="stretch")
        yrs = pd.DataFrame({nm: bt["years"][nm] for nm in (key, "Hold all 200", "NIFTY 200 index")}).T
        st.markdown("**Year by year, %**")
        st.dataframe(yrs.style.map(lambda v: f"color:{ui.signed_color(v)}").format("{:+.0f}"), width="stretch")
    st.markdown("""
**What it can't tell you.**
- **The past numbers are too good.** The stocks come from *today's* NIFTY 500. Companies that collapsed and left the
  index are not in the test, and companies that grew into it are. Even "holding all 200" shows more than the real
  NIFTY 200 index for this reason. Expect the real edge to be a fraction of what the test shows.
- **It falls as hard as the market, sometimes harder.** The market filter (everything in cash while NIFTY is below its
  200-day average) cut the worst fall to roughly 25–33% in testing, at the cost of about 6% a year.
- **It has losing stretches** while the index does fine — 2025 was one.
- **It trades a lot**: about half the portfolio changes each month. Charges are in the test; short-term capital-gains
  tax is not.
""")
    if st.button("Run the test again now (about 3 minutes)" if bt else "Run the test (about 3 minutes)", icon=":material/play_arrow:"):
        with st.spinner("Downloading ~500 full price histories and replaying every month since 2010…"):
            momentum.backtest(force=True)
        st.rerun()

with st.expander("The full ranking — top 40", icon=":material/format_list_numbered:"):
    top = rk.head(40)
    st.dataframe(pd.DataFrame({"Rank": top["rank"], "Stock": top.index, "Company": [name_of.get(x, x) for x in top.index],
                               "Price ₹": top.price, "6 months %": top.r6, "12 months %": top.r12, "Score": top.score})
                 .style.map(lambda v: f"color:{ui.signed_color(v)}", subset=["6 months %", "12 months %"])
                 .format({"Price ₹": "{:,.2f}", "6 months %": "{:+.0f}", "12 months %": "{:+.0f}", "Score": "{:.2f}"}),
                 width="stretch", hide_index=True)
