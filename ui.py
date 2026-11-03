"""Design system: theme-aware colours and small HTML components rendered with st.markdown.

Surfaces, borders and secondary text are mixed from `currentColor`, so the same CSS looks right in both the
light and the dark theme. Up/down text colours are picked per theme (st.context.theme) for contrast."""
import html

import streamlit as st

UP, DOWN, WARN, CAUTION = "#00b386", "#eb5b3c", "#f08c3a", "#e9a23b"   # Groww-style green / red, status orange
ACCENT = "#3987e5"
MUTED = "#8b8f99"            # mid grey: readable on both themes (charts, plotly)
SURFACE = "rgba(0,0,0,0)"    # charts are transparent and sit on the app background
GRID = "rgba(128,128,128,0.16)"

CSS = """
<style>
:root { --up:#00b386; --down:#eb5b3c; --warn:#f08c3a; --accent:#3987e5; }
.block-container { padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1440px; }
#MainMenu, footer { visibility: hidden; }

/* surfaces mixed from the text colour -> correct in light and dark themes */
.card, .tile, .chip, .strip .q, .steps {
  --line: color-mix(in srgb, currentColor 12%, transparent);
  --soft: color-mix(in srgb, currentColor 4%, transparent);
}
.muted, .note, .tile .l, .tile .s, .card h4, .strip .q .n, .sub, .rangelbl, .steps .l, .kicker {
  color: color-mix(in srgb, currentColor 60%, transparent);
}
.card { background:var(--soft); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }
.card h4 { margin:0 0 10px; font-size:12px; letter-spacing:.08em; text-transform:uppercase; font-weight:650; }
.note { font-size:12.5px; line-height:1.5; }
.kicker { font-size:11.5px; letter-spacing:.09em; text-transform:uppercase; font-weight:650; }

.strip { display:flex; gap:10px; flex-wrap:wrap; align-items:stretch; margin: 0 0 18px; }
.strip .q { background:var(--soft); border:1px solid var(--line); border-radius:12px; padding:8px 14px; min-width:140px; flex:1; }
.strip .q .n { font-size:11px; letter-spacing:.06em; text-transform:uppercase; }
.strip .q .v { font-size:16.5px; font-weight:650; font-variant-numeric: tabular-nums; }
.strip .q .c { font-size:12.5px; font-variant-numeric: tabular-nums; font-weight:600; }
.strip .status { display:flex; flex-direction:column; justify-content:center; align-items:flex-end; min-width:170px; }

.pill { display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:12.5px;
        font-weight:600; border:1px solid; white-space:nowrap; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }

.pagehead { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; flex-wrap:wrap; margin: 2px 0 14px; }
.pagehead h1 { font-size:30px; font-weight:750; margin:0; line-height:1.15; padding:0; }
.pagehead .sub { font-size:14px; margin-top:4px; }

.hero2 { display:flex; flex-wrap:wrap; gap:12px 22px; align-items:center; margin: 2px 0 12px; }
.hero2 .hl { flex: 0 1 320px; min-width: 240px; }
.hero2 .hr { flex: 1 1 600px; min-width: 0; }
.hero2 .sym { font-size:28px; font-weight:750; line-height:1.1; }
.hero2 .sub { font-size:12.5px; margin-top:4px; }
.hero2 .pills { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
.hero2 .grid { grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); }

.verdict { font-size:38px; font-weight:800; letter-spacing:.01em; line-height:1.1; margin:2px 0 8px; }
.msg { font-size:14.5px; line-height:1.55; margin-top:10px; }

.grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap:10px; }
.tile { background:var(--soft); border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.tile .l { font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
.tile .v { font-size:19px; font-weight:680; font-variant-numeric: tabular-nums; margin-top:2px; }
.tile .s { font-size:12px; margin-top:1px; }

.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chip { padding:6px 11px; border-radius:8px; font-size:13px; border:1px solid var(--line); background:var(--soft); }

.rangebar { position:relative; height:6px; border-radius:3px; background:linear-gradient(90deg, #eb5b3c, #9993 50%, #00b386); margin:8px 0 4px; }
.rangebar .m { position:absolute; top:-4px; width:3px; height:14px; background:currentColor; border-radius:2px; }
.rangelbl { display:flex; justify-content:space-between; font-size:11.5px; font-variant-numeric: tabular-nums; }

.steps { margin-top:12px; background:var(--soft); border:1px solid var(--line); border-radius:10px; padding:10px 14px 4px; }
.steps .l { font-size:11px; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }
.steps ol { margin:6px 0 6px 18px; padding:0; }
.steps li { font-size:14.5px; line-height:1.5; margin:4px 0; }

/* the signal panel next to the chart is narrow: 2 tiles per row, values on one line */
.sigpanel .grid { grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); }
.sigpanel .tile .v { font-size:17px; white-space:nowrap; }
.sigpanel .tile .l { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

/* signal cards on Home */
.sigcard .top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
.sigcard .nm { font-size:17px; font-weight:720; line-height:1.2; }
.sigcard .co { font-size:12px; color: color-mix(in srgb, currentColor 58%, transparent); margin-top:2px;
               white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:200px; }
.sigcard .px { text-align:right; font-variant-numeric: tabular-nums; }
.sigcard .px .v { font-size:16px; font-weight:650; }
.sigcard .px .c { font-size:12.5px; font-weight:600; }
.sigcard .badge { display:inline-block; margin-top:12px; padding:4px 12px; border-radius:8px; font-size:15px;
                  font-weight:800; letter-spacing:.03em; }
.sigcard .line { font-size:13.5px; line-height:1.45; margin-top:8px; min-height:40px; display:-webkit-box;
                  -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.sigcard .note { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.empty { text-align:center; padding:28px 16px; border:1px dashed color-mix(in srgb, currentColor 18%, transparent);
         border-radius:14px; }
.empty .ic { font-size:30px; }
.empty .t { font-size:16px; font-weight:650; margin-top:6px; }
.empty .x { font-size:13.5px; margin-top:4px; color: color-mix(in srgb, currentColor 60%, transparent); }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def dark() -> bool:
    """Best guess of the active theme (Streamlit infers it from the background; unknown -> dark)."""
    try:
        return st.context.theme.type != "light"
    except Exception:  # noqa: BLE001
        return True


def up_txt() -> str:
    return "#00c896" if dark() else "#008a62"


def down_txt() -> str:
    return "#f06a4d" if dark() else "#cf3f22"


def text_color() -> str:
    return "#e8e8e6" if dark() else "#1f2328"


def plotly_layout(height: int, **kw) -> dict:
    """Transparent, theme-matched Plotly layout."""
    layout = dict(template="plotly_dark" if dark() else "plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                  plot_bgcolor="rgba(0,0,0,0)", height=height, font=dict(color=text_color(), size=12),
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
    return {"up": up_txt(), "down": down_txt(), "warn": WARN, "accent": ACCENT, "muted": MUTED}.get(key, key)


def pill(text: str, col: str) -> str:
    return (f"<span class='pill' style='color:{col};border-color:{col}55;background:{col}14'>"
            f"<span class='dot' style='background:{col}'></span>{esc(text)}</span>")


def tile(label: str, value: str, sub: str = "", col: str | None = None) -> str:
    style = f" style='color:{col}'" if col else ""
    sub_html = f"<div class='s'>{sub}</div>" if sub else ""
    return f"<div class='tile'><div class='l'>{esc(label)}</div><div class='v'{style}>{value}</div>{sub_html}</div>"


def grid(tiles: list[str]) -> str:
    return "<div class='grid'>" + "".join(tiles) + "</div>"


def chip(icon: str, text: str) -> str:
    return f"<span class='chip'>{icon} {text}</span>"


def page_header(title: str, subtitle: str = "", right: str = ""):
    st.markdown(f"<div class='pagehead'><div><h1>{esc(title)}</h1>"
                + (f"<div class='sub'>{subtitle}</div>" if subtitle else "")
                + f"</div><div>{right}</div></div>", unsafe_allow_html=True)


def empty_state(icon: str, title: str, text: str = ""):
    st.markdown(f"<div class='empty'><div class='ic'>{icon}</div><div class='t'>{esc(title)}</div>"
                + (f"<div class='x'>{text}</div>" if text else "") + "</div>", unsafe_allow_html=True)


def market_strip(quotes: list[tuple[str, float, float]], is_open: bool, status: str, clock: str) -> str:
    """quotes: (name, last price, % change)."""
    items = []
    for name, px, pct in quotes:
        col = signed_color(pct)
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "•"
        items.append(f"<div class='q'><div class='n'>{esc(name)}</div><div class='v'>{px:,.2f}</div>"
                     f"<div class='c' style='color:{col}'>{arrow} {pct:+.2f}%</div></div>")
    st_col = UP if is_open else DOWN
    items.append(f"<div class='q status'>{pill(status, st_col)}<div class='note' style='margin-top:6px'>{esc(clock)} IST</div></div>")
    return "<div class='strip'>" + "".join(items) + "</div>"


def range_bar(low: float, high: float, ltp: float, label: str = "Day range") -> str:
    pos = 50 if high <= low else max(0, min(100, (ltp - low) / (high - low) * 100))
    return (f"<div class='l muted' style='font-size:11px;text-transform:uppercase;letter-spacing:.06em'>{esc(label)}</div>"
            f"<div class='rangebar'><div class='m' style='left:calc({pos:.1f}% - 1px)'></div></div>"
            f"<div class='rangelbl'><span>₹{low:,.2f}</span><span>₹{high:,.2f}</span></div>")
