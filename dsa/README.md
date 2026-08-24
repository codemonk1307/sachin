# DSA Mastery - content pipeline

`dsa-master.html` at the repo root is **generated**. Do not edit it by hand;
your changes are overwritten on the next build.

```
dsa/data/program.json   ->   dsa/build.py   ->   dsa-master.html
dsa/data/day-NN.json                             css/dsa-master.css  (hand-written)
```

## Rebuild

```bash
python dsa/build.py
```

It prints a summary and fails loudly on malformed data: a missing day, a
duplicate card id, a bad lane or difficulty, a day without exactly five cards,
or an em dash anywhere in the output.

## What the program is

A **30-day loop you run every month**, not a course you finish once.

- 30 days x 5 cards = **150 concepts**, each with a real LeetCode problem
- Day = `((day of month - 1) % 30) + 1`, so the page always opens on today
- 24 core days, 4 retrieval days (7, 14, 21, 28), 2 simulation days (29, 30)
- Same content every cycle. That repetition **is** the method

Each core day takes one card from each of five lanes, so every family is
touched every single day:

| lane | covers |
|------|--------|
| `arrays` | two pointers, windows, prefix sums, binary search, sorting, bits |
| `structures` | stack, queue, heap, trie, linked list, DSU, cache design |
| `trees` | DFS, BFS, BST, LCA, reconstruction, path accumulation |
| `dp` | linear, grid, knapsack, two-sequence, interval, state machine, bitmask |
| `graphs` | traversal, topological, shortest path, MST, backtracking |

## Adding or changing content

One JSON file per day, `dsa/data/day-01.json` through `day-30.json`. To change
day 12's DP problem, open `day-12.json` and edit the card with `"lane": "dp"`.

```jsonc
{
  "day": 1,
  "title": "Foundations",
  "kind": "core",          // core | retrieval | mock
  "focus": "one line under the day title",
  "cards": [ /* exactly 5 */ ]
}
```

### A card

```jsonc
{
  "id": "two-pointers",              // REQUIRED, stable, globally unique
  "lane": "arrays",                  // REQUIRED
  "title": "Two Pointers",           // REQUIRED
  "trigger": "when you reach for this",   // REQUIRED, always visible
  "recall":  "the prompt shown BEFORE the reveal",  // REQUIRED

  "patterns": ["Opposite ends", "Fast / slow"],     // optional, visible
  "useWhen":  ["...", "..."],                       // optional, visible
  "problem":  { "lc": 125, "name": "Valid Palindrome",
                "slug": "valid-palindrome", "diff": "easy" },

  "template": ["left, right = 0, n - 1", "while left < right:"],  // LOCKED
  "complexity": { "time": "O(n)", "space": "O(1)" },              // LOCKED
  "keyInsights": ["...", "..."],                                  // LOCKED
  "trap": "the follow-up that kills people",                      // LOCKED

  "timerSec": 240                    // optional, overrides the program default
}
```

Everything marked **LOCKED** is hidden behind the recall gate. That split is
the whole design: you commit before you see the answer, because recognition is
not recall.

`template` is an **array of lines**, joined with newlines at build time. Write
it as you would write the code, one array element per line, and never worry
about `\n` escaping.

### Retrieval and mock cards

Use `drill` instead of `problem` for a list of problems, each with an optional
`cue`:

```jsonc
{
  "id": "r1-arrays",
  "lane": "arrays",
  "kind": "drill",
  "title": "Arrays and Strings: blind recall",
  "trigger": "...",
  "recall": "...",
  "drill": [
    { "lc": 125, "name": "Valid Palindrome", "slug": "valid-palindrome",
      "diff": "easy", "cue": "opposite ends" }
  ],
  "template": ["# consolidated cheat sheet"],
  "keyInsights": ["..."]
}
```

A card needs **either** a `template` or a `drill` list; the build rejects a
card with neither.

### Inline markup

Every prose string supports exactly two things, applied after HTML escaping:

- `` `code` `` -> inline code chip
- `**bold**` -> bold

Everything else is escaped, so `<`, `>` and `&` are safe to type literally.

### The one rule about ids

Confidence ratings are keyed by `id`, and they persist across cycles. So:

- **Reordering cards is free.** Ids are strings, not positions.
- **Renaming an id wipes that concept's history.** Only do it deliberately.
- Ids must be unique across all 30 days. The build enforces it.

## Engagement mechanics

All of it lives in the runtime emitted by `build.py`, driven by
`program.json`:

| mechanic | where it is configured |
|----------|------------------------|
| XP per clean recall / peek | `program.json` -> `xp.clean`, `xp.peek` |
| Speed bonus | `xp.speedBonusSec`, `xp.speedBonus` |
| Combo multiplier and its cap | `xp.comboStep`, `xp.comboCap` |
| Perfect-day bonus | `xp.perfectDay` |
| Rank thresholds and names | `program.json` -> `ranks` |
| Default card timer | `program.json` -> `cardTimerSec` |

Nothing about the scoring is hardcoded in the JavaScript. Change the numbers in
`program.json` and rebuild.

## Progress storage

All in `localStorage`, this browser only:

- `dsa:v2:xp` - total XP, an integer
- `dsa:v2:conf` - `{cardId: {s: 1|2, n: cleanCount, t: 'YYYY-MM-DD'}}`
  where `s` is 1 for shaky and 2 for solid
- `dsa:v2:log` - `{'YYYY-MM-DD': {day, xp, clean, total}}`, drives the streak
  and the 13-week heatmap
- `dsa:v2:size` - `'lg'` when the larger reading size is on

The `v2` namespace is deliberate: the previous build used `dsa30_completed`,
and those keys are simply ignored rather than half-read.

## Styling

All of it lives in `css/dsa-master.css`. Two rules that keep the page from
breaking, and which any new CSS must respect:

1. **Every colour is a token**, defined for both themes. Never hard-code a hex
   value in a component rule; add it to `:root` and to `[data-theme="light"]`.
2. **Every flex/grid child gets `min-width: 0`.** Without it a long unbroken
   token pushes its container wider than the viewport and the whole page
   scrolls sideways.

Code blocks scroll inside their own `overflow-x: auto` box. The page body
never scrolls horizontally.

## Syntax highlighting

Done at **build time** in Python (`highlight()` in `build.py`). No client-side
library, nothing to fail at runtime. Every template in the program is Python,
so the tokeniser only covers Python: comments, strings, numbers, keywords,
builtins and call sites. Enough to make a template readable; not a parser.

## No em dashes

`build.py` refuses to write the page if an em dash, `&mdash;` or `&#8212;`
appears anywhere in the output. If a build fails on that, find it in the day
file you just edited.

## Theme

The page reads `localStorage.theme`, which the portfolio shell writes. It is
applied before first paint by an inline script in `<head>`, so there is no
flash, and a `storage` listener picks up changes made in the parent tab.

## How it is linked from the portfolio

`index.html` has one `.lab` overlay reused by every lab:

```html
<a href="#dsa-lab" data-lab-open="dsa-master.html"
   data-lab-title="DSA Mastery: 30-day revision loop">DSA Lab</a>
```

## Local preview

`.claude/launch.json` defines a `portfolio` server on port 8899:

```bash
python -m http.server 8899
```

Then open <http://localhost:8899/dsa-master.html>. Serving over HTTP rather
than opening the file directly matters, because the stylesheet is a separate
file.

## Keyboard

| key | does |
|-----|------|
| `Enter` (home) | start today's run |
| `Space` / `Enter` | I had it |
| `P` | show me |
| `←` `→` | previous / next card |
| `Esc` | back to the cycle view |
