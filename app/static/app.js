"use strict";

const $ = (id) => document.getElementById(id);
let selectedTask = null;
let eventSource = null;
let settings = null;
let logText = "";
let busy = false;
let selectionVersion = 0;
let detailVersion = 0;
let currentPlan = null;
const eventIds = new Set();

function notify(message) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

function resetApproval() {
  $("approval").checked = false;
  $("execute").disabled = true;
}

function invalidatePlan() {
  currentPlan = null;
  resetApproval();
  $("plan-panel").hidden = true;
  $("prompt").value = "";
  $("context-preview").textContent = "Repository context will appear after refinement.";
}

function setBusy(value) {
  busy = value;
  for (const id of ["request", "workspace", "prompt", "approval"]) {
    $(id).disabled = value;
  }
  $("refine").disabled = value;
  $("execute").disabled = value || !$("approval").checked;
}

function renderTask(task) {
  $("operation-state").textContent =
    `${task.execution?.state || task.status} · ${task.id.slice(0, 8)}`;
  $("task-message").textContent =
    `${task.message || "The family is handling your request."}\nCodex exit: ${task.exit_code ?? "NOT RUN"} · Verification: ${task.verification.status}`;
  $("cancel").hidden = task.status !== "RUNNING";
  $("diff").textContent = task.changed_files.length
    ? `${task.changed_files.join("\n")}\n\n${task.diff || "No tracked diff available."}`
    : "No changed files recorded.";
  $("approved-plan").textContent =
    `${task.workspace}\n\nOriginal request\n${task.request}\n\nApproved plan\n${task.prompt}`;
  $("verification").textContent = JSON.stringify(task.verification, null, 2);
  const executionReached = task.exit_code !== null || task.stage === 2;
  const verificationReached = task.verification.status !== "NOT RUN" || task.stage === 3;
  [...$("pipeline").children].forEach((row, index) => {
    row.classList.remove("current", "completed", "failed");
    const state = row.querySelector(".step-state");
    const reached =
      index < 2 || index > 3 || (index === 2 ? executionReached : verificationReached);
    if (!reached) {
      state.textContent = "—";
      return;
    }
    if (index === task.stage) {
      row.classList.add("current");
      state.textContent = task.status === "RUNNING" ? "●" : task.status;
    } else if (index < task.stage) {
      const failedExecution = index === 2 && task.exit_code !== null && task.exit_code !== 0;
      const incompleteVerification = index === 3 && task.verification.status !== "PASS";
      row.classList.add(failedExecution || incompleteVerification ? "failed" : "completed");
      state.textContent = failedExecution
        ? "FAIL"
        : incompleteVerification
          ? task.verification.status
          : "✓";
    } else {
      state.textContent = "—";
    }
  });
}

async function refreshTask(taskId = selectedTask) {
  if (!taskId) return;
  const version = ++detailVersion;
  const task = await api(`/api/tasks/${taskId}`);
  if (selectedTask === taskId && version === detailVersion) renderTask(task);
  if (selectedTask === taskId && version === detailVersion && task.execution) {
    $("execution-record").textContent = JSON.stringify(task.execution, null, 2);
  }
}

async function selectTask(taskId) {
  const version = ++selectionVersion;
  if (eventSource) eventSource.close();
  eventSource = null;
  selectedTask = taskId;
  eventIds.clear();
  logText = "";
  $("logs").textContent = "Waiting for process events…";
  await refreshTask(taskId);
  if (version !== selectionVersion) return;
  const source = new EventSource(`/api/tasks/${taskId}/events`);
  eventSource = source;
  source.onmessage = (event) => {
    if (version !== selectionVersion || eventIds.has(event.lastEventId)) return;
    eventIds.add(event.lastEventId);
    const data = JSON.parse(event.data);
    logText += `[${new Date(data.created_at).toLocaleTimeString()}] ${data.kind.toUpperCase()}  ${data.message}\n`;
    logText = logText.slice(-256000);
    $("logs").textContent = logText;
    $("logs").scrollTop = $("logs").scrollHeight;
    if (data.kind === "stage" || data.kind === "state")
      refreshTask(taskId).catch((error) => notify(error.message));
  };
  source.addEventListener("done", async () => {
    source.close();
    if (version === selectionVersion) {
      try {
        await refreshTask(taskId);
        await loadHistory();
      } catch (error) {
        notify(error.message);
      }
    }
  });
  source.onerror = () => {
    if (version === selectionVersion)
      $("operation-state").textContent = "Event connection interrupted; reconnecting…";
  };
}

