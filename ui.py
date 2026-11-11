"""Design system: colour tokens for the light and dark theme, the app's CSS and small HTML components
rendered with st.markdown.

Every surface, border and text colour comes from the CSS variables set in `inject_css()` for the active theme,
so pages never hard-code a colour. Green and red are reserved for market data (up / down); the brand accent is blue."""
import html
import re
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"

# constants used in Plotly figures and as fallbacks (6-digit hex: callers append alpha, e.g. f"{col}1f")
UP, DOWN, WARN, CAUTION = "#12b886", "#ef5350", "#f0a13a", "#e9a23b"
ACCENT = "#4c84f5"
MUTED = "#8a90a0"            # mid grey: readable on both themes (charts, plotly)
SURFACE = "rgba(0,0,0,0)"    # charts are transparent and sit on the app background
GRID = "rgba(128,128,128,0.14)"

TOKENS = {
    "dark": {"bg": "#0b0d11", "surface": "#12151b", "surface2": "#181c24", "line": "#232834", "line2": "#2e3442",
             "text": "#e7e9ee", "muted": "#8a90a0", "faint": "#5d6373", "up": "#1ec997", "down": "#f4655a",
             "warn": "#f0a13a", "accent": "#6b9bff", "shadow": "0 1px 2px rgba(0,0,0,.35)"},
    "light": {"bg": "#f5f6f8", "surface": "#ffffff", "surface2": "#f0f2f5", "line": "#e3e6eb", "line2": "#d3d8e0",
              "text": "#141821", "muted": "#626a7a", "faint": "#9aa1ae", "up": "#0a8f66", "down": "#d43a34",
              "warn": "#b76a00", "accent": "#2f6be0", "shadow": "0 1px 2px rgba(16,24,40,.06)"},
}

