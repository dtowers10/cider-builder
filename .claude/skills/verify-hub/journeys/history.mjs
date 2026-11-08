// features/history.md: the list, search, filters, the drawer and Overview's link to failures. Read-only.
// The total grows by one cancelled `shop ios` every ~2 min (the fleet's no-source job expires), so it is read from
// /api/history rather than hard-coded.
const count = `document.getElementById("f-count").textContent`;

export default async (t) => {
  await t.nav("/#historial");
  await t.waitFor(`location.hash === "#/history" && /of/.test(${count})`, 5000);
  const total = await t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs.length)`);
  t.check("history-list: the legacy #historial lands on History and lists every finished job", (await t.ev(count)) === `${total} of ${total}`, await t.ev(count));
  t.check("history-filters: Mac options come from the jobs",
    (await t.ev(`[...document.querySelectorAll("#f-mac option")].map((o) => o.value).join()`)) === ",mac-alpha,mac-beta,mac-gamma");

  await t.type("#f-q", "LEDGER");
  t.check("history-search: case-insensitive, 11 ledger jobs", (await t.ev(count)) === `11 of ${total}`, await t.ev(count));
  await t.select("#f-state", "done");
  t.check("history-state: 9 done", (await t.ev(count)) === `9 of ${total}`, await t.ev(count));
  await t.shot("history-ledger-done");

  await t.type("#f-q", "");
  await t.select("#f-state", "");
  await t.type("#f-q", "k0010");
  t.check("history-search: matches the key", (await t.ev(count)) === `1 of ${total}`, await t.ev(count));
  await t.type("#f-q", "");
  await t.select("#f-plat", "android");
  await t.select("#f-client", "daniel");
  await t.select("#f-mac", "mac-gamma");
  t.check("history-filters: filters combine down to nothing", (await t.ev(count)) === `0 of ${total}`
    && (await t.ev(`document.getElementById("histlist").textContent`)).includes("No finished job matches."));
  await t.select("#f-mac", "");
  await t.select("#f-client", "");
  await t.select("#f-plat", "");

  await t.click("#histlist tbody tr td:nth-child(2)");
  await t.waitFor(`/^#\\/history\\/job\\//.test(location.hash) && !document.getElementById("drawer").hidden`, 3000);
  t.check("history-drawer: a row opens the job over History", (await t.ev(`document.getElementById("drawer-title").textContent`)).startsWith("Job "));
  await t.back();
  t.check("history-drawer: Back closes it", (await t.ev(`document.getElementById("drawer").hidden`)) && (await t.ev("location.hash")) === "#/history");

  await t.nav("/#/overview");
  await t.click("#ov-all-failures");
  await t.waitFor(`location.hash === "#/history"`, 3000);
  t.check("history-failures: Overview's link lands on History filtered to failed",
    (await t.ev(`document.getElementById("f-state").value`)) === "failed" && (await t.ev(count)) === `6 of ${total}`, await t.ev(count));
  await t.shot("history-failures");
};
