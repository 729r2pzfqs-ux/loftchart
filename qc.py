#!/usr/bin/env python3
"""Data quality check over every model file in data/.

generate.py already fails the build on the errors that would break a page
(missing required key, no specs, unknown brand). This goes further: it checks
the numbers themselves for plausibility — loft ranges, monotonic loft
progression, duplicate clubs — and reports the soft gaps (missing lie, missing
length) that generate.py tolerates.

    python qc.py            # report everything
    python qc.py --errors   # errors only, for a pre-commit gate

Exit status is 1 if any error was found, 0 otherwise (warnings never fail).
"""

import os
import re
import sys
from collections import Counter

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

# The five categories generate.py knows how to label and build a page for
# (CATEGORY_LABEL). A value outside this set silently loses its category page.
CATEGORIES = {"blade", "players", "players-distance",
              "game-improvement", "super-game-improvement"}

# Required at the top level of every model file. club_type and slug are not in
# the brief but are load-bearing in generate.py, so they are checked too.
REQUIRED = ("model", "brand", "brand_slug", "club_type", "slug",
            "year_introduced", "category", "description", "specs", "sources")

YEAR_MIN, YEAR_MAX = 1970, 2026
SEVEN_IRON_MIN, SEVEN_IRON_MAX = 26.0, 38.0
DESC_MIN_CHARS = 50


def seven_iron_loft(specs):
    for row in specs:
        if str(row.get("club", "")).upper() == "7":
            return row.get("loft")
    return None


def check(path, rel, brand_dir, errors, warnings):
    def err(msg):
        errors.append(f"{rel}: {msg}")

    def warn(msg):
        warnings.append(f"{rel}: {msg}")

    with open(path, encoding="utf-8") as f:
        m = yaml.safe_load(f)

    if not isinstance(m, dict):
        err("not a YAML mapping")
        return

    # (a) schema completeness
    for key in REQUIRED:
        if not m.get(key):
            err(f"missing required field {key!r}")

    # (f) slug consistency — both the brand slug against its directory and the
    # model slug against its filename, since generate.py builds the URL from
    # the pair and a mismatch silently moves the page.
    if m.get("brand_slug") and m["brand_slug"] != brand_dir:
        err(f"brand_slug {m['brand_slug']!r} != directory {brand_dir!r}")
    expected_slug = os.path.splitext(os.path.basename(path))[0]
    if m.get("slug") and m["slug"] != expected_slug:
        err(f"slug {m['slug']!r} != filename {expected_slug!r}")

    # (d) category
    cat = m.get("category")
    if cat and cat not in CATEGORIES:
        err(f"category {cat!r} not one of {sorted(CATEGORIES)}")

    # (e) year
    year = m.get("year_introduced")
    if year is not None:
        if not isinstance(year, int):
            err(f"year_introduced {year!r} is not an integer")
        elif not YEAR_MIN <= year <= YEAR_MAX:
            err(f"year_introduced {year} outside {YEAR_MIN}-{YEAR_MAX}")
    disc = m.get("year_discontinued")
    if isinstance(disc, int) and isinstance(year, int) and disc < year:
        err(f"year_discontinued {disc} precedes year_introduced {year}")

    # (h) description
    desc = (m.get("description") or "").strip()
    if desc and len(desc) < DESC_MIN_CHARS:
        warn(f"description is {len(desc)} chars (< {DESC_MIN_CHARS})")

    # (g) sources
    sources = m.get("sources") or []
    if sources and not all(str(s).strip() for s in sources):
        err("empty entry in sources")

    specs = m.get("specs") or []
    if not specs:
        return

    # (b) per-club fields
    names = []
    for i, row in enumerate(specs):
        if not isinstance(row, dict):
            err(f"specs[{i}] is not a mapping")
            continue
        club = str(row.get("club", "")).upper()
        if not club:
            err(f"specs[{i}] missing club name")
            continue
        names.append(club)
        if row.get("loft") is None:
            err(f"club {club} missing loft")
        for key in ("lie", "length"):
            if row.get(key) is None:
                warn(f"club {club} missing {key}")

    # (c) no duplicate club names
    for club, n in sorted(Counter(names).items()):
        if n > 1:
            err(f"duplicate club {club!r} appears {n} times")

    # (c) lofts increase from long iron to wedge. Checked in the order the file
    # lists them, not a re-sorted order: SCHEMA.md has specs authored long ->
    # short, so a pair out of sequence here is a transposed row in the source
    # rather than something the build can sort its way out of.
    rows = [r for r in specs if isinstance(r, dict) and r.get("loft") is not None]
    for prev, cur in zip(rows, rows[1:]):
        if cur["loft"] <= prev["loft"]:
            err(f"loft not increasing: {prev['club']} {prev['loft']}° "
                f"-> {cur['club']} {cur['loft']}°")

    # (c) 7-iron plausibility
    l7 = seven_iron_loft(specs)
    if l7 is None:
        # Sets sold by loft (Ben Hogan) and partial sets have no club "7".
        if any(re.fullmatch(r"\d", str(r.get("club", ""))) for r in specs
               if isinstance(r, dict)):
            warn("no 7-iron in a number-labelled set")
    elif not SEVEN_IRON_MIN <= l7 <= SEVEN_IRON_MAX:
        warn(f"7-iron loft {l7}° outside {SEVEN_IRON_MIN}-{SEVEN_IRON_MAX}°")


def main():
    errors, warnings = [], []
    count = 0
    for brand_dir in sorted(os.listdir(DATA)):
        d = os.path.join(DATA, brand_dir)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(d, fn)
            count += 1
            check(path, os.path.relpath(path, ROOT), brand_dir, errors, warnings)

    only_errors = "--errors" in sys.argv
    if errors:
        print(f"ERRORS ({len(errors)})")
        for e in errors:
            print("  -", e)
    if warnings and not only_errors:
        print(f"\nWARNINGS ({len(warnings)})")
        for w in warnings:
            print("  -", w)

    print(f"\n{count} models checked: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
