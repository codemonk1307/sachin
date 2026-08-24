# War Room - content pipeline

`war-room.html` at the repo root is **generated**. Do not edit it by hand; your
changes will be overwritten on the next build.

```
guide/data/*.json   ->   guide/build.py   ->   war-room.html
                                               css/war-room.css  (hand-written)
```

## Rebuild

```bash
python guide/build.py
```

It prints a summary (tracks, modules, concepts, snippets, questions) and fails
loudly on malformed data - missing required keys, duplicate ids, a bad `tier`,
or a module with no concepts.

## Adding content

One JSON file per track, in `guide/data/`. Files load in **filename order**, and
that is the order tracks appear on the home page - hence the numeric prefixes
(`10-`, `20-`, …). To insert a track between two existing ones, use `35-`.

```jsonc
{
  "id": "ai",                    // unique, used in URLs: #/t/ai
  "name": "AI Systems",
  "desc": "one line, shown on the home tile",
  "color": "#B295F0",            // tile accent
  "modules": [
    {
      "id": "rag",               // unique within the track: #/m/ai/rag
      "name": "RAG",
      "desc": "one line under the module title",
      "bullet": "the exact résumé line this module defends",   // optional
      "concepts": [ /* ... */ ]
    }
  ]
}
```

### A concept

Only `t` and `one` are required. Every other field is optional and simply
does not render when absent, so a stub is two lines and a full card is one
pattern - the layout is identical either way.

```jsonc
{
  "t": "Chunking",                       // term (required)
  "tier": "core" | "deep" | "jargon",    // default "core"
  "resume": true,                        // adds the "On your résumé" chip
  "one": "one-breath definition",        // required
  "analogy": "real-life comparison",     // -> amber "Think of it as" box
  "points": ["mechanism bullet", "..."], // -> "How it actually works"
  "code": {                              // -> syntax-highlighted panel
    "lang": "python",                    // py java js ts sql bash yaml text
    "cap": "caption shown in the bar",
    "src": "def f():\n    ..."
  },
  "qa": [                                // -> blue "They will ask" accordions
    { "q": "the question", "a": ["para 1", "para 2"] }
  ],
  "trap": "the follow-up that kills people",   // -> red box
  "say": "the sentence to say out loud"        // -> green box
}
```

`code` also accepts an **array** of code objects if a concept needs two
snippets. `qa[].a` accepts a plain string instead of an array for a single
paragraph.

### Inline markup

Every prose string supports exactly two things, applied after HTML escaping:

- `` `code` `` → inline code chip
- `**bold**` → bold

Everything else is escaped, so `<`, `>` and `&` are safe to type literally.

## Syntax highlighting

Done at **build time** in Python (`highlight()` in `build.py`) - no client-side
library, nothing to fail at runtime, and it still reads correctly with
JavaScript disabled. It is a shallow regex tokenizer covering comments,
strings, numbers, keywords, types and call sites. Enough to make a template
readable; not a parser. Unknown languages fall back to `text` (escaped, no
colour) rather than erroring.

## Styling

All of it lives in `css/war-room.css`. Two rules that keep the page from
breaking, and which any new CSS must respect:

1. **Every colour is a token**, defined for both themes. Never hard-code a hex
   value in a component rule - add it to `:root` and to `[data-theme="light"]`.
2. **Every flex/grid child gets `min-width: 0`.** Without it a long unbroken
   token (a URL, an identifier) pushes its container wider than the viewport
   and the whole page scrolls sideways.

Anything that can be wide - code, tables - scrolls inside its own
`overflow-x: auto` box. The page body never scrolls horizontally.

## Theme

The guide reads `localStorage.theme`, which the portfolio shell writes. It is
applied before first paint by an inline script in `<head>`, so there is no
flash, and a `storage` listener picks up changes made in another tab.

## How it is linked from the portfolio

`index.html` has one `.lab` overlay reused by every lab. Triggers carry their
target:

```html
<a href="#war-room" data-lab-open="war-room.html"
   data-lab-title="War Room: interview revision guide">War Room</a>
```

`openLab(src, title)` only reloads the iframe when the source actually
changes, so switching back to a lab you were already reading keeps your place.

## Local preview

`.claude/launch.json` defines a `portfolio` server on port 8899:

```bash
python -m http.server 8899
```

Then open <http://localhost:8899/war-room.html>. Serving over HTTP (rather than
opening the file directly) matters because the stylesheet is a separate file.

## Progress storage

- `warroom:conf` - `{conceptId: 1|2}`, the three-state confidence rating
  (absent = unrated, 1 = shaky, 2 = solid)
- `warroom:size` - `"lg"` when the larger reading size is on

Concept ids are `c-<trackId>-<moduleId>-<index>`. **Reordering concepts within
a module shifts the ids and therefore loses those ratings.** Append rather than
insert if you care about keeping your progress.
