#!/usr/bin/env python3
"""
War Room builder.

Reads every guide/data/*.json track file and emits war-room.html at the repo
root. All layout comes from loops here, so every concept card in the guide is
structurally identical and one CSS fix lands everywhere.

    python guide/build.py

Data shape (one file per track):

    {
      "id": "ai",
      "name": "AI Systems",
      "desc": "one line for the tile",
      "color": "#8B7FE8",
      "modules": [
        {
          "id": "rag",
          "name": "RAG",
          "desc": "one line under the module title",
          "bullet": "the exact resume line this module defends",   # optional
          "concepts": [
            {
              "t":       "Chunking",                # term
              "tier":    "core" | "deep" | "jargon",
              "resume":  true,                      # optional: on your resume
              "one":     "one-breath definition",
              "analogy": "real-life comparison",    # optional
              "points":  ["mechanism bullet", ...], # optional
              "code":    {"lang":"python","cap":"...","src":"..."},  # optional
              "qa":      [{"q":"...","a":"..."}],   # optional
              "trap":    "the follow-up that kills people",          # optional
              "say":     "the sentence to say out loud"              # optional
            }
          ]
        }
      ]
    }

Inline markup allowed in every prose string: `code`, **bold**.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
OUT = ROOT / "war-room.html"


# ───────────────────────────────────────────────────────────── inline markup ──

_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline(text: str) -> str:
    """Escape, then apply the tiny markup subset the data files use."""
    out = html.escape(str(text), quote=False)
    out = _CODE_RE.sub(lambda m: "<code>" + m.group(1) + "</code>", out)
    out = _BOLD_RE.sub(lambda m: "<strong>" + m.group(1) + "</strong>", out)
    return out


def plain(text: str) -> str:
    """Markup-stripped version, for the search index."""
    out = _CODE_RE.sub(lambda m: m.group(1), str(text))
    return _BOLD_RE.sub(lambda m: m.group(1), out)


# ────────────────────────────────────────────────────────────── highlighting ──
#
# Build-time syntax highlighting: no client JS, nothing to go wrong at runtime,
# and the page still works with scripting off. Deliberately shallow - enough to
# make a template readable at a glance, not a real parser.

KW = {
    "python": (
        "False None True and as assert async await break class continue def del "
        "elif else except finally for from global if import in is lambda nonlocal "
        "not or pass raise return try while with yield match case"
    ),
    "java": (
        "abstract assert boolean break byte case catch char class const continue "
        "default do double else enum extends final finally float for goto if "
        "implements import instanceof int interface long native new package "
        "private protected public return short static strictfp super switch "
        "synchronized this throw throws transient try void volatile while var "
        "record sealed yield true false null"
    ),
    "js": (
        "async await break case catch class const continue debugger default "
        "delete do else export extends finally for function if import in "
        "instanceof let new of return static super switch this throw try typeof "
        "var void while with yield true false null undefined interface type "
        "implements enum readonly as satisfies keyof infer declare namespace"
    ),
    "sql": (
        "SELECT FROM WHERE JOIN LEFT RIGHT INNER OUTER FULL CROSS ON GROUP BY "
        "ORDER HAVING LIMIT OFFSET INSERT INTO VALUES UPDATE SET DELETE CREATE "
        "TABLE INDEX VIEW ALTER DROP UNION ALL DISTINCT AS AND OR NOT NULL IS IN "
        "EXISTS BETWEEN LIKE CASE WHEN THEN ELSE END WITH RECURSIVE OVER "
        "PARTITION PRIMARY KEY FOREIGN REFERENCES UNIQUE DEFAULT BEGIN COMMIT "
        "ROLLBACK TRANSACTION EXPLAIN ANALYZE RETURNING CONFLICT DO NOTHING "
        "select from where join on group by order having limit insert into "
        "values update set delete create table index alter drop union distinct "
        "as and or not null is in exists between like case when then else end"
    ),
    "bash": (
        "if then else elif fi for while do done case esac in function return "
        "export local set unset source echo cd exit trap shift read declare "
        "readonly break continue"
    ),
    "yaml": "true false null yes no on off",
    "text": "",
}

TYPES = {
    "python": "int str float bool list dict set tuple bytes None self cls Optional List Dict Any Union",
    "java": "String Integer Long Double Boolean List Map Set Optional Object Exception Override",
    "js": "string number boolean object Array Promise Map Set Record Partial console JSON Math",
    "sql": "",
    "bash": "",
    "yaml": "",
    "text": "",
}

LANG_ALIAS = {
    "py": "python",
    "python": "python",
    "java": "java",
    "js": "js",
    "javascript": "js",
    "ts": "js",
    "typescript": "js",
    "jsx": "js",
    "tsx": "js",
    "json": "js",
    "sql": "sql",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    "yaml": "yaml",
    "yml": "yaml",
    "dockerfile": "bash",
    "hcl": "bash",
    "text": "text",
    "": "text",
}

# Comment syntax per normalised language.
COMMENT = {
    "python": r"#[^\n]*",
    "java": r"//[^\n]*|/\*[\s\S]*?\*/",
    "js": r"//[^\n]*|/\*[\s\S]*?\*/",
    "sql": r"--[^\n]*|/\*[\s\S]*?\*/",
    "bash": r"#[^\n]*",
    "yaml": r"#[^\n]*",
    "text": r"(?!x)x",  # never matches
}

STRING = (
    r"\"\"\"[\s\S]*?\"\"\""
    r"|'''[\s\S]*?'''"
    r"|\"(?:\\.|[^\"\\\n])*\""
    r"|'(?:\\.|[^'\\\n])*'"
    r"|`(?:\\.|[^`\\])*`"
)

NUMBER = r"\b(?:0[xX][0-9a-fA-F_]+|\d[\d_]*\.?[\d_]*(?:[eE][-+]?\d+)?)\b"
FUNC = r"\b([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()"

_CACHE: dict[str, re.Pattern] = {}


def _pattern(lang: str) -> re.Pattern:
    if lang in _CACHE:
        return _CACHE[lang]
    kw = "|".join(sorted(set(KW[lang].split()), key=len, reverse=True)) or r"(?!x)x"
    ty = "|".join(sorted(set(TYPES[lang].split()), key=len, reverse=True)) or r"(?!x)x"
    pat = re.compile(
        "(?P<com>" + COMMENT[lang] + ")"
        "|(?P<str>" + STRING + ")"
        "|(?P<num>" + NUMBER + ")"
        "|(?P<kw>\\b(?:" + kw + ")\\b)"
        "|(?P<typ>\\b(?:" + ty + ")\\b)"
        "|(?P<fn>" + FUNC + ")"
    )
    _CACHE[lang] = pat
    return pat


def highlight(src: str, lang: str) -> str:
    lang = LANG_ALIAS.get((lang or "").lower(), "text")
    # Escape first (quote=False keeps ' and " intact so the string rule works),
    # then tokenise. The entities we introduce (&amp; &lt; &gt;) contain no
    # quotes or digits, so no rule can match inside them.
    esc = html.escape(src, quote=False)
    if lang == "text":
        return esc
    pat = _pattern(lang)

    def repl(m: re.Match) -> str:
        g = m.lastgroup
        cls = {"com": "tk-com", "str": "tk-str", "num": "tk-num",
               "kw": "tk-kw", "typ": "tk-typ", "fn": "tk-fn"}[g]
        return '<span class="' + cls + '">' + m.group(0) + "</span>"

    return pat.sub(repl, esc)


# ─────────────────────────────────────────────────────────────── components ──

TIER_LABEL = {"core": "Core", "deep": "Deep", "jargon": "Jargon"}


def render_box(kind: str, label: str, text: str) -> str:
    return (
        '<div class="box box--' + kind + '">'
        '<div class="box__l">' + label + "</div>"
        "<p>" + inline(text) + "</p>"
        "</div>"
    )


def render_code(code: dict) -> str:
    lang = code.get("lang", "text")
    cap = code.get("cap", "")
    src = code.get("src", "")
    return (
        '<div class="code-wrap">'
        '<div class="code-wrap__bar">'
        '<span class="code-wrap__lang">' + html.escape(lang) + "</span>"
        '<span class="code-wrap__cap">' + html.escape(cap) + "</span>"
        '<button class="code-wrap__copy" type="button" data-copy>copy</button>'
        "</div>"
        '<pre class="code">' + highlight(src, lang) + "</pre>"
        "</div>"
    )


def render_qa(qa: dict, uid: str) -> str:
    return (
        '<div class="qa" data-open="false">'
        '<button class="qa__q" type="button" data-qa aria-expanded="false" aria-controls="' + uid + '">'
        '<span class="qa__mark">Q</span>'
        '<span class="qa__qt">' + inline(qa["q"]) + "</span>"
        '<span class="qa__caret">&#9654;</span>'
        "</button>"
        '<div class="qa__a" id="' + uid + '">' + "".join(
            "<p>" + inline(p) + "</p>" for p in _as_list(qa["a"])
        ) + "</div>"
        "</div>"
    )


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def render_concept(c: dict, cid: str, n: int) -> str:
    tier = c.get("tier", "core")
    chips = ['<span class="chip chip--' + tier + '">' + TIER_LABEL.get(tier, tier) + "</span>"]
    if c.get("resume"):
        chips.insert(0, '<span class="chip chip--resume">On your r&eacute;sum&eacute;</span>')

    parts = [
        '<article class="cpt" id="' + cid + '" data-conf="0" data-revealed="false">',
        '<div class="cpt__head">',
        '<span class="cpt__idx">' + f"{n:02d}" + "</span>",
        '<h3 class="cpt__title">' + inline(c["t"]) + "</h3>",
        '<span class="cpt__tags">' + "".join(chips) + "</span>",
        "</div>",
        '<div class="cpt__body">',
        '<p class="cpt__one">' + inline(c["one"]) + "</p>",
    ]

    if c.get("analogy"):
        parts.append(render_box("analogy", "Think of it as", c["analogy"]))

    points = _as_list(c.get("points"))
    if points:
        parts.append('<div class="sub-l">How it actually works</div>')
        parts.append('<ul class="cpt__points">')
        parts += ["<li>" + inline(p) + "</li>" for p in points]
        parts.append("</ul>")

    if c.get("code"):
        for i, code in enumerate(_as_list(c["code"])):
            parts.append('<div class="sub-l">' + ("Template" if i == 0 else "Also") + "</div>")
            parts.append(render_code(code))

    qas = _as_list(c.get("qa"))
    if qas:
        parts.append('<div class="sub-l">They will ask</div>')
        parts += [render_qa(q, cid + "-a" + str(i)) for i, q in enumerate(qas)]

    if c.get("trap"):
        parts.append(render_box("trap", "Trap", c["trap"]))
    if c.get("say"):
        parts.append(render_box("say", "Say this", c["say"]))

    parts += [
        "</div>",
        '<div class="cpt__foot">',
        '<button class="mark mark--conf" type="button" data-conf-btn '
        'title="Cycle: unrated &rarr; shaky &rarr; solid">'
        '<span class="mark__dot"></span><span data-conf-label>Rate it</span></button>',
        '<button class="mark reveal-btn" type="button" data-reveal>Reveal</button>',
        "</div>",
        "</article>",
    ]
    return "".join(parts)


def render_module(track: dict, mod: dict) -> str:
    mid = track["id"] + "/" + mod["id"]
    concepts = mod["concepts"]

    head = [
        '<section class="view" data-view="module" data-mid="' + mid + '">',
        '<div class="pad pad--read">',
        '<nav class="crumb">',
        '<button type="button" data-go="#/">War Room</button><i>/</i>',
        '<button type="button" data-go="#/t/' + track["id"] + '">' + inline(track["name"]) + "</button><i>/</i>",
        "<span>" + inline(mod["name"]) + "</span>",
        "</nav>",
        '<header class="mod-head">',
        "<h1>" + inline(mod["name"]) + "</h1>",
    ]
    if mod.get("desc"):
        head.append("<p>" + inline(mod["desc"]) + "</p>")
    head.append("</header>")

    for b in _as_list(mod.get("bullet")):
        head.append(
            '<div class="mod-bullet">'
            '<div class="mod-bullet__l">The line this defends</div>'
            "<p>" + inline(b) + "</p></div>"
        )

    head += [
        '<div class="mod-toolbar">',
        '<div class="pill-row mod-toolbar__count">',
        '<button class="pill" type="button" data-filter="all" aria-pressed="true">All '
        + str(len(concepts)) + "</button>",
        '<button class="pill" type="button" data-filter="weak" aria-pressed="false">Not solid</button>',
        '<button class="pill" type="button" data-filter="shaky" aria-pressed="false">Shaky</button>',
        "</div>",
        '<button class="btn" type="button" data-expand-all>Open all answers</button>',
        '<button class="btn" type="button" data-collapse-all>Collapse</button>',
        "</div>",
        '<div class="concepts">',
    ]

    body = [
        render_concept(c, "c-" + track["id"] + "-" + mod["id"] + "-" + str(i), i + 1)
        for i, c in enumerate(concepts)
    ]

    foot = [
        "</div>",
        '<nav class="mod-nav" data-modnav></nav>',
        "</div>",
        "</section>",
    ]
    return "".join(head + body + foot)


def render_track(track: dict) -> str:
    tiles = []
    for i, mod in enumerate(track["modules"]):
        mid = track["id"] + "/" + mod["id"]
        tiles.append(
            '<button class="tile" type="button" data-go="#/m/' + mid + '" '
            'style="--tile-c:' + track["color"] + '">'
            '<div class="tile__top">'
            '<span class="tile__idx">' + f"{i + 1:02d}" + "</span>"
            '<span class="tile__name">' + inline(mod["name"]) + "</span>"
            "</div>"
            + ('<p class="tile__desc">' + inline(mod["desc"]) + "</p>" if mod.get("desc") else "")
            + '<div class="tile__meta">'
            "<span>" + str(len(mod["concepts"])) + "</span>"
            '<span class="tile__bar"><i data-bar="' + mid + '"></i></span>'
            '<span data-pct="' + mid + '">0%</span>'
            "</div></button>"
        )

    total = sum(len(m["concepts"]) for m in track["modules"])
    return (
        '<section class="view" data-view="track" data-tid="' + track["id"] + '">'
        '<div class="pad">'
        '<nav class="crumb"><button type="button" data-go="#/">War Room</button>'
        "<i>/</i><span>" + inline(track["name"]) + "</span></nav>"
        '<header class="mod-head"><h1>' + inline(track["name"]) + "</h1>"
        "<p>" + inline(track["desc"]) + "</p></header>"
        '<div class="section-title">' + str(len(track["modules"])) + " modules &middot; "
        + str(total) + " concepts</div>"
        '<div class="tiles">' + "".join(tiles) + "</div>"
        "</div></section>"
    )


def render_home(tracks: list) -> str:
    tiles = []
    for i, t in enumerate(tracks):
        total = sum(len(m["concepts"]) for m in t["modules"])
        tiles.append(
            '<button class="tile" type="button" data-go="#/t/' + t["id"] + '" '
            'style="--tile-c:' + t["color"] + '">'
            '<div class="tile__top">'
            '<span class="tile__idx">' + f"{i + 1:02d}" + "</span>"
            '<span class="tile__name">' + inline(t["name"]) + "</span>"
            "</div>"
            '<p class="tile__desc">' + inline(t["desc"]) + "</p>"
            '<div class="tile__meta">'
            "<span>" + str(total) + "</span>"
            '<span class="tile__bar"><i data-bar="' + t["id"] + '"></i></span>'
            '<span data-pct="' + t["id"] + '">0%</span>'
            "</div></button>"
        )

    n_con = sum(len(m["concepts"]) for t in tracks for m in t["modules"])
    n_mod = sum(len(t["modules"]) for t in tracks)
    n_qa = sum(
        len(_as_list(c.get("qa")))
        for t in tracks for m in t["modules"] for c in m["concepts"]
    )

    return (
        '<section class="view is-active" data-view="home">'
        '<div class="pad">'
        '<header class="hero">'
        '<div class="hero__eyebrow">Sachin Mishra &middot; interview prep</div>'
        "<h1>Every line of your r&eacute;sum&eacute;, defensible.</h1>"
        "<p>The whole stack you claim, résumé bullets, AI systems, system design, "
        "CI/CD, languages, fundamentals, broken into one-breath explanations, a "
        "real-life analogy, the mechanism, a template, and the exact follow-up an "
        "interviewer will use to find out whether you actually did the work.</p>"
        '<div class="stats">'
        '<div class="stat"><div class="stat__n">' + str(n_con) + '</div><div class="stat__l">Concepts</div></div>'
        '<div class="stat"><div class="stat__n">' + str(n_qa) + '</div><div class="stat__l">Interview questions</div></div>'
        '<div class="stat"><div class="stat__n">' + str(n_mod) + '</div><div class="stat__l">Modules</div></div>'
        '<div class="stat"><div class="stat__n" data-known-n>0</div><div class="stat__l">Marked solid</div></div>'
        "</div></header>"
        '<div class="section-title">Tracks</div>'
        '<div class="tiles">' + "".join(tiles) + "</div>"
        "</div></section>"
    )


def render_rail(tracks: list) -> str:
    out = ['<div class="rail__inner">', '<div class="rail__label">Tracks</div>']
    for t in tracks:
        out.append('<div class="rail-track">')
        out.append(
            '<button class="rail-track__btn" type="button" data-track-toggle="' + t["id"] + '" aria-expanded="false">'
            '<span class="rail-track__caret">&#9654;</span>'
            '<span class="rail-track__name">' + inline(t["name"]) + "</span>"
            '<span class="rail-track__n">' + str(len(t["modules"])) + "</span>"
            "</button>"
        )
        out.append('<div class="rail-track__list" data-track-list="' + t["id"] + '" data-open="false">')
        out.append(
            '<button class="rail-mod" type="button" data-go="#/t/' + t["id"] + '">Overview</button>'
        )
        for m in t["modules"]:
            mid = t["id"] + "/" + m["id"]
            out.append(
                '<button class="rail-mod" type="button" data-go="#/m/' + mid + '" '
                'data-rail-mid="' + mid + '">' + inline(m["name"]) + "</button>"
            )
        out.append("</div></div>")
    out.append("</div>")
    return "".join(out)


def build_index(tracks: list) -> list:
    idx = []
    for t in tracks:
        for m in t["modules"]:
            for i, c in enumerate(m["concepts"]):
                blob = " ".join(
                    [plain(c["t"]), plain(c["one"])]
                    + [plain(p) for p in _as_list(c.get("points"))]
                    + [plain(q["q"]) for q in _as_list(c.get("qa"))]
                )
                idx.append({
                    "i": "c-" + t["id"] + "-" + m["id"] + "-" + str(i),
                    "t": plain(c["t"]),
                    "p": plain(c["one"]),
                    "m": t["id"] + "/" + m["id"],
                    "c": plain(t["name"]) + " · " + plain(m["name"]),
                    "b": blob.lower(),
                })
    return idx


def build_nav(tracks: list) -> list:
    """Flat module order, for prev/next."""
    return [
        {"id": t["id"] + "/" + m["id"], "n": plain(m["name"]), "t": t["id"], "tn": plain(t["name"])}
        for t in tracks for m in t["modules"]
    ]


# ───────────────────────────────────────────────────────────────── template ──

PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>War Room &middot; Sachin Mishra</title>
<meta name="description" content="Interview revision guide: every concept behind the resume, with analogies, templates and the follow-up questions.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/war-room.css">
<script>
/* Theme before first paint: the portfolio shell writes localStorage.theme. */
(function(){try{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
</script>
</head>
<body>
<div class="app">

  <header class="topbar">
    <button class="btn btn--icon rail-toggle" type="button" id="railToggle" aria-label="Menu" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>
    <div class="brand" id="brandHome" role="button" tabindex="0">
      <span class="brand__mark">WR</span>
      <span class="brand__name">War Room</span>
    </div>
    <div class="topbar__spacer"></div>
    <div class="topbar__actions">
      <button class="search-trigger" type="button" id="searchOpen" aria-label="Search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <span class="st-label">Search</span><span class="kbd">/</span>
      </button>
      <button class="btn" type="button" id="drillBtn" title="Hide the answers, show only the questions">
        <span class="btn--label">Drill</span>
      </button>
      <button class="btn" type="button" id="sizeBtn" title="Larger text" aria-pressed="false">Aa</button>
    </div>
  </header>

  <div class="scrollbar" aria-hidden="true"><i id="scrollFill"></i></div>

  <div class="shell">
    <aside class="rail" id="rail" data-open="false" aria-label="Guide navigation">__RAIL__</aside>
    <div class="rail__scrim" id="railScrim" data-open="false"></div>
    <main class="main" id="main">__VIEWS__</main>
    <aside class="spine" id="spine" aria-label="On this page" hidden></aside>
  </div>

  <div class="foot">War Room &middot; <span>built from guide/data/*.json</span> &middot; progress saved in this browser</div>
</div>

<div class="search" id="search" data-open="false" role="dialog" aria-modal="true" aria-label="Search concepts">
  <div class="search__panel">
    <div class="search__bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input class="search__input" id="searchInput" type="text" placeholder="Search every concept, question and term&hellip;" autocomplete="off" spellcheck="false">
      <button class="btn btn--icon" type="button" id="searchClose" aria-label="Close">&times;</button>
    </div>
    <div class="search__results" id="searchResults"></div>
    <div class="search__hint"><span><span class="kbd">&uarr;</span><span class="kbd">&darr;</span> move</span><span><span class="kbd">&crarr;</span> open</span><span><span class="kbd">esc</span> close</span></div>
  </div>
</div>

<script>
(function () {
  'use strict';

  var IDX  = __IDX__;
  var NAV  = __NAV__;
  var KEY  = 'warroom:conf';

  var main       = document.getElementById('main');
  var rail       = document.getElementById('rail');
  var railScrim  = document.getElementById('railScrim');
  var railToggle = document.getElementById('railToggle');
  var spine      = document.getElementById('spine');
  var scrollFill = document.getElementById('scrollFill');
  var search     = document.getElementById('search');
  var sInput     = document.getElementById('searchInput');
  var sResults   = document.getElementById('searchResults');

  var views = Array.prototype.slice.call(main.querySelectorAll('.view'));

  /* Confidence is three-state, not a checkbox: 0 unrated, 1 shaky, 2 solid.
     Binary "done" lies to you the night before an interview - the whole point
     is to find the shaky ones fast. */
  var CONF_LABEL = ['Rate it', 'Shaky', 'Solid'];
  var conf = {};
  try { conf = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { conf = {}; }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(conf)); } catch (e) {}
  }
  function confOf(id) { return conf[id] || 0; }

  /* ---------------------------------------------------------- theme sync -- */
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme' && e.newValue) document.documentElement.setAttribute('data-theme', e.newValue);
  });

  /* -------------------------------------------------------------- routing -- */
  function show(view) {
    views.forEach(function (v) { v.classList.toggle('is-active', v === view); });
  }

  function route() {
    var h = location.hash || '#/';
    var view = null, mid = null, tid = null;

    if (h.indexOf('#/m/') === 0) {
      mid = h.slice(4);
      view = main.querySelector('.view[data-mid="' + CSS.escape(mid) + '"]');
      if (view) tid = mid.split('/')[0];
    } else if (h.indexOf('#/t/') === 0) {
      tid = h.slice(4);
      view = main.querySelector('.view[data-tid="' + CSS.escape(tid) + '"]');
    }
    if (!view) { view = main.querySelector('.view[data-view="home"]'); mid = null; tid = null; }

    show(view);
    if (mid) buildModNav(view, mid);
    syncRail(tid, mid);
    refreshProgress();
    buildSpine(mid ? view : null);
    applyFilter(mid ? view : null);
    closeRail();
    window.scrollTo({ top: 0, behavior: 'auto' });
    onScroll();
  }

  function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

  /* ------------------------------------------------------------- mod nav -- */
  function buildModNav(view, mid) {
    var nav = view.querySelector('[data-modnav]');
    if (!nav || nav.dataset.built === '1') return;
    var i = -1;
    for (var k = 0; k < NAV.length; k++) if (NAV[k].id === mid) { i = k; break; }
    var prev = i > 0 ? NAV[i - 1] : null;
    var next = i >= 0 && i < NAV.length - 1 ? NAV[i + 1] : null;
    nav.innerHTML =
      '<button type="button" class="prev"' + (prev ? ' data-go="#/m/' + prev.id + '"' : ' disabled') + '>' +
        '<div class="dir">&larr; Previous</div><div class="nm">' + (prev ? esc(prev.n) : '&middot;') + '</div></button>' +
      '<button type="button" class="next"' + (next ? ' data-go="#/m/' + next.id + '"' : ' disabled') + '>' +
        '<div class="dir">Next &rarr;</div><div class="nm">' + (next ? esc(next.n) : '&middot;') + '</div></button>';
    nav.dataset.built = '1';
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ---------------------------------------------------------------- rail -- */
  function syncRail(tid, mid) {
    rail.querySelectorAll('[data-rail-mid]').forEach(function (b) {
      b.setAttribute('aria-current', b.dataset.railMid === mid ? 'true' : 'false');
    });
    if (!tid) return;
    var btn  = rail.querySelector('[data-track-toggle="' + CSS.escape(tid) + '"]');
    var list = rail.querySelector('[data-track-list="' + CSS.escape(tid) + '"]');
    if (btn && list) { btn.setAttribute('aria-expanded', 'true'); list.dataset.open = 'true'; }
  }

  function openRail()  { rail.dataset.open = 'true';  railScrim.dataset.open = 'true';  railToggle.setAttribute('aria-expanded', 'true'); }
  function closeRail() { rail.dataset.open = 'false'; railScrim.dataset.open = 'false'; railToggle.setAttribute('aria-expanded', 'false'); }

  railToggle.addEventListener('click', function () {
    if (rail.dataset.open === 'true') closeRail(); else openRail();
  });
  railScrim.addEventListener('click', closeRail);

  rail.addEventListener('click', function (e) {
    var t = e.target.closest('[data-track-toggle]');
    if (!t) return;
    var list = rail.querySelector('[data-track-list="' + CSS.escape(t.dataset.trackToggle) + '"]');
    var open = list.dataset.open === 'true';
    list.dataset.open = open ? 'false' : 'true';
    t.setAttribute('aria-expanded', open ? 'false' : 'true');
  });

  /* --------------------------------------------------------------- spine -- */
  function buildSpine(view) {
    if (!view) { spine.hidden = true; spine.innerHTML = ''; return; }
    var cards = Array.prototype.slice.call(view.querySelectorAll('.cpt'));
    spine.hidden = false;
    spine.innerHTML =
      '<div class="spine__l">On this page</div><div class="spine__list">' +
      cards.map(function (c, i) {
        var t = c.querySelector('.cpt__title').textContent;
        return '<button class="spine__item" type="button" data-spine="' + c.id + '" ' +
          'data-conf="' + confOf(c.id) + '" aria-current="false">' +
          '<span class="spine__n">' + (i + 1 < 10 ? '0' : '') + (i + 1) + '</span>' +
          '<span class="spine__t">' + esc(t) + '</span></button>';
      }).join('') + '</div>';
    observeSpine(cards);
  }

  var spineObs = null;
  function observeSpine(cards) {
    if (spineObs) spineObs.disconnect();
    if (!('IntersectionObserver' in window) || !cards.length) return;
    spineObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        spine.querySelectorAll('[data-spine]').forEach(function (b) {
          b.setAttribute('aria-current', b.dataset.spine === en.target.id ? 'true' : 'false');
        });
      });
    }, { rootMargin: '-15% 0px -70% 0px' });
    cards.forEach(function (c) { spineObs.observe(c); });
  }

  spine.addEventListener('click', function (e) {
    var b = e.target.closest('[data-spine]');
    if (!b) return;
    var el = document.getElementById(b.dataset.spine);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  /* -------------------------------------------------------------- filter -- */
  var filterMode = 'all';
  function applyFilter(view) {
    if (!view) return;
    var shown = 0;
    view.querySelectorAll('.cpt').forEach(function (c) {
      var k = confOf(c.id);
      var ok = filterMode === 'all' || (filterMode === 'weak' && k < 2) || (filterMode === 'shaky' && k === 1);
      c.hidden = !ok;
      if (ok) shown++;
    });
    view.querySelectorAll('[data-filter]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.filter === filterMode ? 'true' : 'false');
    });
    var note = view.querySelector('[data-empty]');
    if (!note) {
      note = document.createElement('div');
      note.className = 'empty-note';
      note.setAttribute('data-empty', '');
      note.textContent = 'Nothing left in this filter. Switch back to All.';
      view.querySelector('.concepts').appendChild(note);
    }
    note.hidden = shown > 0;
  }

  /* ------------------------------------------------------------ progress -- */
  function refreshProgress() {
    var byMod = {}, byTrack = {}, solid = 0;
    document.querySelectorAll('.view[data-mid]').forEach(function (v) {
      var mid = v.dataset.mid, tid = mid.split('/')[0];
      var cards = v.querySelectorAll('.cpt');
      var done = 0;
      cards.forEach(function (c) {
        var k = confOf(c.id);
        c.dataset.conf = k;
        var lbl = c.querySelector('[data-conf-label]');
        if (lbl) lbl.textContent = CONF_LABEL[k];
        if (k === 2) done++;
      });
      solid += done;
      byMod[mid] = [done, cards.length];
      if (!byTrack[tid]) byTrack[tid] = [0, 0];
      byTrack[tid][0] += done; byTrack[tid][1] += cards.length;
    });

    function paint(key, pair) {
      var pct = pair[1] ? Math.round(pair[0] / pair[1] * 100) : 0;
      document.querySelectorAll('[data-bar="' + CSS.escape(key) + '"]').forEach(function (b) { b.style.width = pct + '%'; });
      document.querySelectorAll('[data-pct="' + CSS.escape(key) + '"]').forEach(function (p) { p.textContent = pct + '%'; });
    }
    Object.keys(byMod).forEach(function (k) { paint(k, byMod[k]); });
    Object.keys(byTrack).forEach(function (k) { paint(k, byTrack[k]); });

    var n = document.querySelector('[data-known-n]');
    if (n) n.textContent = solid;

    spine.querySelectorAll('[data-spine]').forEach(function (b) {
      b.dataset.conf = confOf(b.dataset.spine);
    });
  }

  /* ----------------------------------------------------- scroll progress -- */
  function onScroll() {
    var h = document.documentElement.scrollHeight - window.innerHeight;
    scrollFill.style.width = (h > 40 ? Math.min(100, window.scrollY / h * 100) : 0) + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);

  /* ------------------------------------------------------- card handlers -- */
  document.addEventListener('click', function (e) {
    var goEl = e.target.closest('[data-go]');
    if (goEl) { e.preventDefault(); go(goEl.dataset.go); return; }

    var qa = e.target.closest('[data-qa]');
    if (qa) {
      var box = qa.closest('.qa');
      var open = box.dataset.open === 'true';
      box.dataset.open = open ? 'false' : 'true';
      qa.setAttribute('aria-expanded', open ? 'false' : 'true');
      return;
    }

    var mk = e.target.closest('[data-conf-btn]');
    if (mk) {
      var card = mk.closest('.cpt');
      var next = (confOf(card.id) + 1) % 3;
      if (next === 0) delete conf[card.id]; else conf[card.id] = next;
      save(); refreshProgress();
      return;
    }

    var fl = e.target.closest('[data-filter]');
    if (fl) {
      filterMode = fl.dataset.filter;
      applyFilter(fl.closest('.view'));
      return;
    }

    var rv = e.target.closest('[data-reveal]');
    if (rv) {
      var c2 = rv.closest('.cpt');
      c2.dataset.revealed = c2.dataset.revealed === 'true' ? 'false' : 'true';
      return;
    }

    var cp = e.target.closest('[data-copy]');
    if (cp) {
      var pre = cp.closest('.code-wrap').querySelector('pre.code');
      var txt = pre.textContent;
      var done = function () { cp.textContent = 'copied'; setTimeout(function () { cp.textContent = 'copy'; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(done, function () {});
      } else {
        var ta = document.createElement('textarea');
        ta.value = txt; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (err) {}
        document.body.removeChild(ta);
      }
      return;
    }

    var ex = e.target.closest('[data-expand-all]');
    if (ex) {
      ex.closest('.view').querySelectorAll('.qa').forEach(function (q) {
        q.dataset.open = 'true';
        q.querySelector('[data-qa]').setAttribute('aria-expanded', 'true');
      });
      return;
    }

    var co = e.target.closest('[data-collapse-all]');
    if (co) {
      co.closest('.view').querySelectorAll('.qa').forEach(function (q) {
        q.dataset.open = 'false';
        q.querySelector('[data-qa]').setAttribute('aria-expanded', 'false');
      });
      return;
    }
  });

  document.getElementById('brandHome').addEventListener('click', function () { go('#/'); });

  /* ---------------------------------------------------------- drill / Aa -- */
  var drillBtn = document.getElementById('drillBtn');
  drillBtn.addEventListener('click', function () {
    var on = document.body.classList.toggle('drill');
    drillBtn.classList.toggle('is-on', on);
    if (on) {
      document.querySelectorAll('.cpt').forEach(function (c) { c.dataset.revealed = 'false'; });
      document.querySelectorAll('.qa').forEach(function (q) {
        q.dataset.open = 'false';
        q.querySelector('[data-qa]').setAttribute('aria-expanded', 'false');
      });
    }
  });

  var sizeBtn = document.getElementById('sizeBtn');
  try { if (localStorage.getItem('warroom:size') === 'lg') { document.body.classList.add('type-large'); sizeBtn.classList.add('is-on'); sizeBtn.setAttribute('aria-pressed', 'true'); } } catch (e) {}
  sizeBtn.addEventListener('click', function () {
    var on = document.body.classList.toggle('type-large');
    sizeBtn.classList.toggle('is-on', on);
    sizeBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    try { localStorage.setItem('warroom:size', on ? 'lg' : 'sm'); } catch (e) {}
  });

  /* ---------------------------------------------------------------- search */
  var sel = 0, hits = [];

  function openSearch() {
    search.dataset.open = 'true';
    sInput.value = ''; runSearch('');
    setTimeout(function () { sInput.focus(); }, 30);
  }
  function closeSearch() { search.dataset.open = 'false'; }

  function runSearch(q) {
    q = q.trim().toLowerCase();
    if (!q) {
      hits = [];
      sResults.innerHTML = '<div class="search__empty">Type a term: RAG, GIL, idempotent, HPA, quorum, KV cache&hellip;</div>';
      return;
    }
    var terms = q.split(/\\s+/);
    hits = IDX.filter(function (r) {
      for (var i = 0; i < terms.length; i++) if (r.b.indexOf(terms[i]) === -1) return false;
      return true;
    }).sort(function (a, b) {
      var at = a.t.toLowerCase(), bt = b.t.toLowerCase();
      var as = at.indexOf(q) === 0 ? 0 : at.indexOf(q) > -1 ? 1 : 2;
      var bs = bt.indexOf(q) === 0 ? 0 : bt.indexOf(q) > -1 ? 1 : 2;
      return as - bs || at.length - bt.length;
    }).slice(0, 60);

    if (!hits.length) {
      sResults.innerHTML = '<div class="search__empty">Nothing for &ldquo;' + esc(q) + '&rdquo;.</div>';
      return;
    }
    sel = 0;
    sResults.innerHTML = hits.map(function (r, i) {
      return '<button class="sr' + (i === 0 ? ' is-sel' : '') + '" type="button" data-hit="' + i + '">' +
        '<div class="sr__t">' + mark(r.t, terms) + '</div>' +
        '<div class="sr__p">' + esc(r.p) + '</div>' +
        '<div class="sr__c">' + esc(r.c) + '</div></button>';
    }).join('');
  }

  function mark(text, terms) {
    var out = esc(text);
    terms.forEach(function (t) {
      if (!t) return;
      var re = new RegExp('(' + t.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'ig');
      out = out.replace(re, '<mark>$1</mark>');
    });
    return out;
  }

  function openHit(i) {
    var r = hits[i];
    if (!r) return;
    closeSearch();
    go('#/m/' + r.m);
    setTimeout(function () {
      var el = document.getElementById(r.i);
      if (!el) return;
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.style.transition = 'box-shadow .4s';
      el.style.boxShadow = '0 0 0 2px var(--accent-line)';
      setTimeout(function () { el.style.boxShadow = ''; }, 1600);
    }, 60);
  }

  function moveSel(d) {
    if (!hits.length) return;
    sel = (sel + d + hits.length) % hits.length;
    var nodes = sResults.querySelectorAll('.sr');
    nodes.forEach(function (n, i) { n.classList.toggle('is-sel', i === sel); });
    if (nodes[sel]) nodes[sel].scrollIntoView({ block: 'nearest' });
  }

  document.getElementById('searchOpen').addEventListener('click', openSearch);
  document.getElementById('searchClose').addEventListener('click', closeSearch);
  search.addEventListener('click', function (e) { if (e.target === search) closeSearch(); });
  sInput.addEventListener('input', function () { runSearch(sInput.value); });
  sResults.addEventListener('click', function (e) {
    var b = e.target.closest('[data-hit]');
    if (b) openHit(parseInt(b.dataset.hit, 10));
  });

  window.addEventListener('keydown', function (e) {
    var open = search.dataset.open === 'true';
    if (open) {
      if (e.key === 'Escape') { e.preventDefault(); closeSearch(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); moveSel(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); moveSel(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); openHit(sel); }
      return;
    }
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    if (e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key === 'k')) { e.preventDefault(); openSearch(); }
    else if (e.key === 'Escape' && rail.dataset.open === 'true') closeRail();
  });

  window.addEventListener('hashchange', route);
  route();
})();
</script>
</body>
</html>
"""


