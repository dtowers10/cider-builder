const SUBJECT = "Panel: show each build's estimated time left";

export default async (t) => {
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const mac = async (label) => (await state()).workers.find((w) => w.label === label);
  const card = (label) => t.ev(`document.querySelector('#maclist .card[data-id=${JSON.stringify(label)}]')?.textContent.replace(/\\s+/g, " ").trim()`);
  const chip = () => t.ev(`document.querySelector('#summary a[href="#/updates"]')?.textContent`);
  const toast = (text) => t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent.includes(${JSON.stringify(text)}))`, 5000);
  const watch = () => t.ev(`window.sawUpdating = new Set(); new MutationObserver(() => {
      for (const c of document.querySelectorAll("#maclist .card")) if (c.querySelector(".b-updating")) window.sawUpdating.add(c.dataset.id);
    }).observe(document.getElementById("maclist"), { childList: true, subtree: true }); true`);
  const updateFromDrawer = async (label) => {
    await t.click(`#maclist a[href="#mac/${label}"]`);
    await t.waitFor(`!document.getElementById("drawer").hidden && document.getElementById("drawer-body").textContent.includes("(outdated)")`, 5000);
    await t.click("#drawer-body button", "Update agent");
  };

  await t.nav("/");
  await t.waitFor(`/Hub update · 5 agents outdated/.test(document.querySelector('#summary a[href="#/updates"]')?.textContent)`, 8000);
  t.check("updates-nav: the top bar has a chip for the hub update and the outdated agents", (await chip()) === "Hub update · 5 agents outdated", await chip());
  await t.click('#summary a[href="#/updates"]');
  t.check("updates-nav: the chip opens Fleet at its Updates section",
    (await t.ev("location.hash")) === "#/fleet" && (await t.ev("document.activeElement.id")) === "fleet-updates");
  await t.waitFor(`document.getElementById("up-hub").textContent.includes("update available")`, 8000);
  const hub = await t.ev(`document.getElementById("up-hub").textContent`);
  const rel = (await state()).release;
  t.check("updates-hub: shows the update with the latest commit on the branch, its subject and the change not installed",
    hub.includes(rel.remote.commit.slice(0, 12)) && hub.includes(rel.installed.slice(0, 12)) && hub.includes(SUBJECT)
    && hub.includes("Latest on main") && hub.includes("1 change not installed yet"), hub.slice(0, 300));
  const log = await t.ev(`[...document.querySelectorAll("#up-hub tbody tr")].map((r) => r.textContent.replace(/\\s+/g, " ").trim())`);
  t.check("updates-changelog: lists every change on main, the new one pending and the installed one too",
    log.length === 2 && log[0].startsWith(rel.remote.commit.slice(0, 12)) && log[0].includes(SUBJECT) && log[0].endsWith("pending")
    && log[1].startsWith(rel.installed.slice(0, 12)) && log[1].endsWith("installed"), JSON.stringify(log));
  t.check("updates-hub: names the update source from hub.json and its branch, and no git host",
    hub.includes("Source" + rel.source.url + " · main") && !/github/i.test(hub), hub.slice(0, 300));
  const banner = await t.ev(`document.getElementById("fleet-banner").textContent.replace(/\\s+/g, " ").trim()`);
  t.check("updates-banner: the banner names the hub update and the outdated agents, with their buttons enabled",
    banner.includes("Hub update available · " + rel.remote.commit.slice(0, 12) + " " + SUBJECT) && banner.includes("5 agents outdated · the hub hands out " + (await state()).agent)
    && await t.ev(`[...document.querySelectorAll("#fleet-banner button")].map((b) => b.textContent + ":" + b.disabled).join() === "Update hub:false,Update all outdated (3):false"`), banner);
  t.check("updates-hub: Check for updates is enabled", await t.ev(`[...document.querySelectorAll("#up-hub button")].some((b) => b.textContent === "Check for updates" && !b.disabled)`));
  await t.shot("updates-hub-available");

  await t.click("#up-hub button", "Check for updates");
  await toast("Check for updates: checking");
  t.check("updates-check: Check for updates answers with a toast", true);
  await t.waitFor(`fetch("/api/state").then((r) => r.json()).then((s) => s.release.phase === "idle" && s.release.checked > ${rel.checked})`, 10000);
  t.check("updates-check: /api/state has a newer check, still 1 behind", ((s) => s.available && s.behind === 1)((await state()).release));

  t.check("updates-agents: mac-beta's card says its agent is outdated", (await card("mac-beta")).includes("agent outdated"), await card("mac-beta"));
  t.check("updates-agents: mac-zeta, too old to update itself, says to run cider-build add",
    (await card("mac-zeta")).includes("run cider-build add mac-zeta once"), await card("mac-zeta"));
  await updateFromDrawer("mac-beta");
  await t.shot("updates-confirm-agent");
  await t.click("#confirm-no");
  t.check("updates-agent-refuse: Keep it changes nothing", !(await mac("mac-beta")).update && !(await mac("mac-beta")).agent_current);

  await watch();
  await t.click("#drawer-body button", "Update agent");
  await t.click("#confirm-yes");
  await toast("Update mac-beta: updating mac-beta");
  t.check("updates-agent: the toast confirms it", true);
  await t.waitFor(`window.sawUpdating.has("mac-beta")`, 5000);
  t.check("updates-agent: the card goes to updating", true);
  await t.waitFor(`!/outdated|updating/.test(document.querySelector('#maclist .card[data-id="mac-beta"]').textContent)`, 10000);
  const beta = await mac("mac-beta");
  t.check("updates-agent: then current, and /api/state agrees (version is the hub's agent, flag cleared, online)",
    beta.agent_current && !beta.update && beta.state === "online" && beta.version === (await state()).agent, JSON.stringify(beta));
  await t.waitFor(`!document.getElementById("drawer-body").textContent.includes("(outdated)")`, 5000);
  t.check("updates-drawer: the drawer no longer marks it outdated", true);
  await t.shot("updates-beta-current");
  await t.click("#drawer-close");

  await updateFromDrawer("mac-epsilon");
  await t.click("#confirm-yes");
  await toast("Update mac-epsilon: updating mac-epsilon");
  await t.waitFor(`!document.getElementById("drawer-body").textContent.includes("(outdated)")`, 10000);
  t.check("updates-drawer: Update agent from the drawer brings it current", (await mac("mac-epsilon")).agent_current);
  await t.shot("updates-drawer-epsilon");
  await t.click("#drawer-close");

  await t.waitFor(`[...document.querySelectorAll("#fleet-banner button")].some((b) => b.textContent === "Update all outdated (1)")`, 5000);
  t.check("updates-all: one outdated Mac left that can update", true);
  await t.click("#fleet-banner button", "Update all outdated (1)");
  await t.click("#confirm-yes");
  await toast("Update all: 1 updating");
  await t.waitFor(`!/outdated|updating/.test(document.querySelector('#maclist .card[data-id="mac-alpha"]').textContent)`, 10000);
  const s = await state();
  t.check("updates-all: every Mac that can update itself is current; mac-zeta still needs cider-build add",
    s.workers.filter((w) => w.self_update).every((w) => w.agent_current) && !s.workers.find((w) => w.label === "mac-zeta").agent_current,
    JSON.stringify(s.workers.map((w) => [w.label, w.agent_current])));
  await t.waitFor(`/2 agents outdated/.test(document.querySelector('#summary a[href="#/updates"]')?.textContent)`, 5000);
  t.check("updates-nav: the chip drops to the Macs still outdated", (await chip()) === "Hub update · 2 agents outdated", await chip());
  t.check("updates-all: the banner's bulk button is disabled at zero",
    await t.ev(`[...document.querySelectorAll("#fleet-banner button")].some((b) => b.textContent === "Update all outdated (0)" && b.disabled)`));
  await t.shot("updates-after");
  await t.aria("updates-after");
};
