# LoftChart data schema

One YAML file per club model, at `data/<brand-slug>/<model-slug>.yaml`.

```yaml
brand: Ping                      # display name
brand_slug: ping
model: Eye 2                     # display name WITHOUT the club type suffix
slug: eye-2-irons                # matches filename
club_type: irons                 # irons | driver | fairway_wood | hybrid | wedges | putter
year_introduced: 1982            # int
year_discontinued: 1993          # int, or null if no end year is on file
current_as_of: "2026-09"         # OMIT unless confirmed current — see Rules
category: game-improvement       # blade | players | players-distance | game-improvement | super-game-improvement
construction: investment cast    # e.g. "investment cast", "forged", "cast/forged hybrid"
material: 17-4 stainless steel
successor: Ping ISI              # display string or null
predecessor: Ping Eye            # display string or null
description: >                   # 2-4 sentences, factual, no marketing fluff
  One of the most iconic iron sets ever made...
length_note: >                   # OMIT unless the length basis needs explaining
  Lengths use the USGA / R&A measuring method...
specs:                           # one entry per club, in set order (long -> short)
  - club: "3"                    # ALWAYS a quoted string: "3", "PW", "UW", "SW", "LW"
    loft: 21.0                   # float, degrees
    lie: 60.0                    # float, degrees
    length: 39.0                 # float, inches (steel shaft standard length)
    offset: 0.130                # float, inches — OMIT the key entirely if unknown
    bounce: 2.0                  # float, degrees — OMIT if unknown
    swing_weight: D1             # string — OMIT if unknown
stock_shafts:
  - name: "Ping ZZ Lite"
    material: steel              # steel | graphite
    weight: "light"              # OMIT if unknown
    flex: ["L", "A", "R", "S"]   # OMIT if unknown
sources:                         # REQUIRED, >=1. Be specific and honest.
  - "Ping 1990 product catalog via archive.org"
related_models:                  # OMIT if none
  - slug: "ping/isi-irons"
    label: "Successor: Ping ISI"
faq:                             # REQUIRED, >=2 entries
  - q: "What is the loft of a Ping Eye 2 7-iron?"
    a: "The Ping Eye 2 7-iron has a loft of 36 degrees."
confidence: high                 # high | medium | low — how well-verified the spec numbers are
```

## Rules

- **Do not invent numbers.** Use manufacturer catalogs, archived spec pages, GolfWorks
  /Golf Club Design spec databases, and well-corroborated forum/retailer listings.
  If a field can't be corroborated, omit that key rather than guessing.
- Set `confidence: medium` or `low` and say so in `sources` when the numbers come from
  secondary sources rather than a manufacturer spec sheet.
- `year_introduced` is the **announcement year** — the calendar year the maker first
  showed the model publicly, not the marketing model year printed on the packaging and
  not the year it reached shop floors. Several makers announce in the autumn of year N
  and market the result as the year N+1 line; Mizuno did this consistently through the
  MP era. Record the announcement year in those cases and note the model year in
  `description` if it is likely to confuse. `year_discontinued` is the year the
  successor was announced, on the same convention. Where announcement and retail fall
  in different calendar years — Mizuno's Pro line announced in Q4 and shipped the
  following Q1 — record which basis the year uses in `sources`, so the gap is visible
  rather than silently resolved one way or the other.
- A null `year_discontinued` does **not** mean the model is current. The site only
  calls a set current ("2024–present", "a current set in the range") when the file
  carries `current_as_of: "YYYY-MM"`, the month someone last confirmed it was still in
  the maker's own catalogue with no replacement announced. Without it the page reads
  "from 2024" and says the end date is not confirmed. Remove `current_as_of` when you
  record a `successor` or a `year_discontinued`; the build warns if both are present.
- Page dates are never the build date. A model page's "Last updated", `datePublished`,
  `dateModified` and sitemap `lastmod` come from the git history of its YAML file. The
  wedge and driver guides carry theirs as `*_PUBLISHED` / `*_REVIEWED` constants in
  `generate.py`; move a `*_REVIEWED` date only after re-checking the figures.
- Use `length_note` where a maker's published lengths are not comparable with its other
  charts, as with Mizuno's move to the USGA / R&A measuring method.
