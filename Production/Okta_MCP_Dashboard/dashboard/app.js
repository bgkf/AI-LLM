/**
 * dashboard/app.js
 *
 * Okta Intelligence Dashboard — client-side logic.
 * Handles apfel queries, health checks, export, workflow modal,
 * token modal, row selection, and table rendering.
 */

"use strict";

// ---------------------------------------------------------------------------
// Config / constants
// ---------------------------------------------------------------------------

const APFEL_BASE = "http://localhost:11434";
const APFEL_CHAT = `${APFEL_BASE}/v1/chat/completions`;
const APFEL_HEALTH = `${APFEL_BASE}/health`;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
  lastResult: null,          // { tool_called, result_count, data[] }
  selectedRows: new Set(),   // indices of checked rows
  pendingQuery: null,        // original query text for clarify re-submit
  lastInvokeUrl: "",         // last-used workflow URL (session only)
  activeRange: "24h",        // currently selected time range
  sortCol: null,
  sortDir: "asc",
};

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const $ = id => document.getElementById(id);

const elIndServer       = $("ind-server");
const elIndApi          = $("ind-api");
const elTooltipServer   = $("tooltip-server");
const elTooltipApi      = $("tooltip-api");
const elBtnRestart      = $("btn-restart");
const elBtnToken        = $("btn-token");
const elBtnQuit         = $("btn-quit");
const elQueryInput      = $("query-input");
const elSelectLimit     = $("select-limit");
const elBtnRun          = $("btn-run");
const elClarifyPanel    = $("clarify-panel");
const elClarifyQuestion = $("clarify-question");
const elClarifyInput    = $("clarify-input");
const elBtnClarify      = $("btn-clarify-submit");
const elResultPanel     = $("result-panel");
const elResultContent   = $("result-content");
const elResultBadge     = $("result-tool-badge");
const elResultCount     = $("result-count");
const elBtnExportJson   = $("btn-export-json");
const elBtnExportCsv    = $("btn-export-csv");
const elBtnWorkflow     = $("btn-workflow");
const elModalToken      = $("modal-token");
const elConfigOrgUrl    = $("config-org-url");
const elConfigClientId  = $("config-client-id");
const elConfigScopes    = $("config-scopes");
const elBtnTokenCancel  = $("btn-token-cancel");
const elBtnTokenSave    = $("btn-token-save");
const elModalWorkflow   = $("modal-workflow");
const elWorkflowUrl     = $("workflow-url-input");
const elWfAllCount      = $("wf-all-count");
const elWfSelectedCount = $("wf-selected-count");
const elWfRadioSelected = $("wf-radio-selected");
const elBtnWfCancel     = $("btn-workflow-cancel");
const elBtnWfSend       = $("btn-workflow-send");
const elWorkflowStatus  = $("workflow-status");

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function timestamp() {
  return new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15);
}

