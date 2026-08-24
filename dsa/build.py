#!/usr/bin/env python3
"""
DSA Mastery builder.

Reads dsa/data/program.json and dsa/data/day-NN.json and emits dsa-master.html
at the repo root. Every card in the page comes from a loop here, so one layout
fix lands on all 150 of them.

    python dsa/build.py

Syntax highlighting happens at BUILD time, in Python. There is no client-side
highlighter to fail, and the markup still reads correctly with JavaScript off.

Data shape, one file per day:

    {
      "day": 1,
      "title": "Foundations",
      "kind": "core" | "retrieval" | "mock",
      "focus": "one line under the day title",
      "cards": [ ... exactly 5 ... ]
    }

A card:

    {
      "id":       "two-pointers",          # stable, keyed for confidence across cycles
      "lane":     "arrays" | "structures" | "trees" | "dp" | "graphs" | "mock",
      "title":    "Two Pointers",
      "trigger":  "when you reach for this",            # always visible
      "recall":   "the prompt shown BEFORE the reveal", # always visible
      "patterns": ["...", "..."],                       # optional, visible
      "useWhen":  ["...", "..."],                       # optional, visible
      "problem":  {"lc": 125, "name": "...", "slug": "...", "diff": "easy"},
      "drill":    [{"lc":.., "name":.., "slug":.., "diff":.., "cue":".."}],
      "template": ["line", "line", ...],                # LOCKED until revealed
      "complexity": {"time": "O(n)", "space": "O(1)"},  # LOCKED
      "keyInsights": ["...", "..."],                    # LOCKED
      "trap":     "the follow-up that kills people",    # LOCKED
      "timerSec": 240                                   # optional override
    }

Inline markup allowed in every prose string: `code` and **bold**. Everything
else is escaped, so <, > and & are safe to type literally.

Changing a card's "id" resets its confidence history. Reordering cards does not,
which is the whole reason ids are strings rather than positions.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
OUT = ROOT / "dsa-master.html"

LANES = ("arrays", "structures", "trees", "dp", "graphs", "mock")
KINDS = ("core", "retrieval", "mock")
DIFFS = ("easy", "medium", "hard")


# ───────────────────────────────────────────────────────────── inline markup ──

_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline(text) -> str:
    """Escape, then apply the tiny markup subset the data files use."""
    out = html.escape(str(text), quote=False)
    out = _CODE_RE.sub(lambda m: '<code class="ic">' + m.group(1) + "</code>", out)
    out = _BOLD_RE.sub(lambda m: "<strong>" + m.group(1) + "</strong>", out)
    return out


def plain(text) -> str:
    out = _CODE_RE.sub(lambda m: m.group(1), str(text))
    return _BOLD_RE.sub(lambda m: m.group(1), out)


# ────────────────────────────────────────────────────────────── highlighting ──
#
# Every template in this program is Python, so this is a Python tokeniser and
# nothing else. Shallow by design: enough to make a template readable at a
# glance, not a parser.

KEYWORDS = (
    "False None True and as assert async await break class continue def del "
    "elif else except finally for from global if import in is lambda nonlocal "
    "not or pass raise return try while with yield match case"
).split()

TYPES = (
    "int str float bool list dict set tuple bytes self cls range len enumerate "
    "min max sum sorted abs any all zip map reversed deque Counter defaultdict "
    "heapq bisect OrderedDict lru_cache"
).split()

COMMENT = r"#[^\n]*"
STRING = (
    r"\"\"\"[\s\S]*?\"\"\""
    r"|'''[\s\S]*?'''"
    r"|\"(?:\\.|[^\"\\\n])*\""
    r"|'(?:\\.|[^'\\\n])*'"
)
NUMBER = r"\b(?:0[xX][0-9a-fA-F_]+|\d[\d_]*\.?[\d_]*(?:[eE][-+]?\d+)?)\b"
FUNC = r"\b([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()"

_PATTERN = re.compile(
    "(?P<com>" + COMMENT + ")"
    "|(?P<str>" + STRING + ")"
    "|(?P<num>" + NUMBER + ")"
    "|(?P<kw>\\b(?:" + "|".join(sorted(set(KEYWORDS), key=len, reverse=True)) + ")\\b)"
    "|(?P<typ>\\b(?:" + "|".join(sorted(set(TYPES), key=len, reverse=True)) + ")\\b)"
    "|(?P<fn>" + FUNC + ")"
)

_CLASS = {"com": "tk-com", "str": "tk-str", "num": "tk-num",
          "kw": "tk-kw", "typ": "tk-typ", "fn": "tk-fn"}


def highlight(src: str) -> str:
    # Escape first (quote=False keeps quotes intact so the string rule still
    # matches), then tokenise. The entities introduced (&amp; &lt; &gt;) contain
    # no quotes or digits, so no rule can match inside one.
    esc = html.escape(src, quote=False)
    return _PATTERN.sub(
        lambda m: '<span class="' + _CLASS[m.lastgroup] + '">' + m.group(0) + "</span>",
        esc,
    )


# ─────────────────────────────────────────────────────────────── components ──

def render_problem(p: dict, cue: str | None = None) -> str:
    diff = p.get("diff", "medium")
    url = "https://leetcode.com/problems/" + p["slug"] + "/"
    cue_html = (
        '<span class="problem__cue">' + inline(cue) + "</span>" if cue else ""
    )
    return (
        '<a class="problem" href="' + url + '" target="_blank" rel="noopener">'
        '<span class="problem__lc">LC ' + str(p["lc"]) + "</span>"
        '<span class="problem__name">' + inline(p["name"]) + "</span>"
        '<span class="diff diff--' + diff + '">' + diff + "</span>"
        + cue_html +
        '<span class="problem__go">Solve &rarr;</span>'
        "</a>"
    )


def render_open(card: dict, lane_name: str) -> str:
    """The part of a card visible before the reveal. Deliberately never shows
    the template, the complexity or the insights - that is the whole point."""
    out = ['<h2 class="card__title">' + inline(card["title"]) + "</h2>"]

    if card.get("trigger"):
        out.append(
            '<div class="box box--trigger">'
            '<span class="box__k">Reach for this when</span>'
            + inline(card["trigger"]) + "</div>"
        )

    if card.get("patterns"):
        out.append('<div class="block-label">Shapes</div><div class="pills">')
        out += ['<span class="pill">' + inline(p) + "</span>" for p in card["patterns"]]
        out.append("</div>")

    if card.get("useWhen"):
        out.append('<div class="block-label">Triggers in the wild</div><ul>')
        out += ["<li>" + inline(u) + "</li>" for u in card["useWhen"]]
        out.append("</ul>")

    if card.get("problem"):
        out.append('<div class="block-label">Today\'s problem</div>')
        out.append(render_problem(card["problem"]))

    if card.get("drill"):
        out.append('<div class="block-label">The set</div><div class="drill">')
        out += [render_problem(d, d.get("cue")) for d in card["drill"]]
        out.append("</div>")

    return "".join(out)


def render_locked(card: dict) -> str:
    """Everything hidden until you commit. Revealing this is what costs XP."""
    out = []

    tpl = card.get("template")
    if tpl:
        src = "\n".join(tpl) if isinstance(tpl, list) else str(tpl)
        out.append(
            '<div class="block-label">Template</div>'
            '<div class="code"><div class="code__bar">python'
            '<button class="code__copy" data-copy>copy</button></div>'
            "<pre><code>" + highlight(src) + "</code></pre></div>"
        )

    cx = card.get("complexity")
    if cx:
        out.append(
            '<div class="cx">'
            '<div class="cx__item"><div class="cx__k">Time</div>'
            '<div class="cx__v">' + inline(cx.get("time", "?")) + "</div></div>"
            '<div class="cx__item"><div class="cx__k">Space</div>'
            '<div class="cx__v">' + inline(cx.get("space", "?")) + "</div></div>"
            "</div>"
        )

    if card.get("keyInsights"):
        out.append('<div class="block-label">What actually matters</div><ul>')
        out += ["<li>" + inline(i) + "</li>" for i in card["keyInsights"]]
        out.append("</ul>")

    if card.get("trap"):
        out.append(
            '<div class="box box--trap">'
            '<span class="box__k">The follow-up that kills people</span>'
            + inline(card["trap"]) + "</div>"
        )

    return "".join(out)


# ────────────────────────────────────────────────────────────────── loading ──

def load() -> tuple[dict, list]:
    prog_path = DATA / "program.json"
    if not prog_path.exists():
        die("missing " + str(prog_path))
    program = json.loads(prog_path.read_text(encoding="utf-8"))

    days = []
    for path in sorted(DATA.glob("day-*.json")):
        try:
            days.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            die(path.name + ": " + str(exc))
    return program, days


def die(msg: str) -> None:
    print("build failed: " + msg, file=sys.stderr)
    raise SystemExit(1)


def validate(program: dict, days: list) -> None:
    cycle = program.get("cycleDays", 30)
    seen_days, seen_ids = set(), {}

    if len(days) != cycle:
        die("expected " + str(cycle) + " day files, found " + str(len(days)))

    for d in days:
        n = d.get("day")
        where = "day " + str(n)
        if not isinstance(n, int) or not 1 <= n <= cycle:
            die("bad day number: " + repr(n))
        if n in seen_days:
            die("duplicate day " + str(n))
        seen_days.add(n)

        if d.get("kind", "core") not in KINDS:
            die(where + ": bad kind " + repr(d.get("kind")))
        for key in ("title", "focus"):
            if not d.get(key):
                die(where + ": missing " + key)

        cards = d.get("cards") or []
        if len(cards) != 5:
            die(where + ": expected 5 cards, found " + str(len(cards)))

        for c in cards:
            cid = c.get("id")
            if not cid:
                die(where + ": a card has no id")
            if cid in seen_ids:
                die("duplicate card id " + repr(cid)
                    + " (day " + str(seen_ids[cid]) + " and day " + str(n) + ")")
            seen_ids[cid] = n

            if c.get("lane") not in LANES:
                die(where + "/" + cid + ": bad lane " + repr(c.get("lane")))
            for key in ("title", "trigger", "recall"):
                if not c.get(key):
                    die(where + "/" + cid + ": missing " + key)
            if not c.get("template") and not c.get("drill"):
                die(where + "/" + cid + ": needs a template or a drill list")

            for p in ([c["problem"]] if c.get("problem") else []) + list(c.get("drill", [])):
                for key in ("lc", "name", "slug", "diff"):
                    if key not in p:
                        die(where + "/" + cid + ": problem missing " + key)
                if p["diff"] not in DIFFS:
                    die(where + "/" + cid + ": bad difficulty " + repr(p["diff"]))

    missing = sorted(set(range(1, cycle + 1)) - seen_days)
    if missing:
        die("missing days: " + ", ".join(map(str, missing)))


# ─────────────────────────────────────────────────────────────── the payload ──

def build_payload(program: dict, days: list) -> dict:
    lanes = program["lanes"]
    default_timer = program.get("cardTimerSec", 240)
    out = {}

    for d in sorted(days, key=lambda x: x["day"]):
        cards = []
        for c in d["cards"]:
            cards.append({
                "id": c["id"],
                "lane": c["lane"],
                "laneName": lanes[c["lane"]]["name"],
                "title": plain(c["title"]),
                "recall": inline(c["recall"]),
                "timer": int(c.get("timerSec", default_timer)),
                "open": render_open(c, lanes[c["lane"]]["name"]),
                "locked": render_locked(c),
                "search": plain(
                    c["title"] + " " + c["trigger"] + " "
                    + " ".join(c.get("patterns", []))
                    + " " + " ".join(c.get("useWhen", []))
                ).lower(),
            })

        out[str(d["day"])] = {
            "day": d["day"],
            "title": plain(d["title"]),
            "kind": d.get("kind", "core"),
            "focus": plain(d["focus"]),
            "label": " · ".join(plain(c["title"]) for c in d["cards"]),
            "cards": cards,
        }

    return out


def js_literal(obj) -> str:
    """JSON that is safe to drop inside a <script> block."""
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


# ─────────────────────────────────────────────────────────────────── output ──

PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<meta name="description" content="__TAGLINE__">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;family=JetBrains+Mono:wght@400;500;700&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/dsa-master.css">

<script>
/* Applied before first paint so the theme never flashes. */
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t) document.documentElement.setAttribute('data-theme', t);
    if (localStorage.getItem('dsa:v2:size') === 'lg') {
      document.documentElement.classList.add('pending-large');
    }
  } catch (e) {}
})();
</script>
</head>
<body>

<div class="app">

  <header class="topbar">
    <div class="topbar__logo" id="goHome" role="button" tabindex="0">DSA Mastery</div>
    <div class="topbar__spacer"></div>
    <div class="topbar__meters">
      <span class="meter meter--xp"    id="mXp">XP <b>0</b></span>
      <span class="meter meter--rank"  id="mRank">Cold Start</span>
      <span class="meter meter--streak" id="mStreak">Streak <b>0</b></span>
      <span class="meter meter--clean" id="mClean">Clean <b>0%</b></span>
    </div>
    <button class="btn-icon" id="sizeBtn" title="Larger text" aria-pressed="false">Aa</button>
    <button class="btn-icon" id="resetBtn">Reset</button>
  </header>

  <div class="xprail"><div class="xprail__fill" id="xpFill"></div></div>

  <!-- ============================ HOME ============================ -->
  <main class="view is-active" id="homeView">
    <div class="wrap">

      <section class="hero">
        <div class="hero__grid">
          <div>
            <div class="hero__eyebrow" id="heroEyebrow">Today</div>
            <h1 id="heroTitle">Day 1</h1>
            <p class="hero__focus" id="heroFocus"></p>
            <div class="hero__lanes" id="heroLanes"></div>
            <div class="hero__actions">
              <button class="btn-primary" id="startBtn">Start today's run &rarr;</button>
              <button class="btn-ghost" id="weakBtn">Drill my weak spots</button>
            </div>
          </div>
          <div class="dial">
            <svg width="132" height="132" viewBox="0 0 132 132" aria-hidden="true">
              <defs>
                <linearGradient id="dialgrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stop-color="var(--accent)"></stop>
                  <stop offset="100%" stop-color="var(--accent-2)"></stop>
                </linearGradient>
              </defs>
              <circle class="dial__track" cx="66" cy="66" r="56" fill="none" stroke-width="9"></circle>
              <circle class="dial__fill" id="dialFill" cx="66" cy="66" r="56" fill="none" stroke-width="9"
                      stroke-dasharray="351.858" stroke-dashoffset="351.858"></circle>
            </svg>
            <div class="dial__inner">
              <div class="dial__num" id="dialNum">1</div>
              <div class="dial__lbl">Cycle</div>
            </div>
          </div>
        </div>
      </section>

      <div class="stats">
        <div class="stat stat--accent"><div class="stat__num" id="sXp">0</div><div class="stat__lbl">Total XP</div><div class="stat__sub" id="sRankNote"></div></div>
        <div class="stat"><div class="stat__num" id="sDays">0</div><div class="stat__lbl">Runs finished</div><div class="stat__sub" id="sDaysNote"></div></div>
        <div class="stat"><div class="stat__num" id="sClean">0%</div><div class="stat__lbl">Clean recall</div><div class="stat__sub">Recalled without peeking</div></div>
        <div class="stat"><div class="stat__num" id="sSolid">0</div><div class="stat__lbl">Solid concepts</div><div class="stat__sub" id="sSolidNote">of __CONCEPTS__</div></div>
        <div class="stat stat--warn"><div class="stat__num" id="sShaky">0</div><div class="stat__lbl">Shaky concepts</div><div class="stat__sub">These resurface first</div></div>
      </div>

      <div class="sec-head">
        <h2>Last 13 weeks</h2>
        <span class="sec-head__note" id="heatNote"></span>
      </div>
      <div class="heat" id="heat"></div>
      <div class="heat__legend">
        <span>Quiet</span>
        <span class="heat__cell"></span>
        <span class="heat__cell" data-lvl="1"></span>
        <span class="heat__cell" data-lvl="2"></span>
        <span class="heat__cell" data-lvl="3"></span>
        <span>Full run</span>
      </div>

      <div class="sec-head">
        <h2>The cycle</h2>
        <span class="sec-head__note">30 days, 150 problems, then start again. Dotted days are retrieval and mock days.</span>
      </div>
      <div class="month" id="month"></div>

      <div class="sec-head">
        <h2>Weak spots</h2>
        <span class="sec-head__note">Rated shaky, or never recalled clean. Fix these before adding anything new.</span>
      </div>
      <div class="weak" id="weak"></div>

    </div>
  </main>

  <!-- ============================= RUN ============================= -->
  <main class="view" id="runView">
    <div class="wrap wrap--narrow">

      <div class="run-head">
        <button class="btn-ghost" id="backBtn">&larr; Cycle</button>
        <h1 id="runTitle">Day 1</h1>
        <div class="run-head__spacer"></div>
        <span class="meter" id="runElapsed">0:00</span>
      </div>

      <div class="segments" id="segments"></div>

      <div class="combo" id="combo">
        <span class="combo__label">Combo</span>
        <span class="combo__pips" id="comboPips"></span>
        <span class="combo__mult" id="comboMult">1.0&times;</span>
      </div>

      <article class="card" id="card">
        <div class="card__bar">
          <span class="lane-chip" id="cardLane"></span>
          <span class="card__pos" id="cardPos"></span>
          <div class="card__bar-spacer"></div>
          <span class="card__pos" id="cardId"></span>
        </div>
        <div class="card__body">
          <div id="cardOpen"></div>

          <section class="gate" id="gate">
            <div class="gate__k">Recall first, no peeking</div>
            <div class="gate__prompt" id="gatePrompt"></div>
            <div class="gate__row">
              <div class="ring" id="ring">
                <svg width="54" height="54" viewBox="0 0 54 54" aria-hidden="true">
                  <circle class="ring__track" cx="27" cy="27" r="23" fill="none" stroke-width="4"></circle>
                  <circle class="ring__fill" id="ringFill" cx="27" cy="27" r="23" fill="none" stroke-width="4"
                          stroke-dasharray="144.513" stroke-dashoffset="0"></circle>
                </svg>
                <span class="ring__t" id="ringT">4:00</span>
              </div>
              <button class="btn-win" id="hadItBtn">I had it</button>
              <button class="btn-peek" id="peekBtn">Show me</button>
              <span class="gate__hint">Space = had it &nbsp;&middot;&nbsp; P = show me</span>
            </div>
          </section>

          <div class="locked" id="locked" hidden></div>

          <div class="conf" id="conf" hidden>
            <span class="conf__k">Mark it</span>
            <button class="conf__btn" data-v="1">Shaky</button>
            <button class="conf__btn" data-v="2">Solid</button>
          </div>
        </div>
      </article>

      <nav class="runnav">
        <button class="btn-ghost" id="prevBtn">&larr;</button>
        <span class="runnav__dots" id="dots"></span>
        <button class="btn-ghost" id="nextBtn">&rarr;</button>
      </nav>

    </div>
  </main>

  <!-- =========================== COMPLETE =========================== -->
  <main class="view" id="doneView">
    <div class="wrap wrap--narrow">
      <section class="done-panel">
        <div class="confetti" id="confetti"></div>
        <div id="levelupSlot"></div>
        <h2 id="doneTitle">Day 1 complete</h2>
        <p class="done-panel__sub" id="doneSub"></p>
        <div class="done-grid">
          <div class="stat"><div class="stat__num" id="dXp">0</div><div class="stat__lbl">XP earned</div></div>
          <div class="stat"><div class="stat__num" id="dClean">0/5</div><div class="stat__lbl">Clean recalls</div></div>
          <div class="stat"><div class="stat__num" id="dCombo">0</div><div class="stat__lbl">Best combo</div></div>
          <div class="stat"><div class="stat__num" id="dTime">0:00</div><div class="stat__lbl">Time</div></div>
          <div class="stat"><div class="stat__num" id="dStreak">0</div><div class="stat__lbl">Day streak</div></div>
        </div>
        <div class="done-panel__actions">
          <button class="btn-primary" id="doneNextBtn">Next day &rarr;</button>
          <button class="btn-ghost" id="doneHomeBtn">Back to the cycle</button>
        </div>
      </section>
    </div>
  </main>

  <footer class="foot">__TAGLINE__ &nbsp;&middot;&nbsp; Progress is stored in this browser only.</footer>
</div>

<script>
"use strict";

var DAYS    = __DAYS__;
var PROGRAM = __PROGRAM__;

__RUNTIME__
</script>
</body>
</html>
"""


