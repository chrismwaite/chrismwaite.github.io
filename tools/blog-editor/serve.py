#!/usr/bin/env python3
"""Blog editor server. Serves the editor UI and provides API endpoints for post management.

Usage: python3 serve.py [port]
Default port: 8010
"""

import hashlib
import html as html_module
import json
import os
import re
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_feed import build_feed  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
ALLOWED_ORIGINS = {f"http://{host}" for host in ALLOWED_HOSTS}
MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

# Load .env for Cloudinary credentials
CLOUDINARY = {}
env_path = SCRIPT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            CLOUDINARY[k.strip()] = v.strip()


class EditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def request_allowed(self):
        """Only serve requests that genuinely come from this local editor.

        Checking Host blocks DNS-rebinding; checking Origin stops other web
        pages open in the browser from posting to the API.
        """
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send_json({"error": "Forbidden host"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            self.send_json({"error": "Forbidden origin"}, 403)
            return False
        return True

    def valid_slug(self, slug):
        if SLUG_RE.match(slug):
            return True
        self.send_json({"error": f"Invalid slug: {slug}"}, 400)
        return False

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_json({"error": "Content-Length required"}, 411)
            return None
        return self.rfile.read(length)

    def do_GET(self):
        if not self.request_allowed():
            return
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])

        # Never serve dotfiles (.env, .git, ...)
        if any(part.startswith(".") for part in path.split("/")):
            self.send_error(404)
            return

        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/tools/blog-editor/")
            self.end_headers()
            return

        if path == "/api/posts":
            self.list_posts()
        elif path.startswith("/api/posts/"):
            slug = path[len("/api/posts/"):]
            self.read_post(slug)
        else:
            super().do_GET()

    def do_POST(self):
        if not self.request_allowed():
            return
        path = unquote(self.path)

        if path == "/api/upload":
            self.upload_image()
        elif path.startswith("/api/posts/"):
            slug = path[len("/api/posts/"):]
            self.save_post(slug)
        else:
            self.send_error(404)

    def list_posts(self):
        devlog = DOCS_DIR / "devlog"
        slugs = sorted(
            d.name for d in devlog.iterdir()
            if d.is_dir() and (d / "index.html").exists()
        )
        self.send_json(slugs)

    def read_post(self, slug):
        if not self.valid_slug(slug):
            return
        filepath = DOCS_DIR / "devlog" / slug / "index.html"
        if not filepath.exists():
            self.send_error(404, f"Post not found: {slug}")
            return
        self.send_json({"slug": slug, "html": filepath.read_text(encoding="utf-8")})

    def upload_image(self):
        cloud = CLOUDINARY.get("CLOUDINARY_CLOUD_NAME", "")
        api_key = CLOUDINARY.get("CLOUDINARY_API_KEY", "")
        api_secret = CLOUDINARY.get("CLOUDINARY_API_SECRET", "")

        if not all([cloud, api_key, api_secret]):
            self.send_json({"error": "Cloudinary credentials not configured in .env"}, 500)
            return

        # Parse multipart form data
        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            self.send_json({"error": "Invalid content type"}, 400)
            return

        boundary = content_type.split("boundary=")[1].strip()
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]

        body = self.read_body()
        if body is None:
            return
        boundary_bytes = boundary.encode()

        parts = body.split(b"--" + boundary_bytes)
        file_data = None
        filename = "upload"

        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers = part[:header_end].decode("utf-8", errors="replace")
            if 'name="file"' not in headers:
                continue
            # Extract filename
            fn_match = re.search(r'filename="([^"]+)"', headers)
            if fn_match:
                filename = fn_match.group(1)
            file_data = part[header_end + 4:]
            # Strip trailing \r\n
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]
            break

        if file_data is None:
            self.send_json({"error": "No file found in request"}, 400)
            return

        # Cloudinary signed upload
        timestamp = str(int(time.time()))
        params = f"timestamp={timestamp}{api_secret}"
        signature = hashlib.sha1(params.encode()).hexdigest()

        # Build multipart request for Cloudinary
        cb = b"----CloudinaryBoundary"
        parts_out = []

        for key, val in [("api_key", api_key), ("timestamp", timestamp), ("signature", signature)]:
            parts_out.append(
                b"--" + cb + b"\r\n"
                + f'Content-Disposition: form-data; name="{key}"\r\n\r\n{val}'.encode()
            )

        parts_out.append(
            b"--" + cb + b"\r\n"
            + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
            + b"Content-Type: application/octet-stream\r\n\r\n"
            + file_data
        )

        payload = b"\r\n".join(parts_out) + b"\r\n--" + cb + b"--\r\n"

        url = f"https://api.cloudinary.com/v1_1/{cloud}/image/upload"
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={cb.decode()}")

        try:
            resp = urlopen(req)
            result = json.loads(resp.read().decode())
            image_url = result.get("secure_url", result.get("url", ""))
            self.send_json({"url": image_url})
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, "read"):
                error_msg = e.read().decode("utf-8", errors="replace")
            self.send_json({"error": f"Cloudinary upload failed: {error_msg}"}, 500)

    def save_post(self, slug):
        if not self.valid_slug(slug):
            return
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.send_json({"error": "Expected application/json"}, 415)
            return
        body = self.read_body()
        if body is None:
            return
        try:
            html = json.loads(body).get("html", "")
        except (ValueError, AttributeError):
            self.send_json({"error": "Invalid JSON"}, 400)
            return
        if not html.strip():
            self.send_json({"error": "Empty post"}, 400)
            return

        # Create directory and write file
        post_dir = DOCS_DIR / "devlog" / slug
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "index.html").write_text(html, encoding="utf-8")

        # Update sitemap, homepage and RSS feed
        self.update_sitemap(slug)
        self.update_homepage(slug, html)
        build_feed(DOCS_DIR)

        self.send_json({"ok": True, "path": f"devlog/{slug}/index.html"})

    def update_homepage(self, slug, post_html):
        """Add or update the post entry in docs/index.html, keeping date order."""

        index_path = DOCS_DIR / "index.html"
        if not index_path.exists():
            return

        # Extract metadata from the post HTML
        title_match = re.search(r'<h1 class="title">([^<]+)</h1>', post_html)
        title = html_module.unescape(title_match.group(1)) if title_match else slug

        desc_match = re.search(r'<meta name="description" content="([^"]*)"', post_html)
        description = html_module.unescape(desc_match.group(1)) if desc_match else ""

        date_match = re.search(r'"datePublished":\s*"(\d{4})-(\d{2})', post_html)
        if date_match:
            year, month = date_match.group(1), int(date_match.group(2))
            date_display = f"{MONTHS[month]} {year}"
            date_key = (int(year), month)
        else:
            date_display = ""
            date_key = None

        # Build the new article entry
        title_esc = html_module.escape(title)
        desc_esc = html_module.escape(description)
        new_article = (
            f'                    <article>\n'
            f'                        <span class="title"'
            f'><a href="devlog/{slug}"'
            f'>{title_esc}</a'
            f'></span'
            f'>\n'
            f'                        <span class="date">{date_display}</span>\n'
            f'                        <div class="summary">\n'
            f'                            {desc_esc}\n'
            f'                        </div>\n'
            f'                    </article>'
        )

        homepage = index_path.read_text(encoding="utf-8")

        # If slug already has a homepage entry, replace it in place
        existing = re.compile(
            r'[ \t]*<article>\s*<span class="title"[^>]*>'
            r'<a href="devlog/' + re.escape(slug) + r'"'
            r'.*?</article>',
            re.DOTALL
        )
        if existing.search(homepage):
            # A function avoids backslashes in the title being read as escapes
            homepage = existing.sub(lambda m: new_article, homepage, count=1)
            index_path.write_text(homepage, encoding="utf-8")
            return

        # New post: insert above the first entry that is the same month or
        # older, so the list stays newest-first whatever date the post has.
        insert_at = None
        last_end = None
        if date_key:
            for m in re.finditer(r'[ \t]*<article>.*?</article>', homepage, re.DOTALL):
                last_end = m.end()
                d = re.search(r'<span class="date">\s*([A-Za-z]+) (\d{4})\s*</span>', m.group(0))
                if d and d.group(1) in MONTHS:
                    if (int(d.group(2)), MONTHS.index(d.group(1))) <= date_key:
                        insert_at = m.start()
                        break

        if insert_at is not None:
            homepage = homepage[:insert_at] + new_article + '\n' + homepage[insert_at:]
        elif date_key and last_end is not None:
            # Older than everything already listed
            homepage = homepage[:last_end] + '\n' + new_article + homepage[last_end:]
        else:
            marker = '<h1 class="sr-only">chriswaite.dev</h1>'
            if marker not in homepage:
                return
            homepage = homepage.replace(marker, marker + '\n' + new_article, 1)

        index_path.write_text(homepage, encoding="utf-8")

    def update_sitemap(self, slug):
        sitemap_path = DOCS_DIR / "sitemap.xml"
        if not sitemap_path.exists():
            return

        xml = sitemap_path.read_text(encoding="utf-8")
        entry_url = f"/devlog/{slug}/"

        if entry_url in xml:
            return

        new_entry = f"  <url><loc>https://chriswaite.dev/devlog/{slug}/</loc></url>"
        lines = xml.split("\n")
        result = []
        inserted = False

        for line in lines:
            if not inserted and "</urlset>" in line:
                result.append(new_entry)
                inserted = True
            elif not inserted and "/devlog/" in line:
                m = re.search(r"/devlog/([^/]+)/", line)
                if m and m.group(1) > slug:
                    result.append(new_entry)
                    inserted = True
            result.append(line)

        sitemap_path.write_text("\n".join(result), encoding="utf-8")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Only log API calls, not static file requests
        msg = str(args[0]) if args else ""
        if "/api/" in msg:
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"Docs directory: {DOCS_DIR}")
    print(f"Blog editor: http://localhost:{PORT}")
    httpd = HTTPServer(("localhost", PORT), EditorHandler)
    httpd.serve_forever()