function fmtTime(ts) {
  if (!ts) return "—";
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function setIndicator(el, tooltipEl, state, message) {
  el.className = `indicator ${state}`;
  tooltipEl.textContent = `${message} · ${new Date().toLocaleTimeString()}`;
}

function setQueryDisabled(disabled) {
  elQueryInput.disabled = disabled;
  elSelectLimit.disabled = disabled;
  elBtnRun.disabled = disabled;
  document.querySelectorAll(".chip").forEach(c => c.disabled = disabled);
}

// ---------------------------------------------------------------------------
// Health checks (event-driven — no polling)
// ---------------------------------------------------------------------------

async function checkServer() {
  setIndicator(elIndServer, elTooltipServer, "grey", "Checking…");
  try {
    const [apfelRes, procRes] = await Promise.all([
      fetch(APFEL_HEALTH, { signal: AbortSignal.timeout(4000) }),
      fetch("/server-status", { signal: AbortSignal.timeout(4000) }),
    ]);
    const apfelJson = await apfelRes.json().catch(() => ({}));
    const procJson  = await procRes.json().catch(() => ({}));
    const apfelOk   = apfelRes.ok && apfelJson.status === "ok";
    const procOk    = procJson.apfel === true;

    if (apfelOk && procOk) {
      setIndicator(elIndServer, elTooltipServer, "green", "apfel running · MCP connected");
    } else {
      const reason = !procOk ? "apfel process not running" : "apfel health check failed";
      setIndicator(elIndServer, elTooltipServer, "red", reason);
    }
  } catch {
    setIndicator(elIndServer, elTooltipServer, "red", "Could not reach apfel");
  }
}

async function checkApi() {
  setIndicator(elIndApi, elTooltipApi, "grey", "Checking…");
  try {
    const res = await fetch("/api-status", { signal: AbortSignal.timeout(4000) });
    if (!res.ok) {
      setIndicator(elIndApi, elTooltipApi, "red", `Server error ${res.status}`);
      setTokenButtonState("error");
      return;
    }
    const body = await res.json();
    if (body.configured) {
      setIndicator(elIndApi, elTooltipApi, "green", `OAuth configured · ${body.org_url}`);
      setTokenButtonState("active");
    } else {
      setIndicator(elIndApi, elTooltipApi, "amber", "Credentials not configured — use Configure Okta OAuth");
      setTokenButtonState("unset");
    }
  } catch {
    setIndicator(elIndApi, elTooltipApi, "red", "Could not reach server");
    setTokenButtonState("error");
  }
}

function runHealthChecks() {
  checkServer();
  checkApi();
}

// ---------------------------------------------------------------------------
// Token button state
// ---------------------------------------------------------------------------

function setTokenButtonState(s) {
  elBtnToken.className = `btn btn-token state-${s}`;
  if (s === "active") {
    elBtnToken.textContent = "✓ Token active";
  } else if (s === "error") {
    elBtnToken.textContent = "⚠ Re-enter token";
  } else {
    elBtnToken.textContent = "Set Token";
  }
}

// ---------------------------------------------------------------------------
// Query execution
// ---------------------------------------------------------------------------

function handleApfelContent(content) {
  if (!content) {
    showError("Empty response from apfel.");
    return;
  }

  if (content.startsWith("CLARIFY:")) {
    const question = content.replace(/^CLARIFY:\s*/i, "").trim();
    state.pendingQuery = state.pendingQuery ?? elQueryInput.value;
    showClarify(question);
    hideResultPanel();
    return;
  }

  let parsed;
  try {
    const clean = content.replace(/^```json\s*/i, "").replace(/```$/, "").trim();
    parsed = JSON.parse(clean);
  } catch {
    showError("Could not parse response from apfel. Raw output: " + content.slice(0, 200));
    return;
  }

  state.lastResult = parsed;
  state.selectedRows.clear();
  renderResults(parsed);
}

async function runQuery(queryText) {
  if (!queryText.trim()) return;

  hideClarify();
  showLoading();
  setQueryDisabled(true);

  const limit  = parseInt(elSelectLimit.value, 10);
  const prompt = `${queryText} [limit=${limit}]`;

  try {
    const res = await fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal: AbortSignal.timeout(65000),
    });

    if (!res.ok) {
      showError(`Server error ${res.status}`);
      if (res.status >= 500) checkServer();
      return;
    }

    const body    = await res.json();
    const content = body?.content ?? "";
    handleApfelContent(content);

  } catch (err) {
    if (err.name === "TimeoutError") {
      showError("Query timed out (60s). Try a narrower query or check the Server indicator.");
    } else {
      showError("Connection error: " + err.message);
      checkServer();
    }
  } finally {
    setQueryDisabled(false);
  }
}

// ---------------------------------------------------------------------------
// Clarify flow
// ---------------------------------------------------------------------------

function showClarify(question) {
  elClarifyQuestion.textContent = question;
  elClarifyInput.value = "";

  // Hide the input/submit for error messages — user just needs to read them
  const isError = /^\d{3}\s/.test(question);  // starts with a status code like "403 "
  elClarifyInput.style.display  = isError ? "none" : "";
  elBtnClarify.style.display    = isError ? "none" : "";

  elClarifyPanel.classList.add("visible");
  if (!isError) elClarifyInput.focus();
}

function hideClarify() {
  elClarifyPanel.classList.remove("visible");
  elClarifyInput.value = "";
  elClarifyInput.style.display = "";
  elBtnClarify.style.display   = "";
  state.pendingQuery = null;
}

elBtnClarify.addEventListener("click", () => {
  const answer = elClarifyInput.value.trim();
  if (!answer || !state.pendingQuery) return;
  const combined = `${state.pendingQuery} — ${answer}`;
  elQueryInput.value = combined;
  hideClarify();
  runQuery(combined);
});

elClarifyInput.addEventListener("keydown", e => {
  if (e.key === "Enter") elBtnClarify.click();
});

// ---------------------------------------------------------------------------
// Result rendering
// ---------------------------------------------------------------------------

