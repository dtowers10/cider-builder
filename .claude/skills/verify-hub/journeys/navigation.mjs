// features/navigation.md: sidebar clicks, keyboard, direct URLs, Back/Forward, legacy anchors,
// the detail drawer over every view, and the narrow-screen menu.
const VIEWS = ["overview", "macs", "add", "updates", "builds", "history", "cache"];
const LEGACY = { "#macs": "macs", "#trabajos": "builds", "#historial": "history", "#cache": "cache", "#unir": "add" };

export default async (t) => {
  const shown = () => t.ev(`[...document.querySelectorAll("main > section")].filter((s) => !s.hidden).map((s) => s.id.slice(5)).join()`);
  const current = () => t.ev(`document.querySelector('#nav [aria-current="page"]')?.getAttribute("href")`);
  const drawer = () => t.ev(`document.getElementById("drawer").hidden ? null : document.getElementById("drawer-title").textContent`);

  await t.nav("/");
  t.check("nav-url: an empty hash lands on Overview", (await shown()) === "overview" && (await current()) === "#/overview");
  await t.aria("sidebar-overview");

  for (const v of VIEWS) {
    await t.click(`#nav a[href="#/${v}"]`);
    t.check(`nav-click: ${v} shows only its view, marks it current and titles the tab`,
      (await shown()) === v && (await current()) === "#/" + v && (await t.ev("location.hash")) === "#/" + v
      && (await t.ev("document.title")).endsWith("· Cider Builder"));
    await t.shot("view-" + v);
  }

  await t.back();
  t.check("nav-back: Back returns to the previous view", (await shown()) === "history" && (await current()) === "#/history");
  await t.forward();
  t.check("nav-back: Forward returns to Cache", (await shown()) === "cache" && (await current()) === "#/cache");

  await t.nav("/#/overview");
  await t.press("Tab");
  await t.press("Tab");
  t.check("nav-keyboard: Tab reaches the sidebar with a visible focus ring",
    (await t.ev(`document.activeElement.getAttribute("href")`)) === "#/macs" && (await t.ev(`document.activeElement.matches(":focus-visible")`)));
  await t.press("Enter");
  t.check("nav-keyboard: Enter opens the view and moves focus to its heading",
    (await shown()) === "macs" && (await t.ev(`document.activeElement.tagName + " " + document.activeElement.textContent`)) === "H2 Macs");

  for (const [anchor, view] of Object.entries(LEGACY)) {
    await t.ev(`location.hash = ${JSON.stringify(anchor)}`);
    await t.sleep(200);
    t.check(`nav-legacy: ${anchor} opens ${view} and is rewritten to #/${view}`,
      (await shown()) === view && (await t.ev("location.hash")) === "#/" + view);
  }

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

  await t.nav("/#/overview");
  await t.ev(`location.hash = "#/history/mac/mac-alpha"`);
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  await t.press("Escape");
  t.check("nav-drawer: Escape on a drawer pasted from another view keeps that view",
    (await shown()) === "history" && (await drawer()) === null && (await t.ev("location.hash")) === "#/history");

  const worked = await t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs.find((j) => j.worker).id)`);
  await t.nav("/#/overview");
  await t.ev(`location.hash = "#job/${worked}"`);
  await t.waitFor(`!!document.querySelector('#drawer a[href^="#mac/"]')`);
  await t.click(`#drawer a[href^="#mac/"]`);
  await t.waitFor(`document.getElementById("drawer-title").textContent.startsWith("Mac ")`);
  await t.click("#drawer-close");
  t.check("nav-drawer: Close on a drawer opened from a drawer closes it",
    (await shown()) === "overview" && (await drawer()) === null && (await t.ev("location.hash")) === "#/overview");

  await t.nav("/#/overview");
  await t.ev(`location.hash = "#mac/mac-gamma"`);
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  await t.click("#drawer-close");
  await t.forward();
  t.check("nav-back: Close after an in-page open goes Back, so Forward reopens the drawer",
    (await drawer()) === "Mac mac-gamma" && (await t.ev("location.hash")) === "#/overview/mac/mac-gamma");

  const job = await t.ev(`fetch("/api/history").then((r) => r.json()).then((d) => d.jobs[0].id)`);
  await t.nav("/#job/" + encodeURIComponent(job));
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-url: a cold load of a legacy #job/<id> link opens the drawer over Overview",
    (await shown()) === "overview" && (await drawer()) === "Job " + job);
  await t.nav("/#/cache/mac/mac-alpha");
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  t.check("nav-url: a cold load of #/cache/mac/<label> restores the view and the drawer",
    (await shown()) === "cache" && (await drawer()) === "Mac mac-alpha");
  await t.click("#drawer-close");
  t.check("nav-url: Close on a cold-loaded drawer leaves #/cache", (await t.ev("location.hash")) === "#/cache");

  await t.nav("/#/overview");
  await t.ev('location.hash = "#/nope"');
  await t.waitFor(`location.hash === "#/overview"`, 3000);
  t.check("nav-url: an unknown hash lands on Overview and is rewritten to #/overview", (await shown()) === "overview");
  await t.click('#nav a[href="#/macs"]');
  await t.click('#maclist a.card[href="#mac/mac-gamma"]');
  await t.waitFor(`!document.getElementById("drawer").hidden`);
  await t.clickAt(100, 400);
  t.check("nav-drawer: a click on the backdrop beside the drawer closes it and keeps the view",
    (await drawer()) === null && (await t.ev("location.hash")) === "#/macs");

  await t.size(390, 800);
  await t.nav("/#/overview");
  t.check("nav-narrow: the sidebar is collapsed behind Menu",
    (await t.ev(`getComputedStyle(document.getElementById("nav")).display`)) === "none");
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
  await t.click("#menu-btn");
  await t.click("#menu-btn");
  t.check("nav-narrow: pressing Menu again closes it",
    (await t.ev(`document.getElementById("menu-btn").getAttribute("aria-expanded")`)) === "false");
};
