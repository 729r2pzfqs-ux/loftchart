#!/usr/bin/env python3
"""
LoftChart.com static site generator.

Reads YAML club-spec files from data/ and writes a complete static site to docs/
(GitHub Pages serves from /docs). Run: python generate.py
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict, OrderedDict
from datetime import date
from urllib.parse import quote_plus

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATIC = os.path.join(ROOT, "static")
OUT = os.path.join(ROOT, "docs")

SITE = "https://loftchart.com"
SITE_NAME = "LoftChart"
# Set to a real "G-..." measurement ID to switch analytics on. Set it to "" to
# omit the snippet entirely rather than ship it dead: a bogus ID still costs
# every visitor a googletagmanager request and logs a console error, and
# collects nothing in return.
GA_ID = "G-0LYNSK0WVL"
GA_ENABLED = bool(GA_ID) and GA_ID != "G-XXXXXXXXXX"
ADSENSE_CLIENT = "ca-pub-5861928596436289"

# Affiliate programme IDs. Set an ID to enable tracked links for that
# partner; leave empty to use plain search links instead. eBay is the only
# affiliate partner — do not add retailer links without a signed programme.
EBAY_CAMPAIGN_ID = "5339221177"  # eBay Partner Network

# Consent mode regions that default to denied: the EU27 plus the rest of the
# EEA (IS/LI/NO), the UK and Switzerland. Google matches `region` on ISO 3166
# codes, so Greece is GR here - the Eurostat spelling EL would match nothing
# and silently drop Greek visitors onto the granted fallback. Everyone outside
# this list gets the granted default from the second call.
CONSENT_DENIED_REGIONS = [
    "BE", "BG", "CZ", "DK", "DE", "EE", "IE", "GR", "ES", "FR", "HR", "IT",
    "CY", "LV", "LT", "LU", "HU", "MT", "NL", "AT", "PL", "PT", "RO", "SI",
    "SK", "FI", "SE", "GB", "CH", "IS", "LI", "NO",
]
# Rendered compact - Python's list repr pads after every comma, which is 31
# wasted bytes on every page.
CONSENT_REGION_JS = "[" + ",".join(f"'{c}'" for c in CONSENT_DENIED_REGIONS) + "]"
EMAIL = "info@loftchart.com"
# Cloudflare's email obfuscation rewrites any literal mailto: it finds into a
# /cdn-cgi/l/email-protection URL that 404s for crawlers without JS, so every page
# got flagged as linking to a broken page. Entity encoding alone does not help -
# Cloudflare decodes entities before it scans - so every address also sits inside
# the documented <!--email_off--> opt-out markers. The entities stay as a second
# layer for any other scraper that does not decode them.
EMAIL_HTML = EMAIL.replace("@", "&#64;").replace(".", "&#46;")
EMAIL_OFF = "<!--email_off-->"
EMAIL_OFF_END = "<!--/email_off-->"


def email_link(text=None):
    """A mailto: anchor fenced off from Cloudflare's email obfuscator."""
    return (f'{EMAIL_OFF}<a href="mailto:{EMAIL_HTML}">'
            f'{EMAIL_HTML if text is None else text}</a>{EMAIL_OFF_END}')
TODAY = date.today().isoformat()

# Dates shown on a page and written to its schema and sitemap entry are the
# dates the content actually changed, never the date the site happened to be
# rebuilt. Model pages take theirs from the history of their data file (see
# git_dates); the hand-written guides carry theirs here, and *_REVIEWED moves
# only when someone has re-checked the figures against their sources.
WEDGE_PUBLISHED = "2026-08-27"
WEDGE_REVIEWED = "2026-09-29"
DRIVER_PUBLISHED = "2026-08-28"
DRIVER_REVIEWED = "2026-09-29"
# The iron, fairway wood and hybrid hubs, added when the nav moved to one
# landing page per club type. HUB_REVIEWED moves only when someone re-checks
# their figures, same contract as WEDGE_REVIEWED / DRIVER_REVIEWED above.
HUB_PUBLISHED = "2026-10-24"
HUB_REVIEWED = "2026-10-24"
# The cross-cutting knowledge guides (/guides/iron-number-equivalents/ and
# friends). Their tables are computed from data/ at build time, so the figures
# track the archive on their own; KNOWLEDGE_REVIEWED moves only when someone
# re-checks the prose claims and curated bands around those tables.
KNOWLEDGE_PUBLISHED = "2026-10-26"
KNOWLEDGE_REVIEWED = "2026-10-26"
PRIVACY_UPDATED = "2026-10-11"

# A model with no discontinuation year is only described as current when its
# file carries `current_as_of` — the month someone last confirmed it was still
# in the maker's catalogue. Anything else is reported as "end date not
# confirmed" rather than being passed off as a set that is still on the rack.
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def long_date(iso):
    """2026-09-29 -> 29 September 2026; 2026-09 -> September 2026."""
    parts = str(iso).split("-")
    month = MONTHS[int(parts[1]) - 1]
    if len(parts) == 2:
        return f"{month} {parts[0]}"
    return f"{int(parts[2])} {month} {parts[0]}"


def git_dates():
    """Map each data file to the (first, last) commit date that touched it.

    One `git log` pass over data/. A file with uncommitted changes, or one git
    has not seen yet, is dated today: the edit being built is the latest one.
    Outside a git checkout every file falls back to today.
    """
    dates = {}
    try:
        log = subprocess.run(
            ["git", "log", "--format=@%cs", "--name-only", "--", "data"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "data"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return dates
    day = None
    for line in log.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line.strip() and day:
            first, last = dates.get(line, (day, day))
            dates[line] = (min(first, day), max(last, day))
    for line in dirty.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        first, _ = dates.get(path, (TODAY, TODAY))
        dates[path] = (first, TODAY)
    return dates

CLUB_TYPE_LABEL = {
    "irons": "Irons",
    "driver": "Driver",
    "fairway_wood": "Fairway Woods",
    "hybrid": "Hybrids",
    "wedges": "Wedges",
    "putter": "Putter",
}

CATEGORY_LABEL = {
    "blade": "Blade / Muscleback",
    "players": "Players Irons",
    "players-distance": "Players Distance Irons",
    "game-improvement": "Game Improvement Irons",
    "super-game-improvement": "Super Game Improvement Irons",
}

# Reads naturally mid-sentence ("across 5 blade irons"), where the display
# label ("Blade / Muscleback") does not.
CATEGORY_SHORT = {
    "blade": "blade",
    "players": "players",
    "players-distance": "players distance",
    "game-improvement": "game improvement",
    "super-game-improvement": "super game improvement",
}

CATEGORY_BLURB = {
    "blade": "Compact muscleback irons with minimal offset, thin toplines and "
             "the smallest sweet spot — built for shot-shaping over forgiveness.",
    "players": "Small-to-mid cavity backs with traditional lofts, modest offset "
               "and workable shaping for low-handicap players.",
    "players-distance": "Forged or multi-material heads that keep a compact look "
                        "while adding face technology and stronger lofts for distance.",
    "game-improvement": "Perimeter-weighted cavity backs with wider soles, more "
                        "offset and stronger lofts, aimed at mid handicaps.",
    "super-game-improvement": "The most forgiving category — very wide soles, "
                              "maximum perimeter weighting and the strongest lofts.",
}

# Wedge models use their own category enum — the iron categories describe set
# design (blade vs cavity), which says nothing about a standalone wedge.
WEDGE_CATEGORY_LABEL = {
    "tour": "Tour / Players Wedges",
    "game-improvement": "Game Improvement Wedges",
    "specialty": "Specialty Wedges",
}

WEDGE_CATEGORY_SHORT = {
    "tour": "tour",
    "game-improvement": "game improvement",
    "specialty": "specialty",
}

# Driver models get their own enum too: a driver file is a whole family of head
# variants (the LS head in it is a players' club, the Max a forgiveness club),
# so the category describes the family's market position, not a head design.
DRIVER_CATEGORY_LABEL = {
    "flagship": "Flagship Driver Line",
    "lightweight": "Lightweight Driver",
    "game-improvement": "Game Improvement Driver",
}

DRIVER_CATEGORY_SHORT = {
    "flagship": "flagship",
    "lightweight": "lightweight",
    "game-improvement": "game improvement",
}

# Fairway woods and hybrids are families of head variants exactly like
# drivers — same variants/specs/hosel schema, same page layout — so they share
# the driver code paths. WOOD_TYPES is the switch; everything driver-specific
# in wording goes through WOOD_NOUN / WOOD_PLURAL instead of the literal.
WOOD_TYPES = ("driver", "fairway_wood", "hybrid")

WOOD_NOUN = {"driver": "driver", "fairway_wood": "fairway wood",
             "hybrid": "hybrid"}
WOOD_PLURAL = {"driver": "Drivers", "fairway_wood": "Fairway Woods",
               "hybrid": "Hybrids"}

# All three wood types share the driver category enum; only the display label
# changes so a fairway line does not read as a "Flagship Driver Line".
WOOD_CATEGORY_LABEL = {
    "driver": DRIVER_CATEGORY_LABEL,
    "fairway_wood": {
        "flagship": "Flagship Fairway Wood Line",
        "lightweight": "Lightweight Fairway Wood",
        "game-improvement": "Game Improvement Fairway Wood",
    },
    "hybrid": {
        "flagship": "Flagship Hybrid Line",
        "lightweight": "Lightweight Hybrid",
        "game-improvement": "Game Improvement Hybrid",
    },
}


# Order and heading for the per-club-type sections on year and category hubs.
CLUB_SECTION_ORDER = ("irons", "wedges", "driver", "fairway_wood", "hybrid")
CLUB_SECTION_LABEL = {"irons": "Irons", "wedges": "Wedges", **WOOD_PLURAL}

# /category/ hubs are keyed on the raw category slug, and the iron, wedge and
# wood enums overlap ("game-improvement" exists in all three), so one hub can
# hold several club types. These page-level labels, nouns and blurbs describe
# the hub as a whole; the per-type enums above still label each section.
CATEGORY_PAGE_LABEL = {
    "blade": CATEGORY_LABEL["blade"],
    "players": CATEGORY_LABEL["players"],
    "players-distance": CATEGORY_LABEL["players-distance"],
    "game-improvement": "Game Improvement Clubs",
    "super-game-improvement": CATEGORY_LABEL["super-game-improvement"],
    "tour": WEDGE_CATEGORY_LABEL["tour"],
    "specialty": WEDGE_CATEGORY_LABEL["specialty"],
    "flagship": "Flagship Lines",
    "lightweight": "Lightweight Clubs",
}

# Mid-sentence plural noun for the hub, doubling as the shop search query.
CATEGORY_PAGE_NOUN = {
    "blade": "blade irons",
    "players": "players irons",
    "players-distance": "players distance irons",
    "game-improvement": "game improvement clubs",
    "super-game-improvement": "super game improvement irons",
    "tour": "tour wedges",
    "specialty": "specialty wedges",
    "flagship": "flagship drivers",
    "lightweight": "lightweight drivers",
}

CATEGORY_PAGE_BLURB = {
    **CATEGORY_BLURB,
    "game-improvement": "Forgiveness-first designs across irons, wedges, "
                        "drivers and woods — perimeter weighting, wider soles "
                        "and higher launch, aimed at mid and high handicaps.",
    "tour": "Compact wedge heads with multiple sole grinds and tight loft "
            "gapping — the short-game profile most OEMs put in play on tour.",
    "specialty": "Wedges built around a specific short-game fix — extra-wide "
                 "soles, full-face grooves and very high lofts.",
    "flagship": "Each brand's headline driver, fairway wood and hybrid "
                "families — several head variants per line, led by the newest "
                "face technology.",
    "lightweight": "Reduced-weight heads and builds that help moderate swing "
                   "speeds launch the ball higher with more speed.",
}


def is_wood(m):
    return m.get("club_type") in WOOD_TYPES


def category_label(m):
    """Display label for a model's category, keyed on its club type."""
    cat = m.get("category")
    if m.get("club_type") == "wedges":
        return WEDGE_CATEGORY_LABEL.get(cat, cat or "—")
    if is_wood(m):
        return WOOD_CATEGORY_LABEL[m["club_type"]].get(cat, cat or "—")
    return CATEGORY_LABEL.get(cat, cat or "—")


# Ordering used for club rows within a set.
CLUB_ORDER = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
              "PW", "P", "UW", "GW", "AW", "A", "SW", "S", "LW", "L"]

# Vintage/discontinued models with the highest search demand — surfaced on the homepage.
FEATURED = [
    "ping/eye-2-irons",
    "titleist/710-ap2-irons",
    "mizuno/mp-33-irons",
    "callaway/x-14-irons",
    "taylormade/burner-2-0-irons",
    "ping/i3-o-size-irons",
    "titleist/dci-990-irons",
    "mizuno/mp-32-irons",
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s), quote=True)


def num(v):
    """Render a spec number without a trailing .0, keeping real decimals."""
    if v is None:
        return None
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


# --------------------------------------------------------------------------
# meta descriptions
#
# Target 120-160 rendered characters, unique across the whole site, with the
# most-searched data point (7-iron loft, for iron sets) front-loaded.
# Every description flows through head(), which records it in DESC_REGISTRY;
# audit_descriptions() then fails the build on a duplicate or a length miss.
# --------------------------------------------------------------------------

DESC_MIN = 120
DESC_MAX = 160

# Google truncates the SERP title around 60 characters. Titles are assembled
# from a mandatory core plus optional tails ordered most- to least-valuable,
# and fit_title() drops tails from the right until the whole thing fits, so
# the brand suffix is what goes first and the keywords are what survive.
TITLE_MAX = 60


def fit_title(core, *tails):
    out = core
    for t in tails:
        if len(out) + len(t) > TITLE_MAX:
            break
        out += t
    return out

# path -> description, filled by head() for every page the build emits.
DESC_REGISTRY = {}


def comma_list(items):
    """'a' / 'a and b' / 'a, b, and c' — Oxford comma only where it belongs."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def plural(n, singular, plural_form=None):
    """'1 iron' / '4 irons' — a stray plural on a count of one reads as a bug."""
    if n == 1:
        return f"{n} {singular}"
    if plural_form is None:
        if singular.endswith("y") and singular[-2:-1] not in "aeiou":
            plural_form = singular[:-1] + "ies"
        elif singular.endswith(("s", "x", "z", "ch", "sh")):
            plural_form = singular + "es"
        else:
            plural_form = singular + "s"
    return f"{n} {plural_form}"


def loft_span(models, label="7-iron"):
    """'7-iron lofts 28.5°-36°', or the single value when they all match.

    Returns '' when no model in the group carries a 7-iron loft, so callers can
    fall back to a tail that does not promise a number we do not have.
    """
    lofts = [s7["loft"] for s7 in (seven_iron(m) for m in models)
             if s7 and s7.get("loft") is not None]
    if not lofts:
        return ""
    lo, hi = min(lofts), max(lofts)
    if lo == hi:
        return f"{label} loft {num(lo)}°"
    return f"{label} lofts {num(lo)}°–{num(hi)}°"


def fit_desc(head_part, tails):
    """Pick the richest tail that keeps the description inside the length band.

    `tails` runs longest/most-informative first. We take the first one that
    lands at or under DESC_MAX, so a page with more data advertises more of it
    and a page with a long model name degrades gracefully instead of truncating
    mid-word in the SERP.
    """
    cands = [head_part + t for t in tails]
    # First choice: richest tail that lands fully inside the band.
    for c in cands:
        if DESC_MIN <= len(c) <= DESC_MAX:
            return c
    # Otherwise the longest that at least does not overflow, so we lose
    # detail rather than get truncated mid-word in the SERP.
    under = [c for c in cands if len(c) <= DESC_MAX]
    if under:
        return max(under, key=len)
    return min(cands, key=len)


def club_sort_key(c):
    """Total order over club labels, used to break ties between equal lofts.

    Label order alone cannot order a set correctly: wedge naming is per-brand
    and does not follow one loft progression. Callaway sells AW 47 alongside
    GW 51, Cleveland puts DW 50 between PW and SW, Titleist's DCI sets label a
    single 50-52 degree wedge "W". Any fixed list of labels gets one of those
    backwards, so the sorts below lead with the loft and fall back to this only
    to keep the order total and the build reproducible.
    """
    c = str(c).upper()
    if c in CLUB_ORDER:
        return (float(CLUB_ORDER.index(c)), "")
    # Loft-numbered wedges ("45W", "50W", as used in the G430 set) sit after
    # the pitching wedge, ordered by their own loft.
    m = re.fullmatch(r"(\d{2})W", c)
    if m:
        return (CLUB_ORDER.index("PW") + int(m.group(1)) / 1000.0, "")
    # Sets sold by loft rather than club number (the Ben Hogan lines) label
    # every club with its loft; order them numerically after the named clubs.
    if re.fullmatch(r"\d{2}(\.\d+)?", c):
        return (float(len(CLUB_ORDER)) + float(c) / 1000.0, "")
    return (float(len(CLUB_ORDER)) + 1.0, c)


def ldjson(obj):
    # Escapes inside a <script> would survive into the parsed JSON as literal
    # text, so the address is written plainly and the whole block is fenced with
    # the email_off markers Cloudflare's obfuscator honours.
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    tag = '<script type="application/ld+json">' + payload + "</script>"
    return EMAIL_OFF + tag + EMAIL_OFF_END if EMAIL in payload else tag


def write(path, content):
    full = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load():
    with open(os.path.join(DATA, "brands.yaml"), encoding="utf-8") as f:
        brands = yaml.safe_load(f)["brands"]
    by_slug = {b["slug"]: b for b in brands}

    models = []
    errors = []
    file_dates = git_dates()
    for brand_dir in sorted(os.listdir(DATA)):
        d = os.path.join(DATA, brand_dir)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(d, fn)
            with open(path, encoding="utf-8") as f:
                m = yaml.safe_load(f)
            rel = os.path.relpath(path, ROOT)
            if not isinstance(m, dict):
                errors.append(f"{rel}: not a YAML mapping")
                continue

            m.setdefault("brand_slug", brand_dir)
            expected = os.path.splitext(fn)[0]
            if m.get("slug") != expected:
                errors.append(f"{rel}: slug {m.get('slug')!r} != filename {expected!r}")
                m["slug"] = expected
            if m["brand_slug"] not in by_slug:
                errors.append(f"{rel}: unknown brand_slug {m['brand_slug']!r}")
                continue

            for key in ("brand", "model", "club_type", "year_introduced", "category"):
                if not m.get(key):
                    errors.append(f"{rel}: missing required field {key!r}")
            specs = m.get("specs") or []
            if not specs:
                errors.append(f"{rel}: no specs rows")
            if m.get("club_type") == "wedges":
                # A wedge model is a loft × bounce × grind option matrix, not a
                # set: rows carry no club label, lie/length are optional (OEMs
                # publish them per loft, when at all), and every grind code must
                # resolve to the model's grind catalogue. Models with no named
                # grinds (Kirkland, Wilson) omit both sides.
                if not m.get("grinds") and any(r.get("grind") for r in specs):
                    errors.append(f"{rel}: spec rows carry grinds but the model "
                                  "declares no grinds catalogue")
                grind_codes = {g.get("code") for g in (m.get("grinds") or [])}
                for row in specs:
                    row["club"] = str(row.get("club", "")).upper()
                    for key in ("loft", "bounce"):
                        if row.get(key) is None:
                            errors.append(f"{rel}: wedge spec row missing {key}")
                    if row.get("grind") and row["grind"] not in grind_codes:
                        errors.append(f"{rel}: grind {row['grind']!r} not in "
                                      "grinds list")
                if m.get("category") and m["category"] not in WEDGE_CATEGORY_LABEL:
                    errors.append(f"{rel}: unknown wedge category "
                                  f"{m['category']!r}")
                specs.sort(key=lambda r: (r.get("loft") or 0,
                                          r.get("bounce") or 0,
                                          str(r.get("grind") or "")))
            elif m.get("club_type") in WOOD_TYPES:
                # A wood model (driver, fairway wood, hybrid) is a family of
                # head variants, each sold in a few stock lofts: rows carry a
                # variant name and a loft, lie/length are optional (OEMs
                # publish them per head, when at all), and every variant must
                # resolve to the family's variant catalogue. The
                # adjustable-hosel chart lives in `hosel`.
                if not m.get("variants"):
                    errors.append(f"{rel}: wood model missing variants "
                                  "catalogue")
                vorder = {v.get("name"): i
                          for i, v in enumerate(m.get("variants") or [])}
                for row in specs:
                    row["club"] = str(row.get("club", "")).upper()
                    if row.get("loft") is None:
                        errors.append(f"{rel}: driver spec row missing loft")
                    if not row.get("variant"):
                        errors.append(f"{rel}: driver spec row missing variant")
                    elif row["variant"] not in vorder:
                        errors.append(f"{rel}: variant {row['variant']!r} not "
                                      "in variants list")
                if m.get("category") and m["category"] not in DRIVER_CATEGORY_LABEL:
                    errors.append(f"{rel}: unknown driver category "
                                  f"{m['category']!r}")
                for s in ((m.get("hosel") or {}).get("settings") or []):
                    if not s.get("setting"):
                        errors.append(f"{rel}: hosel setting row missing "
                                      "'setting' label")
                # Variants stay in catalogue order (core head first), with
                # lofts ascending within each head.
                specs.sort(key=lambda r: (vorder.get(r.get("variant"), len(vorder)),
                                          r.get("loft") or 0))
            else:
                for row in specs:
                    row["club"] = str(row.get("club", "")).upper()
                    for key in ("loft", "lie", "length"):
                        if row.get(key) is None:
                            errors.append(f"{rel}: club {row['club']} missing {key}")
                specs.sort(key=lambda r: (r["loft"] if r.get("loft") is not None
                                          else float("inf"), club_sort_key(r["club"])))
            if not m.get("sources"):
                errors.append(f"{rel}: no sources listed")
            if len(m.get("faq") or []) < 2:
                errors.append(f"{rel}: fewer than 2 FAQ entries")

            m["specs"] = specs
            m["key"] = f"{m['brand_slug']}/{m['slug']}"
            m["url"] = f"/{m['brand_slug']}/{m['slug']}/"
            m["brand_meta"] = by_slug[m["brand_slug"]]
            m["type_label"] = CLUB_TYPE_LABEL.get(m.get("club_type"), "Clubs")
            m["title"] = f"{m['brand']} {m['model']} {m['type_label']}"
            m["published"], m["modified"] = file_dates.get(
                rel.replace(os.sep, "/"), (TODAY, TODAY))
            if m.get("current_as_of") and (m.get("year_discontinued")
                                           or m.get("successor")):
                errors.append(f"{rel}: current_as_of set on a model with a "
                              "successor or discontinuation year")
            models.append(m)

    return brands, models, errors


def seven_iron(m):
    # A wedge or wood model has no set order and no reference club, so every
    # caller that summarises a set by its 7-iron (cards, loft spans, brand rows)
    # skips them rather than quoting a meaningless middle row.
    if m.get("club_type") == "wedges" or is_wood(m):
        return None
    for row in m["specs"]:
        if row["club"] == "7":
            return row
    mid = m["specs"][len(m["specs"]) // 2] if m["specs"] else None
    return mid


def wedge_reference_loft(m):
    """The representative row for a wedge model — 56° preferred, else middle loft."""
    for row in m["specs"]:
        if row.get("loft") == 56.0:
            return row
    if m["specs"]:
        return m["specs"][len(m["specs"]) // 2]
    return None


def wedge_lofts(m):
    """Sorted unique lofts a wedge model is sold in."""
    return sorted({r["loft"] for r in m["specs"] if r.get("loft") is not None})


def driver_lofts(m):
    """Sorted unique stock lofts across every head variant of a driver family."""
    return sorted({r["loft"] for r in m["specs"] if r.get("loft") is not None})


def variant_short(m, name):
    """Compact head label: the variant name minus the family name it repeats.

    'Qi35 Max Lite' on the Qi35 page reads as 'Max Lite'; the core head that
    carries the bare family name reads as 'Std'. Numbered heads like the
    Titleist GT2 keep their full name — stripping 'GT' would leave a bare digit.
    """
    name = str(name)
    if name == m["model"]:
        return "Std"
    return re.sub(r"^" + re.escape(m["model"]) + r"\s+", "", name).strip() or name


def driver_rows_by_variant(m):
    """Spec rows grouped by head variant, in catalogue order."""
    by = OrderedDict((v.get("name"), []) for v in (m.get("variants") or []))
    for r in m["specs"]:
        by.setdefault(r.get("variant"), []).append(r)
    return by


def is_current(m):
    """True only for a set confirmed to be in the maker's catalogue."""
    return bool(m.get("current_as_of")) and not (
        m.get("year_discontinued") or m.get("successor"))


def year_range(m):
    a = m.get("year_introduced")
    b = m.get("year_discontinued")
    if a and b:
        return f"{a}–{b}"
    if a:
        # "present" is a claim, and it is only made for a set someone has
        # confirmed is still catalogued. A superseded model, or one whose end
        # date simply is not on file, gets the open-ended "from" instead.
        return f"{a}–present" if is_current(m) else f"from {a}"
    return "Year unknown"


# --------------------------------------------------------------------------
# chrome
# --------------------------------------------------------------------------

def head(title, desc, path, ld=None, og_type="website", noindex=False,
         googlebot_noindex=False):
    canon = SITE + path
    # Record the rendered (unescaped) description; noindex pages are tracked
    # but exempted from the audit since they never surface in search.
    DESC_REGISTRY[path] = {"desc": desc, "title": title, "noindex": noindex}
    ldblocks = "".join(ldjson(o) for o in (ld or []))
    # Consent mode: deny every signal for EEA/UK/CH visitors until the CMP
    # grants it, and grant by default everywhere else. This has to be the first
    # tag in the head - AdSense delivers the consent UI at runtime via
    # adsbygoogle.js, so both that script and gtag must already see a default on
    # the dataLayer, and once a tag has fired without one the hit has already
    # gone out. The dataLayer/gtag stub is therefore defined here rather than
    # alongside the config call below. wait_for_update holds the tags for 500ms
    # so the CMP's update lands before the first hit; it only applies to the
    # regional call, since the fallback is already granted and has nothing to
    # wait for. The regional call is emitted first so the narrower rule is on
    # the dataLayer before the catch-all.
    consent = (
        "<script>window.dataLayer=window.dataLayer||[];"
        "function gtag(){dataLayer.push(arguments);}"
        "gtag('consent','default',{'analytics_storage':'denied',"
        "'ad_storage':'denied','ad_user_data':'denied',"
        "'ad_personalization':'denied','wait_for_update':500,"
        f"'region':{CONSENT_REGION_JS}}});"
        "gtag('consent','default',{'analytics_storage':'granted',"
        "'ad_storage':'granted','ad_user_data':'granted',"
        "'ad_personalization':'granted'});</script>"
    ) if GA_ENABLED else ""
    analytics = (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        f"<script>gtag('js',new Date());gtag('config','{GA_ID}');</script>"
    ) if GA_ENABLED else ""
    adsense = (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
        f'?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>'
    ) if ADSENSE_CLIENT else ""
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    # Googlebot-only noindex keeps a page out of Google while leaving it
    # crawlable, linkable and indexable by other engines.
    if googlebot_noindex and not noindex:
        robots = '<meta name="googlebot" content="noindex">'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:image" content="{SITE}/og-default.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#1B4332">
<meta name="impact-site-verification" value="13634fd5-12af-4ed3-b703-3be8dd0b4fad">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/css/style.css?v=7">
{ldblocks}
{consent}
{adsense}
{analytics}
<script src="https://analytics.ahrefs.com/analytics.js" data-key="Q1ltvzQDnlsCUSrZfvGd0g" async></script>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/">
      <svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="12" fill="#FAFAF7" opacity=".08"/><path d="M25 24 L28 9" stroke="#FAFAF7" stroke-width="7" stroke-linecap="round" fill="none"/><path d="M21 44 L46 45 L50 30 L23 22 Z" fill="#FAFAF7" stroke="#FAFAF7" stroke-width="4.5" stroke-linejoin="round"/><g stroke="#1B4332" stroke-width="2.4" stroke-linecap="round"><path d="M25 30.5 H45"/><path d="M24 35.5 H45.5"/><path d="M23.5 40.5 H46"/></g></svg>
      <span>Loft<span class="dot">Chart</span></span>
    </a>
    <button class="nav-toggle" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="site-nav">
      <span class="nav-toggle-bar"></span><span class="nav-toggle-bar"></span><span class="nav-toggle-bar"></span>
    </button>
    <nav class="site-nav" id="site-nav">
      <a href="/iron-lofts/">Irons</a>
      <a href="/wedge-lofts/">Wedges</a>
      <a href="/driver-lofts/">Drivers</a>
      <a href="/fairway-wood-lofts/">Fairways</a>
      <a href="/hybrid-lofts/">Hybrids</a>
      <div class="nav-more">
        <button class="nav-more-btn" type="button" aria-haspopup="true" aria-expanded="false">More</button>
        <div class="nav-more-menu">
          <a href="/brands/">Brands</a>
          <a href="/compare/">Compare</a>
          <a href="/years/">Years</a>
          <a href="/about/">About</a>
        </div>
      </div>
    </nav>
  </div>
</header>
<main id="main-content" tabindex="-1">
"""


def foot(brands):
    blinks = "".join(f'<li><a href="/{b["slug"]}/">{esc(b["name"])}</a></li>' for b in brands[:7])
    return f"""</main>
<footer class="site-footer">
  <div class="wrap">
    <div class="footer-cols">
      <div>
        <h3>Brands</h3>
        <ul>{blinks}<li><a href="/brands/">All brands →</a></li></ul>
      </div>
      <div>
        <h3>Browse</h3>
        <ul>
          <li><a href="/years/">By year</a></li>
          <li><a href="/category/">By category</a></li>
          <li><a href="/iron-lofts/">Iron loft chart</a></li>
          <li><a href="/wedge-lofts/">Wedge loft chart</a></li>
          <li><a href="/driver-lofts/">Driver loft chart</a></li>
          <li><a href="/fairway-wood-lofts/">Fairway wood loft chart</a></li>
          <li><a href="/hybrid-lofts/">Hybrid loft chart</a></li>
          <li><a href="/compare/">Comparisons</a></li>
        </ul>
      </div>
      <div>
        <h3>Site</h3>
        <ul>
          <li><a href="/about/">About</a></li>
          <li><a href="/privacy/">Privacy</a></li>
          <li><a href="/sitemap.xml">Sitemap</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-legal">
      <p>LoftChart is an independent reference project. Specifications are compiled from
      manufacturer catalogues, archived product pages and published spec databases, and are
      provided for reference only. Brand and model names are the trademarks of their
      respective owners; LoftChart is not affiliated with, endorsed by or sponsored by any
      golf club manufacturer.</p>
      <p>© {date.today().year} LoftChart.com · {email_link()}</p>
    </div>
  </div>
</footer>
<script src="/js/search.js?v=2" defer></script>
</body>
</html>
"""


def page(path, title, desc, body, brands, ld=None, og_type="website", noindex=False,
         googlebot_noindex=False):
    write(os.path.join(path.strip("/"), "index.html") if path != "/" else "index.html",
          head(title, desc, path, ld, og_type, noindex,
               googlebot_noindex) + body + foot(brands))


def crumbs(items):
    """items: list of (label, url|None). Returns (html, BreadcrumbList schema)."""
    lis = []
    elements = []
    for i, (label, url) in enumerate(items, 1):
        if url:
            lis.append(f'<li><a href="{esc(url)}">{esc(label)}</a></li>')
        else:
            lis.append(f'<li><span aria-current="page">{esc(label)}</span></li>')
        el = {"@type": "ListItem", "position": i, "name": label}
        if url:
            el["item"] = SITE + url
        elements.append(el)
    nav = ('<nav class="breadcrumbs" aria-label="Breadcrumb"><div class="wrap"><ol>'
           + "".join(lis) + "</ol></div></nav>")
    schema = {"@context": "https://schema.org", "@type": "BreadcrumbList",
              "itemListElement": elements}
    return nav, schema


def item_list(models, name):
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "numberOfItems": len(models),
        "itemListElement": [
            {"@type": "ListItem", "position": i, "url": SITE + m["url"], "name": m["title"]}
            for i, m in enumerate(models, 1)
        ],
    }


def club_noun(m, club):
    """'7' + irons -> '7-iron'; falls back to the bare club label for woods/wedges."""
    if m.get("club_type") == "irons" and str(club).isdigit():
        return f"{club}-iron"
    return str(club)


def model_card(m):
    if is_wood(m):
        lofts = driver_lofts(m)
        n_var = len(m.get("variants") or [])
        spec = (f'<span class="card-spec">{num(lofts[0])}°–{num(lofts[-1])}° · '
                f'{plural(n_var, "head variant")}</span>'
                if lofts else "")
        return (f'<a class="card" href="{m["url"]}">'
                f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
                f'<span class="card-meta">{esc(m["type_label"])} · {year_range(m)}</span>'
                f"{spec}</a>")
    if m.get("club_type") == "wedges":
        lofts = wedge_lofts(m)
        spec = (f'<span class="card-spec">{num(lofts[0])}°–{num(lofts[-1])}° · '
                f'{plural(len(m["specs"]), "loft/bounce/grind option")}</span>'
                if lofts else "")
        return (f'<a class="card" href="{m["url"]}">'
                f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
                f'<span class="card-meta">{esc(m["type_label"])} · {year_range(m)}</span>'
                f"{spec}</a>")
    s7 = seven_iron(m)
    spec = ""
    if s7:
        length_part = (f' · {num(s7["length"])}&Prime;'
                       if s7.get("length") is not None else "")
        lie_part = f' · {num(s7["lie"])}° lie' if s7.get("lie") is not None else ""
        spec = (f'<span class="card-spec">{esc(club_noun(m, s7["club"]))}: '
                f'{num(s7["loft"])}° loft{lie_part}{length_part}</span>')
    return (f'<a class="card" href="{m["url"]}">'
            f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
            f'<span class="card-meta">{esc(m["type_label"])} · {year_range(m)}</span>'
            f"{spec}</a>")


# --------------------------------------------------------------------------
# spec table
# --------------------------------------------------------------------------

OPTIONAL_COLS = [("offset", "Offset (in)"), ("bounce", "Bounce"), ("swing_weight", "Swing wt")]


def spec_table(m, caption=None):
    rows = m["specs"]
    cols = [("loft", "Loft (°)"), ("lie", "Lie (°)"), ("length", "Length (in)")]
    cols += [(k, l) for k, l in OPTIONAL_COLS if any(r.get(k) is not None for r in rows)]

    thead = "".join(f"<th scope=\"col\">{l}</th>" for _, l in cols)
    body = []
    for r in rows:
        cells = []
        for k, _ in cols:
            v = r.get(k)
            cells.append(f"<td>{esc(num(v))}</td>" if v is not None
                         else '<td class="na">—</td>')
        body.append(f'<tr><th scope="row">{esc(r["club"])}</th>{"".join(cells)}</tr>')

    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (f'<div class="table-scroll data-table-zone"><table class="specs">{cap}'
            f'<thead><tr><th scope="col">Club</th>{thead}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def wedge_spec_table(m, caption=None):
    """Loft × bounce × grind option table for a wedge model.

    One row per combination the maker actually sells, led by the loft, with the
    lie/length columns only when the model publishes them. Rows at a new loft
    get a class so the CSS can rule off each loft group.
    """
    rows = m["specs"]
    has_lie = any(r.get("lie") is not None for r in rows)
    has_length = any(r.get("length") is not None for r in rows)

    hdr = ('<th scope="col">Loft (°)</th><th scope="col">Bounce (°)</th>'
           '<th scope="col">Grind</th>')
    if has_lie:
        hdr += '<th scope="col">Lie (°)</th>'
    if has_length:
        hdr += '<th scope="col">Length (in)</th>'

    body = []
    prev_loft = None
    for r in rows:
        cls = ' class="loft-group"' if prev_loft is not None and r["loft"] != prev_loft else ""
        prev_loft = r["loft"]
        cells = (f'<th scope="row">{num(r["loft"])}°</th>'
                 f'<td>{num(r["bounce"])}°</td>'
                 f'<td>{esc(r["grind"]) if r.get("grind") else "—"}</td>')
        if has_lie:
            cells += (f'<td>{num(r["lie"])}</td>' if r.get("lie") is not None
                      else '<td class="na">—</td>')
        if has_length:
            cells += (f'<td>{num(r["length"])}</td>' if r.get("length") is not None
                      else '<td class="na">—</td>')
        body.append(f"<tr{cls}>{cells}</tr>")

    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (f'<div class="table-scroll data-table-zone"><table class="specs">{cap}'
            f'<thead><tr>{hdr}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def grind_guide(m):
    """The model's grind catalogue, with the lofts each grind is sold at."""
    grinds = m.get("grinds")
    if not grinds:
        return ""
    grind_lofts = defaultdict(set)
    for r in m["specs"]:
        if r.get("grind") and r.get("loft") is not None:
            grind_lofts[r["grind"]].add(r["loft"])
    items = []
    for g in grinds:
        lofts = sorted(grind_lofts.get(g.get("code"), []))
        loft_str = ", ".join(f"{num(l)}°" for l in lofts) if lofts else "—"
        name = g.get("name") or f"{g.get('code', '')} Grind"
        items.append(
            f'<div><dt><strong>{esc(name)}</strong>'
            f'<span class="grind-lofts">{loft_str}</span></dt>'
            f'<dd>{esc((g.get("description") or "").strip())}</dd></div>')
    return (f'<h2>Grind options</h2>'
            f'<p>The sole grinds this model is sold in, with the lofts each one '
            f'is available at.</p>'
            f'<dl class="grind-guide">{"".join(items)}</dl>')


def wedge_gapping_links(m):
    """Link the lofts a wedge model covers to the matching wedge-type guides.

    WEDGE_TYPES is defined further down with the guide pages; this only runs at
    build time, so the forward reference is fine.
    """
    lofts = set(wedge_lofts(m))
    links = []
    seen_bands = set()
    for w in WEDGE_TYPES:
        lo, hi = w["band"]
        # GW and AW share a band; one link is enough.
        if (lo, hi) in seen_bands:
            continue
        if any(lo <= l <= hi for l in lofts):
            seen_bands.add((lo, hi))
            links.append(f'<li><a href="/wedge-lofts/{w["slug"]}/">'
                         f'{esc(w["name"])} loft guide ({lo}°–{hi}°)</a></li>')
    if not links:
        return ""
    return ('<h2>Wedge loft guides</h2>'
            '<p>How each loft slot this model covers fits into a gapped bag:</p>'
            f'<ul class="linklist">{"".join(links)}</ul>')


def driver_spec_table(m, caption=None):
    """Stock-loft table for a driver family: one row per head variant.

    Lie, length and head size are shown only when the maker publishes them;
    where a value varies across the variant's lofts, the distinct values are
    joined rather than averaged.
    """
    by = driver_rows_by_variant(m)
    vmeta = {v.get("name"): v for v in (m.get("variants") or [])}

    def uniq(rows, key):
        vals = []
        for r in rows:
            v = r.get(key)
            if v is not None and v not in vals:
                vals.append(v)
        return vals

    has_lie = any(uniq(rows, "lie") for rows in by.values())
    has_length = any(uniq(rows, "length") for rows in by.values())
    has_cc = any(v.get("head_cc") for v in (m.get("variants") or []))

    hdr = '<th scope="col">Head</th><th scope="col">Stock lofts</th>'
    if has_cc:
        hdr += '<th scope="col">Head size</th>'
    if has_lie:
        hdr += '<th scope="col">Lie (°)</th>'
    if has_length:
        hdr += '<th scope="col">Length (in)</th>'

    body = []
    for name, rows in by.items():
        lofts = ", ".join(f"{num(r['loft'])}°" for r in rows
                          if r.get("loft") is not None)
        cells = (f'<th scope="row">{esc(name)}</th>'
                 f'<td>{lofts or "—"}</td>')
        if has_cc:
            cc = (vmeta.get(name) or {}).get("head_cc")
            cells += (f'<td>{num(cc)} cc</td>' if cc else '<td class="na">—</td>')
        if has_lie:
            lies = uniq(rows, "lie")
            cells += (f'<td>{" / ".join(num(v) for v in lies)}</td>' if lies
                      else '<td class="na">—</td>')
        if has_length:
            lengths = uniq(rows, "length")
            cells += (f'<td>{" / ".join(num(v) for v in lengths)}</td>'
                      if lengths else '<td class="na">—</td>')
        body.append(f"<tr>{cells}</tr>")

    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (f'<div class="table-scroll data-table-zone"><table class="specs">{cap}'
            f'<thead><tr>{hdr}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def variant_guide(m):
    """The family's head catalogue, with the stock lofts each head is sold in."""
    variants = m.get("variants")
    if not variants:
        return ""
    by = driver_rows_by_variant(m)
    items = []
    for v in variants:
        rows = by.get(v.get("name"), [])
        lofts = [r["loft"] for r in rows if r.get("loft") is not None]
        loft_str = ", ".join(f"{num(l)}°" for l in lofts) if lofts else "—"
        items.append(
            f'<div><dt><strong>{esc(v.get("name") or "—")}</strong>'
            f'<span class="grind-lofts">{loft_str}</span></dt>'
            f'<dd>{esc((v.get("description") or "").strip())}</dd></div>')
    return (f'<h2>Head variants</h2>'
            f'<p>The heads this family is sold in, with each one&rsquo;s stock '
            f'loft options.</p>'
            f'<dl class="grind-guide">{"".join(items)}</dl>')


def hosel_chart(m):
    """The adjustable-hosel settings chart — the page's highest-intent section.

    Rendered from the model's own `hosel` block so a TaylorMade sleeve chart, a
    Ping eight-setting chart and Cobra's 33-combination system all fit the same
    template. A driver with no hosel block gets an explicit non-adjustable note
    rather than silence, since "can you adjust it" is itself the question.
    """
    h = m.get("hosel")
    name = f"{esc(m['brand'])} {esc(m['model'])}"
    if not h:
        return (f'<h2>Hosel adjustment</h2>'
                f'<p>The {name} has a glued, non-adjustable hosel — the loft '
                f'printed on the head is the loft it plays. Loft and lie can '
                f'only be altered by a clubmaker, so pick the stock loft to '
                f'match your launch rather than planning to tune it later.</p>')

    bits = []
    if h.get("system"):
        bits.append(f"<strong>{esc(h['system'])}</strong>")
    if h.get("loft_range"):
        bits.append(f"loft {esc(h['loft_range'])}")
    if h.get("positions"):
        bits.append(f"{plural(h['positions'], 'setting')}")
    intro = " · ".join(bits)
    notes = []
    if h.get("lie_effect"):
        notes.append(esc(str(h["lie_effect"]).strip()))
    if h.get("face_note"):
        notes.append(esc(str(h["face_note"]).strip()))
    notes_html = f'<p>{" ".join(notes)}</p>' if notes else ""

    rows = h.get("settings") or []
    table = ""
    if rows:
        has_lie = any(r.get("lie") for r in rows)
        has_face = any(r.get("face") for r in rows)
        hdr = '<th scope="col">Setting</th><th scope="col">Loft</th>'
        if has_lie:
            hdr += '<th scope="col">Lie</th>'
        if has_face:
            hdr += '<th scope="col">Face angle</th>'
        body = []
        for r in rows:
            cells = (f'<th scope="row">{esc(r.get("setting"))}</th>'
                     f'<td>{esc(r.get("loft") or "std")}</td>')
            if has_lie:
                cells += (f'<td>{esc(r["lie"])}</td>' if r.get("lie")
                          else '<td class="na">std</td>')
            if has_face:
                cells += (f'<td>{esc(r["face"])}</td>' if r.get("face")
                          else '<td class="na">—</td>')
            body.append(f"<tr>{cells}</tr>")
        table = (f'<div class="table-scroll data-table-zone"><table class="specs">'
                 f'<caption>Hosel adjustment chart for the {name} — what each '
                 f'setting does to the stated loft.</caption>'
                 f'<thead><tr>{hdr}</tr></thead>'
                 f'<tbody>{"".join(body)}</tbody></table></div>')

    extra = (f'<p class="table-note">{esc(str(h["notes"]).strip())}</p>'
             if h.get("notes") else "")
    return (f'<h2>Hosel adjustment chart</h2>'
            f'<p>{intro}.</p>'
            f'{notes_html}'
            f'{table}'
            f'{extra}')


def driver_guide_links(m):
    """Link a driver model page back to the driver loft guide hub.

    The guides are driver-specific (swing-speed bands, 9° vs 10.5°), so
    fairway and hybrid pages get nothing rather than advice about a
    different club.
    """
    if m.get("club_type") != "driver":
        return ""
    lofts = driver_lofts(m)
    if not lofts:
        return ""
    return ('<h2>Driver loft guides</h2>'
            '<p>How to pick between these stock lofts:</p>'
            '<ul class="linklist">'
            '<li><a href="/driver-lofts/">Driver loft chart — the overview</a></li>'
            '<li><a href="/guides/driver-loft-by-swing-speed/">Driver loft by '
            'swing speed</a></li>'
            '<li><a href="/guides/9-vs-10-5-degree-driver/">9° vs 10.5° driver'
            '</a></li>'
            '<li><a href="/guides/10-5-vs-12-degree-driver/">10.5° vs 12° driver'
            '</a></li>'
            '</ul>')


# --------------------------------------------------------------------------
# diagrams
#
# Inline SVG, drawn from the same spec rows as the tables, so a chart can never
# disagree with the chart beside it. Colours are fixed hex values rather than
# CSS variables because SVG presentation attributes do not resolve var(), and
# the sizing that matters is inline so a page still lays out correctly against
# a cached copy of the stylesheet. No script: the hover text is each mark's
# own <title>.
# --------------------------------------------------------------------------

FIG_INK = "#1A1A1A"
FIG_MUTED = "#5A5A54"
FIG_GRID = "#E4E4DA"
FIG_AXIS = "#B9B9AC"
FIG_SURFACE = "#FFFFFF"
FIG_GREEN = "#2D6A4F"
# The comparison pair. The site green sits just under the chroma floor for a
# two-series palette, so series A uses a slightly more saturated step of it;
# checked against the gold for colour-blind separation and 3:1 contrast.
FIG_A = "#25805A"
FIG_B = "#A98C36"


def xy(v):
    """Coordinate with at most one decimal and no trailing zero."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def svg_open(width, height, title, desc, ident, max_px):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" '
            f'aria-labelledby="{ident}-t {ident}-d" '
            f'style="display:block;width:100%;max-width:{max_px}px;height:auto;margin:0 auto" '
            f'font-size="9" fill="{FIG_INK}">'
            f'<title id="{ident}-t">{esc(title)}</title>'
            f'<desc id="{ident}-d">{esc(desc)}</desc>')


def loft_rows(m):
    return [r for r in m["specs"] if r.get("loft") is not None]


def loft_chart(m):
    """Column chart of loft by club, with the gap to the next club beneath."""
    rows = loft_rows(m)
    if len(rows) < 2:
        return ""
    W, H = 320, 232
    left, right, top, base = 28, 4, 18, 180
    n = len(rows)
    slot = (W - left - right) / n
    bar = min(24, slot - 3)
    top_loft = max(r["loft"] for r in rows)
    ymax = max(10, int(-(-top_loft // 10)) * 10)
    scale = (base - top) / ymax
    small = n > 10
    size = 8 if small else 9

    out = [svg_open(
        W, H, f"{m['brand']} {m['model']} loft by club",
        "Column chart of loft in degrees for each club in the set: "
        + ", ".join(f"{r['club']} {num(r['loft'])}" for r in rows) + ".",
        "lp", 520)]
    for tick in range(0, ymax + 1, 10):
        y = base - tick * scale
        out.append(f'<line x1="{left}" x2="{W - right}" y1="{xy(y)}" y2="{xy(y)}" '
                   f'stroke="{FIG_AXIS if tick == 0 else FIG_GRID}"/>')
        out.append(f'<text x="{left - 5}" y="{xy(y + 3)}" text-anchor="end" '
                   f'fill="{FIG_MUTED}">{tick}°</text>')

    for i, r in enumerate(rows):
        cx = left + slot * (i + 0.5)
        h = r["loft"] * scale
        x0, y0 = cx - bar / 2, base - h
        rad = min(3, bar / 2, h)
        out.append(
            f'<path d="M{xy(x0)} {xy(base)}V{xy(y0 + rad)}Q{xy(x0)} {xy(y0)} '
            f'{xy(x0 + rad)} {xy(y0)}H{xy(x0 + bar - rad)}Q{xy(x0 + bar)} {xy(y0)} '
            f'{xy(x0 + bar)} {xy(y0 + rad)}V{xy(base)}Z" fill="{FIG_GREEN}">'
            f'<title>{esc(r["club"])}: {num(r["loft"])}°</title></path>')
        out.append(f'<text x="{xy(cx)}" y="{xy(y0 - 4)}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="600">{num(r["loft"])}'
                   f'{"" if small else "°"}</text>')
        out.append(f'<text x="{xy(cx)}" y="{base + 13}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="600">{esc(r["club"])}</text>')
        if i + 1 < n:
            gap = round(rows[i + 1]["loft"] - r["loft"], 1)
            out.append(f'<text x="{xy(cx + slot / 2)}" y="{base + 31}" '
                       f'text-anchor="middle" font-size="{size}" '
                       f'fill="{FIG_MUTED}">+{num(gap)}</text>')
    out.append(f'<text x="0" y="{base + 13}" font-size="8" fill="{FIG_MUTED}">Club</text>')
    out.append(f'<text x="0" y="{base + 31}" font-size="8" fill="{FIG_MUTED}">Gap</text>')
    out.append(f'<text x="0" y="8" font-size="8" fill="{FIG_MUTED}">Loft</text>')
    out.append("</svg>")

    gaps = [round(b["loft"] - a["loft"], 1) for a, b in zip(rows, rows[1:])]
    if min(gaps) == max(gaps):
        gap_txt = f"every gap is {num(gaps[0])}°"
    else:
        gap_txt = f"gaps run from {num(min(gaps))}° to {num(max(gaps))}°"
    caption = (f"Loft for each club, {esc(rows[0]['club'])} to {esc(rows[-1]['club'])}. "
               f"The Gap row is the loft added from one club to the next; {gap_txt}.")
    return (f'<figure class="fig data-table-zone">{"".join(out)}'
            f'<figcaption>{caption}</figcaption></figure>')


def loft_angle(m):
    """Side view of the face, tilted back from vertical by the set's own loft."""
    import math
    row = seven_iron(m)
    if not row or row.get("loft") is None:
        return ""
    loft = row["loft"]
    club = club_noun(m, row["club"])
    W, H = 200, 176
    px, py = 62, 150          # leading edge, on the ground
    face = 104
    rad = math.radians(loft)
    tx, ty = px + face * math.sin(rad), py - face * math.cos(rad)
    # the head behind the face: sole along the ground, back edge up to the topline
    sole = 30 + 34 * math.sin(rad)
    bx = px + sole
    arc = 46
    ax, ay = px + arc * math.sin(rad), py - arc * math.cos(rad)
    # topline and back of the head, so the wedge reads as a club rather than
    # a triangle: a short flat topline, then down to the trailing edge
    hx, hy = tx + 9 * math.cos(rad), ty + 9 * math.sin(rad)

    out = [svg_open(
        W, H, f"{m['brand']} {m['model']} {club} loft angle",
        f"Side view of the club face tilted {num(loft)} degrees back from vertical, "
        f"the loft of the {club}.", "la", 300)]
    out.append(f'<line x1="8" x2="{W - 8}" y1="{py}" y2="{py}" stroke="{FIG_AXIS}"/>')
    out.append(f'<path d="M{px} {py}L{xy(tx)} {xy(ty)}L{xy(hx)} {xy(hy)}'
               f'Q{xy(bx + 14)} {xy(py - 30)} {xy(bx + 8)} {py}Z" '
               f'fill="{FIG_GREEN}" fill-opacity=".14"/>')
    out.append(f'<line x1="{px}" x2="{px}" y1="{py}" y2="26" stroke="{FIG_MUTED}" '
               f'stroke-dasharray="3 3"/>')
    out.append(f'<path d="M{px} {py - arc}A{arc} {arc} 0 0 1 {xy(ax)} {xy(ay)}" '
               f'fill="none" stroke="{FIG_B}" stroke-width="1.5"/>')
    out.append(f'<line x1="{px}" x2="{xy(tx)}" y1="{py}" y2="{xy(ty)}" '
               f'stroke="{FIG_GREEN}" stroke-width="3" stroke-linecap="round"/>')
    out.append(f'<text x="{px - 8}" y="{py - arc + 2}" text-anchor="end" '
               f'font-size="13" font-weight="700">{num(loft)}°</text>')
    out.append(f'<text x="{px}" y="18" text-anchor="middle" font-size="8" '
               f'fill="{FIG_MUTED}">Vertical</text>')
    out.append(f'<text x="{xy(min(tx + 4, W - 30))}" y="{xy(max(ty - 5, 10))}" '
               f'font-size="8" fill="{FIG_MUTED}">Face</text>')
    out.append(f'<path d="M34 {py + 14}H12m5 -4l-5 4l5 4" fill="none" '
               f'stroke="{FIG_MUTED}"/>')
    out.append(f'<text x="38" y="{py + 17}" font-size="8" fill="{FIG_MUTED}">Target</text>')
    out.append("</svg>")
    caption = (f"The {esc(club)} face, drawn at its {num(loft)}° loft from the chart. "
               "Head shape is schematic, not to scale.")
    return (f'<figure class="fig data-table-zone">{"".join(out)}'
            f'<figcaption>{caption}</figcaption></figure>')


def wedge_loft_bounce_chart(m):
    """Loft × bounce matrix chart: one mark per option, grind codes beside it.

    This is the picture wedge buyers actually use — which bounces exist at each
    degree — so it plots the full option matrix rather than a set progression.
    """
    rows = [r for r in m["specs"]
            if r.get("loft") is not None and r.get("bounce") is not None]
    if len(rows) < 2:
        return ""
    # Group by loft/bounce cell: two grinds can share a bounce at a loft, and
    # two marks on one spot would hide each other.
    cells = OrderedDict()
    for r in rows:
        cells.setdefault((r["loft"], r["bounce"]), []).append(r.get("grind") or "")
    lofts = sorted({l for l, _ in cells})
    bounces = [b for _, b in cells]

    W, H = 320, 232
    left, right, top, base = 28, 8, 16, 196
    slot = (W - left - right) / len(lofts)
    bmin = min(0, int(min(bounces) // 4) * 4)
    bmax = max(bmin + 8, int(-(-max(bounces) // 4)) * 4)
    scale = (base - top) / (bmax - bmin)
    size = 8 if len(lofts) > 7 else 9

    def px(loft):
        return left + slot * (lofts.index(loft) + 0.5)

    def py(bounce):
        return base - (bounce - bmin) * scale

    out = [svg_open(
        W, H, f"{m['brand']} {m['model']} loft and bounce options",
        "Chart of every loft and bounce combination offered, with the grinds "
        "available at each: " + "; ".join(
            f"{num(l)}° loft, {num(b)}° bounce ({', '.join(g for g in gs if g) or 'standard'})"
            for (l, b), gs in cells.items()) + ".",
        "wlb", 520)]
    for tick in range(bmin, bmax + 1, 4):
        y = py(tick)
        out.append(f'<line x1="{left}" x2="{W - right}" y1="{xy(y)}" y2="{xy(y)}" '
                   f'stroke="{FIG_AXIS if tick == bmin else FIG_GRID}"/>')
        out.append(f'<text x="{left - 5}" y="{xy(y + 3)}" text-anchor="end" '
                   f'fill="{FIG_MUTED}">{tick}°</text>')
    for l in lofts:
        out.append(f'<text x="{xy(px(l))}" y="{base + 14}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="600">{num(l)}</text>')
    for (l, b), gs in cells.items():
        x, y = px(l), py(b)
        codes = "·".join(g for g in gs if g)
        out.append(f'<circle cx="{xy(x)}" cy="{xy(y)}" r="4.5" fill="{FIG_GREEN}" '
                   f'stroke="{FIG_SURFACE}" stroke-width="1.5">'
                   f'<title>{num(l)}° / {num(b)}° bounce'
                   f'{" / " + esc(codes) if codes else ""}</title></circle>')
        if codes:
            out.append(f'<text x="{xy(x)}" y="{xy(y - 7)}" text-anchor="middle" '
                       f'font-size="7" font-weight="600" fill="{FIG_MUTED}">'
                       f'{esc(codes)}</text>')
    out.append(f'<text x="0" y="8" font-size="8" fill="{FIG_MUTED}">Bounce</text>')
    out.append(f'<text x="0" y="{base + 14}" font-size="8" fill="{FIG_MUTED}">Loft</text>')
    out.append("</svg>")

    caption = (f"Every loft and bounce combination the {esc(m['brand'])} "
               f"{esc(m['model'])} is sold in — {plural(len(rows), 'option')} across "
               f"{plural(len(lofts), 'loft')}. The letters above each point are the "
               f"grinds available there.")
    return (f'<figure class="fig data-table-zone">{"".join(out)}'
            f'<figcaption>{caption}</figcaption></figure>')


def driver_loft_matrix(m):
    """Head × loft matrix chart: one row per variant, one mark per stock loft.

    The question a driver family page answers at a glance is which heads come
    in which lofts, so the chart is the availability matrix itself rather than
    a progression.
    """
    by = {name: [r["loft"] for r in rows if r.get("loft") is not None]
          for name, rows in driver_rows_by_variant(m).items()}
    by = {name: lofts for name, lofts in by.items() if lofts}
    if not by or sum(len(v) for v in by.values()) < 2:
        return ""
    lofts = sorted({l for ls in by.values() for l in ls})

    W = 320
    left, right, top, rowh = 78, 12, 10, 26
    base = top + len(by) * rowh
    H = base + 30
    lo, hi = lofts[0] - 0.75, lofts[-1] + 0.75

    def px(l):
        return left + (l - lo) / (hi - lo) * (W - left - right)

    out = [svg_open(
        W, H, f"{m['brand']} {m['model']} stock lofts by head",
        "Chart of the stock lofts each head variant is sold in: " + "; ".join(
            f"{name} at {', '.join(num(l) for l in ls)} degrees"
            for name, ls in by.items()) + ".",
        "dlm", 520)]
    for l in lofts:
        x = px(l)
        out.append(f'<line x1="{xy(x)}" x2="{xy(x)}" y1="{top}" y2="{base}" '
                   f'stroke="{FIG_GRID}"/>')
        out.append(f'<text x="{xy(x)}" y="{base + 14}" text-anchor="middle" '
                   f'font-weight="600">{num(l)}°</text>')
    out.append(f'<line x1="{left}" x2="{W - right}" y1="{base}" y2="{base}" '
               f'stroke="{FIG_AXIS}"/>')
    for i, (name, ls) in enumerate(by.items()):
        y = top + i * rowh + rowh / 2
        out.append(f'<text x="{left - 6}" y="{xy(y + 3)}" text-anchor="end" '
                   f'fill="{FIG_MUTED}">{esc(variant_short(m, name))}</text>')
        for l in ls:
            out.append(f'<circle cx="{xy(px(l))}" cy="{xy(y)}" r="4.5" '
                       f'fill="{FIG_GREEN}" stroke="{FIG_SURFACE}" '
                       f'stroke-width="1.5">'
                       f'<title>{esc(name)}: {num(l)}°</title></circle>')
    out.append(f'<text x="0" y="{base + 14}" font-size="8" '
               f'fill="{FIG_MUTED}">Loft</text>')
    out.append("</svg>")

    caption = (f"Stock loft options for each {esc(m['brand'])} {esc(m['model'])} "
               f"head — {plural(len(by), 'variant')} across "
               f"{plural(len(lofts), 'stock loft')}."
               + (" The hosel settings extend each head beyond its stamped loft."
                  if m.get("hosel") else ""))
    return (f'<figure class="fig data-table-zone">{"".join(out)}'
            f'<figcaption>{caption}</figcaption></figure>')


def compare_chart(a, b, clubs, aspec, bspec, label_a, label_b):
    """Both sets' lofts on one chart, club by club."""
    pts_a = [(i, aspec[c]["loft"]) for i, c in enumerate(clubs)
             if c in aspec and aspec[c].get("loft") is not None]
    pts_b = [(i, bspec[c]["loft"]) for i, c in enumerate(clubs)
             if c in bspec and bspec[c].get("loft") is not None]
    if len(pts_a) < 2 or len(pts_b) < 2:
        return ""
    W, H = 320, 232
    left, right, top, base = 28, 8, 20, 202
    n = len(clubs)
    slot = (W - left - right) / n
    lofts = [v for _, v in pts_a + pts_b]
    lo = int(min(lofts) // 10) * 10
    hi = max(lo + 10, int(-(-max(lofts) // 10)) * 10)
    scale = (base - top) / (hi - lo)
    size = 8 if n > 10 else 9

    def px(i):
        return left + slot * (i + 0.5)

    def py(v):
        return base - (v - lo) * scale

    out = [svg_open(
        W, H, f"{label_a} and {label_b} lofts compared",
        f"Line chart of loft in degrees by club for the {label_a} and the {label_b}. "
        + " ".join(
            f"{c}: {num(aspec[c]['loft']) if c in aspec else 'none'} and "
            f"{num(bspec[c]['loft']) if c in bspec else 'none'}." for c in clubs),
        "cmp", 520)]
    for tick in range(lo, hi + 1, 10):
        y = py(tick)
        out.append(f'<line x1="{left}" x2="{W - right}" y1="{xy(y)}" y2="{xy(y)}" '
                   f'stroke="{FIG_AXIS if tick == lo else FIG_GRID}"/>')
        out.append(f'<text x="{left - 5}" y="{xy(y + 3)}" text-anchor="end" '
                   f'fill="{FIG_MUTED}">{tick}°</text>')
    for i, c in enumerate(clubs):
        out.append(f'<text x="{xy(px(i))}" y="{base + 14}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="600">{esc(c)}</text>')
    for pts, colour in ((pts_a, FIG_A), (pts_b, FIG_B)):
        path = "".join(f'{"M" if k == 0 else "L"}{xy(px(i))} {xy(py(v))}'
                       for k, (i, v) in enumerate(pts))
        out.append(f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2" '
                   'stroke-linejoin="round" stroke-linecap="round"/>')
    # Markers last, A as a disc and B as a smaller diamond on top, so both
    # stay visible where the two sets share a loft.
    for i, v in pts_a:
        out.append(f'<circle cx="{xy(px(i))}" cy="{xy(py(v))}" r="5" fill="{FIG_A}" '
                   f'stroke="{FIG_SURFACE}" stroke-width="2">'
                   f'<title>{esc(label_a)} {esc(clubs[i])}: {num(v)}°</title></circle>')
    for i, v in pts_b:
        x, y = px(i), py(v)
        out.append(f'<path d="M{xy(x)} {xy(y - 4)}L{xy(x + 4)} {xy(y)}L{xy(x)} '
                   f'{xy(y + 4)}L{xy(x - 4)} {xy(y)}Z" fill="{FIG_B}" '
                   f'stroke="{FIG_SURFACE}" stroke-width="1.5">'
                   f'<title>{esc(label_b)} {esc(clubs[i])}: {num(v)}°</title></path>')
    out.append(f'<text x="0" y="8" font-size="8" fill="{FIG_MUTED}">Loft</text>')
    out.append("</svg>")

    legend = (
        '<ul class="fig-key">'
        f'<li><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        f'<circle cx="6" cy="6" r="5" fill="{FIG_A}"/></svg>{esc(label_a)}</li>'
        f'<li><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        f'<path d="M6 1L11 6L6 11L1 6Z" fill="{FIG_B}"/></svg>{esc(label_b)}</li></ul>')
    shared = [c for c in clubs if c in aspec and c in bspec]
    differing = [c for c in shared if aspec[c].get("loft") != bspec[c].get("loft")]
    if not shared:
        note = "The two sets have no club label in common."
    elif not differing:
        note = ("Lofts match on every club the two sets share, so the markers sit "
                "on top of each other.")
    else:
        note = (f"Lofts differ on {len(differing)} of the {len(shared)} clubs the two "
                "sets share. A lower point is a stronger loft.")
    return (f'<figure class="fig data-table-zone">{legend}{"".join(out)}'
            f'<figcaption>{note}</figcaption></figure>')


def wedge_compare_chart(a, b, label_a, label_b):
    """Paired columns: how many bounce/grind options each model offers per loft."""
    a_by, b_by = defaultdict(int), defaultdict(int)
    for r in a["specs"]:
        if r.get("loft") is not None:
            a_by[r["loft"]] += 1
    for r in b["specs"]:
        if r.get("loft") is not None:
            b_by[r["loft"]] += 1
    lofts = sorted(set(a_by) | set(b_by))
    if len(lofts) < 2:
        return ""

    W, H = 320, 232
    left, right, top, base = 28, 8, 18, 196
    slot = (W - left - right) / len(lofts)
    bar = min(12, slot / 2 - 2)
    nmax = max(max(a_by.values(), default=0), max(b_by.values(), default=0))
    ymax = max(2, nmax)
    scale = (base - top) / ymax
    size = 8 if len(lofts) > 7 else 9
    step = 1 if ymax <= 6 else 2

    out = [svg_open(
        W, H, f"{label_a} and {label_b} options per loft",
        f"Column chart of the number of bounce and grind options per loft for the "
        f"{label_a} and the {label_b}. " + " ".join(
            f"{num(l)} degrees: {a_by.get(l, 0)} and {b_by.get(l, 0)}."
            for l in lofts),
        "wcmp", 520)]
    for tick in range(0, ymax + 1, step):
        y = base - tick * scale
        out.append(f'<line x1="{left}" x2="{W - right}" y1="{xy(y)}" y2="{xy(y)}" '
                   f'stroke="{FIG_AXIS if tick == 0 else FIG_GRID}"/>')
        out.append(f'<text x="{left - 5}" y="{xy(y + 3)}" text-anchor="end" '
                   f'fill="{FIG_MUTED}">{tick}</text>')
    for i, l in enumerate(lofts):
        cx = left + slot * (i + 0.5)
        out.append(f'<text x="{xy(cx)}" y="{base + 14}" text-anchor="middle" '
                   f'font-size="{size}" font-weight="600">{num(l)}</text>')
        for off, count, colour, label in ((-bar - 1, a_by.get(l, 0), FIG_A, label_a),
                                          (1, b_by.get(l, 0), FIG_B, label_b)):
            if not count:
                continue
            h = count * scale
            x0, y0 = cx + off, base - h
            out.append(f'<rect x="{xy(x0)}" y="{xy(y0)}" width="{xy(bar)}" '
                       f'height="{xy(h)}" rx="2" fill="{colour}">'
                       f'<title>{esc(label)} at {num(l)}°: '
                       f'{plural(count, "option")}</title></rect>')
    out.append(f'<text x="0" y="8" font-size="8" fill="{FIG_MUTED}">Options</text>')
    out.append(f'<text x="0" y="{base + 14}" font-size="8" fill="{FIG_MUTED}">Loft</text>')
    out.append("</svg>")

    legend = (
        '<ul class="fig-key">'
        f'<li><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        f'<rect width="12" height="12" rx="2" fill="{FIG_A}"/></svg>{esc(label_a)}</li>'
        f'<li><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        f'<rect width="12" height="12" rx="2" fill="{FIG_B}"/></svg>{esc(label_b)}</li></ul>')
    note = (f"Bounce/grind options offered at each loft: "
            f"{plural(len(a['specs']), 'option')} in all for the {esc(label_a)}, "
            f"{len(b['specs'])} for the {esc(label_b)}. A missing column means the "
            f"model is not sold at that degree.")
    return (f'<figure class="fig data-table-zone">{legend}{"".join(out)}'
            f'<figcaption>{note}</figcaption></figure>')


# --------------------------------------------------------------------------
# model page
# --------------------------------------------------------------------------

AFFILIATE_DISCLOSURE = (
    '<p class="affiliate-note">We may earn a commission from purchases made '
    'through links on this page at no extra cost to you.</p>')


def wedge_availability(m):
    """Wedge version of availability(): same status logic, wedge-market wording."""
    brand, model = esc(m["brand"]), esc(m["model"])
    intro = m.get("year_introduced")
    pred = m.get("predecessor")
    succ = m.get("successor")
    check = ("Check the loft and bounce against the chart above before buying used — "
             "wedges are routinely bent from standard, and worn grooves cost spin "
             "long before a wedge looks worn.")

    if m.get("year_discontinued"):
        return f"""<h2>Finding one used</h2>
  <p>The {brand} {model} ran from {intro} to {m['year_discontinued']} and is no longer in
  production, so the used market is the only source. Search the used listings on eBay.
  {check}</p>"""

    if succ:
        return f"""<h2>Buying one</h2>
  <p>{brand} has since introduced the {esc(succ)} above it in the range, so the {model} is at
  the end of its retail life rather than fully retired — closeout stock still turns up at
  retailers, and it is well represented in the used listings on eBay. {check}</p>"""

    lineage = f" It replaced the {esc(pred)}." if pred else ""
    intro_txt = f"Introduced in {intro}, t" if intro else "T"
    if not is_current(m):
        return f"""<h2>Production status</h2>
  <p>{intro_txt}he {brand} {model} has no confirmed end date on file.{lineage} LoftChart
  records a discontinuation year only where a source dates it, and none has been found for
  this wedge, so it may or may not still be in the {brand} catalogue — check with {brand} or
  a retailer before counting on a new one. {check}</p>"""

    cat = WEDGE_CATEGORY_SHORT.get(m.get("category"))
    slot = (f"a current {cat} wedge in the {brand} range" if cat
            else f"a current wedge model in the {brand} range")
    return f"""<h2>Where it sits in the lineup</h2>
  <p>{intro_txt}he {brand} {model} is {slot} as of
  {long_date(m['current_as_of'])}, with no replacement announced.{lineage} New wedges are
  built to the loft, bounce and grind options in the chart above; a fitting can bend loft
  and lie from standard, so confirm the numbers on the order sheet. {check}</p>"""


def driver_availability(m):
    """Wood version of availability(): same status logic, wood-market wording."""
    brand, model = esc(m["brand"]), esc(m["model"])
    noun = WOOD_NOUN[m["club_type"]]
    intro = m.get("year_introduced")
    pred = m.get("predecessor")
    succ = m.get("successor")
    check = ("Before buying used, check the stamped loft against the chart above "
             f"and ask which hosel setting it is in — an adjustable {noun} may be "
             "set a degree or more away from the number on the sole, and sleeve "
             "adapters are brand- and generation-specific.")

    if m.get("year_discontinued"):
        return f"""<h2>Finding one used</h2>
  <p>The {brand} {model} ran from {intro} to {m['year_discontinued']} and is no longer in
  production, so the used market is the only source. Search the used listings on eBay.
  {check}</p>"""

    if succ:
        return f"""<h2>Buying one</h2>
  <p>{brand} has since introduced the {esc(succ)} above it in the range, so the {model} is at
  the end of its retail life rather than fully retired — closeout stock still turns up at
  retailers, and {noun}s one generation back are the sweet spot of the used market. {check}</p>"""

    lineage = f" It replaced the {esc(pred)}." if pred else ""
    intro_txt = f"Introduced in {intro}, t" if intro else "T"
    if not is_current(m):
        return f"""<h2>Production status</h2>
  <p>{intro_txt}he {brand} {model} has no confirmed end date on file.{lineage} LoftChart
  records a discontinuation year only where a source dates it, and none has been found for
  this line, so it may or may not still be in the {brand} catalogue — check with {brand} or
  a retailer before counting on a new one. {check}</p>"""

    cat = DRIVER_CATEGORY_SHORT.get(m.get("category"))
    slot = (f"a current {cat} line in the {brand} range" if cat and cat != "flagship"
            else f"the current {brand} {noun} line")
    hosel_txt = (" New heads are sold in the stock lofts charted above; the hosel "
                 "settings extend each head beyond its stamped loft, so a loft "
                 "between two stock options is usually reachable from either."
                 if m.get("hosel") else
                 " New heads are sold in the stock lofts charted above, and with "
                 "no adjustable hosel the stock loft is the one to get right.")
    return f"""<h2>Where it sits in the lineup</h2>
  <p>{intro_txt}he {brand} {model} is {slot} as of
  {long_date(m['current_as_of'])}, with no replacement announced.{lineage}{hosel_txt} {check}</p>"""


def _link_retailers(section, m):
    """Link the eBay mention in availability prose to the model's shop search.

    The buying-advice paragraphs are where purchase intent peaks, and a bare
    retailer name there is a dead end. Only eBay — the one tracked partner —
    gets an anchor. The replace never matches inside an href: URLs carry the
    lowercase "ebay".
    """
    ebay_url = _shop_links(m)
    section = section.replace(
        "eBay",
        f'<a href="{esc(ebay_url)}" rel="sponsored nofollow noopener" '
        f'target="_blank">eBay</a>')
    return section


def availability(m):
    """Closing section, written from the production status the data actually records.

    Only a set with a discontinuation year on file can be called out of production;
    55 models have `year_discontinued: null` and are still catalogued, and telling a
    reader to shop the used market for a set that is on the rack is simply wrong.
    """
    if m.get("club_type") == "wedges":
        return _link_retailers(wedge_availability(m), m)
    if is_wood(m):
        return _link_retailers(driver_availability(m), m)
    brand, model = esc(m["brand"]), esc(m["model"])
    intro = m.get("year_introduced")
    pred = m.get("predecessor")
    succ = m.get("successor")
    cat = CATEGORY_SHORT.get(m.get("category"))

    if m.get("year_discontinued"):
        section = f"""<h2>Finding a used set</h2>
  <p>The {brand} {model} ran from {intro} to {m['year_discontinued']} and is no longer in
  production, so the used market is the only source. Search the used listings on eBay, and
  check the loft and lie against the chart above before buying — sets this age have often
  been bent from standard.</p>"""

    elif succ:
        # Superseded, but no retirement year is recorded — say that plainly rather
        # than guessing at a date or claiming it is still current.
        section = f"""<h2>Buying a set</h2>
  <p>{brand} has since introduced the {esc(succ)} above it in the range, so the {model} is at
  the end of its retail life rather than fully retired — closeout sets still turn up at
  retailers while stock lasts, and it is well represented in the used listings on eBay.
  Check the loft and lie against the chart above before buying a used set: irons are
  routinely bent from standard during a fitting.</p>"""

    else:
        lineage = f" It replaced the {esc(pred)}." if pred else ""
        intro_txt = f"Introduced in {intro}, t" if intro else "T"
        if not is_current(m):
            # No end year, no successor and nobody has confirmed it is still on
            # sale: say exactly that instead of guessing in either direction.
            section = f"""<h2>Production status</h2>
  <p>{intro_txt}he {brand} {model} has no confirmed end date on file.{lineage} LoftChart
  records a discontinuation year only where a source dates it, and none has been found for
  this set, so it may or may not still be in the {brand} catalogue — check with {brand} or a
  retailer before counting on a new set. Used sets appear on eBay, and should be measured
  against the chart above before buying, since irons are routinely bent from standard.</p>"""
        else:
            # "a current ... " not "the current ...": several brands catalogue more than
            # one live set in the same category.
            slot = (f"a current {cat} set in the {brand} range" if cat
                    else f"a current model in the {brand} range")
            section = f"""<h2>Where it sits in the lineup</h2>
  <p>{intro_txt}he {brand} {model} is {slot} as of {long_date(m['current_as_of'])}, with no
  replacement announced.{lineage} New sets
  are built to the standard lofts, lies and lengths in the chart above, though a fitting can
  move any of them — so confirm the numbers on the order sheet. Used sets appear on eBay,
  and should be measured against this chart before buying.</p>"""

    return _link_retailers(section, m)


def _ebay_url(query):
    base = (f"https://www.ebay.com/sch/i.html"
            f"?_nkw={quote_plus(query)}&_sacat=0")
    if EBAY_CAMPAIGN_ID:
        return f"{base}&mkevt=1&mkcid=1&mkrid=711-53200-19255-0&campid={EBAY_CAMPAIGN_ID}&toolid=10001"
    return base


def _shop_links(m):
    """Return the eBay shop URL for a model.

    Wood family names are shared with iron lines (G440, Stealth), so the
    wood queries say which club they mean; iron and wedge queries stay as they
    were.
    """
    query = f"{m['brand']} {m['model']}"
    if is_wood(m):
        query += f" {WOOD_NOUN[m['club_type']]}"
    return _ebay_url(f"{query} golf")


def _shop_buttons(ebay_url):
    """The eBay button shared by the model and guide shop blocks.

    eBay is the sole affiliate partner, so it gets the one button and the
    primary (solid, highest-contrast) treatment. The label carries a verb —
    a retailer name alone reads as a citation, not something to click.
    """
    return (f'<a href="{esc(ebay_url)}" rel="sponsored nofollow noopener" '
            f'target="_blank" class="shop-btn shop-ebay shop-btn-primary">'
            f'See eBay listings</a>')


def top_cta(m):
    """Compact price-check CTA under the page head, above the spec table.

    The main shop block sits below the spec table, which puts it under the
    fold on every page; this strip is the above-the-fold entry point. One
    button — eBay is the sole affiliate partner.
    """
    ebay_url = _shop_links(m)
    brand, model = esc(m["brand"]), esc(m["model"])
    return f"""<div class="top-cta">
    <a href="{esc(ebay_url)}" rel="sponsored nofollow noopener"
       target="_blank" class="cta-btn cta-primary">Check {brand} {model} prices on eBay</a>
    <span class="cta-disc">Affiliate link &mdash; we may earn a commission at no extra cost to you.</span>
  </div>"""


def shop_block(m):
    """Affiliate shop links for a model page."""
    ebay_url = _shop_links(m)
    brand, model = esc(m["brand"]), esc(m["model"])
    buttons = _shop_buttons(ebay_url)

    noun = f"{WOOD_NOUN[m['club_type']]}s" if is_wood(m) else "sets"
    return f"""<div id="shop-block">
  <h2>Shop {brand} {model}</h2>
  <p class="shop-lede">Compare prices for new and used {noun} on eBay:</p>
  <div class="shop-links">{buttons}</div>
  {AFFILIATE_DISCLOSURE}
  </div>"""


# Shown/hidden against the main shop block's visibility; shared by every
# sticky bar variant, so it lives outside the f-strings.
STICKY_SCRIPT = """<script>
(function(){
  var bar=document.getElementById('sticky-bar'),
      block=document.getElementById('shop-block'),
      closed=false;
  if(!bar||!block) return;
  bar.querySelector('.sticky-bar-close').addEventListener('click',function(){
    bar.hidden=true; closed=true;
  });
  if('IntersectionObserver' in window){
    new IntersectionObserver(function(entries){
      if(closed) return;
      bar.hidden=entries[0].isIntersecting;
    },{threshold:0}).observe(block);
  }
})();
</script>"""


def _sticky_bar_shell(label, links, extra_class="", two_links=False):
    """The sticky bar chrome around any set of links."""
    cls = f" {extra_class}" if extra_class else ""
    noun = "links" if two_links else "link"
    return f"""<div id="sticky-bar" class="sticky-bar{cls}" hidden>
  <div class="sticky-bar-inner">
    <span class="sticky-bar-label">{esc(label)}</span>
    <div class="sticky-bar-links">{links}</div>
    <a class="sticky-bar-disc" href="/about/#affiliate-disclosure">Affiliate {noun}</a>
    <button class="sticky-bar-close" aria-label="Dismiss">&times;</button>
  </div>
</div>
{STICKY_SCRIPT}"""


def _sticky_link(ebay_url, text="See eBay listings"):
    return (f'<a href="{esc(ebay_url)}" rel="sponsored nofollow noopener"\n'
            f'         target="_blank" class="sticky-btn">{esc(text)}</a>')


def sticky_bar(m):
    """Floating bottom bar that appears once the main shop block scrolls away."""
    return _sticky_bar_shell(f"Shop {m['brand']} {m['model']}",
                             _sticky_link(_shop_links(m)))


def guide_shop_block(heading, query, lede):
    """Affiliate shop block for guide/aggregation pages (drivers, wedges)."""
    ebay_url = _ebay_url(query)
    buttons = _shop_buttons(ebay_url)
    return f"""<div id="shop-block">
  <h2>{esc(heading)}</h2>
  <p class="shop-lede">{esc(lede)}</p>
  <div class="shop-links">{buttons}</div>
  {AFFILIATE_DISCLOSURE}
  </div>"""


def guide_sticky_bar(label, query):
    """Floating bottom bar for guide/aggregation pages."""
    return _sticky_bar_shell(label, _sticky_link(_ebay_url(query)))


def compare_shop_block(a, b):
    """Dual-model shop block for compare pages.

    A compare reader is weighing both models, and intent usually leans to the
    newer one (b) — so each model gets its own primary button rather than
    model A getting the only link on the page.
    """
    noun = f"{WOOD_NOUN[a['club_type']]}s" if is_wood(a) else "sets"
    buttons = "".join(
        f'<a href="{esc(_shop_links(m))}" rel="sponsored nofollow noopener" '
        f'target="_blank" class="shop-btn shop-ebay shop-btn-primary">'
        f'Shop {esc(m["brand"])} {esc(m["model"])}</a>'
        for m in (a, b))
    return f"""<div id="shop-block">
  <h2>Shop both models</h2>
  <p class="shop-lede">Compare prices for new and used {noun} on eBay:</p>
  <div class="shop-links">{buttons}</div>
  {AFFILIATE_DISCLOSURE}
  </div>"""


def compare_sticky_bar(a, b):
    """Floating bottom bar for compare pages — one eBay link per model.

    Model names alone keep the two buttons short enough to sit side by side;
    the sticky-bar-two class drops the label on narrow screens so neither
    button is pushed off the bar.
    """
    links = "".join(_sticky_link(_shop_links(m), f"{m['model']} on eBay")
                    for m in (a, b))
    return _sticky_bar_shell("Shop these models", links,
                             extra_class="sticky-bar-two", two_links=True)


# Source citations are prose with the raw URL embedded ("retrieved from
# http://web.archive.org/web/2012.../ir_spec.htm - manufacturer spec table").
# The reader needs a working link and the host, not eighty characters of path,
# so each URL is swapped for a compact anchor. Trailing punctuation belongs to
# the sentence, not the URL.
SOURCE_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
WAYBACK_RE = re.compile(
    r'https?://web\.archive\.org/web/(\d{4})[^/]*/(?:https?:/{1,2})?(?:www\.)?([^/\s]+)')


# Only the affiliate partner's domain carries rel="sponsored": other retailer
# citations (2ndswing.com, globalgolf.com, ...) are plain spec references with
# no commercial relationship, so "sponsored" would misdescribe them.
SPONSORED_DOMAINS = {"ebay.com"}


def _is_sponsored_url(url):
    host = url.split('/')[2].split(':')[0].lower()
    host = re.sub(r'^www\.', '', host)
    return host in SPONSORED_DOMAINS


def source_link(url):
    m = WAYBACK_RE.match(url)
    if m:
        label = f"{m.group(2).split(':')[0]}, archived {m.group(1)}"
    else:
        label = re.sub(r'^www\.', '', url.split('/')[2].split(':')[0])
    rel = "sponsored nofollow noopener" if _is_sponsored_url(url) else "nofollow noopener"
    return f'<a href="{esc(url)}" rel="{rel}">{esc(label)}</a>'


def linkify_source(text):
    out, pos = [], 0
    for m in SOURCE_URL_RE.finditer(text):
        url = m.group(0).rstrip('.,;:')
        out.append(esc(text[pos:m.start()]))
        out.append(source_link(url))
        pos = m.start() + len(url)
    out.append(esc(text[pos:]))
    return "".join(out)


def model_page(m, brands, models_by_key, compares_by_key):
    is_wedge = m.get("club_type") == "wedges"
    # is_driver gates the wood family code path — drivers, fairway woods and
    # hybrids all render the same page; wood_noun carries the per-type word.
    is_driver = is_wood(m)
    wood_noun = WOOD_NOUN.get(m.get("club_type"))
    s7 = seven_iron(m)
    if is_wedge:
        title = fit_title(f"{m['title']} Specs", " — Loft & Bounce Chart",
                          f" | {SITE_NAME}")
    elif is_driver:
        # The club type is already in m["title"]; the tail carries the chart
        # terms people search ("qi35 loft settings", "g440 adjustment chart").
        title = fit_title(f"{m['title']} Specs", " — Lofts & Settings Chart",
                          f" | {SITE_NAME}")
    else:
        title = fit_title(f"{m['title']} Specs", " — Loft & Lie Chart",
                          f" | {SITE_NAME}")
    # Only advertise columns this model actually carries — several sets (the
    # Eye 2 among them) have no published offset or swing weight, and promising
    # data the chart doesn't show costs more in bounces than it gains in clicks.
    rows = m["specs"]
    has_offset = any(r.get("offset") is not None for r in rows)
    has_sw = any(r.get("swing_weight") is not None for r in rows)
    extras = ["lie angles", "lengths"]
    if has_offset:
        extras.append("offsets")
    if has_sw:
        extras.append("swing weights")
    cols = comma_list(extras)

    if rows:
        span = f"{club_noun(m, rows[0]['club'])} to {club_noun(m, rows[-1]['club'])}"
    else:
        span = "every club"

    if is_wedge:
        lofts = wedge_lofts(m)
        n_combos = len(m["specs"])
        grind_codes = [g.get("code") for g in (m.get("grinds") or []) if g.get("code")]
        n_grinds = len(grind_codes)
        if n_grinds:
            head_part = (f"{m['brand']} {m['model']} wedge specs: "
                         f"{num(lofts[0])}°–{num(lofts[-1])}°, "
                         f"{n_combos} loft/bounce/grind options. ")
            desc = fit_desc(head_part, [
                f"Full option chart with {plural(n_grinds, 'grind')} "
                f"({', '.join(grind_codes)}), bounce angles and availability at "
                f"every loft.",
                f"Full option chart with {plural(n_grinds, 'grind')}, bounce angles "
                f"and availability at every loft.",
                "Full option chart with bounce and grind at every loft.",
                "Complete loft, bounce and grind chart.",
            ])
        else:
            head_part = (f"{m['brand']} {m['model']} wedge specs: "
                         f"{num(lofts[0])}°–{num(lofts[-1])}°, "
                         f"{plural(n_combos, 'loft/bounce option')}. ")
            desc = fit_desc(head_part, [
                "Full factory chart with the bounce, lie and length at every "
                "loft the model is sold in.",
                "Full factory chart with the bounce at every loft it is sold in.",
                "Complete loft and bounce chart.",
            ])
    elif is_driver:
        d_lofts = driver_lofts(m)
        variants = m.get("variants") or []
        n_var = len(variants)
        hosel = m.get("hosel") or {}
        head_part = (f"{m['brand']} {m['model']} {wood_noun} specs: "
                     f"{plural(n_var, 'head variant')}, lofts "
                     f"{num(d_lofts[0])}°–{num(d_lofts[-1])}°. " if d_lofts else
                     f"{m['brand']} {m['model']} {wood_noun} specifications. ")
        if hosel:
            rich = ([f"Stock lofts for every head plus the full "
                     f"{hosel['system']} adjustment chart, "
                     f"{hosel['loft_range']} of loft."]
                    if hosel.get("system") and hosel.get("loft_range") else [])
            desc = fit_desc(head_part, rich + [
                "Stock lofts for every head plus the full hosel adjustment "
                "chart with every setting.",
                "Stock lofts for every head and the hosel adjustment chart.",
                "Full loft and hosel settings chart.",
            ])
        else:
            desc = fit_desc(head_part, [
                "Stock loft options for every head variant, with head sizes "
                "and stock shafts — a non-adjustable, glued hosel.",
                "Stock loft options for every head, with lies and lengths — "
                "a non-adjustable, glued hosel.",
                "Stock loft options for every head variant on a fixed hosel.",
                "Full stock loft chart for every head.",
            ])
    elif s7:
        length_part = (f", {num(s7['length'])}\" length"
                       if s7.get("length") is not None else "")
        lie_part = f", {num(s7['lie'])}° lie" if s7.get("lie") is not None else ""
        head_part = (f"{m['brand']} {m['model']} specifications: {num(s7['loft'])}° loft "
                     f"({club_noun(m, s7['club'])}){lie_part}"
                     f"{length_part}. ")
        desc = fit_desc(head_part, [
            f"Full loft chart with {cols} for every club, {span}.",
            f"Full loft chart with {cols} for every club in the set.",
            f"Full loft chart with lie angles and lengths, {span}.",
            "Full loft chart for every club in the set.",
        ])
    else:
        head_part = f"{m['brand']} {m['model']} {m['type_label'].lower()} specifications: "
        desc = fit_desc(head_part, [
            f"complete loft chart with {cols} for every club, {span}.",
            f"complete loft chart with {cols} for every club in the set.",
            "complete loft chart with lie angles and lengths for every club.",
        ])

    nav, bc = crumbs([("Home", "/"),
                      (m["brand"], f"/{m['brand_slug']}/"),
                      (f"{m['model']} {m['type_label']}", None)])

    # The release year and the category link to their hubs — the only
    # contextual route from a chart to the other sets of its year and type.
    intro = m.get("year_introduced")
    years_html = esc(year_range(m))
    if intro:
        years_html = years_html.replace(
            str(intro), f'<a href="/years/{intro}/">{intro}</a>', 1)
    cat = m.get("category")
    cat_html = esc(category_label(m))
    # Every validated category has a hub page — iron, wedge and wood models
    # all feed /category/ — so the label links for every club type.
    if (cat in CATEGORY_LABEL or cat in WEDGE_CATEGORY_LABEL
            or cat in DRIVER_CATEGORY_LABEL):
        cat_html = f'<a href="/category/{esc(cat)}/">{cat_html}</a>'
    if is_driver:
        hosel = m.get("hosel") or {}
        ccs = sorted({v["head_cc"] for v in (m.get("variants") or [])
                      if v.get("head_cc") is not None})
        cc_txt = (f"{num(ccs[0])} cc" if len(ccs) == 1 else
                  f"{num(ccs[0])}–{num(ccs[-1])} cc") if ccs else "—"
        if hosel:
            hosel_txt = " · ".join(
                x for x in (hosel.get("system"), hosel.get("loft_range")) if x) or "Adjustable"
        else:
            hosel_txt = "Non-adjustable"
        facts = [("Years produced", years_html),
                 ("Category", cat_html),
                 ("Head variants", esc(", ".join(
                     variant_short(m, v.get("name"))
                     for v in (m.get("variants") or [])) or "—")),
                 ("Loft range", f"{num(d_lofts[0])}°–{num(d_lofts[-1])}°"
                  if d_lofts else "—"),
                 ("Head size", esc(cc_txt)),
                 ("Hosel", esc(hosel_txt))]
    elif is_wedge:
        facts = [("Years produced", years_html),
                 ("Category", cat_html),
                 ("Construction", esc(m.get("construction") or "—")),
                 ("Material", esc(m.get("material") or "—")),
                 ("Loft range", f"{num(lofts[0])}°–{num(lofts[-1])}°" if lofts else "—"),
                 ("Options", esc(f"{n_combos} loft/bounce/grind combinations"
                                 if n_grinds else
                                 f"{n_combos} loft/bounce combinations"))]
    else:
        facts = [("Years produced", years_html),
                 ("Category", cat_html),
                 ("Construction", esc(m.get("construction") or "—")),
                 ("Material", esc(m.get("material") or "—")),
                 ("Set makeup", esc("–".join([m["specs"][0]["club"], m["specs"][-1]["club"]])
                                    if m["specs"] else "—"))]
    facts_html = "".join(
        f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in facts)

    # shafts
    shafts = ""
    if m.get("stock_shafts"):
        items = []
        for s in m["stock_shafts"]:
            bits = [f'<strong>{esc(s["name"])}</strong>']
            meta = []
            if s.get("material"):
                meta.append(esc(s["material"]))
            if s.get("weight"):
                meta.append(esc(s["weight"]))
            if s.get("flex"):
                meta.append("flexes: " + esc(", ".join(s["flex"])))
            if meta:
                bits.append(" — " + " · ".join(meta))
            items.append("<li>" + "".join(bits) + "</li>")
        shafts = ("<h2>Stock shafts</h2><ul class=\"linklist\">"
                  + "".join(items) + "</ul>")

    # faq
    faq_html = ""
    faq_ld = None
    if m.get("faq"):
        blocks = "".join(
            f"<details><summary>{esc(f['q'])}</summary>"
            f"<p class=\"faq-body\">{esc(f['a'])}</p></details>" for f in m["faq"])
        faq_html = f'<h2>Frequently asked questions</h2><div class="faq">{blocks}</div>'
        faq_ld = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
                for f in m["faq"]],
        }

    # related models
    related = []
    for r in (m.get("related_models") or []):
        target = models_by_key.get(r["slug"])
        if target:
            related.append(f'<li><a href="{target["url"]}">{esc(r.get("label") or target["title"])}</a></li>')
    for cmp_slug, other in compares_by_key.get(m["key"], []):
        related.append(f'<li><a href="/compare/{cmp_slug}/">Compare: '
                       f'{esc(m["brand"])} {esc(m["model"])} vs {esc(other["brand"])} {esc(other["model"])}</a></li>')
    related_html = ""
    if related:
        related_html = "<h2>Related models</h2><ul class=\"linklist\">" + "".join(related) + "</ul>"

    # confidence note
    conf = (m.get("confidence") or "").lower()
    conf_note = ""
    if conf in ("medium", "low"):
        conf_note = ('<div class="note"><p><strong>Data confidence: '
                     f'{esc(conf)}.</strong> These figures are compiled from secondary '
                     "sources rather than a manufacturer spec sheet. If you have an "
                     f'original catalogue page, {email_link("send it over")} '
                     "and we will update the chart.</p></div>")

    sources_html = ("<div class=\"sources\"><strong>Data compiled from:</strong><ul>"
                    + "".join(f"<li>{linkify_source(s)}</li>" for s in (m.get("sources") or []))
                    + f"</ul><p>Last updated {long_date(m['modified'])}. Spot an error? "
                    f'{email_link()}</p></div>')

    article_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": f"{m['title']} Specifications",
        "description": desc,
        "datePublished": m["published"],
        "dateModified": m["modified"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + m["url"]},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        # A Product entity here makes Google expect offers/review/aggregateRating.
        # These are reference spec pages, not listings, so describe the subject
        # as a plain Thing instead.
        "about": {"@type": "Thing", "name": m["title"]},
        "keywords": ", ".join(
            [m["brand"], m["model"], "wedges", "wedge", "loft", "bounce",
             "grind", "specifications"] if is_wedge else
            [m["brand"], m["model"], wood_noun, "loft", "settings",
             "adjustment chart", "hosel", "specifications"] if is_driver else
            [m["brand"], m["model"], m["type_label"],
             "loft", "lie", "length", "specifications"]),
    }

    if is_wedge:
        caption = (f"Loft, bounce and grind options for the "
                   f"{m['brand']} {m['model']} wedges.")
        lede = (f"Every loft, bounce and grind combination the {m['brand']} "
                f"{m['model']} wedges are sold in, {year_range(m)}.")
    elif is_driver:
        caption = (f"Stock loft options for each {m['brand']} {m['model']} "
                   f"head variant.")
        lede = (f"Stock lofts for every {m['brand']} {m['model']} head"
                + (" and the full hosel adjustment chart" if m.get("hosel")
                   else "")
                + f", {year_range(m)}.")
    else:
        caption = (f"Standard men's steel-shaft specifications for the "
                   f"{m['brand']} {m['model']} {m['type_label'].lower()}.")

        # Keep the chart high on the page — the long-form description follows it.
        lede = (f"Full factory loft, lie and length chart for the {m['brand']} {m['model']} "
                f"{m['type_label'].lower()}, {year_range(m)}.")
    about = ""
    if m.get("description"):
        about = (f"<h2>About the {esc(m['brand'])} {esc(m['model'])}</h2>"
                 f"<p>{esc(m['description'].strip())}</p>")

    availability_html = availability(m)

    # A maker that changes how it measures a club makes two of its own charts
    # disagree without the clubs changing; the note says which basis this is.
    length_note = (f'<p class="table-note"><strong>Length note:</strong> '
                   f'{esc(m["length_note"].strip())}</p>'
                   if m.get("length_note") else "")

    # Drivers get the hosel adjustment chart directly under the spec table —
    # it is the page's highest-intent content and must sit above the fold-ish.
    extra_top = ""
    if is_wedge:
        chart = wedge_loft_bounce_chart(m)
        figures = (f'<h2>Loft and bounce options</h2>'
                   f'<div class="figs figs-one">{chart}</div>' if chart else "")
        grind_html = grind_guide(m)
        gapping_html = wedge_gapping_links(m)
        table_heading = "Loft, bounce &amp; grind chart"
        table_html = wedge_spec_table(m, caption)
        table_note = ("<p class=\"table-note\">Each row is one combination the model is "
                      "sold in, factory standard. Loft and lie on an individual wedge may "
                      "differ if it has been bent during a fitting.</p>")
    elif is_driver:
        chart = driver_loft_matrix(m)
        figures = (f'<h2>Lofts at a glance</h2>'
                   f'<div class="figs figs-one">{chart}</div>' if chart else "")
        grind_html = variant_guide(m)
        gapping_html = driver_guide_links(m)
        extra_top = hosel_chart(m)
        table_heading = "Stock lofts by head variant"
        table_html = driver_spec_table(m, caption)
        table_note = ("<p class=\"table-note\">Lofts are the stamped stock options for "
                      "each head, factory standard."
                      + (" The hosel chart below shows how far each can be "
                         "adjusted from its stamped loft.</p>" if m.get("hosel")
                         else "</p>"))
    else:
        chart, angle = loft_chart(m), loft_angle(m)
        figures = (f'<h2>Loft progression</h2><div class="figs">{chart}{angle}</div>'
                   if chart or angle else "")
        grind_html = ""
        gapping_html = ""
        table_heading = "Loft, lie &amp; length chart"
        table_html = spec_table(m, caption)
        # Byte-identical to the note this replaced, line break included, so the
        # 830 built iron pages do not all change over whitespace.
        table_note = ("<p class=\"table-note\">Lofts and lies are the factory standard "
                      "build. Individual clubs may\n  differ if they have been bent, "
                      "re-shafted or re-gripped during their life.</p>")

    # The hosel chart rides in the shop slot so empty pages stay byte-identical.
    shop_html = (extra_top + "\n\n  " if extra_top else "") + shop_block(m)
    sticky_html = sticky_bar(m)

    # Each block after the chart sits in its own .model-section so the CSS can
    # draw a hairline between them; empty blocks are dropped rather than
    # rendering a divider with nothing under it.
    sections_html = "".join(
        f'<section class="model-section">{s}</section>'
        for s in (about, grind_html, shafts, related_html, gapping_html,
                  faq_html, availability_html) if s)

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(m['title'])} Specifications</h1>
    <p class="lede">{esc(lede)}</p>
  </div>

  {top_cta(m)}

  <dl class="facts">{facts_html}</dl>

  {conf_note}

  <h2>{table_heading}</h2>
  {table_html}
  {table_note}
  {length_note}

  {shop_html}

  {figures}

  {sections_html}

  {sources_html}
</div>
{sticky_html}
"""
    ld = [bc, article_ld] + ([faq_ld] if faq_ld else [])
    page(m["url"], title, desc, body, brands, ld, og_type="article")


# --------------------------------------------------------------------------
# brand pages
# --------------------------------------------------------------------------

def brand_page(b, models, brands):
    ms = sorted(models, key=lambda m: (m.get("year_introduced") or 0, m["model"]))
    years = [m["year_introduced"] for m in ms if m.get("year_introduced")]
    names = ", ".join(m["model"] for m in ms[:3])
    # A brand with wedge (or other) models on file is no longer an iron archive,
    # so its page stops claiming to be one.
    irons_only = all(m["club_type"] == "irons" for m in ms)
    noun = "Iron" if irons_only else "Golf Club"
    title = fit_title(f"{b['name']} {noun} Specs", " — Loft & Lie Charts",
                      f" | {SITE_NAME}")
    # Compact head leaves room for the family list, which is the part that
    # carries the searched terms ("Ping G series").
    head_part = (f"{b['name']} {noun.lower()} specifications, "
                 f"{min(years)}–{max(years)}. ")
    # Prefer naming model families over a truncated model list — families are
    # what people actually search ("Ping G series", "Ping i series").
    fam = b.get("families")
    fam_txt = ", ".join(fam) if fam else names
    all_names = ", ".join(m["model"] for m in ms)
    span = loft_span(ms)
    # The loft figure earns its place ahead of a longer model list: it is the
    # number people search, and it differentiates one brand page from the next.
    spanned = [
        f"{span}. Loft charts, lie angles and lengths for "
        f"{plural(len(ms), 'model')} including {fam_txt}.",
        f"{span}. Loft charts for {plural(len(ms), 'model')} including {fam_txt}.",
        f"{span}. Loft charts for {plural(len(ms), 'model')}: {all_names}.",
        f"{span}. Loft charts, lie angles and lengths for every model.",
    ] if span else []
    desc = fit_desc(head_part, spanned + [
        f"Loft charts, lie angles and lengths for {plural(len(ms), 'model')} "
        f"including {fam_txt}.",
        f"Loft charts for {plural(len(ms), 'model')}: {all_names}.",
        f"Loft charts, lie angles and lengths for all {plural(len(ms), 'model')}.",
    ])

    nav, bc = crumbs([("Home", "/"), ("Brands", "/brands/"), (b["name"], None)])

    types = sorted({m["club_type"] for m in ms})
    chips = ('<ul class="chips"><li><button class="chip" data-filter="all" '
             'aria-pressed="true">All</button></li>'
             + "".join(f'<li><button class="chip" data-filter="{esc(t)}" '
                       f'aria-pressed="false">{esc(CLUB_TYPE_LABEL.get(t, t))}</button></li>'
                       for t in types)
             + "</ul>") if len(types) > 1 else ""

    by_decade = defaultdict(list)
    for m in ms:
        by_decade[(m["year_introduced"] // 10) * 10].append(m)

    sections = []
    for dec in sorted(by_decade):
        lis = []
        for m in by_decade[dec]:
            if is_wood(m):
                d_lofts = driver_lofts(m)
                spec = (f'<span class="mt">{num(d_lofts[0])}°–{num(d_lofts[-1])}° · '
                        f'{plural(len(m.get("variants") or []), "head variant")}</span>'
                        if d_lofts else "")
            elif m["club_type"] == "wedges":
                w_lofts = wedge_lofts(m)
                spec = (f'<span class="mt">{num(w_lofts[0])}°–{num(w_lofts[-1])}° · '
                        f'{plural(len(m["specs"]), "loft/bounce/grind option")}</span>'
                        if w_lofts else "")
            else:
                s7 = seven_iron(m)
                spec = (f'<span class="mt">{club_noun(m, s7["club"])} {num(s7["loft"])}° loft · '
                        f'{CATEGORY_LABEL.get(m.get("category"), "")}</span>') if s7 else ""
            lis.append(f'<li data-club-type="{esc(m["club_type"])}">'
                       f'<span class="yr">{year_range(m)}</span>'
                       f'<span class="nm"><a href="{m["url"]}">{esc(m["model"])} '
                       f'{esc(m["type_label"])}</a></span>{spec}</li>')
        sections.append(f'<section class="decade" data-decade-group>'
                        f"<h2>{dec}s</h2>"
                        f'<ul class="model-list">{"".join(lis)}</ul></section>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(b['name'])} Golf Club Specifications</h1>
    <p class="lede">{esc((b.get('blurb') or '').strip())}</p>
  </div>
  <dl class="facts">
    <div><dt>Founded</dt><dd>{esc(b.get('founded', '—'))}</dd></div>
    <div><dt>Headquarters</dt><dd>{esc(b.get('hq', '—'))}</dd></div>
    <div><dt>Models on file</dt><dd>{len(ms)}</dd></div>
    <div><dt>Years covered</dt><dd>{min(years)}–{max(years)}</dd></div>
  </dl>
  {chips}
  {''.join(sections)}

  {guide_shop_block(f"Shop {b['name']} clubs", f"{b['name']} golf clubs",
                     f"Search new and used {b['name']} clubs on eBay:")}
</div>
{guide_sticky_bar(f"Shop {b['name']} clubs", f"{b['name']} golf clubs")}
"""
    page(f"/{b['slug']}/", title, desc, body, brands,
         [bc, item_list(ms, f"{b['name']} club models")])


def brands_index(brands, by_brand, all_models):
    title = f"All Golf Club Brands — Specification Archive | {SITE_NAME}"
    span = loft_span(all_models)
    head_part = (f"{plural(len(all_models), 'golf club model')} across "
                 f"{plural(len(brands), 'manufacturer')}, {span}. " if span else
                 f"{plural(len(all_models), 'golf club model')} across "
                 f"{plural(len(brands), 'manufacturer')}. ")
    desc = fit_desc(head_part, [
        "Loft charts, lie angles and lengths for Ping, Titleist, Callaway, "
        "TaylorMade, Mizuno and more.",
        "Loft charts, lie angles and lengths for every brand.",
        "Full loft charts for every brand."])
    nav, bc = crumbs([("Home", "/"), ("Brands", None)])

    cards = []
    listed = []
    for b in brands:
        ms = by_brand.get(b["slug"], [])
        if not ms:
            continue
        listed.append({"url": f"/{b['slug']}/", "title": b["name"]})
        years = [m["year_introduced"] for m in ms if m.get("year_introduced")]
        cards.append(
            f'<a class="card brand-card" href="/{b["slug"]}/" '
            f'style="--brand-color:{esc(b.get("color", "#C9A94E"))}">'
            f'<span class="card-title">{esc(b["name"])}</span>'
            f'<span class="card-meta">{plural(len(ms), "model")} · {min(years)}–{max(years)}</span>'
            f'<span class="card-spec">Founded {esc(b.get("founded", "—"))}</span></a>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Club Brands</h1>
    <p class="lede">Every manufacturer in the LoftChart archive. Each brand page lists its
    models by decade with the headline loft for each set.</p>
  </div>
  <div class="grid">{''.join(cards)}</div>
</div>
"""
    page("/brands/", title, desc, body, brands,
         [bc, item_list(listed, "Golf club brands")])


# --------------------------------------------------------------------------
# year / category pages
# --------------------------------------------------------------------------

# Fewer than this many models on a year page and it carries nothing the model
# cards do not already say — indexed, it competes with them for nothing.
YEAR_MIN_MODELS = 3


def club_row(m, club):
    for row in m["specs"]:
        if row["club"] == club:
            return row
    return None


def median(values):
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else round((s[mid - 1] + s[mid]) / 2, 1)


def year_summary(year, ms, by_year):
    """The paragraph and table that make a year page more than a list of cards.

    Everything here is computed from the sets on file, so it stays in step with
    the archive; a year with no 7-iron on file simply gets no summary.
    """
    sevens = [(club_row(m, "7")["loft"], m) for m in ms
              if club_row(m, "7") and club_row(m, "7").get("loft") is not None]
    if not sevens:
        return ""
    sevens.sort(key=lambda p: (p[0], p[1]["brand"], p[1]["model"]))
    lofts = [l for l, _ in sevens]

    def named(m):
        return f'<a href="{m["url"]}">{esc(m["brand"])} {esc(m["model"])}</a>'

    if len(sevens) == 1:
        text = (f"The one set on file for {year}, the {named(sevens[0][1])}, has a "
                f"{num(lofts[0])}° 7-iron.")
    elif lofts[0] == lofts[-1]:
        text = (f"All {len(sevens)} sets on file for {year} have a {num(lofts[0])}° "
                "7-iron.")
    else:
        text = (f"Across the {len(sevens)} sets on file for {year}, the 7-iron runs "
                f"from {num(lofts[0])}° in the {named(sevens[0][1])} to "
                f"{num(lofts[-1])}° in the {named(sevens[-1][1])}, with a median of "
                f"{num(median(lofts))}°.")

    wedges = [club_row(m, "PW")["loft"] for m in ms
              if club_row(m, "PW") and club_row(m, "PW").get("loft") is not None]
    if wedges:
        text += (f" The median pitching wedge is {num(median(wedges))}°."
                 if len(wedges) > 1 else
                 f" The pitching wedge on file is {num(wedges[0])}°.")

    # Context from a decade either side, where the archive has enough sets for
    # the comparison to mean something.
    context = []
    for other in (year - 10, year + 10):
        theirs = [club_row(m, "7")["loft"] for m in by_year.get(other, [])
                  if club_row(m, "7") and club_row(m, "7").get("loft") is not None]
        if len(theirs) >= YEAR_MIN_MODELS:
            context.append(f"{num(median(theirs))}° among the "
                           f'<a href="/years/{other}/">{other} releases</a>')
    if context:
        text += (" For comparison, the median 7-iron is "
                 + " and ".join(context) + ".")

    cats = defaultdict(int)
    for m in ms:
        cats[m.get("category")] += 1
    mix = comma_list([
        f'{n} <a href="/category/{esc(c)}/">{esc(CATEGORY_SHORT.get(c, c))}</a>'
        for c, n in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0])) if c])
    mix_html = f"<p>By category: {mix}.</p>" if mix else ""

    def cell(row, key):
        return num(row[key]) if row and row.get(key) is not None else "—"

    rows = "".join(
        f'<tr><th scope="row">{named(m)}</th>'
        f'<td>{esc(CATEGORY_SHORT.get(m.get("category"), "—"))}</td>'
        f'<td>{cell(club_row(m, "7"), "loft")}</td>'
        f'<td>{cell(club_row(m, "7"), "lie")}</td>'
        f'<td>{cell(club_row(m, "7"), "length")}</td>'
        f'<td>{cell(club_row(m, "PW"), "loft")}</td></tr>'
        for _, m in sevens)
    return f"""<h2>{year} iron lofts compared</h2>
  <p>{text}</p>
  {mix_html}
  <div class="table-scroll data-table-zone"><table class="specs">
    <thead><tr><th scope="col">Model</th><th scope="col">Category</th>
    <th scope="col">7-iron loft (°)</th><th scope="col">7-iron lie (°)</th>
    <th scope="col">7-iron length (in)</th><th scope="col">PW loft (°)</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Strongest 7-iron first. Sets with no 7-iron on file are listed
  below but left out of the table.</p>"""


def year_page(year, ms, brands, by_year):
    ms = sorted(ms, key=lambda m: (m["brand"], m["model"]))
    by_type = defaultdict(list)
    for m in ms:
        by_type[m["club_type"]].append(m)
    types = ([t for t in CLUB_SECTION_ORDER if by_type[t]]
             + sorted(t for t in by_type if t not in CLUB_SECTION_ORDER))
    types_txt = comma_list(CLUB_SECTION_LABEL.get(t, t).lower() for t in types)
    irons = by_type.get("irons", [])
    years = sorted(by_year)
    at = years.index(year)
    around = []
    if at > 0:
        around.append(f'<a href="/years/{years[at - 1]}/">← {years[at - 1]}</a>')
    if at < len(years) - 1:
        around.append(f'<a href="/years/{years[at + 1]}/">{years[at + 1]} →</a>')
    around_html = (f'<p class="table-note">{" · ".join(around)} · '
                   '<a href="/years/">All years</a></p>')
    title = f"{year} Golf Club Releases — Specifications | {SITE_NAME}"
    brand_names = sorted({m["brand"] for m in ms})
    blist = comma_list(brand_names)
    span = loft_span(irons)
    if len(types) == 1:
        noun = {"irons": "iron model", "wedges": "wedge model",
                "driver": "driver family", "fairway_wood": "fairway wood family",
                "hybrid": "hybrid family"}.get(types[0], "model")
        head = f"{year} golf club releases: {plural(len(ms), noun)}"
    else:
        head = (f"{year} golf club releases: {plural(len(ms), 'model')} across "
                f"{types_txt}")
    head_part = f"{head}, {span}. " if span else f"{head}. "
    desc = fit_desc(head_part, [
        f"Full specifications from {blist}. Compare loft, lie and length across "
        f"every model released in {year}.",
        f"Full specifications from {blist}. Compare loft, lie and length.",
        f"Specifications from {plural(len(brand_names), 'brand')}. Compare loft, "
        f"lie and length across every {year} release.",
        f"Compare loft, lie and length across every {year} release.",
        f"Specifications from {plural(len(brand_names), 'brand')}.",
    ])
    nav, bc = crumbs([("Home", "/"), ("Years", "/years/"), (str(year), None)])
    if len(types) == 1:
        lede = (f"{len(ms)} model{'s' if len(ms) != 1 else ''} on file introduced in "
                f"{year}. Every entry links to its full loft, lie and length chart.")
        sections = (f"<h2>Every {year} model</h2>"
                    f'<div class="grid">{"".join(model_card(m) for m in ms)}</div>')
    else:
        lede = (f"{len(ms)} models on file introduced in {year}, spanning "
                f"{types_txt}. Every entry links to its full specification chart.")
        sections = "".join(
            f'<h2>{year} {esc(CLUB_SECTION_LABEL.get(t, t).lower())}</h2>'
            f'<div class="grid">{"".join(model_card(m) for m in by_type[t])}</div>'
            for t in types)
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Clubs Released in {year}</h1>
    <p class="lede">{lede}</p>
  </div>
  {year_summary(year, irons, by_year)}
  {sections}
  {around_html}

  {guide_shop_block(f"Shop {year} clubs", f"{year} golf clubs",
                     f"Search new and used clubs from the {year} release year on eBay:")}
</div>
{guide_sticky_bar(f"Shop {year} clubs", f"{year} golf clubs")}
"""
    # A year page listing one or two models is a thin duplicate of the cards it
    # holds. Keep it as a crawl path from /years/, but out of the index.
    page(f"/years/{year}/", title, desc, body, brands, [bc, item_list(ms, f"{year} releases")],
         noindex=len(ms) < YEAR_MIN_MODELS)


def years_index(by_year, brands, all_models):
    title = f"Golf Clubs by Year of Release | {SITE_NAME}"
    yrs = sorted(by_year)
    desc = fit_desc(
        f"Golf club specifications by release year, {yrs[0]} to {yrs[-1]}: "
        f"{plural(len(all_models), 'model')} across {plural(len(yrs), 'year')}. ",
        ["Full loft, lie and length charts for every model.",
         "Full loft and lie charts.",
         ""])
    nav, bc = crumbs([("Home", "/"), ("Years", None)])
    cards = "".join(
        f'<a class="card" href="/years/{y}/"><span class="card-title">{y}</span>'
        f'<span class="card-meta">{len(by_year[y])} model'
        f'{"s" if len(by_year[y]) != 1 else ""}</span></a>'
        for y in sorted(by_year, reverse=True))
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Clubs by Year</h1>
    <p class="lede">Release years covered by the archive, newest first.</p>
  </div>
  <div class="grid">{cards}</div>
</div>
"""
    listed = [{"url": f"/years/{y}/", "title": str(y)}
              for y in sorted(by_year, reverse=True)]
    page("/years/", title, desc, body, brands, [bc, item_list(listed, "Release years")])


def category_page(cat, ms, brands):
    label = CATEGORY_PAGE_LABEL.get(cat) or CATEGORY_LABEL.get(cat, cat)
    noun = CATEGORY_PAGE_NOUN.get(cat, "clubs")
    ms = sorted(ms, key=lambda m: (m.get("year_introduced") or 0, m["brand"]))
    by_type = defaultdict(list)
    for m in ms:
        by_type[m["club_type"]].append(m)
    types = ([t for t in CLUB_SECTION_ORDER if by_type[t]]
             + sorted(t for t in by_type if t not in CLUB_SECTION_ORDER))
    irons = by_type.get("irons", [])
    multi = len(types) > 1
    title = fit_title(label, " — Loft Charts & Specs", f" | {SITE_NAME}")
    span = loft_span(irons)
    # Lead with the loft figure — it is the number that distinguishes one
    # category from the next, and the reason someone clicks a category page.
    if not multi and irons:
        short = CATEGORY_SHORT.get(cat, label.replace(" Irons", "").lower())
        if span:
            head_part = f"{label}: {span} across {plural(len(ms), f'{short} iron')}. "
        else:
            head_part = (f"{label}: specifications for "
                         f"{plural(len(ms), f'{short} iron')}. ")
        desc = fit_desc(head_part, [
            "Compare loft, lie, length and swing weight for every club, from every "
            "major brand.",
            "Compare loft, lie and length for every club from every major brand.",
            "Compare loft, lie and length for every club.",
        ])
    else:
        types_txt = comma_list(CLUB_SECTION_LABEL.get(t, t).lower() for t in types)
        head_part = (f"{label}: specifications for {plural(len(ms), 'model')} "
                     f"across {types_txt}. " if multi else
                     f"{label}: specifications for {plural(len(ms), 'model')}. ")
        desc = fit_desc(head_part, [
            f"Compare lofts, specifications and model options for every line of "
            f"{noun} from the major brands.",
            "Compare lofts and specifications across every model, from every "
            "major brand.",
            "Compare lofts and specifications across every model.",
            "Full spec charts for every model.",
        ])
    nav, bc = crumbs([("Home", "/"), ("Categories", "/category/"), (label, None)])

    sections = []
    for t in types:
        tms = by_type[t]
        if t == "irons":
            rows = "".join(
                f'<tr><th scope="row"><a href="{m["url"]}">{esc(m["brand"])} {esc(m["model"])}</a></th>'
                f'<td>{esc(year_range(m))}</td>'
                f'<td>{num(seven_iron(m)["loft"]) if seven_iron(m) else "—"}</td>'
                f'<td>{num(seven_iron(m)["lie"]) if seven_iron(m) and seven_iron(m).get("lie") is not None else "—"}</td>'
                f'<td>{num(seven_iron(m)["length"]) if seven_iron(m) and seven_iron(m).get("length") is not None else "—"}</td></tr>'
                for m in tms)
            h2 = ("Irons — 7-iron specifications compared" if multi
                  else "7-iron specifications compared")
            sections.append(f"""<h2>{h2}</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <thead><tr><th scope="col">Model</th><th scope="col">Years</th><th scope="col">Loft (°)</th>
    <th scope="col">Lie (°)</th><th scope="col">Length (in)</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Figures shown are the 7-iron from each set (or the nearest middle
  iron where a 7-iron is not on file). Follow a model link for the full set chart.</p>""")
        else:
            h2 = CLUB_SECTION_LABEL.get(t, t) if multi else "Every model on file"
            sections.append(
                f"<h2>{esc(h2)}</h2>"
                f'<div class="grid">{"".join(model_card(m) for m in tms)}</div>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(label)}</h1>
    <p class="lede">{esc(CATEGORY_PAGE_BLURB.get(cat, ''))}</p>
  </div>
  {''.join(sections)}

  {guide_shop_block(f"Shop {noun}", f"{noun} golf",
                     f"Search new and used {noun} on eBay:")}
</div>
{guide_sticky_bar(f"Shop {noun}", f"{noun} golf")}
"""
    page(f"/category/{cat}/", title, desc, body, brands, [bc, item_list(ms, label)])


def categories_index(by_cat, brands, all_models):
    title = fit_title("Golf Club Categories — Blade, Players & Game Improvement",
                      f" | {SITE_NAME}")
    head_part = (f"Golf club categories compared: {plural(len(all_models), 'model')} "
                 f"across {plural(len(by_cat), 'category')}. ")
    desc = fit_desc(head_part, [
        "Blade, players and game improvement irons, tour and specialty wedges, "
        "flagship and lightweight driver and wood lines.",
        "Blade, players and game improvement irons, plus wedge, driver and "
        "wood categories.",
        "Iron, wedge, driver and wood categories compared.",
    ])
    nav, bc = crumbs([("Home", "/"), ("Categories", None)])
    order = ["blade", "players", "players-distance", "game-improvement",
             "super-game-improvement", "tour", "specialty", "flagship",
             "lightweight"]
    cats = [c for c in order if c in by_cat] + [c for c in by_cat if c not in order]
    cards = "".join(
        f'<a class="card" href="/category/{esc(c)}/">'
        f'<span class="card-title">{esc(CATEGORY_PAGE_LABEL.get(c, c))}</span>'
        f'<span class="card-meta">{plural(len(by_cat[c]), "model")}</span>'
        f'<span class="card-spec">{esc(CATEGORY_PAGE_BLURB.get(c, "")[:88])}…</span></a>'
        for c in cats)
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Club Categories</h1>
    <p class="lede">Clubs are grouped by design and intended player. The iron categories
    run from the most compact and least forgiving to the most forgiving; wedges, drivers
    and woods carry their own groupings.</p>
  </div>
  <div class="grid">{cards}</div>
</div>
"""
    listed = [{"url": f"/category/{c}/", "title": CATEGORY_PAGE_LABEL.get(c, c)}
              for c in cats]
    page("/category/", title, desc, body, brands, [bc, item_list(listed, "Club categories")])


# --------------------------------------------------------------------------
# compare pages
# --------------------------------------------------------------------------

TYPE_SUFFIX = re.compile(r"-(irons|driver|fairway-wood|hybrid|wedges|putter)$")


def compare_slug(a, b):
    ab = TYPE_SUFFIX.sub("", a["slug"])
    bb = TYPE_SUFFIX.sub("", b["slug"])
    # Iron compares own the bare namespace (those URLs are long since indexed);
    # wood families reuse iron line names (G430, Paradym, Stealth), so their
    # compare slugs carry the type to keep g430-vs-g440 irons, drivers,
    # fairways and hybrids apart.
    suffix = {"driver": "-drivers", "fairway_wood": "-fairway-woods",
              "hybrid": "-hybrids"}.get(a.get("club_type"), "")
    if a["brand_slug"] == b["brand_slug"]:
        return f"{a['brand_slug']}-{ab}-vs-{bb}{suffix}"
    return f"{a['brand_slug']}-{ab}-vs-{b['brand_slug']}-{bb}{suffix}"


def model_name_index(models):
    """club_type + name -> model, for resolving declared predecessor/successor.

    Keys carry the club type because driver families share names with iron
    lines (Ping sells both G440 irons and G440 drivers); a flat name index
    would resolve a driver's successor to the iron set and silently drop the
    comparison pair.
    """
    name_index = {}
    for m in models:
        t = m.get("club_type")
        name_index[f"{t}:{m['brand']} {m['model']}".lower()] = m
        name_index[f"{t}:{m['model']}".lower()] = m
    return name_index


# Every declared pair gets a page, identical specs included. Pairs with few
# differing cells were once dropped as thin content, but Google had already
# indexed those URLs and reported them as 404s; most pages carry a googlebot
# noindex anyway (see compare_indexable), and "the lofts are identical" is
# itself the answer people searching a comparison want.
def find_pairs(models, by_key):
    """Pair each model with its declared predecessor/successor when both are on file."""
    pairs = OrderedDict()
    name_index = model_name_index(models)

    def resolve(m, value):
        if not value:
            return None
        v = f"{m.get('club_type')}:{str(value).strip().lower()}"
        target = name_index.get(v)
        if target and target["key"] != m["key"]:
            return target
        return None

    for m in models:
        candidates = [resolve(m, m.get("predecessor")), resolve(m, m.get("successor"))]
        for r in (m.get("related_models") or []):
            candidates.append(by_key.get(r["slug"]))
        for other in candidates:
            if not other or other["key"] == m["key"]:
                continue
            if other["club_type"] != m["club_type"]:
                continue
            a, b = sorted([m, other], key=lambda x: (x.get("year_introduced") or 0, x["slug"]))
            pairs.setdefault((a["key"], b["key"]), (a, b))
    return list(pairs.values())


# --------------------------------------------------------------------------
# Which comparisons Google may index. Every declared pair still gets a page,
# since they carry internal-navigation value, but most are vintage or niche
# pairs nobody searches for. Only generation upgrades within the most-searched
# current lines, plus the curated popular list below, stay indexable; the rest
# get a googlebot-only noindex and are left out of the sitemap. When in doubt
# a pair stays out: widening this later is cheap, unwinding thin pages is not.
# --------------------------------------------------------------------------

INDEX_MIN_YEAR = 2016

# Model lines with real search demand, matched against the start of the
# model name. Only these brands' pages are ever indexed.
POPULAR_LINES = {
    "titleist": r"(T\d{3}S?|620 (CB|MB)|718 (AP1|AP2|AP3|CB|MB)|Vokey SM\d{1,2}|"
                r"GTS?\b|TSR\b|TSi\b)",
    "taylormade": r"(P7(MB|MC|CB)\b|P7[579]0\b|P760\b|Qi\b|Qi\d|Stealth\b|SIM2? Max|"
                  r"M[2-6]\b|MG\d\b|Hi-Toe)",
    "ping": r"(G4\d\d|G7\d0|i2\d0|i5\d\d|i59|Blueprint|S\d{3}\b|Glide)",
    "callaway": r"(Apex|Paradym|Rogue ST|Mavrik|Elyte|Quantum|Opus|JAWS|MD\d)\b",
    "mizuno": r"(JPX-9\d\d|JPX One\b|ST-MAX\b|Pro \d{3}\b|Pro [SMT]-\d+|MP-20)",
    "cobra": r"(KING (Forged )?TEC|LTDx|Aerojet|Darkspeed|DS-ADAPT|OPTM|KING F[789]\b|"
             r"KING Speedzone|KING Radspeed|Snakebite)",
    "srixon": r"(ZXi?\d|ZXi?\b|Z [579]85)",
    "cleveland": r"(Launcher XL|ZipCore XL|HALO XL|RTZ\b|RTX\b|CBX\d?\b)",
    "pxg": r"(Black Ops|Lightning)\b",
    "wilson": r"(Dynapwr)\b",
}

# The "which one" decisions people actually search, shown first on /compare/
# and always indexed. The build fails if one of these stops resolving.
POPULAR_COMPARES = [
    "titleist-t100-2025-vs-t150-2025",
    "titleist-t100-2023-vs-t150",
    "titleist-t150-2025-vs-t250",
    "titleist-t100-2023-vs-t100-2025",
    "titleist-t200-2023-vs-t350",
    "titleist-620-cb-vs-620-mb",
    "titleist-620-cb-vs-t100",
    "taylormade-p770-2025-vs-p790-2025",
    "taylormade-p770-2023-vs-p790-2023",
    "taylormade-p790-2023-vs-p790-2025",
    "taylormade-p7mb-2023-vs-p7mc-2023",
    "taylormade-p770-2025-vs-p7cb",
    "taylormade-stealth-vs-qi",
    "ping-g430-vs-g440",
    "ping-g425-vs-g430",
    "ping-i230-vs-g430",
    "ping-i230-vs-i240",
    "ping-i525-vs-i530",
    "ping-blueprint-s-vs-blueprint-t",
    "callaway-apex-ai200-vs-apex-ai300",
    "callaway-apex-ai200-vs-apex-ai150",
    "callaway-apex-cb-2024-vs-apex-pro-2024",
    "callaway-paradym-vs-paradym-x",
    "callaway-paradym-ai-smoke-vs-elyte",
    "mizuno-pro-243-vs-pro-245",
    "mizuno-jpx-925-forged-vs-jpx-925-hot-metal",
    "srixon-zx5-mkii-vs-zx7-mkii",
    "srixon-zxi5-vs-zxi7",
    "cobra-king-tec-2024-vs-king-tec-x-2024",
    # Wedges — the generation upgrades and cross-brand pairs people search.
    "titleist-vokey-sm10-vs-vokey-sm11",
    "cleveland-rtz-vs-rtz-2",
    "callaway-opus-sp-vs-opus-sp-plus",
    "cleveland-rtz-2-vs-titleist-vokey-sm11",
    "taylormade-mg5-vs-titleist-vokey-sm11",
    # Drivers — the upgrade decisions of the current and previous cycle.
    "taylormade-qi10-vs-qi35-drivers",
    "taylormade-qi35-vs-qi4d-drivers",
    "ping-g430-vs-g440-drivers",
    "ping-g425-vs-g430-drivers",
    "titleist-gt-vs-gts-drivers",
    "titleist-tsr-vs-gt-drivers",
    "callaway-elyte-vs-quantum-drivers",
    "callaway-ai-smoke-vs-elyte-drivers",
    "cobra-ds-adapt-vs-optm-drivers",
    "pxg-black-ops-vs-lightning-drivers",
    "srixon-zxi-vs-zxi-rkt-drivers",
]


def on_popular_line(m):
    pat = POPULAR_LINES.get(m["brand_slug"])
    return bool(pat and re.match(pat, m["model"], re.I))


def is_generation_step(a, b, names):
    """True when b is a's declared successor, or a is b's declared predecessor."""
    def res(v):
        if not v:
            return None
        return names.get(f"{a.get('club_type')}:{str(v).strip().lower()}")
    s, p = res(a.get("successor")), res(b.get("predecessor"))
    return bool((s and s["key"] == b["key"]) or (p and p["key"] == a["key"]))


def compare_indexable(slug, a, b, names):
    if slug in POPULAR_COMPARES:
        return True
    return (on_popular_line(a) and on_popular_line(b)
            and min(a["year_introduced"], b["year_introduced"]) >= INDEX_MIN_YEAR
            and is_generation_step(a, b, names))


# --------------------------------------------------------------------------
# compare page analysis: plain-language text generated from the spec data
# --------------------------------------------------------------------------

# Low number = less forgiving. Used to say which way a category gap runs.
CATEGORY_RANK = {"blade": 0, "players": 1, "players-distance": 2,
                 "game-improvement": 3, "super-game-improvement": 4}

CATEGORY_GOLFER = {
    "blade": "low single-digit handicaps who strike the ball consistently",
    "players": "roughly scratch to 10 handicaps",
    "players-distance": "roughly 5 to 15 handicaps who want extra distance from a compact head",
    "game-improvement": "roughly 10 to 25 handicaps",
    "super-game-improvement": "high handicaps, beginners and slower swing speeds",
}


def shared_ref_club(aspec, bspec):
    """The club both sets are compared on: the 7-iron, or the middle shared club."""
    common = [c for c in aspec if c in bspec
              and aspec[c].get("loft") is not None and bspec[c].get("loft") is not None]
    if "7" in common:
        return "7"
    common.sort(key=lambda c: (aspec[c]["loft"], club_sort_key(c)))
    return common[len(common) // 2] if common else None


def carry_yards(deg):
    """Rule of thumb: one degree of loft is worth 3-4 yards of carry."""
    lo, hi = round(deg * 3), round(deg * 4)
    if hi <= 1:
        return "a yard or so"
    if lo == hi:
        return f"about {lo} yards"
    return f"roughly {lo} to {hi} yards"


def build_traits(m):
    t = f"{m.get('construction') or ''} {m.get('material') or ''}".lower()
    # A forged face or face cup on a cast or hollow body says nothing about how
    # the body is made, so it does not count towards the build method.
    body = re.sub(r"forged[\w\s-]*?face( cup)?", "", t)
    forged, cast = "forged" in body, "cast" in body
    return {
        "known": bool(t.strip()),
        "method": ("forged and cast" if forged and cast else
                   "forged" if forged else "cast" if cast else None),
        "hollow": "hollow" in t,
        "tungsten": "tungsten" in t,
        "muscle": any(k in t for k in ("muscle", "blade")),
    }


def compare_analysis(a, b, label_a, label_b, aspec, bspec, generation=False):
    """(paragraphs, faq) for a compare page, every sentence driven by the data."""
    full_a = f"{a['brand']} {a['model']}"
    ref = shared_ref_club(aspec, bspec)
    shared = [c for c in aspec if c in bspec
              and aspec[c].get("loft") is not None and bspec[c].get("loft") is not None]
    # b minus a: positive means the b set is weaker lofted on that club.
    deltas = {c: bspec[c]["loft"] - aspec[c]["loft"] for c in shared}
    identical = bool(shared) and all(d == 0 for d in deltas.values())
    paras, faq = [], []

    # --- lofts --------------------------------------------------------------
    if ref:
        noun = club_noun(a, ref)
        la, lb = aspec[ref]["loft"], bspec[ref]["loft"]
        d = round(lb - la, 1)
        stronger, weaker = (label_b, label_a) if d < 0 else (label_a, label_b)
        if identical:
            same_lie = all(aspec[c].get("lie") == bspec[c].get("lie") for c in shared)
            same_len = all(aspec[c].get("length") == bspec[c].get("length") for c in shared)
            extra = ""
            if same_lie and same_len:
                extra = (" Lie angles and lengths match as well, so any fitting "
                         "adjustment made to one set would carry straight over to the other.")
            paras.append(
                f"Every club the two sets share has exactly the same loft, starting with a "
                f"{num(la)}° {noun}. On paper there is no distance or trajectory difference: "
                f"with the same swing, a {noun} from either set should launch and carry about "
                f"the same. The real differences are in how the heads are built, how they "
                f"look at address and how they feel at impact, none of which a spec table "
                f"can show.{extra}")
        else:
            text = f"At the {noun}, the {label_a} is {num(la)}° and the {label_b} is {num(lb)}°"
            if d:
                text += (f", a {num(abs(d))}° gap. Each degree of loft is worth roughly 3 "
                         f"to 4 yards of carry at the same swing speed, so the {stronger} "
                         f"should carry {carry_yards(abs(d))} further with that club, on a "
                         f"slightly lower, shallower flight than the {weaker}.")
            else:
                text += (", identical at the club most golfers compare on, although other "
                         "clubs in the sets differ.")
            if len(shared) > 1:
                avg = sum(deltas.values()) / len(deltas)
                big_c = max(shared, key=lambda c: (abs(deltas[c]), -club_sort_key(c)[0]))
                if abs(avg) >= 0.25:
                    way = "weaker" if avg > 0 else "stronger"
                    text += (f" Across the {len(shared)} clubs both sets share, the "
                             f"{label_b} averages {num(round(abs(avg), 1))}° {way}")
                else:
                    text += (f" Across the {len(shared)} clubs both sets share, the "
                             f"differences roughly cancel out")
                if abs(deltas[big_c]) > 0:
                    text += (f", with the largest gap at the {club_noun(a, big_c)} "
                             f"({num(aspec[big_c]['loft'])}° vs {num(bspec[big_c]['loft'])}°).")
                else:
                    text += "."
            if "PW" in shared and deltas["PW"]:
                pw = min(aspec["PW"]["loft"], bspec["PW"]["loft"])
                text += (f" The pitching wedges are {num(aspec['PW']['loft'])}° and "
                         f"{num(bspec['PW']['loft'])}°; the stronger one leaves a "
                         f"{num(round(abs(50 - pw), 1))}° jump to a 50° gap wedge, which "
                         f"matters when planning wedge gapping.")
            paras.append(text)

        lie_a, lie_b = aspec[ref].get("lie"), bspec[ref].get("lie")
        len_a, len_b = aspec[ref].get("length"), bspec[ref].get("length")
        bits = []
        if lie_a is not None and lie_b is not None and lie_a != lie_b:
            flatter = label_a if lie_a < lie_b else label_b
            bits.append(f"the {flatter} {noun} sits {num(round(abs(lie_a - lie_b), 1))}° "
                        f"flatter ({num(lie_a)}° vs {num(lie_b)}°), which nudges start "
                        f"direction slightly right for a right-hander")
        if len_a is not None and len_b is not None and len_a != len_b:
            longer = label_a if len_a > len_b else label_b
            bits.append(f"the {longer} {noun} is {num(round(abs(len_a - len_b), 2))} "
                        f"inches longer ({num(len_a)}\" vs {num(len_b)}\")")
        if bits and not identical:
            paras[-1] += " Beyond loft, " + "; ".join(bits) + "."

    # --- set make-up ----------------------------------------------------------
    if a["specs"] and b["specs"]:
        span_a = (a["specs"][0]["club"], a["specs"][-1]["club"], len(a["specs"]))
        span_b = (b["specs"][0]["club"], b["specs"][-1]["club"], len(b["specs"]))
        if span_a != span_b:
            paras.append(
                f"The sets are built differently: the {label_a} runs "
                f"{club_noun(a, span_a[0])} to {club_noun(a, span_a[1])} "
                f"({plural(span_a[2], 'club')}), the {label_b} "
                f"{club_noun(b, span_b[0])} to {club_noun(b, span_b[1])} "
                f"({plural(span_b[2], 'club')}).")

    # --- category -------------------------------------------------------------
    ca, cb = a.get("category"), b.get("category")
    ra, rb = CATEGORY_RANK.get(ca), CATEGORY_RANK.get(cb)
    if ra is not None and rb is not None:
        sa, sb = CATEGORY_SHORT[ca], CATEGORY_SHORT[cb]
        if ra == rb:
            paras.append(
                f"Both are {sa} irons, built for {CATEGORY_GOLFER[ca]}. "
                f"{CATEGORY_BLURB[ca]} Because they target the same golfer, the decision "
                f"comes down to the specific loft, feel and shaping differences rather "
                f"than who the sets are made for.")
        else:
            easy, hard = (label_a, label_b) if ra > rb else (label_b, label_a)
            ce, ch = (ca, cb) if ra > rb else (cb, ca)
            steps = abs(ra - rb)
            gap = "one step" if steps == 1 else f"{steps} steps"
            paras.append(
                f"The {label_a} is a {sa} iron and the {label_b} a {sb} iron, so they sit "
                f"{gap} apart on the forgiveness scale. The {easy} is the more forgiving "
                f"design, with a wider sole, more offset and more perimeter weighting "
                f"for {CATEGORY_GOLFER[ce]}. The {hard} trades some of that for a more "
                f"compact head, thinner topline and more control over flight and shape, "
                f"which suits {CATEGORY_GOLFER[ch]}.")

    # --- construction -----------------------------------------------------------
    ta, tb = build_traits(a), build_traits(b)
    cons = []
    if ta["known"] and tb["known"]:
        ca_txt, cb_txt = a.get("construction"), b.get("construction")
        if ca_txt and cb_txt:
            if ca_txt.lower() == cb_txt.lower():
                cons.append(f"Both heads are listed as {ca_txt}.")
            else:
                cons.append(f"The {label_a} is listed as {ca_txt} and the {label_b} "
                            f"as {cb_txt}.")
        if ta["method"] != tb["method"] and {ta["method"], tb["method"]} == {"forged", "cast"}:
            fg = label_a if ta["method"] == "forged" else label_b
            cs = label_b if fg == label_a else label_a
            cons.append(f"Forging, as in the {fg}, is generally credited with a softer "
                        f"feel; casting, as in the {cs}, allows more complex cavity and "
                        f"weighting shapes, which is why it dominates forgiving irons.")
        if ta["hollow"] != tb["hollow"]:
            hw = label_a if ta["hollow"] else label_b
            sd = label_b if hw == label_a else label_a
            cons.append(f"The {hw}'s hollow body lets the face flex more and moves mass "
                        f"low and outward, usually giving higher launch and more ball speed "
                        f"on off-centre strikes than the {sd}, at some cost in feel.")
        elif ta["hollow"] and tb["hollow"]:
            cons.append("Both use hollow-body heads, so both trade a little feel for face "
                        "flex and launch help.")
        if ta["tungsten"] != tb["tungsten"]:
            tw = label_a if ta["tungsten"] else label_b
            cons.append(f"The {tw} adds tungsten weighting, which lowers the centre of "
                        f"gravity and raises stability on mis-hits, helping the long irons "
                        f"launch.")
        elif ta["tungsten"] and tb["tungsten"]:
            cons.append("Both use tungsten weighting to lower the centre of gravity and "
                        "steady the head on off-centre strikes.")
        if ta["muscle"] != tb["muscle"]:
            mb = label_a if ta["muscle"] else label_b
            cons.append(f"The {mb}'s muscle-back shape keeps mass directly behind the "
                        f"strike for feedback and control, where a cavity spreads it to "
                        f"the perimeter for forgiveness.")
        if len(cons) <= 1:
            cons.append("With the build method this similar, differences in feel come "
                        "down to head size, sole width, topline and offset rather than "
                        "how the heads are made.")
    elif identical:
        cons.append("Neither listing gives full construction details, so compare head "
                    "size, sole width and offset in person; that is where these sets differ.")
    if cons:
        paras.append(" ".join(cons))

    # --- year gap ---------------------------------------------------------------
    ya, yb = a.get("year_introduced"), b.get("year_introduced")
    if ya and yb:
        gap = abs(yb - ya)
        loft_move = ""
        if ref and aspec[ref]["loft"] != bspec[ref]["loft"]:
            loft_move = (f" Here the {club_noun(a, ref)} loft moved from "
                         f"{num(aspec[ref]['loft'])}° to {num(bspec[ref]['loft'])}°.")
        if gap == 0:
            if a["brand"] == b["brand"]:
                paras.append(f"Both sets were introduced in {ya}, so this is a choice "
                             f"between two models from the same lineup rather than an "
                             f"upgrade: {a['brand']} designed them to sit side by side for "
                             f"different players.")
            else:
                paras.append(f"Both sets were introduced in {ya}, so they are direct "
                             f"rivals from the same generation of iron design.")
        elif gap <= 3 and not generation:
            if a["brand"] == b["brand"]:
                paras.append(f"The {label_b} came out {plural(gap, 'year')} after the "
                             f"{label_a}, but it is a different line rather than a direct "
                             f"replacement, so the two were designed for different golfers "
                             f"as well as different seasons.")
            else:
                paras.append(f"The two sets launched within {plural(gap, 'year')} of each "
                             f"other ({ya} and {yb}), so they come from the same era of iron "
                             f"design.{loft_move}")
        elif gap <= 3:
            paras.append(f"The {label_b} arrived {plural(gap, 'year')} after the {label_a}, "
                         f"a typical one-generation refresh. Changes over that span are "
                         f"usually incremental: refined face thickness, revised weighting, "
                         f"updated looks and small loft tweaks rather than a new concept."
                         f"{loft_move}")
        else:
            paras.append(f"There are {gap} years between these sets ({ya} and {yb}), more "
                         f"than one design generation. Over that time irons moved toward "
                         f"stronger lofts, thinner and faster faces, hollow and "
                         f"multi-material heads and wider use of tungsten, so the newer set "
                         f"is not simply a better version of the older one: it may launch "
                         f"and spin quite differently.{loft_move}")

    # --- FAQ --------------------------------------------------------------------
    if ref:
        noun = club_noun(a, ref)
        la, lb = aspec[ref]["loft"], bspec[ref]["loft"]
        d = round(lb - la, 1)
        if identical:
            ans = (f"No. Both have a {num(la)}° {noun} and the same loft on every club "
                   f"they share, so neither is stronger lofted. The difference is in "
                   f"construction and feel.")
        elif d > 0:
            ans = (f"Yes. The {full_a} {noun} is {num(la)}° against {num(lb)}° for the "
                   f"{label_b}, {num(abs(d))}° stronger, which is worth "
                   f"{carry_yards(abs(d))} of extra carry with the same swing.")
        elif d < 0:
            ans = (f"No. The {label_b} is the stronger-lofted set: its {noun} is "
                   f"{num(lb)}° against {num(la)}° for the {full_a}, {num(abs(d))}° "
                   f"stronger and worth {carry_yards(abs(d))} of extra carry.")
        else:
            ans = (f"Not at the {noun}, where both are {num(la)}°. Other clubs in the "
                   f"sets differ, so compare the full table above.")
        faq.append((f"Is the {full_a} stronger lofted than the {label_b}?", ans))

        if identical:
            ans = (f"There is none. Every club both sets include has the same loft, "
                   f"including the {num(la)}° {noun}.")
        else:
            ans = (f"At the {noun} the difference is {num(abs(d))}° ({num(la)}° vs "
                   f"{num(lb)}°).")
            nz = [c for c in shared if deltas[c]]
            if nz:
                big_c = max(nz, key=lambda c: (abs(deltas[c]), -club_sort_key(c)[0]))
                ans += (f" The largest gap on a shared club is "
                        f"{num(round(abs(deltas[big_c]), 1))}° at the "
                        f"{club_noun(a, big_c)}, and "
                        + (f"all {len(shared)}" if len(nz) == len(shared)
                           else f"{len(nz)} of the {len(shared)}")
                        + " shared clubs differ.")
        faq.append((f"What is the loft difference between the {full_a} and {label_b}?",
                    ans))

    if ra is not None and rb is not None:
        if ra == rb:
            faq.append((f"Are the {full_a} and {label_b} aimed at the same golfer?",
                        f"Yes. Both are {CATEGORY_SHORT[ca]} irons, built for "
                        f"{CATEGORY_GOLFER[ca]}. Choose on feel, looks and gapping, "
                        f"ideally after hitting both."))
        else:
            easy, ce = (full_a, ca) if ra > rb else (label_b, cb)
            hard, ch = (label_b, cb) if ra > rb else (full_a, ca)
            faq.append((f"Which is better for higher handicap golfers, the {full_a} or "
                        f"the {label_b}?",
                        f"The {easy}. As a {CATEGORY_SHORT[ce]} iron it is the more "
                        f"forgiving design, suited to {CATEGORY_GOLFER[ce]}. The {hard} "
                        f"is a {CATEGORY_SHORT[ch]} iron, better suited to "
                        f"{CATEGORY_GOLFER[ch]}."))

    if ref:
        lie_a, lie_b = aspec[ref].get("lie"), bspec[ref].get("lie")
        len_a, len_b = aspec[ref].get("length"), bspec[ref].get("length")
        if None not in (lie_a, lie_b, len_a, len_b):
            noun = club_noun(a, ref)
            if lie_a == lie_b and len_a == len_b:
                ans = (f"At the {noun}, yes: both are {num(lie_a)}° lie and "
                       f"{num(len_a)} inches long.")
            else:
                ans = (f"Not exactly. At the {noun} the {full_a} is {num(lie_a)}° lie and "
                       f"{num(len_a)} inches, the {label_b} {num(lie_b)}° and "
                       f"{num(len_b)} inches. Both can be bent or built to your own fit.")
            faq.append((f"Do the {full_a} and {label_b} have the same lie and length?",
                        ans))

    return paras, faq


# --------------------------------------------------------------------------
# wedge compare pages
#
# Iron comparisons align on club label and ask "which is stronger lofted?".
# Wedge models share most of their lofts by construction — both offer a 56°,
# both offer a 60° — so the questions that matter are coverage questions:
# which degrees each is sold in, and how many bounce/grind options each offers
# at the degrees they share.
# --------------------------------------------------------------------------

def _wedge_by_loft(m):
    by = defaultdict(list)
    for r in m["specs"]:
        if r.get("loft") is not None:
            by[r["loft"]].append(r)
    return by


def _wedge_opts_cell(opts):
    """'8° F, 10° S, 12° D' for the options at one loft."""
    return ", ".join(
        f"{num(r['bounce'])}°{' ' + esc(r['grind']) if r.get('grind') else ''}"
        for r in sorted(opts, key=lambda r: (r.get("bounce") or 0,
                                             str(r.get("grind") or ""))))


def wedge_compare_table(a, b, label_a, label_b):
    """Side-by-side wedge comparison: bounce/grind options at each loft."""
    a_by, b_by = _wedge_by_loft(a), _wedge_by_loft(b)
    all_lofts = sorted(set(a_by) | set(b_by))

    rows = []
    for loft in all_lofts:
        a_opts, b_opts = a_by.get(loft, []), b_by.get(loft, [])
        diff = ' class="diff"' if len(a_opts) != len(b_opts) else ""
        a_cell = _wedge_opts_cell(a_opts) or '<span class="na">not offered</span>'
        b_cell = _wedge_opts_cell(b_opts) or '<span class="na">not offered</span>'
        rows.append(
            f'<tr><th scope="row">{num(loft)}°</th>'
            f'<td>{a_cell}</td><td{diff}>{len(a_opts) or "—"}</td>'
            f'<td>{b_cell}</td><td{diff}>{len(b_opts) or "—"}</td></tr>')

    return f"""<div class="table-scroll data-table-zone"><table class="specs">
<caption>Bounce and grind options at each loft: {esc(label_a)} vs {esc(label_b)}.</caption>
<thead><tr>
  <th scope="col">Loft</th>
  <th scope="col">{esc(label_a)} bounce / grind</th>
  <th scope="col">#</th>
  <th scope="col">{esc(label_b)} bounce / grind</th>
  <th scope="col">#</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>"""


def wedge_compare_analysis(a, b, label_a, label_b, generation=False):
    """(paragraphs, faq) for a wedge compare page, driven by the option matrices."""
    full_a = f"{a['brand']} {a['model']}"
    a_by, b_by = _wedge_by_loft(a), _wedge_by_loft(b)
    a_lofts, b_lofts = sorted(a_by), sorted(b_by)
    shared = sorted(set(a_by) & set(b_by))
    a_combos, b_combos = len(a["specs"]), len(b["specs"])
    a_grinds = [g["code"] for g in (a.get("grinds") or []) if g.get("code")]
    b_grinds = [g["code"] for g in (b.get("grinds") or []) if g.get("code")]
    paras, faq = [], []

    # --- total selection ------------------------------------------------------
    if a_combos == b_combos:
        text = (f"Both models offer {a_combos} loft/bounce/grind combinations, so "
                f"neither wins on raw selection.")
    else:
        more, less = (label_a, label_b) if a_combos > b_combos else (label_b, label_a)
        hi, lo = max(a_combos, b_combos), min(a_combos, b_combos)
        text = (f"The {more} offers the wider selection: {hi} loft/bounce/grind "
                f"combinations against {lo} for the {less}.")
    if not a_grinds and not b_grinds:
        pass  # neither model names its grinds; nothing to compare
    elif len(a_grinds) == len(b_grinds):
        text += (f" Each is ground {plural(len(a_grinds), 'way')} — "
                 f"{comma_list(a_grinds)} for the {label_a}, "
                 f"{comma_list(b_grinds)} for the {label_b}.")
    else:
        gm, gl = (label_a, label_b) if len(a_grinds) > len(b_grinds) else (label_b, label_a)
        text += (f" The {gm} also has the deeper grind catalogue: "
                 f"{max(len(a_grinds), len(b_grinds))} sole grinds against "
                 f"{min(len(a_grinds), len(b_grinds))}.")
    paras.append(text)

    # --- loft coverage --------------------------------------------------------
    if a_lofts and b_lofts:
        a_span = (a_lofts[0], a_lofts[-1])
        b_span = (b_lofts[0], b_lofts[-1])
        only_a = sorted(set(a_by) - set(b_by))
        only_b = sorted(set(b_by) - set(a_by))
        if not only_a and not only_b:
            text = (f"Loft coverage is identical: both run {num(a_span[0])}° to "
                    f"{num(a_span[1])}° and are sold at the same "
                    f"{plural(len(shared), 'degree')}.")
        else:
            text = (f"The {label_a} is sold from {num(a_span[0])}° to {num(a_span[1])}°, "
                    f"the {label_b} from {num(b_span[0])}° to {num(b_span[1])}°.")
            if only_a:
                text += (f" Only the {label_a} comes in "
                         f"{comma_list(f'{num(l)}°' for l in only_a)}.")
            if only_b:
                text += (f" Only the {label_b} comes in "
                         f"{comma_list(f'{num(l)}°' for l in only_b)}.")
        paras.append(text)

    # --- options at the scoring lofts -----------------------------------------
    key_lofts = [l for l in (56.0, 58.0, 60.0) if l in a_by or l in b_by]
    if key_lofts:
        bits = []
        for l in key_lofts:
            na, nb = len(a_by.get(l, [])), len(b_by.get(l, []))
            if na == nb:
                bits.append(f"at {num(l)}° both offer {plural(na, 'option')}")
            else:
                lead = label_a if na > nb else label_b
                bits.append(f"at {num(l)}° the {lead} offers {max(na, nb)} "
                            f"options to {min(na, nb)}")
        paras.append(
            "The scoring lofts are where bounce and grind choice matters most: "
            + "; ".join(bits) +
            ". More options at a degree means more ways to match the sole to "
            "your turf and swing, which is what a wedge fitting actually selects.")

    # --- generation / era -----------------------------------------------------
    ya, yb = a.get("year_introduced"), b.get("year_introduced")
    if ya and yb:
        gap = abs(yb - ya)
        if gap == 0:
            paras.append(f"Both lines were introduced in {ya}, so this is a choice "
                         f"between two current designs rather than an upgrade.")
        elif generation:
            paras.append(f"The {label_b} arrived {plural(gap, 'year')} after the "
                         f"{label_a} as its replacement. Wedge generations usually "
                         f"carry over the core loft ladder and adjust the grind "
                         f"catalogue, groove spec and finishes, so the older model "
                         f"is the value buy while stock lasts — the trade-off is "
                         f"the newer grooves, which matter more the more you play.")
        else:
            paras.append(f"The two lines launched {plural(gap, 'year')} apart "
                         f"({ya} and {yb}), so they compete head-to-head rather "
                         f"than one replacing the other.")

    # --- FAQ ------------------------------------------------------------------
    faq.append((f"Which offers more options, the {full_a} or the {label_b}?",
                (f"Both offer {a_combos} loft, bounce and grind combinations."
                 if a_combos == b_combos else
                 f"The {full_a if a_combos > b_combos else label_b} does: "
                 f"{max(a_combos, b_combos)} loft, bounce and grind combinations "
                 f"against {min(a_combos, b_combos)} for the "
                 f"{label_b if a_combos > b_combos else full_a}.")))
    if a_lofts and b_lofts:
        faq.append((f"What lofts do the {full_a} and {label_b} come in?",
                    f"The {full_a} is sold from {num(a_lofts[0])} to "
                    f"{num(a_lofts[-1])} degrees and the {label_b} from "
                    f"{num(b_lofts[0])} to {num(b_lofts[-1])} degrees. "
                    + (f"They share {plural(len(shared), 'loft')}."
                       if shared else "They share no loft.")))
    if 56.0 in a_by and 56.0 in b_by:
        faq.append((f"Which has more 56 degree options, the {full_a} or the {label_b}?",
                    (f"Both offer {plural(len(a_by[56.0]), 'bounce/grind option')} "
                     f"at 56 degrees."
                     if len(a_by[56.0]) == len(b_by[56.0]) else
                     f"The {full_a if len(a_by[56.0]) > len(b_by[56.0]) else label_b}: "
                     f"{max(len(a_by[56.0]), len(b_by[56.0]))} bounce/grind options "
                     f"at 56 degrees against "
                     f"{min(len(a_by[56.0]), len(b_by[56.0]))}.")))

    return paras, faq


def wedge_compare_page(a, b, brands, indexed=False, generation=False):
    """Compare page for two wedge models: option matrices side by side."""
    slug = compare_slug(a, b)
    same_brand = a["brand"] == b["brand"]
    label_a = a["model"] if same_brand else f"{a['brand']} {a['model']}"
    label_b = b["model"] if same_brand else f"{b['brand']} {b['model']}"
    core = f"{a['brand']} {a['model']} vs {label_b}"
    if len(core) > TITLE_MAX:
        core = f"{a['model']} vs {b['model']}"
    if len(core) > TITLE_MAX:
        core = core[:TITLE_MAX - 1] + "…"
    title = fit_title(core, " Wedges — Compared", f" | {SITE_NAME}")

    a_combos, b_combos = len(a["specs"]), len(b["specs"])
    a_lofts, b_lofts = wedge_lofts(a), wedge_lofts(b)
    shared = sorted(set(a_lofts) & set(b_lofts))
    head_part = (f"{a['brand']} {a['model']} vs {label_b} wedges: "
                 f"{a_combos} loft/bounce/grind options vs {b_combos}. ")
    desc = fit_desc(head_part, [
        f"Compare bounce and grind availability at every loft, "
        f"{plural(len(shared), 'shared degree')} side by side.",
        f"Compare bounce and grind availability at every shared loft.",
        "Compare bounce, grind availability and loft range.",
        "Full wedge spec comparison.",
    ])
    url = f"/compare/{slug}/"
    nav, bc = crumbs([("Home", "/"), ("Compare", "/compare/"),
                      (f"{a['model']} vs {b['model']}", None)])

    table = wedge_compare_table(a, b, label_a, label_b)
    chart = wedge_compare_chart(a, b, label_a, label_b)
    overlay = (f'<h2>Options per loft</h2><div class="figs figs-one">{chart}</div>'
               if chart else "")
    paras, faq = wedge_compare_analysis(a, b, label_a, label_b, generation)
    analysis = "\n  ".join(f"<p>{esc(p)}</p>" for p in paras)
    faq_html, faq_ld = faq_block(faq) if faq else ("", None)

    # verdict driven by the matrices
    if generation:
        verdict = (f"The {label_b} is the newer generation, so it carries the current "
                   f"groove spec and the fuller retail availability; the {label_a} is "
                   f"the value buy while closeout and used stock lasts. The option "
                   f"chart above is the tiebreaker — if the exact loft, bounce and "
                   f"grind you play is only in one of them, that decides it.")
    elif a_combos != b_combos:
        more = label_a if a_combos > b_combos else label_b
        verdict = (f"Neither is the better wedge outright — both are current tour-style "
                   f"designs. The {more} offers the wider option matrix, which matters "
                   f"if you want an unusual bounce or grind at your loft; otherwise "
                   f"choose on feel, finish and price at the combination you actually "
                   f"play.")
    else:
        verdict = (f"The two lines offer the same number of combinations, so the choice "
                   f"comes down to the specific bounce and grind characters, feel and "
                   f"price rather than selection.")

    def col_card(m):
        c_lofts = wedge_lofts(m)
        span = (f"{num(c_lofts[0])}°–{num(c_lofts[-1])}°" if c_lofts else "")
        return (f'<a class="card" href="{m["url"]}">'
                f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
                f'<span class="card-meta">{year_range(m)} · '
                f'{esc(category_label(m))}</span>'
                f'<span class="card-spec">{span} · '
                f'{plural(len(m["specs"]), "option")}</span></a>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(a['brand'])} {esc(a['model'])} vs {esc(b['brand'])} {esc(b['model'])} Wedges</h1>
    <p class="lede">Side-by-side factory option matrices. Lofts where the two lines offer a
    different number of options are highlighted.</p>
  </div>
  <div class="cmp-cols">{col_card(a)}{col_card(b)}</div>

  <h2>Options at each loft</h2>
  {table}
  <p class="table-note">Each cell lists the bounce/grind combinations sold at that loft,
  factory standard. Highlighted counts differ between the two lines.</p>

  {overlay}

  <h2>What the differences mean</h2>
  {analysis}

  <h2>Which should you choose?</h2>
  <p>{esc(verdict)}</p>
  <p>Both option charts are reproduced in full on their own pages:
  <a href="{a['url']}">{esc(a['brand'])} {esc(a['model'])} specs</a> and
  <a href="{b['url']}">{esc(b['brand'])} {esc(b['model'])} specs</a>.</p>
  {faq_html}

  {compare_shop_block(a, b)}
</div>
{compare_sticky_bar(a, b)}
"""
    page(url, title, desc, body, brands, [bc] + ([faq_ld] if faq_ld else []),
         googlebot_noindex=not indexed)
    return slug


def _driver_by_loft(m):
    """loft -> [variant short names sold at that loft], in catalogue order."""
    by = OrderedDict()
    for name, rows in driver_rows_by_variant(m).items():
        for r in rows:
            if r.get("loft") is not None:
                by.setdefault(r["loft"], []).append(variant_short(m, name))
    return by


def driver_compare_table(a, b, label_a, label_b):
    """Side-by-side driver comparison: which heads offer each stock loft."""
    a_by, b_by = _driver_by_loft(a), _driver_by_loft(b)
    all_lofts = sorted(set(a_by) | set(b_by))

    rows = []
    for loft in all_lofts:
        a_heads, b_heads = a_by.get(loft, []), b_by.get(loft, [])
        diff = ' class="diff"' if len(a_heads) != len(b_heads) else ""
        a_cell = ", ".join(esc(h) for h in a_heads) or '<span class="na">not offered</span>'
        b_cell = ", ".join(esc(h) for h in b_heads) or '<span class="na">not offered</span>'
        rows.append(
            f'<tr><th scope="row">{num(loft)}°</th>'
            f'<td>{a_cell}</td><td{diff}>{len(a_heads) or "—"}</td>'
            f'<td>{b_cell}</td><td{diff}>{len(b_heads) or "—"}</td></tr>')

    return f"""<div class="table-scroll data-table-zone"><table class="specs">
<caption>Heads offered at each stock loft: {esc(label_a)} vs {esc(label_b)}.</caption>
<thead><tr>
  <th scope="col">Loft</th>
  <th scope="col">{esc(label_a)} heads</th>
  <th scope="col">#</th>
  <th scope="col">{esc(label_b)} heads</th>
  <th scope="col">#</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>"""


def _hosel_phrase(m):
    h = m.get("hosel")
    if not h:
        return None
    bits = [b for b in (h.get("system"),
                        h.get("loft_range") and f"{h['loft_range']} of loft",
                        h.get("positions") and plural(h["positions"], "setting"))
            if b]
    return ", ".join(str(b) for b in bits)


def driver_compare_analysis(a, b, label_a, label_b, generation=False):
    """(paragraphs, faq) for a driver compare page, driven by the two families."""
    full_a = f"{a['brand']} {a['model']}"
    a_by, b_by = _driver_by_loft(a), _driver_by_loft(b)
    a_lofts, b_lofts = sorted(a_by), sorted(b_by)
    shared = sorted(set(a_by) & set(b_by))
    a_heads = [variant_short(a, v.get("name")) for v in (a.get("variants") or [])]
    b_heads = [variant_short(b, v.get("name")) for v in (b.get("variants") or [])]
    paras, faq = [], []

    # --- head lineups -----------------------------------------------------
    if len(a_heads) == len(b_heads):
        text = (f"Both families are sold in {plural(len(a_heads), 'head')} — "
                f"{comma_list(a_heads)} for the {label_a}, "
                f"{comma_list(b_heads)} for the {label_b}.")
    else:
        more, less = ((label_a, label_b) if len(a_heads) > len(b_heads)
                      else (label_b, label_a))
        text = (f"The {more} family is the broader line: "
                f"{max(len(a_heads), len(b_heads))} heads against "
                f"{min(len(a_heads), len(b_heads))} — "
                f"{comma_list(a_heads)} for the {label_a}, "
                f"{comma_list(b_heads)} for the {label_b}.")
    paras.append(text)

    # --- loft coverage ----------------------------------------------------
    if a_lofts and b_lofts:
        only_a = sorted(set(a_by) - set(b_by))
        only_b = sorted(set(b_by) - set(a_by))
        if not only_a and not only_b:
            text = (f"Stock loft coverage is identical: both run "
                    f"{num(a_lofts[0])}° to {num(a_lofts[-1])}° across the same "
                    f"{plural(len(shared), 'stock loft')}.")
        else:
            text = (f"The {label_a} is sold from {num(a_lofts[0])}° to "
                    f"{num(a_lofts[-1])}°, the {label_b} from {num(b_lofts[0])}° "
                    f"to {num(b_lofts[-1])}°.")
            if only_a:
                text += (f" Only the {label_a} has a stock "
                         f"{comma_list(f'{num(l)}°' for l in only_a)} option.")
            if only_b:
                text += (f" Only the {label_b} has a stock "
                         f"{comma_list(f'{num(l)}°' for l in only_b)} option.")
        paras.append(text)

    # --- hosel adjustability ------------------------------------------------
    ha, hb = _hosel_phrase(a), _hosel_phrase(b)
    if ha and hb:
        if (a.get("hosel") or {}).get("system") == (b.get("hosel") or {}).get("system"):
            paras.append(f"Adjustability is a wash: both use the same hosel "
                         f"system ({ha}), so a given head reaches the same "
                         f"effective loft window in either generation.")
        else:
            paras.append(f"The hosels differ: the {label_a} uses {ha}; the "
                         f"{label_b} uses {hb}. The full setting-by-setting "
                         f"charts are on each model's own page.")
    elif ha or hb:
        adj, fixed = (label_a, label_b) if ha else (label_b, label_a)
        paras.append(f"Only the {adj} has an adjustable hosel ({ha or hb}); "
                     f"the {fixed} plays at its stamped loft.")

    # --- generation / era ---------------------------------------------------
    ya, yb = a.get("year_introduced"), b.get("year_introduced")
    if ya and yb:
        gap = abs(yb - ya)
        if gap == 0:
            paras.append(f"Both lines were introduced in {ya}, so this is a "
                         f"choice between two current designs rather than an "
                         f"upgrade.")
        elif generation:
            paras.append(f"The {label_b} arrived {plural(gap, 'year')} after "
                         f"the {label_a} as its replacement. "
                         f"{WOOD_NOUN[a['club_type']].capitalize()} generations "
                         f"usually carry over the loft ladder and move the "
                         f"technology — face design, adjustability, head "
                         f"options — so the older family is the value buy on "
                         f"the used market while the newer one holds retail "
                         f"price.")
        else:
            paras.append(f"The two lines launched {plural(gap, 'year')} apart "
                         f"({ya} and {yb}), so they compete head-to-head rather "
                         f"than one replacing the other.")

    # --- FAQ ------------------------------------------------------------------
    nounp = f"{WOOD_NOUN[a['club_type']]}s"
    if a_lofts and b_lofts:
        faq.append((f"What lofts do the {full_a} and {label_b} {nounp} come in?",
                    f"The {full_a} is sold in stock lofts from {num(a_lofts[0])} "
                    f"to {num(a_lofts[-1])} degrees and the {label_b} from "
                    f"{num(b_lofts[0])} to {num(b_lofts[-1])} degrees. "
                    + (f"They share {plural(len(shared), 'stock loft')}."
                       if shared else "They share no stock loft.")))
    faq.append((f"Which has more head options, the {full_a} or the {label_b}?",
                (f"Both families are sold in {plural(len(a_heads), 'head')}."
                 if len(a_heads) == len(b_heads) else
                 f"The {full_a if len(a_heads) > len(b_heads) else label_b}: "
                 f"{max(len(a_heads), len(b_heads))} head variants against "
                 f"{min(len(a_heads), len(b_heads))}.")))
    if ha and hb:
        faq.append((f"Are the {full_a} and {label_b} {nounp} adjustable?",
                    f"Yes — the {full_a} uses {ha}, and the {label_b} uses "
                    f"{hb}. Each model page carries the full "
                    f"setting-by-setting adjustment chart."))

    return paras, faq


def driver_compare_page(a, b, brands, indexed=False, generation=False):
    """Compare page for two wood families: head lineups and loft coverage."""
    slug = compare_slug(a, b)
    type_word = WOOD_PLURAL[a["club_type"]]
    nounp = f"{WOOD_NOUN[a['club_type']]}s"
    same_brand = a["brand"] == b["brand"]
    label_a = a["model"] if same_brand else f"{a['brand']} {a['model']}"
    label_b = b["model"] if same_brand else f"{b['brand']} {b['model']}"
    core = f"{a['brand']} {a['model']} vs {label_b} {type_word}"
    if len(core) > TITLE_MAX:
        core = f"{a['model']} vs {b['model']} {type_word}"
    if len(core) > TITLE_MAX:
        core = core[:TITLE_MAX - 1] + "…"
    title = fit_title(core, " — Compared", f" | {SITE_NAME}")

    a_lofts, b_lofts = driver_lofts(a), driver_lofts(b)
    n_a = len(a.get("variants") or [])
    n_b = len(b.get("variants") or [])
    head_part = (f"{a['brand']} {a['model']} vs {label_b} {nounp}: "
                 f"{n_a} head variants vs {n_b}. ")
    desc = fit_desc(head_part, [
        "Compare stock lofts head by head, plus each family's hosel "
        "adjustment range and settings.",
        "Compare stock lofts head by head and each family's hosel "
        "adjustability.",
        "Compare stock lofts, head lineups and adjustability.",
        f"Full {WOOD_NOUN[a['club_type']]} spec comparison.",
    ])
    url = f"/compare/{slug}/"
    nav, bc = crumbs([("Home", "/"), ("Compare", "/compare/"),
                      (f"{a['model']} vs {b['model']} {type_word}", None)])

    table = driver_compare_table(a, b, label_a, label_b)
    paras, faq = driver_compare_analysis(a, b, label_a, label_b, generation)
    analysis = "\n  ".join(f"<p>{esc(p)}</p>" for p in paras)
    faq_html, faq_ld = faq_block(faq) if faq else ("", None)

    if generation:
        verdict = (f"The {label_b} is the newer generation, so it carries the "
                   f"current face technology and full retail availability; the "
                   f"{label_a} is the value buy used or on closeout. If the "
                   f"head and loft you want is only in one lineup, that decides "
                   f"it — otherwise the newer family is the default at equal "
                   f"prices, and the older one the smarter buy at a real "
                   f"discount.")
    else:
        verdict = (f"Neither family is better outright — match the head to "
                   f"your shot shape and forgiveness needs first, then pick "
                   f"the stock loft nearest your launch window and fine-tune "
                   f"with the hosel. Feel, sound and price at your spec are "
                   f"the real tiebreakers.")

    def col_card(m):
        c_lofts = driver_lofts(m)
        span = (f"{num(c_lofts[0])}°–{num(c_lofts[-1])}°" if c_lofts else "")
        return (f'<a class="card" href="{m["url"]}">'
                f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
                f'<span class="card-meta">{year_range(m)} · '
                f'{esc(category_label(m))}</span>'
                f'<span class="card-spec">{span} · '
                f'{plural(len(m.get("variants") or []), "head")}</span></a>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(a['brand'])} {esc(a['model'])} vs {esc(b['brand'])} {esc(b['model'])} {type_word}</h1>
    <p class="lede">Side-by-side stock loft coverage, head by head. Lofts where the two
    families offer a different number of heads are highlighted.</p>
  </div>
  <div class="cmp-cols">{col_card(a)}{col_card(b)}</div>

  <h2>Stock lofts compared</h2>
  {table}
  <p class="table-note">Each cell lists the heads sold at that stock loft, factory
  standard. Adjustable hosels extend every head beyond its stamped loft — each model
  page has the full settings chart.</p>

  <h2>What the differences mean</h2>
  {analysis}

  <h2>Which should you choose?</h2>
  <p>{esc(verdict)}</p>
  <p>Both families are charted in full on their own pages:
  <a href="{a['url']}">{esc(a['brand'])} {esc(a['model'])} {WOOD_NOUN[a['club_type']]} specs</a> and
  <a href="{b['url']}">{esc(b['brand'])} {esc(b['model'])} {WOOD_NOUN[b['club_type']]} specs</a>.</p>
  {faq_html}

  {compare_shop_block(a, b)}
</div>
{compare_sticky_bar(a, b)}
"""
    page(url, title, desc, body, brands, [bc] + ([faq_ld] if faq_ld else []),
         googlebot_noindex=not indexed)
    return slug


def compare_page(a, b, brands, indexed=False, generation=False):
    if a.get("club_type") == "wedges":
        return wedge_compare_page(a, b, brands, indexed, generation)
    if is_wood(a):
        return driver_compare_page(a, b, brands, indexed, generation)
    slug = compare_slug(a, b)
    # Lead with the two 7-iron lofts: it is the number people are comparing,
    # and it keeps sibling comparisons from reading as near-duplicates.
    a7, b7 = seven_iron(a), seven_iron(b)
    same_brand = a["brand"] == b["brand"]
    label_a = a["model"] if same_brand else f"{a['brand']} {a['model']}"
    label_b = b["model"] if same_brand else f"{b['brand']} {b['model']}"
    # Sibling comparisons name the brand once — repeating "TaylorMade" twice
    # pushed most of these titles past the SERP cutoff.
    # Try progressively shorter cores for long model names.
    core_full = f"{a['brand']} {a['model']} vs {label_b}"
    core_short = f"{a['model']} vs {b['model']}"
    core = core_full
    if len(core) > TITLE_MAX:
        core = core_short
    if len(core) > TITLE_MAX:
        # Truncate to fit — search engines truncate anyway past 60.
        core = core[:TITLE_MAX - 1] + "…"
    title = fit_title(core,
                      " — Spec Comparison", f" | {SITE_NAME}")
    head_part = f"{a['brand']} {a['model']} vs {label_b}: side-by-side specs. "
    if a7 and b7 and a7.get("loft") == b7.get("loft"):
        # Matching lofts: "34° vs 34°" reads like an error, and the real story
        # is that the difference lives in the other columns.
        lofts = f"Identical {club_noun(a, a7['club'])} loft at {num(a7['loft'])}°. "
    elif a7 and b7:
        lofts = (f"{club_noun(a, a7['club'])} loft {num(a7['loft'])}° vs "
                 f"{num(b7['loft'])}°. ")
    else:
        lofts = None
    # Name only the columns at least one of the two sets actually publishes.
    rows = list(a["specs"]) + list(b["specs"])
    cmp_cols = ["loft", "lie", "length"]
    if any(r.get("offset") is not None for r in rows):
        cmp_cols.append("offset")
    if any(r.get("swing_weight") is not None for r in rows):
        cmp_cols.append("swing weight")
    cols = comma_list(cmp_cols)

    span = (f"{club_noun(a, a['specs'][0]['club'])} to "
            f"{club_noun(a, a['specs'][-1]['club'])}") if a["specs"] else ""
    if lofts:
        desc = fit_desc(head_part + lofts, [
            f"Compare {cols} across the full set, {span}." if span else "",
            f"Compare {cols} across the full set.",
            f"Compare {cols} for every club.",
            "Compare every loft, lie and length difference.",
            "Full spec comparison.",
        ])
    else:
        desc = fit_desc(head_part, [
            f"Compare {cols} for every club in the {label_a} and {label_b} sets.",
            f"Compare {cols} for every club.",
            "Compare loft, lie and length for every club.",
            "Full spec comparison.",
        ])
    url = f"/compare/{slug}/"
    nav, bc = crumbs([("Home", "/"), ("Compare", "/compare/"),
                      (f"{a['model']} vs {b['model']}", None)])

    aspec = {r["club"]: r for r in a["specs"]}
    bspec = {r["club"]: r for r in b["specs"]}
    # Ordered by the loft whichever set records it, so a label only one of the
    # two sets carries still lands in the right place in the merged table.
    clubs = sorted(set(aspec) | set(bspec),
                   key=lambda c: ((aspec.get(c) or bspec.get(c)).get("loft")
                                  or float("inf"), club_sort_key(c)))

    cols = ["loft", "lie", "length"]
    head_cells = "".join(
        f'<th scope="col">{lbl}</th>' for lbl in
        [f"{a['model']} loft", f"{b['model']} loft",
         f"{a['model']} lie", f"{b['model']} lie",
         f"{a['model']} length", f"{b['model']} length"])

    rows = []
    diffs = []
    for c in clubs:
        ra, rb = aspec.get(c), bspec.get(c)
        cells = []
        for k in cols:
            va = ra.get(k) if ra else None
            vb = rb.get(k) if rb else None
            differs = va is not None and vb is not None and va != vb
            cls = ' class="diff"' if differs else ""
            cells.append(f'<td{cls}>{esc(num(va))}</td>' if va is not None else '<td class="na">—</td>')
            cells.append(f'<td{cls}>{esc(num(vb))}</td>' if vb is not None else '<td class="na">—</td>')
            if k == "loft" and differs:
                diffs.append((c, va, vb))
        rows.append(f'<tr><th scope="row">{esc(c)}</th>{"".join(cells)}</tr>')

    # verdict text driven by the actual loft deltas
    if diffs:
        stronger = sum(1 for _, va, vb in diffs if vb < va)
        weaker = sum(1 for _, va, vb in diffs if vb > va)
        if stronger > weaker:
            delta = max(abs(vb - va) for _, va, vb in diffs)
            verdict = (f"The {b['model']} is the stronger-lofted set — up to "
                       f"{num(round(delta, 1))}° stronger than the {a['model']} on matching "
                       f"clubs. Expect longer carry per numbered iron but a flatter descent "
                       f"angle; gapping at the wedge end is where that shows up.")
        elif weaker > stronger:
            delta = max(abs(vb - va) for _, va, vb in diffs)
            verdict = (f"The {b['model']} is the weaker-lofted set — up to "
                       f"{num(round(delta, 1))}° weaker than the {a['model']}. That trades "
                       f"raw distance for a steeper landing angle and more predictable "
                       f"stopping power into greens.")
        else:
            verdict = (f"Loft differences between the {a['model']} and {b['model']} run in "
                       f"both directions rather than shifting the whole set one way, so the "
                       f"choice comes down to shaping, feel and gapping at the ends of the "
                       f"set rather than outright distance.")
    else:
        verdict = (f"The {a['model']} and {b['model']} share the same lofts on every club on "
                   f"file, so the difference is in head construction, feel and forgiveness "
                   f"rather than trajectory.")

    chart = compare_chart(a, b, clubs, aspec, bspec, label_a, label_b)
    paras, faq = compare_analysis(a, b, label_a, label_b, aspec, bspec, generation)
    analysis = "\n  ".join(f"<p>{esc(p)}</p>" for p in paras)
    faq_html, faq_ld = faq_block(faq) if faq else ("", None)
    overlay = (f'<h2>Lofts compared</h2><div class="figs figs-one">{chart}</div>'
               if chart else "")

    def col_card(m):
        return (f'<a class="card" href="{m["url"]}">'
                f'<span class="card-title">{esc(m["brand"])} {esc(m["model"])}</span>'
                f'<span class="card-meta">{year_range(m)} · '
                f'{esc(CATEGORY_LABEL.get(m.get("category"), ""))}</span>'
                f'<span class="card-spec">{esc(m.get("construction") or "")} · '
                f'{esc(m.get("material") or "")}</span></a>')

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(a['brand'])} {esc(a['model'])} vs {esc(b['brand'])} {esc(b['model'])}</h1>
    <p class="lede">Side-by-side factory specifications. Differing values are highlighted.</p>
  </div>
  <div class="cmp-cols">{col_card(a)}{col_card(b)}</div>

  <h2>Specification comparison</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <thead><tr><th scope="col">Club</th>{head_cells}</tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>
  <p class="table-note">Highlighted cells differ between the two sets. Lofts and lies are
  factory standard.</p>

  {overlay}

  <h2>What the differences mean</h2>
  {analysis}

  <h2>Which should you choose?</h2>
  <p>{esc(verdict)}</p>
  <p>Both charts are reproduced in full on their own pages:
  <a href="{a['url']}">{esc(a['brand'])} {esc(a['model'])} specs</a> and
  <a href="{b['url']}">{esc(b['brand'])} {esc(b['model'])} specs</a>.</p>
  {faq_html}

  {compare_shop_block(a, b)}
</div>
{compare_sticky_bar(a, b)}
"""
    page(url, title, desc, body, brands, [bc] + ([faq_ld] if faq_ld else []),
         googlebot_noindex=not indexed)
    return slug


def compare_card(slug, a, b):
    """Index card: names with their 7-iron lofts, brands and years, category badges."""
    is_wedge = a.get("club_type") == "wedges"
    is_driver = is_wood(a)
    # "T100 (2025)" would read "T100 (2025) (33°)" next to its loft.
    na, nb = (re.sub(r" \((\d{4})\)$", r" \1", m["model"]) for m in (a, b))
    if is_driver:
        # Wood pairs compare head lineups, not a reference loft.
        names = f"{na} vs {nb} {WOOD_PLURAL[a['club_type']]}"
        diff = abs(len(a.get("variants") or []) - len(b.get("variants") or []))
        ref = None
        ref_note = f" · {WOOD_NOUN[a['club_type']]} heads"
    elif is_wedge:
        # Wedge pairs compare on selection, not a reference loft.
        names = f"{na} vs {nb}"
        diff = abs(len(a["specs"]) - len(b["specs"]))
        ref = None
        ref_note = " · wedge options"
    else:
        aspec = {r["club"]: r for r in a["specs"]}
        bspec = {r["club"]: r for r in b["specs"]}
        ref = shared_ref_club(aspec, bspec)
        if ref:
            la, lb = aspec[ref]["loft"], bspec[ref]["loft"]
            names = f"{na} ({num(la)}°) vs {nb} ({num(lb)}°)"
            diff = round(abs(lb - la), 1)
        else:
            names = f"{na} vs {nb}"
            diff = 0
        ref_note = f" · {club_noun(a, ref)} lofts" if ref and ref != "7" else ""
    cats = [c for c in dict.fromkeys([a.get("category"), b.get("category")]) if c]
    short = (WEDGE_CATEGORY_SHORT if is_wedge else
             DRIVER_CATEGORY_SHORT if is_driver else CATEGORY_SHORT)
    badge_tail = (" wedges" if is_wedge
                  else f" {WOOD_NOUN[a['club_type']]}" if is_driver else "")
    badges = "".join(f'<span class="badge">{esc(short.get(c, c))}'
                     f'{badge_tail}</span>'
                     for c in cats)
    brands_attr = a["brand"] if a["brand"] == b["brand"] else f"{a['brand']}|{b['brand']}"
    search = " ".join([a["brand"], a["model"], b["brand"], b["model"]]
                      + [CATEGORY_SHORT.get(c, c) for c in cats]).lower()
    years = [y for y in (a.get("year_introduced"), b.get("year_introduced")) if y]
    return (f'<a class="card" href="/compare/{slug}/"'
            f' data-brands="{esc(brands_attr)}" data-cats="{esc("|".join(cats))}"'
            f' data-search="{esc(search)}" data-year="{max(years) if years else 0}"'
            f' data-year2="{min(years) if years else 0}"'
            f' data-diff="{diff}" data-name="{esc(names.lower())}">'
            f'<span class="card-title">{esc(names)}</span>'
            f'<span class="card-meta">{esc(a["brand"])}'
            f'{"" if a["brand"] == b["brand"] else " vs " + esc(b["brand"])} · '
            f'{a.get("year_introduced")} vs {b.get("year_introduced")}{ref_note}</span>'
            f'<span class="card-badges" style="display:flex;flex-wrap:wrap;gap:.3rem;'
            f'margin-top:.5rem">{badges}</span></a>')


def compares_index(pairs_built, brands):
    title = f"Golf Club Spec Comparisons | {SITE_NAME}"
    desc = fit_desc(
        f"{plural(len(pairs_built), 'side-by-side iron and wedge comparison')}, "
        f"generation by generation. ",
        ["Compare 7-iron loft, lie, length, swing weight and wedge bounce/grind "
         "options for every club.",
         "Compare 7-iron loft, lie, length and wedge bounce/grind options.",
         "Compare loft, lie and length for every club."])
    nav, bc = crumbs([("Home", "/"), ("Compare", None)])

    by_slug = {slug: (a, b) for slug, a, b, _ in pairs_built}
    popular = "".join(compare_card(s, *by_slug[s]) for s in POPULAR_COMPARES)

    sorted_brands = sorted({m["brand"] for _s, a, b, _i in pairs_built for m in (a, b)})
    brand_options = "".join(
        f'<option value="{esc(br)}">{esc(br)}</option>' for br in sorted_brands)
    present = {m.get("category") for _s, a, b, _i in pairs_built for m in (a, b)}
    chip_style = ' style="font-family:inherit"'
    cat_chips = (f'<button type="button" class="chip" data-cat="" aria-pressed="true"'
                 f'{chip_style}>All categories</button>' + "".join(
                     f'<button type="button" class="chip" data-cat="{c}" '
                     f'aria-pressed="false"{chip_style}>{esc(CATEGORY_LABEL[c])}</button>'
                     for c in CATEGORY_RANK if c in present))

    # Rendered newest first, so the default order needs no script.
    def newest_key(p):
        _s, a, b, _i = p
        ys = [a.get("year_introduced") or 0, b.get("year_introduced") or 0]
        return (-max(ys), -min(ys), a["brand"], a["model"], b["model"])
    cards = "".join(compare_card(s, a, b)
                    for s, a, b, _i in sorted(pairs_built, key=newest_key))
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Specification Comparisons</h1>
    <p class="lede">Generation-to-generation spec comparisons, showing exactly which lofts
    and lies changed between models. Each card shows both 7-iron lofts.</p>
  </div>

  <h2>Popular comparisons</h2>
  <p>The current-model decisions golfers search for most: Titleist T-series,
  TaylorMade P-series, Ping G and i-series, Callaway Apex and Paradym, and more.
  <a href="#all-comparisons">Skip to all {len(pairs_built):,} comparisons</a>.</p>
  <div class="grid">{popular}</div>

  <h2 id="all-comparisons">All comparisons</h2>
  <div class="compare-filters">
    <input type="text" id="cmp-search" class="cmp-search" placeholder="Search comparisons…" autocomplete="off" aria-label="Search comparisons">
    <select id="cmp-brand" class="cmp-brand-select" aria-label="Filter by brand">
      <option value="">All brands</option>
      {brand_options}
    </select>
    <select id="cmp-sort" class="cmp-brand-select" aria-label="Sort comparisons">
      <option value="newest">Newest first</option>
      <option value="diff">Biggest loft difference</option>
      <option value="alpha">Alphabetical</option>
    </select>
    <span id="cmp-count" class="cmp-count">{len(pairs_built)} comparisons</span>
  </div>
  <div class="chips" id="cmp-cats" role="group" aria-label="Filter by category">{cat_chips}</div>
  <div class="grid" id="cmp-grid">{cards or '<p>No comparisons available yet.</p>'}</div>
  <p id="cmp-empty" class="cmp-empty" style="display:none">No comparisons match your filters.</p>
</div>
<script>
(function(){{
  var search=document.getElementById('cmp-search'),
      brand=document.getElementById('cmp-brand'),
      sort=document.getElementById('cmp-sort'),
      chips=document.getElementById('cmp-cats').querySelectorAll('.chip'),
      grid=document.getElementById('cmp-grid'),
      count=document.getElementById('cmp-count'),
      empty=document.getElementById('cmp-empty'),
      cards=Array.prototype.slice.call(grid.querySelectorAll('.card')),
      cat='';
  function filter(){{
    var q=search.value.toLowerCase().trim(),
        b=brand.value,
        n=0;
    for(var i=0;i<cards.length;i++){{
      var c=cards[i],
          matchQ=!q||c.getAttribute('data-search').indexOf(q)!==-1,
          matchB=!b||c.getAttribute('data-brands').split('|').indexOf(b)!==-1,
          matchC=!cat||c.getAttribute('data-cats').split('|').indexOf(cat)!==-1;
      if(matchQ&&matchB&&matchC){{c.style.display='';n++;}}
      else{{c.style.display='none';}}
    }}
    count.textContent=n+(n===1?' comparison':' comparisons');
    empty.style.display=n?'none':'block';
  }}
  function num(c,k){{return parseFloat(c.getAttribute(k))||0;}}
  function order(){{
    var m=sort.value,
        byName=function(x,y){{return x.getAttribute('data-name')<y.getAttribute('data-name')?-1:1;}};
    cards.sort(function(x,y){{
      if(m==='diff')return num(y,'data-diff')-num(x,'data-diff')||byName(x,y);
      if(m==='alpha')return byName(x,y);
      return num(y,'data-year')-num(x,'data-year')||num(y,'data-year2')-num(x,'data-year2')||byName(x,y);
    }});
    for(var i=0;i<cards.length;i++)grid.appendChild(cards[i]);
  }}
  for(var i=0;i<chips.length;i++){{
    chips[i].addEventListener('click',function(){{
      cat=this.getAttribute('data-cat');
      for(var j=0;j<chips.length;j++)chips[j].setAttribute('aria-pressed',chips[j]===this?'true':'false');
      filter();
    }});
  }}
  search.addEventListener('input',filter);
  brand.addEventListener('change',filter);
  sort.addEventListener('change',order);
}})();
</script>
"""
    page("/compare/", title, desc, body, brands, [bc])


# --------------------------------------------------------------------------
# homepage & static pages
# --------------------------------------------------------------------------

def homepage(brands, models, by_brand):
    title = f"{SITE_NAME} — Golf Club Specifications Database"
    irons = [m for m in models if m["club_type"] == "irons"]
    wedge_models = [m for m in models if m["club_type"] == "wedges"]
    driver_models = [m for m in models if m["club_type"] == "driver"]
    # Count the real archive rather than claiming "thousands" — the number is
    # the credibility signal, and an inflated one is trivially disproved.
    span = loft_span(irons)
    extra = [plural(len(ms), noun) for ms, noun in
             ((wedge_models, "wedge model"), (driver_models, "driver model")) if ms]
    counts = comma_list([plural(len(irons), "iron model")] + extra)
    head_part = (f"{counts}, {span}: source-attributed "
                 f"loft charts. " if span else
                 f"{counts}: source-attributed loft "
                 f"charts. ")
    desc = fit_desc(head_part, [
        "Lie angles, lengths and swing weights from Ping, Titleist, Callaway, "
        "Mizuno and more.",
        "Lie angles, lengths and swing weights from every major brand.",
        "Lie angles, lengths and swing weights for every club.",
        "Lie angles, lengths and hosel settings included."])

    by_key = {m["key"]: m for m in models}
    featured = [by_key[k] for k in FEATURED if k in by_key]
    if len(featured) < 8:
        extra = sorted(models, key=lambda m: m.get("year_introduced") or 9999)
        for m in extra:
            if m not in featured:
                featured.append(m)
            if len(featured) == 8:
                break

    recent = sorted(irons, key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))[:8]

    wedge_recent = sorted(wedge_models,
                          key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))[:8]
    wedge_model_html = ""
    if wedge_recent:
        wedge_model_html = f"""
  <h2>Wedge model specs</h2>
  <p>Standalone wedge lines with the full factory loft, bounce and grind option chart —
  every combination each model is actually sold in.</p>
  <div class="grid">{''.join(model_card(m) for m in wedge_recent)}</div>
"""

    driver_recent = sorted(driver_models,
                           key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))[:8]
    driver_model_html = ""
    if driver_recent:
        driver_model_html = f"""
  <h2>Driver model specs</h2>
  <p>Driver families with the stock lofts for every head variant and the full hosel
  adjustment chart — the settings the manufacturer sheets bury in a PDF.</p>
  <div class="grid">{''.join(model_card(m) for m in driver_recent)}</div>
"""

    fairway_hybrid = [m for m in models
                      if m["club_type"] in ("fairway_wood", "hybrid")]
    fw_recent = sorted(fairway_hybrid,
                       key=lambda m: (-(m.get("year_introduced") or 0),
                                      m["brand"], m["club_type"]))[:8]
    fw_model_html = ""
    if fw_recent:
        fw_model_html = f"""
  <h2>Fairway wood &amp; hybrid specs</h2>
  <p>Fairway and hybrid families from the same lines as the drivers — stock lofts for
  every head, and the hosel adjustment chart where the family shares one.</p>
  <div class="grid">{''.join(model_card(m) for m in fw_recent)}</div>
"""

    # The "what degree is a sand wedge" family of questions is the highest-volume
    # thing this archive can answer from data it already holds, so the guides get
    # a slot on the homepage rather than living only in the nav.
    wedge_cards = "".join(
        f'<a class="card" href="/wedge-lofts/{w["slug"]}/">'
        f'<span class="card-title">{esc(w["name"])}</span>'
        f'<span class="card-meta">Marked {esc(w["abbr"])}</span>'
        f'<span class="card-spec">{w["band"][0]}°–{w["band"][1]}° · '
        f'{esc(w["distances"][1][1])} carry</span></a>' for w in WEDGE_TYPES)

    driver_home_cards = (
        '<a class="card" href="/driver-lofts/">'
        '<span class="card-title">Driver Loft Chart</span>'
        '<span class="card-meta">The reference table</span>'
        '<span class="card-spec">8°–12° · stock lofts for every major brand</span></a>'
        + driver_guide_card_items())

    brand_cards = "".join(
        f'<a class="card brand-card" href="/{b["slug"]}/" '
        f'style="--brand-color:{esc(b.get("color", "#C9A94E"))}">'
        f'<span class="card-title">{esc(b["name"])}</span>'
        f'<span class="card-meta">{plural(len(by_brand.get(b["slug"], [])), "model")}</span></a>'
        for b in brands if by_brand.get(b["slug"]))

    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": SITE + "/",
        "description": desc,
    }
    org_ld = {
        "@context": "https://schema.org", "@type": "Organization",
        "name": SITE_NAME, "url": SITE + "/", "logo": SITE + "/favicon-192.png",
        "email": EMAIL,
    }

    body = f"""<section class="hero">
  <div class="wrap">
    <h1>Golf Club Specifications Database</h1>
    <p class="tagline">Every club. Every spec. Every generation.</p>
    <div class="search">
      <input id="lc-search" type="search" autocomplete="off" data-base="/"
             placeholder="Search a model — try &ldquo;Ping Eye 2&rdquo;"
             aria-label="Search golf club models" role="combobox"
             aria-expanded="false" aria-autocomplete="list" aria-controls="lc-results">
      <div id="lc-results" class="search-results" role="listbox" aria-label="Search results"></div>
    </div>
    <p class="counter"><strong>{len(models)}</strong> models across
    <strong>{len([b for b in brands if by_brand.get(b['slug'])])}</strong> brands</p>
  </div>
</section>
<div class="wrap">
  <h2>Most-searched vintage sets</h2>
  <p>Discontinued clubs whose specs have vanished from manufacturer sites. These are the
  charts people are looking for.</p>
  <div class="grid">{''.join(model_card(m) for m in featured[:8])}</div>

  <h2>Recently released models on file</h2>
  <div class="grid">{''.join(model_card(m) for m in recent)}</div>

  <h2>Browse by brand</h2>
  <div class="grid">{brand_cards}</div>
{wedge_model_html}{driver_model_html}{fw_model_html}
  <h2>Wedge loft guides</h2>
  <p>What degree each wedge is, what it carries, and how the four slots gap together —
  with the numbers taken from the spec charts on this site. Start with the
  <a href="/wedge-lofts/">wedge loft chart</a>.</p>
  <div class="grid">{wedge_cards}</div>

  <h2>Driver loft guides</h2>
  <p>What degree a driver should be, how loft maps to swing speed, and the head-to-head
  loft questions — with the stock lofts every major brand builds collected on the
  <a href="/driver-lofts/">driver loft chart</a>.</p>
  <div class="grid">{driver_home_cards}</div>

  <h2>Loft &amp; spec knowledge guides</h2>
  <p>The questions behind the charts: how iron lofts drifted two club numbers in forty
  years, which hybrid replaces which iron, and what lie angle does to your aim — every
  table computed from the spec archive itself.</p>
  <div class="grid">{knowledge_guide_card_items()}</div>

  <h2>What is a loft chart?</h2>
  <p>A loft chart lists the factory loft of every club in a set, usually alongside lie angle,
  club length, offset and swing weight. It is the reference you need when you are gapping a
  bag, replacing a single lost iron, buying a used set, or working out why a new 7-iron flies
  further than the one it replaced.</p>
  <p>Lofts have moved considerably over time. A 1980s game-improvement 7-iron sat around 36°;
  a modern distance iron of the same number can be 28–30°. That is why comparing sets by club
  number alone is misleading, and why every chart here records the year the set was
  introduced. It is also why the wedge that comes with a set is worth checking on its own —
  see the <a href="/wedge-lofts/pitching-wedge/">pitching wedge loft guide</a>.</p>
</div>
"""
    page("/", title, desc, body, brands, [website_ld, org_ld])


def about_page(brands, models):
    title = f"About {SITE_NAME} — Golf Club Specification Archive"
    years = [m["year_introduced"] for m in models if m.get("year_introduced")]
    desc = fit_desc(
        f"About LoftChart: {plural(len(models), 'golf club model')} from "
        f"{len(brands)} brands, {min(years)}–{max(years)}. ",
        ["An independent, source-attributed archive of loft, lie and length specs "
         "for discontinued and current sets.",
         "An independent, source-attributed archive of discontinued and current "
         "iron specs.",
         "An independent archive of golf club specifications."])
    nav, bc = crumbs([("Home", "/"), ("About", None)])
    body = f"""{nav}
<div class="wrap narrow">
  <div class="page-head">
    <h1>About LoftChart</h1>
    <p class="lede">A reference archive of golf club specifications, built because the
    originals keep disappearing.</p>
  </div>
  <p>When a club is discontinued, its spec sheet usually goes with it. Manufacturer sites
  drop the product page, the PDF catalogue 404s, and what is left is forum threads and
  auto-generated pages that confidently state a set&rsquo;s loft is &ldquo;between 16 and
  61 degrees&rdquo;. LoftChart exists to put the actual table back online.</p>

  <h2>What is on file</h2>
  <p>{len(models)} models across {len(brands)} manufacturers, each with the full factory
  chart: loft, lie and length for every club in the set, plus offset, bounce and swing weight
  where those were published.</p>

  <h2>Where the numbers come from</h2>
  <p>Specifications are compiled from manufacturer catalogues and archived product pages
  (largely via the Internet Archive), published clubmaker spec databases, and retailer spec
  tables from the period. Every model page lists its sources at the bottom, and pages built
  from secondary sources rather than a manufacturer spec sheet carry a data-confidence note.</p>

  <h2>What the numbers mean</h2>
  <p>Unless a page says otherwise, figures are the standard men&rsquo;s right-handed
  steel-shaft build. Left-handed, women&rsquo;s, senior and graphite builds often differ in
  length and sometimes in lie. A used club may also have been bent, re-shafted or re-gripped
  at some point in its life, so treat the chart as the factory reference rather than a
  guarantee about a specific club in hand.</p>

  <h2>Corrections</h2>
  <p>If you have an original catalogue page or spec sheet that contradicts something here, we
  want it. Email {email_link()} with the source and we will update the
  chart and credit it.</p>

  <h2 id="affiliate-disclosure">Affiliate disclosure</h2>
  <p>LoftChart is a participant in the eBay Partner Network. When a page links to
  eBay, the link may be an affiliate link, which means LoftChart earns a small
  commission if you make a purchase — at no extra cost to you. This income helps cover the
  hosting and research costs of maintaining the archive.</p>
  <p>Affiliate relationships have no influence on which models are listed, which
  specifications are published or how the data is presented. Every chart on this site
  reflects the manufacturer&rsquo;s published figures, regardless of whether the model is
  available through an affiliate partner.</p>

  <h2>Independence</h2>
  <p>LoftChart is not affiliated with, endorsed by or sponsored by any golf club
  manufacturer. Brand and model names are the trademarks of their respective owners and are
  used here for identification only.</p>
</div>
"""
    page("/about/", title, desc, body, brands, [bc])


def privacy_page(brands):
    title = f"Privacy Policy | {SITE_NAME}"
    desc = ("How LoftChart.com handles your data: what the site collects, the cookies "
            "and analytics it uses, and the third-party services involved."
            ) if GA_ENABLED else (
            "How LoftChart.com handles your data: no analytics, no advertising cookies "
            "and no accounts, plus the third-party services a page load touches.")
    nav, bc = crumbs([("Home", "/"), ("Privacy", None)])
    # The analytics section has to track what actually ships — claiming we set
    # GA cookies while the snippet is switched off is its own privacy problem.
    analytics_section = """  <p>We use Google Analytics 4 to understand which pages are being read. Google Analytics
  sets cookies and collects information such as your approximate location (derived from IP
  address), browser and device type, the pages you visit and how you arrived at the site. IP
  addresses are anonymised by Google Analytics 4 by default. This data is processed by Google
  and is governed by
  <a href="https://policies.google.com/privacy" rel="noopener">Google&rsquo;s privacy
  policy</a>. Analytics and advertising storage start out denied on every page load, so
  these cookies are only set once you consent to them; until then Google&rsquo;s tags run in
  a mode that stores nothing on your device. You can opt out site-wide using the
  <a href="https://tools.google.com/dlpage/gaoptout" rel="noopener">Google Analytics opt-out
  browser add-on</a>, or by blocking cookies in your browser settings.</p>""" if GA_ENABLED else """  <p>We do not run analytics on this site. No analytics or advertising cookies are set, and
  we do not build any profile of you or your visit.</p>"""
    advertising_section = """  <h2>Advertising</h2>
  <p>We use Google AdSense to show ads. Google and its partners use cookies to serve ads
  based on your prior visits to this and other websites. Google&rsquo;s use of advertising
  cookies enables it and its partners to serve ads based on your visits to this site and/or
  other sites on the Internet. You can opt out of personalised advertising in
  <a href="https://adssettings.google.com" rel="noopener">Google&rsquo;s Ads Settings</a>,
  or opt out of some third-party vendors&rsquo; use of cookies for personalised advertising at
  <a href="https://www.aboutads.info/choices/" rel="noopener">aboutads.info</a>. See
  <a href="https://policies.google.com/technologies/partner-sites" rel="noopener">how Google
  uses information from sites that use its services</a>.</p>
""" if ADSENSE_CLIENT else ""
    body = f"""{nav}
<div class="wrap narrow">
  <div class="page-head">
    <h1>Privacy Policy</h1>
    <p class="lede">Last updated {long_date(PRIVACY_UPDATED)}.</p>
  </div>
  <h2>What we collect</h2>
  <p>LoftChart is a static website. We do not ask for, collect or store personal information
  directly, and there are no accounts, logins or newsletter signups.</p>

  <h2>Analytics</h2>
{analytics_section}
  <p>We also use Ahrefs Web Analytics to count page views and see which sites and searches
  send visitors here. Its script is loaded from analytics.ahrefs.com on every page. Ahrefs
  describes the service as cookieless: it does not set cookies or build a profile of you
  across sites, and it reports visits in aggregate. Your browser still makes a request to
  Ahrefs&rsquo; servers, which includes your IP address and user agent. That data is
  governed by <a href="https://ahrefs.com/privacy" rel="noopener">Ahrefs&rsquo; privacy
  policy</a>.</p>

{advertising_section}
  <h2>Hosting and delivery</h2>
  <p>The site is hosted on GitHub Pages and delivered through Cloudflare&rsquo;s network.
  Every request for a page therefore passes through Cloudflare and GitHub, which process
  your IP address, user agent and the address of the page requested in order to deliver it
  and to keep server logs. Cloudflare also runs automated checks to tell visitors from bots
  and to block abusive traffic; these can load a small script from this site&rsquo;s
  <code>/cdn-cgi/</code> path and may set a strictly necessary security cookie. We do not
  receive or use this data to identify you. See
  <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener">Cloudflare&rsquo;s
  privacy policy</a> and the
  <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener">GitHub
  privacy statement</a>.</p>

  <h2>Fonts</h2>
  <p>Typefaces are served from Google Fonts, which means your browser makes a request to
  Google&rsquo;s servers when a page loads. That request includes your IP address and user
  agent.</p>

  <h2>Search</h2>
  <p>The site search runs entirely in your browser against a JSON file downloaded with the
  page. Your search terms are not sent to us or to any third party.</p>

  <h2>Outbound links and affiliate programmes</h2>
  <p>Pages may link to retailers, auction sites and archived sources. Some of these links are
  affiliate links: LoftChart participates in the eBay Partner Network. When you click an
  affiliate link, the partner may set
  cookies or collect information in accordance with its own privacy policy in order to
  attribute a referral. LoftChart receives only aggregate reporting (such as the number of
  clicks and any resulting commissions) and does not receive personally identifiable
  information about you from the programme.</p>
  <p>Once you follow any outbound link you are subject to that site&rsquo;s privacy policy,
  not ours. See our <a href="/about/#affiliate-disclosure">affiliate disclosure</a> for more
  detail on these relationships.</p>

  <h2>Children</h2>
  <p>This site is not directed at children under 13 and we do not knowingly collect data
  from them.</p>

  <h2>Changes</h2>
  <p>If this policy changes, the revised version will be posted here with a new date at the
  top of the page.</p>

  <h2>Contact</h2>
  <p>Questions about this policy: {email_link()}.</p>
</div>
"""
    page("/privacy/", title, desc, body, brands, [bc])


def not_found(brands):
    body = """<div class="wrap narrow">
  <div class="page-head">
    <h1>Page not found</h1>
    <p class="lede">That chart isn&rsquo;t here — it may have moved, or it may not be on file
    yet.</p>
  </div>
  <div class="search">
    <input id="lc-search" type="search" autocomplete="off" data-base="/"
           placeholder="Search for a model" aria-label="Search golf club models"
           role="combobox" aria-expanded="false" aria-autocomplete="list"
           aria-controls="lc-results">
    <div id="lc-results" class="search-results" role="listbox" aria-label="Search results"></div>
  </div>
  <p style="margin-top:1.5rem"><a href="/brands/">Browse all brands</a> ·
  <a href="/years/">Browse by year</a> · <a href="/">Go to the homepage</a></p>
</div>
"""
    write("404.html", head("Page not found | " + SITE_NAME,
                           "The page you requested could not be found.",
                           "/404.html", noindex=True) + body + foot(brands))


# Crawled URLs that never had a page and never will — mostly mis-parsed slugs
# search engines picked up. GitHub Pages cannot serve a 301, so each one gets
# a stub that meta-refreshes to the real page and declares it canonical.
REDIRECTS = {
    # "1100s" is a mangled crawl of the T100S; the T150 replaced that model.
    "/compare/titleist-1100s-vs-t150/": "/compare/titleist-t100s-vs-t150/",
    # Comparison slugs put the older model first. Correcting announcement
    # years in September 2026 swapped the order of these pairs, and fixing the
    # M1 and M4 lineage retired two pairs outright; the old URLs were already
    # in circulation, so each points at its replacement.
    "/compare/cobra-amp-vs-amp-cell/": "/compare/cobra-amp-cell-vs-amp/",
    "/compare/cobra-king-forged-tec-vs-king-f7/": "/compare/cobra-king-f7-vs-king-forged-tec/",
    "/compare/cobra-king-os-vs-king-f7/": "/compare/cobra-king-f7-vs-king-os/",
    "/compare/ping-blueprint-t-vs-blueprint-s/": "/compare/ping-blueprint-s-vs-blueprint-t/",
    "/compare/taylormade-m-cgb-vs-m1/": "/compare/taylormade-m1-vs-m-cgb/",
    "/compare/taylormade-m2-2017-vs-m1/": "/compare/taylormade-m1-vs-m2-2017/",
    "/compare/taylormade-m2-vs-m1/": "/compare/taylormade-m1-vs-m2/",
    "/compare/taylormade-psi-vs-rsi-tp/": "/compare/taylormade-rsi-tp-vs-psi/",
    "/compare/taylormade-rsi-tp-vs-rsi-1/": "/compare/taylormade-rsi-1-vs-rsi-tp/",
    "/compare/taylormade-rsi-tp-vs-rsi-2/": "/compare/taylormade-rsi-2-vs-rsi-tp/",
    "/compare/taylormade-aeroburner-vs-rsi-1/": "/compare/taylormade-rsi-1-vs-aeroburner/",
    "/compare/taylormade-psi-vs-rsi-2/": "/compare/taylormade-rsi-2-vs-psi/",
    "/compare/taylormade-m1-vs-p770/": "/compare/taylormade-m1-vs-p770-2017/",
    "/compare/taylormade-r7-vs-m4/": "/taylormade/m4-irons/",
    # The 2023 P7MC and P7MB got their own pages, and the P7CB and the 2023
    # P770 now pair with those rather than with the 2020 generation.
    "/compare/taylormade-p7mb-vs-p7cb/": "/compare/taylormade-p7mb-2023-vs-p7cb/",
    "/compare/taylormade-p7mc-vs-p770-2023/": "/compare/taylormade-p770-2023-vs-p7mc-2023/",
}


def redirect_pages():
    for old, new in REDIRECTS.items():
        target = os.path.join(OUT, new.lstrip("/"), "index.html")
        if not os.path.exists(target):
            raise SystemExit(f"redirect target missing: {old} -> {new}")
        write(old.rstrip("/") + "/index.html", f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0;url={new}">
<link rel="canonical" href="{SITE}{new}">
</head>
<body><p>This page has moved to <a href="{new}">{SITE}{new}</a>.</p></body>
</html>
""")


# --------------------------------------------------------------------------
# wedge loft guides
#
# Standalone informational pages for the "what degree is a <x> wedge" queries.
# Every figure in the brand tables is computed from the sets already on file
# rather than typed in by hand, so the guides inherit the sourcing of the model
# pages and cannot drift out of step with the archive as models are added.
# --------------------------------------------------------------------------

# Brand tables describe sets introduced from this year on. Wedge lofts moved a
# long way through the 1990s and 2000s, so quoting a brand's all-time range
# would answer a question nobody asked ("what was a Callaway PW in 1997?").
WEDGE_ERA = 2010
# Brands with fewer sets than this inside that window are left out of the
# table rather than shown as a one-model "range".
WEDGE_MIN_SETS = 3

# The full ladder, used for the "where it fits" table on every wedge page.
WEDGE_LADDER = [
    ("pitching-wedge", "Pitching wedge", "PW", "43°–48°", "95–125 yd"),
    ("gap-wedge", "Gap wedge", "GW / UW", "48°–52°", "80–110 yd"),
    ("approach-wedge", "Approach wedge", "AW / A", "48°–52°", "80–110 yd"),
    ("sand-wedge", "Sand wedge", "SW", "54°–56°", "65–90 yd"),
    ("lob-wedge", "Lob wedge", "LW", "58°–62°", "50–75 yd"),
]

# Full-swing carry, men's amateur. Deliberately given as bands: wedge distance
# is a function of swing speed and strike, not of loft alone, and a single
# number would be wrong for almost everyone reading it.
WEDGE_DISTANCE_HEAD = ("Player", "Typical carry")

WEDGE_TYPES = [
    {
        "slug": "pitching-wedge",
        "name": "Pitching wedge",
        "title_q": "What Degree Is a Pitching Wedge?",
        "abbr": "PW",
        "article": "A",
        "keys": ("PW", "P"),
        "band": (43, 48),
        "bounce": "5°–12°",
        "also": "P, PW, 10-iron (pre-1970s sets)",
        "desc_tail": ("Loft by brand, how far it carries, and why a modern PW is "
                      "several degrees stronger than a 1990s one."),
        "desc_tail_short": "Loft by brand, carry distances and gapping advice.",
        "lede": ("A pitching wedge is the strongest-lofted wedge in the bag and the club "
                 "that finishes almost every iron set."),
        "uses": [
            "Full approach shots from roughly 100–140 yards for most amateurs.",
            "Low, running chip shots from just off the green, where its strong loft keeps "
            "the ball down and lets it release.",
            "Three-quarter and knock-down shots into wind, where a sand or lob wedge would "
            "balloon.",
        ],
        "distances": [
            ("Slower swing speed", "70–95 yd"),
            ("Average male amateur", "95–125 yd"),
            ("Low handicap / fast swing", "125–145 yd"),
            ("Tour professional (typical)", "~135–150 yd"),
        ],
    },
    {
        "slug": "gap-wedge",
        "name": "Gap wedge",
        "title_q": "What Degree Is a Gap Wedge?",
        "abbr": "GW",
        "article": "A",
        "keys": ("GW", "UW", "W", "DW"),
        "band": (48, 52),
        "bounce": "8°–12°",
        "also": "GW, UW (utility wedge, Ping), W (Titleist), DW (Cleveland), attack wedge",
        "desc_tail": ("Loft by brand, when you actually need one, and how to fill the gap "
                      "between pitching and sand wedge."),
        "desc_tail_short": "Loft by brand, carry distances and set gapping.",
        "lede": ("A gap wedge fills the distance gap that opened up between the pitching "
                 "wedge and the sand wedge as iron lofts got stronger."),
        "uses": [
            "Full shots from roughly 80–110 yards — the yardage that fell into a hole "
            "when pitching wedges went from 48° to 44°.",
            "Standard pitch shots of 30–60 yards, where its mid bounce works on most turf.",
            "Longer greenside chips that need more carry than a pitching wedge and more "
            "release than a sand wedge.",
        ],
        "distances": [
            ("Slower swing speed", "60–80 yd"),
            ("Average male amateur", "80–110 yd"),
            ("Low handicap / fast swing", "110–125 yd"),
            ("Tour professional (typical)", "~115–125 yd"),
        ],
    },
    {
        "slug": "sand-wedge",
        "name": "Sand wedge",
        "title_q": "What Degree Is a Sand Wedge?",
        "abbr": "SW",
        "article": "A",
        "keys": ("SW", "S"),
        "band": (54, 56),
        "bounce": "10°–14°",
        "also": "SW, S, sand iron, blaster (vintage sets)",
        "desc_tail": ("Loft by brand, how bounce works out of sand, and what a sand wedge "
                      "carries on a full swing."),
        "desc_tail_short": "Loft by brand, bounce explained and carry distances.",
        "lede": ("A sand wedge is the highest-bounce club in most bags, built by Gene "
                 "Sarazen in the 1930s to slide through sand instead of digging into it."),
        "uses": [
            "Greenside bunker shots — the wide, high-bounce sole is what makes the club "
            "splash through sand rather than stick in it.",
            "Pitches and chips of 20–50 yards from fairway or light rough.",
            "Full shots from roughly 65–95 yards for an average amateur.",
        ],
        "distances": [
            ("Slower swing speed", "45–65 yd"),
            ("Average male amateur", "65–90 yd"),
            ("Low handicap / fast swing", "90–110 yd"),
            ("Tour professional (typical)", "~100–110 yd"),
        ],
    },
    {
        "slug": "lob-wedge",
        "name": "Lob wedge",
        "title_q": "What Degree Is a Lob Wedge?",
        "abbr": "LW",
        "article": "A",
        "keys": ("LW", "L"),
        "band": (58, 62),
        "bounce": "4°–14°",
        "also": "LW, L, flop wedge",
        "desc_tail": ("Loft by brand, 58° vs 60°, and whether a lob wedge earns its place "
                      "in your bag."),
        "desc_tail_short": "Loft by brand, 58° vs 60° and carry distances.",
        "lede": ("A lob wedge is the highest-lofted club in the bag, carried for shots that "
                 "have to stop almost where they land."),
        "uses": [
            "Short-sided pitches and flop shots that need height and very little roll.",
            "Bunker shots from soft sand or with a short-sided pin, where a sand wedge "
            "would not get the ball up quickly enough.",
            "Full shots of 50–80 yards for an average amateur — though most players score "
            "better laying back to a fuller sand-wedge swing.",
        ],
        "distances": [
            ("Slower swing speed", "30–50 yd"),
            ("Average male amateur", "50–75 yd"),
            ("Low handicap / fast swing", "75–95 yd"),
            ("Tour professional (typical)", "~85–95 yd"),
        ],
    },
    {
        "slug": "approach-wedge",
        "name": "Approach wedge",
        "title_q": "What Degree Is an Approach Wedge?",
        "abbr": "AW",
        "article": "An",
        "keys": ("AW", "A"),
        "band": (48, 52),
        "bounce": "8°–12°",
        "also": "AW, A, attack wedge, gap wedge",
        "desc_tail": ("Which brands use the AW label, how it differs from a gap wedge, and "
                      "what it carries."),
        "desc_tail_short": "Loft by brand, AW vs GW, and carry distances.",
        "lede": ("An approach wedge is the same club as a gap wedge — the name is simply "
                 "what certain manufacturers stamp on the sole."),
        "uses": [
            "Full approach shots from roughly 80–110 yards.",
            "Pitch shots inside 60 yards where a sand wedge would come up short.",
            "The bridge club between the pitching wedge and sand wedge in a modern set.",
        ],
        "distances": [
            ("Slower swing speed", "60–80 yd"),
            ("Average male amateur", "80–110 yd"),
            ("Low handicap / fast swing", "110–125 yd"),
            ("Tour professional (typical)", "~115–125 yd"),
        ],
    },
]

WEDGE_BY_SLUG = {w["slug"]: w for w in WEDGE_TYPES}
# Bag order, so every list of the guides (cards, homepage, sitemap) reads
# strongest loft to weakest rather than in definition order.
WEDGE_TYPES = [WEDGE_BY_SLUG[slug] for slug, *_ in WEDGE_LADDER]


def wedge_sets(models, keys):
    """(loft, model) for every set on file carrying a wedge with one of `keys`.

    Where a set carries two clubs that match (a Callaway with both AW and GW on
    the chart, say) the lower loft wins, because that is the club the label in
    question actually names in that set.
    """
    out = []
    for m in models:
        best = None
        for row in m["specs"]:
            if row["club"] in keys and row.get("loft") is not None:
                if best is None or row["loft"] < best:
                    best = row["loft"]
        if best is not None:
            out.append((best, m))
    return out


def wedge_mode(lofts):
    """Most frequently published loft; ties break to the weaker (higher) loft."""
    counts = defaultdict(int)
    for v in lofts:
        counts[v] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))[0][0]


def wedge_span(lofts):
    lo, hi = min(lofts), max(lofts)
    return f"{num(lo)}°" if lo == hi else f"{num(lo)}°–{num(hi)}°"


def wedge_median(lofts):
    s = sorted(lofts)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def wedge_brand_rows(pairs, era=WEDGE_ERA, minimum=WEDGE_MIN_SETS):
    """Per-brand loft summary over sets introduced in `era` or later.

    Returns (rows, omitted_brand_names). Each row is
    (brand_name, brand_slug, count, span, most-common).
    """
    by_brand = defaultdict(list)
    for loft, m in pairs:
        if (m.get("year_introduced") or 0) >= era:
            by_brand[(m["brand"], m["brand_slug"])].append(loft)
    rows, omitted = [], []
    for (name, slug), lofts in by_brand.items():
        if len(lofts) < minimum:
            omitted.append(name)
            continue
        rows.append((name, slug, len(lofts), wedge_span(lofts), num(wedge_mode(lofts))))
    rows.sort(key=lambda r: (-r[2], r[0]))
    return rows, sorted(omitted)


def wedge_examples(pairs, limit=10):
    """Newest set on file per brand that carries the wedge, for the link list."""
    seen, out = set(), []
    for loft, m in sorted(pairs, key=lambda p: (-(p[1].get("year_introduced") or 0),
                                                p[1]["brand"], p[1]["model"])):
        if m["brand_slug"] in seen:
            continue
        seen.add(m["brand_slug"])
        out.append((loft, m))
        if len(out) == limit:
            break
    return out


def wedge_ladder_table(current=None):
    rows = []
    for slug, name, abbr, band, carry in WEDGE_LADDER:
        cell = (f'<span aria-current="page">{esc(name)}</span>' if slug == current
                else f'<a href="/wedge-lofts/{slug}/">{esc(name)}</a>')
        rows.append(f'<tr><th scope="row">{cell}</th><td>{esc(abbr)}</td>'
                    f"<td>{band}</td><td>{esc(carry)}</td></tr>")
    return f"""<div class="table-scroll data-table-zone"><table class="specs">
    <caption>The wedge ladder — typical lofts and full-swing carry for an average
    male amateur.</caption>
    <thead><tr><th scope="col">Wedge</th><th scope="col">Marked</th>
    <th scope="col">Typical loft</th><th scope="col">Typical carry</th></tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>"""


def wedge_distance_table(w):
    rows = "".join(f'<tr><th scope="row">{esc(label)}</th><td>{esc(carry)}</td></tr>'
                   for label, carry in w["distances"])
    return f"""<div class="table-scroll data-table-zone"><table class="specs">
    <caption>Typical full-swing carry distance for {w["article"].lower()} {esc(w["name"].lower())}.</caption>
    <thead><tr><th scope="col">{WEDGE_DISTANCE_HEAD[0]}</th>
    <th scope="col">{WEDGE_DISTANCE_HEAD[1]}</th></tr></thead>
    <tbody>{rows}</tbody></table></div>"""


def wedge_extra_section(slug, models, pairs, stats):
    """The section that makes each guide worth reading on its own."""
    if slug == "pitching-wedge":
        by_decade = defaultdict(list)
        for loft, m in pairs:
            y = m.get("year_introduced")
            if y:
                by_decade[(y // 10) * 10].append(loft)
        rows = "".join(
            f'<tr><th scope="row">{d}s</th><td>{len(v)}</td>'
            f"<td>{num(wedge_median(v))}°</td><td>{wedge_span(v)}</td></tr>"
            for d, v in sorted(by_decade.items()) if len(v) >= 5)
        old = [v for d, v in by_decade.items() if d <= 1990 for v in v]
        new = [v for d, v in by_decade.items() if d >= 2020 for v in v]
        drift = num(wedge_median(old) - wedge_median(new)) if old and new else "several"
        return f"""<h2>Why pitching wedge lofts keep getting stronger</h2>
  <p>The pitching wedge has lost roughly {drift}° of loft in a generation. Manufacturers
  strengthen iron lofts to advertise more distance, and because the wedge is the last club
  in the set it absorbs the whole shift. That is why a modern 7-iron can fly as far as a
  1990s 5-iron, and why the club stamped &ldquo;PW&rdquo; in one bag is not the same club
  as the PW in another.</p>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Pitching wedge loft by decade of release, across the {len(pairs)} sets on
    file here.</caption>
    <thead><tr><th scope="col">Released</th><th scope="col">Sets on file</th>
    <th scope="col">Median PW loft</th><th scope="col">Range</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Two consequences follow. First, replacing an old set with a new one
  moves every yardage in the bag, so re-gapping is not optional. Second, a strong modern PW
  leaves a bigger hole underneath it — which is exactly why the
  <a href="/wedge-lofts/gap-wedge/">gap wedge</a> exists.</p>"""

    if slug == "gap-wedge":
        return """<h2>Do you actually need a gap wedge?</h2>
  <p>Work it out with subtraction rather than guesswork. Take your pitching wedge loft and
  your sand wedge loft: if the difference is more than about 6°, there is a yardage on the
  course you cannot cover with a full swing, and that is the gap the club is named after.
  A 44° pitching wedge and a 56° sand wedge leave 12° — comfortably two clubs&rsquo; worth
  of distance and the most common gapping problem in an amateur bag.</p>
  <p>Note where inside the 48°–52° band a given club lands. A gap wedge bought on its own
  is normally 50° or 52°; a gap wedge supplied with an iron set is usually 48°–50°, because
  it is built to follow that set&rsquo;s own strong pitching wedge rather than to a
  standard.</p>
  <p>The usual fix is 4°–6° between wedges. With a 44° PW that points to a 50° gap wedge,
  a 54° or 56° sand wedge, and a 58° or 60° lob wedge if you carry one. Look up your set on
  its <a href="/brands/">brand page</a> before you buy: the number stamped on the sole of
  your pitching wedge is the only starting point that matters.</p>
  <h2>Gap wedge, utility wedge, approach wedge — same club</h2>
  <p>There is no agreed name for this club, only agreed loft. Cobra, Mizuno, PXG and Wilson
  stamp <strong>GW</strong>; Ping uses <strong>UW</strong> for utility wedge; Titleist has
  used a plain <strong>W</strong>; Cleveland has used <strong>DW</strong>; Callaway,
  TaylorMade and Srixon use <strong>AW</strong> for
  <a href="/wedge-lofts/approach-wedge/">approach wedge</a>. All of them sit in the same
  48°–52° slot."""

    if slug == "sand-wedge":
        return """<h2>Bounce matters more than loft in the sand</h2>
  <p>Bounce is the angle between the leading edge and the lowest point of the sole. It is
  what stops the club digging, and it is the reason a sand wedge works out of a bunker when
  a pitching wedge does not. Sand wedges carry the most bounce in the bag, typically
  10°–14°.</p>
  <ul>
    <li><strong>Low bounce (4°–8°)</strong> — firm sand, tight lies, shallow attack angle.</li>
    <li><strong>Mid bounce (8°–12°)</strong> — the safe default for most players and most
    course conditions.</li>
    <li><strong>High bounce (12°–16°)</strong> — soft, fluffy sand, soft turf, or a steep
    attack angle that takes a deep divot.</li>
  </ul>
  <p>Where a model page here lists bounce, it appears as its own column in the spec chart.</p>
  <h2>54° or 56°?</h2>
  <p>Both are sand wedges. The choice is set by the clubs either side of it: with a 50° gap
  wedge and a 58° lob wedge, a 54° splits the difference evenly; with a 52° gap wedge and a
  60° lob wedge, 56° is the even split. Iron sets that include a sand wedge overwhelmingly
  build it at 54°–56°, which is why standalone wedges cluster there too."""

    if slug == "lob-wedge":
        return """<h2>58° or 60°?</h2>
  <p>60° is the most common lob wedge loft sold, but 58° is the more forgiving choice for
  most amateurs: the extra 2° of loft on a 60° makes thin and fat strikes more punishing and
  costs distance control on full swings. Set the choice by your sand wedge — a 54° sand wedge
  pairs naturally with a 58°, a 56° with a 60°.</p>
  <h2>Should you carry one at all?</h2>
  <p>A lob wedge is the least forgiving club in the bag and the one most often used for the
  shot that least needs it. If most of your short game is played from decent lies with room
  to land the ball, a sand wedge covers it. A lob wedge earns its place when your home course
  has elevated, firm or tightly bunkered greens where you are regularly short-sided.</p>
  <p>Note the practical limit: above about 64° the club stops generating meaningful extra
  height and starts sliding under the ball, which is why almost no manufacturer builds one.
  Iron sets rarely include a lob wedge at all — it is normally bought as a standalone
  specialty wedge.</p>"""

    if slug == "approach-wedge":
        naming = [
            ("AW — approach wedge", "Callaway, TaylorMade, Srixon, XXIO, Tour Edge, Nike"),
            ("GW — gap wedge", "Cobra, Mizuno, PXG, Wilson, Ben Hogan, Maltby"),
            ("UW — utility wedge", "Ping"),
            ("W — wedge", "Titleist (DCI and AP-era sets)"),
            ("DW — dual wedge", "Cleveland"),
        ]
        rows = "".join(f'<tr><th scope="row">{esc(a)}</th><td>{esc(b)}</td></tr>'
                       for a, b in naming)
        return f"""<h2>Approach wedge vs gap wedge</h2>
  <p>They are the same club. &ldquo;Approach wedge&rdquo; and &ldquo;gap wedge&rdquo; both
  describe the wedge that sits between the pitching wedge and the sand wedge, at 48°–52°.
  Only the stamping differs, and the stamping is a marketing decision — which is why the
  labels below all appear on sets in this archive at effectively the same loft.</p>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>What each manufacturer calls the wedge below the pitching wedge.</caption>
    <thead><tr><th scope="col">Marked</th><th scope="col">Used by</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Because the label carries no loft guarantee, never buy this club by
  its letter. A Callaway AW and a Ping UW from the same year can be 3° apart, and a set AW
  is built to match its own iron set rather than to any industry standard — see the
  <a href="/wedge-lofts/gap-wedge/">gap wedge guide</a> for the gapping maths.</p>"""

    return ""


def wedge_faq(w, stats, pairs):
    """(question, plain-text answer) pairs — rendered and fed to FAQPage schema."""
    name = w["name"].lower()
    lo, hi = w["band"]
    common = num(stats["mode"])
    n = stats["n"]
    base = [(
        f"What degree is {w['article'].lower()} {name}?",
        f"Most {name}s are {lo}° to {hi}°. Across the {n} sets on file at LoftChart the "
        f"most common {w['abbr']} loft is {common}°, and the full published range is "
        f"{stats['span'].replace('°–', ' to ').replace('°', '')} degrees."
    ), (
        f"How far does {w['article'].lower()} {name} go?",
        f"For an average male amateur, {w['distances'][1][1].replace(' yd', ' yards')} of "
        f"carry on a full swing. Slower swing speeds carry it "
        f"{w['distances'][0][1].replace(' yd', ' yards')}, and faster players "
        f"{w['distances'][2][1].replace(' yd', ' yards')}. Distance depends far more on "
        f"swing speed and strike quality than on the loft stamped on the club."
    )]

    extra = {
        "pitching-wedge": [
            ("Is a 46 degree wedge a pitching wedge?",
             "Yes. 46° sits in the middle of the pitching wedge band and was the standard "
             "for most iron sets through the 2000s. Modern game-improvement and distance "
             "sets have moved to 43°-45°, while blades and players irons are still built "
             "at 46°-48°."),
            ("Why is my new pitching wedge stronger than my old one?",
             "Because iron lofts have been strengthened steadily to advertise more "
             "distance, and the pitching wedge absorbs the whole shift as the last club "
             "in the set. Median PW loft across the sets on file has moved from 49° in "
             "1980s sets to 44° in sets released since 2020."),
            ("Do I need a gap wedge if I have a pitching wedge?",
             "If the difference between your pitching wedge and your sand wedge is more "
             "than about 6°, yes. A 44° PW and a 56° sand wedge leave a 12° hole, which is "
             "two clubs' worth of distance with nothing to cover it."),
        ],
        "gap-wedge": [
            ("Is a gap wedge the same as an approach wedge?",
             "Yes. Gap wedge, approach wedge, utility wedge and attack wedge all name the "
             "same club in the same 48°-52° slot. The letters stamped on the sole are a "
             "manufacturer's choice: Cobra, Mizuno, PXG and Wilson use GW, Ping uses UW, "
             "Callaway and TaylorMade use AW."),
            ("Is a 52 degree a gap wedge?",
             "Yes. 52° is the most common standalone gap wedge loft, and it pairs well "
             "with a 48° pitching wedge and a 56° sand wedge. Gap wedges built into iron "
             "sets are usually a little stronger, at 48°-50°, to match the set's own "
             "pitching wedge."),
            ("What loft gap should I have between wedges?",
             "Four to six degrees. That works out to roughly 10-15 yards between clubs for "
             "most players. Larger gaps leave yardages you cannot cover with a full swing; "
             "smaller ones waste a slot in the bag."),
        ],
        "sand-wedge": [
            ("Is a 56 degree a sand wedge?",
             "Yes. 56° is the classic sand wedge loft and the most common standalone sand "
             "wedge sold. 54° is equally a sand wedge, and is the better match if you "
             "carry a 50° gap wedge and a 58° lob wedge."),
            ("How much bounce should a sand wedge have?",
             "Ten to fourteen degrees suits most players and most conditions. Go higher if "
             "your sand is soft and fluffy or you take deep divots; go lower if you play "
             "firm sand and tight lies or sweep the ball off the turf."),
            ("What is the difference between a sand wedge and a lob wedge?",
             "Roughly four to six degrees of loft and a good deal of bounce. A sand wedge "
             "at 54°-56° carries more bounce and flies further; a lob wedge at 58°-62° "
             "flies higher, stops faster and is less forgiving on a mis-hit."),
        ],
        "lob-wedge": [
            ("Is a 60 degree a lob wedge?",
             "Yes, and it is the most commonly sold lob wedge loft. 58° is also a lob "
             "wedge and is easier to control for most amateurs, particularly on full and "
             "three-quarter swings."),
            ("Should a high handicapper carry a lob wedge?",
             "Often not. It is the least forgiving club in the bag, and most short-game "
             "shots amateurs face are better played with a sand wedge or even a pitching "
             "wedge running along the ground. Carry one if you are regularly short-sided "
             "on firm or elevated greens."),
            ("What is the highest lofted wedge you can buy?",
             "Sixty-four degrees is the practical ceiling, sold by a handful of "
             "manufacturers. Above that the extra loft stops adding useful height and the "
             "club begins sliding under the ball."),
        ],
        "approach-wedge": [
            ("What is the difference between an approach wedge and a gap wedge?",
             "Nothing but the stamping. Both name the wedge between the pitching wedge and "
             "the sand wedge, at 48° to 52°. Callaway, TaylorMade and Srixon mark it AW; "
             "Cobra, Mizuno, PXG and Wilson mark it GW; Ping marks it UW."),
            ("What degree is an A wedge?",
             "An A wedge, marked A or AW, is normally 48° to 52°. Set-matched approach "
             "wedges tend to sit at the strong end of that band because they are built to "
             "follow a strong modern pitching wedge."),
            ("How far should I hit my approach wedge?",
             "About 80 to 110 yards for an average male amateur, roughly 10 to 15 yards "
             "shorter than a full pitching wedge. If the difference is much larger than "
             "that, the two clubs are gapped too far apart."),
        ],
    }
    return base + extra.get(w["slug"], [])


def wedge_model_links(w, wedge_models):
    """Link block: standalone wedge models sold in this wedge type's loft band."""
    lo, hi = w["band"]
    relevant = [m for m in wedge_models
                if any(lo <= l <= hi for l in wedge_lofts(m))]
    if not relevant:
        return ""
    relevant.sort(key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))
    items = "".join(
        f'<li><a href="{m["url"]}">{esc(m["title"])}</a> '
        f'<span class="mt">{esc(year_range(m))} · '
        f'{plural(sum(1 for l in wedge_lofts(m) if lo <= l <= hi), "loft")} '
        f'in this band</span></li>'
        for m in relevant[:15])
    return (f'<h2>{esc(w["name"])} models on file</h2>'
            f'<p>Standalone wedge lines sold in the {lo}°–{hi}° band, newest first — '
            f'follow a link for the full loft, bounce and grind chart.</p>'
            f'<ul class="linklist">{items}</ul>')


def wedge_page(w, models, brands, wedge_models=()):
    pairs = wedge_sets(models, w["keys"])
    lofts = [l for l, _ in pairs]
    stats = {"n": len(pairs), "mode": wedge_mode(lofts), "span": wedge_span(lofts),
             "median": wedge_median(lofts)}
    rows, omitted = wedge_brand_rows(pairs)
    lo, hi = w["band"]
    name = w["name"]
    lower = name.lower()

    title = fit_title(w["title_q"], " Loft Chart", f" | {SITE_NAME}")
    head_part = (f"{w['article']} {lower} is {lo}°–{hi}°, most commonly "
                 f"{num(stats['mode'])}°. ")
    desc = fit_desc(head_part, [w["desc_tail"], w["desc_tail_short"],
                               f"{name} lofts by brand, with carry distances."])

    nav, bc = crumbs([("Home", "/"), ("Wedge Lofts", "/wedge-lofts/"), (name, None)])

    brand_rows = "".join(
        f'<tr><th scope="row"><a href="/{esc(slug)}/">{esc(bname)}</a></th>'
        f"<td>{cnt}</td><td>{span}</td><td>{mode}°</td></tr>"
        for bname, slug, cnt, span, mode in rows)
    omitted_note = (f" {plural(len(omitted), 'further brand')} with fewer than "
                    f"{WEDGE_MIN_SETS} qualifying sets "
                    f"({comma_list(omitted[:6])}{', and others' if len(omitted) > 6 else ''}) "
                    f"are left out rather than shown as a one-model range."
                    if omitted else "")

    ex = wedge_examples(pairs)
    examples = "".join(
        f'<li><a href="{m["url"]}">{esc(m["brand"])} {esc(m["model"])}</a> — '
        f'{w["abbr"]} {num(loft)}° ({esc(year_range(m))})</li>' for loft, m in ex)

    faq = wedge_faq(w, stats, pairs)
    faq_blocks = "".join(f"<details><summary>{esc(q)}</summary>"
                         f'<p class="faq-body">{esc(a)}</p></details>' for q, a in faq)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q,
                              "acceptedAnswer": {"@type": "Answer", "text": a}}
                             for q, a in faq]}

    article_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": w["title_q"],
        "description": desc,
        "datePublished": WEDGE_PUBLISHED,
        "dateModified": WEDGE_REVIEWED,
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{SITE}/wedge-lofts/{w['slug']}/"},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "about": {"@type": "Thing", "name": f"{name} loft"},
        "keywords": ", ".join([f"{lower} loft", f"what degree is {w['article'].lower()} "
                               f"{lower}", f"{lower} degrees", f"{w['abbr']} loft",
                               "wedge loft chart"]),
    }

    facts = [("Standard loft", f"{lo}°–{hi}°"),
             ("Most common", f"{num(stats['mode'])}°"),
             ("Published range on file", stats["span"]),
             ("Typical bounce", w["bounce"]),
             ("Also marked", w["also"])]
    facts_html = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in facts)

    uses = "".join(f"<li>{u}</li>" for u in w["uses"])

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(w["title_q"])}</h1>
    <p class="lede">{esc(w["lede"])}</p>
  </div>

  <p><strong>{w["article"]} {lower} is normally {lo}° to {hi}°.</strong> Across the
  {stats['n']} iron sets on file here that carry one, the most common {w["abbr"]} loft is
  <strong>{num(stats['mode'])}°</strong> and the published range runs {stats['span']}.
  There is no industry standard, so the only figure that matters for your bag is the one on
  your own set&rsquo;s chart.</p>

  <dl class="facts">{facts_html}</dl>

  <h2>{esc(name)} loft by brand</h2>
  <p>Every figure below is taken from the factory spec charts on this site, covering sets
  introduced from {WEDGE_ERA} onward.</p>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>{esc(name)} loft by manufacturer, sets introduced {WEDGE_ERA} or later.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">Sets on file</th>
    <th scope="col">Loft range</th><th scope="col">Most common</th></tr></thead>
    <tbody>{brand_rows}</tbody></table></div>
  <p class="table-note">Figures are the standard men&rsquo;s right-handed steel build for
  the {w["abbr"]} supplied with each iron set. Standalone specialty wedges are sold in 2°
  increments and are not counted here.{omitted_note}</p>

  <h2>How far does {w["article"].lower()} {lower} go?</h2>
  {wedge_distance_table(w)}
  <p class="table-note">Carry distance, full swing. These are typical ranges rather than
  published averages, and ranges rather than a single number on purpose: swing speed and
  strike quality move wedge distance far more than a degree or two of loft does.</p>

  <h2>What {w["article"].lower()} {lower} is used for</h2>
  <ul>{uses}</ul>

  {wedge_extra_section(w["slug"], models, pairs, stats)}

  <h2>Where it sits in the set</h2>
  {wedge_ladder_table(w["slug"])}
  <p class="table-note">Aim for 4°–6° between wedges. See the
  <a href="/wedge-lofts/">wedge loft chart</a> for the full gapping walk-through.</p>

  <h2>Sets on file with {w["article"].lower()} {lower}</h2>
  <p>The newest set from each manufacturer in the archive that carries one — follow a link
  for the full loft, lie and length chart.</p>
  <ul class="linklist">{examples}</ul>

  {wedge_model_links(w, wedge_models)}

  <h2>Frequently asked questions</h2>
  <div class="faq">{faq_blocks}</div>

  {guide_shop_block(f"Shop {lower}s", f"golf {lower}",
                     f"Search for new and used {lower}s at these retailers:")}

  <div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>Loft figures are computed from the {stats['n']} manufacturer spec charts on file at
    LoftChart that include {w["article"].lower()} {w["abbr"]}; each model page lists its own
    sources.</li>
    <li>Loft bands, bounce ranges and carry distances are the accepted industry conventions
    for a standard men&rsquo;s build, given as ranges because no standard body defines
    them.</li>
  </ul>
  <p>Last reviewed {long_date(WEDGE_REVIEWED)}. Spot an error? {email_link()}</p></div>
</div>
{guide_sticky_bar(f"Shop {lower}s", f"golf {lower}")}
"""
    page(f"/wedge-lofts/{w['slug']}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def wedge_index(models, brands):
    """The /wedge-lofts/ hub — the 'wedge loft chart' overview page."""
    stats = {}
    for w in WEDGE_TYPES:
        pairs = wedge_sets(models, w["keys"])
        lofts = [l for l, _ in pairs]
        stats[w["slug"]] = {"n": len(pairs), "mode": wedge_mode(lofts),
                            "span": wedge_span(lofts), "pairs": pairs}
    total = sum(s["n"] for s in stats.values())
    pw_era_span = wedge_span([l for l, m in stats["pitching-wedge"]["pairs"]
                              if (m.get("year_introduced") or 0) >= WEDGE_ERA])

    title = fit_title("Wedge Loft Chart — Degrees for Every Wedge", f" | {SITE_NAME}")
    head_part = (f"Wedge loft chart: pitching {stats['pitching-wedge']['mode']:.0f}°, gap "
                 f"{stats['gap-wedge']['mode']:.0f}°, sand {stats['sand-wedge']['mode']:.0f}°, "
                 f"lob {stats['lob-wedge']['mode']:.0f}°. ")
    desc = fit_desc(head_part, [
        f"Typical degrees, carry distances and brand-by-brand lofts from {total} "
        f"set wedges on file.",
        "Typical degrees, carry distances and lofts by brand.",
        "Typical wedge degrees and carry distances by brand."])

    nav, bc = crumbs([("Home", "/"), ("Wedge Lofts", None)])

    master_rows = []
    for slug, name, abbr, band, carry in WEDGE_LADDER:
        s = stats[slug]
        w = WEDGE_BY_SLUG[slug]
        master_rows.append(
            f'<tr><th scope="row"><a href="/wedge-lofts/{slug}/">{esc(name)}</a></th>'
            f"<td>{esc(abbr)}</td><td>{band}</td><td>{num(s['mode'])}°</td>"
            f"<td>{esc(carry)}</td><td>{esc(w['bounce'])}</td></tr>")

    # Brand summary: median loft for each wedge slot, current-era sets only.
    def med_for(slug, brand_slug):
        vals = [l for l, m in stats[slug]["pairs"]
                if m["brand_slug"] == brand_slug
                and (m.get("year_introduced") or 0) >= WEDGE_ERA]
        return f"{num(wedge_median(vals))}°" if len(vals) >= 2 else "—"

    brand_by_slug = {}
    for l, m in stats["pitching-wedge"]["pairs"]:
        brand_by_slug.setdefault(m["brand_slug"], m["brand"])
    counts = defaultdict(int)
    for l, m in stats["pitching-wedge"]["pairs"]:
        if (m.get("year_introduced") or 0) >= WEDGE_ERA:
            counts[m["brand_slug"]] += 1
    ranked = sorted((s for s, c in counts.items() if c >= WEDGE_MIN_SETS),
                    key=lambda s: (-counts[s], brand_by_slug[s]))
    summary = []
    for bs in ranked:
        cells = [med_for(slug, bs) for slug, *_ in WEDGE_LADDER]
        if sum(1 for c in cells if c != "—") < 2:
            continue
        summary.append(
            f'<tr><th scope="row"><a href="/{esc(bs)}/">{esc(brand_by_slug[bs])}</a></th>'
            + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    summary_rows = "".join(summary)

    cards = "".join(
        f'<a class="card" href="/wedge-lofts/{w["slug"]}/">'
        f'<span class="card-title">{esc(w["title_q"])}</span>'
        f'<span class="card-meta">{w["band"][0]}°–{w["band"][1]}° · marked '
        f'{esc(w["abbr"])}</span>'
        f'<span class="card-spec">Most common {num(stats[w["slug"]]["mode"])}° across '
        f'{stats[w["slug"]]["n"]} sets on file</span></a>' for w in WEDGE_TYPES)

    faq = [
        ("What are the standard wedge lofts?",
         "Pitching wedge 43-48 degrees, gap or approach wedge 48-52, sand wedge 54-56, "
         "lob wedge 58-62. No governing body sets these, so they are conventions rather "
         "than standards, and a set's own spec chart always overrides them."),
        ("How many wedges should I carry?",
         "Most players carry three: the pitching wedge that came with the set, a sand "
         "wedge, and one wedge between them. A fourth wedge only makes sense if you can "
         "keep 4 to 6 degrees between every one of them without giving up a club you use "
         "more at the top of the bag."),
        ("What loft gaps should be between my wedges?",
         "Four to six degrees, which works out to roughly 10 to 15 yards for most players. "
         "Start from the pitching wedge loft printed on your own set's spec chart, not from "
         "a generic number, because modern pitching wedges vary by 5 degrees between "
         "brands."),
        ("Why do wedge lofts differ so much between brands?",
         "Because the pitching wedge is part of the iron set, and iron lofts have been "
         "strengthened over time to advertise more distance. Specialty wedges sold "
         "separately are far more consistent: they come in 2 degree increments from about "
         "46 to 62 degrees regardless of brand."),
    ]
    faq_blocks = "".join(f"<details><summary>{esc(q)}</summary>"
                         f'<p class="faq-body">{esc(a)}</p></details>' for q, a in faq)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q,
                              "acceptedAnswer": {"@type": "Answer", "text": a}}
                             for q, a in faq]}
    list_ld = {
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "Wedge loft guides",
        "numberOfItems": len(WEDGE_TYPES),
        "itemListElement": [
            {"@type": "ListItem", "position": i,
             "url": f"{SITE}/wedge-lofts/{w['slug']}/", "name": w["title_q"]}
            for i, w in enumerate(WEDGE_TYPES, 1)],
    }
    article_ld = {
        "@context": "https://schema.org", "@type": "TechArticle",
        "headline": "Wedge Loft Chart",
        "description": desc,
        "datePublished": WEDGE_PUBLISHED, "dateModified": WEDGE_REVIEWED,
        "mainEntityOfPage": {"@type": "WebPage", "@id": f"{SITE}/wedge-lofts/"},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "about": {"@type": "Thing", "name": "Golf wedge loft"},
        "keywords": "wedge loft chart, wedge degrees, wedge lofts, golf wedge loft chart",
    }

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Wedge Loft Chart</h1>
    <p class="lede">What degree every wedge is, what it carries, and how the four slots fit
    together — with the loft figures taken from the factory spec charts on this site.</p>
  </div>

  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Standard wedge lofts, typical carry for an average male amateur, and the
    bounce each wedge normally carries.</caption>
    <thead><tr><th scope="col">Wedge</th><th scope="col">Marked</th>
    <th scope="col">Typical loft</th><th scope="col">Most common</th>
    <th scope="col">Typical carry</th><th scope="col">Bounce</th></tr></thead>
    <tbody>{"".join(master_rows)}</tbody></table></div>
  <p class="table-note">&ldquo;Most common&rdquo; is the single most frequently published
  loft for that club across the {total} set wedges on file here. Gap wedge and approach
  wedge are the same club under two different names.</p>

  <h2>The five wedges, one page each</h2>
  <div class="grid">{cards}</div>

  <h2>How to gap your wedges</h2>
  <p>Wedge gapping is subtraction, and it starts with one number: the loft of the pitching
  wedge that came with your irons. Look your set up on its
  <a href="/brands/">brand page</a> — do not assume, because pitching wedges run
  {pw_era_span} across the sets on file here introduced from {WEDGE_ERA} on.</p>
  <ol>
    <li><strong>Find your pitching wedge loft.</strong> A modern game-improvement set is
    often 43°–44°; a players set or blade is usually 46°–48°.</li>
    <li><strong>Add 4°–6° at a time.</strong> That is roughly 10–15 yards per club for most
    players. From a 44° PW: 50°, 54° or 56°, and 58° or 60° if you carry four wedges.</li>
    <li><strong>Check the bottom of the bag.</strong> Above about 60° you gain height
    without gaining control, so most players stop at 58° or 60°.</li>
    <li><strong>Confirm it on the course.</strong> Loft predicts gaps; it does not
    guarantee them. Bounce, shaft and turf all move real carry numbers.</li>
  </ol>
  <p>The most common gapping fault in an amateur bag is a strong modern pitching wedge
  paired with a traditional 56° sand wedge, which leaves 12° — two clubs&rsquo; worth of
  distance — with nothing in between. That is exactly the hole the
  <a href="/wedge-lofts/gap-wedge/">gap wedge</a> was invented to fill.</p>

  <h2>Wedge lofts by brand</h2>
  <p>Median loft for each wedge slot, across sets introduced {WEDGE_ERA} or later. A dash
  means the manufacturer does not supply that wedge with its iron sets often enough to give
  a meaningful figure — most brands leave the lob wedge to their specialty wedge line.</p>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Median set-wedge loft by manufacturer, sets introduced {WEDGE_ERA} or later.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">PW</th><th scope="col">GW</th>
    <th scope="col">AW</th><th scope="col">SW</th><th scope="col">LW</th></tr></thead>
    <tbody>{summary_rows}</tbody></table></div>
  <p class="table-note">GW and AW are the same slot — brands use one label or the other,
  so each row normally carries a figure in one column and a dash in the other.</p>

  <h2>Set wedges and specialty wedges are not the same thing</h2>
  <p>The wedge that comes with an iron set is built to match that set: same head shape,
  same shaft, same finish, and a loft chosen to follow on from the 9-iron. A specialty
  wedge — a Vokey, a Cleveland RTX, a Milled Grind, a Ping s159, a Mizuno T-series — is
  sold on its own in 2° increments, normally from 46° up to 62°, with a choice of bounce
  and sole grind.</p>
  <p>That is why the tables on this site stop at the set wedge. Every figure here comes from
  a manufacturer spec chart for a complete iron set; specialty wedge lofts are simply
  whatever you order.</p>

  <h2>Frequently asked questions</h2>
  <div class="faq">{faq_blocks}</div>

  {guide_shop_block("Shop wedges", "golf wedges",
                     "Search for new and used wedges at these retailers:")}

  <div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>Loft figures are computed from the manufacturer spec charts on file at LoftChart —
    {total} set wedges across {len(summary)} manufacturers. Each model page lists its own
    sources.</li>
    <li>Loft bands, bounce ranges and carry distances are the accepted industry conventions
    for a standard men&rsquo;s build. No governing body defines them, so they are given as
    ranges.</li>
  </ul>
  <p>Last reviewed {long_date(WEDGE_REVIEWED)}. Spot an error? {email_link()}</p></div>
</div>
{guide_sticky_bar("Shop wedges", "golf wedges")}
"""
    page("/wedge-lofts/", title, desc, body, brands,
         [bc, article_ld, list_ld, faq_ld], og_type="article")


def wedge_pages(models, brands, wedge_models=()):
    """Guide hub + per-type pages. `models` is the iron archive the stats are
    mined from; `wedge_models` are the standalone wedge lines to link out to."""
    wedge_index(models, brands)
    for w in WEDGE_TYPES:
        wedge_page(w, models, brands, wedge_models)


# --------------------------------------------------------------------------
# driver loft pages
#
# Standalone informational pages for the "driver loft" queries: a hub chart at
# /driver-lofts/ and four fitting guides under /guides/. Unlike the wedge
# guides, none of this can be computed from data/ — the archive is iron sets —
# so every figure is curated by hand from manufacturer catalogues and standard
# fitting conventions, and the sources block on each page says so plainly.
# --------------------------------------------------------------------------

# (loft, typical swing speed, who it suits, flight character) — the at-a-glance
# chart on the hub. Bands overlap on purpose: loft choice is a fitting window,
# not a lookup, and pretending otherwise would be false precision.
DRIVER_LOFT_BANDS = [
    ("8°", "110+ mph", "Tour players and elite amateurs", "Very low launch and spin — needs serious speed to stay airborne"),
    ("9°", "100–115 mph", "Fast-swinging low handicaps", "Low-mid launch, penetrating flight"),
    ("9.5°", "95–110 mph", "Faster amateurs", "Mid launch, the classic 'better player' loft"),
    ("10.5°", "85–105 mph", "Most amateur golfers", "Mid-high launch — the most common driver loft sold"),
    ("11°–12°", "75–95 mph", "Moderate swing speeds, beginners", "High launch, more backspin, straighter flight"),
    ("13°+", "Under 80 mph", "Slower swings, seniors, juniors", "Maximum height and carry at low ball speeds"),
]

# (brand name, brand slug, current line, stock lofts, hosel adjustment) — the
# by-brand table. Maintained by hand against each manufacturer's own driver
# pages; DRIVER_CHECKED is the month that was last done and is printed with the
# table, so a stale row reads as dated rather than as current. When a line is
# replaced, edit its row here and move DRIVER_CHECKED and DRIVER_REVIEWED.
DRIVER_CHECKED = "2026-10"
# The stock-lofts-by-brand table on the hub is generated from the driver model
# files (data/<brand>/*-driver.yaml), replacing the hand-maintained table that
# went stale each release cycle: each brand shows its current line(s), or its
# newest line on file when none is confirmed current.
def driver_brand_rows(driver_models):
    by_brand = defaultdict(list)
    for m in driver_models:
        by_brand[m["brand_slug"]].append(m)
    rows = []
    for slug in sorted(by_brand, key=lambda s: by_brand[s][0]["brand"].lower()):
        ms = by_brand[slug]
        current = [m for m in ms if is_current(m)]
        if not current:
            newest = max(ms, key=lambda m: m.get("year_introduced") or 0)
            # A brand whose newest line is itself retired (Cleveland) has no
            # current driver to chart; its models stay findable via the brand
            # page and the model list below the table.
            if newest.get("year_discontinued"):
                continue
            current = [newest]
        current.sort(key=lambda m: -(m.get("year_introduced") or 0))
        for m in current:
            lofts_txt = "; ".join(
                f"{variant_short(m, name)} "
                + ", ".join(f"{num(r['loft'])}°" for r in rws
                            if r.get("loft") is not None)
                for name, rws in driver_rows_by_variant(m).items() if rws)
            h = m.get("hosel")
            if h:
                adj = " ".join(x for x in (
                    h.get("loft_range"),
                    f"({h['system']})" if h.get("system") else None) if x)
            else:
                adj = "Non-adjustable"
            rows.append((m, lofts_txt, adj))
    return rows

# (speed band, recommended loft, typical driver carry, typical player) — the
# recommendation chart shared conceptually by all four guides but rendered in
# full only on the swing-speed page.
DRIVER_SPEED_ROWS = [
    ("Under 70 mph", "12°–14°", "Up to ~150 yd", "Many seniors and beginners"),
    ("70–85 mph", "11°–13°", "150–190 yd", "Slower amateur swings"),
    ("85–95 mph", "10.5°–12°", "190–225 yd", "The average male amateur (~93 mph)"),
    ("95–105 mph", "9°–10.5°", "225–255 yd", "Faster amateurs, low handicaps"),
    ("105–115 mph", "8.5°–9.5°", "255–285 yd", "Elite amateurs, long hitters"),
    ("Over 115 mph", "7°–9°", "285+ yd", "Tour-level speed"),
]

# Card metadata for the hub grid, the homepage section and the sitemap.
DRIVER_GUIDES = [
    {"slug": "driver-loft-by-swing-speed",
     "card_title": "Driver Loft by Swing Speed",
     "card_meta": "Fitting chart",
     "card_spec": "Under 85 mph: 11°–13° · over 105 mph: 8.5°–9.5°"},
    {"slug": "best-driver-loft-for-beginners",
     "card_title": "Best Driver Loft for Beginners",
     "card_meta": "Buying guide",
     "card_spec": "Why 10.5°–12° beats 9° until the speed arrives"},
    {"slug": "10-5-vs-12-degree-driver",
     "card_title": "10.5° vs 12° Driver",
     "card_meta": "Loft comparison",
     "card_spec": "Launch, spin, carry and slice correction compared"},
    {"slug": "9-vs-10-5-degree-driver",
     "card_title": "9° vs 10.5° Driver",
     "card_meta": "Loft comparison",
     "card_spec": "The speed threshold where lower loft starts to pay"},
]


def faq_block(faq):
    """(html, FAQPage schema) from a list of (question, plain-text answer)."""
    blocks = "".join(f"<details><summary>{esc(q)}</summary>"
                     f'<p class="faq-body">{esc(a)}</p></details>' for q, a in faq)
    html_ = f'<h2>Frequently asked questions</h2><div class="faq">{blocks}</div>'
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q,
                          "acceptedAnswer": {"@type": "Answer", "text": a}}
                         for q, a in faq]}
    return html_, ld


def driver_article_ld(headline, desc, path, keywords):
    return {
        "@context": "https://schema.org", "@type": "TechArticle",
        "headline": headline,
        "description": desc,
        "datePublished": DRIVER_PUBLISHED, "dateModified": DRIVER_REVIEWED,
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + path},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "about": {"@type": "Thing", "name": "Golf driver loft"},
        "keywords": keywords,
    }


DRIVER_SOURCES = f"""<div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>Loft bands, launch and spin windows, and carry figures are the accepted
    club-fitting conventions for a standard men&rsquo;s build, given as ranges because no
    governing body defines them and strike quality moves every one of them.</li>
    <li>Brand loft options come from the LoftChart driver spec archive &mdash; the
    per-model pages linked above, each compiled from the manufacturer&rsquo;s own spec
    sheets and source-attributed &mdash; last verified in {long_date(DRIVER_CHECKED)}.</li>
  </ul>
  <p>Last reviewed {long_date(DRIVER_REVIEWED)}. Spot an error? {email_link()}</p></div>"""


def driver_guide_card_items(exclude=None):
    return "".join(
        f'<a class="card" href="/guides/{g["slug"]}/">'
        f'<span class="card-title">{esc(g["card_title"])}</span>'
        f'<span class="card-meta">{esc(g["card_meta"])}</span>'
        f'<span class="card-spec">{esc(g["card_spec"])}</span></a>'
        for g in DRIVER_GUIDES if g["slug"] != exclude)


def driver_guide_cards(exclude=None):
    return f'<div class="grid">{driver_guide_card_items(exclude)}</div>'


def driver_index(brands, driver_models=()):
    """The /driver-lofts/ hub — the 'driver loft chart' overview page."""
    title = fit_title("Driver Loft Chart — What Degree Is a Driver?",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "Most drivers are 9° to 12° and 10.5° is the most common loft sold. ",
        ["Full chart by brand, loft by swing speed, and what adjustable hosels "
         "really change.",
         "Loft chart by brand, loft by swing speed, and hosel adjustability.",
         "Loft chart by brand and swing speed."])

    nav, bc = crumbs([("Home", "/"), ("Driver Lofts", None)])

    band_rows = "".join(
        f'<tr><th scope="row">{esc(loft)}</th><td>{esc(speed)}</td>'
        f"<td>{esc(who)}</td><td>{esc(flight)}</td></tr>"
        for loft, speed, who, flight in DRIVER_LOFT_BANDS)

    brand_rows = "".join(
        f'<tr><th scope="row"><a href="/{esc(m["brand_slug"])}/">{esc(m["brand"])}</a></th>'
        f'<td><a href="{m["url"]}">{esc(m["model"])}</a>'
        + (f' ({m["year_introduced"]})' if m.get("year_introduced") else "")
        + f"</td><td>{esc(lofts)}</td><td>{esc(adj)}</td></tr>"
        for m, lofts, adj in driver_brand_rows(driver_models))

    recent_drivers = sorted(driver_models,
                            key=lambda m: (-(m.get("year_introduced") or 0),
                                           m["brand"]))
    driver_model_html = ""
    if recent_drivers:
        driver_model_html = f"""
  <h2>Driver spec charts on file</h2>
  <p>Per-model pages with the stock lofts for every head variant and the full
  hosel adjustment chart — including discontinued lines whose spec pages have
  left the manufacturer sites.</p>
  <div class="grid">{''.join(model_card(m) for m in recent_drivers)}</div>
"""

    faq = [
        ("What loft should my driver be?",
         "Match it to swing speed. Under 85 mph, 11 to 13 degrees; 85 to 95 mph, "
         "10.5 to 12; 95 to 105 mph, 9 to 10.5; above 105 mph, 8 to 9.5. When in "
         "doubt take the higher loft — too little loft costs an amateur far more "
         "carry than too much."),
        ("What loft driver do pros use?",
         "Mostly 8 to 10.5 degrees, but at around 115 mph of clubhead speed, and 125 mph or more for the fastest. A tour "
         "player generates enough ball speed to fly a low-lofted driver; the same "
         "head at 90 mph launches too low, spins too little and falls out of the "
         "air. Copying tour lofts is the most common driver-buying mistake."),
        ("Is a 10.5 degree driver good for the average golfer?",
         "Yes — it is the default for a reason. The average male amateur swings "
         "around 93 mph, which sits squarely in the 10.5 to 12 degree window. That "
         "is why 10.5 is the best-selling loft in nearly every manufacturer's "
         "line."),
        ("What does adjusting a driver hosel actually do?",
         "Rotating the hosel adds or removes loft, typically within a 1.5 to 4 "
         "degree total range depending on brand. It also changes the face angle: "
         "adding loft closes the face slightly and reducing loft opens it, which "
         "is why lofting up also helps a slice."),
        ("Is a higher lofted driver easier to hit?",
         "Generally yes. More loft launches the ball higher, adds backspin that "
         "keeps mis-hits airborne, and reduces the share of sidespin, so curved "
         "shots curve less. The trade-off — a ballooning flight — only appears at "
         "high swing speeds."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = driver_article_ld(
        "Driver Loft Chart", desc, "/driver-lofts/",
        "driver loft chart, driver degrees, what loft driver, 10.5 degree driver, "
        "driver loft by brand")
    list_ld = {
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "Driver loft guides",
        "numberOfItems": len(DRIVER_GUIDES),
        "itemListElement": [
            {"@type": "ListItem", "position": i,
             "url": f"{SITE}/guides/{g['slug']}/", "name": g["card_title"]}
            for i, g in enumerate(DRIVER_GUIDES, 1)],
    }

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Driver Loft Chart</h1>
    <p class="lede">What degree a driver is, which loft fits which swing, and the stock
    lofts every major manufacturer currently builds.</p>
  </div>

  <p><strong>Most drivers are lofted between 9° and 12°, and 10.5° is the most common
  loft sold.</strong> The full retail range runs from 7° tour heads to 14° high-launch
  builds, and nearly every modern driver adds an adjustable hosel that moves the stated
  loft by 1°–2° in each direction. The right number is set by swing speed and launch,
  not by preference — and for most amateurs it is higher than they think.</p>

  <dl class="facts">
    <div><dt>Standard range</dt><dd>8°–12°</dd></div>
    <div><dt>Most common sold</dt><dd>10.5°</dd></div>
    <div><dt>Beginners &amp; moderate swings</dt><dd>10.5°–12°</dd></div>
    <div><dt>Fast swings (105+ mph)</dt><dd>8°–9.5°</dd></div>
    <div><dt>Typical hosel adjustment</dt><dd>±1°–2°</dd></div>
  </dl>

  <h2>Driver lofts at a glance</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Which driver loft suits which swing — fitting windows, not hard rules.</caption>
    <thead><tr><th scope="col">Loft</th><th scope="col">Typical swing speed</th>
    <th scope="col">Who it suits</th><th scope="col">Flight</th></tr></thead>
    <tbody>{band_rows}</tbody></table></div>
  <p class="table-note">Bands overlap on purpose: attack angle, spin and strike move the
  right answer within them. The <a href="/guides/driver-loft-by-swing-speed/">swing speed
  guide</a> walks through picking a number.</p>

  <h2>Stock driver lofts by brand</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock loft options for each manufacturer&rsquo;s current driver line, as of
    {long_date(DRIVER_CHECKED)}.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">Current line</th>
    <th scope="col">Stock lofts</th><th scope="col">Hosel adjustment</th></tr></thead>
    <tbody>{brand_rows}</tbody></table></div>
  <p class="table-note">Generated from the LoftChart driver spec archive, last verified
  {long_date(DRIVER_CHECKED)}; the year is the model year of the line and the model link
  opens its full chart, including the hosel settings. Some lofts are right-hand only, and
  lightweight builds of the same heads are not listed separately.</p>
{driver_model_html}
  <h2>How loft turns into carry</h2>
  <p>A driver flies furthest when launch angle and backspin match ball speed. For most
  amateurs that means launching at roughly 12°–16° with 2,000–3,000 rpm of spin. The
  slower the swing, the more loft it takes to get there: a ball leaving at 130 mph needs
  height and hang time it cannot generate from a 9° face, while a 175 mph ball off the
  same face rides its own speed on a flat, efficient trajectory.</p>
  <p>The mistake almost always runs one way. Too much loft costs a fast swinger a few
  yards of ballooning; too little loft costs a slow swinger 15–20 yards of carry, because
  the ball never gets up. When a fitting is not an option, take the higher loft.</p>

  <h2>Adjustable hosels move more than loft</h2>
  <p>Most current drivers are sold in three or four stock lofts, and the hosel covers
  the gaps — typically ±1° to ±2° around the stated number. Two things
  are worth knowing before turning one. First, the stamped loft is the middle of the
  range, so a 10.5° head can usually play from about 9° to 12°. Second, adding loft
  closes the face slightly and removing loft opens it, which is why lofting up is also a
  standard slice fix and why a lowered driver can start drifting right.</p>

  <h2>Loft is not the whole story</h2>
  <p>Attack angle — whether the club is travelling up or down at impact — shifts the
  effective launch. A player who hits up on the ball 3°–4° adds that much launch for
  free and can play a lower loft; a player who hits down needs more loft on the face to
  compensate. This is why two golfers with identical swing speeds can be correctly fitted
  two degrees apart, and why the charts above are windows rather than single numbers.</p>

  <h2>Driver loft guides</h2>
  {driver_guide_cards()}

  {faq_html}

  {guide_shop_block("Shop drivers", "golf driver",
                     "Search for new and used drivers at these retailers:")}

  <p>Next clubs down the bag: the <a href="/fairway-wood-lofts/">fairway wood loft
  chart</a> and <a href="/hybrid-lofts/">hybrid loft chart</a> cover the rest of the
  long game, and the <a href="/wedge-lofts/">wedge loft chart</a> handles pitching,
  gap, sand and lob wedge degrees the same way.</p>

  {DRIVER_SOURCES}
</div>
{guide_sticky_bar("Shop drivers", "golf driver")}
"""
    page("/driver-lofts/", title, desc, body, brands,
         [bc, article_ld, list_ld, faq_ld], og_type="article")


def driver_speed_guide(brands):
    slug = "driver-loft-by-swing-speed"
    title = fit_title("Driver Loft by Swing Speed", " — Chart", f" | {SITE_NAME}")
    desc = fit_desc(
        "Driver loft by swing speed: under 85 mph play 11°–13°, 85–95 mph "
        "10.5°–12°, 95–105 mph 9°–10.5°, over 105 mph 8.5°–9.5°. ",
        ["Full chart with typical carry distances.",
         "Chart with carry distances.",
         "Full recommendation chart."])

    nav, bc = crumbs([("Home", "/"), ("Driver Lofts", "/driver-lofts/"),
                      ("Loft by Swing Speed", None)])

    rows = "".join(
        f'<tr><th scope="row">{esc(speed)}</th><td>{esc(loft)}</td>'
        f"<td>{esc(carry)}</td><td>{esc(player)}</td></tr>"
        for speed, loft, carry, player in DRIVER_SPEED_ROWS)

    faq = [
        ("What driver loft do I need for an 85 mph swing speed?",
         "10.5 to 12 degrees. At 85 mph the ball leaves the face around 125 mph, "
         "which needs a high launch and healthy backspin to maximise carry. An "
         "adjustable 10.5 degree head turned up a degree is a sensible way to "
         "cover the whole window."),
        ("What driver loft is best for a 95 mph swing?",
         "9.5 to 10.5 degrees for most players. 95 mph sits on the boundary "
         "between the mid and fast bands, so attack angle decides it: hit up on "
         "the ball and 9.5 works, hit level or down and 10.5 carries further."),
        ("What loft should a 100 mph swing use?",
         "9 to 10.5 degrees. At 100 mph a well-struck drive carries around 240 "
         "yards, and the launch-spin window is wide enough that strike pattern "
         "and attack angle matter more than the degree on the sole. This is the "
         "speed where a proper fitting starts paying for itself."),
        ("Does more loft mean less distance?",
         "Only above the speed that needs it. Below roughly 95 mph, more loft "
         "usually means more carry, because the ball stays in the air long enough "
         "to use its speed. The lower-loft-equals-longer rule is true at tour "
         "speed and false for most amateurs."),
        ("How do I find my swing speed without a launch monitor?",
         "Divide your true driver carry — the number in the air, not with roll — "
         "by 2.3. A 200 yard carry puts you near 87 mph. It is rough, but it "
         "lands you in the right loft band, and any simulator, fitting bay or "
         "driving-range monitor will give you the exact figure."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = driver_article_ld(
        "Driver Loft by Swing Speed", desc, f"/guides/{slug}/",
        "driver loft by swing speed, driver loft chart swing speed, "
        "what loft driver for 90 mph, driver fitting")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Driver Loft by Swing Speed</h1>
    <p class="lede">Swing speed sets the loft window. Find your band, then let attack
    angle and ball flight settle the exact number.</p>
  </div>

  <p><strong>The slower the swing, the more loft the driver needs.</strong> Under 85 mph
  the right answer is 11°–13°; between 85 and 95 mph — where most male amateurs sit —
  it is 10.5°–12°; from 95 to 105 mph it is 9°–10.5°; and only above about 105 mph does
  a driver lofted under 9° start paying for itself.</p>

  <h2>Recommended driver loft by swing speed</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Driver loft recommendations by clubhead speed, with typical well-struck
    carry for each band.</caption>
    <thead><tr><th scope="col">Swing speed</th><th scope="col">Recommended loft</th>
    <th scope="col">Typical carry</th><th scope="col">Typical player</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Speeds are driver clubhead speed, not ball speed. Carry figures
  assume a reasonable strike; thin and heel strikes shed distance at every speed.</p>

  <h2>Why slower swings need more loft</h2>
  <p>Carry distance is launch angle, backspin and ball speed working together. The
  distance-maximising window for an amateur is roughly a 12°–16° launch with
  2,000–3,000 rpm of spin. A fast swing reaches that window with a low-lofted face
  because sheer ball speed does the climbing; a slower swing launched at 9° comes out
  low and under-spun, runs out of hang time, and lands 15–20 yards short of the same
  swing with a 12° face. Loft is how a moderate swing buys the airtime a fast swing
  gets free.</p>

  <h2>Adjust for attack angle</h2>
  <p>The table assumes a roughly level strike. If you hit up on the ball — teeing high,
  ball forward, driver sweeping upward 3°–4° — you add that much launch and can sit at
  the low end of your band, or a band lower. If you hit down on it, as most slicers and
  former iron-first golfers do, move up within the band. A launch monitor reads attack
  angle directly; ball flight hints at it too, with a low-spinning knuckling drive
  suggesting up, and a high-spinning ballooning one suggesting down.</p>

  <h2>Use the hosel to fine-tune, not to span bands</h2>
  <p>An adjustable hosel moves most current drivers ±1°–2°, which comfortably covers
  fine-tuning within a band — a 10.5° head plays anywhere from about 9.5° to 12°. What
  it does not do is turn a tour head into a beginner&rsquo;s driver: the head&rsquo;s
  centre of gravity and face design are built around its stated loft. Buy the loft in
  the middle of your band and adjust from there; the
  <a href="/driver-lofts/">driver loft chart</a> lists what each brand sells.</p>

  <h2>Related guides</h2>
  {driver_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop drivers", "golf driver",
                     "Search for new and used drivers at these retailers:")}

  {DRIVER_SOURCES}
</div>
{guide_sticky_bar("Shop drivers", "golf driver")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def driver_beginner_guide(brands):
    slug = "best-driver-loft-for-beginners"
    title = fit_title("Best Driver Loft for Beginners", " — 10.5° or 12°?",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "The best driver loft for beginners is 10.5° to 12°. ",
        ["Higher loft launches the ball, spins it straighter and keeps slices "
         "and thin strikes in play — here is why.",
         "Higher loft launches the ball, flies straighter and keeps mis-hits in "
         "play — here is why.",
         "Why higher loft launches, straightens and forgives."])

    nav, bc = crumbs([("Home", "/"), ("Driver Lofts", "/driver-lofts/"),
                      ("Best Loft for Beginners", None)])

    cmp_rows = [
        ("Launch", "Low — drives often never reach full height",
         "Mid-high — reaches a full flight window", "High — maximum airtime"),
        ("Backspin", "Too little at slow speeds; ball falls out of the air",
         "Enough to hold the ball up", "Plenty — flight stays stable"),
        ("Slice behaviour", "Sidespin dominates — big curves",
         "Noticeably straighter", "Straightest of the three"),
        ("Typical carry", "Shortest — low, diving flight",
         "Longer — full carry window", "Longest for most beginners"),
        ("Thin / low-face strikes", "Often top or skim along the ground",
         "Usually still airborne", "Most survivable"),
    ]
    cmp_html = "".join(
        f'<tr><th scope="row">{esc(k)}</th><td>{esc(a)}</td><td>{esc(b)}</td>'
        f"<td>{esc(c)}</td></tr>" for k, a, b, c in cmp_rows)

    faq = [
        ("Is a 12 degree driver good for a beginner?",
         "Yes — for most beginners it is the better buy. Twelve degrees launches "
         "the ball properly at slower swing speeds, spins it straight enough to "
         "tame the early slice, and turns low-face strikes into playable drives "
         "instead of tops."),
        ("Should a beginner use a 9.5 degree driver?",
         "Almost never. A 9.5 degree face needs around 100 mph of clubhead speed "
         "to fly properly, and most beginners swing 75 to 90 mph. The result is a "
         "low, curving drive that costs both carry and confidence. Loft is the "
         "cheapest forgiveness there is."),
        ("Do beginners lose distance with a 12 degree driver?",
         "No — they usually gain it. Below roughly 90 mph of swing speed, the "
         "extra launch and spin of a 12 degree face keep the ball in the air "
         "longer, and total carry goes up, not down. Lower lofts only win once "
         "swing speed can support them."),
        ("What about 13 and 14 degree high-launch drivers?",
         "Worth a look below about 75 mph of swing speed. Most manufacturers "
         "build a lightweight high-launch version of their flagship driver at "
         "12 to 13.5 degrees for exactly this player, often with a draw bias "
         "added."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = driver_article_ld(
        "Best Driver Loft for Beginners", desc, f"/guides/{slug}/",
        "best driver loft for beginners, beginner driver loft, "
        "12 degree driver beginner, high handicap driver loft")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Best Driver Loft for Beginners</h1>
    <p class="lede">The short answer is more loft than you think — and the reasons are
    physics, not politeness.</p>
  </div>

  <p><strong>The best driver loft for most beginners is 10.5° to 12°.</strong> Pick 12°
  if your drives fly low, slice hard or carry under about 180 yards; pick 10.5° if you
  already flight the ball well and are gaining speed. What almost no beginner should buy
  is the 8°–9.5° head the marketing is photographed with — those lofts are built for
  swing speeds most golfers never reach.</p>

  <h2>Why higher loft helps a new golfer</h2>
  <p>Three separate effects stack in the same direction.</p>
  <ul>
    <li><strong>Carry.</strong> A beginner&rsquo;s swing speed — typically 75–90 mph —
    produces a ball speed that needs a high launch and generous backspin to stay
    airborne. Loft supplies both. The same swing that dribbles a 9° driver flights a
    12° one.</li>
    <li><strong>Straighter flight.</strong> Loft adds backspin, and backspin crowds out
    the tilt that turns a drive into a slice. The physics is blunt: the more backspin on
    the ball, the smaller the share of its spin that can curve it sideways. A 12° driver
    does not cure a slice, but it shrinks one visibly.</li>
    <li><strong>Mis-hit margin.</strong> Beginners strike the bottom half of the face
    far more often than the middle. Low-face contact delofts the club at the worst
    moment; starting from 12° leaves enough loft behind for the ball to fly anyway,
    where the same strike on a 9° face skims the ground.</li>
  </ul>

  <h2>The same swing at 9°, 10.5° and 12°</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>What each loft gives a typical beginner&rsquo;s swing (around 80–90 mph).</caption>
    <thead><tr><th scope="col"></th><th scope="col">9°</th>
    <th scope="col">10.5°</th><th scope="col">12°</th></tr></thead>
    <tbody>{cmp_html}</tbody></table></div>
  <p class="table-note">Directional tendencies, not lab numbers — strike quality moves
  every row. The pattern is what matters: at beginner speeds, every column improves as
  loft goes up.</p>

  <h2>Choosing between 10.5° and 12°</h2>
  <p>Both are defensible; the tiebreakers are flight and miss. Drives that come off low
  and run out of air, a slice that starts the ball right and keeps going, or a carry
  under about 180 yards all point to 12°. A beginner who already launches the ball well
  — often a younger player, or one arriving from another hitting sport — can take 10.5°
  and grow into it, especially since a modern
  <a href="/driver-lofts/">adjustable hosel</a> will let it play anywhere from 9.5° to
  12°. The full comparison is in the
  <a href="/guides/10-5-vs-12-degree-driver/">10.5° vs 12° guide</a>.</p>

  <h2>Buy the forgiving version, not the tour version</h2>
  <p>Every manufacturer sells its driver in a standard head, a low-spin tour head, and a
  forgiving high-launch or draw-biased head. Beginners belong in the third column — the
  Max, HL and D-type builds — which is also where the 12° and 13° lofts live. The
  <a href="/driver-lofts/">driver loft chart</a> lists what each brand currently
  offers, and the <a href="/guides/driver-loft-by-swing-speed/">swing speed guide</a>
  shows where you will sit as your speed builds.</p>

  <h2>Related guides</h2>
  {driver_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop drivers", "golf driver",
                     "Search for new and used drivers at these retailers:")}

  {DRIVER_SOURCES}
</div>
{guide_sticky_bar("Shop drivers", "golf driver")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def driver_10_5_vs_12(brands):
    slug = "10-5-vs-12-degree-driver"
    title = fit_title("10.5 vs 12 Degree Driver", " — Which Loft?", f" | {SITE_NAME}")
    desc = fit_desc(
        "10.5° suits driver swings of roughly 90 mph and up; 12° launches higher "
        "and flies straighter below that. ",
        ["Launch, spin, carry and slice correction compared.",
         "Launch, spin and carry compared.",
         "Full loft comparison."])

    nav, bc = crumbs([("Home", "/"), ("Driver Lofts", "/driver-lofts/"),
                      ("10.5° vs 12°", None)])

    cmp_rows = [
        ("Best-fit swing speed", "Roughly 90–105 mph", "Roughly 70–90 mph"),
        ("Launch", "Mid — 12°–14° for most", "High — 14°–17° for most"),
        ("Backspin", "Moderate", "Higher — flight holds up longer"),
        ("Flight shape", "Flatter, more roll-out", "Higher peak, steeper landing, less roll"),
        ("Slice correction", "Some", "More — extra backspin straightens curve"),
        ("Typical buyer", "Average and faster amateurs", "Slower swings, beginners, high launch seekers"),
    ]
    cmp_html = "".join(
        f'<tr><th scope="row">{esc(k)}</th><td>{esc(a)}</td><td>{esc(b)}</td></tr>'
        for k, a, b in cmp_rows)

    faq = [
        ("Is a 12 degree driver too much loft?",
         "Not below about 90 mph of swing speed — there it is usually the longer "
         "club, because the extra launch and spin keep the ball airborne. Above "
         "roughly 95 mph, 12 degrees starts to balloon and shed distance, and "
         "10.5 or less fits better."),
        ("Will I lose distance going from 10.5 to 12 degrees?",
         "Only if your swing is fast enough that 10.5 already launches properly. "
         "For slower swings the move usually adds carry; for a 100 mph swing it "
         "usually costs a handful of yards of ballooning flight and roll-out."),
        ("Can I just adjust a 10.5 driver up to 12?",
         "Usually, yes. Most adjustable hosels add at least 1.5 degrees, taking a "
         "10.5 head to 12. Two caveats: adding loft also closes the face slightly, "
         "and the head is still built around 10.5, so a player who knows they need "
         "12 is better served buying it."),
        ("Does a 12 degree driver help a slice?",
         "It helps, without curing it. More loft means more backspin, which "
         "reduces the sideways tilt of the spin axis, so the same swing curves "
         "less. Combined with a draw-biased head it is the standard "
         "equipment-side answer to a slice."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = driver_article_ld(
        "10.5 vs 12 Degree Driver", desc, f"/guides/{slug}/",
        "10.5 vs 12 degree driver, 12 degree driver, driver loft comparison")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>10.5° vs 12° Driver</h1>
    <p class="lede">One and a half degrees, and the most common upgrade question at the
    forgiving end of the rack.</p>
  </div>

  <p><strong>10.5° fits driver swings of roughly 90 mph and up; 12° is the better fit
  below that.</strong> The dividing line is whether your swing generates the ball speed
  to launch a 10.5° face properly. If it does, 12° trades a little distance for height;
  if it does not, 12° is both the straighter and the longer club — the rare equipment
  choice with no real downside.</p>

  <h2>Side by side</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>10.5° and 12° drivers compared for a typical amateur swing.</caption>
    <thead><tr><th scope="col"></th><th scope="col">10.5°</th>
    <th scope="col">12°</th></tr></thead>
    <tbody>{cmp_html}</tbody></table></div>
  <p class="table-note">Launch and spin figures assume a centred strike at the speeds
  shown; attack angle moves both. Loft on the face at impact also depends on shaft bend
  and delivery, which is why fitted numbers beat chart numbers.</p>

  <h2>The carry question, honestly</h2>
  <p>At 80–85 mph, the 12° driver typically carries further — the 10.5° flight peaks too
  low and lands early, while the extra loft buys hang time the swing cannot. Around
  90 mph the two carry within a few yards of each other and the choice becomes flight
  preference. By 100 mph the 12° is clearly shorter, spinning up and climbing instead of
  driving forward. Distance is an argument <em>for</em> 12° at the speeds most people
  who ask this question actually swing at — see the
  <a href="/guides/driver-loft-by-swing-speed/">loft by swing speed chart</a> for the
  full bands.</p>

  <h2>The slice factor</h2>
  <p>The 12° head is meaningfully straighter for a slicer. Extra loft adds backspin, and
  backspin crowds out the axis tilt that curves the ball; the same out-to-in swing that
  slices a 10.5° driver 40 yards might slice a 12° one 25. Manufacturers know it, which
  is why draw-biased heads are routinely offered at 12° and rarely at 9°.</p>

  <h2>Splitting the difference</h2>
  <p>Most current adjustable hosels take a 10.5° head to 12° — a legitimate way to test
  the question with a driver you already own. Turn it up, play a month, and watch carry
  and dispersion rather than looks at address. Remember that lofting up closes the face
  fractionally, and that the reverse experiment (buying 12° and turning it down) gives
  the same coverage. The <a href="/driver-lofts/">driver loft chart</a> lists each
  brand&rsquo;s stock lofts and adjustment ranges. If you are choosing your first
  driver rather than tuning one, start with the
  <a href="/guides/best-driver-loft-for-beginners/">beginner loft guide</a>.</p>

  <h2>Related guides</h2>
  {driver_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop drivers", "golf driver",
                     "Search for new and used drivers at these retailers:")}

  {DRIVER_SOURCES}
</div>
{guide_sticky_bar("Shop drivers", "golf driver")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def driver_9_vs_10_5(brands):
    slug = "9-vs-10-5-degree-driver"
    title = fit_title("9 vs 10.5 Degree Driver", " — Which to Play?", f" | {SITE_NAME}")
    desc = fit_desc(
        "A 9° driver only out-carries a 10.5° at swing speeds around 100 mph and "
        "above. ",
        ["Side-by-side launch, spin and carry, plus how attack angle moves the "
         "threshold.",
         "Side-by-side launch, spin and carry comparison.",
         "Full loft comparison with carry figures."])

    nav, bc = crumbs([("Home", "/"), ("Driver Lofts", "/driver-lofts/"),
                      ("9° vs 10.5°", None)])

    cmp_rows = [
        ("Best-fit swing speed", "Roughly 100+ mph", "Roughly 85–105 mph"),
        ("Launch", "Low-mid — 10°–13°", "Mid — 12°–15°"),
        ("Backspin", "Lower — flight can knuckle if underspun", "Moderate — stable flight"),
        ("Flight shape", "Flat, penetrating, more roll", "Higher carry, softer landing"),
        ("Wind performance", "Stronger into wind", "More affected into wind"),
        ("Mis-hit tolerance", "Less — low strikes dive", "More — mis-hits stay airborne"),
        ("Typical buyer", "Fast, low-spin players", "The broad middle of amateur golf"),
    ]
    cmp_html = "".join(
        f'<tr><th scope="row">{esc(k)}</th><td>{esc(a)}</td><td>{esc(b)}</td></tr>'
        for k, a, b in cmp_rows)

    faq = [
        ("Is a 9 degree driver harder to hit?",
         "Yes, at most amateur speeds. Less loft means less backspin, so mis-hits "
         "curve more and low-face strikes dive. The penetrating flight that makes "
         "9 degrees attractive only appears when ball speed is high enough to "
         "sustain it — around 100 mph of clubhead speed and up."),
        ("Will a 9 degree driver go further than a 10.5?",
         "Only for fast swingers. Above roughly 100 to 105 mph, the lower loft "
         "turns extra ball speed into a flatter, longer flight with more roll. "
         "Below that, the 9 degree launches too low and lands short of the 10.5 — "
         "lower loft is a reward for speed, not a source of it."),
        ("What swing speed do you need for a 9 degree driver?",
         "Around 100 mph as a floor, and 105-plus to get the full benefit — "
         "carrying a 250 yard drive on a 9 degree face takes serious ball speed. "
         "Players who hit up on the ball 3 to 4 degrees can run a 9 at slightly "
         "lower speeds, because the upward strike adds launch the loft does "
         "not."),
        ("Why do pros use 9 degree drivers when amateurs shouldn't?",
         "Because at 115 mph and above, spin is the enemy and launch comes free. "
         "Tour players fight excess spin that costs them distance, so they play "
         "8 to 10 degrees; an amateur at 90 mph has the opposite problem and "
         "needs the loft they are giving up."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = driver_article_ld(
        "9 vs 10.5 Degree Driver", desc, f"/guides/{slug}/",
        "9 vs 10.5 degree driver, 9 degree driver, driver loft comparison")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>9° vs 10.5° Driver</h1>
    <p class="lede">The classic loft question — and the one where ego most reliably picks
    the wrong answer.</p>
  </div>

  <p><strong>A 9° driver only beats a 10.5° at swing speeds around 100 mph and
  above.</strong> Below that threshold the lower loft launches too low, spins too
  little, and lands short — which is why 10.5° is the right call for the broad middle
  of amateur golf, and why 9° heads outsell their fit. Lower loft is a reward for ball
  speed, not a shortcut to it.</p>

  <h2>Side by side</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>9° and 10.5° drivers compared across the speeds amateurs actually swing at.</caption>
    <thead><tr><th scope="col"></th><th scope="col">9°</th>
    <th scope="col">10.5°</th></tr></thead>
    <tbody>{cmp_html}</tbody></table></div>
  <p class="table-note">Tendencies for a centred strike. Modern low-spin heads have
  pushed the workable speed for 9° slightly lower than older designs, but the physics
  of the threshold has not moved.</p>

  <h2>Where the 100 mph threshold comes from</h2>
  <p>Maximum carry wants launch and spin matched to ball speed. At 100+ mph of clubhead
  speed, a 9° face still launches near 11°–12° with spin low enough to fly flat and run
  — the classic strong-player flight. At 90 mph, that same face launches around 9°–10°
  with under 2,000 rpm on mis-hits, and the ball simply runs out of lift. The 10.5°
  covers both cases adequately; the 9° covers only the first. The full band-by-band
  breakdown is in the
  <a href="/guides/driver-loft-by-swing-speed/">loft by swing speed guide</a>.</p>

  <h2>The exceptions that make 9° work at lower speeds</h2>
  <p>Two player types can legitimately play 9° in the mid-90s mph. Players who hit up on
  the ball steeply — positive attack angles of 3°–5°, common in long-drive technique —
  add launch at impact and can pair it with low loft. And naturally high-spin players,
  who balloon everything, sometimes use lower loft to pull spin back into the window.
  Both cases show up on a launch monitor, not in a mirror: the fitting data, not the
  stamp, makes the call.</p>

  <h2>Buying advice</h2>
  <p>If you are between the two, take the 10.5° — its adjustable hosel almost certainly
  reaches 9.5° or 9° anyway, while a 9° head turned up plays with a slightly closed
  face it was not designed around. Check your carry distance honestly against the
  <a href="/guides/driver-loft-by-swing-speed/">swing speed chart</a>, and see the
  <a href="/driver-lofts/">driver loft chart</a> for what each manufacturer builds at
  each loft.</p>

  <h2>Related guides</h2>
  {driver_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop drivers", "golf driver",
                     "Search for new and used drivers at these retailers:")}

  {DRIVER_SOURCES}
</div>
{guide_sticky_bar("Shop drivers", "golf driver")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def driver_pages(brands, driver_models=()):
    driver_index(brands, driver_models)
    driver_speed_guide(brands)
    driver_beginner_guide(brands)
    driver_10_5_vs_12(brands)
    driver_9_vs_10_5(brands)


# --------------------------------------------------------------------------
# club knowledge guides — /guides/iron-number-equivalents/ and friends
#
# Cross-cutting questions the archive can answer with its own numbers: how
# iron lofts drifted era by era, which hybrid stands in for which iron, what
# lie angle does, what loft itself is, and the strong-versus-traditional
# divide. Unlike the driver guides, the tables here are computed from data/
# at build time, so the figures move when the archive does; only the fitting
# conventions around them are curated, and the sources block says which is
# which.
# --------------------------------------------------------------------------

IRON_CLUB_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "PW"]

# Card metadata for the cross-links between guides, the homepage section and
# the sitemap — same contract as DRIVER_GUIDES.
KNOWLEDGE_GUIDES = [
    {"slug": "iron-number-equivalents",
     "card_title": "What Replaced the 3-Iron?",
     "card_meta": "Iron loft history",
     "card_spec": "A modern GI 7-iron carries a 1980s 5-iron's loft"},
    {"slug": "hybrid-to-iron-conversion",
     "card_title": "Hybrid to Iron Conversion",
     "card_meta": "Replacement chart",
     "card_spec": "19°–21° = 3-iron · 22°–24° = 4-iron · 25°–27° = 5-iron"},
    {"slug": "strong-vs-traditional-lofts",
     "card_title": "Strong vs Traditional Lofts",
     "card_meta": "The loft creep debate",
     "card_spec": "29° vs 34° 7-irons — what the numbers hide"},
    {"slug": "lie-angle",
     "card_title": "Lie Angle Explained",
     "card_meta": "Fitting guide",
     "card_spec": "Standard lies by iron, and how 1° aims you offline"},
    {"slug": "golf-club-loft-explained",
     "card_title": "Golf Club Loft Explained",
     "card_meta": "Beginner guide",
     "card_spec": "From 9° drivers to 60° lob wedges — what loft does"},
]


def knowledge_article_ld(headline, desc, path, keywords, about):
    return {
        "@context": "https://schema.org", "@type": "TechArticle",
        "headline": headline,
        "description": desc,
        "datePublished": KNOWLEDGE_PUBLISHED, "dateModified": KNOWLEDGE_REVIEWED,
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + path},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "about": {"@type": "Thing", "name": about},
        "keywords": keywords,
    }


def knowledge_sources(first_bullet):
    return f"""<div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>{first_bullet}</li>
    <li>Every table marked &ldquo;generated from the archive&rdquo; is computed at build
    time from the LoftChart spec archive &mdash; the per-model pages linked on this site,
    each compiled from the manufacturer&rsquo;s own spec sheets and source-attributed
    &mdash; so the figures update whenever a model is added or corrected.</li>
  </ul>
  <p>Last reviewed {long_date(KNOWLEDGE_REVIEWED)}. Spot an error? {email_link()}</p></div>"""


def knowledge_guide_card_items(exclude=None, only=None):
    return "".join(
        f'<a class="card" href="/guides/{g["slug"]}/">'
        f'<span class="card-title">{esc(g["card_title"])}</span>'
        f'<span class="card-meta">{esc(g["card_meta"])}</span>'
        f'<span class="card-spec">{esc(g["card_spec"])}</span></a>'
        for g in KNOWLEDGE_GUIDES
        if g["slug"] != exclude and (only is None or g["slug"] in only))


def knowledge_guide_cards(exclude=None, only=None):
    return f'<div class="grid">{knowledge_guide_card_items(exclude, only)}</div>'


def iron_ladder(ms, clubs=None):
    """club -> median loft (to the nearest 0.5°) over the sets that carry it."""
    out = {}
    for c in clubs or IRON_CLUB_ORDER:
        lofts = [row["loft"] for row in (club_row(m, c) for m in ms)
                 if row and row.get("loft") is not None]
        if lofts:
            out[c] = round(median(lofts) * 2) / 2
    return out


def sets_of_decade(iron_models, dec):
    return [m for m in iron_models
            if dec <= (m.get("year_introduced") or 0) < dec + 10]


def current_irons_of(iron_models, category=None):
    return [m for m in iron_models if is_current(m)
            and (category is None or m.get("category") == category)]


def nearest_club(ladder, loft, tolerance=2.5):
    """(club, loft) in the ladder closest to the target, or None beyond tolerance."""
    cands = [(c, l) for c, l in ladder.items() if abs(l - loft) <= tolerance]
    return min(cands, key=lambda cl: abs(cl[1] - loft)) if cands else None


def clubs_in_band(ladder, lo, hi):
    """The clubs whose median loft falls inside [lo, hi], formatted for a cell."""
    hits = [f"{club_label_long(c)} ({num(ladder[c])}°)"
            for c in IRON_CLUB_ORDER if c in ladder and lo <= ladder[c] <= hi]
    return " / ".join(hits) if hits else "—"


def club_label_long(c):
    return "pitching wedge" if c == "PW" else f"{c}-iron"


def _model_by_key(ms, key):
    for m in ms:
        if m["key"] == key:
            return m
    return None


def iron_equivalents_guide(brands, iron_models):
    """/guides/iron-number-equivalents/ — what replaced the 3-iron, and what a
    modern 7-iron would have been called in earlier decades."""
    slug = "iron-number-equivalents"
    title = fit_title("What Replaced the 3-Iron? Iron Loft Equivalents",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "A modern game-improvement 7-iron carries the loft of a 1980s 5-iron — "
        "about 29°. ",
        ["Decade-by-decade iron loft charts show what each club number used to "
         "mean.",
         "Decade charts show what each iron number used to mean.",
         "Decade-by-decade iron loft charts."])

    nav, bc = crumbs([("Home", "/"), ("Iron Lofts", "/iron-lofts/"),
                      ("Iron Number Equivalents", None)])

    # Median loft per club per decade, computed over every set on file.
    decades = [(dec, sets_of_decade(iron_models, dec))
               for dec in (1980, 1990, 2000, 2010, 2020)]
    show_clubs = IRON_CLUB_ORDER[1:]  # 3-iron through PW
    dec_rows = "".join(
        f'<tr><th scope="row">{dec}s</th>'
        + "".join(f"<td>{num(ladder[c]) + '°' if c in ladder else '—'}</td>"
                  for c in show_clubs)
        + f"<td>{len(ms)}</td></tr>"
        for dec, ms, ladder in ((d, ms, iron_ladder(ms)) for d, ms in decades))

    eighties = iron_ladder(sets_of_decade(iron_models, 1980))
    gi_cur = iron_ladder(current_irons_of(iron_models, "game-improvement"))
    n_gi = len(current_irons_of(iron_models, "game-improvement"))

    # For each club of a current game improvement set, the 1980s club that
    # carried the same loft — the "what would this have been called" mapping.
    equiv_rows = []
    for c in ["4", "5", "6", "7", "8", "9", "PW"]:
        if c not in gi_cur:
            continue
        old = nearest_club(eighties, gi_cur[c])
        old_txt = (f"{club_label_long(old[0])} ({num(old[1])}°)" if old
                   else "between clubs")
        equiv_rows.append(
            f'<tr><th scope="row">{club_label_long(c).capitalize()}</th>'
            f"<td>{num(gi_cur[c])}°</td><td>{old_txt}</td></tr>")

    # Who still sells a 3-iron, computed from the confirmed-current sets.
    cur = [m for m in iron_models if is_current(m)]
    with3 = [m for m in cur if club_row(m, "3")]
    start4 = [m for m in cur if club_row(m, "4") and not club_row(m, "3")]
    start5 = [m for m in cur
              if club_row(m, "5") and not club_row(m, "4") and not club_row(m, "3")]
    n_player3 = len([m for m in with3
                     if m.get("category") in ("blade", "players",
                                              "players-distance")])

    eye2 = _model_by_key(iron_models, "ping/eye-2-irons")
    g440 = _model_by_key(iron_models, "ping/g440-irons")
    example_html = ""
    if eye2 and g440:
        ex_clubs = ["3", "4", "5", "6", "7", "8", "9", "PW"]
        def _cell(m, c):
            row = club_row(m, c)
            return f"{num(row['loft'])}°" if row and row.get("loft") is not None else "—"
        ex_rows = "".join(
            f'<tr><th scope="row">{club_label_long(c).capitalize()}</th>'
            f"<td>{_cell(eye2, c)}</td><td>{_cell(g440, c)}</td></tr>"
            for c in ex_clubs)
        example_html = f"""
  <h2>One brand, 43 years apart</h2>
  <p>The cleanest way to see the shift is two game improvement sets from the same
  maker: the <a href="{eye2['url']}">Ping Eye 2</a> ({eye2['year_introduced']}) against
  the <a href="{g440['url']}">Ping G440</a> ({g440['year_introduced']}).</p>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Ping Eye 2 (1982) and Ping G440 (2025) lofts by club — generated from the
    archive.</caption>
    <thead><tr><th scope="col">Club</th><th scope="col">Eye 2 (1982)</th>
    <th scope="col">G440 (2025)</th></tr></thead>
    <tbody>{ex_rows}</tbody></table></div>
  <p class="table-note">The G440's 29° 7-iron sits within half a degree of the Eye 2's
  28.5° 5-iron, and its 42° pitching wedge is two degrees stronger than the Eye 2's
  8-iron. The G440 does not have a 3-iron slot at all: its set starts at a 19° 4-iron —
  two degrees <em>stronger</em> than the Eye 2's 3-iron.</p>
"""

    faq = [
        ("What replaced the 3-iron?",
         "Three things at once. Hybrids took over the slot directly — a 19 to 21 "
         "degree hybrid carries the classic 3-iron loft with far more forgiveness. "
         "Strong-lofted sets quietly renumbered it: many modern 4-irons are 19 to "
         "21 degrees, which is the old 3-iron. And high-lofted fairway woods (7- "
         "and 9-woods) cover the same distances from the turf."),
        ("What loft was a 7-iron 20 years ago?",
         "Around 34 degrees in the mid-2000s, against roughly 29 to 31 degrees in "
         "a current distance set. Go back 40 years and it was 36 to 37 degrees — "
         "the loft now stamped on many 9-irons."),
        ("Is a modern 7-iron really a 5-iron?",
         "By loft, in distance-oriented sets, close to it: a 29 degree modern game "
         "improvement 7-iron matches the 1980s 5-iron almost exactly. But it is "
         "not simply a relabelled blade — the low, deep centre of gravity launches "
         "that loft much higher, so it flies like a 7-iron and carries like a "
         "5-iron. Blades and players irons have moved far less."),
        ("Why did manufacturers keep the same club numbers?",
         "Because numbers sell on comparison. Golfers demo a new 7-iron against "
         "their old 7-iron, and the set that flies ten yards further wins the "
         "sale. Renumbering honestly — calling a 29 degree head a 5-iron — would "
         "erase the headline gain, so the numbers stayed and the lofts moved."),
        ("Do any current sets still use traditional lofts?",
         "Yes — blades and players irons. Current blades still run 34 to 35 "
         "degree 7-irons, essentially the 1990s spec, and most of them still "
         "offer a 3-iron. Loft creep is concentrated in the distance categories."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = knowledge_article_ld(
        "What Replaced the 3-Iron? Iron Number Equivalents", desc,
        f"/guides/{slug}/",
        "what replaced the 3 iron, iron loft changes over time, modern 7 iron "
        "loft vs old, iron number equivalents, loft creep",
        "Golf iron loft history")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>What Replaced the 3-Iron? Iron Number Equivalents by Era</h1>
    <p class="lede">Iron lofts have strengthened by roughly two club numbers since the
    1980s. Here is what each number used to mean — computed from the spec archive, not
    from folklore.</p>
  </div>

  <p><strong>A modern game-improvement 7-iron (about 29°) carries the loft a 5-iron
  carried in the 1980s, and today's 4-irons are stamped with yesterday's 3-iron
  loft.</strong> The 3-iron did not disappear because golfers stopped needing a 20°
  club — it disappeared because that loft is now sold as a 4-iron, a
  <a href="/hybrid-lofts/">hybrid</a> or a high-lofted
  <a href="/fairway-wood-lofts/">fairway wood</a> instead.</p>

  <dl class="facts">
    <div><dt>1980s 7-iron</dt><dd>{num(eighties.get("7", 37))}°</dd></div>
    <div><dt>Current GI 7-iron</dt><dd>{num(gi_cur.get("7", 29))}°</dd></div>
    <div><dt>Shift since the 1980s</dt><dd>~{num(round((eighties.get("7", 37) - gi_cur.get("7", 29)) * 2) / 2)}°</dd></div>
    <div><dt>Current sets with a 3-iron</dt><dd>{len(with3)} of {len(cur)}</dd></div>
    <div><dt>Classic 3-iron loft</dt><dd>20°–21°</dd></div>
  </dl>

  <h2>Iron lofts by decade</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Median loft by club number for the iron sets introduced in each decade —
    generated from the archive.</caption>
    <thead><tr><th scope="col">Decade</th><th scope="col">3</th><th scope="col">4</th>
    <th scope="col">5</th><th scope="col">6</th><th scope="col">7</th>
    <th scope="col">8</th><th scope="col">9</th><th scope="col">PW</th>
    <th scope="col">Sets on file</th></tr></thead>
    <tbody>{dec_rows}</tbody></table></div>
  <p class="table-note">Medians across every set on file for that decade, blades and
  distance sets together — which is why the drift looks gradual; the split by category
  is in the <a href="/guides/strong-vs-traditional-lofts/">strong vs traditional lofts
  guide</a>. Read a column downwards: the 36°–37° that was a 7-iron in the 1980s is a
  9-iron now. Browse the sets behind any decade <a href="/years/">by year</a>.</p>

  <h2>What a modern club was called in the 1980s</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Current game improvement medians ({plural(n_gi, 'confirmed-current set')})
    against the 1980s club with the same loft — generated from the archive.</caption>
    <thead><tr><th scope="col">Club today (GI set)</th><th scope="col">Median loft</th>
    <th scope="col">Closest 1980s equivalent</th></tr></thead>
    <tbody>{''.join(equiv_rows)}</tbody></table></div>
  <p class="table-note">Loft equivalence, not playing equivalence: the modern head
  launches the same loft noticeably higher, so it holds greens the old club with that
  number could not. See every current distance set on the
  <a href="/category/game-improvement/">game improvement category page</a>.</p>

  <h2>Where the 3-iron actually went</h2>
  <p>Of the {plural(len(cur), 'set')} in this archive confirmed as currently sold,
  only {len(with3)} offer a 3-iron at all — and {n_player3} of those are
  <a href="/category/blade/">blade</a>, <a href="/category/players/">players</a> or
  players distance models aimed at strong ball-strikers.
  {plural(len(start4), 'set')} now start at the 4-iron and
  {len(start5)} start at the 5-iron. The stock answer for the top of the bag is a
  <a href="/guides/hybrid-to-iron-conversion/">hybrid in the 19°–24° window</a> or a
  7-wood, both of which fly the old 3-iron distance with a fraction of the difficulty.</p>
  <p>The irony of loft creep is that many modern &ldquo;4-irons&rdquo; <em>are</em>
  3-irons: a 19° game improvement 4-iron is a degree stronger than the 3-iron in a 1982
  set. The number on the sole changed; the loft did not.</p>
{example_html}
  <h2>How to use this when switching sets</h2>
  <p>Compare lofts, not numbers. Moving from a players set to a distance set — or from
  a 1990s set to a current one — slot by slot on the number alone builds in a one- to
  two-club distance jump and, more importantly, a gap at the wedge end: a 42°
  set pitching wedge needs another wedge before your 54°. Pull the loft chart for both
  sets (every model page on this site has one), line the lofts up, and gap from there —
  the <a href="/wedge-lofts/">wedge loft chart</a> covers the bottom of the bag.</p>

  <h2>Related guides</h2>
  {knowledge_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop irons", "golf irons",
                     "Search for new and used iron sets on eBay:")}

  {knowledge_sources("The decade and equivalence tables are computed from the "
                     "archive at build time; the 3-iron availability counts use only "
                     "sets confirmed current in the maker's catalogue.")}
</div>
{guide_sticky_bar("Shop irons", "golf irons")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


# (hybrid number, curated stock-loft band, band midpoint) — the conversion
# chart rows. The iron equivalents per category are computed from the archive.
HYBRID_BANDS = [
    ("2-hybrid", 16, 18, 17),
    ("3-hybrid", 19, 21, 20),
    ("4-hybrid", 22, 24, 23),
    ("5-hybrid", 25, 27, 26),
    ("6-hybrid", 28, 30, 29),
    ("7-hybrid", 31, 34, 32.5),
]


def hybrid_iron_guide(brands, hybrid_models, iron_models):
    """/guides/hybrid-to-iron-conversion/ — which hybrid replaces which iron."""
    slug = "hybrid-to-iron-conversion"
    title = fit_title("Hybrid to Iron Conversion Chart — Which Replaces Which",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "A 19°–21° hybrid replaces a 3-iron, 22°–24° a 4-iron and 25°–27° a "
        "5-iron. ",
        ["Full conversion chart, loft equivalents by set type, and when to make "
         "the switch.",
         "Full conversion chart and when to make the switch.",
         "Conversion chart and switching advice."])

    nav, bc = crumbs([("Home", "/"), ("Hybrid Lofts", "/hybrid-lofts/"),
                      ("Hybrid to Iron Conversion", None)])

    players_l = iron_ladder(current_irons_of(iron_models, "players"))
    gi_l = iron_ladder(current_irons_of(iron_models, "game-improvement"))
    n_players = len(current_irons_of(iron_models, "players"))
    n_gi = len(current_irons_of(iron_models, "game-improvement"))

    conv_rows = "".join(
        f'<tr><th scope="row">{name}</th><td>{lo}°–{hi}°</td>'
        f"<td>{clubs_in_band(players_l, lo, hi)}</td>"
        f"<td>{clubs_in_band(gi_l, lo, hi)}</td></tr>"
        for name, lo, hi, _mid in HYBRID_BANDS)

    # Stock lofts of the confirmed-current hybrid families, so the chart above
    # is backed by what is actually on the rack.
    cur_hy = sorted((m for m in hybrid_models if is_current(m)),
                    key=lambda m: (m["brand"], m["model"]))
    hy_rows = "".join(
        f'<tr><th scope="row"><a href="{m["url"]}">{esc(m["brand"])} '
        f'{esc(m["model"])}</a></th>'
        f'<td>{", ".join(num(l) + "°" for l in driver_lofts(m))}</td></tr>'
        for m in cur_hy)

    g440h = _model_by_key(hybrid_models, "ping/g440-hybrid")
    g440_note = ""
    if g440h:
        g440_note = (f'<p>Manufacturers publish the same mapping. Ping&rsquo;s own '
                     f'gapping chart for the <a href="{g440h["url"]}">G440 hybrid</a> '
                     f"pairs its 17° head with the 2-iron slot, 20° with the 3-iron, "
                     f"23° with the 4-iron, 26° with the 5-iron, 30° with the 6-iron "
                     f"and 34° with the 7-iron — one degree or so weaker than the "
                     f"matching iron at each slot, to cover the hybrid&rsquo;s longer "
                     f"carry.</p>")

    faq = [
        ("What hybrid replaces a 4-iron?",
         "A 22 to 24 degree hybrid for a modern players set, where the 4-iron is "
         "about 23 degrees. If your set is a strong-lofted distance model, check "
         "its chart first: many current game improvement 4-irons are 19 to 21 "
         "degrees, which calls for a 3-hybrid instead."),
        ("What hybrid replaces a 5-iron?",
         "25 to 27 degrees against a players set's 26 degree 5-iron; 22 to 24 "
         "degrees against a distance set's 22 degree 5-iron. Match the loft "
         "printed on your set's spec chart, not the number on the sole."),
        ("Do hybrids go further than the irons they replace?",
         "Usually half a club to a full club further at the same loft. The "
         "hybrid's longer shaft adds clubhead speed and its deeper centre of "
         "gravity adds launch and ball speed. That is why fitters often put you "
         "in a hybrid one or two degrees weaker than the iron coming out."),
        ("When should I switch from irons to hybrids?",
         "When a long iron stops flying high enough to be useful — for most "
         "amateurs that is any iron below about 25 degrees, and at moderate swing "
         "speeds the 5-iron too. A practical test: if your 4-iron and 5-iron "
         "carry within a few yards of each other, the longer one is not earning "
         "its slot and a hybrid will."),
        ("Can I carry both the iron and the matching hybrid?",
         "Only if their lofts differ enough to create a real carry gap — three to "
         "four degrees, like an iron set's 23 degree 4-iron alongside a 19 to 20 "
         "degree hybrid. Two 23 degree clubs is one slot wasted, however "
         "different they look."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = knowledge_article_ld(
        "Hybrid to Iron Conversion Chart", desc, f"/guides/{slug}/",
        "hybrid to iron conversion chart, what hybrid replaces a 4 iron, "
        "hybrid iron equivalent, hybrid loft chart, when to switch to hybrids",
        "Golf hybrid and iron loft equivalence")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Hybrid to Iron Conversion Chart</h1>
    <p class="lede">Which hybrid replaces which iron, why the answer depends on your
    iron set, and when the switch is worth making.</p>
  </div>

  <p><strong>Match the hybrid's loft to the loft of the iron it replaces — not the
  number on the sole.</strong> Against a modern players set that means 19°–21° for the
  3-iron, 22°–24° for the 4-iron and 25°–27° for the 5-iron. Against a strong-lofted
  distance set every slot shifts one club: its 4-iron is the old 3-iron. Expect the
  hybrid to carry about half a club further at the same loft.</p>

  <dl class="facts">
    <div><dt>3-iron slot</dt><dd>19°–21° hybrid</dd></div>
    <div><dt>4-iron slot</dt><dd>22°–24° hybrid</dd></div>
    <div><dt>5-iron slot</dt><dd>25°–27° hybrid</dd></div>
    <div><dt>Same-loft carry bonus</dt><dd>+5–10 yd</dd></div>
    <div><dt>Current hybrid range</dt><dd>17°–34°</dd></div>
  </dl>

  <h2>Hybrid to iron conversion chart</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Which current iron each hybrid loft band replaces — iron figures are the
    medians of confirmed-current sets, generated from the archive
    ({plural(n_players, 'players set')}, {plural(n_gi, 'game improvement set')}).</caption>
    <thead><tr><th scope="col">Hybrid</th><th scope="col">Typical loft</th>
    <th scope="col">Replaces in a players set</th>
    <th scope="col">Replaces in a game improvement set</th></tr></thead>
    <tbody>{conv_rows}</tbody></table></div>
  <p class="table-note">A dash means no club in those sets carries that loft — current
  game improvement sets simply have no 16°–18° iron to replace. The two columns are one
  club apart all the way down: that is <a href="/guides/strong-vs-traditional-lofts/">
  loft creep</a>, and it is why &ldquo;a 4-hybrid replaces a 4-iron&rdquo; is only true
  for some bags.</p>
{g440_note}
  <h2>Stock lofts of current hybrid families</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock lofts of every hybrid family on file confirmed current — generated
    from the archive.</caption>
    <thead><tr><th scope="col">Family</th><th scope="col">Stock lofts</th></tr></thead>
    <tbody>{hy_rows}</tbody></table></div>
  <p class="table-note">The model link opens the family&rsquo;s full chart, including
  lies, lengths and hosel settings; the <a href="/hybrid-lofts/">hybrid loft chart</a>
  adds the discontinued lines and the by-brand adjustability table.</p>

  <h2>Why the hybrid flies further, and what to do about it</h2>
  <p>A hybrid is built on a longer shaft than the matching iron — typically half an
  inch to an inch and a half — and its head puts the centre of gravity lower and
  further back. Both add ball speed and launch, which is the whole point when a long
  iron has stopped flying, but it means a same-loft swap adds carry at the top of the
  bag. Fitters handle it one of two ways: take the hybrid a degree or two weaker than
  the iron it replaces, or take the matching loft and accept that each club above the
  swap point moves up half a slot.</p>
  <p>Either way, verify the result on the course or a launch monitor: the number that
  matters is the carry gap to the longest iron you kept, which should look like every
  other gap in the set — about 10–15 yards.</p>

  <h2>When to make the switch</h2>
  <p>The switch point is where an iron's loft can no longer buy you height. Mis-hit
  tolerance aside, an iron below about 25° needs real clubhead speed to fly its full
  carry and stop on a green; below 21° that is true even for strong players, which is
  why <a href="/guides/iron-number-equivalents/">the 3-iron disappeared from most
  sets</a>. Moderate swing speeds get more from hybrids from the 5-iron up; faster
  players often keep irons to the 4 and carry one 19°–21° hybrid. There is no penalty
  for mixing — most current sets are sold 5–PW precisely because buyers fill the top
  with hybrids.</p>

  <h2>Related guides</h2>
  {knowledge_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop hybrids", "golf hybrid",
                     "Search for new and used hybrids on eBay:")}

  {knowledge_sources("The hybrid loft bands are the stock-loft conventions of "
                     "current manufacturer lines; the iron equivalents and the "
                     "current-family table are computed from the archive at build "
                     "time.")}
</div>
{guide_sticky_bar("Shop hybrids", "golf hybrid")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def lie_angle_guide(brands, iron_models):
    """/guides/lie-angle/ — what lie angle is and the standard lies by iron."""
    slug = "lie-angle"
    title = fit_title("Golf Club Lie Angle Explained", " — Chart & Fitting",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "Lie angle is the angle between shaft and sole: one degree off sends a "
        "7-iron shot about four yards offline. ",
        ["Standard lie chart by iron, and the signs yours is wrong.",
         "Standard lie chart and fitting signs.",
         "Lie chart by iron number."])

    nav, bc = crumbs([("Home", "/"), ("Iron Lofts", "/iron-lofts/"),
                      ("Lie Angle", None)])

    cur = [m for m in iron_models if is_current(m)]
    lie_rows = []
    for c in IRON_CLUB_ORDER[1:]:  # 3-iron through PW
        lies = [row["lie"] for row in (club_row(m, c) for m in cur)
                if row and row.get("lie") is not None]
        if len(lies) < 5:
            continue
        lie_rows.append(
            f'<tr><th scope="row">{club_label_long(c).capitalize()}</th>'
            f"<td>{num(round(median(lies) * 2) / 2)}°</td>"
            f"<td>{num(min(lies))}°–{num(max(lies))}°</td>"
            f"<td>{len(lies)}</td></tr>")

    # A few current sets' 7-iron lies, to show how much "standard" varies.
    example_keys = ["taylormade/p7tw-irons", "mizuno/jpx-925-hot-metal-irons",
                    "ping/g440-irons", "titleist/t100-2025-irons",
                    "taylormade/qi-irons"]
    ex_rows = []
    for key in example_keys:
        m = _model_by_key(iron_models, key)
        if not m:
            continue
        cells = []
        for c in ("5", "7", "9", "PW"):
            row = club_row(m, c)
            cells.append(f"{num(row['lie'])}°"
                         if row and row.get("lie") is not None else "—")
        ex_rows.append(
            f'<tr><th scope="row"><a href="{m["url"]}">{esc(m["brand"])} '
            f'{esc(m["model"])}</a></th>'
            + "".join(f"<td>{v}</td>" for v in cells) + "</tr>")

    faq = [
        ("What is the standard lie angle for irons?",
         "There is no single standard — each maker sets its own — but current "
         "sets cluster tightly: about 61 degrees at the 4-iron, 62 at the 7-iron "
         "and 64 at the pitching wedge, flattening or steepening in half-degree "
         "steps per club. The chart above gives the medians and ranges across "
         "every confirmed-current set in this archive."),
        ("What does an upright lie angle do to ball flight?",
         "Too upright for your build and delivery, the toe sits up at impact and "
         "the face points left of the target (for a right-hander); too flat and "
         "it points right. The error scales with loft, so it shows up most in "
         "short irons and wedges — the clubs you aim with."),
        ("How do I tell if my lie angles are wrong?",
         "Three signs. A persistent one-way miss with the short irons that your "
         "swing does not explain. Divots deeper on one side than the other. And "
         "the classic test: a strip of impact tape on the sole (or marker ink on "
         "the ball) and a few shots off a lie board — a scuff towards the heel "
         "means too upright, towards the toe means too flat."),
        ("Can lie angle be adjusted after purchase?",
         "Usually, by one to two degrees. Forged heads bend easily and most cast "
         "heads will take a degree or so at a fitter's loft-and-lie machine, "
         "though some hard cast alloys are brittle and resist bending. Many "
         "makers also build to order — Ping's colour-coded dots, for instance, "
         "span several degrees either side of standard."),
        ("Does lie angle matter for drivers and woods?",
         "Far less. The driver's low loft converts a lie error into very little "
         "face misdirection, and the ball is swept off a tee rather than struck "
         "down into the turf. Fitting attention belongs on the irons and "
         "wedges, where loft is high and the sole meets the ground."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = knowledge_article_ld(
        "Golf Club Lie Angle Explained", desc, f"/guides/{slug}/",
        "lie angle golf, what is lie angle, standard lie angle irons, "
        "upright vs flat lie, lie angle chart",
        "Golf club lie angle")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Club Lie Angle Explained</h1>
    <p class="lede">The spec that aims your irons. What lie angle is, the standard lies
    by club computed from current sets, and how to tell if yours fit.</p>
  </div>

  <p><strong>Lie angle is the angle between the shaft and the ground when the club
  sits on its sole.</strong> If it matches your posture and delivery, the face points
  where you aimed; if it is off, the face points offline at impact even on a perfect
  swing — roughly four yards per degree with a 7-iron at normal distances, and more as
  loft goes up. It is the quietest cause of a one-way miss in golf, which is why a lie
  check is the first station of any iron fitting.</p>

  <dl class="facts">
    <div><dt>4-iron (median)</dt><dd>~60.5°</dd></div>
    <div><dt>7-iron (median)</dt><dd>~62°</dd></div>
    <div><dt>PW (median)</dt><dd>~64°</dd></div>
    <div><dt>Step per club</dt><dd>~0.5°</dd></div>
    <div><dt>Miss per 1° error (7-iron)</dt><dd>~4 yd</dd></div>
  </dl>

  <h2>Standard iron lie angles</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Lie angle by club across the {plural(len(cur), 'confirmed-current iron set')}
    in the archive — generated from the archive.</caption>
    <thead><tr><th scope="col">Club</th><th scope="col">Median lie</th>
    <th scope="col">Range on file</th><th scope="col">Sets</th></tr></thead>
    <tbody>{''.join(lie_rows)}</tbody></table></div>
  <p class="table-note">Lie climbs about half a degree per club because shafts get
  shorter down the set — a shorter club stands more upright by geometry. The
  three-degree spread at any one club is each maker&rsquo;s own standard, which is why
  switching brands can change your lie without anyone deciding to.</p>

  <h2>&ldquo;Standard&rdquo; differs by maker</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock lie angles of a few current sets, by club — generated from the
    archive.</caption>
    <thead><tr><th scope="col">Set</th><th scope="col">5-iron</th>
    <th scope="col">7-iron</th><th scope="col">9-iron</th><th scope="col">PW</th></tr></thead>
    <tbody>{''.join(ex_rows)}</tbody></table></div>
  <p class="table-note">A degree and a half separates the flattest and most upright
  stock 7-irons here — as much as many fitters would ever bend a club. Every model page
  in this archive lists lie alongside loft, so you can check a prospective set against
  your current one before buying.</p>

  <h2>Upright or flat: which do you need?</h2>
  <p>At address the sole should sit flush. At <em>impact</em> is what matters, and
  impact dynamics droop the toe as the shaft bows, so static eyeballing misleads.
  The reliable evidence: where the sole scuffs a lie board, where your divots are
  deepest, and which way your well-struck short irons start. Heel contact and shots
  starting left of your path mean too upright — you need flatter. Toe contact and
  shots leaking right mean too flat — you need more upright. (Reverse both for
  left-handers.)</p>
  <p>Taller players and those with very upright postures tend to need upright lies;
  shorter players and flat-swingers the opposite — but hand position at impact matters
  more than height, so test rather than assume. One to two degrees of bend covers
  almost everyone, and a fitter does it in minutes on forged heads.</p>

  <h2>Lie and loft travel together</h2>
  <p>Lie only aims the face because loft tilts it: the higher the loft, the more a lie
  error rotates the face off target, which is why a mis-fit lob wedge misses greens a
  mis-fit 4-iron would hit. It is also why lie angles have barely moved while
  <a href="/guides/strong-vs-traditional-lofts/">lofts strengthened dramatically</a> —
  a 1972 Ben Hogan Apex 7-iron stood at 61.5°, within a degree of today's median. Loft
  is fashion; lie is geometry. The full spec chart for any set — loft, lie and length
  per club — is on its model page, starting from the
  <a href="/iron-lofts/">iron loft chart</a>.</p>

  <h2>Related guides</h2>
  {knowledge_guide_cards(exclude=slug)}

  {faq_html}

  {knowledge_sources("The lie tables are computed from the archive at build time, "
                     "over sets confirmed current in the maker's catalogue; the "
                     "yards-per-degree figure is the standard club-fitting "
                     "approximation for a mid iron at typical amateur distances.")}
</div>
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def loft_explained_guide(brands, models):
    """/guides/golf-club-loft-explained/ — the beginner's what-is-loft page."""
    slug = "golf-club-loft-explained"
    title = fit_title("What Is Loft in Golf? Golf Club Loft Explained",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "Loft is the clubface angle that sets launch, spin and distance — from "
        "9° drivers to 60° lob wedges. ",
        ["A beginner's guide with real lofts for every club type.",
         "A beginner's guide with real examples.",
         "Beginner guide with real lofts."])

    nav, bc = crumbs([("Home", "/"), ("Golf Club Loft Explained", None)])

    # Loft span per club type across the confirmed-current models on file.
    def wood_span(t):
        lofts = [l for m in models if m["club_type"] == t and is_current(m)
                 for l in driver_lofts(m)]
        return (num(min(lofts)), num(max(lofts))) if lofts else None

    iron_cur = [m for m in models if m["club_type"] == "irons" and is_current(m)]
    # 4-iron through PW: the clubs every set shares. 2- and 3-irons exist (down
    # to a 14° driving iron) but would stretch a beginner's table misleadingly.
    iron_lofts_all = [row["loft"] for m in iron_cur for c in IRON_CLUB_ORDER[2:]
                      for row in [club_row(m, c)] if row and row.get("loft")]
    wedge_cur = [m for m in models if m["club_type"] == "wedges" and is_current(m)]
    wedge_lofts_all = [l for m in wedge_cur for l in wedge_lofts(m)]

    spans = []
    for label, url, span, role in (
        ("Driver", "/driver-lofts/", wood_span("driver"),
         "Maximum distance off the tee; lowest loft in the bag"),
        ("Fairway woods", "/fairway-wood-lofts/", wood_span("fairway_wood"),
         "Long shots from tee and turf"),
        ("Hybrids", "/hybrid-lofts/", wood_span("hybrid"),
         "Long-iron replacements, easier to launch"),
        ("Irons (4-iron to PW)", "/iron-lofts/",
         (num(min(iron_lofts_all)), num(max(iron_lofts_all)))
         if iron_lofts_all else None,
         "The scoring ladder — one loft step per club"),
        ("Wedges", "/wedge-lofts/",
         (num(min(wedge_lofts_all)), num(max(wedge_lofts_all)))
         if wedge_lofts_all else None,
         "Short game: height and stopping power over distance"),
    ):
        if span:
            spans.append(f'<tr><th scope="row"><a href="{url}">{label}</a></th>'
                         f"<td>{span[0]}°–{span[1]}°</td><td>{role}</td></tr>")

    mb = _model_by_key(models, "titleist/620-mb-irons")
    gt = _model_by_key(models, "yonex/ezone-gt-irons")
    brand_example = ""
    if mb and gt:
        mb7, gt7 = club_row(mb, "7"), club_row(gt, "7")
        if mb7 and gt7:
            brand_example = (
                f'<p>The spread is real, not rounding. The '
                f'<a href="{mb["url"]}">Titleist 620 MB</a>, a current blade, stamps '
                f"&ldquo;7&rdquo; on a {num(mb7['loft'])}° head; the "
                f'<a href="{gt["url"]}">Yonex EZONE GT</a>, a current '
                f"super-game-improvement set, stamps the same number on a "
                f"{num(gt7['loft'])}° head. Ten degrees — nearly three clubs&rsquo; "
                f"worth of loft — under one label. Both are honest designs for "
                f"different golfers; the label is just not the spec.</p>")

    faq = [
        ("What does loft mean on a golf club?",
         "The angle between the clubface and the shaft axis — effectively how "
         "far the face tilts back from vertical. More loft sends the ball "
         "higher with more backspin and less distance; less loft sends it "
         "lower, further and with more roll."),
        ("How much does loft affect distance?",
         "It is the main reason clubs go different distances. Within an iron "
         "set, each club is about 3 to 4 degrees apart, which works out to "
         "roughly 10 to 15 yards of carry per club for most golfers. Shaft "
         "length adds a little speed club to club, but loft does most of the "
         "work."),
        ("Is lower loft always longer?",
         "Only when your swing is fast enough to launch it. A low-lofted club "
         "needs clubhead speed to get the ball up and carrying; without it, the "
         "ball flies low and dies. That is why beginners usually hit a 5-wood "
         "past a 3-wood and a hybrid past the long iron it replaced."),
        ("Why do lofts vary between brands?",
         "No governing body sets lofts, so each maker chooses its own — and "
         "distance-oriented designs use stronger (lower) lofts because their "
         "low centre of gravity restores the launch. The same club number can "
         "differ by six degrees or more between two current sets, which is why "
         "this site charts the actual lofts per model."),
        ("What is dynamic loft?",
         "The loft the face actually presents at impact, after shaft lean and "
         "shaft bend have added or removed a few degrees from the number "
         "stamped on the club. Good iron players deloft the face slightly; a "
         "scooping release adds loft. Launch monitors measure it directly."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = knowledge_article_ld(
        "Golf Club Loft Explained", desc, f"/guides/{slug}/",
        "what is loft in golf, golf club loft explained, loft meaning golf, "
        "golf club degrees chart, loft and distance",
        "Golf club loft")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Club Loft Explained</h1>
    <p class="lede">What loft is, how it shapes trajectory and distance, and the real
    loft ranges for every club type — the beginner&rsquo;s page the rest of this site
    builds on.</p>
  </div>

  <p><strong>Loft is the backward tilt of the clubface, measured in degrees from
  vertical.</strong> It is the single spec that most decides what a club does: a 9°
  driver face sends the ball out low and fast; a 60° lob wedge sends the same swing
  almost straight up. Every other club in the bag sits on the ladder between them,
  spaced a few degrees apart so each one carries a different distance.</p>

  <dl class="facts">
    <div><dt>Driver</dt><dd>8°–12°</dd></div>
    <div><dt>7-iron</dt><dd>28°–35°</dd></div>
    <div><dt>Pitching wedge</dt><dd>41°–48°</dd></div>
    <div><dt>Lob wedge</dt><dd>58°–60°</dd></div>
    <div><dt>Gap between clubs</dt><dd>3°–4°</dd></div>
  </dl>

  <h2>Loft ranges across the bag</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock loft ranges by club type across the confirmed-current models in the
    archive — generated from the archive.</caption>
    <thead><tr><th scope="col">Club type</th><th scope="col">Lofts on file</th>
    <th scope="col">What it is for</th></tr></thead>
    <tbody>{''.join(spans)}</tbody></table></div>
  <p class="table-note">Each club-type link opens the full chart: typical lofts by club
  number, the stock lofts per brand, and the per-model spec pages behind them.</p>

  <h2>What loft actually does</h2>
  <p>At impact, loft splits the clubhead&rsquo;s speed between forward ball speed and
  upward launch with backspin. Low loft keeps most of the energy going forward — fast,
  flat and long, but hard to get airborne without clubhead speed. High loft trades ball
  speed for height and spin — shorter, but easy to launch, quick to stop on a green and
  far more tolerant of an imperfect strike. That trade is the architecture of the
  whole bag: distance clubs at the low-loft end, scoring clubs at the high-loft end.</p>
  <p>Loft also shrinks your misses. The more loft on the face, the more backspin
  dominates sidespin, so curved shots curve less — one reason beginners' slices are
  worst with the driver and vanish with the 9-iron, and why the standard advice for a
  new golfer is <a href="/guides/best-driver-loft-for-beginners/">more driver loft, not
  less</a>.</p>

  <h2>Why the same number means different lofts</h2>
  <p>Club numbers are labels, not measurements. No rule defines what a 7-iron is, and
  manufacturers have strengthened lofts steadily for forty years as low-CG designs made
  stronger lofts launchable — the full story is in the
  <a href="/guides/strong-vs-traditional-lofts/">strong vs traditional lofts guide</a>
  and the <a href="/guides/iron-number-equivalents/">iron number equivalents chart</a>.</p>
  {brand_example}
  <h2>Using loft when you buy</h2>
  <p>Compare clubs by loft, not by number or by marketing category. When a new set
  claims an extra ten yards, check its loft chart first — most of the gain is usually
  a stronger loft, which you could also get by hitting one more club. When gapping a
  bag, write down the loft of every club from driver to lob wedge and look for even
  3°–5° steps; holes and bunches in that ladder are where your distance gaps come from.
  Every model page on this site lists the full chart, and the
  <a href="/compare/">compare pages</a> put two sets side by side.</p>

  <h2>Related guides</h2>
  {knowledge_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop golf clubs", "golf clubs",
                     "Search for new and used clubs on eBay:")}

  {knowledge_sources("The loft-range table is computed from the archive at build "
                     "time over confirmed-current models; the facts panel uses the "
                     "accepted retail conventions for each club type.")}
</div>
{guide_sticky_bar("Shop golf clubs", "golf clubs")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def strong_vs_traditional_guide(brands, iron_models):
    """/guides/strong-vs-traditional-lofts/ — the loft creep debate, with the
    archive's own numbers on both sides."""
    slug = "strong-vs-traditional-lofts"
    title = fit_title("Strong vs Traditional Iron Lofts — Loft Creep",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "Strong lofts run 3°–5° lower than traditional: a 29° game-improvement "
        "7-iron against 34°–35° on a blade. ",
        ["What loft creep means for distance, gapping and set makeup.",
         "What loft creep means for distance and gapping.",
         "The loft creep debate with real data."])

    nav, bc = crumbs([("Home", "/"), ("Iron Lofts", "/iron-lofts/"),
                      ("Strong vs Traditional Lofts", None)])

    cats = ["blade", "players", "players-distance", "game-improvement",
            "super-game-improvement"]
    show_clubs = ["4", "5", "6", "7", "8", "9", "PW"]
    cat_rows = []
    for c in cats:
        ms = current_irons_of(iron_models, c)
        if not ms:
            continue
        ladder = iron_ladder(ms, show_clubs)
        cat_rows.append(
            f'<tr><th scope="row"><a href="/category/{esc(c)}/">'
            f"{esc(CATEGORY_LABEL.get(c, c))}</a></th>"
            + "".join(f"<td>{num(ladder[cl]) + '°' if cl in ladder else '—'}</td>"
                      for cl in show_clubs)
            + f"<td>{len(ms)}</td></tr>")

    # 7-iron creep by decade — median and range over every set on file.
    creep_rows = []
    for dec in (1980, 1990, 2000, 2010, 2020):
        ms = sets_of_decade(iron_models, dec)
        sevens = [row["loft"] for row in (club_row(m, "7") for m in ms)
                  if row and row.get("loft") is not None]
        if not sevens:
            continue
        creep_rows.append(
            f'<tr><th scope="row">{dec}s</th>'
            f"<td>{num(round(median(sevens) * 2) / 2)}°</td>"
            f"<td>{num(min(sevens))}°–{num(max(sevens))}°</td>"
            f"<td>{len(sevens)}</td></tr>")

    blade_l = iron_ladder(current_irons_of(iron_models, "blade"))
    gi_l = iron_ladder(current_irons_of(iron_models, "game-improvement"))

    faq = [
        ("What are strong lofts in golf?",
         "Lofts set several degrees lower than the traditional number for that "
         "club — a 7-iron at 28 to 31 degrees instead of 34 to 35. Manufacturers "
         "pair them with low-CG heads that restore the launch height, so the club "
         "flies as high as the old loft did but carries further."),
        ("Are strong lofts cheating?",
         "No — but they complicate comparisons. Nothing in the rules defines "
         "club numbers, and a strong-lofted head genuinely launches its loft "
         "higher than an older design could. The honest criticism is about "
         "marketing: a distance gain that comes mostly from loft looks like a "
         "technology gain when the club numbers hide it."),
        ("Do strong lofted irons actually go further?",
         "Yes, by roughly one club per 3 to 4 degrees — that part is simple "
         "geometry. The questions worth asking are whether the ball still flies "
         "high enough to hold greens (in a well-designed head, usually yes) and "
         "what happens at the wedge end of the set, where a 42 degree pitching "
         "wedge leaves a bigger gap to your sand wedge."),
        ("Should I play strong or traditional lofts?",
         "Match the design to your launch, not to the distance claim. Slower "
         "swings and low-ball hitters benefit from strong-lofted heads because "
         "the design adds the height they lack. Faster swings that already "
         "launch high lose nothing with traditional lofts and keep tighter "
         "wedge gapping and more consistent spin. A launch monitor settles it "
         "in ten shots."),
        ("Why does my new 7-iron go further than my old one?",
         "Check both loft charts before crediting the face technology. If the "
         "new 7-iron is 29 degrees and the old one was 33, you are comparing "
         "different clubs with the same label — most of the gain is loft. Every "
         "model page on this site lists the chart, and the compare pages put "
         "two sets side by side."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = knowledge_article_ld(
        "Strong vs Traditional Iron Lofts", desc, f"/guides/{slug}/",
        "strong lofts vs traditional lofts, loft creep golf, jacked lofts, "
        "strong lofted irons, game improvement vs blade lofts",
        "Golf iron loft design")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Strong vs Traditional Iron Lofts</h1>
    <p class="lede">What &ldquo;strong lofts&rdquo; means, how far loft creep has
    actually gone, and how to compare sets honestly — with the numbers computed from
    the spec archive.</p>
  </div>

  <p><strong>Strong lofts are club lofts set 3°–6° lower than the traditional number
  for that club.</strong> Across the sets in this archive confirmed as currently sold,
  the median blade 7-iron is {num(blade_l.get("7", 34))}° and the median game
  improvement 7-iron is {num(gi_l.get("7", 29))}° — about a club and a half apart under
  the same stamped number. Neither is wrong; they are different designs for different
  launch needs. The problems start when sets are compared by number as if the numbers
  meant the same thing.</p>

  <dl class="facts">
    <div><dt>Blade 7-iron (median)</dt><dd>{num(blade_l.get("7", 34))}°</dd></div>
    <div><dt>GI 7-iron (median)</dt><dd>{num(gi_l.get("7", 29))}°</dd></div>
    <div><dt>Blade PW (median)</dt><dd>{num(blade_l.get("PW", 46))}°</dd></div>
    <div><dt>GI PW (median)</dt><dd>{num(gi_l.get("PW", 42.5))}°</dd></div>
    <div><dt>1980s → 2020s 7-iron</dt><dd>37° → 30.5°</dd></div>
  </dl>

  <h2>Current lofts by category</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Median loft by club for the confirmed-current sets in each category —
    generated from the archive.</caption>
    <thead><tr><th scope="col">Category</th><th scope="col">4</th><th scope="col">5</th>
    <th scope="col">6</th><th scope="col">7</th><th scope="col">8</th>
    <th scope="col">9</th><th scope="col">PW</th><th scope="col">Sets</th></tr></thead>
    <tbody>{''.join(cat_rows)}</tbody></table></div>
  <p class="table-note">Read any row against the blade row: the game improvement ladder
  sits one full club ahead all the way down. The category links open every set on file,
  and the <a href="/category/">category guide</a> explains what separates the
  designs.</p>

  <h2>Loft creep, decade by decade</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>7-iron lofts of the sets introduced in each decade — generated from the
    archive.</caption>
    <thead><tr><th scope="col">Decade</th><th scope="col">Median 7-iron</th>
    <th scope="col">Range</th><th scope="col">Sets on file</th></tr></thead>
    <tbody>{''.join(creep_rows)}</tbody></table></div>
  <p class="table-note">The medians mix blades and distance sets, so the creep is
  steeper than it looks: the traditional end of each range has barely moved since the
  1990s, while the strong end dropped from 32° to 25°. The club-by-club version is in
  the <a href="/guides/iron-number-equivalents/">iron number equivalents guide</a>.</p>

  <h2>The case for strong lofts</h2>
  <p>Modern distance heads earn their lofts. Thin faces flex and add ball speed; low,
  deep centres of gravity and wide soles launch the ball several degrees higher from
  the same loft than a blade can. Give that head a traditional 34° and it balloons —
  so designers take the extra launch back as loft and sell the difference as carry.
  For the golfer who hits the ball low, that trade is real help: a 29° 7-iron they can
  launch beats a 34° one they cannot.</p>

  <h2>The case against</h2>
  <p>Three honest costs. First, comparison becomes meaningless: &ldquo;this 7-iron
  goes further than that one&rdquo; says nothing when the lofts differ by five degrees.
  Second, gapping: a set whose pitching wedge is {num(gi_l.get("PW", 42.5))}° leaves a
  wide hole to a 54°–56° sand wedge, which is why strong-lofted sets ship with gap
  wedges and why the <a href="/wedge-lofts/gap-wedge/">gap wedge</a> exists at all.
  Third, the short irons: strong lofts mean less spin on approach shots, and at some
  point a 9-iron that flies like an 8-iron stops checking like a 9-iron.</p>

  <h2>See it in real sets</h2>
  <p>The cleanest live comparisons are same-brand pairs sold side by side:
  <a href="/compare/mizuno-jpx-925-forged-vs-jpx-925-hot-metal/">Mizuno JPX-925 Forged
  vs Hot Metal</a> (30° vs 28° 7-irons from one catalogue) and
  <a href="/compare/titleist-620-cb-vs-t100/">Titleist 620 CB vs T100</a> (35° vs 33°).
  For the full spread, put any <a href="/category/blade/">blade</a> next to any
  <a href="/category/game-improvement/">game improvement set</a> on their model pages —
  every chart lists loft, lie and length per club.</p>

  <h2>How to compare sets honestly</h2>
  <p>Ignore the numbers on the soles. Line up both loft charts, match clubs by loft,
  and compare carry and height loft-for-loft on a launch monitor. Then check the wedge
  end: count the degrees from the set&rsquo;s pitching wedge to your sand wedge and
  make sure a <a href="/wedge-lofts/">wedge ladder</a> of 4°–6° steps fits in between.
  A set that wins loft-for-loft is genuinely better for you; a set that only wins
  number-for-number is a relabelling.</p>

  <h2>Related guides</h2>
  {knowledge_guide_cards(exclude=slug)}

  {faq_html}

  {guide_shop_block("Shop iron sets", "golf iron set",
                     "Search for new and used iron sets on eBay:")}

  {knowledge_sources("The category and decade tables are computed from the archive "
                     "at build time; the launch and spin mechanics are the accepted "
                     "club-design conventions and hold for well-struck shots.")}
</div>
{guide_sticky_bar("Shop iron sets", "golf iron set")}
"""
    page(f"/guides/{slug}/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def knowledge_pages(brands, models, iron_models, hybrid_models):
    iron_equivalents_guide(brands, iron_models)
    hybrid_iron_guide(brands, hybrid_models, iron_models)
    strong_vs_traditional_guide(brands, iron_models)
    lie_angle_guide(brands, iron_models)
    loft_explained_guide(brands, models)


# --------------------------------------------------------------------------
# club-type hub pages — /iron-lofts/, /fairway-wood-lofts/, /hybrid-lofts/
#
# The wedge and driver hubs (wedge_index, driver_index) predate these; the
# three below complete the set so the nav can offer one landing page per club
# type. Same contract as the older hubs: an answer-first lede, a reference
# chart, the brand table generated from the spec archive, and the model cards.
# --------------------------------------------------------------------------

# Month the fairway wood and hybrid brand tables were last checked against the
# archive — the wood files all carry current_as_of from the October 2026 pass.
WOOD_CHECKED = "2026-10"


def hub_article_ld(headline, desc, path, keywords, about):
    return {
        "@context": "https://schema.org", "@type": "TechArticle",
        "headline": headline,
        "description": desc,
        "datePublished": HUB_PUBLISHED, "dateModified": HUB_REVIEWED,
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + path},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "about": {"@type": "Thing", "name": about},
        "keywords": keywords,
    }


def hub_sources(first_bullet, checked):
    return f"""<div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>{first_bullet}</li>
    <li>Brand and model figures come from the LoftChart spec archive &mdash; the
    per-model pages linked above, each compiled from the manufacturer&rsquo;s own spec
    sheets and source-attributed &mdash; last verified in {long_date(checked)}.</li>
  </ul>
  <p>Last reviewed {long_date(HUB_REVIEWED)}. Spot an error? {email_link()}</p></div>"""


def iron_index(brands, iron_models, by_cat):
    """The /iron-lofts/ hub — the 'iron loft chart' overview page."""
    title = fit_title("Iron Loft Chart — Lofts by Club, Category & Era",
                      f" | {SITE_NAME}")
    n_brands = len({m["brand_slug"] for m in iron_models})
    desc = fit_desc(
        "A modern 7-iron runs 28°–35° — about 34° on blades, 29° on game "
        "improvement irons. ",
        [f"Iron loft charts for {plural(len(iron_models), 'set')} across "
         f"{plural(n_brands, 'brand')}, 1960s to today.",
         f"Iron loft charts for {plural(len(iron_models), 'set')}, "
         "1960s to today.",
         "Iron loft charts by brand, year and category."])

    nav, bc = crumbs([("Home", "/"), ("Iron Lofts", None)])

    club_rows = "".join(
        f'<tr><th scope="row">{club}</th><td>{trad}</td><td>{players}</td>'
        f"<td>{gi}</td></tr>"
        for club, trad, players, gi in (
            ("3-iron", "20°–21°", "19°–21°", "18°–19°"),
            ("4-iron", "23°–24°", "22°–24°", "20.5°–22°"),
            ("5-iron", "26°–28°", "25°–27°", "23°–25°"),
            ("6-iron", "30°–31°", "28°–30°", "26°–28°"),
            ("7-iron", "34°–35°", "32°–34°", "28°–31°"),
            ("8-iron", "38°–39°", "36°–38°", "32°–35.5°"),
            ("9-iron", "42°–43°", "40°–42°", "37°–40.5°"),
            ("PW", "46°–48°", "44°–46°", "41°–45°"),
        ))

    # 7-iron loft by category, computed from the archive: every set on file
    # for the count, confirmed-current sets only for the loft figures.
    # by_cat now spans every club type; this table is the iron story only.
    by_cat = {c: [m for m in ms_ if m["club_type"] == "irons"]
              for c, ms_ in by_cat.items()}
    by_cat = {c: ms_ for c, ms_ in by_cat.items() if ms_}
    order = ["blade", "players", "players-distance", "game-improvement",
             "super-game-improvement"]
    cats = [c for c in order if c in by_cat] + [c for c in by_cat if c not in order]
    cat_rows = []
    for c in cats:
        ms = by_cat[c]
        cur = [s7["loft"] for s7 in (seven_iron(m) for m in ms if is_current(m))
               if s7 and s7.get("loft") is not None and str(s7.get("club")) == "7"]
        med = f"{num(median(cur))}°" if cur else "—"
        span = (f"{num(min(cur))}°–{num(max(cur))}°"
                if len(cur) > 1 and min(cur) != max(cur) else med)
        cat_rows.append(
            f'<tr><th scope="row"><a href="/category/{esc(c)}/">'
            f'{esc(CATEGORY_LABEL.get(c, c))}</a></th>'
            f"<td>{len(ms)}</td><td>{med}</td><td>{span}</td></tr>")

    recent = sorted(iron_models,
                    key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))[:8]

    faq = [
        ("What loft is a 7-iron?",
         "Between about 28° and 35° depending on the set. Traditional and blade "
         "irons sit at 34°–35°, modern players irons around 32°–34°, and "
         "distance-oriented game improvement sets as low as 28°. That spread is "
         "why two golfers' 7-irons can fly a club and a half apart."),
        ("Why do iron lofts vary so much between sets?",
         "Lofts have been strengthened steadily since the 1980s. Perimeter "
         "weighting and thin faces launch the ball higher from the same loft, so "
         "manufacturers took loft off each head to turn the extra height into "
         "distance — and the club numbers stayed where they were."),
        ("Are stronger lofts actually longer?",
         "Only when the head design restores the launch the loft took away. A "
         "28° game improvement 7-iron with a low centre of gravity flies like a "
         "well-struck traditional 6-iron; the same loft on a blade would launch "
         "too low to hold a green. Compare sets by loft and carry, not number."),
        ("What loft is a pitching wedge?",
         "Between 41° and 48°, matched to the set it comes with: strong-lofted "
         "distance sets ship 41°–44° pitching wedges, traditional sets 46°–48°. "
         "The full breakdown is on the wedge loft chart."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = hub_article_ld(
        "Iron Loft Chart", desc, "/iron-lofts/",
        "iron loft chart, 7 iron loft, iron lofts by brand, standard iron lofts, "
        "strong lofted irons", "Golf iron loft")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Iron Loft Chart</h1>
    <p class="lede">What degree each iron is, how lofts differ by set category, and why
    the same club number can vary by six degrees between brands.</p>
  </div>

  <p><strong>There is no single standard iron loft.</strong> A modern 7-iron runs from
  about 34°–35° in blades and traditional sets down to 28°–31° in distance-oriented game
  improvement sets. Lofts have been strengthened steadily since the 1980s, which is why
  comparing sets by club number alone is misleading — and why every chart in this archive
  records the year the set was introduced.</p>

  <dl class="facts">
    <div><dt>Blade 7-iron</dt><dd>~34°</dd></div>
    <div><dt>Players 7-iron</dt><dd>32°–34°</dd></div>
    <div><dt>Game improvement 7-iron</dt><dd>28°–31°</dd></div>
    <div><dt>Set pitching wedge</dt><dd>41°–48°</dd></div>
    <div><dt>Loft gap between clubs</dt><dd>3°–4°</dd></div>
  </dl>

  <h2>Typical iron lofts by club</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Typical loft bands by club number — traditional sets against the two main
    modern categories.</caption>
    <thead><tr><th scope="col">Club</th><th scope="col">Traditional (pre-1990s)</th>
    <th scope="col">Modern players</th><th scope="col">Modern game improvement</th></tr></thead>
    <tbody>{club_rows}</tbody></table></div>
  <p class="table-note">Bands, not standards: no governing body defines iron lofts, and
  individual sets sit outside these ranges. Look up the exact chart for any set via the
  <a href="/brands/">brand index</a> or <a href="/years/">by year</a>.</p>

  <h2>7-iron loft by category</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>7-iron lofts across the LoftChart archive; loft figures are from sets
    confirmed current as of {long_date(HUB_REVIEWED)}.</caption>
    <thead><tr><th scope="col">Category</th><th scope="col">Sets on file</th>
    <th scope="col">Current median</th><th scope="col">Current range</th></tr></thead>
    <tbody>{''.join(cat_rows)}</tbody></table></div>
  <p class="table-note">The category link opens every set on file, current and
  discontinued. The <a href="/category/">category guide</a> explains what separates a
  blade from a players iron.</p>

  <h2>Why iron lofts got stronger</h2>
  <p>Perimeter weighting, thin fast faces and low centres of gravity launch the ball
  higher from the same loft. Manufacturers spent that extra height on distance by taking
  loft off each head — roughly a degree per decade in the game improvement category —
  while the numbers stamped on the soles stayed put. The result: a 1985 game improvement
  7-iron at 36° and a 2025 one at 28° are, by loft, two different clubs.</p>
  <p>Neither is wrong. The strong-lofted head still flies high because the design
  launches it; the traditional head still carries its distance on spin and control. What
  matters when switching sets is the loft and carry of each slot, not the number — and
  that the gap to your wedges stays even, which is where the
  <a href="/wedge-lofts/">wedge loft chart</a> takes over.</p>

  <h2>Recently released iron sets on file</h2>
  <div class="grid">{''.join(model_card(m) for m in recent)}</div>
  <p>The archive holds {plural(len(iron_models), 'iron set')} across
  {plural(n_brands, 'brand')}, from current lines to 1960s vintage sets whose spec sheets
  have left the manufacturer sites. Browse the <a href="/brands/">brand index</a>,
  <a href="/years/">by year</a> or <a href="/category/">by category</a>.</p>

  <h2>Iron loft guides</h2>
  {knowledge_guide_cards(only=("iron-number-equivalents",
                               "strong-vs-traditional-lofts", "lie-angle",
                               "golf-club-loft-explained"))}

  {faq_html}

  {guide_shop_block("Shop irons", "golf irons",
                     "Search for new and used iron sets on eBay:")}

  {hub_sources("Loft bands are drawn from the archive itself and from accepted "
               "club-fitting conventions, given as ranges because no governing body "
               "defines iron lofts.", HUB_REVIEWED)}
</div>
{guide_sticky_bar("Shop irons", "golf irons")}
"""
    page("/iron-lofts/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def fairway_index(brands, fw_models):
    """The /fairway-wood-lofts/ hub — the 'fairway wood loft chart' page."""
    title = fit_title("Fairway Wood Loft Chart — 3, 5 & 7 Wood Degrees",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "A 3-wood is 15°, a 5-wood 18°–19° and a 7-wood 21°–22°. ",
        [f"Stock fairway wood lofts by brand, which wood replaces which iron, "
         f"and charts for {plural(len(fw_models), 'family')}.",
         "Stock fairway wood lofts by brand, plus which wood replaces which iron.",
         "Stock fairway wood lofts for every major brand."])

    nav, bc = crumbs([("Home", "/"), ("Fairway Wood Lofts", None)])

    band_rows = "".join(
        f'<tr><th scope="row">{wood}</th><td>{loft}</td><td>{replaces}</td>'
        f"<td>{role}</td></tr>"
        for wood, loft, replaces, role in (
            ("3-wood", "13.5°–16.5°", "—",
             "Distance off the tee and long par 5s; 15° is the standard"),
            ("4-wood", "16°–17.5°", "2-iron",
             "The 3/5-wood tweener, easier to flight than a 3-wood"),
            ("5-wood", "17.5°–19.5°", "2–3 iron / 3-hybrid",
             "The most versatile fairway loft for most golfers"),
            ("7-wood", "20.5°–22.5°", "3–4 iron / 4-hybrid",
             "High, soft-landing long approach club"),
            ("9-wood", "23.5°–26.5°", "4–5 iron",
             "Maximum height; increasingly common even on tour"),
        ))

    brand_rows = "".join(
        f'<tr><th scope="row"><a href="/{esc(m["brand_slug"])}/">{esc(m["brand"])}</a></th>'
        f'<td><a href="{m["url"]}">{esc(m["model"])}</a>'
        + (f' ({m["year_introduced"]})' if m.get("year_introduced") else "")
        + f"</td><td>{esc(lofts)}</td><td>{esc(adj)}</td></tr>"
        for m, lofts, adj in driver_brand_rows(fw_models))

    recent = sorted(fw_models,
                    key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))

    faq = [
        ("What loft is a 3-wood?",
         "15° is the standard, with stock options running from about 13.5° on "
         "low-spin tour heads to 16.5° on high-launch builds. Most adjustable "
         "hosels move that by a degree or so in each direction."),
        ("Should I carry a 3-wood or a 5-wood?",
         "Most amateurs get more out of a 5-wood. A 3-wood's 15° face needs "
         "clubhead speed to launch from the turf, so it often becomes a "
         "tee-only club; an 18°–19° 5-wood flies almost as far, launches far "
         "more easily and holds greens. Carry both only if the gap to the "
         "driver justifies it."),
        ("What fairway wood is easiest to hit?",
         "The highest-lofted one that fills the gap. Loft adds launch and "
         "backspin, which keeps mis-hits airborne and reduces curve — a 7-wood "
         "or 9-wood is markedly easier from the fairway and rough than a "
         "3-wood, which is why high-lofted woods are back in fashion."),
        ("Can a fairway wood replace a driver?",
         "Off the tee, yes — a 13.5°–16.5° 3-wood costs distance against a "
         "driver but its shorter shaft and extra loft make it straighter. "
         "Players who fight the driver often tee off with a 3-wood and give "
         "up less than they think."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = hub_article_ld(
        "Fairway Wood Loft Chart", desc, "/fairway-wood-lofts/",
        "fairway wood loft chart, 3 wood loft, 5 wood loft, 7 wood loft, "
        "fairway wood degrees", "Golf fairway wood loft")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Fairway Wood Loft Chart</h1>
    <p class="lede">What degree each fairway wood is, which long iron or hybrid it
    replaces, and the stock lofts every major manufacturer currently builds.</p>
  </div>

  <p><strong>A standard 3-wood is 15°, a 5-wood 18°–19° and a 7-wood 21°–22°.</strong>
  The retail range runs from 13.5° low-spin 3-woods to 9-woods at 26° and beyond, and
  most current families add an adjustable hosel worth a degree or two in each direction.
  Unlike irons, fairway woods are usually bought one slot at a time — which makes the
  loft, not the number on the sole, the thing to gap by.</p>

  <dl class="facts">
    <div><dt>3-wood</dt><dd>15° standard</dd></div>
    <div><dt>5-wood</dt><dd>18°–19°</dd></div>
    <div><dt>7-wood</dt><dd>21°–22°</dd></div>
    <div><dt>9-wood</dt><dd>24°–26°</dd></div>
    <div><dt>Typical hosel adjustment</dt><dd>±1°–2°</dd></div>
  </dl>

  <h2>Fairway wood lofts at a glance</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Typical loft bands by wood number, and the long clubs each one replaces.</caption>
    <thead><tr><th scope="col">Wood</th><th scope="col">Typical loft</th>
    <th scope="col">Replaces</th><th scope="col">Role</th></tr></thead>
    <tbody>{band_rows}</tbody></table></div>
  <p class="table-note">Bands overlap on purpose — a strong 5-wood and a weak 4-wood are
  the same club. Gap fairway woods by loft and carry against the driver above them and
  the <a href="/hybrid-lofts/">hybrids</a> or irons below.</p>

  <h2>Stock fairway wood lofts by brand</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock loft options for each manufacturer&rsquo;s current fairway wood line,
    as of {long_date(WOOD_CHECKED)}.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">Current line</th>
    <th scope="col">Stock lofts</th><th scope="col">Hosel adjustment</th></tr></thead>
    <tbody>{brand_rows}</tbody></table></div>
  <p class="table-note">Generated from the LoftChart spec archive, last verified
  {long_date(WOOD_CHECKED)}; the model link opens the family&rsquo;s full chart with
  every head variant and hosel setting. Some lofts are right-hand only.</p>

  <h2>Fairway wood spec charts on file</h2>
  <p>Per-family pages with the stock lofts for every head variant and the hosel
  adjustment chart where the family shares one — including discontinued lines whose
  spec pages have left the manufacturer sites.</p>
  <div class="grid">{''.join(model_card(m) for m in recent)}</div>

  <h2>Loft decides the job, not the number</h2>
  <p>The number on a fairway wood's sole is a naming convention; the loft is what sets
  launch, carry and landing angle. A 15° 3-wood is a distance club that needs speed to
  fly from the turf. From about 18° upward the equation flips: the ball climbs easily,
  lands steeply and stops — which is why a 7-wood from light rough is one of the easiest
  long shots in golf, and why the highest-lofted woods have returned to tour bags.</p>
  <p>When gapping, work downward from the driver in roughly 3°–4° steps of loft and
  make each slot either a fairway wood or a <a href="/hybrid-lofts/">hybrid</a>, not
  both. The same loft in a wood flies higher and further; in a hybrid it is shorter,
  more iron-like and easier to control.</p>

  {faq_html}

  {guide_shop_block("Shop fairway woods", "fairway wood",
                     "Search for new and used fairway woods at these retailers:")}

  <p>Working on the rest of the long game? The <a href="/driver-lofts/">driver loft
  chart</a> covers the tee shot and the <a href="/hybrid-lofts/">hybrid loft chart</a>
  maps each hybrid to the iron it replaces.</p>

  {hub_sources("Loft bands and the iron equivalences are the accepted club-fitting "
               "conventions, given as ranges because no governing body defines them "
               "and shaft length and head design move every one of them.",
               WOOD_CHECKED)}
</div>
{guide_sticky_bar("Shop fairway woods", "fairway wood")}
"""
    page("/fairway-wood-lofts/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


def hybrid_index(brands, hy_models):
    """The /hybrid-lofts/ hub — the 'hybrid loft chart' page."""
    title = fit_title("Hybrid Loft Chart — Degrees & Iron Equivalents",
                      f" | {SITE_NAME}")
    desc = fit_desc(
        "A 19° hybrid replaces a 3-iron, 22° a 4-iron and 25° a 5-iron. ",
        [f"Hybrid lofts by brand with iron equivalents, and spec charts for "
         f"{plural(len(hy_models), 'family')} of head variants.",
         "Hybrid lofts by brand, with the iron each loft replaces.",
         "Hybrid loft chart with iron equivalents."])

    nav, bc = crumbs([("Home", "/"), ("Hybrid Lofts", None)])

    band_rows = "".join(
        f'<tr><th scope="row">{h}</th><td>{loft}</td><td>{iron}</td>'
        f"<td>{wood}</td></tr>"
        for h, loft, iron, wood in (
            ("2-hybrid", "16°–18°", "2-iron", "4-wood"),
            ("3-hybrid", "19°–21°", "3-iron", "5-wood / 7-wood"),
            ("4-hybrid", "22°–24°", "4-iron", "7-wood / 9-wood"),
            ("5-hybrid", "25°–27°", "5-iron", "9-wood"),
            ("6-hybrid", "28°–31°", "6-iron", "—"),
        ))

    brand_rows = "".join(
        f'<tr><th scope="row"><a href="/{esc(m["brand_slug"])}/">{esc(m["brand"])}</a></th>'
        f'<td><a href="{m["url"]}">{esc(m["model"])}</a>'
        + (f' ({m["year_introduced"]})' if m.get("year_introduced") else "")
        + f"</td><td>{esc(lofts)}</td><td>{esc(adj)}</td></tr>"
        for m, lofts, adj in driver_brand_rows(hy_models))

    recent = sorted(hy_models,
                    key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))

    faq = [
        ("What loft hybrid replaces a 3-iron?",
         "19°–21°. Match the lofts rather than the numbers: a modern 3-iron is "
         "19°–21° and so is a 3-hybrid. But expect the hybrid to carry half a "
         "club further at the same loft — its longer shaft and lower, deeper "
         "centre of gravity add ball speed and launch — so some players take "
         "one degree more loft in the hybrid."),
        ("Do hybrids go further than irons of the same loft?",
         "Usually, by roughly 5–10 yards. The hybrid's shaft is longer and its "
         "centre of gravity sits further back, which adds ball speed and "
         "launch. That is a feature when replacing a long iron and a problem "
         "when it stacks on top of a full set — check the gap to your longest "
         "iron rather than assuming the numbers line up."),
        ("What hybrid should a beginner carry?",
         "More loft than instinct suggests: a 22°–25° hybrid in place of the "
         "4- and 5-irons is the single easiest upgrade. Low-lofted 17°–19° "
         "hybrids need nearly as much speed as the long irons they replace."),
        ("Hybrid or fairway wood for the same slot?",
         "The same loft flies higher and further in a fairway wood, shorter "
         "and more controlled in a hybrid. Pick the wood for distance slots "
         "and par-5 seconds, the hybrid where you want an iron's trajectory "
         "with more forgiveness — and hold each slot with only one of them."),
    ]
    faq_html, faq_ld = faq_block(faq)

    article_ld = hub_article_ld(
        "Hybrid Loft Chart", desc, "/hybrid-lofts/",
        "hybrid loft chart, hybrid degrees, 3 hybrid loft, hybrid iron "
        "equivalent, what hybrid replaces a 4 iron", "Golf hybrid loft")

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Hybrid Loft Chart</h1>
    <p class="lede">What degree each hybrid is, which iron each loft replaces, and the
    stock lofts every major manufacturer currently builds.</p>
  </div>

  <p><strong>Hybrids run from about 17° to 28°, and the loft maps directly onto the
  long iron it replaces:</strong> 19°–21° stands in for a 3-iron, 22°–24° for a 4-iron,
  25°–27° for a 5-iron. The number stamped on the head follows the same convention as
  the iron, but lofts vary by a degree or two between brands — so gap by loft, and
  expect a hybrid to carry slightly further than the iron it replaces.</p>

  <dl class="facts">
    <div><dt>Common range</dt><dd>17°–28°</dd></div>
    <div><dt>3-iron replacement</dt><dd>19°–21°</dd></div>
    <div><dt>4-iron replacement</dt><dd>22°–24°</dd></div>
    <div><dt>5-iron replacement</dt><dd>25°–27°</dd></div>
    <div><dt>Typical hosel adjustment</dt><dd>±1°–2°</dd></div>
  </dl>

  <h2>Hybrid lofts at a glance</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Typical loft bands by hybrid number, with the iron and fairway wood
    equivalents.</caption>
    <thead><tr><th scope="col">Hybrid</th><th scope="col">Typical loft</th>
    <th scope="col">Replaces</th><th scope="col">Fairway wood equivalent</th></tr></thead>
    <tbody>{band_rows}</tbody></table></div>
  <p class="table-note">Equivalences assume modern iron lofts; against a traditional or
  blade set (see the <a href="/iron-lofts/">iron loft chart</a>) shift everything about
  one club weaker. The same loft carries further in a hybrid than in the iron.</p>

  <h2>Stock hybrid lofts by brand</h2>
  <div class="table-scroll data-table-zone"><table class="specs">
    <caption>Stock loft options for each manufacturer&rsquo;s current hybrid line, as of
    {long_date(WOOD_CHECKED)}.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">Current line</th>
    <th scope="col">Stock lofts</th><th scope="col">Hosel adjustment</th></tr></thead>
    <tbody>{brand_rows}</tbody></table></div>
  <p class="table-note">Generated from the LoftChart spec archive, last verified
  {long_date(WOOD_CHECKED)}; the model link opens the family&rsquo;s full chart with
  every head variant and hosel setting. Some lofts are right-hand only.</p>

  <h2>Hybrid spec charts on file</h2>
  <p>Per-family pages with the stock lofts for every head variant and the hosel
  adjustment chart where the family shares one — including discontinued lines whose
  spec pages have left the manufacturer sites.</p>
  <div class="grid">{''.join(model_card(m) for m in recent)}</div>

  <h2>Match the loft, then check the carry</h2>
  <p>A hybrid is a long-iron replacement, so the fitting logic starts from the iron it
  displaces: find the loft of the iron coming out of the bag and buy the hybrid within a
  degree of it. Then check the gap on the course. The hybrid's longer shaft and deeper
  centre of gravity usually add half a club of carry at the same loft, which is welcome
  at the top of the bag and a problem if it opens a hole above your 5-iron.</p>
  <p>Adjustable hosels, where fitted, move most current hybrids a degree or two either
  way — enough to close a gap without reordering the set. The per-model pages above
  chart each family's settings.</p>

  <h2>Hybrid guides</h2>
  {knowledge_guide_cards(only=("hybrid-to-iron-conversion",
                               "iron-number-equivalents",
                               "golf-club-loft-explained"))}

  {faq_html}

  {guide_shop_block("Shop hybrids", "golf hybrid",
                     "Search for new and used hybrids at these retailers:")}

  <p>Filling the slots around them? The <a href="/fairway-wood-lofts/">fairway wood
  loft chart</a> covers the woods above and the <a href="/iron-lofts/">iron loft
  chart</a> the set below.</p>

  {hub_sources("Loft bands and the iron equivalences are the accepted club-fitting "
               "conventions, given as ranges because no governing body defines them "
               "and shaft length and head design move every one of them.",
               WOOD_CHECKED)}
</div>
{guide_sticky_bar("Shop hybrids", "golf hybrid")}
"""
    page("/hybrid-lofts/", title, desc, body, brands,
         [bc, article_ld, faq_ld], og_type="article")


# --------------------------------------------------------------------------
# feeds
# --------------------------------------------------------------------------

def sitemap(urls):
    entries = "".join(
        f"<url><loc>{esc(SITE + u)}</loc><lastmod>{mod}</lastmod>"
        f"<changefreq>monthly</changefreq><priority>{p}</priority></url>"
        for u, p, mod in urls)
    write("sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + entries + "</urlset>\n")


def robots():
    write("robots.txt",
          "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)


def webmanifest():
    write("site.webmanifest", json.dumps({
        "name": "LoftChart — Golf Club Specifications",
        "short_name": "LoftChart",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#FAFAF7",
        "theme_color": "#1B4332",
        "icons": [
            {"src": "/favicon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/favicon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, indent=2))


def search_index(models):
    idx = [{"t": m["title"],
            "u": m["url"].lstrip("/"),
            "m": f"{year_range(m)} · "
                 f"{category_label(m) if m.get('category') else ''}"}
           for m in sorted(models, key=lambda m: (m["brand"], m["model"]))]
    write("search-index.json", json.dumps(idx, ensure_ascii=False, separators=(",", ":")))


def copy_static():
    for name in os.listdir(STATIC):
        src = os.path.join(STATIC, name)
        dst = os.path.join(OUT, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    write(".nojekyll", "")
    write("CNAME", "loftchart.com\n")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def audit_descriptions():
    """Fail the build on a duplicate or out-of-band meta description.

    Runs over every page head() emitted, so new page types are covered
    automatically rather than needing to be added here.
    """
    indexed = {p: v["desc"] for p, v in DESC_REGISTRY.items() if not v["noindex"]}

    by_text = defaultdict(list)
    for path, desc in indexed.items():
        by_text[desc].append(path)
    dupes = {d: ps for d, ps in by_text.items() if len(ps) > 1}

    long_ = {p: d for p, d in indexed.items() if len(d) > DESC_MAX}
    short_ = {p: d for p, d in indexed.items() if len(d) < DESC_MIN}
    missing = {p: d for p, d in indexed.items() if not (d or "").strip()}

    print(f"  meta descriptions: {len(indexed)} indexed pages, "
          f"{len(by_text)} unique")

    ok = True
    if dupes:
        ok = False
        print("  DUPLICATE descriptions:", file=sys.stderr)
        for d, ps in dupes.items():
            print(f"    {len(ps)}x {d[:70]!r}", file=sys.stderr)
            for p in ps:
                print(f"        {p}", file=sys.stderr)
    if missing:
        ok = False
        print("  EMPTY descriptions:", file=sys.stderr)
        for p in missing:
            print(f"    {p}", file=sys.stderr)
    for name, bucket in (("OVER", long_), ("UNDER", short_)):
        if bucket:
            ok = False
            limit = DESC_MAX if name == "OVER" else DESC_MIN
            print(f"  {name} length ({limit}) — {len(bucket)} pages:",
                  file=sys.stderr)
            for p, d in sorted(bucket.items(), key=lambda kv: -len(kv[1])):
                print(f"    {len(d):>3} {p}", file=sys.stderr)
                print(f"        {d}", file=sys.stderr)

    if not ok:
        print("\nMeta description audit failed.", file=sys.stderr)
        sys.exit(1)
    print("  meta description audit passed "
          f"(all unique, {DESC_MIN}-{DESC_MAX} chars)")


def audit_titles():
    """Fail the build on a duplicate or over-long <title>.

    Same contract as audit_descriptions(): every page flows through head(),
    so new page types are covered without touching this function.
    """
    indexed = {p: v["title"] for p, v in DESC_REGISTRY.items() if not v["noindex"]}

    by_text = defaultdict(list)
    for path, t in indexed.items():
        by_text[t].append(path)
    dupes = {t: ps for t, ps in by_text.items() if len(ps) > 1}
    long_ = {p: t for p, t in indexed.items() if len(t) > TITLE_MAX}

    print(f"  titles: {len(indexed)} indexed pages, {len(by_text)} unique")

    ok = True
    if dupes:
        ok = False
        print("  DUPLICATE titles:", file=sys.stderr)
        for t, ps in dupes.items():
            print(f"    {len(ps)}x {t[:70]!r}", file=sys.stderr)
            for p in ps:
                print(f"        {p}", file=sys.stderr)
    if long_:
        ok = False
        print(f"  OVER length ({TITLE_MAX}) — {len(long_)} pages:", file=sys.stderr)
        for p, t in sorted(long_.items(), key=lambda kv: -len(kv[1])):
            print(f"    {len(t):>3} {p}\n        {t}", file=sys.stderr)

    if not ok:
        print("\nTitle audit failed.", file=sys.stderr)
        sys.exit(1)
    print(f"  title audit passed (all unique, <={TITLE_MAX} chars)")


def main():
    brands, models, errors = load()
    if errors:
        print("Data problems found:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        if any("missing required" in e or "no specs" in e for e in errors):
            sys.exit(1)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    by_key = {m["key"]: m for m in models}
    iron_models = [m for m in models if m["club_type"] == "irons"]
    wedge_models = [m for m in models if m["club_type"] == "wedges"]
    driver_models = [m for m in models if m["club_type"] == "driver"]
    fairway_models = [m for m in models if m["club_type"] == "fairway_wood"]
    hybrid_models = [m for m in models if m["club_type"] == "hybrid"]
    by_brand = defaultdict(list)
    by_year = defaultdict(list)
    by_cat = defaultdict(list)
    for m in models:
        by_brand[m["brand_slug"]].append(m)
        # Year and category hubs span every club type, sectioned by type on
        # the page. Overlapping category slugs (the iron, wedge and wood enums
        # all use "game-improvement") merge into one hub page.
        if m.get("year_introduced"):
            by_year[m["year_introduced"]].append(m)
        if m.get("category"):
            by_cat[m["category"]].append(m)

    # comparison pages first, so model pages can link to them
    pairs = find_pairs(models, by_key)
    names = model_name_index(models)
    pairs_built = []
    compares_by_key = defaultdict(list)
    all_slugs = {compare_slug(a, b) for a, b in pairs}
    missing = [s for s in POPULAR_COMPARES if s not in all_slugs]
    if missing:
        print("POPULAR_COMPARES slugs with no compare page:", file=sys.stderr)
        for s_ in missing:
            print("  -", s_, file=sys.stderr)
        sys.exit(1)
    for a, b in pairs:
        indexed = compare_indexable(compare_slug(a, b), a, b, names)
        slug = compare_page(a, b, brands, indexed, is_generation_step(a, b, names))
        pairs_built.append((slug, a, b, indexed))
        compares_by_key[a["key"]].append((slug, b))
        compares_by_key[b["key"]].append((slug, a))
    compares_index(pairs_built, brands)

    for m in models:
        model_page(m, brands, by_key, compares_by_key)

    for b in brands:
        if by_brand.get(b["slug"]):
            brand_page(b, by_brand[b["slug"]], brands)
    brands_index(brands, by_brand, models)

    for y, ms in by_year.items():
        year_page(y, ms, brands, by_year)
    years_index(by_year, brands, models)

    for c, ms in by_cat.items():
        category_page(c, ms, brands)
    categories_index(by_cat, brands, models)

    # Guide stats continue to come from iron-set wedges; the standalone wedge
    # models are only linked, never mixed into those stats.
    wedge_pages(iron_models, brands, wedge_models)
    driver_pages(brands, driver_models)
    knowledge_pages(brands, models, iron_models, hybrid_models)
    iron_index(brands, iron_models, by_cat)
    fairway_index(brands, fairway_models)
    hybrid_index(brands, hybrid_models)

    homepage(brands, models, by_brand)
    about_page(brands, models)
    privacy_page(brands)
    not_found(brands)
    redirect_pages()

    audit_descriptions()
    audit_titles()

    search_index(models)
    copy_static()
    robots()
    webmanifest()

    # Sitemap carries indexable pages only: no thin year page.
    # lastmod is the date the page's content last changed: a model's own data
    # file, the newest model on a hub, or the review date of a guide.
    def newest(ms):
        return max(m["modified"] for m in ms)

    thin_years = [y for y, ms in by_year.items() if len(ms) < YEAR_MIN_MODELS]
    site_mod = newest(models)
    urls = [("/", "1.0", site_mod), ("/brands/", "0.8", site_mod),
            ("/years/", "0.6", site_mod), ("/category/", "0.6", site_mod),
            ("/wedge-lofts/", "0.9", WEDGE_REVIEWED),
            ("/driver-lofts/", "0.9", DRIVER_REVIEWED),
            ("/iron-lofts/", "0.9", max(HUB_REVIEWED, newest(iron_models))),
            ("/fairway-wood-lofts/", "0.9",
             max(HUB_REVIEWED, newest(fairway_models))),
            ("/hybrid-lofts/", "0.9", max(HUB_REVIEWED, newest(hybrid_models))),
            ("/about/", "0.4", site_mod), ("/privacy/", "0.2", PRIVACY_UPDATED)]
    urls += [(f"/wedge-lofts/{w['slug']}/", "0.8", WEDGE_REVIEWED) for w in WEDGE_TYPES]
    urls += [(f"/guides/{g['slug']}/", "0.8", DRIVER_REVIEWED) for g in DRIVER_GUIDES]
    # The knowledge guides' tables are generated from the archive, so a data
    # change is a content change: lastmod is the newer of the review date and
    # the newest model file feeding the tables.
    urls += [(f"/guides/{g['slug']}/", "0.8", max(KNOWLEDGE_REVIEWED, site_mod))
             for g in KNOWLEDGE_GUIDES]
    urls += [(m["url"], "0.9", m["modified"]) for m in models]
    urls += [(f"/{b['slug']}/", "0.8", newest(by_brand[b["slug"]]))
             for b in brands if by_brand.get(b["slug"])]
    urls += [(f"/years/{y}/", "0.5", newest(ms)) for y, ms in by_year.items()
             if y not in thin_years]
    urls += [(f"/category/{c}/", "0.6", newest(ms)) for c, ms in by_cat.items()]
    urls += [("/compare/", "0.7", site_mod)]
    # Only the comparisons Google may index; the rest carry a googlebot noindex.
    urls += [(f"/compare/{slug}/", "0.7",
              max(a["modified"], b["modified"]))
             for slug, a, b, indexed in pairs_built if indexed]
    sitemap(urls)

    print(f"Built {len(models)} models, {len([b for b in brands if by_brand.get(b['slug'])])} "
          f"brands, {len(pairs_built)} comparisons "
          f"({sum(1 for p in pairs_built if p[3])} indexed), {len(REDIRECTS)} redirect stubs, "
          f"{len(urls)} indexable URLs, {len(thin_years)} year pages noindexed → {OUT}")
    if errors:
        print(f"({len(errors)} non-fatal data warnings — see above)")


if __name__ == "__main__":
    main()
