"""Design system: colour tokens for the light and dark theme, the app's CSS and small HTML components
rendered with st.markdown.

Principles
- One typeface for words (Geist), one for every number (Geist Mono) — figures line up like on a trading terminal.
- Green and red mean market up / down and nothing else. The brand accent is an indigo → violet gradient.
- Surfaces are layered (page → card → inset) and separated by hairlines, not heavy boxes.
Every colour comes from the CSS variables set in `inject_css()` for the active theme; pages never hard-code one."""
import html
import re
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"

# constants used in Plotly figures and as fallbacks (6-digit hex: callers append alpha, e.g. f"{col}1f")
UP, DOWN, WARN, CAUTION = "#16c79a", "#f2555a", "#f5b14c", "#e9a23b"
ACCENT = "#6d8cff"
MUTED = "#8b93a7"            # mid grey: readable on both themes (charts, plotly)
SURFACE = "rgba(0,0,0,0)"    # charts are transparent and sit on the app background
GRID = "rgba(128,128,128,0.13)"
MONO = '"Geist Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'

TOKENS = {
    "dark": {"bg": "#07090d", "surface": "#0e1117", "surface2": "#151922", "line": "#1e2330", "line2": "#2c3345",
             "text": "#eceef3", "muted": "#8b93a7", "faint": "#596175", "up": "#22d3a0", "down": "#ff6b6b",
             "warn": "#f5b14c", "accent": "#7c9cff", "accent2": "#a78bfa",
             "glow": "rgba(124,156,255,.13)", "glow2": "rgba(167,139,250,.09)",
             "shadow": "0 1px 0 rgba(255,255,255,.03) inset, 0 8px 24px -12px rgba(0,0,0,.6)"},
    "light": {"bg": "#f4f5f8", "surface": "#ffffff", "surface2": "#f2f4f8", "line": "#e4e7ee", "line2": "#d0d6e2",
              "text": "#0f1320", "muted": "#5b6478", "faint": "#98a0b3", "up": "#059669", "down": "#dc2626",
              "warn": "#b45309", "accent": "#3b5bdb", "accent2": "#7048e8",
              "glow": "rgba(59,91,219,.08)", "glow2": "rgba(112,72,232,.06)",
              "shadow": "0 1px 2px rgba(16,24,40,.05), 0 10px 24px -16px rgba(16,24,40,.18)"},
}

