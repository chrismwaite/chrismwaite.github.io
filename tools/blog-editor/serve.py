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

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

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

    def do_GET(self):
        path = unquote(self.path)

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
        content_type = self.headers["Content-Type"]
        if "boundary=" not in content_type:
            self.send_json({"error": "Invalid content type"}, 400)
            return

        boundary = content_type.split("boundary=")[1].strip()
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]

        body = self.rfile.read(int(self.headers["Content-Length"]))
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
        body = self.rfile.read(int(self.headers["Content-Length"]))
        data = json.loads(body)
        html = data.get("html", "")

        # Create directory and write file
        post_dir = DOCS_DIR / "devlog" / slug
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "index.html").write_text(html, encoding="utf-8")

        # Update sitemap and homepage
        self.update_sitemap(slug)
        self.update_homepage(slug, html)

        self.send_json({"ok": True, "path": f"devlog/{slug}/index.html"})

    def update_homepage(self, slug, post_html):
        """Add or update the post entry at the top of docs/index.html."""
        MONTHS = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]

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
        else:
            date_display = ""

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
            homepage = existing.sub(new_article, homepage)
            index_path.write_text(homepage, encoding="utf-8")
            return

        # Insert after the <h1> tag for new posts
        marker = '<h1 class="sr-only">chriswaite.dev</h1>'
        if marker not in homepage:
            return

        homepage = homepage.replace(
            marker,
            marker + '\n' + new_article
        )

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
