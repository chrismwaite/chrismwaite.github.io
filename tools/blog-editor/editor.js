(() => {
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

  const seriesEl = document.getElementById("post-series");

  let previewTimer = null;
  let previewRequest = 0;
  let knownSlugs = new Set();

  // Set today's date as default
  dateEl.value = new Date().toISOString().slice(0, 10);

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
  seriesEl.addEventListener("change", schedulePreview);

  // --- Live preview ---
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updatePreview, 300);
  }

  function escHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;");
  }

  // The fields the server needs to render or save a post
  function getFields() {
    const title = titleEl.value.trim();
    return {
      title: title || "Untitled",
      slug: slugEl.value.trim() || toSlug(title),
      description: descEl.value.trim(),
      date: dateEl.value || new Date().toISOString().slice(0, 10),
      series: seriesEl.value,
      content: contentEl.value
    };
  }

  // The server renders the preview with the same template used for saving
  async function updatePreview() {
    const request = ++previewRequest;
    try {
      const resp = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getFields())
      });
      const data = await resp.json();
      if (request !== previewRequest) return; // a newer preview is on its way
      if (!resp.ok) throw new Error(data.error || `Server error: ${resp.status}`);
      previewFrame.srcdoc = data.html;
    } catch (err) {
      showSaveStatus(`Preview error: ${err.message}`, true);
    }
  }

  // --- New post ---
  function updateDescCount() {
    const len = descEl.value.length;
    descCount.textContent = `${len}/155`;
    descCount.classList.toggle("over", len > 155);
  }

  function resetForm() {
    titleEl.value = "";
    slugEl.value = "";
    descEl.value = "";
    contentEl.value = "";
    dateEl.value = new Date().toISOString().slice(0, 10);
    seriesEl.value = "";
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
      const post = await resp.json();
      resetForm();
      titleEl.value = post.title;
      slugEl.value = post.slug;
      descEl.value = post.description;
      dateEl.value = post.date;
      seriesEl.value = post.series || "";
      contentEl.value = post.content;
      updateDescCount();
      checkSlugExists();
      updatePreview();
      showSaveStatus("Post loaded");
    } catch (err) {
      showSaveStatus(`Load error: ${err.message}`, true);
    }
    loadSelect.value = "";
  });

  async function populateSeriesList() {
    try {
      const resp = await fetch("/api/series");
      for (const s of await resp.json()) {
        const opt = document.createElement("option");
        opt.value = s.slug;
        opt.textContent = s.title;
        seriesEl.appendChild(opt);
      }
    } catch {}
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
      const resp = await fetch(`/api/posts/${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getFields())
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
    await Promise.all([populatePostList(), populateSeriesList()]);
    updatePreview();
  }

  init();
})();