CSS = """
<style>
:root { __VARS__ --mono: __MONO__; --grad: linear-gradient(135deg, var(--accent), var(--accent2)); }

/* ------------------------------------------------------------ page shell */
.stApp { background:
  radial-gradient(1100px 480px at 12% -8%, var(--glow), transparent 62%),
  radial-gradient(900px 420px at 96% -6%, var(--glow2), transparent 60%), var(--bg); background-attachment: fixed; }
.block-container { padding-top: 4.6rem; padding-bottom: 4rem; max-width: 1360px; }
#MainMenu, footer { visibility: hidden; }
html, body, .stApp { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
header[data-testid="stHeader"] { background: color-mix(in srgb, var(--bg) 78%, transparent);
  backdrop-filter: saturate(180%) blur(14px); border-bottom: 1px solid var(--line); height: 3.6rem; }
[data-testid="stLogo"] { height: 1.8rem; }
h1, h2, h3, h4, h5 { letter-spacing: -0.02em; }
.stMarkdown h3 { font-size: 17px; font-weight: 650; padding: 0; margin: 0; }
.stMarkdown h4 { font-size: 18px; font-weight: 650; }
.stMarkdown h5 { font-size: 14px; font-weight: 650; }
.stMarkdown a { color: var(--accent); }

/* native widgets: same surfaces and borders as our own components */
[data-testid="stExpander"] details { background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: var(--shadow); }
[data-testid="stExpander"] summary { font-weight: 600; font-size: 14px; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-color: var(--line) !important;
  border-radius: 14px; }
[data-testid="stTabs"] [data-baseweb="tab"] { font-weight: 600; font-size: 14px; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); }
[data-testid="stForm"] { background: var(--surface); border-color: var(--line); border-radius: 16px; box-shadow: var(--shadow); }
.stButton button, .stDownloadButton button, .stFormSubmitButton button { font-weight: 600; border-radius: 10px;
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"] { background: var(--grad); border: 0;
  color: #fff; box-shadow: 0 6px 18px -8px var(--accent); }
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primaryFormSubmit"]:hover { transform: translateY(-1px);
  box-shadow: 0 10px 22px -8px var(--accent); color: #fff; }
.stButton button[kind="secondary"]:hover { border-color: var(--accent); color: var(--accent); }
[data-testid="stCaptionContainer"] { color: var(--muted); }
[data-testid="stProgress"] p { font-size: 13px; color: var(--muted); }
.modebar { opacity: 0; transition: opacity .15s; } .js-plotly-plot:hover .modebar { opacity: 1; }

/* ------------------------------------------------------------ text helpers */
.muted, .note, .sub { color: var(--muted); }
.note { font-size: 12.5px; line-height: 1.55; }
.kicker, .card h4, .tile .l, .steps .l, .over { font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase;
  font-weight: 600; color: var(--muted); }
/* small tabular figures in the monospace face; large display figures stay in the text face with tabular digits */
.num, .tk .v, .tk .c, .sc .px, .rangelbl, .wl .c-px, .rr .v, .rr .p, .hero .facts .tile .v {
  font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -0.03em; }
.tile .v, .hero .price, .hero .chg, .brief .big, .brief .chg { font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.msg { font-size: 14px; line-height: 1.6; margin-top: 12px; }
.msg code { font-size: 12.5px; }

/* ------------------------------------------------------------ ticker bar (every page) */
.ticker { display: flex; align-items: stretch; background: var(--surface); border: 1px solid var(--line);
  border-radius: 14px; box-shadow: var(--shadow); margin: 0 0 24px; overflow: hidden; }
.ticker .cells { display: flex; flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; }
.ticker .cells::-webkit-scrollbar { display: none; }
.tk { flex: 1 0 auto; padding: 10px 18px; border-right: 1px solid var(--line); white-space: nowrap; }
.tk .n { font-size: 10px; letter-spacing: .09em; text-transform: uppercase; font-weight: 600; color: var(--muted); }
.tk .r { display: flex; align-items: baseline; gap: 8px; margin-top: 3px; }
.tk .v { font-size: 14.5px; font-weight: 600; }
.tk .c { font-size: 11.5px; font-weight: 600; }
.ticker .status { display: flex; flex-direction: column; justify-content: center; align-items: flex-end; padding: 8px 18px;
  white-space: nowrap; background: var(--surface2); min-width: 150px; }
.ticker .status .t { font-family: var(--mono); font-size: 12px; color: var(--muted); margin-top: 3px; }
.live { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 650; }
.live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; display: inline-block; }
.live.on i { animation: pulse 1.8s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 60%, transparent); }
                   70%, 100% { box-shadow: 0 0 0 7px transparent; } }

/* ------------------------------------------------------------ headers */
.pagehead { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; margin: 0 0 20px; }
.pagehead h1 { font-size: 28px; font-weight: 700; margin: 0; line-height: 1.15; padding: 0; letter-spacing: -0.03em; }
.pagehead .sub { font-size: 14.5px; margin-top: 6px; max-width: 760px; line-height: 1.5; }
.sec { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-top: 6px; }
.sec .t { font-size: 18px; font-weight: 650; letter-spacing: -0.02em; }
.sec .d { font-size: 13px; color: var(--muted); margin-top: 3px; }

/* ------------------------------------------------------------ pills, dots, badges */
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px;
  font-weight: 600; border: 1px solid; white-space: nowrap; line-height: 1.5; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.badge { display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 6px; font-size: 11.5px; font-weight: 700;
  letter-spacing: .06em; white-space: nowrap; }
.meter { display: inline-flex; gap: 2px; align-items: flex-end; height: 11px; vertical-align: -1px; margin-right: 6px; }
.meter i { width: 3px; border-radius: 1px; background: var(--line2); display: inline-block; }
.meter i:nth-child(1) { height: 4px; } .meter i:nth-child(2) { height: 6px; }
.meter i:nth-child(3) { height: 8.5px; } .meter i:nth-child(4) { height: 11px; }

/* ------------------------------------------------------------ cards, tiles, stats */
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 20px 22px;
  box-shadow: var(--shadow); }
.card h4 { margin: 0; padding: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 10px; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px;
  box-shadow: var(--shadow); min-width: 0; }
.tile .v { font-size: 18px; font-weight: 600; margin-top: 5px; }
.tile .s { font-size: 12px; margin-top: 3px; color: var(--muted); }
.card .tile, .stats .tile { background: var(--surface2); box-shadow: none; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); background: var(--surface);
  border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); overflow: hidden; }
.stats .tile { background: transparent; border: 0; border-radius: 0; padding: 18px 22px;
  box-shadow: 1px 0 0 var(--line), 0 1px 0 var(--line); }
.stats .tile .v { font-size: 21px; }
[data-testid="stMarkdownContainer"] > .grid, [data-testid="stMarkdownContainer"] > .stats { margin-bottom: 14px; }

.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 5px 11px; border-radius: 8px; font-size: 12.5px;
  border: 1px solid var(--line); background: var(--surface2); }

.rangebar { position: relative; height: 4px; border-radius: 2px; margin: 12px 0 6px;
  background: linear-gradient(90deg, var(--down), var(--line2) 50%, var(--up)); }
.rangebar .m { position: absolute; top: -4px; width: 3px; height: 12px; background: var(--text); border-radius: 2px;
  box-shadow: 0 0 0 2px var(--surface); }
.rangelbl { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); }

.callout { display: flex; gap: 10px; margin-top: 12px; padding: 11px 13px; border-radius: 12px; font-size: 13px; line-height: 1.5;
  border: 1px solid color-mix(in srgb, var(--warn) 32%, transparent); background: color-mix(in srgb, var(--warn) 8%, transparent); }
.callout b.i { color: var(--warn); font-weight: 800; }

/* ------------------------------------------------------------ Home: today's briefing */
.brief { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); border-radius: 20px; overflow: hidden;
  position: relative; background: var(--surface); border: 1px solid var(--line); box-shadow: var(--shadow); margin-bottom: 12px; }
.brief::before { content: ""; position: absolute; inset: 0; pointer-events: none; border-radius: 20px;
  background: radial-gradient(600px 240px at 0% 0%, var(--glow), transparent 70%); }
.brief .l { padding: 28px 30px 24px; position: relative; }
.brief h1 { font-size: 32px; font-weight: 700; letter-spacing: -0.035em; line-height: 1.1; margin: 10px 0 0; padding: 0; }
.brief h1 .g { background: var(--grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
.brief .sum { font-size: 15.5px; line-height: 1.6; color: var(--muted); margin-top: 12px; max-width: 540px; }
.brief .sum b { color: var(--text); font-weight: 600; }
.brief .facts { display: flex; gap: 28px; flex-wrap: wrap; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--line); }
.brief .facts .k { font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase; font-weight: 600; color: var(--muted); }
.brief .facts .v { font-size: 15px; font-weight: 600; margin-top: 4px; }
.brief .facts .v small { font-size: 12px; font-weight: 500; color: var(--muted); margin-left: 4px; }
.brief .r { position: relative; border-left: 1px solid var(--line); background: var(--surface2); min-height: 210px;
  display: flex; flex-direction: column; justify-content: space-between; }
.brief .r .top { padding: 22px 24px 0; position: relative; z-index: 1; }
.brief .big { font-size: 32px; font-weight: 650; line-height: 1.1; margin-top: 6px; }
.brief .chg { font-size: 13.5px; font-weight: 600; margin-top: 5px; }
.brief .chart { height: 110px; }
.brief .chart svg { width: 100%; height: 100%; display: block; }

/* ------------------------------------------------------------ Home: watchlist table */
.st-key-wltable { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow);
  overflow: hidden; gap: 0 !important; padding: 0; }
[class*="st-key-wlr-"] [data-testid="stMarkdownContainer"] { line-height: 1.3; }
[class*="st-key-wlr-"] [data-testid="stElementContainer"], [class*="st-key-wlr-"] [data-testid="stMarkdown"] { height: auto; overflow: visible; }
.wl { display: grid; gap: 14px; align-items: center; width: 100%; line-height: 1.3;
  grid-template-columns: minmax(140px, 1.5fr) 96px minmax(104px, .9fr) 92px 104px minmax(190px, 2.2fr) minmax(96px, .9fr); }
.wl.head { padding: 11px 64px 11px 20px; font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase; font-weight: 600;
  color: var(--muted); background: var(--surface2); }
.wl .r { text-align: right; }
[class*="st-key-wlr-"] { padding: 9px 12px 9px 20px; min-height: 60px; border-top: 1px solid var(--line); position: relative;
  transition: background .12s ease; }
[class*="st-key-wlr-"]:hover { background: var(--surface2); }
[class*="st-key-wlr-"]::before { content: ""; position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px; border-radius: 0 3px 3px 0;
  background: transparent; }
[class*="st-key-wlr-BUY-"]::before, [class*="st-key-wlr-HOLD-"]::before { background: var(--up); }
[class*="st-key-wlr-SHORT-"]::before { background: var(--down); }
[class*="st-key-wlr-SELL-"]::before { background: var(--warn); }
[class*="st-key-wlr-"] .stButton button { border: 1px solid var(--line); border-radius: 9px; color: var(--muted); min-height: 0;
  padding: 5px 8px; background: transparent; }
[class*="st-key-wlr-"] .stButton button:hover { color: var(--accent); border-color: var(--accent); }
.wl .nm { font-size: 14.5px; font-weight: 650; letter-spacing: -0.01em; line-height: 1.2; }
.wl .co { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wl .c-spark { height: 30px; } .wl .c-spark svg { width: 100%; height: 100%; display: block; }
.wl .c-px { text-align: right; }
.wl .c-px .v { font-size: 14px; font-weight: 600; }
.wl .c-px .c { font-size: 12px; font-weight: 600; margin-top: 2px; }
.wl .c-conf { font-size: 12px; color: var(--muted); white-space: nowrap; }
.wl .c-line { font-size: 13px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.wl .c-news { font-size: 12px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ------------------------------------------------------------ chart page: instrument header */
.hero { display: flex; flex-wrap: wrap; gap: 16px 30px; align-items: center; background: var(--surface);
  border: 1px solid var(--line); border-radius: 16px; padding: 18px 22px; box-shadow: var(--shadow); margin: 4px 0 14px; }
.hero .id { flex: 0 1 300px; min-width: 220px; }
.hero .sym { font-size: 22px; font-weight: 700; line-height: 1.15; letter-spacing: -0.03em; }
.hero .sub { font-size: 12.5px; margin-top: 4px; }
.hero .pills { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.hero .quote { flex: 0 0 auto; }
.hero .price { font-size: 30px; font-weight: 650; line-height: 1.1; }
.hero .chg { font-size: 13.5px; font-weight: 600; margin-top: 5px; }
.hero .facts { flex: 1 1 520px; min-width: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0; }
.hero .facts .tile { background: transparent; border: 0; border-left: 1px solid var(--line); border-radius: 0;
  padding: 2px 16px; box-shadow: none; }
.hero .facts .tile .v { font-size: 15px; }

/* ------------------------------------------------------------ signal panel: the trade ticket */
.sigpanel { position: relative; overflow: hidden; }
.sigpanel::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--sig, var(--line2)); }
.sigpanel::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(420px 160px at 0% 0%, color-mix(in srgb, var(--sig, transparent) 12%, transparent), transparent 70%); }
.sigpanel > * { position: relative; z-index: 1; }
.sigpanel .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.verdict { font-size: 36px; font-weight: 750; letter-spacing: -0.03em; line-height: 1.05; margin: 12px 0 2px; }
.sigpanel .grid { grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); margin-top: 14px; }
.sigpanel .tile .v { font-size: 15px; white-space: nowrap; }
.sigpanel .tile .l { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rr { margin-top: 20px; }
.rr .bar { position: relative; height: 8px; border-radius: 4px; display: flex; }
.rr .risk { background: linear-gradient(90deg, var(--down), color-mix(in srgb, var(--down) 45%, transparent)); border-radius: 4px 0 0 4px; }
.rr .reward { background: linear-gradient(90deg, color-mix(in srgb, var(--up) 45%, transparent), var(--up)); border-radius: 0 4px 4px 0; flex: 1; }
.rr .entry { position: absolute; top: -4px; width: 2px; height: 16px; background: var(--text); border-radius: 1px; }
.rr .now { position: absolute; top: -5px; width: 18px; height: 18px; margin-left: -9px; border-radius: 50%; background: var(--surface);
  border: 3px solid var(--text); box-shadow: 0 0 0 3px color-mix(in srgb, var(--text) 14%, transparent); }
.rr .lbls { display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 14px; gap: 8px; }
.rr .lbls > div:nth-child(2) { text-align: center; } .rr .lbls > div:nth-child(3) { text-align: right; }
.rr .k { font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase; font-weight: 600; color: var(--muted); }
.rr .v { font-size: 15px; font-weight: 600; margin-top: 3px; }
.rr .p { font-size: 11.5px; margin-top: 1px; color: var(--muted); }
.rr .ratio { font-size: 12.5px; color: var(--muted); margin-top: 12px; }
.rr .ratio b { color: var(--text); font-weight: 600; }
.steps { margin-top: 16px; border-top: 1px solid var(--line); padding-top: 14px; }
.steps ol { margin: 10px 0 0; padding: 0; list-style: none; counter-reset: s; }
.steps li { position: relative; font-size: 14px; line-height: 1.55; margin: 0 0 10px; padding-left: 32px; counter-increment: s; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: 1px; width: 21px; height: 21px; border-radius: 7px;
  background: var(--surface2); border: 1px solid var(--line2); font-family: var(--mono); font-size: 11px; font-weight: 600;
  display: flex; align-items: center; justify-content: center; color: var(--muted); }
.meta { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12.5px; line-height: 1.55;
  color: var(--muted); }
.meta b { color: var(--text); font-weight: 600; }

/* ------------------------------------------------------------ Home: setup cards */
[class*="st-key-sigc-"] { background: var(--surface); border: 1px solid var(--line); border-radius: 16px;
  padding: 18px 20px 10px; box-shadow: var(--shadow); position: relative; overflow: hidden; gap: .35rem;
  transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease; }
[class*="st-key-sigc-"]:hover { border-color: var(--line2); transform: translateY(-2px); }
[class*="st-key-sigc-"]::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: var(--line2); }
[class*="st-key-sigc-BUY-"]::before, [class*="st-key-sigc-HOLD-"]::before { background: var(--up); }
[class*="st-key-sigc-SHORT-"]::before { background: var(--down); }
[class*="st-key-sigc-SELL-"]::before { background: var(--warn); }
[class*="st-key-sigc-WAIT-scan"]::before { background: var(--grad); }
[class*="st-key-sigc-"] .stButton button { border: 0; border-top: 1px solid var(--line); border-radius: 0; color: var(--muted);
  font-size: 13px; padding-top: 8px; min-height: 0; }
[class*="st-key-sigc-"] .stButton button:hover { color: var(--accent); background: transparent; }
.sc { padding-bottom: 14px; }
.sc .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.sc .nm { font-size: 15.5px; font-weight: 650; line-height: 1.2; letter-spacing: -0.02em; }
.sc .co { font-size: 12px; color: var(--muted); margin-top: 3px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; max-width: 190px; }
.sc .px { text-align: right; }
.sc .px .v { font-size: 14.5px; font-weight: 600; }
.sc .px .c { font-size: 12px; font-weight: 600; margin-top: 2px; }
.sc .spark { height: 40px; margin: 12px 0; }
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
.empty { text-align: center; padding: 34px 16px; border: 1px dashed var(--line2); border-radius: 16px; }
.empty .ic { width: 36px; height: 36px; border-radius: 10px; margin: 0 auto; background: var(--surface2);
  border: 1px solid var(--line); display: flex; align-items: center; justify-content: center; }
.empty .ic i { width: 14px; height: 2px; background: var(--faint); border-radius: 1px; display: block; }
.empty .t { font-size: 15px; font-weight: 650; margin-top: 10px; }
.empty .x { font-size: 13.5px; margin-top: 4px; color: var(--muted); }
.welcome { text-align: center; margin: 18px 0 8px; }
.welcome img { height: 48px; }
.welcome h1 { font-size: 34px; font-weight: 700; letter-spacing: -0.035em; margin: 16px 0 8px; padding: 0; }
.welcome .lead { font-size: 15.5px; color: var(--muted); max-width: 560px; margin: 0 auto; line-height: 1.55; }

@media (max-width: 900px) {
  .brief { grid-template-columns: 1fr; }
  .brief .r { border-left: 0; border-top: 1px solid var(--line); min-height: 170px; }
  .wl { grid-template-columns: minmax(110px, 1.3fr) minmax(90px, 1fr) 84px; gap: 10px; }
  .wl .c-spark, .wl .c-conf, .wl .c-line, .wl .c-news { display: none; }
  .wl.head { padding-right: 56px; }
}
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .pagehead h1 { font-size: 23px; }
  .brief .l { padding: 22px 20px 18px; } .brief h1 { font-size: 26px; }
  .hero .facts .tile { border-left: 0; padding: 6px 0; }
  .ticker .status { display: none; }
  .verdict { font-size: 30px; }
  [class*="st-key-wlr-"] { padding-left: 14px; }
}
</style>
"""

