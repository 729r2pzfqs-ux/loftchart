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
    """Total order over club labels.

    Returns a (rank, label) tuple rather than a bare float: anything that
    compares equal here falls back to set-iteration order in compare_page,
    which varies per interpreter run and produced churning diffs in the built
    pages. The trailing label keeps the order total and the build reproducible.
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
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


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

            specs.sort(key=lambda r: club_sort_key(r["club"]))
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
      <p>© {date.today().year} LoftChart.com · <a href="mailto:{EMAIL}">{EMAIL}</a></p>
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
        spec = (f'<span class="card-spec">{esc(club_noun(m, s7["club"]))}: '
                f'{num(s7["loft"])}° loft · '
                f'{num(s7["lie"])}° lie · {num(s7["length"])}&Prime;</span>')
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
        head_part = (f"{m['brand']} {m['model']} specifications: {num(s7['loft'])}° loft "
                     f"({club_noun(m, s7['club'])}), {num(s7['lie'])}° lie, "
                     f"{num(s7['length'])}\" length. ")
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
                     f'original catalogue page, <a href="mailto:{EMAIL}">send it over</a> '
                     "and we will update the chart.</p></div>")

    sources_html = ("<div class=\"sources\"><strong>Data compiled from:</strong><ul>"
                    + "".join(f"<li>{esc(s)}</li>" for s in (m.get("sources") or []))
                    + f"</ul><p>Last reviewed {TODAY}. Spot an error? "
                    f'<a href="mailto:{EMAIL}">{EMAIL}</a></p></div>')

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

  <h2>Finding a used set</h2>
  <p>The {esc(m['brand'])} {esc(m['model'])} is no longer in production, so the used market is
  the only source. Search eBay, 2nd Swing, Golf Avenue and the PGA Tour Superstore trade-in
  listings, and check the loft and lie against the chart above before buying — sets this age
  have often been bent from standard.</p>

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
    page(f"/years/{year}/", title, desc, body, brands, [bc, item_list(ms, f"{year} releases")])


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
        f'<td>{num(seven_iron(m)["lie"]) if seven_iron(m) else "—"}</td>'
        f'<td>{num(seven_iron(m)["length"]) if seven_iron(m) else "—"}</td></tr>'
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
    clubs = sorted(set(aspec) | set(bspec), key=club_sort_key)

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
    page(url, title, desc, body, brands, [bc])
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
    page("/compare/", title, desc, body, brands, [bc])


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

  <h2>What is a loft chart?</h2>
  <p>A loft chart lists the factory loft of every club in a set, usually alongside lie angle,
  club length, offset and swing weight. It is the reference you need when you are gapping a
  bag, replacing a single lost iron, buying a used set, or working out why a new 7-iron flies
  further than the one it replaced.</p>
  <p>Lofts have moved considerably over time. A 1980s game-improvement 7-iron sat around 36°;
  a modern distance iron of the same number can be 28–30°. That is why comparing sets by club
  number alone is misleading, and why every chart here records the year the set was
  introduced.</p>
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
  want it. Email <a href="mailto:{EMAIL}">{EMAIL}</a> with the source and we will update the
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
  <p>Questions about this policy: <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
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

    urls = [("/", "1.0"), ("/brands/", "0.8"), ("/years/", "0.6"),
            ("/category/", "0.6"), ("/compare/", "0.6"),
            ("/about/", "0.4"), ("/privacy/", "0.2")]
    urls += [(m["url"], "0.9") for m in models]
    urls += [(f"/{b['slug']}/", "0.8") for b in brands if by_brand.get(b["slug"])]
    urls += [(f"/years/{y}/", "0.5") for y in by_year]
    urls += [(f"/category/{c}/", "0.6") for c in by_cat]
    urls += [(f"/compare/{s}/", "0.5") for s, _, _ in pairs_built]
    sitemap(urls)

    print(f"Built {len(models)} models, {len([b for b in brands if by_brand.get(b['slug'])])} "
          f"brands, {len(pairs_built)} comparisons, {len(urls)} URLs → {OUT}")
    if errors:
        print(f"({len(errors)} non-fatal data warnings — see above)")


if __name__ == "__main__":
    main()
