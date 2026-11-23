#!/usr/bin/env python3
"""Site generator for chriswaite.dev.

The post files in docs/devlog/<slug>/index.html are the source of truth for
post content. This script re-renders them with the current template and
generates everything derived from them:

    docs/index.html            card homepage
    docs/series/<slug>/        one page per series
    docs/sitemap.xml, docs/feed.xml, docs/llms.txt
    header of the hand-written pages (about, experiments, 404)

Usage: python3 tools/build_site.py
The blog editor calls build_all() after every save.

Series are defined in tools/series.json. Page layout lives in tools/templates.
"""

import html
import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

SITE = "https://chriswaite.dev"
SITE_TITLE = "chriswaite.dev"
SITE_DESCRIPTION = (
    "Christopher Waite's devlog covering game development, "
    "creative coding, and technology experiments."
)
AUTHOR = {
    "@type": "Person",
    "name": "Christopher Waite",
    "url": f"{SITE}/about/",
}
FEED_ITEMS = 30

TOOLS_DIR = Path(__file__).resolve().parent
DOCS_DIR = TOOLS_DIR.parent / "docs"
TEMPLATES_DIR = TOOLS_DIR / "templates"
SERIES_FILE = TOOLS_DIR / "series.json"

MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
NAV = [("devlog", "/"), ("experiments", "/experiments/"), ("about", "/about/")]
HAND_WRITTEN_PAGES = {"about/index.html": "about", "experiments/index.html": "experiments", "404.html": None}

CONTENT_START = "<!-- post:content -->"
CONTENT_END = "<!-- /post:content -->"


# --- helpers ---------------------------------------------------------------

def esc(text):
    return html.escape(text, quote=True)


def fill(template, values):
    """Replace {{KEY}} placeholders in one pass (values are inserted literally)."""
    return re.sub(
        r"\{\{([A-Z_]+)\}\}",
        lambda m: values.get(m.group(1), m.group(0)),
        template,
    )


def template(name):
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def write_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def json_ld(data, indent=8):
    """JSON-LD block that is safe to embed in a <script> element."""
    text = json.dumps(data, indent=2, ensure_ascii=False).replace("<", "\\u003c")
    pad = " " * indent
    return "\n".join(pad + line for line in text.split("\n"))


def optional_p(text, indent):
    """A paragraph, or nothing when the text is empty."""
    return f'{" " * indent}<p>{esc(text)}</p>\n' if text else ""


def description_meta(text):
    """Description tags for the head; left out entirely when there is no description."""
    if not text:
        return ""
    return (
        f'        <meta name="description" content="{esc(text)}" />\n'
        f'        <meta property="og:description" content="{esc(text)}" />\n'
        f'        <meta name="twitter:description" content="{esc(text)}" />\n'
    )


def long_date(iso):
    year, month, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(month)]} {year}"


def short_date(iso):
    year, month, _ = iso.split("-")
    return f"{MONTHS[int(month)]} {year}"


def first_image(content):
    match = re.search(r'<img\b[^>]*?\ssrc="([^"]+)"', content, re.DOTALL)
    return html.unescape(match.group(1)) if match else None


def thumb(url, width, height):
    """Ask Cloudinary for a cropped thumbnail rather than the full-size original."""
    return url.replace(
        "/image/upload/",
        f"/image/upload/c_fill,g_auto,w_{width},h_{height},f_auto,q_auto/",
        1,
    )


def post_url(slug):
    return f"{SITE}/devlog/{slug}/"


# --- shared page furniture -------------------------------------------------

FEED_ICON = (
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
    'stroke-width="3" stroke-linecap="round" aria-hidden="true">'
    '<circle cx="5" cy="19" r="2.5" fill="currentColor" stroke="none" />'
    '<path d="M3 11a10 10 0 0 1 10 10M3 4a17 17 0 0 1 17 17" /></svg>'
)


