"""Rendering shared by several pages: symbol search, signal card, chart, confidence badge, trade dialogs."""
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import chart
import core
import data
import journal
import strategy
import ui
from ui import ACCENT, DOWN, UP, WARN

LINE_COLORS = ("#3987e5", "#9085e9", "#c98500")  # categorical slots 1, 7, 4
GRADE_COLOR = {"good": "up", "warn": "warn", "bad": "down"}
CHART_H = 640
CONF_ICON = {"High": "🟢", "Medium": "🟡", "Low": "🟠", "Not proven": "🔴"}


def run_every(P) -> int | None:
    """Live-refresh period for fragments: only while the market is open and live updates are on."""
    return P.refresh if P.live and core.market()[0] else None


def open_chart(symbol: str):
    core.select(symbol)
    st.switch_page("views/chart_page.py")


# ---------------------------------------------------------------- pickers
def symbol_picker(current: str, key: str = "search", options_only: bool = False) -> str:
    """Search box over indices + every NSE stock (by symbol or company name). Returns the chosen symbol."""
    u = core.universe()
    if options_only:
        und = options_underlyings()
        u = u[u.symbol.isin(und)]
    labels, syms = u.label.tolist(), u.symbol.tolist()
    if current not in syms:
        labels.insert(0, current)
        syms.insert(0, current)
    pick = st.selectbox("Search", labels, index=syms.index(current), key=f"{key}-{current}",
                        label_visibility="collapsed", placeholder="Search a stock or index…",
                        help="Type a symbol or company name, e.g. 'tata power' or 'NIFTY'")
    return syms[labels.index(pick)]


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def options_underlyings() -> list[str]:
    """Indices and stocks that have options, in the app's naming."""
    import options
    idx = list(options.INDEX_UNDERLYING)
    try:
        c = options.contracts()
        stk = sorted(set(c[c.exchange == "NSE"].underlying_symbol) - {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})
    except Exception:  # noqa: BLE001
        stk = []
    return idx + stk


def timeframe_picker(sel, key: str = "tf"):
    """Swing (daily) or intraday 15m / 5m."""
    opts = {"1d": "Swing", "15m": "Intraday 15m", "5m": "Intraday 5m"}
    cur = sel.interval if sel.interval in opts else "1d"
    v = st.segmented_control("Style", list(opts), default=cur, format_func=opts.get, key=f"{key}-{cur}",
                             label_visibility="collapsed",
                             help="Swing = daily candles, hold days to weeks (recommended). Intraday = same-day trades.") or cur
    sel.interval = v


def strategy_controls(sel, key: str = "st"):
    """Pro mode: choose a strategy instead of Auto, and tune it."""
    names = [core.AUTO] + [n for n, s in strategy.STRATEGIES.items() if sel.interval in s.intervals]
    if sel.strategy not in names:
        sel.strategy = core.AUTO
    sel.strategy = st.selectbox("Strategy", names, index=names.index(sel.strategy), key=f"{key}-strat-{sel.interval}",
                                format_func=lambda n: "🤖 Auto — best tested for this chart" if n == core.AUTO else n)
    if sel.strategy != core.AUTO:
        s = strategy.STRATEGIES[sel.strategy]
        with st.popover("Tune strategy", icon=":material/tune:"):
            st.caption(s.summary)
            sel.sl_atr = st.number_input("Stop-loss (× ATR, 0 = off)", 0.0, 6.0, float(s.sl_atr if sel.sl_atr is None else sel.sl_atr), 0.25,
                                         key=f"{key}-sl-{sel.strategy}")
            sel.target_atr = st.number_input("Target (× ATR, 0 = off)", 0.0, 10.0,
                                             float(s.target_atr if sel.target_atr is None else sel.target_atr), 0.25,
                                             key=f"{key}-tg-{sel.strategy}")
            sel.trail = st.checkbox("Trail stop on Supertrend", s.trail if sel.trail is None else sel.trail, key=f"{key}-tr-{sel.strategy}")
            sel.allow_short = st.checkbox("Allow SHORT (intraday)", bool(sel.allow_short), key=f"{key}-sh-{sel.strategy}",
                                          disabled=sel.interval == "1d")
            if s.signals is strategy.score_signals:
                sel.buy_score = st.slider("Confirmations needed", 2, 6, sel.buy_score, key=f"{key}-bs")


