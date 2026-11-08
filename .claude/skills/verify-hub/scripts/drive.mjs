#!/usr/bin/env node
// Drives the panel of a hubctl run in its own headless Chrome and records evidence.
//
//   node drive.mjs [--run ID] [--keep-going] <journey.mjs>
//
// A journey exports `default async (t) => {}`. Every action goes through real CDP input events,
// so clicks and keys reach the page the way a user's would. Evidence goes to the run's evidence dir:
// journal.txt (every step and check), <name>.png and <name>.aria.txt.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const argv = process.argv.slice(2);
const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv.splice(i, 2)[1] : undefined; };
const run = opt("--run") || process.env.VERIFY_HUB_RUN || only();
const keepGoing = argv.includes("--keep-going") && argv.splice(argv.indexOf("--keep-going"), 1);
const journey = argv[0];
if (!journey) die("usage: node drive.mjs [--run ID] [--keep-going] <journey.mjs>");

function only() {
  const runs = fs.existsSync("/tmp/verify-hub") ? fs.readdirSync("/tmp/verify-hub").filter((d) => d.startsWith("run-")) : [];
  if (runs.length !== 1) die("drive: pass --run, one of: " + (runs.map((d) => d.slice(4)).join(", ") || "(none; run hubctl.py up)"));
  return runs[0].slice(4);
}
function die(msg) { console.error(msg); process.exit(2); }

const runDir = "/tmp/verify-hub/run-" + run;
const state = JSON.parse(fs.readFileSync(path.join(runDir, "state.json"), "utf8"));
const evidence = path.join(state.evidence, path.basename(journey, path.extname(journey)) + "-" + new Date().toISOString().slice(11, 19).replace(/:/g, ""));
fs.mkdirSync(evidence, { recursive: true });
const journalPath = path.join(evidence, "journal.txt");
const note = (line) => { console.log(line); fs.appendFileSync(journalPath, new Date().toISOString() + " " + line + "\n"); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = path.join(runDir, "chrome-profile");
const chrome = spawn("google-chrome", ["--headless=new", "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check", "--password-store=basic",
  "--user-data-dir=" + profile, "--window-size=1280,800", "about:blank"],
  { stdio: "ignore", detached: true, env: { ...process.env, VERIFY_HUB_RUN: run } });
fs.writeFileSync(path.join(runDir, "chrome.pid"), String(chrome.pid));

let wsUrl;
for (let i = 0; i < 100 && !wsUrl; i++) {
  try {
    const [port] = fs.readFileSync(path.join(profile, "DevToolsActivePort"), "utf8").split("\n");
    const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    wsUrl = list.find((t) => t.type === "page")?.webSocketDebuggerUrl;
  } catch { await sleep(100); }
}
if (!wsUrl) die("drive: Chrome did not open a DevTools port");
const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0;
const pending = new Map(), consoleErrors = [];
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
  if (d.method === "Runtime.exceptionThrown") consoleErrors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === "Log.entryAdded" && d.params.entry.level === "error") consoleErrors.push(d.params.entry.text);
  if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") consoleErrors.push(JSON.stringify(d.params.args.map((a) => a.value)));
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq;
  const timer = setTimeout(() => { pending.delete(id); reject(new Error(method + ": no answer from Chrome in 15 s")); }, 15000);
  pending.set(id, (d) => { clearTimeout(timer); d.error ? reject(new Error(method + ": " + d.error.message)) : resolve(d.result); });
  ws.send(JSON.stringify({ id, method, params }));
});
for (const domain of ["Runtime", "Log", "Page"]) await send(domain + ".enable");