CSS = """
<style>
:root { __VARS__ }

/* ------------------------------------------------------------ page shell */
.stApp { background: var(--bg); }
.block-container { padding-top: 4.4rem; padding-bottom: 3.5rem; max-width: 1400px; }
#MainMenu, footer { visibility: hidden; }
html, body, .stApp { font-feature-settings: "cv11", "ss01"; -webkit-font-smoothing: antialiased; }
header[data-testid="stHeader"] { background: color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter: saturate(160%) blur(10px); border-bottom: 1px solid var(--line); height: 3.5rem; }
[data-testid="stLogo"] { height: 1.75rem; }
h1, h2, h3, h4, h5 { letter-spacing: -0.01em; }
.stMarkdown h3 { font-size: 17px; font-weight: 650; padding: 0; margin: 0; }
.stMarkdown h5 { font-size: 14px; font-weight: 650; }
.stMarkdown a { color: var(--accent); }

/* native widgets: same surfaces and borders as our own components */
[data-testid="stExpander"] details { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  box-shadow: var(--shadow); }
[data-testid="stExpander"] summary { font-weight: 600; font-size: 14px; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-color: var(--line) !important;
  border-radius: 12px; }
[data-testid="stTabs"] [data-baseweb="tab"] { font-weight: 600; font-size: 14px; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
[data-testid="stForm"] { background: var(--surface); border-color: var(--line); border-radius: 14px; }
.stButton button, .stDownloadButton button, .stFormSubmitButton button { font-weight: 600; border-radius: 9px; }
[data-testid="stCaptionContainer"] { color: var(--muted); }
[data-testid="stProgress"] p { font-size: 13px; color: var(--muted); }

/* ------------------------------------------------------------ text helpers */
.muted, .note, .sub { color: var(--muted); }
.note { font-size: 12.5px; line-height: 1.55; }
.kicker, .card h4, .tile .l, .steps .l, .sec .k { font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
  font-weight: 600; color: var(--muted); }
.num, .tile .v, .tk .v, .tk .c, .sc .px, .hero .price, .rangelbl { font-variant-numeric: tabular-nums; }
.msg { font-size: 14px; line-height: 1.6; margin-top: 12px; }
.msg code { font-size: 12.5px; }

/* ------------------------------------------------------------ ticker bar (every page) */
.ticker { display: flex; align-items: stretch; background: var(--surface); border: 1px solid var(--line);
  border-radius: 12px; box-shadow: var(--shadow); margin: 0 0 22px; overflow: hidden; }
.ticker .cells { display: flex; flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; }
.ticker .cells::-webkit-scrollbar { display: none; }
.tk { flex: 1 0 auto; padding: 10px 18px; border-right: 1px solid var(--line); white-space: nowrap; }
.tk .n { font-size: 10.5px; letter-spacing: .07em; text-transform: uppercase; font-weight: 600; color: var(--muted); }
.tk .r { display: flex; align-items: baseline; gap: 8px; margin-top: 2px; }
.tk .v { font-size: 15px; font-weight: 650; }
.tk .c { font-size: 12px; font-weight: 600; }
.ticker .status { display: flex; flex-direction: column; justify-content: center; align-items: flex-end; padding: 8px 16px;
  white-space: nowrap; background: var(--surface2); }
.ticker .status .t { font-size: 11.5px; color: var(--muted); margin-top: 3px; font-variant-numeric: tabular-nums; }
.live { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 650; }
.live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; display: inline-block; }
.live.on i { box-shadow: 0 0 0 0 currentColor; animation: pulse 1.8s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 60%, transparent); }
                   70%, 100% { box-shadow: 0 0 0 7px transparent; } }

/* ------------------------------------------------------------ headers */
.pagehead { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; margin: 0 0 18px; }
.pagehead h1 { font-size: 26px; font-weight: 700; margin: 0; line-height: 1.2; padding: 0; letter-spacing: -0.02em; }
.pagehead .sub { font-size: 14px; margin-top: 5px; }
.sec { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.sec .t { font-size: 17px; font-weight: 650; letter-spacing: -0.01em; }
.sec .d { font-size: 13px; color: var(--muted); margin-top: 3px; }

/* ------------------------------------------------------------ pills, dots, badges */
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px;
  font-weight: 600; border: 1px solid; white-space: nowrap; line-height: 1.5; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.badge { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 6px; font-size: 12.5px; font-weight: 700;
  letter-spacing: .04em; }
.meter { display: inline-flex; gap: 2px; align-items: flex-end; height: 11px; vertical-align: -1px; margin-right: 6px; }
.meter i { width: 3px; border-radius: 1px; background: var(--line2); display: inline-block; }
.meter i:nth-child(1) { height: 4px; } .meter i:nth-child(2) { height: 6px; }
.meter i:nth-child(3) { height: 8.5px; } .meter i:nth-child(4) { height: 11px; }

/* ------------------------------------------------------------ cards, tiles, stats */
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px;
  box-shadow: var(--shadow); }
.card h4 { margin: 0; padding: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 10px; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px;
  box-shadow: var(--shadow); min-width: 0; }
.tile .v { font-size: 19px; font-weight: 650; margin-top: 4px; letter-spacing: -0.01em; }
.tile .s { font-size: 12px; margin-top: 2px; color: var(--muted); }
.card .tile, .stats .tile { background: var(--surface2); box-shadow: none; }
/* one panel with divided cells — page-level key figures */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); overflow: hidden; }
.stats .tile { background: transparent; border: 0; border-radius: 0; padding: 16px 20px;
  box-shadow: 1px 0 0 var(--line), 0 1px 0 var(--line); }
.stats .tile .v { font-size: 22px; }

[data-testid="stMarkdownContainer"] > .grid, [data-testid="stMarkdownContainer"] > .stats { margin-bottom: 14px; }
.modebar { opacity: 0; transition: opacity .15s; } .js-plotly-plot:hover .modebar { opacity: 1; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 5px 11px; border-radius: 8px; font-size: 12.5px;
  border: 1px solid var(--line); background: var(--surface2); }

.rangebar { position: relative; height: 4px; border-radius: 2px; margin: 12px 0 6px;
  background: linear-gradient(90deg, var(--down), var(--line2) 50%, var(--up)); }
.rangebar .m { position: absolute; top: -4px; width: 3px; height: 12px; background: var(--text); border-radius: 2px;
  box-shadow: 0 0 0 2px var(--surface); }
.rangelbl { display: flex; justify-content: space-between; font-size: 11.5px; color: var(--muted); }

.callout { display: flex; gap: 10px; margin-top: 12px; padding: 10px 12px; border-radius: 10px; font-size: 13px; line-height: 1.5;
  border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent); background: color-mix(in srgb, var(--warn) 9%, transparent); }
.callout b.i { color: var(--warn); font-weight: 800; }

/* ------------------------------------------------------------ chart page: instrument header */
.hero { display: flex; flex-wrap: wrap; gap: 16px 28px; align-items: center; background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; padding: 16px 20px; box-shadow: var(--shadow); margin: 4px 0 14px; }
.hero .id { flex: 0 1 300px; min-width: 220px; }
.hero .sym { font-size: 22px; font-weight: 700; line-height: 1.15; letter-spacing: -0.02em; }
.hero .sub { font-size: 12.5px; margin-top: 4px; }
.hero .pills { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.hero .quote { flex: 0 0 auto; }
.hero .price { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }
.hero .chg { font-size: 14px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
.hero .facts { flex: 1 1 520px; min-width: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0; }
.hero .facts .tile { background: transparent; border: 0; border-left: 1px solid var(--line); border-radius: 0;
  padding: 2px 16px; box-shadow: none; }
.hero .facts .tile .v { font-size: 16px; }

/* ------------------------------------------------------------ signal panel */
.sigpanel { position: relative; overflow: hidden; }
.sigpanel::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--sig, var(--line2)); }
.sigpanel .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.verdict { font-size: 34px; font-weight: 800; letter-spacing: -0.01em; line-height: 1.1; margin: 10px 0 2px; }
.sigpanel .grid { grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); margin-top: 14px; }
.sigpanel .tile .v { font-size: 16px; white-space: nowrap; }
.sigpanel .tile .l { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.steps { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
.steps ol { margin: 8px 0 0; padding: 0; list-style: none; counter-reset: s; }
.steps li { position: relative; font-size: 14px; line-height: 1.55; margin: 0 0 9px; padding-left: 30px; counter-increment: s; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: 1px; width: 20px; height: 20px; border-radius: 50%;
  background: var(--surface2); border: 1px solid var(--line2); font-size: 11px; font-weight: 700; display: flex;
  align-items: center; justify-content: center; color: var(--muted); }
.meta { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 12.5px; line-height: 1.55;
  color: var(--muted); }
.meta b { color: var(--text); font-weight: 600; }

/* ------------------------------------------------------------ Home: signal cards */
[class*="st-key-sigc-"] { background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  padding: 16px 18px 10px; box-shadow: var(--shadow); position: relative; overflow: hidden; gap: .35rem;
  transition: border-color .15s ease, transform .15s ease; }
[class*="st-key-sigc-"]:hover { border-color: var(--line2); transform: translateY(-1px); }
[class*="st-key-sigc-"]::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--line2); }
[class*="st-key-sigc-BUY-"]::before, [class*="st-key-sigc-HOLD-"]::before { background: var(--up); }
[class*="st-key-sigc-SHORT-"]::before { background: var(--down); }
[class*="st-key-sigc-SELL-"]::before { background: var(--warn); }
[class*="st-key-sigc-"] .stButton button { border: 0; border-top: 1px solid var(--line); border-radius: 0; color: var(--muted);
  font-size: 13px; padding-top: 8px; min-height: 0; }
[class*="st-key-sigc-"] .stButton button:hover { color: var(--accent); background: transparent; }
.sc { padding-bottom: 14px; }
.sc .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.sc .nm { font-size: 15.5px; font-weight: 700; line-height: 1.2; letter-spacing: -0.01em; }
.sc .co { font-size: 12px; color: var(--muted); margin-top: 3px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; max-width: 190px; }
.sc .px { text-align: right; }
.sc .px .v { font-size: 15.5px; font-weight: 650; }
.sc .px .c { font-size: 12.5px; font-weight: 600; margin-top: 2px; }
.sc .spark { height: 38px; margin: 10px 0 12px; }
.sc .spark svg { width: 100%; height: 100%; display: block; }
.sc .mid { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.sc .conf { font-size: 12px; color: var(--muted); white-space: nowrap; }
.sc .line { font-size: 13px; line-height: 1.45; margin-top: 10px; min-height: 38px; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sc .foot { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--muted); margin-top: 6px;
  white-space: nowrap; overflow: hidden; }
.sc .foot span { overflow: hidden; text-overflow: ellipsis; }

/* ------------------------------------------------------------ news list */
.newsrow { display: flex; gap: 12px; align-items: baseline; padding: 10px 0; border-top: 1px solid var(--line); }
.newsrow a { color: var(--text) !important; text-decoration: none; font-size: 14px; line-height: 1.45; font-weight: 500; }
.newsrow a:hover { color: var(--accent) !important; }
.newsrow .src { font-size: 12px; color: var(--muted); margin-top: 2px; }

/* ------------------------------------------------------------ empty state, welcome */
.empty { text-align: center; padding: 34px 16px; border: 1px dashed var(--line2); border-radius: 14px; }
.empty .ic { width: 36px; height: 36px; border-radius: 10px; margin: 0 auto; background: var(--surface2);
  border: 1px solid var(--line); display: flex; align-items: center; justify-content: center; }
.empty .ic i { width: 14px; height: 2px; background: var(--faint); border-radius: 1px; display: block; }
.empty .t { font-size: 15px; font-weight: 650; margin-top: 10px; }
.empty .x { font-size: 13.5px; margin-top: 4px; color: var(--muted); }
.welcome { text-align: center; margin: 18px 0 8px; }
.welcome img { height: 44px; }
.welcome h1 { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; margin: 14px 0 6px; padding: 0; }
.welcome .lead { font-size: 15.5px; color: var(--muted); max-width: 560px; margin: 0 auto; line-height: 1.55; }

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .pagehead h1 { font-size: 22px; }
  .hero .facts .tile { border-left: 0; padding: 6px 0; }
  .ticker .status { display: none; }
  .verdict { font-size: 28px; }
}
</style>
"""


