const state = { offset: 0, loading: false, hasMore: true, total: 0, batch: 75, thumbnailSize: 280, tab: location.pathname.startsWith("/viewer/") ? "viewer" : "preview", viewerPostId: null, viewerFilenameFilter: false, viewerHistory: [], viewerHistoryIndex: -1, viewerHistoryLimit: 12, nextAfterStatusChange: true, fetchPresets: new Map(), fetchPresetPayload: {} };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));

async function api(url, options = {}) {
  const response = await fetch(url, { headers: {"Content-Type":"application/json", ...(options.headers || {})}, ...options });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.add("hidden"), 3200);
}

function queryState() {
  return {
    status: $("#preview-status").value,
    search: $("#preview-search").value.trim(),
    sort: $("#preview-sort").value,
  };
}

function queryString(extra = {}) {
  return new URLSearchParams({...queryState(), ...extra}).toString();
}

function signedScore(value) {
  const score = Number(value || 0);
  return `${score >= 0 ? "+" : ""}${score.toFixed(1)}`;
}

function applyPreviewThumbnailSize(size) {
  state.thumbnailSize = Math.max(120, Math.min(600, Number(size) || 280));
  document.documentElement.style.setProperty("--preview-thumbnail-size", `${state.thumbnailSize}px`);
  $("#preview-thumbnail-size").value = state.thumbnailSize;
}

async function savePreviewSettings() {
  state.batch = Math.max(50, Math.min(200, Number($("#preview-batch").value) || 75));
  applyPreviewThumbnailSize($("#preview-thumbnail-size").value);
  const saved = await api("/api/preview/settings", {
    method: "PUT",
    body: JSON.stringify({batch_size: state.batch, thumbnail_size: state.thumbnailSize}),
  });
  state.batch = saved.batch_size;
  $("#preview-batch").value = saved.batch_size;
  applyPreviewThumbnailSize(saved.thumbnail_size);
}

function resetViewerHistory() {
  state.viewerHistory = [];
  state.viewerHistoryIndex = -1;
}

function recordViewerHistory(postId, mode) {
  const id = Number(postId);
  if (mode === "back" && state.viewerHistory[state.viewerHistoryIndex - 1] === id) {
    state.viewerHistoryIndex -= 1;
    return;
  }
  if (mode === "forward" && state.viewerHistory[state.viewerHistoryIndex + 1] === id) {
    state.viewerHistoryIndex += 1;
    return;
  }
  if (mode === "select") {
    const existingIndex = state.viewerHistory.lastIndexOf(id);
    if (existingIndex >= 0) {
      state.viewerHistoryIndex = existingIndex;
      return;
    }
  }
  if (state.viewerHistory[state.viewerHistoryIndex] === id) return;
  state.viewerHistory = state.viewerHistory.slice(0, state.viewerHistoryIndex + 1);
  state.viewerHistory.push(id);
  if (state.viewerHistory.length > state.viewerHistoryLimit) {
    state.viewerHistory.splice(0, state.viewerHistory.length - state.viewerHistoryLimit);
  }
  state.viewerHistoryIndex = state.viewerHistory.length - 1;
}

function viewerStripItems(data) {
  const historyStart = Math.max(0, state.viewerHistoryIndex - 3);
  const historyEnd = Math.min(state.viewerHistory.length, state.viewerHistoryIndex + 4);
  const historyIds = state.viewerHistory.slice(historyStart, historyEnd);
  const itemsById = new Map(data.preview_strip.map(item => [Number(item.id), item]));
  const ids = [...historyIds, ...data.preview_strip.map(item => Number(item.id))]
    .filter((id, index, all) => all.indexOf(id) === index);
  return ids.map(id => itemsById.get(id) || {
    id,
    active: id === Number(data.id),
    thumbnail_url: `/api/media/${id}/thumbnail`,
  });
}

function showTab(tab) {
  if (location.pathname.startsWith("/viewer/")) history.pushState({}, "", "/");
  state.tab = tab;
  if (tab === "preview") resetViewerHistory();
  $("#viewer").classList.add("hidden");
  $("#tabs").classList.remove("hidden");
  $$(".view").forEach(node => node.classList.toggle("hidden", node.id !== `view-${tab}`));
  $$("#tabs button").forEach(button => button.classList.toggle("active", button.dataset.tab === tab));
  if (tab === "preview" && !$("#post-grid").children.length) resetPreview();
  if (tab === "fetch") loadFetchPresets();
  if (tab === "tags") loadTags();
  if (tab === "categories") loadCategories();
  if (tab === "config") loadConfig();
  if (tab === "maintenance") loadMaintenance();
}

async function bootstrap() {
  const data = await api("/api/bootstrap");
  $("#version").textContent = `v${data.version}`;
  applySchedule(data.scheduler);
  renderFetch(data.fetch);
  state.nextAfterStatusChange = data.viewer?.next_after_status_change !== false;
  state.batch = data.preview?.batch_size || 75;
  $("#preview-batch").value = state.batch;
  applyPreviewThumbnailSize(data.preview?.thumbnail_size || 280);
}