# ────────────────────────────────────────────────────────────────────  main ──

def load_tracks() -> list:
    files = sorted(DATA.glob("*.json"))
    if not files:
        sys.exit("No data files in " + str(DATA))
    tracks = []
    for f in files:
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit("Bad JSON in " + f.name + ": " + str(e))
        for key in ("id", "name", "desc", "color", "modules"):
            if key not in t:
                sys.exit(f.name + " is missing '" + key + "'")
        tracks.append(t)
    return tracks


def validate(tracks: list) -> None:
    seen_t, seen_c = set(), set()
    for t in tracks:
        if t["id"] in seen_t:
            sys.exit("duplicate track id: " + t["id"])
        seen_t.add(t["id"])
        seen_m = set()
        for m in t["modules"]:
            if m["id"] in seen_m:
                sys.exit("duplicate module id in " + t["id"] + ": " + m["id"])
            seen_m.add(m["id"])
            if not m.get("concepts"):
                sys.exit("module has no concepts: " + t["id"] + "/" + m["id"])
            for c in m["concepts"]:
                for key in ("t", "one"):
                    if key not in c:
                        sys.exit("concept missing '" + key + "' in " + t["id"] + "/" + m["id"])
                if c.get("tier", "core") not in TIER_LABEL:
                    sys.exit("bad tier '" + c["tier"] + "' on " + c["t"])
                k = (t["id"], m["id"], c["t"])
                if k in seen_c:
                    sys.exit("duplicate concept: " + " / ".join(k))
                seen_c.add(k)