def dark() -> bool:
    """Best guess of the active theme (Streamlit infers it from the background; unknown -> dark)."""
    try:
        return st.context.theme.type != "light"
    except Exception:  # noqa: BLE001
        return True


def tokens() -> dict:
    return TOKENS["dark" if dark() else "light"]


def inject_css():
    """The app's CSS with the active theme's colour tokens, and the brand logo in the top bar."""
    t = tokens()
    st.markdown(CSS.replace("__VARS__", " ".join(f"--{k}:{v};" for k, v in t.items())), unsafe_allow_html=True)
    try:
        st.logo(str(ASSETS / f"logo-{'dark' if dark() else 'light'}.svg"), size="large")
    except Exception:  # noqa: BLE001 — the logo is decoration
        pass


def up_txt() -> str:
    return tokens()["up"]


def down_txt() -> str:
    return tokens()["down"]


def text_color() -> str:
    return tokens()["text"]


def plotly_layout(height: int, **kw) -> dict:
    """Transparent, theme-matched Plotly layout."""
    layout = dict(template="plotly_dark" if dark() else "plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                  plot_bgcolor="rgba(0,0,0,0)", height=height, font=dict(color=text_color(), size=12, family="Inter, sans-serif"),
                  margin=dict(l=8, r=8, t=30, b=8))
    layout.update(kw)
    return layout