function showLoading() {
  elResultPanel.classList.add("visible");
  elResultBadge.textContent = "—";
  elResultCount.textContent = "";
  elResultContent.innerHTML = `<div class="state-placeholder"><span class="spinner"></span>Running…</div>`;
}

function showError(msg) {
  elResultPanel.classList.add("visible");
  elResultBadge.textContent = "error";
  elResultCount.textContent = "";
  elResultContent.innerHTML = `<div class="state-placeholder" style="color:var(--color-danger-text)">${escapeHtml(msg)}</div>`;
}

function hideResultPanel() {
  elResultPanel.classList.remove("visible");
}

// ---------------------------------------------------------------------------
// Per-tool column schemas
// ---------------------------------------------------------------------------
const TOOL_SCHEMAS = {
  list_users: [
    { key: "name",        label: "Name",        get: r => r.displayName ?? (r.firstName && r.lastName ? `${r.firstName} ${r.lastName}` : r.firstName ?? r.lastName ?? "—") },
    { key: "login",       label: "Email",       get: r => r.login ?? r.email },
    { key: "status",      label: "Status",      get: r => r.status,      render: "status" },
    { key: "created",     label: "Created",     get: r => r.created,     render: "date"   },
    { key: "lastLogin",   label: "Last Login",  get: r => r.lastLogin,   render: "date"   },
    { key: "id",          label: "ID",          get: r => r.id },
  ],
  list_group_users: [
    { key: "name",        label: "Name",        get: r => r.displayName ?? (r.firstName && r.lastName ? `${r.firstName} ${r.lastName}` : r.firstName ?? r.lastName ?? "—") },
    { key: "login",       label: "Email",       get: r => r.login ?? r.email },
    { key: "status",      label: "Status",      get: r => r.status,      render: "status" },
    { key: "created",     label: "Created",     get: r => r.created,     render: "date"   },
    { key: "id",          label: "ID",          get: r => r.id },
  ],
  list_groups: [
    { key: "name",        label: "Group Name",  get: r => r.profile?.name ?? r.name },
    { key: "description", label: "Description", get: r => r.profile?.description ?? r.description },
    { key: "type",        label: "Type",        get: r => r.type },
    { key: "created",     label: "Created",     get: r => r.created,     render: "date"   },
    { key: "id",          label: "ID",          get: r => r.id },
  ],
  list_applications: [
    { key: "label",       label: "Application", get: r => r.label },
    { key: "name",        label: "App Type",    get: r => r.name },
    { key: "status",      label: "Status",      get: r => r.status,      render: "status" },
    { key: "signOnMode",  label: "Sign-On",     get: r => r.signOnMode },
    { key: "created",     label: "Created",     get: r => r.created,     render: "date"   },
    { key: "id",          label: "ID",          get: r => r.id },
  ],
  list_policies: [
    { key: "name",        label: "Policy Name", get: r => r.name },
    { key: "type",        label: "Type",        get: r => r.type },
    { key: "status",      label: "Status",      get: r => r.status,      render: "status" },
    { key: "priority",    label: "Priority",    get: r => r.priority },
    { key: "created",     label: "Created",     get: r => r.created,     render: "date"   },
    { key: "id",          label: "ID",          get: r => r.id },
  ],
};

function fmtKey(k) {
  return k.replace(/([A-Z])/g, " $1").replace(/^./, s => s.toUpperCase()).trim();
}

function renderCell(col, row) {
  const val = col.get ? col.get(row) : row[col.key];
  if (col.render === "status") return `<td>${statusPill(val)}</td>`;
  if (col.render === "date")   return `<td>${fmtTime(val)}</td>`;
  if (val === null || val === undefined) return `<td>—</td>`;
  if (typeof val === "object") return `<td class="cell-json">${escapeHtml(JSON.stringify(val))}</td>`;
  return `<td>${escapeHtml(String(val))}</td>`;
}