const KEYS = { Tab: 9, Enter: 13, Escape: 27, ArrowDown: 40, ArrowUp: 38, " ": 32 };
let fails = 0;
const t = {
  base: state.url.replace(/\/$/, ""),
  sleep,
  note,
  async ev(expr) {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("ev(" + expr + "): " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  },
  async nav(target) {
    const url = /^https?:/.test(target) ? target : t.base + "/" + target.replace(/^\//, "");
    await send("Page.navigate", { url: "about:blank" });
    await send("Page.navigate", { url });
    await t.waitFor("document.readyState === 'complete' && !!document.getElementById('summary')?.textContent");
    note("nav " + url);
  },
  async waitFor(expr, ms = 8000) {
    const end = Date.now() + ms;
    while (Date.now() < end) { if (await t.ev(expr).catch(() => false)) return true; await sleep(100); }
    throw new Error("waitFor timed out: " + expr);
  },
  async click(selector, text) {
    const box = await t.ev(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})]
        .find((e) => ${JSON.stringify(text ?? null)} === null || e.textContent.trim() === ${JSON.stringify(text ?? "")});
      if (!el) return null;
      el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    if (!box) throw new Error("click: no element matches " + selector + (text === undefined ? "" : " with text " + JSON.stringify(text)));
    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: type === "mouseMoved" ? 0 : 1 });
    }
    await sleep(150);
    note("click " + selector + (text === undefined ? "" : " " + JSON.stringify(text)));
  },
  async clickAt(x, y) {
    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: type === "mouseMoved" ? 0 : 1 });
    }
    await sleep(150);
    note("click at " + x + "," + y);
  },
  async press(key) {
    const code = KEYS[key];
    const text = key === "Enter" ? "\r" : key.length === 1 ? key : undefined;
    await send("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key, code: key, windowsVirtualKeyCode: code, text });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key, code: key, windowsVirtualKeyCode: code });
    await sleep(120);
    note("press " + key);
  },
  async type(selector, text) {
    await t.click(selector);
    await t.ev(`document.querySelector(${JSON.stringify(selector)}).select?.()`);
    await send("Input.insertText", { text });
    await sleep(150);
    note("type " + JSON.stringify(text) + " into " + selector);
  },
  async select(selector, value) {
    const sel = JSON.stringify(selector);
    await t.ev(`document.querySelector(${sel}).focus()`);
    for (let i = 0; i < 50 && (await t.ev(`document.querySelector(${sel}).selectedIndex`)) > 0; i++) await t.press("ArrowUp");
    for (let i = 0; i < 50 && (await t.ev(`document.querySelector(${sel}).value`)) !== value; i++) await t.press("ArrowDown");
    if ((await t.ev(`document.querySelector(${sel}).value`)) !== value) throw new Error("select: no option " + value + " in " + selector);
    note("select " + JSON.stringify(value) + " in " + selector);
  },
  async size(width, height) {
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await sleep(200);
    note("viewport " + width + "x" + height);
  },
  async back() { await send("Runtime.evaluate", { expression: "history.back()" }); await sleep(300); note("back"); },
  async forward() { await send("Runtime.evaluate", { expression: "history.forward()" }); await sleep(300); note("forward"); },
  async shot(name) {
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(evidence, name + ".png"), Buffer.from(r.data, "base64"));
    note("screenshot " + path.join(evidence, name + ".png"));
  },
  async aria(name) {
    const { nodes } = await send("Accessibility.getFullAXTree");
    const kids = new Map(nodes.map((n) => [n.nodeId, n]));
    const lines = [];
    const walk = (n, depth) => {
      const role = n.role?.value, label = n.name?.value;
      const shown = !n.ignored && role && !["generic", "none", "InlineTextBox", "StaticText", "LineBreak"].includes(role);
      if (shown) lines.push("  ".repeat(depth) + role + (label ? ' "' + label + '"' : "") +
        (n.properties || []).filter((p) => ["expanded", "focused", "selected"].includes(p.name)).map((p) => " [" + p.name + "=" + p.value.value + "]").join(""));
      for (const c of n.childIds || []) if (kids.has(c)) walk(kids.get(c), depth + (shown ? 1 : 0));
    };
    walk(nodes[0], 0);
    fs.writeFileSync(path.join(evidence, name + ".aria.txt"), lines.join("\n") + "\n");
    note("aria snapshot " + path.join(evidence, name + ".aria.txt"));
  },
  check(name, ok, detail) {
    if (!ok) fails++;
    note((ok ? "OK    " : "FAIL  ") + name + (ok || detail === undefined ? "" : "  " + JSON.stringify(detail)));
    if (!ok && !keepGoing) throw new Error("check failed: " + name);
  },
};

note(`journey ${journey} run=${run} url=${state.url} mode=${state.mode}`);
let crashed = false;
try {
  await t.size(1280, 800);
  await (await import(pathToFileURL(path.resolve(journey)).href)).default(t);
} catch (e) {
  crashed = true;
  note("ERROR " + e.message);
  await t.shot("failure").catch(() => {});
}
if (consoleErrors.length) fails++;
note((consoleErrors.length ? "FAIL  " : "OK    ") + "no console or CSP errors" + (consoleErrors.length ? "  " + JSON.stringify(consoleErrors) : ""));
note(crashed || fails ? "RESULT fail (" + fails + " failed checks)" : "RESULT pass");
ws.close();
try { process.kill(-chrome.pid); } catch { /* already gone */ }
fs.rmSync(path.join(runDir, "chrome.pid"), { force: true });
process.exit(crashed || fails ? 1 : 0);