async function loadHistory() {
  const tasks = await api("/api/tasks?limit=100");
  $("total").textContent = tasks.length === 100 ? "100+" : tasks.length;
  $("passed").textContent = tasks.filter((task) => task.status === "PASS").length;
  $("running").textContent = tasks.filter((task) => task.status === "RUNNING").length;
  const tbody = $("history-body");
  tbody.replaceChildren();
  if (!tasks.length) {
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty-state";
    cell.textContent = "A clean ledger. Your first contract starts above.";
    const row = document.createElement("tr");
    row.append(cell);
    tbody.append(row);
  }
  for (const task of tasks) {
    const row = document.createElement("tr");
    const values = [
      task.request.slice(0, 90),
      task.workspace.split(/[\\/]/).pop(),
      new Date(task.started_at).toLocaleString(),
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `status ${task.status}`;
    status.textContent = task.status;
    statusCell.append(status);
    row.append(statusCell);
    const openCell = document.createElement("td");
    const open = document.createElement("button");
    open.type = "button";
    open.className = "text-button history-open";
    open.textContent = "INSPECT ↗";
    open.addEventListener("click", () => {
      selectTask(task.id).catch((error) => notify(error.message));
      $("evidence").scrollIntoView();
    });
    openCell.append(open);
    row.append(openCell);
    tbody.append(row);
  }
}

$("contract-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  invalidatePlan();
  setBusy(true);
  notify("The Consigliere is preparing the plan.");
  try {
    const data = await api("/api/prompts/enhance", {
      request: $("request").value,
      workspace: $("workspace").value,
    });
    $("prompt").value = data.prompt;
    currentPlan = data.plan_id
      ? { id: data.plan_id, revision: data.revision, prompt: data.prompt, approved: false }
      : null;
    $("context-preview").textContent = data.context
      ? JSON.stringify({ structured_plan: data.structured, context: data.context }, null, 2)
      : "No repository context supplied by this server.";
    $("plan-panel").hidden = false;
    $("mode").textContent = `${data.mode.toUpperCase()} MODE`;
    resetApproval();
    notify(
      data.mode === "template"
        ? "Plan saved. Template mode uses repository symbols and fixed constraints; no AI model was used."
        : "AI-refined plan ready. Review and edit it before approval.",
    );
  } catch (error) {
    notify(error.message);
  } finally {
    setBusy(false);
  }
});