function renderResults(parsed) {
  const { tool_called, result_count, data } = parsed;

  elResultBadge.textContent = `tool: ${tool_called ?? "unknown"}`;
  elResultCount.textContent  = `${result_count ?? (data?.length ?? 0)} results`;

  if (!data || data.length === 0) {
    elResultContent.innerHTML = `<div class="state-placeholder">No results returned.</div>`;
    return;
  }

  const isLogTool = tool_called === "get_logs";

  if (isLogTool) {
    elResultContent.innerHTML = buildLogTable(data);
  } else {
    const schema = TOOL_SCHEMAS[tool_called];
    elResultContent.innerHTML = schema
      ? buildSchemaTable(schema, data)
      : buildGenericTable(data);
  }

  // Sort listeners
  elResultContent.querySelectorAll("th[data-col]").forEach(th => {
    th.addEventListener("click", () => onSortClick(th, data, isLogTool));
  });

  // Select-all checkbox
  const cbAll = elResultContent.querySelector("#cb-all");
  if (cbAll) {
    cbAll.addEventListener("change", () => {
      const checked = cbAll.checked;
      elResultContent.querySelectorAll(".cb-row").forEach((cb, i) => {
        cb.checked = checked;
        checked ? state.selectedRows.add(i) : state.selectedRows.delete(i);
      });
    });
  }

  // Row checkboxes
  elResultContent.querySelectorAll(".cb-row").forEach((cb, i) => {
    cb.addEventListener("change", () => {
      cb.checked ? state.selectedRows.add(i) : state.selectedRows.delete(i);
      if (cbAll) cbAll.checked = state.selectedRows.size === data.length;
    });
  });

  // Expandable log rows
  if (isLogTool) {
    elResultContent.querySelectorAll(".row-expandable").forEach(row => {
      row.addEventListener("click", () => {
        const detailRow = row.nextElementSibling;
        if (detailRow?.classList.contains("row-detail")) {
          detailRow.classList.toggle("open");
        }
      });
    });
  }
}

function buildSchemaTable(schema, data) {
  const headerCols = schema.map(col =>
    `<th data-col="${escapeAttr(col.key)}">${escapeHtml(col.label)}</th>`
  ).join("");

  const rows = data.map((row, i) => {
    const cells = schema.map(col => renderCell(col, row)).join("");
    return `<tr>
      <td class="cb-col"><input type="checkbox" class="cb-row" data-idx="${i}" /></td>
      ${cells}
    </tr>`;
  }).join("");

  return `
    <table class="result-table">
      <thead>
        <tr>
          <th class="cb-col"><input type="checkbox" id="cb-all" /></th>
          ${headerCols}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function buildGenericTable(data) {
  const keys = Object.keys(data[0]).filter(k => k !== "__raw");

  const headerCols = keys.map(k =>
    `<th data-col="${escapeAttr(k)}">${escapeHtml(fmtKey(k))}</th>`
  ).join("");

  const rows = data.map((row, i) => {
    const cells = keys.map(k => {
      const val = row[k];
      if (k === "status") return `<td>${statusPill(val)}</td>`;
      if (/date|time|created|updated|published|login/i.test(k) && typeof val === "string" && val.includes("T")) {
        return `<td>${fmtTime(val)}</td>`;
      }
      if (val === null || val === undefined) return `<td>—</td>`;
      if (typeof val === "object") return `<td class="cell-json">${escapeHtml(JSON.stringify(val))}</td>`;
      return `<td>${escapeHtml(String(val))}</td>`;
    }).join("");

    return `<tr>
      <td class="cb-col"><input type="checkbox" class="cb-row" data-idx="${i}" /></td>
      ${cells}
    </tr>`;
  }).join("");

  return `
    <table class="result-table">
      <thead>
        <tr>
          <th class="cb-col"><input type="checkbox" id="cb-all" /></th>
          ${headerCols}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function buildLogTable(data) {
  const rows = data.map((event, i) => {
    const actor     = event.actor?.displayName ?? event.actor?.alternateId ?? "—";
    const action    = event.displayMessage ?? event.eventType ?? "—";
    const outcome   = event.outcome?.result ?? "—";
    const published = fmtTime(event.published);
    const raw       = JSON.stringify(event, null, 2);

    return `
      <tr class="row-expandable">
        <td class="cb-col"><input type="checkbox" class="cb-row" data-idx="${i}" /></td>
        <td>${escapeHtml(published)}</td>
        <td>${escapeHtml(actor)}</td>
        <td>${escapeHtml(action)}</td>
        <td>${statusPill(outcome)}</td>
      </tr>
      <tr class="row-detail">
        <td colspan="5"><pre>${escapeHtml(raw)}</pre></td>
      </tr>`;
  }).join("");

  return `
    <table class="result-table">
      <thead>
        <tr>
          <th class="cb-col"><input type="checkbox" id="cb-all" /></th>
          <th data-col="published">Time</th>
          <th data-col="actor">Actor</th>
          <th data-col="displayMessage">Event</th>
          <th data-col="outcome">Outcome</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function statusPill(val) {
  if (!val) return "—";
  const cls = val.toLowerCase().replace(/_/g, "-");
  return `<span class="status-pill ${cls}">${escapeHtml(val)}</span>`;
}

// ---------------------------------------------------------------------------
// Client-side sort
// ---------------------------------------------------------------------------

function onSortClick(th, data, isLogTool) {
  const col = th.dataset.col;

  if (state.sortCol === col) {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  } else {
    state.sortCol = col;
    state.sortDir = "asc";
  }

  const sorted = [...data].sort((a, b) => {
    const av = String(a[col] ?? "");
    const bv = String(b[col] ?? "");
    return state.sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  const prevSelected = new Set(state.selectedRows);
  renderResults({ ...state.lastResult, data: sorted });
  state.selectedRows = prevSelected;

  th.classList.remove("sort-asc", "sort-desc");
  th.classList.add(`sort-${state.sortDir}`);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

function getExportData() {
  const data = state.lastResult?.data ?? [];
  if (state.selectedRows.size > 0) {
    return [...state.selectedRows].sort((a, b) => a - b).map(i => data[i]);
  }
  return data;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportJson() {
  if (!state.lastResult) return;
  const data = getExportData();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  triggerDownload(blob, `okta-export-${timestamp()}.json`);
}

function exportCsv() {
  const data = getExportData();
  if (!data.length) return;
  const headers = Object.keys(data[0]);
  const rows    = data.map(row =>
    headers.map(h => {
      const val  = row[h];
      const cell = typeof val === "object" ? JSON.stringify(val) : String(val ?? "");
      return `"${cell.replace(/"/g, '""')}"`;
    }).join(",")
  );
  const csv  = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  triggerDownload(blob, `okta-export-${timestamp()}.csv`);
}

