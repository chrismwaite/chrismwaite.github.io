(() => {
  const MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  const BLOCK_TAGS = /^<(?:p|h[1-6]|ul|ol|li|blockquote|div|pre|table|figure|section|header|footer|nav|article|aside|form|fieldset|details|summary|hr|br)/i;

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
      .replace(/['']/g, "")
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
    const len = descEl.value.length;
    descCount.textContent = `${len}/155`;
    descCount.style.color = len > 155 ? "#f44336" : "#aaa";
    schedulePreview();
  });

  // --- Auto-paragraph on Enter ---
  contentEl.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    const val = contentEl.value;
    const pos = contentEl.selectionStart;

    const lineStart = val.lastIndexOf("\n", pos - 1) + 1;
    const lineText = val.slice(lineStart, pos);

    if (lineText.trim() === "" || BLOCK_TAGS.test(lineText.trim())) return;

    e.preventDefault();

    const wrapped = `<p>${lineText}</p>`;
    const before = val.slice(0, lineStart);
    const after = val.slice(pos);

    contentEl.value = before + wrapped + "\n" + after;

    const newPos = before.length + wrapped.length + 1;
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
    const m = html.match(/<img[^>]+src="([^"]+)"/);
    return m ? m[1] : null;
  }

  function buildPostHtml(opts = {}) {
    if (!templateStr) return "<html><body><p>Template not loaded</p></body></html>";

    const title = titleEl.value || "Untitled";
    const slug = slugEl.value || toSlug(title);
    const desc = descEl.value || "";
    const dateIso = dateEl.value || new Date().toISOString().slice(0, 10);
    const dateDisplay = getDateDisplay();
    const content = contentEl.value || "";
    const firstImage = getFirstImage(content);

    const titleEsc = escHtml(title);
    const descEsc = escHtml(desc);

    const cssPath = opts.forSave ? "../../styles/global.css" : "/docs/styles/global.css";

    const ogImageMeta = firstImage
      ? `        <meta property="og:image" content="${firstImage}" />\n`
      : "";
    const twImageMeta = firstImage
      ? `        <meta name="twitter:image" content="${firstImage}" />\n`
      : "";
    const jsonImage = firstImage
      ? `,\n  "image": "${firstImage}"`
      : "";

    return templateStr
      .replace(/\{\{TITLE\}\}/g, titleEsc)
      .replace(/\{\{SLUG\}\}/g, slug)
      .replace(/\{\{DESCRIPTION\}\}/g, descEsc)
      .replace(/\{\{DATE_ISO\}\}/g, dateIso)
      .replace(/\{\{DATE_DISPLAY\}\}/g, dateDisplay)
      .replace(/\{\{CONTENT\}\}/g, content)
      .replace(/\{\{OG_IMAGE_META\}\}/g, ogImageMeta)
      .replace(/\{\{TW_IMAGE_META\}\}/g, twImageMeta)
      .replace(/\{\{JSON_IMAGE\}\}/g, jsonImage)
      .replace(/\{\{CSS_PATH\}\}/g, cssPath);
  }

  function updatePreview() {
    const html = buildPostHtml({ forSave: false });
    previewFrame.srcdoc = html;
  }

  // --- New post ---
  newBtn.addEventListener("click", () => {
    titleEl.value = "";
    slugEl.value = "";
    descEl.value = "";
    contentEl.value = "";
    dateEl.value = new Date().toISOString().slice(0, 10);
    descCount.textContent = "0/155";
    descCount.style.color = "#aaa";
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
        if (ld.datePublished) dateEl.value = ld.datePublished;
      } catch {}
    }

    const article = doc.querySelector("article.post");
    if (article) contentEl.value = article.innerHTML.trim();

    const len = descEl.value.length;
    descCount.textContent = `${len}/155`;
    descCount.style.color = len > 155 ? "#f44336" : "#aaa";

    updatePreview();
  }

  // --- Save post ---
  saveBtn.addEventListener("click", async () => {
    const title = titleEl.value.trim();
    const slug = slugEl.value.trim() || toSlug(title);

    if (!title) { showSaveStatus("Title is required", true); return; }
    if (!slug) { showSaveStatus("Could not generate slug", true); return; }
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

      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);

      const data = await resp.json();
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
      const imgTag = `<img decoding="async" loading="lazy" src="${data.url}" alt="" class="aligncenter" />`;

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
