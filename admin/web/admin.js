/* The Unending — admin page.
 *
 * Talks same-origin to the admin API (DESIGN.md, /api/v0). Plain JS, no build step.
 * Everything you might want to change lives in CONFIG.
 */
"use strict";

const CONFIG = {
  apiBase: "/api/v0",

  // Set models. The API has no endpoint for these, so keep in sync with its settings.
  // The first entry is the default.
  models: [
    "black-forest-labs/FLUX.2-klein-4B",
    "black-forest-labs/FLUX.1-schnell",
  ],

  // How often to refresh while a draft or run is PENDING / IN_PROGRESS.
  pollMs: 4000,

  // Completed drafts get a preview from GET .../drafts/{id}/preview, which returns a
  // short-lived presigned URL. Reuse a fetched URL for this long before asking again;
  // keep it well under the presign expiry.
  previewReuseMs: 5 * 60 * 1000,
};

/* ------------------------------------------------------------------ *
 * Validation, mirroring DESIGN.md
 * ------------------------------------------------------------------ */

const SLUG_RE = /^[a-z][a-z0-9-]{1,126}[a-z]$/;
const PROMPT_MAX = 1023;
const ACTIVE = new Set(["PENDING", "IN_PROGRESS"]);
const CANCELABLE = new Set(["SUBMITTED", "IN_PROGRESS"]);

function slugProblem(slug) {
  if (!slug) return null;
  if (!SLUG_RE.test(slug)) {
    return "lowercase letters, digits, hyphens; starts and ends with a letter; 3–128 chars";
  }
  return null;
}

function nameProblem(name) {
  if (!name) return null;
  if (name.length > 64) return "at most 64 characters";
  const words = name.split(" ");
  if (words.some((w) => w === "")) return "single spaces between words, none at the ends";
  if (words.length > 3) return "at most 3 words";
  if (!words.every((w) => /^\p{Lu}/u.test(w))) return "Title Case: each word starts uppercase";
  return null;
}

/* ------------------------------------------------------------------ *
 * Token storage (sessionStorage by default; localStorage if remembered)
 * ------------------------------------------------------------------ */

const TOKEN_KEY = "unending-admin-token";

function storageGet(store, key) {
  try { return window[store].getItem(key); } catch { return null; }
}
function storageSet(store, key, value) {
  try {
    if (value === null) window[store].removeItem(key);
    else window[store].setItem(key, value);
  } catch { /* storage unavailable: token lives for this page load only */ }
}

let memoryToken = null;

function getToken() {
  return memoryToken ?? storageGet("sessionStorage", TOKEN_KEY) ?? storageGet("localStorage", TOKEN_KEY);
}

function setToken(token, remember) {
  memoryToken = token || null;
  storageSet("sessionStorage", TOKEN_KEY, token || null);
  storageSet("localStorage", TOKEN_KEY, remember && token ? token : null);
}

/* ------------------------------------------------------------------ *
 * API client
 * ------------------------------------------------------------------ */

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function errorMessage(status, body) {
  if (!body) return `HTTP ${status}`;
  const d = body.detail ?? body.details ?? body.error;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    // FastAPI 422: [{loc: [...], msg: "..."}]
    return d.map((e) => {
      const where = Array.isArray(e.loc) ? e.loc.filter((p) => p !== "body").join(".") : "";
      return where ? `${where}: ${e.msg}` : e.msg;
    }).join("\n");
  }
  if (d && typeof d === "object") return d.error ?? JSON.stringify(d);
  return `HTTP ${status}`;
}

async function api(method, path, body) {
  const headers = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(CONFIG.apiBase + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch (err) {
    setConn(false, "network error");
    throw new ApiError(0, `Network error: ${err.message}`);
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = { detail: text.slice(0, 300) }; }
  }

  if (res.status === 401 || res.status === 403) {
    setConn(false, res.status === 401 ? "no token" : "token rejected");
    openTokenDialog();
    throw new ApiError(res.status, res.status === 401 ? "Unauthorized: set a token." : "Forbidden: token rejected.");
  }
  if (!res.ok) {
    setConn(true);
    throw new ApiError(res.status, errorMessage(res.status, data));
  }
  setConn(true);
  return data;
}

