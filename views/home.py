"""Home: today's briefing, the best setups in the market, your watchlist and your open trades."""
import streamlit as st

import core
import journal
import scanner
import ui
from views.common import now_ist, open_chart, price_every

P = core.prefs()
is_open, status = core.market()
interval = core.STYLE_INTERVALS[P.style][0]
ORDER = {"BUY": 0, "SHORT": 0, "SELL": 1, "HOLD": 2, "WAIT": 3, "SKIP": 4}
CONF_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Not proven": 3}
SCAN_ON = P.scan in scanner.UNIVERSES and P.style == "Swing"
LIVE_EVERY = price_every(P, floor=5, slow=60)   # prices on this page: every 5 s with a tick stream, else every minute


# ---------------------------------------------------------------- today's briefing
def _summary(m: dict) -> str:
    """One or two plain sentences: the market, what the scan found, what the watchlist needs."""
    parts = []
    if "trend" in m:
        word = {"UP": "rising", "DOWN": "falling", "SIDEWAYS": "moving sideways"}[m["trend"]]
        mood_ = (" and traders are <b>" + {"Calm": "calm", "Normal": "steady", "Nervous": "nervous", "Fearful": "fearful"}[m["vix"][1]]
                 + "</b>") if "vix" in m else ""
        parts.append(f"The market is <b>{word}</b>{mood_}.")
    if SCAN_ON:
        s = scanner._state()
        pk = scanner.picks(s["rows"]) if s["rows"] else {"new": [], "near": []}
        if s["running"]:
            parts.append(f"Checking {ui.esc(P.scan)} for setups — <b>{len(pk['new'])}</b> found so far.")
        elif s["rows"]:
            n, k = len(pk["new"]), len(pk["near"])
            parts.append((f"<b>{n} stock{'s' * (n != 1)}</b> in {ui.esc(P.scan)} {'have' if n != 1 else 'has'} a tested buy setup today"
                          if n else f"No tested buy setup in {ui.esc(P.scan)} today")
                         + (f", and <b>{k}</b> {'are' if k != 1 else 'is'} close to one." if k else "."))
    b = st.session_state.get("board") or {}
    act = [d["symbol"] for d in b.values() if d.get("ok") and d["S"]["kind"] in ("BUY", "SHORT", "SELL")]
    if act:
        parts.append(f"In your watchlist, <b>{', '.join(ui.esc(x) for x in act[:3])}</b>{' and others' if len(act) > 3 else ''} "
                     f"need{'s' * (len(act) == 1)} action.")
    elif b:
        parts.append("Nothing in your watchlist needs action.")
    return " ".join(parts)