# ---------------------------------------------------------------- small HTML pieces
def conf_badge(level: str, key: str) -> str:
    return ui.pill(f"Confidence: {level}", ui.color(key))


def signal_card_html(c, S, P, *, countdown: str = "", compact: bool = False) -> str:
    col = ui.color(S["color"])
    lvl, ckey, why = S["confidence"]
    plan = ui.grid([ui.tile(lab, val, sub, ui.color(k)) for lab, val, sub, k in S["plan"]]) if S["plan"] else ""
    steps = ("<div class='steps'><div class='l'>What to do now</div><ol>"
             + "".join(f"<li>{x}</li>" for x in S["steps"]) + "</ol></div>") if S["steps"] else ""
    head = (f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap'>"
            f"<h4 style='margin:0'>Signal now</h4>{conf_badge(lvl, ckey)}</div>")
    strat_line = ("🤖 Auto picked " if c.auto_mode else "Strategy: ") + f"<b>{ui.esc(c.strat_name)}</b>"
    return (f"<div class='card sigpanel' style='border-color:{col}88;box-shadow:inset 4px 0 0 {col}'>{head}"
            f"<div class='verdict' style='color:{col};margin-top:8px'>{ui.esc(S['verdict'])}</div>"
            f"{plan}<div class='msg'>{S['msg']}</div>{steps}"
            + (f"<div class='note' style='margin-top:10px'>⏱ {countdown}</div>" if countdown else "")
            + f"<div class='note' style='margin-top:10px'>{strat_line} · {ui.esc(why)}</div>"
            + ("" if compact or not P.pro else auto_note(c)) + "</div>")


def auto_note(c) -> str:
    """Pro detail: what Auto picked and how the picking method did on 3 periods it never saw."""
    a = c.AUTO_INFO
    if not a:
        return ""
    fmt = "%b %Y" if c.interval == "1d" else "%d %b %y"
    folds = " · ".join(
        f"{f['from']:{fmt}}–{f['to']:{fmt}}: " + (f"<b style='color:{ui.signed_color(f['ret'])}'>{f['ret']:+.1f}%</b> ({f['trades']})"
                                                  if f["strategy"] else "nothing qualified")
        for f in a["folds"])
    span = f"{a['span'][0]:%b %Y} → {a['span'][1]:%b %Y}"
    return (f"<div class='note' style='margin-top:10px;border-top:1px solid color-mix(in srgb, currentColor 12%, transparent);"
            f"padding-top:8px'>Tested {a['tested']} settings on {a['bars']:,} candles ({span}); using "
            f"{ui.esc(core.setting_text(a['params'], a['strategy']))}.<br>Walk-forward (3 periods never seen): {folds}</div>")


def checklist_html(c) -> str:
    rows = strategy.reasons(c.last, c.use_vwap)
    rows.insert(0, (f"Daily trend <b>{c.daily_trend}</b>",
                    True if c.daily_trend == "UP" else False if c.daily_trend == "DOWN" else None))
    if c.intraday_tf:
        rows.insert(1, (f"ADX {c.last.ADX:.0f} — {'trending' if c.last.ADX > 22 else 'choppy'}", None))
    return "".join(ui.chip("✅" if b is True else "❌" if b is False else "➖", txt) for txt, b in rows)


def record_html(c) -> str:
    """Plain-language track record of the strategy on this chart."""
    bt = c.bt
    if not bt["Trades"]:
        return "No past trades on this chart yet."
    ret, bh = bt["Strategy return %"], bt["Buy & hold %"]
    span = f"{c.df.index[0]:%b %Y} – {c.df.index[-1]:%b %Y}"
    return (f"Over {span} this strategy made <b style='color:{ui.signed_color(ret)}'>{ret:+.1f}%</b> in {bt['Trades']} trades "
            f"(won {bt['Win rate %']:.0f}% of them; average win {bt['Avg win %']:+.1f}%, average loss {bt['Avg loss %']:+.1f}%). "
            f"Simply holding would have made {bh:+.1f}%. Worst fall along the way: {bt['Max drawdown %']:.0f}%.")