const API = {
  listSets: (params) => api("GET", `/sets${query(params)}`),
  getSet: (id) => api("GET", `/sets/${id}`),
  createSet: (body) => api("POST", "/sets", body),
  patchSet: (id, body) => api("PATCH", `/sets/${id}`, body),
  abandonSet: (id) => api("DELETE", `/sets/${id}`),
  listDrafts: (setId) => api("GET", `/sets/${setId}/drafts`),
  createDraft: (setId, prompt) => api("POST", `/sets/${setId}/drafts`, { prompt }),
  commitDraft: (setId, draftId) => api("POST", `/sets/${setId}/drafts/${draftId}/commit`),
  listRuns: (params) => api("GET", `/runs${query(params)}`),
  redoRun: (runId) => api("POST", `/runs/${runId}`),
  cancelRun: (runId) => api("POST", `/runs/${runId}/cancel`),
  publishSet: (setId) => api("POST", `/sets/${setId}/publish`),
  draftPreview: (setId, draftId) => api("GET", `/sets/${setId}/drafts/${draftId}/preview`),
};

function query(params) {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}

/* ------------------------------------------------------------------ *
 * Small DOM helpers
 * ------------------------------------------------------------------ */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function fromTemplate(id) {
  return document.getElementById(id).content.cloneNode(true);
}

function field(root, name) {
  return root.querySelector(`[data-field="${name}"]`);
}

function setBadge(el, status) {
  el.className = el.className.replace(/\bs-\S+/g, "").trim();
  el.classList.add("badge", `s-${status}`);
  el.textContent = status.replace("_", " ");
}

// API timestamps are naive UTC; make sure the browser parses them as UTC.
function parseUtc(ts) {
  if (!ts) return null;
  const hasZone = /[zZ]|[+-]\d\d:?\d\d$/.test(ts);
  const d = new Date(hasZone ? ts : `${ts}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dateFmt = new Intl.DateTimeFormat(undefined, {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});

function fmtTime(ts) {
  const d = parseUtc(ts);
  return d ? dateFmt.format(d) : "—";
}

function fmtDuration(ms) {
  if (ms < 0 || !Number.isFinite(ms)) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function shortModel(model) {
  return model.split("/").pop();
}

// "(slug)" beside the name. Without a name the slug already is the title, so skip it.
function slugLabel(set) {
  return set.name && set.slug ? `(${set.slug})` : null;
}

function setTitle(set) {
  return set.name || set.slug || "Untitled set";
}

let toastTimer = null;
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 7000 : 3000);
}

function reportError(err) {
  console.error(err);
  toast(err instanceof ApiError ? err.message : String(err), true);
}

async function withBusy(button, fn) {
  if (button) { button.disabled = true; button.classList.add("busy"); }
  try { return await fn(); }
  finally { if (button) { button.disabled = false; button.classList.remove("busy"); } }
}

async function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Fallback for contexts without the async clipboard API (e.g. insecure origins).
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function setConn(ok, why) {
  const el = $("#conn-status");
  el.classList.toggle("ok", ok);
  el.classList.toggle("bad", !ok);
  el.textContent = ok ? "connected" : (why || "offline");
}

function confirmDialog({ title, body, ok }) {
  const dlg = $("#confirm-dialog");
  field(dlg, "title").textContent = title;
  field(dlg, "body").textContent = body;
  field(dlg, "ok").textContent = ok;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
  });
}

/* ------------------------------------------------------------------ *
 * State
 * ------------------------------------------------------------------ */

const state = {
  sets: [],
  filter: "active",
  route: { view: "home" },
  current: null,      // { set, drafts, runs } for the open set
  pollTimer: null,
  loadSeq: 0,         // guards against out-of-order responses when switching sets
  redoing: false,     // guards against duplicate redo submissions while in flight
  publishing: false,  // guards against duplicate publish submissions while in flight
  cancelling: false,  // guards against duplicate cancel submissions while in flight
};

/* One AbortController per rendered view; listeners on long-lived elements use its
 * signal so they disappear with the view. */
let viewController = new AbortController();
function resetView() {
  viewController.abort();
  viewController = new AbortController();
}
function viewSignal() {
  return viewController.signal;
}

/* ------------------------------------------------------------------ *
 * Set list
 * ------------------------------------------------------------------ */

async function loadSets() {
  const params = {};
  if (state.filter !== "active" && state.filter !== "all") params.status = state.filter;
  const data = await API.listSets(params);
  let sets = data.sets ?? [];
  if (state.filter === "active") sets = sets.filter((s) => (s.status !== "ABANDONED" && s.status !== "PUBLISHED"));
  sets.sort((a, b) => (parseUtc(b.created_at) ?? 0) - (parseUtc(a.created_at) ?? 0));
  state.sets = sets;
  renderSetList();
}

function renderSetList() {
  const list = $("#set-list");
  list.replaceChildren();
  const currentId = state.route.view === "set" ? state.route.id : null;

  for (const set of state.sets) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `#/sets/${set.set_id}`;
    if (set.set_id === currentId) a.setAttribute("aria-current", "true");

    const title = document.createElement("span");
    title.className = "title";
    if (!set.name && !set.slug) title.classList.add("untitled");
    title.textContent = setTitle(set);
    const slug = slugLabel(set);
    if (slug) {
      const s = document.createElement("span");
      s.className = "slug";
      s.textContent = slug;
      title.append(s);
    }

    const sub = document.createElement("span");
    sub.className = "sub";
    const badge = document.createElement("span");
    setBadge(badge, set.status);
    badge.classList.add("small");
    const meta = document.createElement("span");
    meta.className = "kicker";
    meta.textContent = `${shortModel(set.model)} · ${fmtTime(set.created_at)}`;
    sub.append(badge, meta);

    a.append(title, sub);
    li.append(a);
    list.append(li);
  }
  $("#set-list-empty").hidden = state.sets.length > 0;
}

