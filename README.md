# LoftChart.com

A static reference archive of golf club specifications — loft, lie, length, offset,
bounce and swing weight — with a focus on discontinued and vintage models whose spec
sheets have disappeared from manufacturer websites.

Live at **https://loftchart.com** (GitHub Pages, served from `/docs`).

## How it works

Every club model is one YAML file under `data/<brand>/<model-slug>.yaml`.
`generate.py` reads those files plus `data/brands.yaml` and writes the complete
static site into `docs/`. There is no build step beyond running the script — no
Node, no framework, no CDN dependencies other than Google Fonts.

```
loftchart/
├── generate.py          # the whole site generator
├── make_assets.py       # rasterises favicon.svg -> ico/png + the OG card
├── SCHEMA.md            # the club-data schema, read this before adding models
├── data/
│   ├── brands.yaml      # brand metadata
│   └── <brand>/*.yaml   # one file per club model
├── static/              # copied verbatim into docs/
│   ├── css/style.css
│   ├── js/search.js
│   └── favicon.svg, favicon.ico, og-default.png, ...
└── docs/                # GENERATED — do not hand-edit
```

## Build

```bash
python3 -m venv .venv
.venv/bin/pip install pyyaml pillow cairosvg
.venv/bin/python generate.py          # writes docs/
.venv/bin/python make_assets.py       # only needed if favicon.svg changed
```

`docs/` is wiped and rebuilt on every run, so never edit anything in it by hand.

To preview locally:

```bash
python3 -m http.server 8231 -d docs
```

## Adding a model

1. Read `SCHEMA.md`.
2. Create `data/<brand-slug>/<model-slug>.yaml`. The `slug` field must match the
   filename, and `<brand-slug>` must exist in `data/brands.yaml`.
3. Run `generate.py`. It validates as it loads and prints warnings for missing
   sources, thin FAQs, slug mismatches and missing loft/lie/length values; it exits
   non-zero if a required field or the whole spec table is missing.

### Data rules

- **Never invent numbers.** Every model carries a `sources` list, and `confidence:
  medium|low` renders a visible note on the page telling readers the figures came
  from secondary sources.
- Omit an optional key (`offset`, `bounce`, `swing_weight`) rather than guessing —
  the table renders an em dash for missing values, and the column disappears
  entirely if no club in the set has it.
- Figures are the standard men's right-handed steel-shaft build unless the
  description says otherwise.

## What gets generated

| URL | Page |
| --- | --- |
| `/` | homepage with client-side search |
| `/brands/`, `/<brand>/` | brand index and per-brand model timeline by decade |
| `/<brand>/<model>/` | the spec chart — the page that matters |
| `/compare/<a>-vs-<b>/` | side-by-side comparison with differences highlighted |
| `/years/`, `/years/<year>/` | release-year hubs |
| `/category/`, `/category/<cat>/` | iron-category hubs with a 7-iron comparison table |
| `/about/`, `/privacy/`, `/404.html` | static pages |
| `/sitemap.xml`, `/robots.txt`, `/search-index.json`, `/site.webmanifest` | feeds |

Comparison pages are generated automatically wherever a model's `predecessor`,
`successor` or `related_models` resolves to another model on file of the same club
type. The "which should you choose?" copy is derived from the actual loft deltas,
not written by hand.

Structured data: `BreadcrumbList` everywhere, `Article` + `FAQPage` on model pages,
`ItemList` on hub pages, `WebSite` + `SearchAction` and `Organization` on the
homepage.

## Notes

- Google Analytics 4 is live (`GA_ID` in `generate.py`). Set `GA_ID = ""` to drop the
  gtag snippet and switch the privacy page back to its no-analytics wording.
- `CNAME` and `.nojekyll` are written into `docs/` by the generator, so they survive
  the rebuild.
- Contact address is `info@loftchart.com`.

## Disclaimer

LoftChart is an independent reference project, not affiliated with, endorsed by or
sponsored by any golf club manufacturer. Brand and model names are the trademarks of
their respective owners and are used for identification only.
