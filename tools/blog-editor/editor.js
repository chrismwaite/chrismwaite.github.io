(() => {
  const MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  // Lines starting with one of these (opening or closing) are not wrapped in <p>
  const BLOCK_TAGS = /^<(?:!--|\/?(?:p|h[1-6]|ul|ol|li|dl|dt|dd|blockquote|div|pre|table|thead|tbody|tr|td|th|figure|figcaption|section|header|footer|nav|article|aside|form|fieldset|details|summary|iframe|video|audio|script|style|hr|br)\b)/i;

  // DOM refs
  const titleEl = document.getElementById("post-title");
  const dateEl = document.getElementById("post-date");
  const slugEl = document.getElementById("post-slug");
  const descEl = document.getElementById("post-description");
  const descCount = document.getElementById("desc-count");
  const contentEl = document.getElementById("post-content");
  const previewFrame = document.getElementById("preview-frame");
  const loadSelect = document.getElementById("load-select");
  const newBtn = document.getElementById("new-btn");
  const saveBtn = document.getElementById("save-btn");
  const saveStatus = document.getElementById("save-status");
  const uploadBtn = document.getElementById("upload-btn");
  const uploadInput = document.getElementById("upload-input");

  let previewTimer = null;
  let templateStr = "";
  let knownSlugs = new Set();

  // Set today's date as default
  dateEl.value = new Date().toISOString().slice(0, 10);

  // --- Load external template ---
  async function loadTemplate() {
    try {
      const resp = await fetch("template.html");
      templateStr = await resp.text();
    } catch {
      templateStr = "";
      showSaveStatus("Could not load template.html", true);
    }
  }

  // --- Slug generation ---
  function toSlug(text) {
    return text
      .toLowerCase()
      .replace(/['‘’]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  const titleExists = document.getElementById("title-exists");
  const slugExistsEl = document.getElementById("slug-exists");

  function checkSlugExists() {
    const slug = slugEl.value.trim();
    const exists = slug && knownSlugs.has(slug);
    titleEl.classList.toggle("slug-exists", exists);
    slugEl.classList.toggle("slug-exists", exists);
    titleExists.textContent = exists ? "exists" : "";
    slugExistsEl.textContent = exists ? "exists" : "";
  }

  titleEl.addEventListener("input", () => {
    slugEl.value = toSlug(titleEl.value);
    checkSlugExists();
    schedulePreview();
  });

  slugEl.addEventListener("input", () => {
    checkSlugExists();
    schedulePreview();
  });

  // --- Description char count ---
  descEl.addEventListener("input", () => {
    updateDescCount();
    schedulePreview();
  });

  // --- Auto-paragraph on Enter ---
  contentEl.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    const val = contentEl.value;
    const pos = contentEl.selectionStart;

    // Leave code alone: no auto-wrapping inside an open <pre> block
    const before = val.slice(0, pos).toLowerCase();
    if (before.lastIndexOf("<pre") > before.lastIndexOf("</pre>")) return;

    const lineStart = val.lastIndexOf("\n", pos - 1) + 1;
    const lineText = val.slice(lineStart, pos);

    if (lineText.trim() === "" || BLOCK_TAGS.test(lineText.trim())) return;

    e.preventDefault();

    const wrapped = `<p>${lineText}</p>`;
    const head = val.slice(0, lineStart);
    const after = val.slice(pos);

    contentEl.value = head + wrapped + "\n" + after;

    const newPos = head.length + wrapped.length + 1;
    contentEl.selectionStart = newPos;
    contentEl.selectionEnd = newPos;

    schedulePreview();
  });

  contentEl.addEventListener("input", schedulePreview);
  dateEl.addEventListener("input", schedulePreview);

  // --- Live preview ---
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updatePreview, 300);
  }

  function getDateDisplay() {
    const val = dateEl.value;
    if (!val) return "";
    const [y, m] = val.split("-");
    return `${MONTHS[parseInt(m, 10)]} ${y}`;
  }

  function escHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;");
  }

  function getFirstImage(html) {
    const img = new DOMParser().parseFromString(html, "text/html").querySelector("img[src]");
    return img ? img.getAttribute("src") : null;
  }

  // JSON string literal that is also safe inside a <script> block
  function jsonStr(str) {
    return JSON.stringify(str).replace(/</g, "\\u003c");
  }

  function buildPostHtml(opts = {}) {
    if (!templateStr) return "<html><body><p>Template not loaded</p></body></html>";

    const title = titleEl.value || "Untitled";
    const desc = descEl.value || "";
    const content = contentEl.value || "";
    const firstImage = getFirstImage(content);
    const hasCode = /<pre[\s>]/i.test(content);

    // Saved posts use relative paths; the preview is served from the project root
    const stylesPath = opts.forSave ? "../../styles" : "/docs/styles";
    const scriptsPath = opts.forSave ? "../../scripts" : "/docs/scripts";

    const values = {
      TITLE: escHtml(title),
      TITLE_JSON: jsonStr(title),
      SLUG: slugEl.value || toSlug(title),
      DESCRIPTION: escHtml(desc),
      DESCRIPTION_JSON: jsonStr(desc),
      DATE_ISO: dateEl.value || new Date().toISOString().slice(0, 10),
      DATE_DISPLAY: getDateDisplay(),
      CONTENT: content,
      OG_IMAGE_META: firstImage
        ? `        <meta property="og:image" content="${escHtml(firstImage)}" />\n`
        : "",
      TW_IMAGE_META: firstImage
        ? `        <meta name="twitter:image" content="${escHtml(firstImage)}" />\n`
        : "",
      JSON_IMAGE: firstImage ? `,\n  "image": ${jsonStr(firstImage)}` : "",
      STYLES_PATH: stylesPath,
      PRISM_CSS: hasCode
        ? `        <link href="${stylesPath}/prism.css" rel="stylesheet" />\n`
        : "",
      PRISM_JS: hasCode
        ? `        <script src="${scriptsPath}/prism.js"></script>\n`
        : ""
    };

    // Single pass with a function, so "$" sequences and "{{...}}" in the
    // post content are inserted literally rather than being reinterpreted.
    return templateStr.replace(/\{\{([A-Z_]+)\}\}/g, (match, key) =>
      key in values ? values[key] : match
    );
  }

  function updatePreview() {
    const html = buildPostHtml({ forSave: false });
    previewFrame.srcdoc = html;
  }

  // --- New post ---
  function updateDescCount() {
    const len = descEl.value.length;
    descCount.textContent = `${len}/155`;
    descCount.style.color = len > 155 ? "#f44336" : "#aaa";
  }

  function resetForm() {
    titleEl.value = "";
    slugEl.value = "";
    descEl.value = "";
    contentEl.value = "";
    dateEl.value = new Date().toISOString().slice(0, 10);
    updateDescCount();
    checkSlugExists();
  }

  newBtn.addEventListener("click", () => {
    resetForm();
    loadSelect.value = "";
    updatePreview();
  });

  // --- Load existing post ---
  async function populatePostList() {
    try {
      const resp = await fetch("/api/posts");
      const slugs = await resp.json();
      knownSlugs = new Set(slugs);
      loadSelect.innerHTML = '<option value="">Load post...</option>';
      for (const slug of slugs) {
        const opt = document.createElement("option");
        opt.value = slug;
        opt.textContent = slug;
        loadSelect.appendChild(opt);
      }
    } catch {}
  }

  loadSelect.addEventListener("change", async () => {
    const slug = loadSelect.value;
    if (!slug) return;

    showSaveStatus("Loading...");
    try {
      const resp = await fetch(`/api/posts/${encodeURIComponent(slug)}`);
      if (!resp.ok) {
        showSaveStatus(`Post not found: ${slug}`, true);
        return;
      }
      const data = await resp.json();
      parsePostIntoEditor(data.html, data.slug);
      showSaveStatus("Post loaded");
    } catch (err) {
      showSaveStatus(`Load error: ${err.message}`, true);
    }
    loadSelect.value = "";
  });

  function parsePostIntoEditor(html, slug) {
    const doc = new DOMParser().parseFromString(html, "text/html");

    // Start clean so nothing carries over from the previously open post
    resetForm();

    const h1 = doc.querySelector(".post-header .title");
    if (h1) titleEl.value = h1.textContent.trim();

    const metaDesc = doc.querySelector('meta[name="description"]');
    if (metaDesc) descEl.value = metaDesc.getAttribute("content") || "";

    if (slug) {
      slugEl.value = slug;
    } else {
      const canonical = doc.querySelector('link[rel="canonical"]');
      if (canonical) {
        const match = (canonical.getAttribute("href") || "").match(/\/devlog\/([^/]+)\//);
        if (match) slugEl.value = match[1];
      }
    }

    const ldScript = doc.querySelector('script[type="application/ld+json"]');
    if (ldScript) {
      try {
        const ld = JSON.parse(ldScript.textContent);
        if (ld.datePublished) dateEl.value = String(ld.datePublished).slice(0, 10);
      } catch {}
    }

    const article = doc.querySelector("article.post");
    if (article) contentEl.value = article.innerHTML.trim();

    updateDescCount();
    checkSlugExists();
    updatePreview();
  }

  // --- Save post ---
  saveBtn.addEventListener("click", async () => {
    const title = titleEl.value.trim();
    const slug = slugEl.value.trim() || toSlug(title);

    if (!title) { showSaveStatus("Title is required", true); return; }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
      showSaveStatus("Slug must be lowercase letters, numbers and hyphens", true);
      return;
    }
    if (!dateEl.value) { showSaveStatus("Date is required", true); return; }

    saveBtn.disabled = true;
    showSaveStatus("Saving...");

    try {
      const html = buildPostHtml({ forSave: true });
      const resp = await fetch(`/api/posts/${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ html })
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `Server error: ${resp.status}`);
      }

      const data = await resp.json();
      knownSlugs.add(slug);
      checkSlugExists();
      showSaveStatus(`Saved to ${data.path}`);
    } catch (err) {
      showSaveStatus(`Error: ${err.message}`, true);
    } finally {
      saveBtn.disabled = false;
    }
  });

  function showSaveStatus(msg, isError = false) {
    saveStatus.textContent = msg;
    saveStatus.className = isError ? "save-status error" : "save-status";
    if (!isError && msg !== "Saving..." && msg !== "Loading...") {
      setTimeout(() => { saveStatus.textContent = ""; }, 5000);
    }
  }

  // --- Image upload ---
  uploadBtn.addEventListener("click", () => uploadInput.click());

  uploadInput.addEventListener("change", async () => {
    const file = uploadInput.files[0];
    if (!file) return;
    uploadInput.value = "";

    uploadBtn.disabled = true;
    showSaveStatus("Uploading image...");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const resp = await fetch("/api/upload", { method: "POST", body: formData });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: `Server error: ${resp.status}` }));
        throw new Error(err.error || `Server error: ${resp.status}`);
      }

      const data = await resp.json();
      const imgTag = `<img decoding="async" loading="lazy" src="${escHtml(data.url)}" alt="" class="aligncenter" />`;

      const pos = contentEl.selectionStart;
      const val = contentEl.value;
      contentEl.value = val.slice(0, pos) + imgTag + val.slice(pos);
      contentEl.selectionStart = contentEl.selectionEnd = pos + imgTag.length;
      contentEl.focus();

      showSaveStatus("Image uploaded");
      schedulePreview();
    } catch (err) {
      showSaveStatus(`Upload error: ${err.message}`, true);
    } finally {
      uploadBtn.disabled = false;
    }
  });

  // --- Init ---
  async function init() {
    await loadTemplate();
    populatePostList();
    updatePreview();
  }

  init();
})();
