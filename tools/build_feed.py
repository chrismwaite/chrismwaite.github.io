#!/usr/bin/env python3
"""Generate docs/feed.xml (RSS 2.0) from the posts in docs/devlog.

Usage: python3 tools/build_feed.py
The blog editor also calls build_feed() every time a post is saved.
"""

import html
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://chriswaite.dev"
SITE_TITLE = "chriswaite.dev"
SITE_DESCRIPTION = (
    "Christopher Waite's devlog covering game development, "
    "creative coding, and technology experiments."
)
MAX_ITEMS = 30
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def read_posts(docs_dir=DOCS_DIR):
    """Return [(date, slug, title, description)] for every post, newest first."""
    posts = []
    for page in (docs_dir / "devlog").glob("*/index.html"):
        text = page.read_text(encoding="utf-8")
        date = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})', text)
        if not date:
            continue
        title = re.search(r'<h1 class="title">(.*?)</h1>', text, re.DOTALL)
        desc = re.search(r'<meta name="description" content="([^"]*)"', text)
        posts.append((
            date.group(1),
            page.parent.name,
            html.unescape(title.group(1).strip()) if title else page.parent.name,
            html.unescape(desc.group(1)) if desc else "",
        ))
    posts.sort(reverse=True)
    return posts


def build_feed(docs_dir=DOCS_DIR):
    posts = read_posts(docs_dir)[:MAX_ITEMS]
    items = []
    for date, slug, title, description in posts:
        url = f"{SITE}/devlog/{slug}/"
        published = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        items.append(
            "    <item>\n"
            f"      <title>{escape(title)}</title>\n"
            f"      <link>{url}</link>\n"
            f'      <guid isPermaLink="true">{url}</guid>\n'
            f"      <pubDate>{format_datetime(published)}</pubDate>\n"
            f"      <description>{escape(description)}</description>\n"
            "    </item>"
        )

    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(SITE_TITLE)}</title>\n"
        f"    <link>{SITE}/</link>\n"
        f"    <description>{escape(SITE_DESCRIPTION)}</description>\n"
        "    <language>en-gb</language>\n"
        f'    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    out = docs_dir / "feed.xml"
    out.write_text(feed, encoding="utf-8")
    return out, len(items)


if __name__ == "__main__":
    path, count = build_feed()
    print(f"Wrote {count} posts to {path}")