# ---------------------------------------------------------------- trade actions
def paper_button(c, S, key: str = "paper"):
    if S["can_paper"] and st.button(f"Paper-trade this {S['verdict']} ({S['qty']:,} qty)", icon=":material/edit_note:",
                                    key=f"{key}-{c.ticker}", width="stretch"):
        journal.add_trade(c.symbol, c.ticker, S["side"], S["qty"], c.ltp, S["stop"], S["target"], c.strat_name)
        st.toast(f"Paper trade added: {S['qty']} × {c.symbol} @ ₹{c.ltp:,.2f}", icon="📝")


@st.dialog("Track a trade you placed on Groww")
def bought_dialog(symbol: str, ticker: str, price: float, stop: float | None, target: float | None, qty: int, strat_name: str):
    st.caption("Enter what you actually bought. The app tracks it live and reminds you when the stop-loss or target is hit.")
    a, b = st.columns(2)
    side = a.segmented_control("Side", ["LONG", "SHORT"], default="LONG", format_func={"LONG": "Bought", "SHORT": "Sold short"}.get) or "LONG"
    qty = b.number_input("Quantity", 1, 10_000_000, max(int(qty), 1))
    a, b, cc = st.columns(3)
    entry = a.number_input("Your price ₹", 0.0, 1e8, round(price, 2))
    stop_v = b.number_input("Stop-loss ₹ (0 = none)", 0.0, 1e8, round(stop or 0.0, 2))
    tgt_v = cc.number_input("Target ₹ (0 = none)", 0.0, 1e8, round(target or 0.0, 2))
    if st.button("Save trade", type="primary", icon=":material/check:", width="stretch"):
        journal.add_trade(symbol, ticker, side, qty, entry, stop_v or None, tgt_v or None, strat_name, kind="real")
        st.toast(f"Tracking your {symbol} trade", icon="✅")
        st.rerun()


def bought_button(c, S, key: str = "real"):
    if st.button("I bought this — track it", icon=":material/add_task:", key=f"{key}-{c.ticker}", width="stretch"):
        # suggest a protective stop (2 typical moves) and a risk-sized quantity when the signal has no fresh plan
        long = S["kind"] != "SHORT"
        stop = S["stop"] or c.ltp + (-2 if long else 2) * float(c.last.ATR)
        qty = S["qty"] or core.qty_for(c, c.ltp, stop)
        bought_dialog(c.symbol, c.ticker, c.ltp, stop, S["target"], qty, c.strat_name)


# ---------------------------------------------------------------- charts
LEVEL_STYLE = {"average": (LINE_COLORS[2], 0, 2), "Buy level": (UP, 2, 1.2), "Exit level": (DOWN, 2, 1.2),
               "high": (UP, 0, 1.2), "low": (DOWN, 0, 1.2), "ago": (LINE_COLORS[1], 2, 1.4)}


def level_overlays(c, df) -> list[dict]:
    """Price lines of the strategy in use (its averages, buy / exit levels, breakout channel)."""
    if c.strat.levels is None:
        return []
    out = []
    for i, (name, series) in enumerate(c.strat.levels(df, c.params).items()):
        key = next((k for k in LEVEL_STYLE if k in name), None)
        colr, style, width = LEVEL_STYLE.get(key, (LINE_COLORS[i % 3], 0, 1.5))
        if "average" in name and i > 0:   # second average of a crossover
            colr = LINE_COLORS[0]
        col = f"LV{i}"
        df[col] = series
        out.append({"name": name, "col": col, "color": colr, "style": style, "width": width,
                    "step": key in ("high", "low")})
    return out


def default_overlays(c) -> list[str]:
    s = c.strat
    if s.levels is not None:
        return list(s.levels(c.df, c.params))
    avg200 = "200-day avg" if not c.intraday_tf else "200-candle avg"
    if s.signals is strategy.orb_trend_signals:
        return ["Opening range", "VWAP"] if c.use_vwap else ["Opening range"]
    if s.signals is strategy.trend200_signals:
        return [avg200]
    if s.signals is strategy.rsi2_signals:
        return [avg200, "5-day avg"]
    if s.signals is strategy.donchian_signals:
        return ["Donchian channel"]
    P = core.prefs()
    return [f"EMA {P.fast}", f"EMA {P.slow}", f"EMA {P.trend}", "Supertrend"]


