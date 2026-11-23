#!/usr/bin/env python3
"""Check the site in docs/ for broken internal links and missing index entries.

Usage: python3 tools/check_site.py
Exits with status 1 if anything is wrong. External links are not fetched.
"""

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
OWN_HOSTS = {"chriswaite.dev", "www.chriswaite.dev"}
SKIP_SCHEMES = ("mailto:", "tel:", "data:", "javascript:")


class RefCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []  # (tag, attribute, value, line)
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        line = self.getpos()[0]
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        for name in ("href", "src", "poster"):
            if name in attrs:
                self.refs.append((tag, name, (attrs[name] or "").strip(), line))
        # srcset entries are "url descriptor" separated by ", " - URLs may contain commas
        for entry in re.split(r",\s+", attrs.get("srcset") or ""):
            if entry.strip():
                self.refs.append((tag, "srcset", entry.split()[0], line))


def check_page(page):
    problems = []
    parser = RefCollector()
    parser.feed(page.read_text(encoding="utf-8"))

    for tag, attr, url, line in parser.refs:
        where = f"{page.relative_to(DOCS_DIR.parent)}:{line}"
        if not url:
            problems.append(f"{where} empty {attr} on <{tag}>")
            continue
        if url.startswith(SKIP_SCHEMES):
            continue
        if url.startswith("#"):
            if len(url) > 1 and url[1:] not in parser.ids:
                problems.append(f"{where} missing anchor {url}")
            continue

        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") or url.startswith("//"):
            if parsed.netloc not in OWN_HOSTS:
                continue
            path = parsed.path or "/"
        elif parsed.scheme:
            problems.append(f"{where} unsupported link scheme: {url}")
            continue
        else:
            path = parsed.path

        path = unquote(path)
        if path.startswith("/"):
            target = DOCS_DIR / path.lstrip("/")
        else:
            target = page.parent / path
        target = Path(os.path.normpath(target))
        if not (target.is_file() or (target / "index.html").is_file()):
            problems.append(f"{where} broken link: {url}")
    return problems


def check_indexes():
    problems = []
    slugs = {
        d.name for d in (DOCS_DIR / "devlog").iterdir()
        if (d / "index.html").is_file()
    }
    sitemap = (DOCS_DIR / "sitemap.xml").read_text(encoding="utf-8")
    in_sitemap = set(re.findall(r"/devlog/([^/<]+)/", sitemap))
    homepage = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
    on_homepage = set(re.findall(r'href="/?devlog/([^"/]+)/?"', homepage))

    for slug in sorted(slugs - in_sitemap):
        problems.append(f"post missing from sitemap.xml: {slug}")
    for slug in sorted(in_sitemap - slugs):
        problems.append(f"sitemap.xml lists a post that does not exist: {slug}")
    for slug in sorted(slugs - on_homepage):
        problems.append(f"post missing from homepage: {slug}")
    for slug in sorted(on_homepage - slugs):
        problems.append(f"homepage links to a post that does not exist: {slug}")
    return problems


def main():
    pages = sorted(DOCS_DIR.rglob("*.html"))
    problems = check_indexes()
    for page in pages:
        problems.extend(check_page(page))

    for problem in problems:
        print(problem)
    print(f"\nChecked {len(pages)} pages: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