async function resetPreview() {
  resetViewerHistory();
  state.offset = 0;
  state.total = 0;
  state.hasMore = true;
  state.batch = Math.max(50, Math.min(200, Number($("#preview-batch").value) || 75));
  $("#post-grid").replaceChildren();
  $("#preview-score-summary").textContent = "Preselection: calculating...";
  await loadMorePosts();
}

function card(post) {
  const params = queryString();
  const node = document.createElement("article");
  node.className = "post-card";
  const preselection = Number(post.recommendation_score || 0);
  const recommendationDetails = [post.recommendation_positive, post.recommendation_negative].filter(Boolean).join(" | ");
  node.innerHTML = `<a href="/viewer/${post.id}?${params}" data-viewer="${post.id}">
    <img class="post-image" src="${post.thumbnail_url}" loading="lazy" decoding="async" alt="Post ${post.id}">
    <div class="post-meta">
      <div class="post-title"><span>#${post.id}</span><span class="status">${esc(post.status)}</span></div>
      <div class="post-stats"><span>Score ${post.score ?? 0}</span><span>Fav ${post.fav_count ?? 0}</span><span>${post.stars == null ? "Unrated" : `${post.stars}/10`}</span></div>
      <div class="post-preselection ${preselection < 0 ? "negative" : ""}" title="${esc(recommendationDetails || "No contributing tag scores")}"><strong>Preselection ${signedScore(preselection)}</strong><span>${post.llm_score == null ? "LLM -" : `LLM ${signedScore(post.llm_score)}`}</span></div>
      <div class="post-category" title="${esc(post.category_source === "automatic" ? "Automatically selected from category rules" : "Stored category assignment")}">${esc(post.category || "_unmatched")}${post.category_source === "automatic" ? " (suggested)" : ""} | ${post.image_width || 0} x ${post.image_height || 0}</div>
      <div class="post-tags">${esc(post.tags || "No tags")}</div>
    </div></a>`;
  return node;
}

async function loadMorePosts() {
  if (state.loading || !state.hasMore || state.tab !== "preview") return;
  state.loading = true;
  $("#preview-sentinel").textContent = "Loading...";
  try {
    const data = await api(`/api/posts?${queryString({offset: state.offset, limit: state.batch})}`);
    const fragment = document.createDocumentFragment();
    data.items.forEach(post => fragment.append(card(post)));
    $("#post-grid").append(fragment);
    state.offset += data.items.length;
    state.total = data.total;
    state.hasMore = data.has_more;
    $("#preview-count").textContent = `${state.offset} / ${state.total}`;
    if (data.preselection_summary) {
      const summary = data.preselection_summary;
      $("#preview-score-summary").textContent = `Preselection: Best ${signedScore(summary.best)} | Worst ${signedScore(summary.worst)} | Average ${signedScore(summary.average)}`;
    }
    $("#preview-sentinel").textContent = state.hasMore ? "Scroll to load more" : "End of results";
  } catch (error) { toast(error.message); }
  finally { state.loading = false; }
}

function viewerUrl(id) { return `/viewer/${id}?${queryString()}`; }

function viewerTagGroup(title, type, items, detailed = false) {
  const rows = items.length ? items.map(item => {
    const score = item.scoring_excluded ? "off" : Number(item.score || 0).toFixed(1);
    const average = item.scoring_excluded ? "off" : item.average_rating == null ? "-" : Number(item.average_rating).toFixed(1);
    const flags = [item.filename_excluded ? "name" : "", item.fetch_excluded ? "fetch" : "", item.ignore_category_influence ? "cat" : "", item.ignore_recommendation_score ? "pre" : "", item.ignore_llm_input ? "llm" : ""].filter(Boolean).join(", ");
    return `<div class="viewer-tag-row ${item.filename_excluded ? "filename-excluded" : ""}" data-tag-row data-tag="${esc(item.tag)}" data-manual-score="${item.manual_score ?? ""}" data-scoring-excluded="${Boolean(item.scoring_excluded)}" data-filename-excluded="${Boolean(item.filename_excluded)}" data-fetch-excluded="${Boolean(item.fetch_excluded)}" data-ignore-category="${Boolean(item.ignore_category_influence)}" data-ignore-recommendation="${Boolean(item.ignore_recommendation_score)}" data-ignore-llm="${Boolean(item.ignore_llm_input)}" title="Right-click for tag actions">
      <span class="viewer-tag-name">${esc(item.tag)}</span>
      ${detailed ? `<span class="viewer-tag-score">${score}</span><span class="viewer-tag-average">${average}</span><span class="viewer-tag-flags">${esc(flags || "-")}</span>` : ""}
    </div>`;
  }).join("") : `<div class="viewer-tag-empty">No tags</div>`;
  return `<section class="viewer-tag-group tag-${type}"><header><strong>${title}</strong>${detailed ? "<span>Score</span><span>Avg</span><span>Flags</span>" : ""}</header><div class="viewer-tag-rows">${rows}</div></section>`;
}