def esc(x) -> str:
    return html.escape(str(x))


def signed_color(v: float) -> str:
    return up_txt() if v > 0 else down_txt() if v < 0 else MUTED


def color(key: str | None) -> str | None:
    """Theme-aware colour for a semantic key ('up', 'down', 'warn', 'accent', 'muted') or a literal colour."""
    if key is None:
        return None
    t = tokens()
    return {"up": t["up"], "down": t["down"], "warn": t["warn"], "accent": t["accent"], "muted": MUTED}.get(key, key)


def slug(x: str) -> str:
    """Safe piece of a widget key / CSS class."""
    return re.sub(r"[^A-Za-z0-9]", "_", str(x))


def pill(text: str, col: str) -> str:
    return (f"<span class='pill' style='color:{col};border-color:{col}44;background:{col}14'>"
            f"<span class='dot' style='background:{col}'></span>{esc(text)}</span>")


def badge(text: str, col: str) -> str:
    """Solid-tint label for a verdict (BUY / HOLD / WAIT…)."""
    return f"<span class='badge' style='color:{col};background:{col}1c'>{esc(text)}</span>"


CONF_BARS = {"High": (4, "up"), "Medium": (3, "warn"), "Low": (2, "warn"), "Not proven": (1, "down")}


def conf_meter(level: str) -> str:
    """Four small bars, like a signal-strength icon, filled by confidence level."""
    n, key = CONF_BARS.get(level, (0, "muted"))
    col = color(key)
    return "<span class='meter'>" + "".join(f"<i{f' style=\"background:{col}\"' if i < n else ''}></i>" for i in range(4)) + "</span>"


