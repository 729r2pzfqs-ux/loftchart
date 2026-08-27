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
import sys
from collections import defaultdict, OrderedDict
from datetime import date

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
EMAIL = "info@loftchart.com"
# Cloudflare's email obfuscation rewrites any literal mailto: it finds into a
# /cdn-cgi/l/email-protection URL that 404s for crawlers without JS, so every page
# got flagged as linking to a broken page. Entity encoding alone does not help -
# Cloudflare decodes entities before it scans - so every address also sits inside
# the documented <!--email_off--> opt-out markers. The entities stay as a second
# layer for any other scraper that does not decode them.
EMAIL_HTML = EMAIL.replace("@", "&#64;").replace(".", "&#46;")
EMAIL_OFF = "<!--email_off-->"


def email_link(text=None):
    """A mailto: anchor fenced off from Cloudflare's email obfuscator."""
    return (f'{EMAIL_OFF}<a href="mailto:{EMAIL_HTML}">'
            f'{EMAIL_HTML if text is None else text}</a>{EMAIL_OFF}')
TODAY = date.today().isoformat()

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
    return EMAIL_OFF + tag + EMAIL_OFF if EMAIL in payload else tag


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
            for row in specs:
                row["club"] = str(row.get("club", "")).upper()
                for key in ("loft", "lie", "length"):
                    if row.get(key) is None:
                        errors.append(f"{rel}: club {row['club']} missing {key}")
            if not m.get("sources"):
                errors.append(f"{rel}: no sources listed")
            if len(m.get("faq") or []) < 2:
                errors.append(f"{rel}: fewer than 2 FAQ entries")

            specs.sort(key=lambda r: (r["loft"] if r.get("loft") is not None
                                      else float("inf"), club_sort_key(r["club"])))
            m["specs"] = specs
            m["key"] = f"{m['brand_slug']}/{m['slug']}"
            m["url"] = f"/{m['brand_slug']}/{m['slug']}/"
            m["brand_meta"] = by_slug[m["brand_slug"]]
            m["type_label"] = CLUB_TYPE_LABEL.get(m.get("club_type"), "Clubs")
            m["title"] = f"{m['brand']} {m['model']} {m['type_label']}"
            models.append(m)

    return brands, models, errors