# The clock ticks in the browser every second (the server only re-sends prices), in Indian time whatever the device's zone is.
CLOCK_JS = """<script>
(function () {
  if (window.__tsClock) return;
  var l = document.createElement('link'); l.rel = 'stylesheet';   // the figures' typeface (a stylesheet link can't be sent as markdown)
  l.href = 'https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600;700&display=swap'; document.head.appendChild(l);
  var fmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  window.__tsClock = setInterval(function () {
    var e = document.getElementById('ts-clock');
    if (e) e.textContent = fmt.format(new Date()) + ' IST';
  }, 1000);
})();
</script>"""


def dark() -> bool:
    """Best guess of the active theme (Streamlit infers it from the background; unknown -> dark)."""
    try:
        return st.context.theme.type != "light"
    except Exception:  # noqa: BLE001
        return True


def tokens() -> dict:
    return TOKENS["dark" if dark() else "light"]


def inject_css():
    """The app's CSS with the active theme's colour tokens, the brand logo in the top bar and the ticking clock."""
    t = tokens()
    st.markdown(CSS.replace("__VARS__", " ".join(f"--{k}:{v};" for k, v in t.items())).replace("__MONO__", MONO),
                unsafe_allow_html=True)
    try:
        st.logo(str(ASSETS / f"logo-{'dark' if dark() else 'light'}.svg"), size="large")
        st.html(CLOCK_JS, unsafe_allow_javascript=True)
    except Exception:  # noqa: BLE001 — decoration: the app works without them
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
                  plot_bgcolor="rgba(0,0,0,0)", height=height, font=dict(color=text_color(), size=12, family="Geist, Inter, sans-serif"),
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
    return f"<span class='badge' style='color:{col};background:{col}1f'>{esc(text)}</span>"


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
    """The ticker bar. quotes: (name, last price, % change). The clock text is kept ticking by CLOCK_JS."""
    cells = []
    for name, px, pct in quotes:
        col = signed_color(pct)
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else ""
        cells.append(f"<div class='tk'><div class='n'>{esc(name)}</div><div class='r'><span class='v'>{px:,.2f}</span>"
                     f"<span class='c' style='color:{col}'>{arrow} {abs(pct):.2f}%</span></div></div>")
    st_col = up_txt() if is_open else MUTED
    return ("<div class='ticker'><div class='cells'>" + "".join(cells) + "</div>"
            f"<div class='status'><span class='live{' on' if is_open else ''}' style='color:{st_col}'><i></i>{esc(status)}</span>"
            f"<span class='t' id='ts-clock'>{esc(clock)} IST</span></div></div>")


