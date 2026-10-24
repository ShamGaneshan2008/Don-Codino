import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../app/static/app.js", import.meta.url), "utf8");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((accept, fail) => {
    resolve = accept;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function response(data, ok = true) {
  return { ok, status: ok ? 200 : 502, json: async () => data };
}

function element() {
  const listeners = new Map();
  const classes = new Set();
  return {
    value: "",
    checked: false,
    disabled: false,
    hidden: false,
    textContent: "",
    children: [],
    classList: {
      add: (...values) => values.forEach((value) => classes.add(value)),
      remove: (...values) => values.forEach((value) => classes.delete(value)),
      toggle: (value, enabled) => (enabled ? classes.add(value) : classes.delete(value)),
    },
    addEventListener: (name, listener) => listeners.set(name, listener),
    dispatch: (name, event = {}) => listeners.get(name)(event),
    append(...children) {
      this.children.push(...children);
    },
    replaceChildren() {
      this.children = [];
    },
    scrollIntoView() {},
  };
}

function contract(id, status = "BLOCKED") {
  return {
    id,
    status,
    message: "Test contract",
    stage: status === "RUNNING" ? 2 : 5,
    verification: { status: "NOT RUN" },
    exit_code: null,
    changed_files: [],
    workspace: "calculator",
    request: "Build calculator",
    prompt: "Approved plan",
  };
}

async function dashboard() {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  get("pipeline").children = Array.from({ length: 6 }, () => {
    const row = element();
    const state = element();
    row.querySelector = () => state;
    return row;
  });
  const sources = [];
  const context = vm.createContext({
    document: { getElementById: get, querySelectorAll: () => [], createElement: element },
    fetch: async (path) => {
      if (path === "/api/tasks?limit=100") return response([]);
      if (path === "/api/settings")
        return response({
          workspaces: [],
          workspace_root: "workspaces",
          verification: { message: "blocked" },
          codex: { available: false, message: "Not logged in" },
          prompt_mode: "template",
        });
      throw new Error(`Unexpected request: ${path}`);
    },
    EventSource: class {
      constructor(url) {
        this.url = url;
        sources.push(this);
      }
      close() {
        this.closed = true;
      }
      addEventListener() {}
    },
  });
  vm.runInContext(source, context);
  await new Promise(setImmediate);
  return { context, get, sources };
}

test("refinement locks the approved inputs and clears the previous approval", async () => {
  const { context, get } = await dashboard();
  const pending = deferred();
  context.fetch = () => pending.promise;
  get("request").value = "Build calculator";
  get("workspace").value = "calculator";
  get("prompt").value = "Previous plan";
  get("approval").checked = true;
  const operation = get("contract-form").dispatch("submit", { preventDefault() {} });
  for (const id of ["request", "workspace", "prompt", "approval"]) {
    assert.equal(get(id).disabled, true);
  }
  assert.equal(get("approval").checked, false);
  assert.equal(get("prompt").value, "");
  pending.resolve(response({ mode: "template", prompt: "Refined plan" }));
  await operation;
  assert.equal(get("request").disabled, false);
  assert.equal(get("prompt").value, "Refined plan");
  assert.equal(get("execute").disabled, true);
});

test("refinement failure cannot leave an old plan approved", async () => {
  const { context, get } = await dashboard();
  context.fetch = async () => response({ detail: "Refinement failed" }, false);
  get("approval").checked = true;
  get("prompt").value = "Old plan";
  await get("contract-form").dispatch("submit", { preventDefault() {} });
  assert.equal(get("approval").checked, false);
  assert.equal(get("plan-panel").hidden, true);
  assert.equal(get("execute").disabled, true);
  assert.equal(get("notice").textContent, "Refinement failed");
});

test("a late selection response cannot replace the current event stream", async () => {
  const { context, sources } = await dashboard();
  const pending = deferred();
  context.fetch = (path) =>
    path.endsWith("/older") ? pending.promise : Promise.resolve(response(contract("newer")));
  const older = context.selectTask("older");
  await context.selectTask("newer");
  pending.resolve(response(contract("older")));
  await older;
  assert.equal(sources.length, 1);
  assert.equal(sources[0].url, "/api/tasks/newer/events");
});

test("an older detail response cannot overwrite a newer verdict", async () => {
  const { context, get } = await dashboard();
  context.fetch = async () => response(contract("current"));
  await context.selectTask("current");
  const pending = deferred();
  context.fetch = () => pending.promise;
  const older = context.refreshTask("current");
  context.fetch = async () => response(contract("current", "PASS"));
  await context.refreshTask("current");
  pending.resolve(response(contract("current", "RUNNING")));
  await older;
  assert.match(get("operation-state").textContent, /^PASS/);
});