elBtnExportJson.addEventListener("click", exportJson);
elBtnExportCsv.addEventListener("click",  exportCsv);

// ---------------------------------------------------------------------------
// Workflow modal
// ---------------------------------------------------------------------------

function openWorkflowModal() {
  const total    = state.lastResult?.data?.length ?? 0;
  const selected = state.selectedRows.size;

  elWfAllCount.textContent      = `(${total} records)`;
  elWfSelectedCount.textContent = `(${selected} selected)`;
  elWfRadioSelected.disabled    = selected === 0;

  if (selected === 0) {
    document.querySelector('input[name="wf-scope"][value="all"]').checked = true;
  }

  elWorkflowUrl.value = state.lastInvokeUrl;
  elWorkflowStatus.textContent = "";
  elWorkflowStatus.className   = "modal-status";
  validateWorkflowUrl();

  elModalWorkflow.classList.add("open");
  elWorkflowUrl.focus();
}

function closeWorkflowModal() {
  elModalWorkflow.classList.remove("open");
}

function validateWorkflowUrl() {
  const url = elWorkflowUrl.value.trim();
  elBtnWfSend.disabled = !url.startsWith("https://");
}

elWorkflowUrl.addEventListener("input", validateWorkflowUrl);
elBtnWorkflow.addEventListener("click", openWorkflowModal);
elBtnWfCancel.addEventListener("click", closeWorkflowModal);