function viewerStatusButton(value, label, current, title = "") {
  return `<button type="button" class="viewer-status-button status-${value} ${value === current ? "active" : ""}" data-viewer-status="${value}"${title ? ` title="${esc(title)}"` : ""}>${label}</button>`;
}

function ratingLabel(value) {
  return ({g: "general", s: "sensitive", q: "questionable", e: "explicit"})[value] || value || "-";
}

function booleanData(element, name) {
  return element.dataset[name] === "true" || element.dataset[name] === "1";
}

function tagContextMetadata(element) {
  const manual = element.dataset.manualScore;
  return {
    tag: element.dataset.tag,
    manual_score: manual === "" || manual == null ? null : Number(manual),
    scoring_excluded: booleanData(element, "scoringExcluded"),
    filename_excluded: booleanData(element, "filenameExcluded"),
    fetch_excluded: booleanData(element, "fetchExcluded"),
    ignore_category_influence: booleanData(element, "ignoreCategory"),
    ignore_recommendation_score: booleanData(element, "ignoreRecommendation"),
    ignore_llm_input: booleanData(element, "ignoreLlm"),
  };
}

function contextAction(action, label, danger = false) {
  return `<button type="button" role="menuitem" data-tag-action="${action}" class="${danger ? "danger-text" : ""}">${label}</button>`;
}

function openTagContextMenu(event, element) {
  event.preventDefault();
  const menu = $("#tag-context-menu");
  const meta = tagContextMetadata(element);
  menu.context = {meta, source: element.closest("#viewer") ? "viewer" : "tags"};
  menu.innerHTML = `<div class="context-title">${esc(meta.tag)}</div>
    ${contextAction("filename", meta.filename_excluded ? "Remove filename exclude" : "Exclude from filename")}
    ${contextAction("fetch", meta.fetch_excluded ? "Remove fetch exclude" : "Exclude from fetch")}
    <div class="context-separator"></div>
    <div class="context-heading">Scoring / usage</div>
    ${contextAction("manual", meta.manual_score == null ? "Set manual score..." : `Edit manual score (${meta.manual_score})...`)}
    ${meta.manual_score == null ? "" : contextAction("manual-clear", "Clear manual score")}
    ${contextAction("scoring", meta.scoring_excluded ? "Enable legacy scoring" : "Exclude from legacy scoring")}
    ${contextAction("category", meta.ignore_category_influence ? "Use category hint again" : "Ignore category hint")}
    ${contextAction("recommendation", meta.ignore_recommendation_score ? "Use preselection again" : "Ignore preselection")}
    ${contextAction("llm", meta.ignore_llm_input ? "Use LLM input again" : "Ignore LLM input")}
    ${contextAction("all-ignore", "Ignore for all automatic scores")}
    ${contextAction("all-use", "Use for all automatic scores again")}
    <div class="context-separator"></div>
    ${contextAction("copy", "Copy tag")}
    ${contextAction("search", "Search tag in Preview")}`;
  menu.classList.remove("hidden");
  const width = 270;
  const height = Math.min(menu.scrollHeight, window.innerHeight - 12);
  menu.style.left = `${Math.max(6, Math.min(event.clientX, window.innerWidth - width - 6))}px`;
  menu.style.top = `${Math.max(6, Math.min(event.clientY, window.innerHeight - height - 6))}px`;
}

async function runTagContextAction(action) {
  const menu = $("#tag-context-menu");
  const {meta, source} = menu.context || {};
  if (!meta) return;
  let payload = null;
  if (action === "filename") payload = {filename_excluded: !meta.filename_excluded};
  if (action === "fetch") payload = {fetch_excluded: !meta.fetch_excluded};
  if (action === "scoring") payload = {scoring_excluded: !meta.scoring_excluded};
  if (action === "category") payload = {ignore_category_influence: !meta.ignore_category_influence};
  if (action === "recommendation") payload = {ignore_recommendation_score: !meta.ignore_recommendation_score};
  if (action === "llm") payload = {ignore_llm_input: !meta.ignore_llm_input};
  if (action === "all-ignore") payload = {ignore_category_influence: true, ignore_recommendation_score: true, ignore_llm_input: true};
  if (action === "all-use") payload = {ignore_category_influence: false, ignore_recommendation_score: false, ignore_llm_input: false};
  if (action === "manual-clear") payload = {manual_score: null};
  if (action === "manual") {
    const entered = prompt(`Manual score for '${meta.tag}' (-10 to +10):`, meta.manual_score ?? 0);
    if (entered == null) return;
    const score = Number(entered);
    if (!Number.isFinite(score) || score < -10 || score > 10) throw new Error("Manual score must be between -10 and 10");
    payload = {manual_score: score};
  }
  if (action === "copy") {
    await navigator.clipboard.writeText(meta.tag);
    toast("Tag copied");
    return;
  }
  if (action === "search") {
    showTab("preview");
    $("#preview-search").value = meta.tag;
    await resetPreview();
    return;
  }
  if (!payload) return;
  await api(`/api/tags/${encodeURIComponent(meta.tag)}`, {method: "PATCH", body: JSON.stringify(payload)});
  toast("Tag settings saved");
  if (source === "viewer" && state.viewerPostId != null) await openViewer(state.viewerPostId, false);
  else await loadTags();
}