def site_header(current=None, within=False):
    """The nav. `current` is the section to highlight; `within` means the page
    is inside that section (a post or series page) rather than the section itself."""
    items = []
    for label, href in NAV:
        cur = ""
        if label == current:
            cur = ' aria-current="true"' if within else ' aria-current="page"'
        items.append(f'                    <li><a href="{href}"{cur}>{label}</a></li>')
    items.append(
        '                    <li><a class="feed-link" href="/feed.xml" '
        f'aria-label="RSS feed" title="RSS feed">{FEED_ICON}</a></li>'
    )
    return (
        "<!-- site:header -->\n"
        '        <header class="site-header">\n'
        '            <nav aria-label="Site">\n'
        "                <ul>\n" + "\n".join(items) + "\n"
        "                </ul>\n"
        "            </nav>\n"
        "        </header>\n"
        "<!-- /site:header -->"
    )


# --- posts -----------------------------------------------------------------

def parse_post(text, slug):
    """Extract the editable fields from a post file."""
    title = re.search(r'<h1 class="title">(.*?)</h1>', text, re.DOTALL)
    desc = re.search(r'<meta name="description" content="([^"]*)"', text)
    date = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})', text)

    if CONTENT_START in text and CONTENT_END in text:
        start = text.index(CONTENT_START) + len(CONTENT_START)
        content = text[start:text.index(CONTENT_END)].strip("\n")
    else:
        # Posts written before the content markers existed
        body = re.search(
            r'<article class="post">\n?(.*?)\n?[ \t]*</article>\s*</main>', text, re.DOTALL
        )
        content = body.group(1) if body else ""

    return {
        "slug": slug,
        "title": html.unescape(re.sub(r"\s+", " ", title.group(1)).strip()) if title else slug,
        "description": html.unescape(desc.group(1)) if desc else "",
        "date": date.group(1) if date else "1970-01-01",
        "content": content,
    }


def load_posts(docs_dir=DOCS_DIR):
    """All posts, newest first."""
    posts = []
    for page in (docs_dir / "devlog").glob("*/index.html"):
        post = parse_post(page.read_text(encoding="utf-8"), page.parent.name)
        post["image"] = first_image(post["content"])
        posts.append(post)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


def load_series(posts=None):
    """Series from series.json, with post slugs resolved to post dicts."""
    if not SERIES_FILE.exists():
        return []
    series = json.loads(SERIES_FILE.read_text(encoding="utf-8"))
    if posts is not None:
        by_slug = {p["slug"]: p for p in posts}
        for s in series:
            s["items"] = [by_slug[slug] for slug in s["posts"] if slug in by_slug]
        series = [s for s in series if s["items"]]
    return series


def series_for(slug, series):
    for s in series:
        if slug in s["posts"]:
            return s
    return None