elBtnWfSend.addEventListener("click", async () => {
  const invokeUrl = elWorkflowUrl.value.trim();
  const scope     = document.querySelector('input[name="wf-scope"]:checked')?.value ?? "all";
  const allData   = state.lastResult?.data ?? [];
  const sendData  = scope === "selected" && state.selectedRows.size > 0
    ? [...state.selectedRows].sort((a, b) => a - b).map(i => allData[i])
    : allData;

  const payload = {
    source: "okta-intelligence-dashboard",
    tool_called: state.lastResult?.tool_called ?? "unknown",
    result_count: sendData.length,
    exported_at: new Date().toISOString(),
    data: sendData,
  };

  state.lastInvokeUrl = invokeUrl;
  elBtnWfSend.disabled = true;
  elWorkflowStatus.textContent = "Sending…";
  elWorkflowStatus.className   = "modal-status";

  try {
    const res  = await fetch("/send-to-workflow", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invoke_url: invokeUrl, payload }),
    });
    const body = await res.json();

    if (body.status === "ok") {
      elWorkflowStatus.textContent = `✓ Sent — workflow responded ${body.http_code}`;
      elWorkflowStatus.className   = "modal-status ok";
    } else {
      elWorkflowStatus.textContent = `✗ ${body.message ?? "Unknown error"}`;
      elWorkflowStatus.className   = "modal-status error";
    }
  } catch {
    elWorkflowStatus.textContent = `✗ Could not reach the invoke URL`;
    elWorkflowStatus.className   = "modal-status error";
  } finally {
    elBtnWfSend.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// OAuth config modal
// ---------------------------------------------------------------------------

async function openTokenModal() {
  elModalToken.classList.add("open");
  try {
    const res = await fetch("/get-config");
    if (res.ok) {
      const cfg = await res.json();
      elConfigOrgUrl.value   = cfg.org_url   || "";
      elConfigClientId.value = cfg.client_id || "";
      elConfigScopes.value   = cfg.scopes    || "";
    }
  } catch { /* leave fields as-is */ }
  elConfigOrgUrl.focus();
}

function closeTokenModal() {
  elModalToken.classList.remove("open");
}

elBtnToken.addEventListener("click", openTokenModal);
elBtnTokenCancel.addEventListener("click", closeTokenModal);

elBtnTokenSave.addEventListener("click", async () => {
  const org_url   = elConfigOrgUrl.value.trim();
  const client_id = elConfigClientId.value.trim();
  const scopes    = elConfigScopes.value.trim();
  if (!org_url || !client_id) {
    elConfigOrgUrl.placeholder = "Required";
    elConfigClientId.placeholder = "Required";
    return;
  }

  try {
    const res = await fetch("/set-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ org_url, client_id, scopes }),
    });

    if (res.ok) {
      closeTokenModal();
      setTokenButtonState("active");
      checkApi();
    }
  } catch {
    elConfigOrgUrl.placeholder = "Failed to save — try again";
  }
});

elConfigScopes.addEventListener("keydown", e => {
  if (e.key === "Enter") elBtnTokenSave.click();
});

// Close modals on overlay click
elModalToken.addEventListener("click", e => {
  if (e.target === elModalToken) closeTokenModal();
});
elModalWorkflow.addEventListener("click", e => {
  if (e.target === elModalWorkflow) closeWorkflowModal();
});

// ---------------------------------------------------------------------------
// Restart
// ---------------------------------------------------------------------------

elBtnRestart.addEventListener("click", async () => {
  elBtnRestart.disabled = true;
  setQueryDisabled(true);
  setIndicator(elIndServer, elTooltipServer, "amber", "Restarting…");
  setIndicator(elIndApi,    elTooltipApi,    "amber", "Restarting…");

  try {
    await fetch("/restart", { method: "POST" });
  } catch { /* server may not respond immediately */ }

  // Poll /server-status until apfel is back (max 30s)
  const start   = Date.now();
  const timeout = 30_000;

  while (Date.now() - start < timeout) {
    await sleep(500);
    try {
      const res  = await fetch("/server-status");
      const body = await res.json();
      if (body.apfel === true) break;
    } catch { /* keep polling */ }
  }

  hideResultPanel();
  setQueryDisabled(false);
  elBtnRestart.disabled = false;
  runHealthChecks();
});

// ---------------------------------------------------------------------------
// Quit
// ---------------------------------------------------------------------------

elBtnQuit.addEventListener("click", async () => {
  try { await fetch("/quit", { method: "POST" }); } catch { /* expected */ }
  document.body.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:var(--font-sans);color:var(--color-text-tertiary);font-size:13px;">Server stopped. Close this tab.</div>`;
});

// ---------------------------------------------------------------------------
// Time range
// ---------------------------------------------------------------------------

document.querySelectorAll(".btn-time").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".btn-time").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.activeRange = btn.dataset.range;
  });
});

// ---------------------------------------------------------------------------
// Template chips
// ---------------------------------------------------------------------------

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    const prompt = chip.dataset.prompt;
    if (!prompt) return;
    elQueryInput.value = prompt;
    runQuery(prompt);
  });
});

// ---------------------------------------------------------------------------
// Run button / Enter key
// ---------------------------------------------------------------------------

elBtnRun.addEventListener("click", () => runQuery(elQueryInput.value));

elQueryInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    runQuery(elQueryInput.value);
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return String(str).replace(/"/g, "&quot;");
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Init — run health checks on page load
// ---------------------------------------------------------------------------

runHealthChecks();

// Logo — show icon if logo.png is present, otherwise text only
fetch("logo.png", { method: "HEAD" })
  .then(res => {
    if (res.ok) {
      const img        = document.createElement("img");
      img.src          = "logo.png";
      img.alt          = "";
      img.width        = 14;
      img.height       = 14;
      img.style.flexShrink = "0";
      document.querySelector(".header-logo").prepend(img);
    }
  })
  .catch(() => {});