async function openViewer(postId, push = true, historyMode = "append") {
  try {
    state.tab = "viewer";
    const params = new URLSearchParams(location.search);
    const filters = {
      status: params.get("status") || queryState().status,
      search: params.get("search") || queryState().search,
      sort: params.get("sort") || queryState().sort,
    };
    $("#preview-status").value = filters.status;
    $("#preview-search").value = filters.search;
    $("#preview-sort").value = filters.sort;
    const data = await api(`/api/posts/${postId}?${new URLSearchParams(filters)}`);
    state.viewerPostId = Number(postId);
    recordViewerHistory(postId, historyMode);
    if (push) history.pushState({viewer: postId}, "", viewerUrl(postId));
    $("#tabs").classList.add("hidden");
    $$(".view").forEach(node => node.classList.add("hidden"));
    const viewer = $("#viewer");
    viewer.classList.remove("hidden");
    const nav = data.navigation;
    const tags = data.typed_tags;
    const stripItems = viewerStripItems(data);
    const activeStripIndex = stripItems.findIndex(item => Number(item.id) === Number(data.id));
    const strip = stripItems.map((item, index) => `<button class="viewer-strip-tile ${Number(item.id) === Number(data.id) ? "active" : ""}" data-strip-post="${item.id}" title="Open post ${item.id}">
      <span>${index < activeStripIndex ? "Previous" : index === activeStripIndex ? "Current" : "Next"}</span>
      <img src="${item.thumbnail_url}" loading="eager" decoding="async" alt="Post ${item.id}">
      <strong>#${item.id}</strong>
    </button>`).join("");
    const historyPreviousId = state.viewerHistoryIndex > 0 ? state.viewerHistory[state.viewerHistoryIndex - 1] : null;
    const historyNextId = state.viewerHistoryIndex < state.viewerHistory.length - 1 ? state.viewerHistory[state.viewerHistoryIndex + 1] : null;
    const previousId = historyPreviousId ?? nav.previous_id;
    const nextId = historyNextId ?? nav.next_id;
    const positionText = nav.index >= 0
      ? `Position ${nav.index + 1} / ${nav.total}`
      : `Recent review ${state.viewerHistoryIndex + 1} / ${state.viewerHistory.length}`;
    const rating = Math.max(0, Math.min(10, Math.round(Number(data.stars || 0))));
    viewer.innerHTML = `<div class="viewer-toolbar">
      <button class="icon-button" id="viewer-back" title="Back to preview" aria-label="Back">&#8592;</button>
      <label class="viewer-fit"><input id="viewer-fit" type="checkbox" checked> Fit</label>
      <a class="button-link" id="viewer-original" href="${esc(data.original_post_url)}" target="_blank" rel="noreferrer" title="Open original post (O)">Original Post</a>
      <button type="button" id="viewer-copy-link">Copy Link</button>
      <button type="button" class="primary" id="viewer-save" title="Save final file (F)">Save</button>
      <span class="viewer-toolbar-spacer"></span>
      <strong>Post #${data.id}</strong>
    </div>
    <div class="viewer-info">ID ${data.id} - ${esc(ratingLabel(data.rating))} - Score: ${data.score ?? 0} | Preselection: ${signedScore(data.recommendation_score)} | LLM: ${data.llm_score == null ? "-" : signedScore(data.llm_score)} | Favorites: ${data.fav_count ?? 0} | Parent: ${data.parent_id ?? "-"} | Parent/Child known: ${(data.known_parent_loaded || 0) + (data.known_child_count || 0)} | locally saved: ${data.final_file_path ? 1 : 0}</div>
    <div class="viewer-layout">
      <div class="viewer-content">
        <div class="viewer-stage" id="viewer-stage"><img id="viewer-image" src="${data.image_url}" alt="Post ${data.id}"></div>
        <div class="viewer-strip" aria-label="Nearby posts">${strip}</div>
        <div class="viewer-controls">
          <div class="viewer-rating"><span id="viewer-rating-label">Personal Rating: ${rating}/10</span><div class="viewer-stars">${Array.from({length: 10}, (_, i) => `<button type="button" data-rating="${i + 1}" class="${i < rating ? "active" : ""}" title="Rate ${i + 1} of 10">&#9733;</button>`).join("")}</div></div>
          <button class="viewer-nav-button" id="viewer-prev" ${previousId == null ? "disabled" : ""}>&#8249; Previous</button>
          <strong class="viewer-position">${positionText}</strong>
          <button class="viewer-nav-button" id="viewer-next" ${nextId == null ? "disabled" : ""}>Next &#8250;</button>
          <label class="viewer-category">Category <select id="viewer-category"><option value="">Unassigned</option>${data.categories.map(c => `<option value="${c.id}" ${Number(c.id) === Number(data.category_id) ? "selected" : ""}>${esc(c.name)}${Number(c.id) === Number(data.category_id) && data.category_source === "automatic" ? " (suggested)" : ""}</option>`).join("")}</select></label>
        </div>
        <div class="viewer-path"><strong>Target Path</strong><span>${esc(data.final_file_path || "Not saved locally")}</span></div>
      </div>
      <aside class="viewer-sidebar">
        <div class="viewer-statuses">
          ${viewerStatusButton("new", "New", data.status, "Set status to New (N)")}
          ${viewerStatusButton("potential", "High Potential", data.status, "Set status to High Potential (H)")}
          ${viewerStatusButton("rejected", "Rejected", data.status, "Reject post (Delete)")}
          ${viewerStatusButton("saved", "Saved", data.status)}
        </div>
        <label class="viewer-auto-next"><input id="viewer-next-after-status" type="checkbox" ${state.nextAfterStatusChange ? "checked" : ""}> Next after status change</label>
        <div class="viewer-tag-top">
          ${viewerTagGroup("Artist", "artist", tags.artist)}
          ${viewerTagGroup("Series / Copyright", "copyright", tags.copyright)}
          ${viewerTagGroup("Character", "character", tags.character)}
        </div>
        ${viewerTagGroup("General", "general", tags.general, true)}
        ${viewerTagGroup("Meta", "meta", tags.meta, true)}
        <label class="viewer-tag-filter"><input id="viewer-filename-filter" type="checkbox"> Show only tags allowed in filenames</label>
        <div class="viewer-details"><span>${data.image_width || 0} x ${data.image_height || 0}</span><span>${esc(data.file_ext || "")}</span><span>${esc(data.status || "new")}</span></div>
      </aside>
    </div>`;
    $("#viewer-filename-filter").checked = state.viewerFilenameFilter;
    $("#viewer").classList.toggle("hide-filename-excluded", state.viewerFilenameFilter);
    $("#viewer-back").onclick = () => showTab("preview");
    $("#viewer-prev").onclick = () => previousId != null && openViewer(previousId, true, historyPreviousId != null ? "back" : "append");
    $("#viewer-next").onclick = () => nextId != null && openViewer(nextId, true, historyNextId != null ? "forward" : "append");
    $("#viewer-fit").onchange = event => {
      const nativeSize = !event.target.checked;
      $("#viewer-stage").classList.toggle("native-size", nativeSize);
      $("#viewer-image").classList.toggle("native-size", nativeSize);
      event.target.blur();
    };
    $("#viewer-copy-link").onclick = () => navigator.clipboard.writeText(data.original_post_url).then(() => toast("Link copied"));
    $("#viewer-save").onclick = async () => {
      const button = $("#viewer-save");
      const overwriteExisting = Boolean(data.final_file_path);
      if (overwriteExisting && !confirm(`Replace the existing saved file?\n\n${data.final_file_path}`)) return;
      button.disabled = true;
      try {
        const categoryValue = $("#viewer-category").value;
        const result = await api(`/api/posts/${data.id}/save`, {
          method: "POST",
          body: JSON.stringify({
            category_id: categoryValue ? Number(categoryValue) : null,
            overwrite_existing: overwriteExisting,
          }),
        });
        toast(`Saved to ${result.final_path}`);
        if (nextId != null) await openViewer(nextId, true, historyNextId != null ? "forward" : "append");
        else await openViewer(data.id, false);
      } catch (error) {
        toast(error.message);
      } finally {
        if (document.body.contains(button)) button.disabled = false;
      }
    };
    $("#viewer-filename-filter").onchange = event => {
      state.viewerFilenameFilter = event.target.checked;
      $("#viewer").classList.toggle("hide-filename-excluded", event.target.checked);
      event.target.blur();
    };
    $("#viewer-next-after-status").onchange = async event => {
      const checkbox = event.target;
      const previous = state.nextAfterStatusChange;
      state.nextAfterStatusChange = checkbox.checked;
      checkbox.blur();
      try {
        await api("/api/viewer/settings", {
          method: "PUT",
          body: JSON.stringify({next_after_status_change: state.nextAfterStatusChange}),
        });
        toast("Viewer preference saved");
      } catch (error) {
        state.nextAfterStatusChange = previous;
        checkbox.checked = previous;
        toast(error.message);
      }
    };
    $$('[data-strip-post]').forEach(button => button.onclick = () => openViewer(Number(button.dataset.stripPost)));
    $$('[data-viewer-status]').forEach(button => button.onclick = async () => {
      const statusButtons = $$('[data-viewer-status]');
      statusButtons.forEach(item => { item.disabled = true; });
      try {
        await api(`/api/posts/${data.id}`, {method: "PATCH", body: JSON.stringify({status: button.dataset.viewerStatus})});
        statusButtons.forEach(item => item.classList.toggle("active", item === button));
        toast("Status saved");
        if (state.nextAfterStatusChange && nextId != null) {
          await openViewer(nextId, true, historyNextId != null ? "forward" : "append");
        }
      } catch (error) {
        toast(error.message);
      } finally {
        statusButtons.forEach(item => { if (document.body.contains(item)) item.disabled = false; });
      }
    });
    $$('[data-rating]').forEach(button => button.onclick = async () => {
      const stars = Number(button.dataset.rating);
      await api(`/api/posts/${data.id}`, {method: "PATCH", body: JSON.stringify({stars})});
      $$('[data-rating]').forEach(item => item.classList.toggle("active", Number(item.dataset.rating) <= stars));
      $("#viewer-rating-label").textContent = `Personal Rating: ${stars}/10`;
    });
    $("#viewer-category").onchange = async event => {
      event.target.blur();
      const select = event.target;
      if (!select.value) return;
      select.disabled = true;
      try {
        const result = await api(`/api/posts/${data.id}`, {method: "PATCH", body: JSON.stringify({category_id: Number(select.value)})});
        data.category_id = result.category_id;
        data.category = result.category;
        data.category_source = result.category_source;
        [...select.options].forEach(option => {
          option.textContent = option.textContent.replace(/ \(suggested\)$/, "");
        });
        toast(`Category saved: ${result.category}`);
      } catch (error) {
        select.value = data.category_id == null ? "" : String(data.category_id);
        toast(error.message);
      } finally {
        select.disabled = false;
      }
    };
  } catch (error) { toast(error.message); }
}

function renderFetch(data) {
  $("#fetch-start").disabled = data.running;
  $("#fetch-cancel").disabled = !data.running || data.cancelling;
  $("#global-status").textContent = data.running ? (data.message || "Fetch running") : "Ready";
  const progress = data.progress || {};
  $("#fetch-state").innerHTML = `<dt>State</dt><dd>${esc(data.phase)}</dd><dt>Message</dt><dd>${esc(data.message || "-")}</dd><dt>Started</dt><dd>${esc(data.started_at || "-")}</dd><dt>Seen</dt><dd>${progress.seen_posts ?? 0}</dd><dt>Inserted</dt><dd>${progress.inserted_posts ?? 0}</dd><dt>Updated</dt><dd>${progress.updated_posts ?? 0}</dd>`;
  $("#fetch-result").textContent = data.error || (data.result ? JSON.stringify(data.result, null, 2) : "");
}

async function pollFetch() {
  try { renderFetch(await api("/api/fetch")); } catch (_) {}
}

function applySchedule(data) {
  $("#schedule-enabled").checked = data.enabled;
  $("#schedule-hours").value = data.interval_hours;
}

function updateFetchSourceFields() {
  const saved = $("#fetch-source").value === "saved_searches";
  $("#fetch-query-field").classList.toggle("hidden", saved);
  $("#fetch-saved-labels-field").classList.toggle("hidden", !saved);
  $("#fetch-saved-queries-field").classList.toggle("hidden", !saved);
}

function applyFetchPreset(payload) {
  state.fetchPresetPayload = {...payload};
  $("#fetch-source").value = payload.source_mode === "saved_searches" ? "saved_searches" : "tags";
  $("#fetch-query").value = payload.manual_query || payload.search_tags || "order:id_desc";
  $("#fetch-saved-labels").value = payload.saved_search_labels || "";
  $("#fetch-saved-queries").value = payload.saved_search_queries || "";
  $("#fetch-per-query").value = payload.max_posts_per_query || 200;
  $("#fetch-total").value = payload.max_total_posts || 500;
  $("#fetch-known").value = payload.max_consecutive_known_posts || 0;
  updateFetchSourceFields();
}

function currentFetchPayload() {
  return {
    ...state.fetchPresetPayload,
    source_mode: $("#fetch-source").value,
    manual_query: $("#fetch-query").value.trim(),
    saved_search_labels: $("#fetch-saved-labels").value.trim(),
    saved_search_queries: $("#fetch-saved-queries").value.trim(),
    max_posts_per_query: Number($("#fetch-per-query").value),
    max_total_posts: Number($("#fetch-total").value),
    max_consecutive_known_posts: Number($("#fetch-known").value),
  };
}

async function loadFetchPresets(selectedName = null) {
  try {
    const data = await api("/api/fetch-presets");
    state.fetchPresets = new Map(data.items.map(item => [item.name, item.payload]));
    const select = $("#fetch-preset");
    const selected = selectedName ?? select.value;
    select.innerHTML = `<option value="">No preset</option>${data.items.map(item => `<option value="${esc(item.name)}">${esc(item.name)}</option>`).join("")}`;
    if (selected && state.fetchPresets.has(selected)) select.value = selected;
    $("#fetch-preset-delete").disabled = !select.value;
  } catch (error) { toast(error.message); }
}

async function saveFetchPreset() {
  const name = $("#fetch-preset-name").value.trim();
  if (!name) throw new Error("Enter a preset name");
  await api(`/api/fetch-presets/${encodeURIComponent(name)}`, {method: "PUT", body: JSON.stringify({payload: currentFetchPayload()})});
  await loadFetchPresets(name);
  toast("Fetch preset saved");
}

async function deleteFetchPreset() {
  const name = $("#fetch-preset").value;
  if (!name || !confirm(`Delete fetch preset '${name}'?`)) return;
  await api(`/api/fetch-presets/${encodeURIComponent(name)}`, {method: "DELETE"});
  state.fetchPresetPayload = {};
  $("#fetch-preset-name").value = "";
  await loadFetchPresets("");
  toast("Fetch preset deleted");
}

async function loadTags() {
  try {
    const params = new URLSearchParams({search: $("#tag-search").value, tag_type: $("#tag-type").value, limit: 200});
    const data = await api(`/api/tags?${params}`);
    $("#tag-rows").innerHTML = data.items.map((tag, index) => `<tr data-tag-row data-tag="${esc(tag.tag)}" data-manual-score="${tag.manual_score}" data-scoring-excluded="${Boolean(tag.scoring_excluded)}" data-filename-excluded="${Boolean(tag.filename_excluded)}" data-fetch-excluded="${Boolean(tag.fetch_excluded)}" data-ignore-category="${Boolean(tag.ignore_category_influence)}" data-ignore-recommendation="${Boolean(tag.ignore_recommendation_score)}" data-ignore-llm="${Boolean(tag.ignore_llm_input)}" title="Right-click for tag actions"><td>${esc(tag.tag)}</td><td>${esc(tag.tag_type)}</td><td>${tag.post_count}</td><td>${tag.average_rating == null ? "-" : Number(tag.average_rating).toFixed(2)}</td><td><input class="tag-score" type="number" step="0.25" value="${tag.manual_score}"></td><td><input class="tag-alias" type="text" value="${esc(tag.alias_tag)}"></td><td><input class="tag-score-off" type="checkbox" ${tag.scoring_excluded ? "checked" : ""}></td><td><input class="tag-fetch-off" type="checkbox" ${tag.fetch_excluded ? "checked" : ""}></td><td><button data-save-tag="${index}">Save</button></td></tr>`).join("");
  } catch (error) { toast(error.message); }
}

async function saveTag(button) {
  const row = button.closest("tr");
  const score = row.querySelector(".tag-score").value;
  await api(`/api/tags/${encodeURIComponent(row.dataset.tag)}`, {method:"PATCH", body:JSON.stringify({alias:row.querySelector(".tag-alias").value, manual_score:score === "" ? null : Number(score), scoring_excluded:row.querySelector(".tag-score-off").checked, fetch_excluded:row.querySelector(".tag-fetch-off").checked})});
  toast("Tag saved");
}

async function loadCategories() {
  try {
    const data = await api("/api/categories");
    $("#category-list").innerHTML = data.items.map(c => `<div class="list-row"><span>${c.sort_order}</span><strong>${esc(c.name)}</strong><span>${esc(c.folder_name)}</span><button class="danger" data-delete-category="${c.id}">Delete</button></div>`).join("") || "No categories";
  } catch (error) { toast(error.message); }
}

async function loadConfig() {
  try {
    const data = await api("/api/settings");
    $("#config-form").innerHTML = `<label>Danbooru URL <input name="base_url" value="${esc(data.base_url)}"></label><label>Username <input name="username" value="${esc(data.username || "")}"></label><label>API key <input name="api_key" type="password" placeholder="${data.api_key_configured ? "Configured" : "Not configured"}"></label><label>Request timeout <input name="request_timeout_seconds" type="number" value="${data.request_timeout_seconds}"></label><label>Minimum request interval <input name="request_min_interval_seconds" type="number" step="0.05" value="${data.request_min_interval_seconds}"></label><button class="primary" type="submit">Save configuration</button><small>Database: ${esc(data.database_file)}</small>`;
  } catch (error) { toast(error.message); }
}

async function loadMaintenance() {
  try {
    const data = await api("/api/maintenance");
    const values = {...data.counts, database_bytes: data.file_sizes.database, wal_bytes: data.file_sizes.wal, free_pages: data.sqlite.freelist_count};
    $("#maintenance-report").innerHTML = Object.entries(values).map(([key,value]) => `<div class="metric-box"><span>${esc(key.replaceAll("_", " "))}</span><strong>${Number(value || 0).toLocaleString()}</strong></div>`).join("");
  } catch (error) { toast(error.message); }
}

document.addEventListener("click", event => {
  const tagAction = event.target.closest("[data-tag-action]");
  if (tagAction) {
    $("#tag-context-menu").classList.add("hidden");
    runTagContextAction(tagAction.dataset.tagAction).catch(error => toast(error.message));
    return;
  }
  if (!event.target.closest("#tag-context-menu")) $("#tag-context-menu").classList.add("hidden");
  const tab = event.target.closest("[data-tab]");
  if (tab) showTab(tab.dataset.tab);
  const viewer = event.target.closest("[data-viewer]");
  if (viewer) { event.preventDefault(); openViewer(Number(viewer.dataset.viewer)); }
  const saveTagButton = event.target.closest("[data-save-tag]");
  if (saveTagButton) saveTag(saveTagButton).catch(error => toast(error.message));
  const deleteCategory = event.target.closest("[data-delete-category]");
  if (deleteCategory && confirm("Delete this category?")) api(`/api/categories/${deleteCategory.dataset.deleteCategory}`, {method:"DELETE"}).then(loadCategories).catch(error => toast(error.message));
});

document.addEventListener("contextmenu", event => {
  const row = event.target.closest("[data-tag-row]");
  if (row) openTagContextMenu(event, row);
  else $("#tag-context-menu").classList.add("hidden");
});

$("#preview-apply").onclick = () => savePreviewSettings().then(resetPreview).catch(error => toast(error.message));
$("#preview-thumbnail-size").onchange = () => savePreviewSettings().catch(error => toast(error.message));
$("#fetch-source").onchange = updateFetchSourceFields;
$("#fetch-preset").onchange = event => {
  const name = event.target.value;
  $("#fetch-preset-name").value = name;
  $("#fetch-preset-delete").disabled = !name;
  if (name && state.fetchPresets.has(name)) applyFetchPreset(state.fetchPresets.get(name));
};
$("#fetch-preset-save").onclick = () => saveFetchPreset().catch(error => toast(error.message));
$("#fetch-preset-delete").onclick = () => deleteFetchPreset().catch(error => toast(error.message));
$("#tag-load").onclick = loadTags;
$("#maintenance-refresh").onclick = loadMaintenance;
$("#maintenance-checkpoint").onclick = () => api("/api/maintenance/checkpoint", {method:"POST"}).then(() => { toast("WAL checkpoint completed"); loadMaintenance(); }).catch(error => toast(error.message));
$("#fetch-start").onclick = async () => {
  try { renderFetch(await api("/api/fetch", {method:"POST", body:JSON.stringify({preset_name:$("#fetch-preset").value || null, payload:currentFetchPayload()})})); }
  catch (error) { toast(error.message); }
};
$("#fetch-cancel").onclick = () => api("/api/fetch/cancel", {method:"POST"}).then(renderFetch).catch(error => toast(error.message));
$("#schedule-form").onsubmit = async event => { event.preventDefault(); try { applySchedule(await api("/api/scheduler", {method:"PUT", body:JSON.stringify({enabled:$("#schedule-enabled").checked, interval_hours:Number($("#schedule-hours").value)})})); toast("Schedule saved"); } catch(error) { toast(error.message); } };
$("#category-form").onsubmit = async event => { event.preventDefault(); try { await api("/api/categories", {method:"POST", body:JSON.stringify({name:$("#category-name").value, folder_name:$("#category-folder").value || null})}); event.target.reset(); loadCategories(); } catch(error) { toast(error.message); } };
$("#config-form").onsubmit = async event => { event.preventDefault(); const form = new FormData(event.target); const payload = Object.fromEntries(form.entries()); if (!payload.api_key) delete payload.api_key; payload.request_timeout_seconds = Number(payload.request_timeout_seconds); payload.request_min_interval_seconds = Number(payload.request_min_interval_seconds); try { await api("/api/settings", {method:"PATCH", body:JSON.stringify(payload)}); toast("Configuration saved"); } catch(error) { toast(error.message); } };

new IntersectionObserver(entries => { if (entries[0].isIntersecting) loadMorePosts(); }, {rootMargin:"500px"}).observe($("#preview-sentinel"));
window.addEventListener("popstate", () => { const match = location.pathname.match(/^\/viewer\/(\d+)/); if (match) openViewer(Number(match[1]), false, "select"); else showTab("preview"); });
function isTypingTarget(target) {
  if (target instanceof HTMLInputElement) {
    return !["button", "checkbox", "color", "radio", "range", "reset", "submit"].includes(target.type);
  }
  return target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || target?.isContentEditable;
}

document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !$("#tag-context-menu").classList.contains("hidden")) {
    $("#tag-context-menu").classList.add("hidden");
    return;
  }
  if ($("#viewer").classList.contains("hidden") || isTypingTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;

  const key = event.key.toLowerCase();
  let target = null;
  if (event.key === "ArrowLeft") target = $("#viewer-prev");
  else if (event.key === "ArrowRight") target = $("#viewer-next");
  else if (event.key === "Escape") target = $("#viewer-back");
  else if (/^[1-5]$/.test(event.key)) target = $(`[data-rating="${event.key}"]`);
  else if (key === "h") target = $('[data-viewer-status="potential"]');
  else if (key === "n") target = $('[data-viewer-status="new"]');
  else if (event.key === "Delete") target = $('[data-viewer-status="rejected"]');
  else if (key === "o") target = $("#viewer-original");
  else if (key === "f") target = $("#viewer-save");

  if (target && !target.disabled) {
    event.preventDefault();
    target.click();
  }
});

bootstrap().then(() => {
  const match = location.pathname.match(/^\/viewer\/(\d+)/);
  if (match) openViewer(Number(match[1]), false); else resetPreview();
}).catch(error => toast(error.message));
setInterval(pollFetch, 1500);