def chart_live(c, P) -> dict | None:
    """The chart's live-update settings while the market is open. Calling it again also keeps a cloud chart's
    live file fresh (see livefeed.py), so the Chart page calls it on every refresh."""
    return core.live_feed(ticker=c.ticker, interval=c.interval) if P.live and c.is_open else None


def chart_html(c, S, P, height: int = CHART_H) -> str:
    """The Groww-style interactive chart for one analysed instrument."""
    df = c.df
    if c.live_bar is not None:   # show the forming candle too (signals use completed candles only)
        df = core.prepare(c.raw, c.daily, c.use_vwap, c.interval, P.ind).loc[c.df.index[0]:]
    df = df.copy()
    df["ST_up"], df["ST_dn"] = df.ST.where(df.ST_dir > 0), df.ST.where(df.ST_dir < 0)
    df["OR_hi"], df["OR_lo"] = df.ORH.where(df.After_OR), df.ORL.where(df.After_OR)
    avg200 = "200-day avg" if not c.intraday_tf else "200-candle avg"
    overlays = [
        {"name": f"EMA {P.fast}", "col": "EMA_fast", "color": LINE_COLORS[0]},
        {"name": f"EMA {P.slow}", "col": "EMA_slow", "color": LINE_COLORS[1]},
        {"name": f"EMA {P.trend}", "col": "EMA_trend", "color": LINE_COLORS[2]},
        {"name": "Supertrend", "col": "ST_up", "color": UP, "style": 2, "width": 1},
        {"name": "Supertrend", "col": "ST_dn", "color": DOWN, "style": 2, "width": 1},
        {"name": "Bollinger", "col": "BB_up", "color": "#8b8f99", "width": 1},
        {"name": "Bollinger", "col": "BB_low", "color": "#8b8f99", "width": 1},
        {"name": avg200, "col": "SMA200", "color": LINE_COLORS[2], "width": 2},
        {"name": "5-day avg" if not c.intraday_tf else "5-candle avg", "col": "SMA5", "color": LINE_COLORS[0]},
        {"name": "Donchian channel", "col": "DC_hi20", "color": UP, "width": 1.2, "step": True},
        {"name": "Donchian channel", "col": "DC_lo10", "color": DOWN, "width": 1.2, "step": True},
    ]
    if c.use_vwap:
        overlays.insert(5, {"name": "VWAP", "col": "VWAP", "color": "#d55181"})
    if c.intraday_tf:
        overlays += [{"name": "Opening range", "col": "OR_hi", "color": UP, "style": 2, "width": 1.2, "step": True},
                     {"name": "Opening range", "col": "OR_lo", "color": DOWN, "style": 2, "width": 1.2, "step": True}]
    overlays += level_overlays(c, df)
    rsi_col, rsi_lv = ("RSI2", [90, 10]) if c.strat.signals is strategy.rsi2_signals else ("RSI", [70, 30])
    panes = [
        {"name": "RSI-2" if rsi_col == "RSI2" else "RSI", "lines": [{"col": rsi_col, "color": LINE_COLORS[1]}], "levels": rsi_lv},
        {"name": "MACD", "hist": "MACD_hist", "lines": [{"col": "MACD", "color": LINE_COLORS[0]}, {"col": "MACD_signal", "color": LINE_COLORS[2]}]},
        {"name": "ADX", "lines": [{"col": "ADX", "color": LINE_COLORS[2]}], "levels": [22]},
    ]
    markers = []
    for t in c.res.trades + ([c.res.open_trade] if c.res.open_trade else []):
        long = t.side == "LONG"
        markers.append({"time": t.entry_time, "position": "belowBar" if long else "aboveBar", "color": UP if long else DOWN,
                        "shape": "arrowUp" if long else "arrowDown", "text": "BUY" if long else "SHORT"})
        if t.exit_time is not None:
            markers.append({"time": t.exit_time, "position": "aboveBar" if long else "belowBar", "color": WARN,
                            "shape": "circle", "text": f"{t.pnl_pct - 2 * c.cost:+.1f}%"})
    lines = []
    if c.res.open_trade:
        t = c.res.open_trade
        if abs(t.stop) < 1e12:
            lines.append({"price": round(t.stop, 2), "color": DOWN, "title": "SL"})
        if abs(t.target) < 1e12:
            lines.append({"price": round(t.target, 2), "color": UP, "title": "Target"})
        lines.append({"price": round(t.entry, 2), "color": ACCENT, "title": "Entry"})
    return chart.build_html(df, symbol=c.symbol, intraday=c.intraday_tf, prev_close=c.prev_close, overlays=overlays,
                            default_overlays=default_overlays(c), panes=panes, markers=markers, price_lines=lines,
                            up=UP, down=DOWN, accent=ACCENT, bg="transparent", store_key=f"tsi-{int(c.intraday_tf)}-",
                            height=height, live=chart_live(c, P),
                            alert={"key": c.alert_key, "verdict": S["verdict"], "title": f"{c.symbol}: {S['verdict']}",
                                   "body": S["note"]})