/* ------------------------------------------------------------------ *
 * New set view
 * ------------------------------------------------------------------ */

function renderNewSet() {
  const detail = $("#detail");
  detail.replaceChildren(fromTemplate("tpl-new-set"));
  const form = $("#new-set-form");

  const modelSelect = form.elements.model;
  for (const m of CONFIG.models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSelect.append(opt);
  }

  wireValidation(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!validateForm(form)) return;
    const body = { model: form.elements.model.value };
    const slug = form.elements.slug.value.trim();
    const name = form.elements.name.value.trim();
    if (slug) body.slug = slug;
    if (name) body.name = name;

    try {
      const set = await withBusy(form.querySelector("button[type=submit]"), () => API.createSet(body));
      toast("Set created.");
      await loadSets().catch(reportError);
      location.hash = `#/sets/${set.set_id}`;
    } catch (err) { reportError(err); }
  });

  form.elements.slug.focus();
}

function wireValidation(form) {
  for (const [name, check] of [["slug", slugProblem], ["name", nameProblem]]) {
    const input = form.elements[name];
    if (!input) continue;
    const hint = form.querySelector(`[data-hint="${name}"]`);
    const original = hint ? hint.textContent : "";
    input.addEventListener("input", () => {
      const problem = check(input.value.trim());
      input.classList.toggle("bad", !!problem);
      if (hint) {
        hint.textContent = problem || original;
        hint.classList.toggle("bad", !!problem);
      }
    });
  }
}

function validateForm(form) {
  let ok = true;
  for (const [name, check] of [["slug", slugProblem], ["name", nameProblem]]) {
    const input = form.elements[name];
    if (!input || input.disabled) continue;
    const problem = check(input.value.trim());
    if (problem) {
      ok = false;
      input.classList.add("bad");
      input.dispatchEvent(new Event("input"));
    }
  }
  if (!ok) toast("Fix the highlighted fields.", true);
  return ok;
}

/* ------------------------------------------------------------------ *
 * Set detail view
 * ------------------------------------------------------------------ */

async function openSet(setId) {
  stopPolling();
  const seq = ++state.loadSeq;
  const detail = $("#detail");
  detail.replaceChildren(fromTemplate("tpl-set-detail"));
  detail.dataset.setId = setId;
  wireSetDetail(detail, setId);

  try {
    await refreshCurrent(setId, seq, { resetForm: true });
  } catch (err) {
    if (seq !== state.loadSeq) return;
    if (err instanceof ApiError && err.status === 404) {
      detail.replaceChildren();
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "That set doesn't exist.";
      detail.append(p);
    } else {
      reportError(err);
    }
  }
}