def render_post(post, posts=None, series=None, root=""):
    """Full HTML for a post. `root` prefixes asset paths (used by the editor preview)."""
    posts = posts or []
    series = series or []
    slug = post["slug"]
    url = post_url(slug)
    image = first_image(post["content"])
    has_code = bool(re.search(r"<pre[\s>]", post["content"], re.IGNORECASE))
    in_series = series_for(slug, series)

    ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post["title"],
        "description": post["description"],
        "url": url,
        "mainEntityOfPage": url,
        "datePublished": post["date"],
        "author": AUTHOR,
        "publisher": AUTHOR,
    }
    if image:
        ld["image"] = image
    if in_series:
        ld["isPartOf"] = {
            "@type": "CreativeWorkSeries",
            "name": in_series["title"],
            "url": f"{SITE}/series/{in_series['slug']}/",
        }

    if image:
        image_meta = (
            f'        <meta property="og:image" content="{esc(image)}" />\n'
            '        <meta name="twitter:card" content="summary_large_image" />\n'
            f'        <meta name="twitter:image" content="{esc(image)}" />\n'
        )
    else:
        image_meta = '        <meta name="twitter:card" content="summary" />\n'

    series_tag = series_box = ""
    if in_series:
        titles = {p["slug"]: p["title"] for p in in_series.get("items", [])}
        titles.setdefault(slug, post["title"])
        listed = [s for s in in_series["posts"] if s in titles]
        part = listed.index(slug) + 1
        series_href = f"/series/{in_series['slug']}/"
        series_tag = (
            f'                    <p class="series-tag"><a href="{series_href}">'
            f'{esc(in_series["title"])}</a> · Part {part} of {len(listed)}</p>\n'
        )
        rows = []
        for s in listed:
            if s == slug:
                rows.append(f'                    <li aria-current="page">{esc(titles[s])}</li>')
            else:
                rows.append(f'                    <li><a href="/devlog/{s}/">{esc(titles[s])}</a></li>')
        series_box = (
            '            <aside class="series-box" aria-labelledby="series-heading">\n'
            '                <p class="kicker">Series</p>\n'
            f'                <h2 id="series-heading"><a href="{series_href}">{esc(in_series["title"])}</a></h2>\n'
            "                <ol>\n" + "\n".join(rows) + "\n                </ol>\n"
            "            </aside>\n"
        )

    # Newer / older links (posts are newest first)
    post_nav = ""
    order = [p["slug"] for p in posts]
    if slug in order:
        i = order.index(slug)
        links = []
        if i + 1 < len(posts):
            older = posts[i + 1]
            links.append(
                f'                <a class="older" href="/devlog/{older["slug"]}/" rel="prev">'
                f'<span>Older</span>{esc(older["title"])}</a>'
            )
        if i > 0:
            newer = posts[i - 1]
            links.append(
                f'                <a class="newer" href="/devlog/{newer["slug"]}/" rel="next">'
                f'<span>Newer</span>{esc(newer["title"])}</a>'
            )
        if links:
            post_nav = (
                '            <nav class="post-nav" aria-label="More posts">\n'
                + "\n".join(links) + "\n            </nav>\n"
            )

    return fill(template("post.html"), {
        "TITLE": esc(post["title"]),
        "DESCRIPTION": esc(post["description"]),
        "URL": url,
        "DATE_ISO": post["date"],
        "DATE_DISPLAY": long_date(post["date"]),
        "IMAGE_META": image_meta,
        "ROOT": root,
        "PRISM_CSS": f'        <link rel="stylesheet" href="{root}/styles/prism.css" />\n' if has_code else "",
        "PRISM_JS": f'        <script src="{root}/scripts/prism.js"></script>\n' if has_code else "",
        "JSON_LD": json_ld(ld),
        "HEADER": site_header("devlog", within=True),
        "SERIES_TAG": series_tag,
        "SERIES_BOX": series_box,
        "POST_NAV": post_nav,
        "CONTENT": post["content"],
    })


def write_post(post, docs_dir=DOCS_DIR):
    """Save a post from its fields (used by the editor, which then calls build_all)."""
    path = docs_dir / "devlog" / post["slug"] / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_post(post), encoding="utf-8")
    return path