- Lofts/lies/lengths are the **standard steel-shaft men's** spec unless noted in `description`.
- Every model needs at least loft + lie + length for each club.
- Cover the real stock set composition for that model (e.g. 3-PW, 4-PW, 4-GW, plus U/SW/LW
  if they were part of the stock set).

## Wedge models (`club_type: wedges`)

A standalone wedge model is a **loft × bounce × grind option matrix**, not a set, at
`data/<brand-slug>/<model-slug>-wedges.yaml`. Differences from irons:

```yaml
club_type: wedges                # triggers the wedge code paths in generate.py
category: tour                   # tour | game-improvement | specialty
grinds:                          # REQUIRED — the model's grind catalogue
  - code: F                      # matches the `grind` values in specs
    name: F Grind
    description: >
      Full sole for full swings and square-face shots. (Use the maker's own
      description, condensed.)
specs:                           # one row PER COMBINATION SOLD, strongest loft first
  - loft: 46.0                   # REQUIRED, degrees
    bounce: 10.0                 # REQUIRED, degrees (effective bounce as published)
    grind: F                     # cross-referenced against `grinds`; omit only if
                                 # the model has no named grinds
    lie: 64.0                    # OPTIONAL — include when the maker publishes it
    length: 35.75                # OPTIONAL, inches
```

- `club` is not used — a wedge is identified by its degree.
- `lie`/`length` are optional per row because OEMs publish them per loft, when at all.
- Record the **base/widest finish variant's** matrix (e.g. Cleveland Tour Satin); note
  narrower finish variants in `description` rather than multiplying rows.
- Author rows grouped by loft, ascending; within a loft order by bounce then grind.
- Everything else (sources, faq, confidence, predecessor/successor, current_as_of,
  stock_shafts, related_models) works exactly as for irons.

## Driver models (`club_type: driver`)

A driver model is a **family of head variants**, one file per family (not per head), at
`data/<brand-slug>/<family-slug>-driver.yaml` — e.g. `qi35-driver.yaml` covers the Qi35,
Qi35 LS, Qi35 Max and Qi35 Max Lite. Differences from irons:

```yaml
club_type: driver                # triggers the driver code paths in generate.py
category: flagship               # flagship | lightweight | game-improvement
variants:                        # REQUIRED — the head catalogue, core head first
  - name: Qi35 Max               # matches the `variant` values in specs
    head_cc: 460                 # OPTIONAL, cc
    description: >
      Who the head is for and its weighting scheme, condensed from the maker.
specs:                           # one row PER VARIANT × STOCK LOFT
  - variant: Qi35 Max            # REQUIRED, cross-referenced against `variants`
    loft: 9.0                    # REQUIRED, degrees (the stamped stock loft)
    lie: 58.5                    # OPTIONAL — only when the maker publishes a figure
    length: 45.75                # OPTIONAL, inches
hosel:                           # OPTIONAL — omit entirely for a glued hosel
  system: "4° Loft Sleeve"       # the maker's name for the system
  loft_range: "±2°"
  positions: 12                  # OPTIONAL — omit if the count is unverified
  lie_effect: one line on what it does to lie
  face_note: one line on what it does to face angle
  notes: >
    Context the table cannot carry (sleeve compatibility, how the dials work,
    why no per-position chart exists). If the maker publishes no
    position-by-position chart, say so here and OMIT `settings` rather than
    reproducing a third-party reconstruction.
  settings:                      # the adjustment chart, one row per position
    - { setting: "STD LOFT", loft: "std", lie: "std", face: "square" }
    - { setting: "HIGHER", loft: "+2°", lie: "2° upright", face: "4° closed" }
```

- `club` is not used — rows are identified by variant + loft.
- `hosel.settings` values are display strings ("+0.75°", "std", "3° flat"), since
  systems differ too much for a numeric schema; `lie` and `face` are optional columns.
- TaylorMade-style makers publish lie only as an adjustable range — omit the `lie`
  key then and note the ranges in `sources`.
- Record men's right-handed stock lofts; note right-hand-only lofts in the variant
  description and women's/HL builds in one line, not as extra rows.
- Same-name generations get a year suffix in the model name ("Dynapwr (2023)").
- Everything else (sources, faq, confidence, predecessor/successor, current_as_of,
  stock_shafts, related_models, length_note) works exactly as for irons.