async function refreshCurrent(setId, seq = state.loadSeq, { resetForm = false } = {}) {
  const [set, draftsResp, runsResp] = await Promise.all([
    API.getSet(setId),
    API.listDrafts(setId),
    API.listRuns({ set_id: setId }),
  ]);
  if (seq !== state.loadSeq) return; // user moved on

  state.current = {
    set,
    drafts: draftsResp.drafts ?? [],
    runs: runsResp.runs ?? [],
  };
  renderSetMeta(resetForm);
  renderBatch();
  renderDrafts();
  syncListRow(set);
  schedulePoll();
}

function wireSetDetail(detail, setId) {
  const editForm = $("#edit-set-form", detail);
  wireValidation(editForm);

  editForm.addEventListener("input", () => { editForm.dataset.dirty = "1"; });

  editForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!validateForm(editForm)) return;
    const { set } = state.current;
    const slug = editForm.elements.slug.value.trim();
    const name = editForm.elements.name.value.trim();
    const body = {};
    if (slug && slug !== (set.slug ?? "")) body.slug = slug;
    if (name && name !== (set.name ?? "")) body.name = name;
    if (!Object.keys(body).length) { toast("Nothing to save."); return; }

    try {
      await withBusy(editForm.querySelector('[data-action="save"]'), () => API.patchSet(setId, body));
      delete editForm.dataset.dirty;
      toast("Saved.");
      await refreshCurrent(setId, state.loadSeq, { resetForm: true });
    } catch (err) { reportError(err); }
  });

  editForm.querySelector('[data-action="abandon"]').addEventListener("click", async (e) => {
    const ok = await confirmDialog({
      title: "Abandon this set?",
      body: "It will be marked ABANDONED and can't be drafted or committed afterwards.",
      ok: "Abandon",
    });
    if (!ok) return;
    try {
      await withBusy(e.currentTarget, () => API.abandonSet(setId));
      toast("Set abandoned.");
      await Promise.all([refreshCurrent(setId, state.loadSeq, { resetForm: true }), loadSets()]);
    } catch (err) { reportError(err); }
  });

  const draftForm = $("#new-draft-form", detail);
  const promptInput = draftForm.elements.prompt;
  const counter = field(detail, "prompt-count");
  const updateCount = () => {
    const n = promptInput.value.length;
    counter.textContent = `${n}/${PROMPT_MAX}`;
    counter.classList.toggle("bad", n > PROMPT_MAX);
  };
  promptInput.addEventListener("input", updateCount);
  updateCount();

  draftForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt) { toast("Write a prompt first.", true); return; }
    if (prompt.length > PROMPT_MAX) { toast(`Prompt must be at most ${PROMPT_MAX} characters.`, true); return; }
    try {
      await withBusy(draftForm.querySelector("button[type=submit]"), () => API.createDraft(setId, prompt));
      promptInput.value = "";
      updateCount();
      toast("Draft started.");
      await refreshCurrent(setId);
    } catch (err) { reportError(err); }
  });

  // ⌘/Ctrl+Enter submits the prompt
  promptInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) draftForm.requestSubmit();
  });

  // Delegated actions inside draft and batch lists. #detail outlives views, so the
  // listener is tied to this view's AbortController and removed when the view changes;
  // otherwise every visit to a set would add another handler (and another POST).
  detail.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;

    if (action === "commit") {
      const draft = state.current.drafts.find((d) => d.draft_id === btn.dataset.draftId);
      if (!draft || state.committing) return;
      state.committing = true;
      try {
        const ok = await confirmDialog({
          title: `Commit “${setTitle(state.current.set)}”?`,
          body: `This locks the set to this prompt and starts the full batch:\n\n“${draft.prompt}”`,
          ok: "Commit & run batch",
        });
        if (!ok) return;
        try {
          await withBusy(btn, () => API.commitDraft(setId, draft.draft_id));
          toast("Committed. Batch run started.");
          await Promise.all([refreshCurrent(setId, state.loadSeq, { resetForm: true }), loadSets()]);
        } catch (err) { reportError(err); }
      } finally {
        state.committing = false;
      }
    }

    if (action === "publish") {
      const { set } = state.current;
      if (state.publishing || set.status !== "COMPLETED") return;
      state.publishing = true;
      try {
        const ok = await confirmDialog({
          title: `Publish “${setTitle(set)}”?`,
          body: "This starts the publish task: it builds the set's assets and ships them to the site bucket.\n\nPublished assets are write-once.",
          ok: "Publish",
        });
        if (!ok) return;
        try {
          await withBusy(btn, () => API.publishSet(setId));
          toast("Publishing. Publish run started.");
          await Promise.all([refreshCurrent(setId, state.loadSeq, { resetForm: true }), loadSets()]);
        } catch (err) { reportError(err); }
      } finally {
        state.publishing = false;
      }
    }

    if (action === "redo") {
      if (state.redoing) return;
      state.redoing = true;
      try {
        await withBusy(btn, () => API.redoRun(btn.dataset.runId));
        toast("Run resubmitted.");
        await refreshCurrent(setId);
      } catch (err) { reportError(err); }
      finally { state.redoing = false; }
    }

    if (action === "cancel") {
      if (state.cancelling) return;
      state.cancelling = true;
      try {
        const ok = await confirmDialog({
          title: `Cancel this ${btn.dataset.runType ?? "run"}?`,
          body: "The external job will be cancelled and this run marked CANCELLED. It can be redone afterwards via Retry.",
          ok: "Cancel run",
        });
        if (!ok) return;
        try {
          await withBusy(btn, () => API.cancelRun(btn.dataset.runId));
          toast("Run cancelled.");
          await refreshCurrent(setId);
        } catch (err) { reportError(err); }
      } finally { state.cancelling = false; }
    }

    if (action === "copy-prompt") {
      const text = promptInput.value;
      if (!text.trim()) { toast("Write a prompt first.", true); return; }
      try {
        await copyToClipboard(text);
        btn.classList.add("copied");
        toast("Prompt copied.");
      } catch (err) {
        btn.classList.remove("copied");
        toast("Couldn't copy prompt.", true);
      }
    }
  }, { signal: viewSignal() });
}