def set_series(post_slug, series_slug):
    """Move a post into the given series (or out of all series if empty)."""
    if not SERIES_FILE.exists():
        return
    series = json.loads(SERIES_FILE.read_text(encoding="utf-8"))
    changed = False
    for s in series:
        if s["slug"] == series_slug:
            if post_slug not in s["posts"]:
                s["posts"].append(post_slug)
                changed = True
        elif post_slug in s["posts"]:
            s["posts"].remove(post_slug)
            changed = True
    if changed:
        SERIES_FILE.write_text(
            json.dumps(series, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


# --- cards and listing pages -----------------------------------------------

def card(post, heading="h2", featured=False, eager=False, indent=16):
    pad = " " * indent
    if post["image"]:
        width, height = (960, 540) if featured else (640, 360)
        media = (
            f'<img src="{esc(thumb(post["image"], width, height))}" alt="" '
            f'width="{width}" height="{height}" '
            f'loading="{"eager" if eager else "lazy"}" decoding="async" />'
        )
    else:
        tile = sum(map(ord, post["slug"])) % 3 + 1
        year, month, _ = post["date"].split("-")
        media = (
            f'<div class="card-noimg tile-{tile}" aria-hidden="true">'
            f"{MONTHS[int(month)][:3]}<span>{year}</span></div>"
        )
    cls = "card featured" if featured else "card"
    return (
        f'{pad}<article class="{cls}">\n'
        f'{pad}    <div class="card-media">{media}</div>\n'
        f'{pad}    <div class="card-body">\n'
        f'{pad}        <time datetime="{post["date"]}">{short_date(post["date"])}</time>\n'
        f'{pad}        <{heading}><a href="/devlog/{post["slug"]}/">{esc(post["title"])}</a></{heading}>\n'
        f'{pad}        <p>{esc(post["description"])}</p>\n'
        f'{pad}    </div>\n'
        f'{pad}</article>'
    )


def build_home(posts, series):
    in_series = {slug for s in series for slug in s["posts"]}

    # One stream, newest first. A series sits where its most recent post would.
    stream = [(p["date"], "post", p) for p in posts if p["slug"] not in in_series]
    stream += [(max(p["date"] for p in s["items"]), "series", s) for s in series]
    stream.sort(key=lambda item: item[0], reverse=True)

    blocks = []
    images_seen = 0
    for i, (_, kind, item) in enumerate(stream):
        if kind == "post":
            blocks.append(card(item, featured=(i == 0), eager=images_seen < 4))
            images_seen += 1
            continue
        n = series.index(item)
        cards = "\n".join(card(p, heading="h3", indent=24) for p in item["items"])
        blocks.append(
            f'                <section class="series-block band-{n % 4 + 1}" '
            f'aria-labelledby="series-{item["slug"]}">\n'
            '                    <header>\n'
            f'                        <h2 id="series-{item["slug"]}">'
            f'<a href="/series/{item["slug"]}/">{esc(item["title"])}</a></h2>\n'
            f'                        <p class="kicker">Series · {len(item["items"])} posts</p>\n'
            + optional_p(item["description"], 24) +
            '                    </header>\n'
            f'                    <div class="series-row" tabindex="0" role="group" '
            f'aria-label="{esc(item["title"])} posts">\n'
            f'{cards}\n'
            '                    </div>\n'
            '                </section>'
        )

    main = (
        '            <h1 class="sr-only">chriswaite.dev</h1>\n'
        f'            <p class="intro">{esc(SITE_DESCRIPTION)}</p>\n'
        '            <div class="card-grid">\n' + "\n".join(blocks) + "\n            </div>"
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "Blog",
        "name": SITE_TITLE,
        "description": SITE_DESCRIPTION,
        "url": f"{SITE}/",
        "author": AUTHOR,
    }
    return fill(template("page.html"), {
        "HEAD_TITLE": SITE_TITLE,
        "TITLE": SITE_TITLE,
        "DESCRIPTION_META": description_meta(SITE_DESCRIPTION),
        "URL": f"{SITE}/",
        "JSON_LD": json_ld(ld),
        "HEADER": site_header("devlog"),
        "MAIN": main,
    })


def build_series_page(s):
    url = f"{SITE}/series/{s['slug']}/"
    cards = "\n".join(card(p, eager=i < 3) for i, p in enumerate(s["items"]))
    main = (
        '            <header class="page-header">\n'
        f'                <h1>{esc(s["title"])}</h1>\n'
        '                <p class="kicker">Series</p>\n'
        + optional_p(s["description"], 16) +
        '            </header>\n'
        '            <div class="card-grid">\n' + cards + "\n            </div>"
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": s["title"],
        "url": url,
        "hasPart": [
            {"@type": "BlogPosting", "headline": p["title"], "url": post_url(p["slug"])}
            for p in s["items"]
        ],
    }
    return fill(template("page.html"), {
        # "Series" keeps this distinct from a post with the same name
        "HEAD_TITLE": f"{esc(s['title'])} – Series – chriswaite.dev",
        "TITLE": esc(s["title"]),
        "DESCRIPTION_META": description_meta(s["description"]),
        "URL": url,
        "JSON_LD": json_ld(ld),
        "HEADER": site_header("devlog", within=True),
        "MAIN": main,
    })


# --- sitemap, feed, llms.txt -----------------------------------------------

def build_sitemap(posts, series):
    latest = posts[0]["date"] if posts else None
    # (url, last modified): listing pages change whenever their newest post does
    urls = [(f"{SITE}/", latest), (f"{SITE}/about/", None), (f"{SITE}/experiments/", None)]
    urls += [
        (f"{SITE}/series/{s['slug']}/", max(p["date"] for p in s["items"])) for s in series
    ]
    urls += [(post_url(p["slug"]), p["date"]) for p in sorted(posts, key=lambda p: p["slug"])]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(
            f"  <url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>"
            for u, d in urls
        )
        + "\n</urlset>\n"
    )


def build_feed(posts):
    items = []
    for post in posts[:FEED_ITEMS]:
        url = post_url(post["slug"])
        published = datetime.strptime(post["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        items.append(
            "    <item>\n"
            f"      <title>{xml_escape(post['title'])}</title>\n"
            f"      <link>{url}</link>\n"
            f'      <guid isPermaLink="true">{url}</guid>\n'
            f"      <pubDate>{format_datetime(published)}</pubDate>\n"
            f"      <description>{xml_escape(post['description'])}</description>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{xml_escape(SITE_TITLE)}</title>\n"
        f"    <link>{SITE}/</link>\n"
        f"    <description>{xml_escape(SITE_DESCRIPTION)}</description>\n"
        "    <language>en-gb</language>\n"
        f'    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )


def build_llms(posts, series):
    """llms.txt: a plain-text map of the site for AI crawlers."""
    lines = [
        f"# {SITE_TITLE}",
        "",
        f"> {SITE_DESCRIPTION}",
        "",
        "## Pages",
        "",
        f"- [About]({SITE}/about/)",
        f"- [Experiments]({SITE}/experiments/)",
        "",
        "## Series",
        "",
    ]
    for s in series:
        summary = f": {s['description']}" if s["description"] else ""
        lines.append(f"- [{s['title']}]({SITE}/series/{s['slug']}/){summary}")
    lines += ["", "## Posts", ""]
    for p in posts:
        summary = f": {p['description']}" if p["description"] else ""
        lines.append(f"- [{p['title']}]({post_url(p['slug'])}) ({p['date']}){summary}")
    return "\n".join(lines) + "\n"


# --- hand-written pages ----------------------------------------------------

def refresh_page_furniture(docs_dir=DOCS_DIR):
    """Keep the header of about/experiments/404 in step with the rest."""
    changed = 0
    for rel, current in HAND_WRITTEN_PAGES.items():
        path = docs_dir / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"<!-- site:header -->.*?<!-- /site:header -->",
            lambda m: site_header(current), text, flags=re.DOTALL,
        )
        changed += write_if_changed(path, text)
    return changed


# --- build -----------------------------------------------------------------

def build_all(docs_dir=DOCS_DIR):
    posts = load_posts(docs_dir)
    series = load_series(posts)

    changed = 0
    for post in posts:
        page = docs_dir / "devlog" / post["slug"] / "index.html"
        changed += write_if_changed(page, render_post(post, posts, series))

    changed += write_if_changed(docs_dir / "index.html", build_home(posts, series))
    for s in series:
        changed += write_if_changed(
            docs_dir / "series" / s["slug"] / "index.html", build_series_page(s)
        )
    # Remove the pages of series that no longer exist
    current = {s["slug"] for s in series}
    for page in (docs_dir / "series").glob("*/index.html"):
        if page.parent.name not in current:
            page.unlink()
            page.parent.rmdir()
            changed += 1
    changed += write_if_changed(docs_dir / "sitemap.xml", build_sitemap(posts, series))
    changed += write_if_changed(docs_dir / "feed.xml", build_feed(posts))
    changed += write_if_changed(docs_dir / "llms.txt", build_llms(posts, series))
    changed += refresh_page_furniture(docs_dir)
    return len(posts), len(series), changed


if __name__ == "__main__":
    post_count, series_count, changed_count = build_all()
    print(f"{post_count} posts, {series_count} series, {changed_count} file(s) updated")
