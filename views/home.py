"""Home: what to do today — signals for the whole watchlist, market mood and your open trades."""
import streamlit as st

import core
import journal
import ui
from views.common import CONF_ICON, now_ist, open_chart

P = core.prefs()
is_open, status = core.market()
interval = core.STYLE_INTERVALS[P.style][0]
ORDER = {"BUY": 0, "SHORT": 0, "SELL": 1, "HOLD": 2, "WAIT": 3, "SKIP": 4}
CONF_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Not proven": 3}

who = f", {P.name}" if P.name else ""
ui.page_header(f"{core.greeting()}{who}", f"{now_ist():%A, %d %B} · {core.market_clock()}",
               ui.pill(f"{P.style} signals", ui.ACCENT))


# ---------------------------------------------------------------- market mood
@st.fragment(run_every=60 if P.live and is_open else None)
def mood():
    m = core.market_mood()
    tiles = []
    if "nifty" in m:
        px, pct = m["nifty"]
        tiles.append(ui.tile("NIFTY 50 today", f"₹{px:,.2f}", f"<span style='color:{ui.signed_color(pct)}'>{pct:+.2f}%</span>"))
    if "trend" in m:
        word = {"UP": "Rising 📈", "DOWN": "Falling 📉", "SIDEWAYS": "Sideways ↔️"}[m["trend"]]
        sub = f"{m['vs200']:+.1f}% vs 200-day average" if m.get("vs200") is not None else "daily trend"
        tiles.append(ui.tile("Market trend", word, sub, ui.color({"UP": "up", "DOWN": "down"}.get(m["trend"], "muted"))))
    if "vix" in m:
        lvl, word = m["vix"]
        tiles.append(ui.tile("Fear gauge (India VIX)", f"{lvl:.1f} · {word}", "lower = calmer market",
                             ui.color({"Calm": "up", "Normal": None, "Nervous": "warn", "Fearful": "down"}[word])))
    tiles.append(ui.tile("Your risk per trade", f"₹{P.capital * P.risk_pct / 100:,.0f}",
                         f"{P.risk_pct:g}% of ₹{P.capital:,.0f}"))
    st.markdown(ui.grid(tiles), unsafe_allow_html=True)


mood()
st.write("")


# ---------------------------------------------------------------- today's signals
def snapshot(sym: str) -> dict:
    try:
        c = core.build(core.Sel(symbol=sym, interval=interval), P)
        if c is None:
            return {"ok": False, "symbol": sym, "err": "No data for this symbol"}
        S = core.signal(c)
        return {"ok": True, "symbol": sym, "name": core.name_of(sym), "ltp": c.ltp, "chg_pct": c.chg_pct, "S": S,
                "strat": core.SHORT_NAME.get(c.strat_name, c.strat_name), "at": now_ist()}
    except Exception as e:  # noqa: BLE001 — one bad symbol shouldn't break the page
        return {"ok": False, "symbol": sym, "err": str(e)[:120]}


def card(d: dict):
    with st.container(border=True):
        if not d["ok"]:
            st.markdown(f"<div class='sigcard'><div class='nm'>{ui.esc(d['symbol'])}</div>"
                        f"<div class='line muted'>Couldn't analyse: {ui.esc(d['err'])}</div></div>", unsafe_allow_html=True)
            return
        S = d["S"]
        col = ui.color(S["color"])
        lvl, _, why = S["confidence"]
        name = d["name"] if d["name"].upper() != d["symbol"] else ""
        st.markdown(
            f"<div class='sigcard'><div class='top'><div><div class='nm'>{ui.esc(d['symbol'])}</div>"
            f"<div class='co'>{ui.esc(name) or '&nbsp;'}</div></div>"
            f"<div class='px'><div class='v'>₹{d['ltp']:,.2f}</div>"
            f"<div class='c' style='color:{ui.signed_color(d['chg_pct'])}'>{d['chg_pct']:+.2f}%</div></div></div>"
            f"<div class='badge' style='color:{col};background:{col}1f'>{ui.esc(S['verdict'])}</div>"
            f"<div class='line'>{ui.esc(S['headline'])}</div>"
            f"<div class='note' title='{ui.esc(why)}'>{CONF_ICON.get(lvl, '')} Confidence: {lvl} · {ui.esc(d['strat'])}</div></div>",
            unsafe_allow_html=True)
        if st.button("Open", key=f"open-{d['symbol']}", icon=":material/arrow_forward:", width="stretch", type="tertiary"):
            open_chart(d["symbol"])