RUNTIME = r"""
/* ===================================================================
   STATE
   Keys are namespaced dsa:v2 so an older build's progress cannot be
   half-read into this one.
   =================================================================== */
var K = { xp: 'dsa:v2:xp', conf: 'dsa:v2:conf', log: 'dsa:v2:log', size: 'dsa:v2:size' };

function read(key, fallback) {
  try { var raw = localStorage.getItem(key); return raw === null ? fallback : JSON.parse(raw); }
  catch (e) { return fallback; }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}

var S = {
  xp:   read(K.xp, 0) || 0,
  conf: read(K.conf, {}) || {},   /* id -> {s: 1|2, n: cleanCount, t: 'YYYY-MM-DD'} */
  log:  read(K.log, {}) || {}     /* 'YYYY-MM-DD' -> {day, xp, clean, total} */
};

var CYCLE = PROGRAM.cycleDays;
var TOTAL_CONCEPTS = Object.keys(DAYS).reduce(function (n, k) { return n + DAYS[k].cards.length; }, 0);

/* ---- dates ---- */
function todayKey(d) {
  d = d || new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function todaysDay() { return ((new Date().getDate() - 1) % CYCLE) + 1; }

/* ---- derived ---- */
function runsDone()  { return Object.keys(S.log).length; }
function cycleNo()   { return Math.floor(runsDone() / CYCLE) + 1; }
function cycleProgress() { return (runsDone() % CYCLE) / CYCLE; }

function rankFor(xp) {
  var r = PROGRAM.ranks[0];
  for (var i = 0; i < PROGRAM.ranks.length; i++) if (xp >= PROGRAM.ranks[i].at) r = PROGRAM.ranks[i];
  return r;
}
function nextRank(xp) {
  for (var i = 0; i < PROGRAM.ranks.length; i++) if (xp < PROGRAM.ranks[i].at) return PROGRAM.ranks[i];
  return null;
}

function streak() {
  var n = 0, d = new Date();
  if (!S.log[todayKey(d)]) d.setDate(d.getDate() - 1);   /* today not done yet is fine */
  while (S.log[todayKey(d)]) { n++; d.setDate(d.getDate() - 1); }
  return n;
}

function cleanRate() {
  var clean = 0, total = 0;
  for (var k in S.log) { clean += S.log[k].clean || 0; total += S.log[k].total || 0; }
  return total ? Math.round((clean / total) * 100) : 0;
}

function confCounts() {
  var solid = 0, shaky = 0;
  for (var id in S.conf) { if (S.conf[id].s === 2) solid++; else if (S.conf[id].s === 1) shaky++; }
  return { solid: solid, shaky: shaky };
}

/* A concept is weak if it is marked shaky, or has never been recalled clean
   in a cycle where it was seen. Untouched concepts are not weak, they are new. */
function weakList() {
  var out = [];
  for (var d in DAYS) {
    DAYS[d].cards.forEach(function (c, i) {
      var r = S.conf[c.id];
      if (!r) return;
      if (r.s === 1 || !r.n) out.push({ day: DAYS[d].day, idx: i, card: c, rec: r });
    });
  }
  return out.sort(function (a, b) { return (a.rec.s || 9) - (b.rec.s || 9) || a.day - b.day; });
}

/* ===================================================================
   SMALL HELPERS
   =================================================================== */
function $(id) { return document.getElementById(id); }
function fmt(sec) { return Math.floor(sec / 60) + ':' + String(Math.floor(sec % 60)).padStart(2, '0'); }
function bump(el) { if (!el) return; el.classList.remove('is-bump'); void el.offsetWidth; el.classList.add('is-bump'); }

function xpFloat(text, anchor) {
  var r = anchor.getBoundingClientRect();
  var el = document.createElement('div');
  el.className = 'xpfloat';
  el.textContent = text;
  el.style.left = (r.left + r.width / 2 - 20) + 'px';
  el.style.top = (r.top - 6) + 'px';
  document.body.appendChild(el);
  setTimeout(function () { el.remove(); }, 1200);
}

/* ===================================================================
   TOP METERS
   =================================================================== */
function paintMeters() {
  var rank = rankFor(S.xp), nxt = nextRank(S.xp);
  $('mXp').innerHTML = 'XP <b>' + S.xp.toLocaleString() + '</b>';
  $('mRank').textContent = rank.name;
  $('mStreak').innerHTML = 'Streak <b>' + streak() + '</b>';
  $('mClean').innerHTML = 'Clean <b>' + cleanRate() + '%</b>';

  var pct = nxt ? Math.min(100, ((S.xp - rank.at) / (nxt.at - rank.at)) * 100) : 100;
  $('xpFill').style.width = pct + '%';
}

/* ===================================================================
   HOME
   =================================================================== */
function paintHome() {
  var day = todaysDay(), data = DAYS[String(day)];

  $('heroEyebrow').textContent = 'Day ' + day + ' of ' + CYCLE + ' · Cycle ' + cycleNo()
    + (data.kind === 'core' ? '' : ' · ' + (data.kind === 'mock' ? 'Simulation' : 'Retrieval'));
  $('heroTitle').textContent = data.title;
  $('heroFocus').textContent = data.focus;

  $('heroLanes').innerHTML = data.cards.map(function (c) {
    return '<span class="lane-chip lane-' + c.lane + '">' + c.title + '</span>';
  }).join('');

  $('startBtn').textContent = (S.log[todayKey()] ? 'Run day ' + day + ' again' : "Start day " + day) + ' →';

  /* cycle dial */
  var circ = 2 * Math.PI * 56;
  $('dialFill').style.strokeDashoffset = String(circ * (1 - cycleProgress()));
  $('dialNum').textContent = cycleNo();

  /* stats */
  var rank = rankFor(S.xp), nxt = nextRank(S.xp), counts = confCounts();
  $('sXp').textContent = S.xp.toLocaleString();
  $('sRankNote').textContent = nxt
    ? rank.name + ' · ' + (nxt.at - S.xp).toLocaleString() + ' to ' + nxt.name
    : rank.name + ' · ' + rank.note;
  $('sDays').textContent = runsDone();
  $('sDaysNote').textContent = (runsDone() % CYCLE) + ' of ' + CYCLE + ' this cycle';
  $('sClean').textContent = cleanRate() + '%';
  $('sSolid').textContent = counts.solid;
  $('sSolidNote').textContent = 'of ' + TOTAL_CONCEPTS + ' concepts';
  $('sShaky').textContent = counts.shaky;

  paintHeat();
  paintMonth(day);
  paintWeak();
  paintMeters();
}

function paintHeat() {
  var cells = [], d = new Date(), hits = 0;
  d.setDate(d.getDate() - 90);
  for (var i = 0; i < 91; i++) {
    var key = todayKey(d), entry = S.log[key], lvl = 0;
    if (entry) {
      hits++;
      lvl = entry.clean >= 5 ? 3 : entry.clean >= 3 ? 2 : 1;
    }
    cells.push('<span class="heat__cell"' + (lvl ? ' data-lvl="' + lvl + '"' : '')
      + ' title="' + key + (entry ? ' · day ' + entry.day + ' · ' + entry.clean + '/' + entry.total + ' clean' : ' · nothing') + '"></span>');
    d.setDate(d.getDate() + 1);
  }
  $('heat').innerHTML = cells.join('');
  $('heatNote').textContent = hits + ' of the last 91 days';
}

function paintMonth(today) {
  var out = [];
  for (var n = 1; n <= CYCLE; n++) {
    var data = DAYS[String(n)];
    var cls = 'tile tile--' + data.kind;
    if (n === today) cls += ' is-today';

    var solid = 0, shaky = 0, dots = data.cards.map(function (c) {
      var r = S.conf[c.id];
      if (!r) return '<span class="tile__dot"></span>';
      if (r.s === 2) { solid++; return '<span class="tile__dot is-solid"></span>'; }
      shaky++; return '<span class="tile__dot is-shaky"></span>';
    }).join('');

    if (solid === 5) cls += ' is-done';
    if (shaky) cls += ' is-weak';

    out.push(
      '<button class="' + cls + '" data-day="' + n + '">' +
        '<span class="tile__top">' +
          '<span class="tile__num">' + String(n).padStart(2, '0') + '</span>' +
          '<span class="tile__mark">' + (solid === 5 ? '✓' : n === today ? '→' : '') + '</span>' +
        '</span>' +
        '<span class="tile__name">' + data.title + '</span>' +
        '<span class="tile__dots">' + dots + '</span>' +
      '</button>'
    );
  }
  $('month').innerHTML = out.join('');
}

function paintWeak() {
  var list = weakList();
  if (!list.length) {
    $('weak').innerHTML = '<div class="empty-note">Nothing marked shaky. Either you are in good shape, '
      + 'or you have not been honest on the Mark it buttons yet.</div>';
    return;
  }
  $('weak').innerHTML = list.slice(0, 24).map(function (w) {
    return '<button class="weak__row" data-day="' + w.day + '" data-idx="' + w.idx + '">'
      + '<span class="lane-chip lane-' + w.card.lane + '">' + w.card.laneName + '</span>'
      + '<span class="weak__title">' + w.card.title + '</span>'
      + '<span class="weak__meta">Day ' + w.day + ' · ' + (w.rec.n || 0) + ' clean</span>'
      + '</button>';
  }).join('');
}

/* ===================================================================
   RUN
   =================================================================== */
var R = null;   /* the live run, or null */

/* Both intervals are tracked outside R. Starting a second run while one is
   live used to orphan the old interval, which then fired against a null R. */
var CARD_TICK = null;
var RUN_TICK = null;

function clearTicks() {
  if (CARD_TICK) { clearInterval(CARD_TICK); CARD_TICK = null; }
  if (RUN_TICK)  { clearInterval(RUN_TICK);  RUN_TICK = null; }
}

function startRun(day, idx) {
  var data = DAYS[String(day)];
  if (!data) return;
  clearTicks();
  R = {
    day: day, data: data, i: idx || 0,
    results: new Array(data.cards.length).fill(null),  /* 'clean' | 'peek' */
    combo: 0, bestCombo: 0, xp: 0,
    started: Date.now(), cardStarted: 0
  };
  show('runView');
  $('runTitle').textContent = 'Day ' + day + ' · ' + data.title;
  renderCard(0);

  RUN_TICK = setInterval(function () {
    if (!R) { clearTicks(); return; }
    $('runElapsed').textContent = fmt((Date.now() - R.started) / 1000);
  }, 1000);
}

function renderCard(dir) {
  var c = R.data.cards[R.i];
  var card = $('card');

  $('cardLane').className = 'lane-chip lane-' + c.lane;
  $('cardLane').textContent = c.laneName;
  $('cardPos').textContent = (R.i + 1) + ' of ' + R.data.cards.length;
  $('cardId').textContent = c.id;

  $('cardOpen').innerHTML = c.open;
  $('locked').innerHTML = c.locked;
  $('gatePrompt').innerHTML = c.recall;

  var done = R.results[R.i];
  $('gate').hidden = !!done;
  $('locked').hidden = !done;
  $('conf').hidden = !done;
  paintConf(c.id);

  if (!done) startTimer(c.timer);
  else stopTimer();

  paintSegments();
  paintDots();
  paintCombo();

  if (dir) { card.classList.remove('is-flipping'); void card.offsetWidth; card.classList.add('is-flipping'); }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ---- timer ring ---- */
function startTimer(seconds) {
  stopTimer();
  R.cardStarted = Date.now();
  var circ = 2 * Math.PI * 23;
  var fill = $('ringFill'), ring = $('ring'), label = $('ringT');
  fill.style.strokeDasharray = String(circ);

  function paint() {
    if (!R) { stopTimer(); return; }
    var left = seconds - (Date.now() - R.cardStarted) / 1000;
    if (left < 0) left = 0;
    label.textContent = fmt(left);
    fill.style.strokeDashoffset = String(circ * (1 - left / seconds));
    ring.classList.toggle('is-low', left <= 30);
    if (left === 0) stopTimer();
  }
  paint();
  CARD_TICK = setInterval(paint, 1000);
}
function stopTimer() { if (CARD_TICK) { clearInterval(CARD_TICK); CARD_TICK = null; } }

function elapsedOnCard() { return (Date.now() - R.cardStarted) / 1000; }

/* ---- resolving a card ---- */
function resolve(clean) {
  if (!R || R.results[R.i]) return;
  var x = PROGRAM.xp;
  var secs = elapsedOnCard();
  stopTimer();

  var base = clean ? x.clean : x.peek;
  var speed = (clean && secs <= x.speedBonusSec) ? x.speedBonus : 0;

  if (clean) { R.combo++; R.bestCombo = Math.max(R.bestCombo, R.combo); }
  else { R.combo = 0; }

  var mult = Math.min(x.comboCap, 1 + Math.max(0, R.combo - 1) * x.comboStep);
  var gained = Math.round((base + speed) * mult);

  R.results[R.i] = clean ? 'clean' : 'peek';
  R.xp += gained;
  S.xp += gained;
  write(K.xp, S.xp);

  /* confidence: a clean recall counts, a peek marks it shaky unless already solid today */
  var id = R.data.cards[R.i].id;
  var rec = S.conf[id] || { s: 0, n: 0, t: '' };
  if (clean) { rec.s = 2; rec.n = (rec.n || 0) + 1; }
  else { rec.s = 1; }
  rec.t = todayKey();
  S.conf[id] = rec;
  write(K.conf, S.conf);

  $('gate').hidden = true;
  $('locked').hidden = false;
  $('locked').classList.remove('is-revealing'); void $('locked').offsetWidth;
  $('locked').classList.add('is-revealing');
  $('conf').hidden = false;
  paintConf(id);

  xpFloat('+' + gained + (speed ? ' ⚡' : ''), clean ? $('hadItBtn') : $('peekBtn'));
  bump($('mXp'));
  paintMeters();
  paintSegments();
  paintDots();
  paintCombo();
}

function paintConf(id) {
  var rec = S.conf[id];
  Array.prototype.forEach.call($('conf').querySelectorAll('.conf__btn'), function (b) {
    b.classList.toggle('is-on', !!rec && rec.s === Number(b.dataset.v));
  });
}

function paintSegments() {
  $('segments').innerHTML = R.results.map(function (r, i) {
    var cls = 'segment';
    if (r === 'clean') cls += ' is-clean';
    else if (r === 'peek') cls += ' is-peeked';
    else if (i === R.i) cls += ' is-current';
    return '<span class="' + cls + '"></span>';
  }).join('');
}

function paintDots() {
  $('dots').innerHTML = R.results.map(function (r, i) {
    return '<button class="dot' + (i === R.i ? ' is-on' : r ? ' is-done' : '') + '" data-i="' + i + '" aria-label="Card ' + (i + 1) + '"></button>';
  }).join('');
  $('prevBtn').disabled = R.i === 0;
  $('nextBtn').textContent = R.i === R.data.cards.length - 1 ? 'Finish →' : '→';
}

function paintCombo() {
  var x = PROGRAM.xp;
  var lit = Math.min(6, R.combo);
  var pips = '';
  for (var i = 0; i < 6; i++) pips += '<span class="combo__pip' + (i < lit ? ' is-lit' : '') + '"></span>';
  $('comboPips').innerHTML = pips;
  var mult = Math.min(x.comboCap, 1 + Math.max(0, R.combo - 1) * x.comboStep);
  $('comboMult').textContent = mult.toFixed(1) + '×';
  $('combo').classList.toggle('is-hot', R.combo >= 3);
}

function step(delta) {
  var next = R.i + delta;
  if (next < 0) return;
  if (next >= R.data.cards.length) { finishRun(); return; }
  R.i = next;
  renderCard(delta);
}

/* ---- finishing ---- */
function finishRun() {
  if (!R) return;
  var clean = R.results.filter(function (r) { return r === 'clean'; }).length;
  var total = R.results.length;
  var attempted = R.results.filter(Boolean).length;
  var secs = Math.round((Date.now() - R.started) / 1000);

  var rankBefore = rankFor(S.xp).name;
  if (clean === total) { R.xp += PROGRAM.xp.perfectDay; S.xp += PROGRAM.xp.perfectDay; write(K.xp, S.xp); }
  var rankAfter = rankFor(S.xp).name;

  if (attempted) {
    var key = todayKey();
    var prev = S.log[key];
    S.log[key] = {
      day: R.day,
      xp: (prev ? prev.xp : 0) + R.xp,
      clean: Math.max(prev ? prev.clean : 0, clean),
      total: total
    };
    write(K.log, S.log);
  }

  clearTicks();

  $('doneTitle').textContent = 'Day ' + R.day + ' complete';
  $('doneSub').textContent = clean === total
    ? 'Five for five, no peeking. That is the run you want every time.'
    : clean >= 3
      ? 'Solid run. The ones you peeked at are now on your weak list.'
      : 'The peeked ones are flagged. Come back to them before the next cycle.';

  $('dXp').textContent = '+' + R.xp;
  $('dClean').textContent = clean + '/' + total;
  $('dCombo').textContent = R.bestCombo;
  $('dTime').textContent = fmt(secs);
  $('dStreak').textContent = streak();

  $('levelupSlot').innerHTML = (rankAfter !== rankBefore)
    ? '<div class="levelup">⭐ New rank: ' + rankAfter + '</div>' : '';

  confetti(clean === total ? 40 : 18);
  $('doneNextBtn').dataset.day = String(R.day % CYCLE + 1);

  R = null;
  paintMeters();
  show('doneView');
}

function confetti(n) {
  var colors = ['var(--accent)', 'var(--c-win)', 'var(--c-trigger)', 'var(--lane-arrays)', 'var(--lane-structures)'];
  var html = '';
  for (var i = 0; i < n; i++) {
    html += '<i style="left:' + (Math.random() * 100) + '%;background:' + colors[i % colors.length]
      + ';animation-delay:' + (Math.random() * 0.7).toFixed(2) + 's"></i>';
  }
  $('confetti').innerHTML = html;
}

/* ===================================================================
   VIEW SWITCHING
   =================================================================== */
function show(id) {
  ['homeView', 'runView', 'doneView'].forEach(function (v) {
    $(v).classList.toggle('is-active', v === id);
  });
  if (id === 'homeView') paintHome();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goHome() {
  clearTicks();
  R = null;
  show('homeView');
}

/* ===================================================================
   WIRING
   =================================================================== */
$('goHome').addEventListener('click', goHome);
$('goHome').addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') goHome(); });
$('backBtn').addEventListener('click', goHome);
$('doneHomeBtn').addEventListener('click', goHome);
$('startBtn').addEventListener('click', function () { startRun(todaysDay(), 0); });
$('doneNextBtn').addEventListener('click', function () { startRun(Number(this.dataset.day), 0); });

$('weakBtn').addEventListener('click', function () {
  var list = weakList();
  if (!list.length) { document.querySelector('.weak').scrollIntoView({ behavior: 'smooth' }); return; }
  startRun(list[0].day, list[0].idx);
});

$('month').addEventListener('click', function (e) {
  var t = e.target.closest('.tile');
  if (t) startRun(Number(t.dataset.day), 0);
});

$('weak').addEventListener('click', function (e) {
  var t = e.target.closest('.weak__row');
  if (t) startRun(Number(t.dataset.day), Number(t.dataset.idx));
});

$('hadItBtn').addEventListener('click', function () { resolve(true); });
$('peekBtn').addEventListener('click', function () { resolve(false); });
$('prevBtn').addEventListener('click', function () { step(-1); });
$('nextBtn').addEventListener('click', function () { step(1); });

$('dots').addEventListener('click', function (e) {
  var d = e.target.closest('.dot');
  if (!d) return;
  var i = Number(d.dataset.i);
  var dir = i > R.i ? 1 : -1;
  R.i = i;
  renderCard(dir);
});

$('conf').addEventListener('click', function (e) {
  var b = e.target.closest('.conf__btn');
  if (!b || !R) return;
  var id = R.data.cards[R.i].id;
  var v = Number(b.dataset.v);
  var rec = S.conf[id] || { s: 0, n: 0, t: '' };
  rec.s = rec.s === v ? 0 : v;
  rec.t = todayKey();
  S.conf[id] = rec;
  write(K.conf, S.conf);
  paintConf(id);
});

/* copy buttons live inside injected HTML, so delegate from the card */
$('card').addEventListener('click', function (e) {
  var b = e.target.closest('[data-copy]');
  if (!b) return;
  var pre = b.closest('.code').querySelector('pre');
  navigator.clipboard.writeText(pre.textContent).then(function () {
    b.textContent = 'copied';
    setTimeout(function () { b.textContent = 'copy'; }, 1400);
  }, function () { b.textContent = 'failed'; });
});

/* ---- reading size ---- */
function applySize(on) {
  document.body.classList.toggle('type-large', on);
  var b = $('sizeBtn');
  b.classList.toggle('is-on', on);
  b.setAttribute('aria-pressed', on ? 'true' : 'false');
  b.title = on ? 'Default text size' : 'Larger text';
  write(K.size, on ? 'lg' : 'sm');
}
$('sizeBtn').addEventListener('click', function () {
  applySize(!document.body.classList.contains('type-large'));
});

/* ---- reset ---- */
$('resetBtn').addEventListener('click', function () {
  if (!confirm('Reset everything?\n\nThis clears your XP, streak, confidence ratings and the whole heatmap. It cannot be undone.')) return;
  S = { xp: 0, conf: {}, log: {} };
  try { localStorage.removeItem(K.xp); localStorage.removeItem(K.conf); localStorage.removeItem(K.log); } catch (e) {}
  goHome();
});

/* ---- keyboard ---- */
document.addEventListener('keydown', function (e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (!R) {
    if (e.key === 'Enter') { e.preventDefault(); startRun(todaysDay(), 0); }
    return;
  }
  var open = !$('gate').hidden;
  if (e.key === 'Escape') { goHome(); }
  else if (e.key === 'ArrowLeft')  { e.preventDefault(); step(-1); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  else if (open && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); resolve(true); }
  else if (open && (e.key === 'p' || e.key === 'P')) { e.preventDefault(); resolve(false); }
});

/* ---- theme follows the portfolio shell ---- */
window.addEventListener('storage', function (e) {
  if (e.key === 'theme' && e.newValue) document.documentElement.setAttribute('data-theme', e.newValue);
});

/* ===================================================================
   INIT
   =================================================================== */
applySize(read(K.size, 'sm') === 'lg');
document.documentElement.classList.remove('pending-large');
show('homeView');
"""