def rangebreaks(intraday: bool):
    b = [dict(bounds=["sat", "mon"])]
    if intraday:
        b.append(dict(bounds=[15.5, 9.25], pattern="hour"))
    return b


def equity_figure(c):
    eq = c.res.equity
    bhs = c.df.Close / c.df.Open.iloc[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=(eq - 1) * 100, name="Strategy", line=dict(color=LINE_COLORS[0], width=2),
                             fill="tozeroy", fillcolor="rgba(57,135,229,0.08)"))
    fig.add_trace(go.Scatter(x=bhs.index, y=(bhs - 1) * 100, name="Buy & hold", line=dict(color=LINE_COLORS[2], width=1.6)))
    fig.update_layout(**ui.plotly_layout(340, hovermode="x unified", legend=dict(orientation="h", y=1.08, x=0)))
    fig.update_xaxes(rangebreaks=rangebreaks(c.intraday_tf), showgrid=False)
    fig.update_yaxes(gridcolor=ui.GRID, zeroline=False, side="right", ticksuffix="%")
    return fig


def monthly_heatmap(eq: pd.Series):
    """Calendar of monthly strategy returns (diverging: red loss · neutral · green gain)."""
    m = eq.resample("ME").last().dropna()
    if len(m) < 3:
        return
    r = m.pct_change() * 100
    r.iloc[0] = (m.iloc[0] - 1) * 100
    tbl = pd.DataFrame({"y": r.index.year, "m": r.index.month, "r": r.to_numpy()})
    piv = tbl.pivot(index="y", columns="m", values="r").reindex(columns=range(1, 13)).iloc[-12:]
    yearly = (piv.fillna(0) / 100 + 1).prod(axis=1).sub(1).mul(100)
    lim = max(2.0, float(np.nanpercentile(np.abs(piv.to_numpy()), 95)))
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    text = [[("" if pd.isna(v) else f"{v:+.1f}") for v in row] for row in piv.to_numpy()]
    mid = "#2a2e37" if ui.dark() else "#eceef1"
    fig = go.Figure(go.Heatmap(
        z=piv.to_numpy(), x=months, y=[f"{y}  ({yearly[y]:+.0f}%)" for y in piv.index], text=text, texttemplate="%{text}",
        textfont=dict(size=11), zmid=0, zmin=-lim, zmax=lim, xgap=2, ygap=2, showscale=False,
        colorscale=[[0, DOWN], [0.5, mid], [1, UP]], hovertemplate="%{y} %{x}: %{z:+.2f}%<extra></extra>"))
    fig.update_layout(**ui.plotly_layout(70 + 30 * len(piv), margin=dict(l=8, r=8, t=8, b=8),
                                         xaxis=dict(side="top", showgrid=False), yaxis=dict(autorange="reversed", showgrid=False)))
    st.markdown("##### Monthly returns % (year total in brackets)")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


def now_ist() -> datetime:
    return datetime.now(data.IST)