def range_bar(low: float, high: float, ltp: float, label: str = "Day range") -> str:
    pos = 50 if high <= low else max(0, min(100, (ltp - low) / (high - low) * 100))
    return (f"<div class='l'>{esc(label)}</div>"
            f"<div class='rangebar'><div class='m' style='left:calc({pos:.1f}% - 1px)'></div></div>"
            f"<div class='rangelbl'><span>{low:,.2f}</span><span>{high:,.2f}</span></div>")


def rr_bar(stop: float, entry: float, target: float, ltp: float, stop_label: str = "Stop-loss") -> str:
    """The trade at a glance: stop ← entry → target on one bar, with where the price is now and the reward-to-risk.
    Works for longs (stop < entry < target) and shorts (the reverse)."""
    span = target - stop
    if not span or (entry - stop) * span <= 0 or (target - entry) * span <= 0:
        return ""
    pe = (entry - stop) / span * 100
    pn = max(0.0, min(100.0, (ltp - stop) / span * 100))
    risk, reward = abs(entry - stop), abs(target - entry)
    return (f"<div class='rr'><div class='bar'><div class='risk' style='width:{pe:.1f}%'></div><div class='reward'></div>"
            f"<div class='entry' style='left:calc({pe:.1f}% - 1px)'></div><div class='now' style='left:{pn:.1f}%' "
            f"title='Price now ₹{ltp:,.2f}'></div></div>"
            f"<div class='lbls'>"
            f"<div><div class='k'>{esc(stop_label)}</div><div class='v' style='color:{down_txt()}'>₹{stop:,.2f}</div>"
            f"<div class='p'>{(stop / entry - 1) * 100:+.1f}%</div></div>"
            f"<div><div class='k'>Entry</div><div class='v'>₹{entry:,.2f}</div><div class='p'>now ₹{ltp:,.2f}</div></div>"
            f"<div><div class='k'>Target</div><div class='v' style='color:{up_txt()}'>₹{target:,.2f}</div>"
            f"<div class='p'>{(target / entry - 1) * 100:+.1f}%</div></div></div>"
            f"<div class='ratio'>Aiming for <b>{reward / risk:.1f}×</b> what is risked — the ring shows the price now.</div></div>")


def sparkline(values: list[float], col: str, fill: float = .28) -> str:
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
            f"<linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{col}' stop-opacity='{fill}'/>"
            f"<stop offset='1' stop-color='{col}' stop-opacity='0'/></linearGradient></defs>"
            f"<polygon points='0,28 {line} 100,28' fill='url(#{gid})'/>"
            f"<polyline points='{line}' fill='none' stroke='{col}' stroke-width='1.6' stroke-linejoin='round' "
            f"vector-effect='non-scaling-stroke'/></svg>")