function renderSetMeta(resetForm) {
  const { set } = state.current;
  const detail = $("#detail");

  field(detail, "model").textContent = set.model;
  const title = field(detail, "title");
  title.textContent = setTitle(set);
  title.classList.toggle("untitled", !set.name && !set.slug);
  const slugEl = field(detail, "slug");
  slugEl.textContent = slugLabel(set) ?? "";
  slugEl.hidden = !slugLabel(set);
  setBadge(field(detail, "status"), set.status);

  field(detail, "set_id").textContent = set.set_id;
  field(detail, "created_at").textContent = fmtTime(set.created_at);
  field(detail, "updated_at").textContent = fmtTime(set.updated_at);
  field(detail, "committed_at").textContent = fmtTime(set.committed_at);
  field(detail, "post_date").textContent = set.post_date ?? "—";
  field(detail, "abandoned_at").textContent = fmtTime(set.abandoned_at);
  field(detail, "prompt").textContent = set.prompt ?? "";

  field(detail, "published_at").textContent = fmtTime(set.published_at);
  $$('[data-show="published"]', detail).forEach((el) => { el.hidden = !set.published_at; });

  // Publish: only a COMPLETED set (a failed publish is retried from its run instead)
  detail.querySelector('[data-action="publish"]').hidden = set.status !== "COMPLETED";

  const committed = !!set.committed_at ||
    ["COMMITTED", "COMPLETED", "FAILED", "PUBLISHING", "PUBLISHED"].includes(set.status);
  $$('[data-show="committed"]', detail).forEach((el) => { el.hidden = !committed; });
  $$('[data-show="abandoned"]', detail).forEach((el) => { el.hidden = set.status !== "ABANDONED"; });

  // Editing: slug/name only while DRAFT. Don't clobber in-progress edits on a poll.
  const editable = set.status === "DRAFT";
  const editForm = $("#edit-set-form", detail);
  editForm.hidden = !editable;
  if (editable && (resetForm || !editForm.dataset.dirty)) {
    editForm.elements.slug.value = set.slug ?? "";
    editForm.elements.name.value = set.name ?? "";
    delete editForm.dataset.dirty;
    editForm.elements.slug.dispatchEvent(new Event("input"));
    editForm.elements.name.dispatchEvent(new Event("input"));
    delete editForm.dataset.dirty;
  }

  // New drafts only while DRAFT
  const draftForm = $("#new-draft-form", detail);
  draftForm.hidden = !editable;

  document.title = `${setTitle(set)} · Admin · The Unending`;
}