@st.fragment(run_every=LIVE_EVERY)
def briefing():
    m = core.market_mood()
    who = f", {ui.esc(P.name)}" if P.name else ""
    facts = []
    if "trend" in m and m.get("vs200") is not None:
        facts.append(("NIFTY vs 200-day average", f"<span style='color:{ui.signed_color(m['vs200'])}'>{m['vs200']:+.1f}%</span>"))
    if "vix" in m:
        lvl, word = m["vix"]
        col = ui.color({"Calm": "up", "Nervous": "warn", "Fearful": "down"}.get(word))
        facts.append(("Fear gauge · India VIX", f"<span class='num'>{lvl:.1f}</span><small"
                      + (f" style='color:{col}'" if col else "") + f">{word}</small>"))
    facts.append(("Your risk per trade", f"<span class='num'>₹{P.capital * P.risk_pct / 100:,.0f}</span><small>{P.risk_pct:g}% of "
                                         f"₹{P.capital:,.0f}</small>"))
    right = ""
    if "nifty" in m:
        px, pct = m["nifty"]
        d = core.load_daily("^NSEI")
        closes = d.Close.tail(120).tolist() + ([px] if is_open else [])
        col = ui.signed_color(closes[-1] - closes[0]) if closes else ui.MUTED
        right = (f"<div class='r'><div class='top'><div class='over'>NIFTY 50 · last 6 months</div><div class='big'>{px:,.2f}</div>"
                 f"<div class='chg' style='color:{ui.signed_color(pct)}'>{'▲' if pct > 0 else '▼' if pct < 0 else ''} "
                 f"{abs(pct):.2f}% today</div></div><div class='chart'>{ui.sparkline(closes, col, .35)}</div></div>")
    st.markdown(
        f"<div class='brief'><div class='l'><div class='over'>{now_ist():%A, %d %B} · {ui.esc(core.market_clock())}</div>"
        f"<h1>{core.greeting()}{who}<span class='g'>.</span></h1><div class='sum'>{_summary(m)}</div>"
        "<div class='facts'>" + "".join(f"<div><div class='k'>{k}</div><div class='v'>{v}</div></div>" for k, v in facts)
        + f"</div></div>{right}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- one instrument, analysed
def snapshot(sym: str) -> dict:
    try:
        c = core.build(core.Sel(symbol=sym, interval=interval), P)
        if c is None:
            return {"ok": False, "symbol": sym, "err": "No data for this symbol"}
        S = core.signal(c)
        closes = c.raw["Close"].tail(90)
        return {"ok": True, "symbol": sym, "ticker": c.ticker, "name": core.name_of(sym), "ltp": c.ltp, "chg_pct": c.chg_pct, "S": S,
                "tag": S.get("news_tag"), "spark": closes.tolist(), "spark_up": bool(closes.iloc[-1] >= closes.iloc[0]),
                "strat": core.SHORT_NAME.get(c.strat_name, c.strat_name), "at": now_ist()}
    except Exception as e:  # noqa: BLE001 — one bad symbol shouldn't break the page
        return {"ok": False, "symbol": sym, "err": str(e)[:120]}


def card(d: dict, prefix: str = ""):
    """A setup as a card (used for the market scan)."""
    kind = d["S"]["kind"]
    with st.container(key=f"sigc-{kind}-{prefix}{ui.slug(d['symbol'])}"):
        S = d["S"]
        col = ui.color(S["color"])
        lvl, _, why = S["confidence"]
        name = d["name"] if d["name"].upper() != d["symbol"] else ""
        tag = d.get("tag")
        st.markdown(
            f"<div class='sc'><div class='top'><div><div class='nm'>{ui.esc(d['symbol'])}</div>"
            f"<div class='co'>{ui.esc(name) or '&nbsp;'}</div></div>"
            f"<div class='px'><div class='v'>₹{d['ltp']:,.2f}</div>"
            f"<div class='c' style='color:{ui.signed_color(d['chg_pct'])}'>{d['chg_pct']:+.2f}%</div></div></div>"
            f"<div class='spark'>{ui.sparkline(d.get('spark', []), ui.up_txt() if d.get('spark_up') else ui.down_txt())}</div>"
            f"<div class='mid'>{ui.badge(S['verdict'], col)}"
            f"<span class='conf' title='{ui.esc(why)}'>{ui.conf_meter(lvl)}{ui.esc(lvl)}</span></div>"
            f"<div class='line'>{ui.esc(S['headline'])}</div>"
            f"<div class='foot'><span>{ui.esc(d['strat'])}</span>"
            + (f"<span style='color:{ui.color(tag[1])}'>{ui.esc(tag[0])}</span>" if tag else "") + "</div></div>",
            unsafe_allow_html=True)
        if st.button("Open chart", key=f"open-{prefix}{d['symbol']}", icon=":material/arrow_forward:", width="stretch", type="tertiary"):
            open_chart(d["symbol"])


def row(d: dict):
    """A watchlist instrument as one table row."""
    kind = d["S"]["kind"] if d["ok"] else "ERR"
    with st.container(key=f"wlr-{kind}-{ui.slug(d['symbol'])}", horizontal=True, wrap=False, vertical_alignment="center", gap="small"):
        if not d["ok"]:
            st.markdown(f"<div class='wl'><div><div class='nm'>{ui.esc(d['symbol'])}</div></div><div class='c-spark'></div>"
                        f"<div class='c-px'></div><div></div><div class='c-conf'></div>"
                        f"<div class='c-line muted'>Couldn't analyse: {ui.esc(d['err'])}</div><div class='c-news'></div></div>",
                        unsafe_allow_html=True, width="stretch")
        else:
            S = d["S"]
            lvl, _, why = S["confidence"]
            name = d["name"] if d["name"].upper() != d["symbol"] else ""
            tag = d.get("tag")
            st.markdown(
                f"<div class='wl'><div style='min-width:0'><div class='nm'>{ui.esc(d['symbol'])}</div><div class='co'>{ui.esc(name)}</div></div>"
                f"<div class='c-spark'>{ui.sparkline(d.get('spark', []), ui.up_txt() if d.get('spark_up') else ui.down_txt(), .2)}</div>"
                f"<div class='c-px'><div class='v'>{d['ltp']:,.2f}</div>"
                f"<div class='c' style='color:{ui.signed_color(d['chg_pct'])}'>{d['chg_pct']:+.2f}%</div></div>"
                f"<div>{ui.badge(S['verdict'], ui.color(S['color']))}</div>"
                f"<div class='c-conf' title='{ui.esc(why)}'>{ui.conf_meter(lvl)}{ui.esc(lvl)}</div>"
                f"<div class='c-line'>{ui.esc(S['headline'])}</div>"
                f"<div class='c-news'" + (f" style='color:{ui.color(tag[1])}'>{ui.esc(tag[0])}" if tag else ">") + "</div></div>",
                unsafe_allow_html=True, width="stretch")
        if st.button("", key=f"open-{d['symbol']}", icon=":material/arrow_forward:", type="tertiary", help=f"Open {d['symbol']}"):
            open_chart(d["symbol"])


# ---------------------------------------------------------------- your watchlist
@st.fragment(run_every=LIVE_EVERY)
def board():
    wl = P.watchlist
    if not wl:
        ui.empty_state("", "Your watchlist is empty", "Add stocks or indices on the Chart page (Watch) or in Settings.")
        return
    b = st.session_state.setdefault("board", {})
    key = (P.style, core.candle_key(interval, P.closed_only), P.capital, P.risk_pct, P.ind, P.closed_only, P.news)
    todo = [s for s in wl if s not in b or b[s]["key"] != key]
    if todo:
        bar = st.progress(0.0, text=f"Downloading prices for {len(todo)} symbols…")
        core.prefetch([core.data.to_yahoo(s) for s in todo], interval, P)
        if P.news:
            core.prefetch_news(todo)
        for i, s in enumerate(todo):
            bar.progress(i / len(todo), text=f"Checking {s} ({i + 1} of {len(todo)}) — the first check of the day takes a moment")
            b[s] = {"key": key, **snapshot(s)}
        bar.empty()
    rows = [b[s] for s in wl if s in b]
    if core.market()[0]:   # signals are decided per candle, but the price shown should be the one trading now
        for d in rows:
            if d["ok"] and (q := core.quote(d["ticker"])):
                d["ltp"], d["chg_pct"] = q
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
    h1.markdown(ui.section("Your watchlist", f"<b style='color:{ui.color('accent')}'>{len(act)}</b> to act on · {len(hold)} holding · "
                           f"{len(wait)} waiting · {P.style.lower()} signals · updated {now_ist():%H:%M:%S}"), unsafe_allow_html=True)
    view = h2.segmented_control("Show", ["All", "Act now", "Holding", "Waiting"], default="All", key="board_view",
                                label_visibility="collapsed") or "All"
    shown = {"All": rows, "Act now": act, "Holding": hold, "Waiting": wait}[view]
    shown = sorted(shown, key=lambda d: (ORDER.get(d["S"]["kind"], 9) if d["ok"] else 9,
                                         CONF_ORDER.get(d["S"]["confidence"][0], 9) if d["ok"] else 9))
    if not shown:
        ui.empty_state("", "Nothing here right now",
                       "No stock in your watchlist needs action. Waiting is a decision too — the app beeps when that changes.")
        return
    with st.container(key="wltable"):
        st.markdown("<div class='wl head'><div>Instrument</div><div class='c-spark'>90 days</div><div class='r'>Price</div>"
                    "<div>Signal</div><div class='c-conf'>Confidence</div><div class='c-line'>What it means</div>"
                    "<div class='c-news r'>News</div></div>", unsafe_allow_html=True)
        for d in shown:
            row(d)


# ---------------------------------------------------------------- best setups in the whole index (not only the watchlist)
def scan_card(r: dict):
    near = r["badge"] != "BUY"
    py = r.get("per_year")
    card({"symbol": r["symbol"], "name": r["name"], "ltp": r["ltp"], "chg_pct": r["chg_pct"],
          "spark": r["spark"], "spark_up": r["spark"][-1] >= r["spark"][0] if r["spark"] else True, "strat": r["strat"],
          "tag": (f"{py:+.0f}%/yr on unseen years", "muted") if py is not None else None,
          "S": {"kind": "WAIT" if near else "BUY", "color": "accent" if near else "up", "verdict": r["badge"],
                "confidence": tuple(r["conf"]), "headline": r["line"]}}, prefix="scan-")


def _scan_every() -> int | None:
    s = scanner._state()
    return 4 if s["running"] or s["key"] is None else (300 if P.live else None)


@st.fragment(run_every=_scan_every() if SCAN_ON else None)
def setups():
    sc = scanner.ensure(P)
    pk = scanner.picks(sc["rows"])
    prog = (f"checking {sc['done']} of {sc['total']} stocks…" if sc["running"] else f"{len(sc['rows'])} stocks checked")
    h1, h2 = st.columns([2, 1.4], vertical_alignment="bottom")
    h1.markdown(ui.section("Best setups today", f"Scanned {ui.esc(sc['universe'])} · {prog} · only stocks where the method "
                           "passed its test on years it never saw"), unsafe_allow_html=True)
    labels = {"new": f"Buy now ({len(pk['new'])})", "near": f"Close to a buy ({len(pk['near'])})"}
    view = h2.segmented_control("Setups", list(labels), default="new", format_func=labels.get, key="scan_view",
                                label_visibility="collapsed") or "new"
    shown = pk[view][:6]
    if sc["running"]:
        st.progress(sc["done"] / max(sc["total"], 1))
    if not shown:
        if sc["running"]:
            st.caption("Results appear here as stocks are checked — the first scan of the day takes a few minutes.")
        else:
            ui.empty_state("", "No fresh buy signals today" if view == "new" else "Nothing is close to a buy level",
                           "That's normal — good setups don't appear every day, and forcing a trade is how money is lost. "
                           + ("Check <b>Close to a buy</b> for what may trigger next." if view == "new" else ""))
        return
    for i in range(0, len(shown), 3):
        for col, r in zip(st.columns(3, gap="small"), shown[i:i + 3]):
            with col:
                scan_card(r)
    more = len(pk[view]) - len(shown)
    st.caption((f"+{more} more with a weaker record not shown · " if more > 0 else "") + "Ranked by the result on years the method "
               "was never tuned on. A strong record makes a profit more likely, not certain — always use the stop-loss.")


top = st.container()     # the briefing is drawn last, so its summary can count what the sections below found
if SCAN_ON:
    scanner.ensure(P)
    setups()
    st.write("")
board()
st.write("")
with top:
    briefing()


# ---------------------------------------------------------------- your trades
@st.fragment(run_every=price_every(P, floor=5, slow=30))
def my_trades():
    trades = [t for t in journal.load_trades() if t["status"] == "OPEN"]
    h1, h2 = st.columns([3, 1], vertical_alignment="bottom")
    h1.markdown(ui.section("Your open trades"), unsafe_allow_html=True)
    if h2.button("All trades", icon=":material/account_balance_wallet:", width="stretch", type="tertiary"):
        st.switch_page("views/trades_page.py")
    if not trades:
        ui.empty_state("", "No open trades", "When a signal says BUY, use <b>Paper-trade</b> to practise, or "
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
1. **BUY** — the setup just appeared. Open it to see the price, the **stop-loss** (where you get out if it goes wrong),
   the **target** (where you take profit) and how many shares to buy so one loss costs only your chosen risk.
2. **HOLD** — the strategy is already in a trade. If you're in, keep holding and keep your stop-loss. If you're not, don't chase it.
3. **SELL** — time to exit what you bought.
4. **WAIT** — nothing to do. The row shows the price that would trigger a BUY.
5. **Confidence** tells you how well this method worked on that stock in tests it was never tuned on.
   Prefer **High**; skip **Not proven**.

Practise with **Paper-trade** for a few weeks before using real money.
""")
