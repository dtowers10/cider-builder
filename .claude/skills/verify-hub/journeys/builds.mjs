// features/builds.md: Running & queue, the job drawer with its live log, and cancelling a queued job. The last part
// cancels the queued `demo android`, so run this journey on its own run or after the read-only ones.
const lastToast = `[...document.querySelectorAll("#toasts .toast")].map((e) => e.textContent).pop() || ""`;
const queueRows = `[...document.querySelectorAll("#queue tbody tr")].map((r) => r.textContent.replace(/\\s+/g, " ").trim())`;

export default async (t) => {
  await t.nav("/#/builds");
  await t.waitFor(`document.querySelectorAll("#running tbody tr").length === 4`, 5000);
  const running = await t.ev(`[...document.querySelectorAll("#running tbody tr")].map((r) => r.textContent)`);
  t.check("builds-running: four builds, scanner android on linux-delta among them",
    running.some((r) => r.includes("scanner") && r.includes("android") && r.includes("linux-delta")), JSON.stringify(running));
  const t1 = await t.ev(`document.querySelector("#running [data-since]").textContent`);
  await t.sleep(1500);
  t.check("builds-running: the time cells count up", (await t.ev(`document.querySelector("#running [data-since]").textContent`)) !== t1);

  const q = await t.ev(queueRows);
  t.check("builds-queue: scanner android, demo android, then shop ios with no source yet",
    q.length === 3 && q[0].startsWith("1") && q[0].includes("scanner") && q[1].startsWith("2") && q[1].includes("demo")
    && q[2].startsWith("3") && q[2].includes("shop") && q[2].includes("no source yet"), JSON.stringify(q));
  t.check("builds-counts: the sidebar reads 4 building and 3 queued",
    (await t.ev(`document.querySelector('#nav a[href="#/builds"] .nav-count').textContent`)) === "4 building3 queued");
  await t.shot("builds-view");

  await t.click(`#running a[href^="#job/"]`);
  await t.waitFor(`!document.getElementById("drawer").hidden && document.getElementById("drawer-title").textContent.startsWith("Job ")`, 3000);
  await t.waitFor(`/Live: updates every second/.test(document.querySelector(".log-status")?.textContent || "")`, 5000);
  const before = await t.ev(`document.querySelector("pre.log").textContent.length`);
  await t.waitFor(`document.querySelector("pre.log").textContent.length > ${before}`, 6000);
  const log = await t.ev(`document.querySelector("pre.log").textContent`);
  t.check("builds-log: the log grows live, with no ANSI escapes", !log.includes("\u001b"));
  t.check("builds-drawer: a building job shows its source and a Cancel job button",
    /Source uploaded\s*yes/.test(await t.ev(`document.getElementById("drawer-body").textContent`))
    && (await t.ev(`[...document.querySelectorAll("#drawer-body button")].some((b) => b.textContent === "Cancel job")`)));
  await t.shot("builds-log");
  await t.press("Escape");

  const demo = `[...document.querySelectorAll("#queue tbody tr")].find((r) => r.textContent.includes("demo"))`;
  const id = await t.ev(`${demo}.querySelector('a[href^="#job/"]').getAttribute("href").slice(5)`);
  await t.click(`#queue a[href="#job/${id}"]`);
  await t.waitFor(`document.getElementById("drawer-title").textContent.includes(${JSON.stringify(id)})`, 3000);
  await t.click("#drawer-body button", "Cancel job");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("builds-cancel: the confirmation starts on Keep it and says it never reaches a Mac",
    (await t.ev(`document.activeElement.id`)) === "confirm-no"
    && (await t.ev(`document.getElementById("confirm-body").textContent`)).includes("It leaves the queue and never reaches a Mac."));
  await t.click("#confirm-yes");
  await t.waitFor(`(${lastToast}).startsWith("Cancel ")`, 5000);
  t.check("builds-cancel: toast says cancelled", (await t.ev(lastToast)) === `Cancel ${id}: cancelled`, await t.ev(lastToast));
  await t.waitFor(`document.querySelectorAll("#queue tbody tr").length === 2`, 5000);
  const s = await t.ev(`fetch("/api/state").then((r) => r.json())`);
  t.check("builds-cancel: /api/state no longer lists it and the queue renumbers 1, 2",
    !s.active.some((j) => j.id === id) && (await t.ev(queueRows)).map((r) => r[0]).join() === "1,2");
  await t.shot("builds-cancelled");
};