def main() -> None:
    tracks = load_tracks()
    validate(tracks)

    views = [render_home(tracks)]
    for t in tracks:
        views.append(render_track(t))
        for m in t["modules"]:
            views.append(render_module(t, m))

    page = (
        PAGE.replace("__RAIL__", render_rail(tracks))
            .replace("__VIEWS__", "".join(views))
            .replace("__IDX__", json.dumps(build_index(tracks), ensure_ascii=False, separators=(",", ":")))
            .replace("__NAV__", json.dumps(build_nav(tracks), ensure_ascii=False, separators=(",", ":")))
    )
    OUT.write_text(page, encoding="utf-8")

    n_con = sum(len(m["concepts"]) for t in tracks for m in t["modules"])
    n_qa = sum(len(_as_list(c.get("qa"))) for t in tracks for m in t["modules"] for c in m["concepts"])
    n_code = sum(len(_as_list(c.get("code"))) for t in tracks for m in t["modules"] for c in m["concepts"])
    print("war-room.html  " + f"{OUT.stat().st_size / 1024:.0f}" + " KB")
    print("  tracks   " + str(len(tracks)))
    print("  modules  " + str(sum(len(t["modules"]) for t in tracks)))
    print("  concepts " + str(n_con))
    print("  snippets " + str(n_code))
    print("  questions " + str(n_qa))


if __name__ == "__main__":
    main()
