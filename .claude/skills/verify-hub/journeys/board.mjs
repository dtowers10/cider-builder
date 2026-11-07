export default async (t) => {
  const text = (sel) => t.ev(`document.querySelector(${JSON.stringify(sel)})?.textContent.replace(/\\s+/g, " ").trim()`);
  const texts = (sel) => t.ev(`[...document.querySelectorAll(${JSON.stringify(sel)})].map((e) => e.textContent.replace(/\\s+/g, " ").trim())`);
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const lastToast = () => t.ev(`[...document.querySelectorAll("#toasts .toast")].map((e) => e.textContent).pop() || ""`);

  await t.nav("/#/board");
  await t.waitFor(`document.querySelectorAll("#board-lanes .lane").length === 5 && document.querySelectorAll("#board-recent li").length > 0`, 8000);
  t.check("board-lanes: the heading counts the busy slots", (await text("#board-lanes h3")) === "Macs · 3 of 6 slots busy", await text("#board-lanes h3"));
  const alpha = await texts('#board-lanes .lane[data-id="mac-alpha"] .cell.job');
  t.check("board-eta: demo ios on mac-alpha is past its typical 3m00s and reads running long",
    alpha.length === 2 && alpha[0].startsWith("demo ios ci-runner") && alpha[0].includes("running long"), JSON.stringify(alpha));
  t.check("board-eta: shop android has one done sample, so it shows elapsed time only",
    alpha[1].startsWith("shop android daniel") && !alpha[1].includes("left") && !alpha[1].includes("running long"), alpha[1]);
  const beta = await text('#board-lanes .lane[data-id="mac-beta"] .cell.job');
  t.check("board-eta: ledger ios on mac-beta shows its time left (or running long once past 3m00s)",
    beta.startsWith("ledger ios elena") && /~\d+m\d\ds left|running long/.test(beta), beta);
  t.check("board-eta: a running cell with an estimate has a 2 px meter",
    await t.ev(`!!document.querySelector('#board-lanes .lane[data-id="mac-beta"] .cell.job .meter span[data-fill]')`));
  const off = await texts("#board-lanes .cell.off");
  t.check("board-lanes: a Mac that takes no builds says why and offers the action",
    off.length === 3 && off[0] === "missing tools · Why" && /^no heartbeat · lost 1 h ago · Why$/.test(off[1]) && off[2] === "disabled · Enable", JSON.stringify(off));
  const since = await text('#board-lanes .lane[data-id="mac-alpha"] .cell.job [data-since]');
  await t.waitFor(`document.querySelector('#board-lanes .lane[data-id="mac-alpha"] .cell.job [data-since]').textContent !== ${JSON.stringify(since)}`, 3000);
  t.check("board-lanes: the elapsed time ticks", (await text('#board-lanes .lane[data-id="mac-alpha"] .cell.job [data-since]')) !== since);

  const queue = await texts("#board-queue li");
  t.check("board-forecast: scanner android starts soon on mac-alpha, its affinity Mac with an overdue slot",
    queue.length === 3 && queue[0].startsWith("1 · scanner android ci-runner") && queue[0].includes("starts soon on mac-alpha"), queue[0]);
  t.check("board-forecast: demo android starts on mac-beta when ledger reaches its typical time",
    queue[1].startsWith("2 · demo android daniel") && /starts (in ~\d+m\d\ds|soon) on mac-beta/.test(queue[1]), queue[1]);
  t.check("board-forecast: the job with no source says so, with the time the hub cancels it",
    queue[2].startsWith("3 · shop ios elena") && queue[2].includes("no source yet") && /cancelled (in ~\d+m\d\ds|soon) if none/.test(queue[2])
    && await t.ev(`!!document.querySelector("#board-queue li:nth-child(3) .b-nosrc")`), queue[2]);
  t.check("board-forecast: the queue is labelled as an estimate", (await text("#board-queue")).includes("Start times are estimates from typical build times."));

  t.check("board-recent: the heading counts the failures", (await text("#board-recent h3")) === "Last 24 h · 2 failed", await text("#board-recent h3"));
  t.check("board-recent: done and failed jobs of the last 24 h, newest first, 2 of them failed",
    (await t.ev(`document.querySelectorAll("#board-recent li").length`)) === 9 && (await t.ev(`document.querySelectorAll("#board-recent li .b-failed").length`)) === 2);
  await t.shot("board");

  await t.click("#board-lanes .cell.off a", "Why");
  await t.waitFor(`!document.getElementById("drawer").hidden && !!document.querySelector("#drawer-body p.note")`, 5000);
  t.check("board-lanes: Why opens the Mac with the reason first",
    (await text("#drawer-title")) === "Mac mac-epsilon" && (await text("#drawer-body p.note")).includes("xcodegen, Java 17"), await text("#drawer-body p.note"));
  await t.press("Escape");
  await t.click("#board-lanes .cell.off button", "Enable");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("board-lanes: Enable on a disabled Mac asks first", (await text("#confirm-title")) === "Enable mac-zeta" && (await t.ev("document.activeElement.id")) === "confirm-no");
  await t.click("#confirm-no");
  t.check("board-lanes: Keep it leaves it disabled", !(await state()).workers.find((w) => w.label === "mac-zeta").enabled);

  await t.click('#board-lanes .lane[data-id="mac-alpha"] .cell.job a[href^="#job/"]');
  await t.waitFor(`!document.getElementById("drawer").hidden && document.querySelector(".log-status")?.textContent.startsWith("Live: updates every second.")`, 8000);
  const head = await text(".job-head");
  t.check("board-detail: one header line with project, platform, state, elapsed, typical, client, Mac and kind",
    /^demo ios building \d+m\d\ds typical 3m00s running long ci-runner on mac-alpha expo \d clients? waiting Details Cancel job$/.test(head), head);
  t.check("board-detail: the log fills the drawer", await t.ev(`(() => { const p = document.querySelector("pre.log").getBoundingClientRect(); return p.bottom > innerHeight * 0.8; })()`));
  const lines = await t.ev(`document.querySelector("pre.log").textContent.split("\\n").length`);
  await t.waitFor(`document.querySelector("pre.log").textContent.split("\\n").length > ${lines}`, 6000);
  t.check("board-log: the log streams live with no escape codes",
    await t.ev(`/CompileSwift normal arm64 Module\\d+\\.swift/.test(document.querySelector("pre.log").textContent) && !document.querySelector("pre.log").textContent.includes("\\x1b")`));
  await t.shot("job-detail");
  t.check("board-detail: Details is folded", await t.ev(`document.getElementById("job-more").hidden && document.querySelector(".job-head .details").getAttribute("aria-expanded") === "false"`));
  await t.click("#drawer-body button", "Details");
  t.check("board-detail: Details unfolds the full field list",
    await t.ev(`!document.getElementById("job-more").hidden && document.querySelector(".job-head .details").getAttribute("aria-expanded") === "true"`)
    && /Source uploaded\s*yes/.test(await text("#job-more")) && (await text("#job-more")).includes("cfg.MB_SCHEME"));
  await t.click("#drawer-body button", "Details");
  t.check("board-detail: Details folds again", await t.ev(`document.getElementById("job-more").hidden`));
  await t.type(".log-tools input[type=search]", "Module");
  await t.waitFor(`/\\d+ hits?/.test(document.querySelector(".log-find").textContent)`, 3000);
  t.check("board-detail: search counts the hits", /^\d+ hits?$/.test(await text(".log-find")), await text(".log-find"));
  await t.press("Enter");
  t.check("board-detail: Enter moves to the first hit and turns Follow off",
    /^1 of \d+/.test(await text(".log-find")) && (await t.ev(`[...document.querySelectorAll(".log-tools button")].find((b) => b.textContent === "Follow").getAttribute("aria-pressed")`)) === "false", await text(".log-find"));
  await t.click(".log-tools button", "Follow");
  t.check("board-detail: Follow turns it back on", await t.ev(`[...document.querySelectorAll(".log-tools button")].find((b) => b.textContent === "Follow").getAttribute("aria-pressed") === "true"`));
  await t.click(".log-tools button", "Wrap");
  t.check("board-detail: Wrap toggles wrapping", await t.ev(`document.querySelector("pre.log").classList.contains("nowrap") && [...document.querySelectorAll(".log-tools button")].find((b) => b.textContent === "Wrap").getAttribute("aria-pressed") === "false"`));
  t.check("board-detail: From start is disabled when the log is shown from byte 0", await t.ev(`[...document.querySelectorAll(".log-tools button")].find((b) => b.textContent === "From start").disabled`));
  await t.press("Escape");

  await t.size(390, 800);
  await t.nav("/#/board");
  await t.waitFor(`document.querySelectorAll("#board-lanes .lane").length === 5`, 8000);
  t.check("board-narrow: lanes stack with no horizontal scroll", (await t.ev("document.documentElement.scrollWidth")) <= 390);
  await t.shot("board-narrow");
  await t.size(1280, 800);

  await t.nav("/#/board");
  await t.waitFor(`document.querySelectorAll("#board-queue li").length === 3`, 8000);
  const id = await t.ev(`document.querySelector("#board-queue li:nth-child(2)").dataset.id`);
  await t.click(`#board-queue li:nth-child(2) a[href^="#job/"]`);
  await t.waitFor(`!document.getElementById("drawer").hidden && !!document.querySelector("#drawer-body button.danger")`, 5000);
  await t.click("#drawer-body button.danger");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("board-cancel: the confirmation names the job and focuses Keep it",
    (await text("#confirm-title")) === "Cancel job " + id && (await t.ev("document.activeElement.id")) === "confirm-no");
  await t.shot("cancel-confirm");
  await t.click("#confirm-no");
  t.check("board-cancel: Keep it leaves it queued", (await state()).active.some((j) => j.id === id && j.state === "queued"));
  await t.click("#drawer-body button.danger");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent === "Cancel ${id}: cancelled")`, 5000);
  t.check("board-cancel: the toast confirms it", true, await lastToast());
  await t.waitFor(`document.querySelector(".job-head .badge")?.textContent === "cancelled" && document.querySelectorAll("#board-queue li").length === 2`, 8000);
  t.check("board-cancel: the drawer and the queue show it gone, and /api/state agrees",
    !(await state()).active.some((j) => j.id === id)
    && (await t.ev(`document.querySelector('#nav a[href="#/board"] .nav-count').textContent`)) === "3 building2 queued");
  await t.shot("cancel-after");
};
