#!/usr/bin/env python3
"""Blog editor server. Serves the editor UI and provides API endpoints for post management.

Usage: python3 serve.py [port]
Default port: 8010
"""

import hashlib
import importlib
import json
import re
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_site  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
ALLOWED_ORIGINS = {f"http://{host}" for host in ALLOWED_HOSTS}

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
        elif path == "/api/series":
            series = build_site.load_series()
            self.send_json([{"slug": s["slug"], "title": s["title"]} for s in series])
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
        elif path == "/api/preview":
            self.preview_post()
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
        """Return the editable fields of a post."""
        if not self.valid_slug(slug):
            return
        filepath = DOCS_DIR / "devlog" / slug / "index.html"
        if not filepath.exists():
            self.send_json({"error": f"Post not found: {slug}"}, 404)
            return
        post = build_site.parse_post(filepath.read_text(encoding="utf-8"), slug)
        in_series = build_site.series_for(slug, build_site.load_series())
        post["series"] = in_series["slug"] if in_series else ""
        self.send_json(post)

    def read_fields(self):
        """Read and validate the post fields sent by the editor."""
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.send_json({"error": "Expected application/json"}, 415)
            return None
        body = self.read_body()
        if body is None:
            return None
        try:
            data = json.loads(body)
            fields = {
                key: str(data.get(key, "")).strip()
                for key in ("slug", "title", "description", "date", "series")
            }
            fields["content"] = str(data.get("content", "")).strip("\n")
        except (ValueError, AttributeError):
            self.send_json({"error": "Invalid JSON"}, 400)
            return None
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", fields["date"]):
            self.send_json({"error": "Date must be YYYY-MM-DD"}, 400)
            return None
        return fields

    def preview_post(self):
        fields = self.read_fields()
        if fields is None:
            return
        fields["slug"] = fields["slug"] or "preview"
        posts = build_site.load_posts(DOCS_DIR)
        series = build_site.load_series(posts)
        # Asset paths are prefixed because the editor serves the project root
        self.send_json({"html": build_site.render_post(fields, posts, series, root="/docs")})

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
        fields = self.read_fields()
        if fields is None:
            return
        if not fields["title"]:
            self.send_json({"error": "Title is required"}, 400)
            return
        fields["slug"] = slug

        # Pick up any changes made to the generator since the editor was started
        importlib.reload(build_site)
        build_site.write_post(fields, DOCS_DIR)
        build_site.set_series(slug, fields["series"])
        # Regenerates the homepage, series pages, sitemap, feed and llms.txt,
        # and the newer/older links on neighbouring posts
        build_site.build_all(DOCS_DIR)

        self.send_json({"ok": True, "path": f"devlog/{slug}/index.html"})

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
