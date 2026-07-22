# LoftChart data schema

One YAML file per club model, at `data/<brand-slug>/<model-slug>.yaml`.

```yaml
brand: Ping                      # display name
brand_slug: ping
model: Eye 2                     # display name WITHOUT the club type suffix
slug: eye-2-irons                # matches filename
club_type: irons                 # irons | driver | fairway_wood | hybrid | wedges | putter
year_introduced: 1982            # int
year_discontinued: 1993          # int, or null if current
category: game-improvement       # blade | players | players-distance | game-improvement | super-game-improvement
construction: investment cast    # e.g. "investment cast", "forged", "cast/forged hybrid"
material: 17-4 stainless steel
successor: Ping ISI              # display string or null
predecessor: Ping Eye            # display string or null
description: >                   # 2-4 sentences, factual, no marketing fluff
  One of the most iconic iron sets ever made...
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
- Lofts/lies/lengths are the **standard steel-shaft men's** spec unless noted in `description`.
- Every model needs at least loft + lie + length for each club.
- Cover the real stock set composition for that model (e.g. 3-PW, 4-PW, 4-GW, plus U/SW/LW
  if they were part of the stock set).
