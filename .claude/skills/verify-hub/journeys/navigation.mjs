const VIEWS = ["board", "history", "fleet", "cache"];
const LEGACY = { "#/overview": "board", "#/builds": "board", "#trabajos": "board", "#historial": "history", "#cache": "cache",
  "#/macs": "fleet", "#macs": "fleet", "#/add": "fleet", "#unir": "fleet", "#/updates": "fleet" };

export default async (t) => {
  const shown = () => t.ev(`[...document.querySelectorAll("main > section")].filter((s) => !s.hidden).map((s) => s.id.slice(5)).join()`);
  const current = () => t.ev(`document.querySelector('#nav [aria-current="page"]')?.getAttribute("href")`);
  const drawer = () => t.ev(`document.getElementById("drawer").hidden ? null : document.getElementById("drawer-title").textContent`);
  const count = (v) => t.ev(`document.querySelector('#nav a[href="#/${v}"] .nav-count').textContent`);

  await t.nav("/");
  t.check("nav-url: an empty hash lands on Board", (await shown()) === "board" && (await current()) === "#/board");
  await t.aria("bar-board");

  await t.waitFor(`document.querySelector('#nav a[href="#/board"] .nav-count').textContent === "3 building3 queued"`, 8000);
  t.check("nav-counts: Board counts building and queued", (await count("board")) === "3 building3 queued", await count("board"));
  t.check("nav-counts: History counts the failures of the last 24 h", (await count("history")) === "2 failed in the last 24 h", await count("history"));
  t.check("nav-counts: Fleet counts what needs attention", (await count("fleet")) === "3 need attention", await count("fleet"));
  const chips = await t.ev(`[...document.querySelectorAll("#summary a")].filter((a) => !a.classList.contains("alerts-n")).map((a) => a.textContent)`);
  t.check("nav-alerts: the top bar has a chip per alert, worst first",
    chips.length === 3 && chips[0].startsWith("mac-gamma lost") && chips[1] === "mac-epsilon missing tools" && chips[2] === "Hub update · 5 agents outdated", JSON.stringify(chips));
  await t.click('#summary a[href="#mac/mac-gamma"]');
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-alerts: the lost chip opens that Mac over Board", (await shown()) === "board" && (await drawer()) === "Mac mac-gamma");
  await t.press("Escape");

  for (const v of VIEWS) {
    await t.click(`#nav a[href="#/${v}"]`);
    t.check(`nav-click: ${v} shows only its view, marks it current and titles the tab`,
      (await shown()) === v && (await current()) === "#/" + v && (await t.ev("location.hash")) === "#/" + v
      && (await t.ev("document.title")).endsWith("· Cider Builder"));
    await t.shot("view-" + v);
  }

  await t.back();
  t.check("nav-back: Back returns to the previous view", (await shown()) === "fleet" && (await current()) === "#/fleet");
  await t.forward();
  t.check("nav-back: Forward returns to Cache", (await shown()) === "cache" && (await current()) === "#/cache");

  await t.nav("/#/board");
  await t.press("Tab");
  await t.press("Tab");
  t.check("nav-keyboard: Tab reaches the top bar with a visible focus ring",
    (await t.ev(`document.activeElement.getAttribute("href")`)) === "#/history" && (await t.ev(`document.activeElement.matches(":focus-visible")`)));
  await t.press("Enter");
  t.check("nav-keyboard: Enter opens the view and moves focus to its heading",
    (await shown()) === "history" && (await t.ev(`document.activeElement.tagName + " " + document.activeElement.textContent`)) === "H2 History");

  for (const [anchor, view] of Object.entries(LEGACY)) {
    await t.ev(`location.hash = ${JSON.stringify(anchor)}`);
    await t.sleep(200);
    t.check(`nav-legacy: ${anchor} opens ${view} and is rewritten to #/${view}`,
      (await shown()) === view && (await t.ev("location.hash")) === "#/" + view);
  }
  await t.click('.jump a[href="#/add"]');
  t.check("nav-target: Add a Mac stays on Fleet and focuses its Add a Mac heading",
    (await t.ev("location.hash")) === "#/fleet" && (await t.ev("document.activeElement.id")) === "fleet-add");
  await t.click('.jump a[href="#/updates"]');
  t.check("nav-target: Updates focuses the Updates heading", (await t.ev("document.activeElement.id")) === "fleet-updates");

  for (const v of VIEWS) {
    await t.click(`#nav a[href="#/${v}"]`);
    await t.ev(`location.hash = "#mac/mac-gamma"`);
    await t.waitFor(`!document.getElementById("drawer").hidden`);
    t.check(`nav-drawer: #mac/<label> opens the drawer over ${v}`,
      (await shown()) === v && (await drawer()) === "Mac mac-gamma" && (await t.ev("location.hash")) === `#/${v}/mac/mac-gamma`);
    if (v === "history") await t.shot("drawer-over-history");
    await t.press("Escape");
    t.check(`nav-drawer: Escape closes it and keeps ${v}`, (await drawer()) === null && (await t.ev("location.hash")) === "#/" + v);
  }

  await t.nav("/#/board");
  await t.ev(`location.hash = "#/history/mac/mac-alpha"`);
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  await t.press("Escape");
  t.check("nav-drawer: Escape on a drawer pasted from another view keeps that view",
    (await shown()) === "history" && (await drawer()) === null && (await t.ev("location.hash")) === "#/history");

  const worked = await t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs.find((j) => j.worker).id)`);
  await t.nav("/#/board");
  await t.ev(`location.hash = "#job/${worked}"`);
  await t.waitFor(`!!document.querySelector('#drawer a[href^="#mac/"]')`);
  await t.click(`#drawer a[href^="#mac/"]`);
  await t.waitFor(`document.getElementById("drawer-title").textContent.startsWith("Mac ")`);
  await t.click("#drawer-close");
  t.check("nav-drawer: Close on a drawer opened from a drawer closes it",
    (await shown()) === "board" && (await drawer()) === null && (await t.ev("location.hash")) === "#/board");

  await t.nav("/#/board");
  await t.ev(`location.hash = "#mac/mac-gamma"`);
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  await t.click("#drawer-close");
  await t.forward();
  t.check("nav-back: Close after an in-page open goes Back, so Forward reopens the drawer",
    (await drawer()) === "Mac mac-gamma" && (await t.ev("location.hash")) === "#/board/mac/mac-gamma");

  await t.nav("/#/board");
  await t.waitFor(`!!document.querySelector('#board-lanes a[href^="#job/"]')`);
  const opener = await t.ev(`document.querySelector('#board-lanes a[href^="#job/"]').getAttribute("href")`);
  await t.click(`#board-lanes a[href="${opener}"]`);
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-focus: opening a drawer by click moves focus to Close", (await t.ev("document.activeElement.id")) === "drawer-close");
  await t.press("Escape");
  await t.sleep(300);
  t.check("nav-focus: closing it returns focus to the link that opened it",
    (await drawer()) === null && (await t.ev(`document.activeElement.getAttribute("href")`)) === opener, await t.ev("document.activeElement.outerHTML.slice(0, 80)"));

  const job = await t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs[0].id)`);
  await t.nav("/#job/" + encodeURIComponent(job));
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-url: a cold load of an old #job/<id> link opens the drawer over Board",
    (await shown()) === "board" && (await drawer()) === "Job " + job);
  await t.nav("/#/cache/mac/mac-alpha");
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-url: a cold load of #/cache/mac/<label> restores the view and the drawer",
    (await shown()) === "cache" && (await drawer()) === "Mac mac-alpha");
  await t.click("#drawer-close");
  t.check("nav-url: Close on a cold-loaded drawer leaves #/cache", (await t.ev("location.hash")) === "#/cache");

  await t.size(390, 800);
  for (const v of ["board", "history", "fleet"]) {
    await t.nav("/#/" + v);
    await t.sleep(500);
    t.check(`nav-narrow: ${v} fits a 390 px screen without horizontal scroll`, (await t.ev("document.documentElement.scrollWidth")) <= 390,
      await t.ev("document.documentElement.scrollWidth"));
  }
  await t.nav("/#/board");
  t.check("nav-narrow: the nav is collapsed behind Menu",
    (await t.ev(`getComputedStyle(document.getElementById("nav")).display`)) === "none");
  t.check("nav-narrow: the alerts fold into one chip that links to Fleet",
    (await t.ev(`document.querySelector("#summary .alerts-n")?.textContent`)) === "3 alerts"
    && (await t.ev(`getComputedStyle(document.querySelector("#summary .alerts-n")).display`)) !== "none"
    && (await t.ev(`getComputedStyle(document.querySelector('#summary a[href="#mac/mac-gamma"]')).display`)) === "none");
  await t.click("#menu-btn");
  t.check("nav-narrow: Menu opens the nav and sets aria-expanded",
    (await t.ev(`document.getElementById("menu-btn").getAttribute("aria-expanded")`)) === "true");
  await t.shot("narrow-menu-open");
  await t.aria("narrow-menu-open");
  await t.press("Escape");
  t.check("nav-narrow: Escape closes the menu and returns focus to Menu",
    (await t.ev(`document.getElementById("menu-btn").getAttribute("aria-expanded")`)) === "false"
    && (await t.ev("document.activeElement.id")) === "menu-btn");
  await t.click("#menu-btn");
  await t.click(`#nav a[href="#/history"]`);
  t.check("nav-narrow: picking an item opens it and closes the menu",
    (await shown()) === "history" && (await t.ev(`document.getElementById("menu-btn").getAttribute("aria-expanded")`)) === "false");
};