function runsFor(draftId, type) {
  return state.current.runs
    .filter((r) => r.draft_id === draftId && (!type || r.type === type))
    .sort((a, b) => (parseUtc(b.created_at) ?? 0) - (parseUtc(a.created_at) ?? 0));
}

// details is free-form JSON from the job. Known shapes get a readable summary;
// anything else falls back to compact key: value pairs. Full JSON is on hover.
function renderDetails(el, details) {
  el.replaceChildren();
  if (!details || typeof details !== "object" || !Object.keys(details).length) return;
  el.title = JSON.stringify(details, null, 2);

  const { keys, bucket, ...rest } = details;
  const parts = [];
  if (Array.isArray(keys)) {
    const n = keys.length;
    const files = `${n} file${n === 1 ? "" : "s"}`;
    parts.push(bucket ? `${files} in ${bucket}` : files);
  } else if (bucket) {
    parts.push(`bucket ${bucket}`);
  }
  for (const [k, v] of Object.entries(rest)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  }
  el.textContent = parts.join(" · ");
}

function renderRun(run, { latest }) {
  const node = fromTemplate("tpl-run");
  setBadge(field(node, "status"), run.status);
  field(node, "type").textContent = run.type;

  const start = parseUtc(run.created_at);
  const end = parseUtc(run.finished_at);
  let time = `started ${fmtTime(run.created_at)}`;
  if (end && start) time += ` · took ${fmtDuration(end - start)}`;
  else if (ACTIVE.has(run.status) && start) time += ` · ${fmtDuration(Date.now() - start)} so far`;
  field(node, "time").textContent = time;

  field(node, "message").textContent = run.message ?? "";
  renderDetails(field(node, "details"), run.details);
  const idEl = field(node, "run_id");
  idEl.textContent = run.run_id.slice(-8);
  idEl.title = `run ${run.run_id}\nexternal ${run.external_run_id}`;

  const redo = node.querySelector('[data-action="redo"]');
  // Only offer a retry on the most recent run for that draft/type, and only if it
  // failed or was cancelled.
  if (latest && (run.status === "FAILED" || run.status === "CANCELLED")) {
    redo.hidden = false;
    redo.dataset.runId = run.run_id;
  }

  const cancel = node.querySelector('[data-action="cancel"]');
  // Only offer a cancel for the newest BATCH run while it is still in flight.
  if (latest && run.type === "BATCH" && CANCELABLE.has(run.status)) {
    cancel.hidden = false;
    cancel.dataset.runId = run.run_id;
    cancel.dataset.runType = run.type;
  }
  return node;
}

function renderBatch() {
  const { set } = state.current;
  const detail = $("#detail");
  const section = $('[data-section="batch"]', detail);
  const batchRuns = state.current.runs
    .filter((r) => r.type === "BATCH" || r.type === "PUBLISH")
    .sort((a, b) => (parseUtc(b.created_at) ?? 0) - (parseUtc(a.created_at) ?? 0));
  // Retry is offered only on the newest run of each type
  const newestOfType = new Map();
  for (const r of batchRuns) if (!newestOfType.has(r.type)) newestOfType.set(r.type, r.run_id);

  section.hidden = batchRuns.length === 0 && set.status === "DRAFT";
  const box = field(detail, "batch-runs");
  box.replaceChildren();
  if (!batchRuns.length) {
    if (!section.hidden) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "No batch run recorded.";
      box.append(p);
    }
    return;
  }
  batchRuns.forEach((run) => box.append(renderRun(run, { latest: newestOfType.get(run.type) === run.run_id })));
}