def main() -> None:
    program, days = load()
    validate(program, days)
    payload = build_payload(program, days)

    concepts = sum(len(d["cards"]) for d in payload.values())

    page = (PAGE
            .replace("__RUNTIME__", RUNTIME)
            .replace("__DAYS__", js_literal(payload))
            .replace("__PROGRAM__", js_literal(program))
            .replace("__TITLE__", html.escape(program["title"] + ": 30-Day Revision Loop"))
            .replace("__TAGLINE__", html.escape(program["tagline"]))
            .replace("__CONCEPTS__", str(concepts)))

    for bad in ("—", "&mdash;", "&#8212;"):
        if bad in page:
            die("an em dash (" + bad + ") survived into the output")

    OUT.write_text(page, encoding="utf-8", newline="\n")

    problems = set()
    drills = 0
    for d in days:
        for c in d["cards"]:
            if c.get("problem"):
                problems.add(c["problem"]["lc"])
            for x in c.get("drill", []):
                problems.add(x["lc"])
                drills += 1

    print(OUT.name + "  " + str(len(page) // 1024) + " KB")
    print("  days          " + str(len(days)))
    print("  cards         " + str(concepts))
    print("  problems      " + str(len(problems)) + " distinct LeetCode links")
    print("  drill entries " + str(drills))


if __name__ == "__main__":
    main()