@st.fragment(run_every=60 if P.live and is_open else None)
def board():
    wl = P.watchlist
    if not wl:
        ui.empty_state("⭐", "Your watchlist is empty", "Add stocks or indices on the Chart page (☆) or in Settings.")
        return
    b = st.session_state.setdefault("board", {})
    key = (P.style, core.candle_key(interval, P.closed_only), P.capital, P.risk_pct, P.ind, P.closed_only)
    todo = [s for s in wl if s not in b or b[s]["key"] != key]
    if todo:
        bar = st.progress(0.0, text="Checking your watchlist…")
        for i, s in enumerate(todo):
            bar.progress(i / len(todo), text=f"Checking {s} ({i + 1} of {len(todo)}) — the first check of the day takes a moment")
            b[s] = {"key": key, **snapshot(s)}
        bar.empty()
    rows = [b[s] for s in wl if s in b]
    prev = st.session_state.setdefault("board_prev", {})
    for d in rows:   # tell the user when a signal changes between refreshes
        if d["ok"]:
            v = d["S"]["verdict"]
            if prev.get(d["symbol"]) not in (None, v) and d["S"]["kind"] in ("BUY", "SHORT", "SELL"):
                st.toast(f"{d['symbol']}: now {v}", icon="🔔")
            prev[d["symbol"]] = v
    ok = [d for d in rows if d["ok"]]
    act = [d for d in ok if d["S"]["kind"] in ("BUY", "SHORT", "SELL")]
    hold = [d for d in ok if d["S"]["kind"] == "HOLD"]
    wait = [d for d in ok if d["S"]["kind"] in ("WAIT", "SKIP")]
    h1, h2 = st.columns([2, 1.4], vertical_alignment="bottom")
    h1.markdown(f"### Today's signals\n<span class='muted'>{len(act)} to act on · {len(hold)} holding · "
                f"{len(wait)} waiting — updated {now_ist():%H:%M}</span>", unsafe_allow_html=True)
    view = h2.segmented_control("Show", ["All", "Act now", "Holding", "Waiting"], default="All", key="board_view",
                                label_visibility="collapsed") or "All"
    shown = {"All": rows, "Act now": act, "Holding": hold, "Waiting": wait}[view]
    shown = sorted(shown, key=lambda d: (ORDER.get(d["S"]["kind"], 9) if d["ok"] else 9,
                                         CONF_ORDER.get(d["S"]["confidence"][0], 9) if d["ok"] else 9))
    if not shown:
        ui.empty_state("☕", "Nothing here right now",
                       "No stock in your watchlist needs action. Waiting is a decision too — the app beeps when that changes.")
        return
    for i in range(0, len(shown), 3):
        cols = st.columns(3, gap="small")
        for col, d in zip(cols, shown[i:i + 3]):
            with col:
                card(d)


board()
st.write("")


# ---------------------------------------------------------------- your trades
@st.fragment(run_every=30 if P.live and is_open else None)
def my_trades():
    trades = [t for t in journal.load_trades() if t["status"] == "OPEN"]
    h1, h2 = st.columns([3, 1], vertical_alignment="bottom")
    h1.markdown("### Your open trades")
    if h2.button("All trades", icon=":material/account_balance_wallet:", width="stretch", type="tertiary"):
        st.switch_page("views/trades_page.py")
    if not trades:
        ui.empty_state("📝", "No open trades", "When a signal says BUY, use <b>Paper-trade</b> to practise, or "
                       "<b>I bought this</b> to track a real Groww trade.")
        return
    prices = {t["ticker"]: px for t in trades if (px := core.trade_price(t)) is not None}
    for t in journal.auto_close(prices):
        st.toast(f"{t['symbol']}: {t['exit_reason']} reached — trade closed", icon="📒")
    tiles = []
    for t in trades[:6]:
        px = prices.get(t["ticker"])
        rs, pc = journal.pnl(t, px)
        tag = "Real" if t.get("kind") == "real" else "Paper"
        tiles.append(ui.tile(f"{t['symbol']} · {tag}", f"₹{rs:+,.0f}",
                             f"{pc:+.2f}% · {t['qty']:,} @ ₹{t['entry']:,.2f}" + (f" · stop ₹{t['stop']:,.2f}" if t.get("stop") else ""),
                             ui.signed_color(rs)))
    st.markdown(ui.grid(tiles), unsafe_allow_html=True)


my_trades()

if not P.pro:
    st.write("")
    with st.expander("New here? How to use the signals (1 minute)", icon=":material/school:"):
        st.markdown("""
1. **BUY** — the setup just appeared. Open it to see the price, the **stop-loss** (where you get out if it goes wrong)
   and how many shares to buy so one loss costs only your chosen risk.
2. **HOLD** — the strategy is already in a trade. If you're in, keep holding and keep your stop-loss. If you're not, don't chase it.
3. **SELL** — time to exit what you bought.
4. **WAIT** — nothing to do. The card shows the price that would trigger a BUY.
5. **Confidence** tells you how well this method worked on that stock in tests it was never tuned on.
   Prefer **High**; skip **Not proven**.

Practise with **Paper-trade** for a few weeks before using real money.
""")