def tile(label: str, value: str, sub: str = "", col: str | None = None) -> str:
    style = f" style='color:{col}'" if col else ""
    sub_html = f"<div class='s'>{sub}</div>" if sub else ""
    return f"<div class='tile'><div class='l'>{esc(label)}</div><div class='v'{style}>{value}</div>{sub_html}</div>"


def grid(tiles: list[str]) -> str:
    return "<div class='grid'>" + "".join(tiles) + "</div>"


def stats(tiles: list[str]) -> str:
    """Key figures of a page as one panel with divided cells."""
    return "<div class='stats'>" + "".join(tiles) + "</div>"


def chip(icon: str, text: str) -> str:
    """`icon` is a colour key ('up' / 'down' / 'muted') drawn as a dot, or any short text."""
    mark = f"<span class='dot' style='background:{color(icon)}'></span>" if icon in ("up", "down", "muted", "warn") else icon
    return f"<span class='chip'>{mark}<span>{text}</span></span>"


def callout(text: str) -> str:
    return f"<div class='callout'><b class='i'>!</b><div>{esc(text)}</div></div>"


def page_header(title: str, subtitle: str = "", right: str = ""):
    st.markdown(f"<div class='pagehead'><div><h1>{esc(title)}</h1>"
                + (f"<div class='sub'>{subtitle}</div>" if subtitle else "")
                + f"</div><div>{right}</div></div>", unsafe_allow_html=True)


def section(title: str, desc: str = "") -> str:
    return (f"<div class='sec'><div><div class='t'>{esc(title)}</div>"
            + (f"<div class='d'>{desc}</div>" if desc else "") + "</div></div>")


def empty_state(icon: str, title: str, text: str = ""):
    """`icon` is kept for callers but not drawn: the empty state uses one neutral mark."""
    st.markdown(f"<div class='empty'><div class='ic'><i></i></div><div class='t'>{esc(title)}</div>"
                + (f"<div class='x'>{text}</div>" if text else "") + "</div>", unsafe_allow_html=True)


def market_strip(quotes: list[tuple[str, float, float]], is_open: bool, status: str, clock: str) -> str:
    """The ticker bar. quotes: (name, last price, % change)."""
    cells = []
    for name, px, pct in quotes:
        col = signed_color(pct)
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else ""
        cells.append(f"<div class='tk'><div class='n'>{esc(name)}</div><div class='r'><span class='v'>{px:,.2f}</span>"
                     f"<span class='c' style='color:{col}'>{arrow} {abs(pct):.2f}%</span></div></div>")
    st_col = up_txt() if is_open else MUTED
    return ("<div class='ticker'><div class='cells'>" + "".join(cells) + "</div>"
            f"<div class='status'><span class='live{' on' if is_open else ''}' style='color:{st_col}'><i></i>{esc(status)}</span>"
            f"<span class='t'>{esc(clock)} IST</span></div></div>")


def range_bar(low: float, high: float, ltp: float, label: str = "Day range") -> str:
    pos = 50 if high <= low else max(0, min(100, (ltp - low) / (high - low) * 100))
    return (f"<div class='l'>{esc(label)}</div>"
            f"<div class='rangebar'><div class='m' style='left:calc({pos:.1f}% - 1px)'></div></div>"
            f"<div class='rangelbl'><span>{low:,.2f}</span><span>{high:,.2f}</span></div>")


def sparkline(values: list[float], col: str) -> str:
    """Small area chart (inline SVG) of a price series, stretched to its container."""
    v = [float(x) for x in values if x == x]
    if len(v) < 3:
        return ""
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1.0
    pts = [(i / (len(v) - 1) * 100, 26 - (x - lo) / span * 24) for i, x in enumerate(v)]
    line = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    gid = f"g{abs(hash((line, col))) % 10 ** 8}"
    return (f"<svg viewBox='0 0 100 28' preserveAspectRatio='none' aria-hidden='true'><defs>"
            f"<linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{col}' stop-opacity='.28'/>"
            f"<stop offset='1' stop-color='{col}' stop-opacity='0'/></linearGradient></defs>"
            f"<polygon points='0,28 {line} 100,28' fill='url(#{gid})'/>"
            f"<polyline points='{line}' fill='none' stroke='{col}' stroke-width='1.5' stroke-linejoin='round' "
            f"vector-effect='non-scaling-stroke'/></svg>")
