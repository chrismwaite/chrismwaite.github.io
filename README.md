# chriswaite.dev

A static site served by GitHub Pages from `docs/`. There is no build step on GitHub: what is committed is what is published.

- `docs/` is the site. `docs/devlog/<slug>/index.html` is one post.
- `tools/` is the generator, the writing tool and a link checker. None of it is published.

## Writing a post

```
tools/blog-editor/start.sh
```

Open http://localhost:8010. Fill in the title, date, description and content (HTML), and pick a series if it belongs to one. The right-hand side shows the real page as you type. **Upload Image** sends a picture to Cloudinary and inserts the tag (needs the `CLOUDINARY_*` keys in `tools/blog-editor/.env`).

**Save Post** writes the post and rebuilds everything that depends on it. Then commit and push to publish.

To edit an old post, choose it from **Load post**.

## What a save rebuilds

Saving runs `tools/build_site.py`, which you can also run by hand:

```
python3 tools/build_site.py
```

It reads every post and regenerates:

- **Homepage** (`docs/index.html`): one card per post, newest first. The card uses the post's title, description and first image.
- **Series pages** (`docs/series/<slug>/`).
- **Feed** (`docs/feed.xml`): the newest 30 posts.
- **`sitemap.xml` and `llms.txt`**.
- **Every post**, so the series list and older/newer links stay right.

None of these are edited by hand; changes would be overwritten.

## Series

Series live in `tools/series.json`. Each has a `slug`, `title`, optional `description` and an ordered list of post slugs.

- Add a post to an existing series with the Series box in the editor.
- To start a new series or reorder one, edit `series.json` and run the build.

On the homepage a series appears as one row, placed at the date of its newest post.

## Templates and styling

- `tools/templates/post.html` is the layout of a post, `page.html` of the homepage and series pages. `{{NAME}}` slots are filled by `build_site.py`.
- A post's content is whatever sits between `<!-- post:content -->` and `<!-- /post:content -->` in its file. Everything around it is replaced from the template on each build, so change the template, not the posts.
- About, experiments and 404 are hand-written in `docs/`. Only their nav is kept in step by the build.
- All styling is in `docs/styles/global.css`. The colours are the variables at the top.

## Checking

```
python3 tools/check_site.py                  # broken internal links, missing pages
cd docs && python3 -m http.server 8009       # view the site locally
```