/* Preview images: the API hands out short-lived presigned S3 URLs. <img> can't send
 * the Bearer token, so fetch the URL via the API, then point the <img> at S3.
 * URLs are cached per draft so the 4 s polling doesn't re-sign on every refresh. */
const previewCache = new Map(); // draft_id -> { url, at } | { failed: true, at }

async function previewUrl(setId, draftId, { fresh = false } = {}) {
  const hit = previewCache.get(draftId);
  if (!fresh && hit && Date.now() - hit.at < CONFIG.previewReuseMs) {
    if (hit.failed) return null;
    return hit.url;
  }
  try {
    const { preview_url: url } = await API.draftPreview(setId, draftId);
    previewCache.set(draftId, url ? { url, at: Date.now() } : { failed: true, at: Date.now() });
    return url || null;
  } catch (err) {
    console.warn("preview unavailable", draftId, err);
    previewCache.set(draftId, { failed: true, at: Date.now() });
    return null;
  }
}

async function showPreview(setId, draftId, fig) {
  const img = fig.querySelector("img");
  const link = fig.querySelector("a");
  let retried = false;

  const apply = (url) => {
    if (!url || !fig.isConnected) { fig.hidden = true; return; }
    link.href = url;
    img.src = url;
    fig.hidden = false;
  };

  // An expired or bad URL: re-sign once, then give up quietly.
  img.addEventListener("error", async () => {
    if (retried) { fig.hidden = true; return; }
    retried = true;
    apply(await previewUrl(setId, draftId, { fresh: true }));
  });

  apply(await previewUrl(setId, draftId));
}

function renderDrafts() {
  const { set, drafts } = state.current;
  const detail = $("#detail");
  const list = field(detail, "drafts");
  list.replaceChildren();
  field(detail, "drafts-empty").hidden = drafts.length > 0;

  const sorted = [...drafts].sort((a, b) => (parseUtc(b.created_at) ?? 0) - (parseUtc(a.created_at) ?? 0));

  for (const draft of sorted) {
    const node = fromTemplate("tpl-draft");
    const li = node.querySelector("li");

    setBadge(field(node, "status"), draft.status);
    field(node, "created_at").textContent = fmtTime(draft.created_at);
    field(node, "prompt").textContent = draft.prompt;
    const hash = field(node, "hash");
    hash.textContent = draft.model_prompt_hash.slice(0, 16) + "…";
    hash.title = draft.model_prompt_hash;

    const isCommitted = !!set.model_prompt_hash && set.model_prompt_hash === draft.model_prompt_hash;
    field(node, "committed-tag").hidden = !isCommitted;
    li.classList.toggle("is-committed", isCommitted);

    // Commit button: set DRAFT + draft COMPLETED + slug & name present
    const commit = node.querySelector('[data-action="commit"]');
    commit.dataset.draftId = draft.draft_id;
    if (set.status !== "DRAFT") {
      commit.hidden = true;
    } else {
      const reasons = [];
      if (draft.status !== "COMPLETED") reasons.push("draft must be COMPLETED");
      if (!set.slug) reasons.push("set needs a slug");
      if (!set.name) reasons.push("set needs a name");
      commit.disabled = reasons.length > 0;
      commit.title = reasons.length ? `Can't commit yet: ${reasons.join(", ")}` : "Commit the set with this prompt and run the batch";
    }

    // Preview grid for completed drafts (presigned URL fetched from the API); committed
    // drafts keep their preview since the draft status flips to COMMITTED on commit.
    if (draft.status === "COMPLETED" || draft.status === "COMMITTED") {
      showPreview(set.set_id, draft.draft_id, field(node, "preview"));
    }

    // Evaluation runs for this draft
    const runsBox = field(node, "runs");
    const evalRuns = runsFor(draft.draft_id, "EVALUATION");
    evalRuns.forEach((run, i) => runsBox.append(renderRun(run, { latest: i === 0 })));

    list.append(node);
  }
}

function syncListRow(set) {
  const i = state.sets.findIndex((s) => s.set_id === set.set_id);
  if (i === -1) return;
  const old = state.sets[i];
  if (old.status !== set.status || old.name !== set.name || old.slug !== set.slug) {
    state.sets[i] = set;
    renderSetList();
  }
}