def seven_iron(m):
    for row in m["specs"]:
        if row["club"] == "7":
            return row
    mid = m["specs"][len(m["specs"]) // 2] if m["specs"] else None
    return mid


def year_range(m):
    a = m.get("year_introduced")
    b = m.get("year_discontinued")
    if a and b:
        return f"{a}–{b}"
    if a:
        # A model with a known successor is not still in production, even when
        # the research does not pin down the year it was replaced.
        return f"from {a}" if m.get("successor") else f"{a}–present"
    return "Year unknown"


# --------------------------------------------------------------------------
# chrome
# --------------------------------------------------------------------------

def head(title, desc, path, ld=None, og_type="website", noindex=False):
    canon = SITE + path
    # Record the rendered (unescaped) description; noindex pages are tracked
    # but exempted from the audit since they never surface in search.
    DESC_REGISTRY[path] = {"desc": desc, "title": title, "noindex": noindex}
    ldblocks = "".join(ldjson(o) for o in (ld or []))
    analytics = (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        "<script>window.dataLayer=window.dataLayer||[];"
        "function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config','{GA_ID}');</script>"
    ) if GA_ENABLED else ""
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
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
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/css/style.css">
{ldblocks}
{analytics}
<script src="https://analytics.ahrefs.com/analytics.js" data-key="Q1ltvzQDnlsCUSrZfvGd0g" async></script>
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/">
      <svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="12" fill="#FAFAF7" opacity=".08"/><path d="M25 24 L28 9" stroke="#FAFAF7" stroke-width="7" stroke-linecap="round" fill="none"/><path d="M21 44 L46 45 L50 30 L23 22 Z" fill="#FAFAF7" stroke="#FAFAF7" stroke-width="4.5" stroke-linejoin="round"/><g stroke="#1B4332" stroke-width="2.4" stroke-linecap="round"><path d="M25 30.5 H45"/><path d="M24 35.5 H45.5"/><path d="M23.5 40.5 H46"/></g></svg>
      <span>Loft<span class="dot">Chart</span></span>
    </a>
    <nav class="site-nav">
      <a href="/brands/">Brands</a>
      <a href="/years/">Years</a>
      <a href="/category/">Categories</a>
      <a href="/wedge-lofts/">Wedge Lofts</a>
      <a href="/compare/">Compare</a>
      <a href="/about/">About</a>
    </nav>
  </div>
</header>
<main>
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
          <li><a href="/wedge-lofts/">Wedge loft chart</a></li>
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
<script src="/js/search.js" defer></script>
</body>
</html>
"""


def page(path, title, desc, body, brands, ld=None, og_type="website", noindex=False):
    write(os.path.join(path.strip("/"), "index.html") if path != "/" else "index.html",
          head(title, desc, path, ld, og_type, noindex) + body + foot(brands))


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
    return (f'<div class="table-scroll"><table class="specs">{cap}'
            f'<thead><tr><th scope="col">Club</th>{thead}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


# --------------------------------------------------------------------------
# model page
# --------------------------------------------------------------------------

def availability(m):
    """Closing section, written from the production status the data actually records.

    Only a set with a discontinuation year on file can be called out of production;
    55 models have `year_discontinued: null` and are still catalogued, and telling a
    reader to shop the used market for a set that is on the rack is simply wrong.
    """
    brand, model = esc(m["brand"]), esc(m["model"])
    intro = m.get("year_introduced")
    pred = m.get("predecessor")
    succ = m.get("successor")
    cat = CATEGORY_SHORT.get(m.get("category"))

    if m.get("year_discontinued"):
        return f"""<h2>Finding a used set</h2>
  <p>The {brand} {model} ran from {intro} to {m['year_discontinued']} and is no longer in
  production, so the used market is the only source. Search eBay, 2nd Swing, Golf Avenue and
  the PGA Tour Superstore trade-in listings, and check the loft and lie against the chart
  above before buying — sets this age have often been bent from standard.</p>"""

    if succ:
        # Superseded, but no retirement year is recorded — say that plainly rather
        # than guessing at a date or claiming it is still current.
        return f"""<h2>Buying a set</h2>
  <p>{brand} has since introduced the {esc(succ)} above it in the range, so the {model} is at
  the end of its retail life rather than fully retired — closeout sets still turn up at
  retailers while stock lasts, and it is well represented used on eBay, 2nd Swing and Golf
  Avenue. Check the loft and lie against the chart above before buying a used set: irons are
  routinely bent from standard during a fitting.</p>"""

    lineage = f" It replaced the {esc(pred)}." if pred else ""
    # "a current ... " not "the current ...": several brands catalogue more than
    # one live set in the same category.
    slot = (f"a current {cat} set in the {brand} range" if cat
            else f"a current model in the {brand} range")
    intro_txt = f"Introduced in {intro}, t" if intro else "T"
    return f"""<h2>Where it sits in the lineup</h2>
  <p>{intro_txt}he {brand} {model} is {slot}, with no replacement announced.{lineage} New sets
  are built to the standard lofts, lies and lengths in the chart above, though a fitting can
  move any of them — so confirm the numbers on the order sheet. Used sets appear on eBay,
  2nd Swing and Golf Avenue, and should be measured against this chart before buying.</p>"""


def model_page(m, brands, models_by_key, compares_by_key):
    s7 = seven_iron(m)
    title = fit_title(f"{m['title']} Specs", " — Loft & Lie Chart", f" | {SITE_NAME}")
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

    if s7:
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

    facts = [("Years produced", year_range(m)),
             ("Category", CATEGORY_LABEL.get(m.get("category"), m.get("category", "—"))),
             ("Construction", m.get("construction") or "—"),
             ("Material", m.get("material") or "—"),
             ("Set makeup", "–".join([m["specs"][0]["club"], m["specs"][-1]["club"]])
              if m["specs"] else "—")]
    facts_html = "".join(
        f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in facts)

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
                    + "".join(f"<li>{esc(s)}</li>" for s in (m.get("sources") or []))
                    + f"</ul><p>Last reviewed {TODAY}. Spot an error? "
                    f'{email_link()}</p></div>')

    article_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": f"{m['title']} Specifications",
        "description": desc,
        "datePublished": TODAY,
        "dateModified": TODAY,
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + m["url"]},
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        # A Product entity here makes Google expect offers/review/aggregateRating.
        # These are reference spec pages, not listings, so describe the subject
        # as a plain Thing instead.
        "about": {"@type": "Thing", "name": m["title"]},
        "keywords": ", ".join([m["brand"], m["model"], m["type_label"],
                               "loft", "lie", "length", "specifications"]),
    }

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

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(m['title'])} Specifications</h1>
    <p class="lede">{esc(lede)}</p>
  </div>

  <dl class="facts">{facts_html}</dl>

  {conf_note}

  <h2>Loft, lie &amp; length chart</h2>
  {spec_table(m, caption)}
  <p class="table-note">Lofts and lies are the factory standard build. Individual clubs may
  differ if they have been bent, re-shafted or re-gripped during their life.</p>

  {about}
  {shafts}
  {related_html}
  {faq_html}

  {availability_html}

  {sources_html}
</div>
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
    title = fit_title(f"{b['name']} Iron Specs", " — Loft & Lie Charts",
                      f" | {SITE_NAME}")
    # Compact head leaves room for the family list, which is the part that
    # carries the searched terms ("Ping G series").
    head_part = f"{b['name']} iron specifications, {min(years)}–{max(years)}. "
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
</div>
"""
    page(f"/{b['slug']}/", title, desc, body, brands,
         [bc, item_list(ms, f"{b['name']} club models")])


def brands_index(brands, by_brand, all_models):
    title = f"All Golf Club Brands — Specification Archive | {SITE_NAME}"
    span = loft_span(all_models)
    head_part = (f"{plural(len(all_models), 'iron model')} across "
                 f"{plural(len(brands), 'manufacturer')}, {span}. " if span else
                 f"{plural(len(all_models), 'iron model')} across "
                 f"{plural(len(brands), 'manufacturer')}. ")
    desc = fit_desc(head_part, [
        "Loft charts, lie angles and lengths for Ping, Titleist, Callaway, "
        "TaylorMade, Mizuno and more.",
        "Loft charts, lie angles and lengths for every brand.",
        "Full loft charts for every brand."])
    nav, bc = crumbs([("Home", "/"), ("Brands", None)])

    cards = []
    for b in brands:
        ms = by_brand.get(b["slug"], [])
        if not ms:
            continue
        years = [m["year_introduced"] for m in ms if m.get("year_introduced")]
        cards.append(
            f'<a class="card brand-card" href="/{b["slug"]}/" '
            f'style="--brand-color:{esc(b.get("color", "#C9A94E"))}">'
            f'<span class="card-title">{esc(b["name"])}</span>'
            f'<span class="card-meta">{len(ms)} models · {min(years)}–{max(years)}</span>'
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
         [bc, item_list(all_models, "Golf club brands")])


# --------------------------------------------------------------------------
# year / category pages
# --------------------------------------------------------------------------

# Fewer than this many models on a year page and it carries nothing the model
# cards do not already say — indexed, it competes with them for nothing.
YEAR_MIN_MODELS = 3


def year_page(year, ms, brands):
    ms = sorted(ms, key=lambda m: (m["brand"], m["model"]))
    title = f"{year} Golf Club Releases — Specifications | {SITE_NAME}"
    brand_names = sorted({m["brand"] for m in ms})
    blist = comma_list(brand_names)
    span = loft_span(ms)
    head = f"{year} golf club releases: {plural(len(ms), 'iron model')}"
    head_part = f"{head}, {span}. " if span else f"{head}. "
    desc = fit_desc(head_part, [
        f"Full specifications from {blist}. Compare loft, lie and length across "
        f"every model released in {year}.",
        f"Full specifications from {blist}. Compare loft, lie and length.",
        f"Specifications from {plural(len(brand_names), 'brand')}. Compare loft, "
        f"lie and length across every {year} release.",
        f"Compare loft, lie and length across every {year} release.",
    ])
    nav, bc = crumbs([("Home", "/"), ("Years", "/years/"), (str(year), None)])
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Golf Clubs Released in {year}</h1>
    <p class="lede">{len(ms)} model{'s' if len(ms) != 1 else ''} on file introduced in
    {year}. Every entry links to its full loft, lie and length chart.</p>
  </div>
  <div class="grid">{''.join(model_card(m) for m in ms)}</div>
</div>
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
        f"{plural(len(all_models), 'iron model')} across {plural(len(yrs), 'year')}. ",
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
    page("/years/", title, desc, body, brands, [bc, item_list(all_models, "Release years")])


def category_page(cat, ms, brands):
    label = CATEGORY_LABEL.get(cat, cat)
    ms = sorted(ms, key=lambda m: (m.get("year_introduced") or 0, m["brand"]))
    short = CATEGORY_SHORT.get(cat, label.replace(" Irons", "").lower())
    title = fit_title(label, " — Loft Charts & Specs", f" | {SITE_NAME}")
    span = loft_span(ms)
    # Lead with the loft figure — it is the number that distinguishes one
    # category from the next, and the reason someone clicks a category page.
    if span:
        head_part = f"{label}: {span} across {plural(len(ms), f'{short} iron')}. "
    else:
        head_part = f"{label}: specifications for {plural(len(ms), f'{short} iron')}. "
    desc = fit_desc(head_part, [
        "Compare loft, lie, length and swing weight for every club, from every "
        "major brand.",
        "Compare loft, lie and length for every club from every major brand.",
        "Compare loft, lie and length for every club.",
    ])
    nav, bc = crumbs([("Home", "/"), ("Categories", "/category/"), (label, None)])

    rows = "".join(
        f'<tr><th scope="row"><a href="{m["url"]}">{esc(m["brand"])} {esc(m["model"])}</a></th>'
        f'<td>{esc(year_range(m))}</td>'
        f'<td>{num(seven_iron(m)["loft"]) if seven_iron(m) else "—"}</td>'
        f'<td>{num(seven_iron(m)["lie"]) if seven_iron(m) and seven_iron(m).get("lie") is not None else "—"}</td>'
        f'<td>{num(seven_iron(m)["length"]) if seven_iron(m) and seven_iron(m).get("length") is not None else "—"}</td></tr>'
        for m in ms)

    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>{esc(label)}</h1>
    <p class="lede">{esc(CATEGORY_BLURB.get(cat, ''))}</p>
  </div>
  <h2>7-iron specifications compared</h2>
  <div class="table-scroll"><table class="specs">
    <thead><tr><th scope="col">Model</th><th scope="col">Years</th><th scope="col">Loft (°)</th>
    <th scope="col">Lie (°)</th><th scope="col">Length (in)</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <p class="table-note">Figures shown are the 7-iron from each set (or the nearest middle
  iron where a 7-iron is not on file). Follow a model link for the full set chart.</p>
</div>
"""
    page(f"/category/{cat}/", title, desc, body, brands, [bc, item_list(ms, label)])


def categories_index(by_cat, brands, all_models):
    title = fit_title("Iron Categories — Blade, Players & Game Improvement",
                      f" | {SITE_NAME}")
    span = loft_span(all_models)
    head_part = (f"Golf iron categories compared: {plural(len(all_models), 'model')} "
                 f"across {plural(len(by_cat), 'category')}, {span}. " if span else
                 f"Golf iron categories compared: {plural(len(all_models), 'model')} "
                 f"across {plural(len(by_cat), 'category')}. ")
    desc = fit_desc(head_part, [
        "Blades, players, players distance and game improvement irons.",
        "Blades, players and game improvement irons.",
        ""])
    nav, bc = crumbs([("Home", "/"), ("Categories", None)])
    order = ["blade", "players", "players-distance", "game-improvement",
             "super-game-improvement"]
    cats = [c for c in order if c in by_cat] + [c for c in by_cat if c not in order]
    cards = "".join(
        f'<a class="card" href="/category/{esc(c)}/">'
        f'<span class="card-title">{esc(CATEGORY_LABEL.get(c, c))}</span>'
        f'<span class="card-meta">{len(by_cat[c])} models</span>'
        f'<span class="card-spec">{esc(CATEGORY_BLURB.get(c, "")[:88])}…</span></a>'
        for c in cats)
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Iron Categories</h1>
    <p class="lede">Irons are grouped by head design and intended player. The categories
    below run from the most compact and least forgiving to the most forgiving.</p>
  </div>
  <div class="grid">{cards}</div>
</div>
"""
    page("/category/", title, desc, body, brands, [bc, item_list(all_models, "Iron categories")])


# --------------------------------------------------------------------------
# compare pages
# --------------------------------------------------------------------------

TYPE_SUFFIX = re.compile(r"-(irons|driver|fairway-wood|hybrid|wedges|putter)$")


def compare_slug(a, b):
    ab = TYPE_SUFFIX.sub("", a["slug"])
    bb = TYPE_SUFFIX.sub("", b["slug"])
    if a["brand_slug"] == b["brand_slug"]:
        return f"{a['brand_slug']}-{ab}-vs-{bb}"
    return f"{a['brand_slug']}-{ab}-vs-{b['brand_slug']}-{bb}"


# A comparison table is only worth a page if it actually shows differences.
# Below this many highlighted cells the page is two copies of the same chart
# with a verdict paragraph on top — thin content, and 65 pairs had zero.
MIN_COMPARE_DIFFS = 3


def spec_diff_count(a, b):
    """Number of highlighted cells the compare table would render for this pair."""
    aspec = {r["club"]: r for r in a["specs"]}
    bspec = {r["club"]: r for r in b["specs"]}
    n = 0
    for c in set(aspec) & set(bspec):
        ra, rb = aspec[c], bspec[c]
        for k in ("loft", "lie", "length"):
            va, vb = ra.get(k), rb.get(k)
            if va is not None and vb is not None and va != vb:
                n += 1
    return n


def find_pairs(models, by_key):
    """Pair each model with its declared predecessor/successor when both are on file."""
    pairs = OrderedDict()
    name_index = {}
    for m in models:
        name_index[f"{m['brand']} {m['model']}".lower()] = m
        name_index[m["model"].lower()] = m

    def resolve(m, value):
        if not value:
            return None
        v = str(value).strip().lower()
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


def compare_page(a, b, brands):
    slug = compare_slug(a, b)
    # Lead with the two 7-iron lofts: it is the number people are comparing,
    # and it keeps sibling comparisons from reading as near-duplicates.
    a7, b7 = seven_iron(a), seven_iron(b)
    same_brand = a["brand"] == b["brand"]
    label_a = a["model"] if same_brand else f"{a['brand']} {a['model']}"
    label_b = b["model"] if same_brand else f"{b['brand']} {b['model']}"
    # Sibling comparisons name the brand once — repeating "TaylorMade" twice
    # pushed most of these titles past the SERP cutoff.
    title = fit_title(f"{a['brand']} {a['model']} vs {label_b}",
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
        ])
    else:
        desc = fit_desc(head_part, [
            f"Compare {cols} for every club in the {label_a} and {label_b} sets.",
            f"Compare {cols} for every club.",
            "Compare loft, lie and length for every club.",
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
  <div class="table-scroll"><table class="specs">
    <thead><tr><th scope="col">Club</th>{head_cells}</tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>
  <p class="table-note">Highlighted cells differ between the two sets. Lofts and lies are
  factory standard.</p>

  <h2>Which should you choose?</h2>
  <p>{esc(verdict)}</p>
  <p>Both charts are reproduced in full on their own pages:
  <a href="{a['url']}">{esc(a['brand'])} {esc(a['model'])} specs</a> and
  <a href="{b['url']}">{esc(b['brand'])} {esc(b['model'])} specs</a>.</p>
</div>
"""
    # Compare pages stay linked and usable, but out of the index for now: the
    # domain should establish itself on the 241 model pages first.
    page(url, title, desc, body, brands, [bc], noindex=True)
    return slug


def compares_index(pairs_built, brands):
    title = f"Golf Club Spec Comparisons | {SITE_NAME}"
    desc = fit_desc(
        f"{plural(len(pairs_built), 'side-by-side iron comparison')}, generation by "
        f"generation. ",
        ["Compare 7-iron loft, lie, length, offset and swing weight for every club "
         "in each set.",
         "Compare 7-iron loft, lie, length and swing weight for every club.",
         "Compare loft, lie and length for every club."])
    nav, bc = crumbs([("Home", "/"), ("Compare", None)])
    cards = "".join(
        f'<a class="card" href="/compare/{slug}/">'
        f'<span class="card-title">{esc(a["model"])} vs {esc(b["model"])}</span>'
        f'<span class="card-meta">{esc(a["brand"])}'
        f'{"" if a["brand"] == b["brand"] else " vs " + esc(b["brand"])} · '
        f'{a.get("year_introduced")} vs {b.get("year_introduced")}</span></a>'
        for slug, a, b in pairs_built)
    body = f"""{nav}
<div class="wrap">
  <div class="page-head">
    <h1>Specification Comparisons</h1>
    <p class="lede">Generation-to-generation spec comparisons, showing exactly which lofts
    and lies changed between models.</p>
  </div>
  <div class="grid">{cards or '<p>No comparisons available yet.</p>'}</div>
</div>
"""
    page("/compare/", title, desc, body, brands, [bc], noindex=True)


# --------------------------------------------------------------------------
# homepage & static pages
# --------------------------------------------------------------------------

def homepage(brands, models, by_brand):
    title = f"{SITE_NAME} — Golf Club Specifications Database"
    # Count the real archive rather than claiming "thousands" — the number is
    # the credibility signal, and an inflated one is trivially disproved.
    span = loft_span(models)
    head_part = (f"{plural(len(models), 'iron model')}, {span}: source-attributed "
                 f"loft charts. " if span else
                 f"{plural(len(models), 'iron model')}: source-attributed loft "
                 f"charts. ")
    desc = fit_desc(head_part, [
        "Lie angles, lengths and swing weights from Ping, Titleist, Callaway, "
        "Mizuno and more.",
        "Lie angles, lengths and swing weights from every major brand.",
        "Lie angles, lengths and swing weights for every club."])

    by_key = {m["key"]: m for m in models}
    featured = [by_key[k] for k in FEATURED if k in by_key]
    if len(featured) < 8:
        extra = sorted(models, key=lambda m: m.get("year_introduced") or 9999)
        for m in extra:
            if m not in featured:
                featured.append(m)
            if len(featured) == 8:
                break

    recent = sorted(models, key=lambda m: (-(m.get("year_introduced") or 0), m["brand"]))[:8]

    # The "what degree is a sand wedge" family of questions is the highest-volume
    # thing this archive can answer from data it already holds, so the guides get
    # a slot on the homepage rather than living only in the nav.
    wedge_cards = "".join(
        f'<a class="card" href="/wedge-lofts/{w["slug"]}/">'
        f'<span class="card-title">{esc(w["name"])}</span>'
        f'<span class="card-meta">Marked {esc(w["abbr"])}</span>'
        f'<span class="card-spec">{w["band"][0]}°–{w["band"][1]}° · '
        f'{esc(w["distances"][1][1])} carry</span></a>' for w in WEDGE_TYPES)

    brand_cards = "".join(
        f'<a class="card brand-card" href="/{b["slug"]}/" '
        f'style="--brand-color:{esc(b.get("color", "#C9A94E"))}">'
        f'<span class="card-title">{esc(b["name"])}</span>'
        f'<span class="card-meta">{len(by_brand.get(b["slug"], []))} models</span></a>'
        for b in brands if by_brand.get(b["slug"]))

    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": SITE + "/",
        "description": desc,
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint",
                       "urlTemplate": SITE + "/search/?q={search_term_string}"},
            "query-input": "required name=search_term_string",
        },
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
             aria-label="Search golf club models">
      <div id="lc-results" class="search-results" role="listbox"></div>
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

  <h2>Wedge loft guides</h2>
  <p>What degree each wedge is, what it carries, and how the four slots gap together —
  with the numbers taken from the spec charts on this site. Start with the
  <a href="/wedge-lofts/">wedge loft chart</a>.</p>
  <div class="grid">{wedge_cards}</div>

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
        f"About LoftChart: {plural(len(models), 'iron model')} from "
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
  policy</a>. You can opt out site-wide using the
  <a href="https://tools.google.com/dlpage/gaoptout" rel="noopener">Google Analytics opt-out
  browser add-on</a>, or by blocking cookies in your browser settings.</p>""" if GA_ENABLED else """  <p>We do not run analytics on this site. No analytics or advertising cookies are set, and
  we do not build any profile of you or your visit.</p>"""
    body = f"""{nav}
<div class="wrap narrow">
  <div class="page-head">
    <h1>Privacy Policy</h1>
    <p class="lede">Last updated {TODAY}.</p>
  </div>
  <h2>What we collect</h2>
  <p>LoftChart is a static website. We do not ask for, collect or store personal information
  directly, and there are no accounts, logins or newsletter signups.</p>

  <h2>Analytics</h2>
{analytics_section}

  <h2>Fonts</h2>
  <p>Typefaces are served from Google Fonts, which means your browser makes a request to
  Google&rsquo;s servers when a page loads. That request includes your IP address and user
  agent.</p>

  <h2>Search</h2>
  <p>The site search runs entirely in your browser against a JSON file downloaded with the
  page. Your search terms are not sent to us or to any third party.</p>

  <h2>Outbound links</h2>
  <p>Pages may link to retailers, auction sites and archived sources. Once you follow a link
  you are subject to that site&rsquo;s privacy policy, not ours.</p>

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
           placeholder="Search for a model" aria-label="Search golf club models">
    <div id="lc-results" class="search-results" role="listbox"></div>
  </div>
  <p style="margin-top:1.5rem"><a href="/brands/">Browse all brands</a> ·
  <a href="/years/">Browse by year</a> · <a href="/">Go to the homepage</a></p>
</div>
"""
    write("404.html", head("Page not found | " + SITE_NAME,
                           "The page you requested could not be found.",
                           "/404.html", noindex=True) + body + foot(brands))


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
        "bounce": "2°–8°",
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
            ("PGA Tour average", "~140–150 yd"),
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
            ("PGA Tour average", "~115–125 yd"),
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
            ("PGA Tour average", "~100–110 yd"),
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
        "bounce": "4°–10°",
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
            ("PGA Tour average", "~85–95 yd"),
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
            ("PGA Tour average", "~115–125 yd"),
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
    return f"""<div class="table-scroll"><table class="specs">
    <caption>The wedge ladder — typical lofts and full-swing carry for an average
    male amateur.</caption>
    <thead><tr><th scope="col">Wedge</th><th scope="col">Marked</th>
    <th scope="col">Typical loft</th><th scope="col">Typical carry</th></tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>"""


def wedge_distance_table(w):
    rows = "".join(f'<tr><th scope="row">{esc(label)}</th><td>{esc(carry)}</td></tr>'
                   for label, carry in w["distances"])
    return f"""<div class="table-scroll"><table class="specs">
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
  <div class="table-scroll"><table class="specs">
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
  <div class="table-scroll"><table class="specs">
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


def wedge_page(w, models, brands):
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
        "datePublished": TODAY,
        "dateModified": TODAY,
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
  <div class="table-scroll"><table class="specs">
    <caption>{esc(name)} loft by manufacturer, sets introduced {WEDGE_ERA} or later.</caption>
    <thead><tr><th scope="col">Brand</th><th scope="col">Sets on file</th>
    <th scope="col">Loft range</th><th scope="col">Most common</th></tr></thead>
    <tbody>{brand_rows}</tbody></table></div>
  <p class="table-note">Figures are the standard men&rsquo;s right-handed steel build for
  the {w["abbr"]} supplied with each iron set. Standalone specialty wedges are sold in 2°
  increments and are not counted here.{omitted_note}</p>

  <h2>How far does {w["article"].lower()} {lower} go?</h2>
  {wedge_distance_table(w)}
  <p class="table-note">Carry distance, full swing, men&rsquo;s amateur. These are ranges
  rather than a single number on purpose: swing speed and strike quality move wedge
  distance far more than a degree or two of loft does.</p>

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

  <h2>Frequently asked questions</h2>
  <div class="faq">{faq_blocks}</div>

  <div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>Loft figures are computed from the {stats['n']} manufacturer spec charts on file at
    LoftChart that include {w["article"].lower()} {w["abbr"]}; each model page lists its own
    sources.</li>
    <li>Loft bands, bounce ranges and carry distances are the accepted industry conventions
    for a standard men&rsquo;s build, given as ranges because no standard body defines
    them.</li>
  </ul>
  <p>Last reviewed {TODAY}. Spot an error? {email_link()}</p></div>
</div>
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
        "datePublished": TODAY, "dateModified": TODAY,
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

  <div class="table-scroll"><table class="specs">
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
  <div class="table-scroll"><table class="specs">
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

  <div class="sources"><strong>How these figures were compiled:</strong>
  <ul>
    <li>Loft figures are computed from the manufacturer spec charts on file at LoftChart —
    {total} set wedges across {len(summary)} manufacturers. Each model page lists its own
    sources.</li>
    <li>Loft bands, bounce ranges and carry distances are the accepted industry conventions
    for a standard men&rsquo;s build. No governing body defines them, so they are given as
    ranges.</li>
  </ul>
  <p>Last reviewed {TODAY}. Spot an error? {email_link()}</p></div>
</div>
"""
    page("/wedge-lofts/", title, desc, body, brands,
         [bc, article_ld, list_ld, faq_ld], og_type="article")


def wedge_pages(models, brands):
    wedge_index(models, brands)
    for w in WEDGE_TYPES:
        wedge_page(w, models, brands)


# --------------------------------------------------------------------------
# feeds
# --------------------------------------------------------------------------

def sitemap(urls):
    entries = "".join(
        f"<url><loc>{esc(SITE + u)}</loc><lastmod>{TODAY}</lastmod>"
        f"<changefreq>monthly</changefreq><priority>{p}</priority></url>"
        for u, p in urls)
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
            "m": f"{year_range(m)} · {CATEGORY_LABEL.get(m.get('category'), '')}"}
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
    by_brand = defaultdict(list)
    by_year = defaultdict(list)
    by_cat = defaultdict(list)
    for m in models:
        by_brand[m["brand_slug"]].append(m)
        if m.get("year_introduced"):
            by_year[m["year_introduced"]].append(m)
        if m.get("category"):
            by_cat[m["category"]].append(m)

    # comparison pages first, so model pages can link to them
    pairs = find_pairs(models, by_key)
    skipped = [(a, b) for a, b in pairs if spec_diff_count(a, b) < MIN_COMPARE_DIFFS]
    pairs = [(a, b) for a, b in pairs if spec_diff_count(a, b) >= MIN_COMPARE_DIFFS]
    pairs_built = []
    compares_by_key = defaultdict(list)
    for a, b in pairs:
        slug = compare_page(a, b, brands)
        pairs_built.append((slug, a, b))
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
        year_page(y, ms, brands)
    years_index(by_year, brands, models)

    for c, ms in by_cat.items():
        category_page(c, ms, brands)
    categories_index(by_cat, brands, models)

    wedge_pages(models, brands)

    homepage(brands, models, by_brand)
    about_page(brands, models)
    privacy_page(brands)
    not_found(brands)

    audit_descriptions()
    audit_titles()

    search_index(models)
    copy_static()
    robots()
    webmanifest()

    # Sitemap carries indexable pages only: no /compare/ (noindexed wholesale)
    # and no thin year page.
    thin_years = [y for y, ms in by_year.items() if len(ms) < YEAR_MIN_MODELS]
    urls = [("/", "1.0"), ("/brands/", "0.8"), ("/years/", "0.6"),
            ("/category/", "0.6"), ("/wedge-lofts/", "0.9"),
            ("/about/", "0.4"), ("/privacy/", "0.2")]
    urls += [(f"/wedge-lofts/{w['slug']}/", "0.8") for w in WEDGE_TYPES]
    urls += [(m["url"], "0.9") for m in models]
    urls += [(f"/{b['slug']}/", "0.8") for b in brands if by_brand.get(b["slug"])]
    urls += [(f"/years/{y}/", "0.5") for y in by_year if y not in thin_years]
    urls += [(f"/category/{c}/", "0.6") for c in by_cat]
    sitemap(urls)

    print(f"Built {len(models)} models, {len([b for b in brands if by_brand.get(b['slug'])])} "
          f"brands, {len(pairs_built)} comparisons "
          f"({len(skipped)} pairs skipped for <{MIN_COMPARE_DIFFS} differing cells), "
          f"{len(urls)} indexable URLs, {len(thin_years)} year pages noindexed → {OUT}")
    if errors:
        print(f"({len(errors)} non-fatal data warnings — see above)")


if __name__ == "__main__":
    main()