$("request").addEventListener("input", invalidatePlan);
$("workspace").addEventListener("change", invalidatePlan);
$("prompt").addEventListener("input", resetApproval);
$("approval").addEventListener("change", () => {
  $("execute").disabled = busy || !$("approval").checked;
});
$("execute").addEventListener("click", async () => {
  if (busy || !$("approval").checked || !$("prompt").value.trim()) return;
  setBusy(true);
  try {
    if (currentPlan?.executed) throw new Error("Refine a new plan before another execution.");
    let task;
    if (currentPlan) {
      if ($("prompt").value !== currentPlan.prompt) {
        const revision = await api(`/api/v1/plans/${currentPlan.id}/revisions`, {
          revision: currentPlan.revision,
          prompt: $("prompt").value,
        });
        currentPlan.revision = revision.revision;
        currentPlan.prompt = revision.prompt;
        currentPlan.approved = false;
      }
      if (!currentPlan.approved) {
        await api(`/api/v1/plans/${currentPlan.id}/approve`, {
          revision: currentPlan.revision,
          approved: true,
        });
        currentPlan.approved = true;
      }
      task = await api(`/api/v1/plans/${currentPlan.id}/execute`, {
        revision: currentPlan.revision,
        approved: true,
        max_repairs: $("allow-repair").checked ? 2 : 0,
      });
      currentPlan.executed = true;
    } else {
      task = await api("/api/tasks", {
        request: $("request").value,
        workspace: $("workspace").value,
        prompt: $("prompt").value,
        approved: true,
      });
    }
    resetApproval();
    notify("The family is handling your request.");
    await selectTask(task.id);
    await loadHistory();
  } catch (error) {
    notify(error.message);
  } finally {
    setBusy(false);
  }
});
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("prompt").value);
    notify("The plan is copied.");
  } catch {
    $("prompt").focus();
    $("prompt").select();
    notify("Clipboard unavailable. The plan is selected; use Ctrl+C to copy.");
  }
});
$("cancel").addEventListener("click", async () => {
  if (!selectedTask) return;
  try {
    const result = await api(`/api/tasks/${selectedTask}/cancel`, {});
    notify(
      result.cancellation_requested
        ? "Cancellation requested. Partial changes will be preserved for review."
        : "This contract has already ended.",
    );
  } catch (error) {
    notify(error.message);
  }
});
$("refresh").addEventListener("click", () => loadHistory().catch((error) => notify(error.message)));
$("load-memory").addEventListener("click", async () => {
  try {
    if (!$("workspace").value) throw new Error("Select an approved workspace first.");
    const result = await api(
      `/api/v1/memory?selection=${encodeURIComponent($("workspace").value)}`,
    );
    $("memory-records").textContent = result.items.length
      ? JSON.stringify(result.items, null, 2)
      : "No current verified outcomes for this repository and dependency fingerprint.";
  } catch (error) {
    notify(error.message);
  }
});
document.querySelectorAll("[data-tab]").forEach((button) =>
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((other) => {
      const active = other === button;
      other.classList.toggle("selected", active);
      other.setAttribute("aria-selected", String(active));
      $(other.dataset.tab).hidden = !active;
    });
  }),
);
document.querySelectorAll("nav a").forEach((link) =>
  link.addEventListener("click", () => {
    document
      .querySelectorAll("nav a")
      .forEach((other) => other.classList.toggle("active", other === link));
  }),
);

async function loadWorkspaces() {
  const discovery = await api("/api/workspaces");
  $("root").textContent = discovery.workspace_root;
  for (const option of [...$("workspace").children].slice(1)) option.remove();
  for (const workspace of discovery.workspaces) {
    const option = document.createElement("option");
    option.value = workspace.path;
    option.textContent = workspace.name;
    $("workspace").append(option);
  }
  if (!discovery.workspaces.length)
    notify(
      `No approved Git workspaces found in ${discovery.workspace_root}. Initialize a direct child folder with git init, then reload this page.`,
    );
}

async function boot() {
  $("date").textContent = new Date()
    .toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
    .toUpperCase();
  await loadWorkspaces();
  await loadHistory();
  settings = await api("/api/settings");
  $("root").textContent = settings.workspace_root;
  $("isolation").textContent = settings.verification.message;
  $("codex-status").textContent = settings.codex.available ? "Available" : "Unavailable";
  $("codex-detail").textContent = settings.codex.message;
  $("mode").textContent = `${settings.prompt_mode.toUpperCase()} MODE`;
  if (settings.workspaces.length && !settings.codex.available)
    notify(
      `Our associate Codex is unavailable. ${settings.codex.message} You can still refine and copy a plan.`,
    );
}
boot().catch((error) => notify(`The office could not connect to the backend: ${error.message}`));