/* ------------------------------------------------------------------ *
 * Polling: only while something is PENDING / IN_PROGRESS
 * ------------------------------------------------------------------ */

function hasActiveWork() {
  if (!state.current) return false;
  const { drafts, runs } = state.current;
  return drafts.some((d) => ACTIVE.has(d.status)) || runs.some((r) => ACTIVE.has(r.status));
}

function schedulePoll() {
  stopPolling();
  if (!hasActiveWork() || document.visibilityState === "hidden") return;
  const setId = state.current.set.set_id;
  state.pollTimer = setTimeout(async () => {
    if (state.route.view !== "set" || state.route.id !== setId) return;
    try {
      await refreshCurrent(setId);
    } catch (err) {
      console.warn("poll failed", err);
      if (!(err instanceof ApiError && (err.status === 401 || err.status === 403))) schedulePoll();
    }
  }, CONFIG.pollMs);
}

function stopPolling() {
  clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.route.view === "set" && state.current) {
    refreshCurrent(state.current.set.set_id).catch(reportError);
  } else if (document.visibilityState === "hidden") {
    stopPolling();
  }
});

/* ------------------------------------------------------------------ *
 * Token dialog
 * ------------------------------------------------------------------ */

function openTokenDialog() {
  const dlg = $("#token-dialog");
  if (dlg.open) return;
  const form = $("#token-form");
  form.elements.token.value = getToken() ?? "";
  form.elements.remember.checked = !!storageGet("localStorage", TOKEN_KEY);
  dlg.returnValue = "";
  dlg.showModal();
  form.elements.token.focus();
}

function wireTokenDialog() {
  const dlg = $("#token-dialog");
  $("#token-button").addEventListener("click", openTokenDialog);
  dlg.addEventListener("close", () => {
    const form = $("#token-form");
    if (dlg.returnValue === "save") {
      setToken(form.elements.token.value.trim(), form.elements.remember.checked);
      toast("Token saved.");
      boot();
    } else if (dlg.returnValue === "clear") {
      setToken(null, false);
      toast("Token cleared.");
    }
  });
}

/* ------------------------------------------------------------------ *
 * Routing
 * ------------------------------------------------------------------ */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function parseRoute() {
  const h = location.hash.replace(/^#\/?/, "");
  if (h === "new") return { view: "new" };
  const m = h.match(/^sets\/([^/]+)$/);
  if (m && UUID_RE.test(m[1])) return { view: "set", id: m[1].toLowerCase() };
  return { view: "home" };
}

function route() {
  resetView();
  state.route = parseRoute();
  stopPolling();
  state.current = null;

  $$(".site-bar [data-nav]").forEach((a) => {
    const on = (a.dataset.nav === "new" && state.route.view === "new") ||
               (a.dataset.nav === "sets" && state.route.view !== "new");
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  renderSetList();

  if (state.route.view === "new") {
    document.title = "New set · Admin · The Unending";
    renderNewSet();
  } else if (state.route.view === "set") {
    openSet(state.route.id);
  } else {
    document.title = "Admin · The Unending";
    const detail = $("#detail");
    detail.replaceChildren();
    const p = document.createElement("p");
    p.className = "empty";
    p.append("Pick a set, or ");
    const a = document.createElement("a");
    a.href = "#/new";
    a.textContent = "make a new one";
    p.append(a, ".");
    detail.append(p);
  }
}

/* ------------------------------------------------------------------ *
 * Boot
 * ------------------------------------------------------------------ */

async function boot() {
  if (!getToken()) { setConn(false, "no token"); route(); return; }
  try {
    await loadSets();
  } catch (err) {
    if (!(err instanceof ApiError && (err.status === 401 || err.status === 403))) reportError(err);
  }
  route();
}

document.addEventListener("DOMContentLoaded", () => {
  wireTokenDialog();

  $("#status-filter").addEventListener("change", (e) => {
    state.filter = e.target.value;
    loadSets().catch(reportError);
  });
  $("#refresh-sets").addEventListener("click", () => {
    loadSets().catch(reportError);
    if (state.route.view === "set" && state.current) refreshCurrent(state.current.set.set_id).catch(reportError);
  });
  window.addEventListener("hashchange", route);

  if (!getToken()) openTokenDialog();
  boot();
});
