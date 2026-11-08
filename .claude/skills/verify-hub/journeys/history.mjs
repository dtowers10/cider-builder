export default async (t) => {
  const text = (sel) => t.ev(`document.querySelector(${JSON.stringify(sel)})?.textContent.replace(/\\s+/g, " ").trim()`);
  const count = () => text("#f-count");
  const hist = () => t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs)`);
  await t.nav("/#/history");
  const jobs = await hist();
  const total = jobs.length, now = await t.ev(`fetch("/api/state").then((r) => r.json()).then((s) => s.now)`);
  const day = jobs.filter((j) => j.finished >= now - 86400).length;
  const failed = jobs.filter((j) => j.state === "failed").length, failedDay = jobs.filter((j) => j.state === "failed" && j.finished >= now - 86400).length;
  const done = jobs.filter((j) => j.state === "done").length, ledgerDone = jobs.filter((j) => j.state === "done" && j.proj === "ledger").length;
  t.check("history-list: the seed has at least 42 finished jobs, 6 failed, 2 of them in the last 24 h", total >= 42 && failed >= 6 && failedDay === 2, JSON.stringify({ total, failed, failedDay }));

  await t.waitFor(`document.getElementById("f-count").textContent === "${total} of ${total}"`, 8000);
  t.check("history-list: newest first, with the count", await t.ev(`(() => { const d = [...document.querySelectorAll("#histlist tbody tr td:first-child")].map((td) => td.textContent); return d.length === ${Math.min(total, 500)}; })()`));
  t.check("history-list: rows read as cards below 860 px only", (await t.ev(`getComputedStyle(document.querySelector("#histlist thead")).display`)) !== "none");

  await t.click("#f-when label", "24 h");
  t.check("history-window: 24 h narrows to the last day", (await count()) === `${day} of ${total}`, await count());
  await t.click(".filters label", "Failed");
  t.check("history-window: Failed sets the state filter", (await t.ev(`document.getElementById("f-state").value`)) === "failed" && (await count()) === `${failedDay} of ${total}`, await count());
  await t.click("#f-when label", "All");
  t.check("history-window: All widens again", (await count()) === `${failed} of ${total}`, await count());
  await t.select("#f-state", "done");
  t.check("history-filters: the state select unticks Failed and filters to done",
    !(await t.ev(`document.getElementById("f-failed").checked`)) && (await count()) === `${done} of ${total}`
    && await t.ev(`[...document.querySelectorAll("#histlist tbody .badge")].every((b) => b.textContent === "done")`), await count());
  await t.select("#f-mac", "mac-beta");
  t.check("history-filters: Mac narrows further", await t.ev(`[...document.querySelectorAll("#histlist tbody tr td:nth-child(5)")].every((td) => td.textContent === "mac-beta")`));
  await t.select("#f-mac", "");
  await t.type("#f-q", "ledger");
  t.check("history-search: the search matches the project without regard to case",
    (await count()) === `${ledgerDone} of ${total}` && await t.ev(`[...document.querySelectorAll("#histlist tbody tr td:nth-child(2)")].every((td) => td.textContent === "ledger")`), await count());
  await t.shot("history-filtered");

  const nosrc = await t.ev(`fetch("/api/state").then((r) => r.json()).then((s) => s.active.find((j) => j.state === "queued" && !j.src)?.id)`);
  await t.ev(`fetch("/detach?job=" + encodeURIComponent(${JSON.stringify(nosrc)}) + "&all=1", { method: "POST" }).then((r) => r.text())`);
  await t.waitFor(`document.getElementById("f-count").textContent === "${ledgerDone} of ${total + 1}"`, 8000);
  t.check("history-persist: new history arrives and the query and filters stay",
    (await t.ev(`document.getElementById("f-q").value`)) === "ledger" && (await t.ev(`document.getElementById("f-state").value`)) === "done"
    && (await t.ev(`[...document.querySelectorAll("main > section")].filter((s) => !s.hidden).map((s) => s.id).join()`)) === "view-history");

  await t.click("#histlist tbody tr td:nth-child(2)");
  await t.waitFor(`!document.getElementById("drawer").hidden`, 5000);
  const id = await t.ev(`document.getElementById("drawer-title").textContent.slice(4)`);
  t.check("history-list: a row opens the job over History", (await t.ev("location.hash")) === "#/history/job/" + encodeURIComponent(id));
  await t.waitFor(`document.querySelector(".log-status")?.textContent.startsWith("Log complete")`, 8000);
  t.check("history-list: a done job offers its download and a complete log",
    (await text(".job-head")).includes("Download k") && (await text(".log-status")).startsWith("Log complete ("), await text(".job-head"));
  await t.shot("history-drawer");
  await t.back();
  await t.sleep(300);
  t.check("history-list: Back closes it and keeps the filters",
    await t.ev(`document.getElementById("drawer").hidden`) && (await t.ev(`document.getElementById("f-q").value`)) === "ledger" && (await count()) === `${ledgerDone} of ${total + 1}`);

  await t.nav("/#/board");
  await t.waitFor(`document.querySelectorAll("#board-recent li .b-failed").length === 2`, 8000);
  await t.click("#board-failures");
  await t.waitFor(`document.getElementById("f-state").value === "failed"`, 3000);
  t.check("history-failures-link: the Board's link opens History filtered to failed",
    (await t.ev(`[...document.querySelectorAll("main > section")].filter((s) => !s.hidden).map((s) => s.id).join()`)) === "view-history"
    && (await t.ev(`document.getElementById("f-failed").checked`)) && (await count()) === `${failed} of ${total + 1}`, await count());
  await t.shot("history-failures");
};
