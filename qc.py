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
from datetime import datetime

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

# The five categories generate.py knows how to label and build a page for
# (CATEGORY_LABEL). A value outside this set silently loses its category page.
CATEGORIES = {"blade", "players", "players-distance",
              "game-improvement", "super-game-improvement"}

# Wedge models use their own enum (WEDGE_CATEGORY_LABEL in generate.py).
WEDGE_CATEGORIES = {"tour", "game-improvement", "specialty"}

WEDGE_LOFT_MIN, WEDGE_LOFT_MAX = 40.0, 66.0
WEDGE_BOUNCE_MIN, WEDGE_BOUNCE_MAX = 0.0, 20.0

# Wood models (driver, fairway wood, hybrid) share an enum
# (WOOD_CATEGORY_LABEL in generate.py) and the family/variants schema; only
# the plausible loft band differs per type.
DRIVER_CATEGORIES = {"flagship", "lightweight", "game-improvement"}

WOOD_LOFT_RANGE = {
    "driver": (6.0, 16.0),
    "fairway_wood": (12.0, 28.0),
    "hybrid": (14.0, 40.0),
}

# Required at the top level of every model file. club_type and slug are not in
# the brief but are load-bearing in generate.py, so they are checked too.
REQUIRED = ("model", "brand", "brand_slug", "club_type", "slug",
            "year_introduced", "category", "description", "specs", "sources")

# YEAR_MIN is 1969 because the Ping Karsten I (1969) is the oldest model on file.
# YEAR_MAX allows next year's models, which are typically announced in the fall.
YEAR_MIN, YEAR_MAX = 1969, datetime.now().year + 1
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

    is_wedge = m.get("club_type") == "wedges"
    # Drivers, fairway woods and hybrids share the family/variants schema.
    is_driver = m.get("club_type") in WOOD_LOFT_RANGE

    # (a) schema completeness
    for key in REQUIRED:
        if not m.get(key):
            err(f"missing required field {key!r}")
    if (is_wedge and not m.get("grinds")
            and any(isinstance(r, dict) and r.get("grind")
                    for r in (m.get("specs") or []))):
        err("spec rows carry grinds but the model declares no grinds catalogue")
    if is_driver and not m.get("variants"):
        err("wood model missing variants catalogue")

    # (f) slug consistency — both the brand slug against its directory and the
    # model slug against its filename, since generate.py builds the URL from
    # the pair and a mismatch silently moves the page.
    if m.get("brand_slug") and m["brand_slug"] != brand_dir:
        err(f"brand_slug {m['brand_slug']!r} != directory {brand_dir!r}")
    expected_slug = os.path.splitext(os.path.basename(path))[0]
    if m.get("slug") and m["slug"] != expected_slug:
        err(f"slug {m['slug']!r} != filename {expected_slug!r}")

    # (d) category — wedges and drivers use their own enums
    cat = m.get("category")
    if is_wedge:
        if cat and cat not in WEDGE_CATEGORIES:
            err(f"wedge category {cat!r} not one of {sorted(WEDGE_CATEGORIES)}")
    elif is_driver:
        if cat and cat not in DRIVER_CATEGORIES:
            err(f"wood category {cat!r} not one of {sorted(DRIVER_CATEGORIES)}")
    elif cat and cat not in CATEGORIES:
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

    if is_driver:
        # (b/c) wood rows: a head variant × stock loft matrix.
        loft_min, loft_max = WOOD_LOFT_RANGE[m["club_type"]]
        variant_names = [v.get("name") for v in (m.get("variants") or [])
                         if isinstance(v, dict)]
        combos = []
        for i, row in enumerate(specs):
            if not isinstance(row, dict):
                err(f"specs[{i}] is not a mapping")
                continue
            loft, variant = row.get("loft"), row.get("variant")
            if loft is None:
                err(f"specs[{i}] missing loft")
            elif not loft_min <= loft <= loft_max:
                warn(f"{m['club_type']} loft {loft}° outside "
                     f"{loft_min}-{loft_max}°")
            if not variant:
                err(f"specs[{i}] missing variant")
            elif variant not in variant_names:
                err(f"variant {variant!r} at {loft}° not in variants list")
            combos.append((variant, loft))
        # No duplicate variant/loft combination.
        for combo, n in sorted(Counter(combos).items(), key=lambda kv: str(kv[0])):
            if n > 1:
                err(f"duplicate combo {combo} appears {n} times")
        # Every declared variant should be sold at at least one loft.
        used = {v for v, _ in combos if v}
        for v in variant_names:
            if v and v not in used:
                warn(f"variant {v!r} declared but used by no spec row")
        # Hosel settings, when present, each need a label.
        for i, s in enumerate(((m.get("hosel") or {}).get("settings") or [])):
            if not isinstance(s, dict) or not s.get("setting"):
                err(f"hosel settings[{i}] missing 'setting' label")
        return

    if is_wedge:
        # (b/c) wedge rows: a loft × bounce × grind matrix rather than a set.
        grind_codes = {g.get("code") for g in (m.get("grinds") or [])}
        combos = []
        for i, row in enumerate(specs):
            if not isinstance(row, dict):
                err(f"specs[{i}] is not a mapping")
                continue
            loft, bounce = row.get("loft"), row.get("bounce")
            if loft is None:
                err(f"specs[{i}] missing loft")
            elif not WEDGE_LOFT_MIN <= loft <= WEDGE_LOFT_MAX:
                warn(f"loft {loft}° outside {WEDGE_LOFT_MIN}-{WEDGE_LOFT_MAX}°")
            if bounce is None:
                err(f"specs[{i}] ({loft}°) missing bounce")
            elif not WEDGE_BOUNCE_MIN <= bounce <= WEDGE_BOUNCE_MAX:
                warn(f"bounce {bounce}° at {loft}° outside "
                     f"{WEDGE_BOUNCE_MIN}-{WEDGE_BOUNCE_MAX}°")
            grind = row.get("grind")
            if grind and grind not in grind_codes:
                err(f"grind {grind!r} at {loft}° not in grinds list")
            combos.append((loft, bounce, grind))
        # No duplicate loft/bounce/grind combination.
        for combo, n in sorted(Counter(combos).items(), key=lambda kv: str(kv[0])):
            if n > 1:
                err(f"duplicate combo {combo} appears {n} times")
        # Every declared grind should be sold at at least one loft.
        used = {g for _, _, g in combos if g}
        for g in sorted(c for c in grind_codes if c):
            if g not in used:
                warn(f"grind {g!r} declared but used by no spec row")
        # Lofts non-decreasing in file order (authored strongest to weakest).
        lofts = [l for l, _, _ in combos if l is not None]
        for prev, cur in zip(lofts, lofts[1:]):
            if cur < prev:
                err(f"loft not non-decreasing: {prev}° -> {cur}°")
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
