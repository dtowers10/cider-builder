// features/updates.md: the Updates view on a seeded run (its repository is one commit ahead of what the hub
// runs, and mac-alpha, mac-beta and mac-epsilon run an old agent that can update itself; mac-zeta cannot).
// Updates mac-beta from its row, mac-epsilon from its drawer and the rest with "Update all outdated".
// Never clicks "Update hub": the seeded hub has no launchd to start it again (verification/hub-update.py proves it).
const SUBJECT = "Panel: show each build's estimated time left";

export default async (t) => {
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const mac = async (label) => (await state()).workers.find((w) => w.label === label);
  const row = (label) => `[...document.querySelectorAll("#up-agents tbody tr")].find((r) => r.querySelector("td").textContent === ${JSON.stringify(label)})`;
  const rowText = (label) => t.ev(`${row(label)}?.textContent.replace(/\\s+/g, " ").trim()`);
  const rowIndex = (label) => t.ev(`[...document.querySelectorAll("#up-agents tbody tr")].indexOf(${row(label)}) + 1`);
  const toast = (text) => t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent.includes(${JSON.stringify(text)}))`, 5000);
  // Records every Mac whose row showed "updating", even if the fake Mac reports the new version a beat later.
  const watch = () => t.ev(`window.sawUpdating = new Set(); new MutationObserver(() => {
      for (const r of document.querySelectorAll("#up-agents tbody tr"))
        if (r.querySelector(".b-updating")) window.sawUpdating.add(r.querySelector("td").textContent);
    }).observe(document.getElementById("up-agents"), { childList: true, subtree: true }); true`);

  await t.nav("/");
  t.check("updates-nav: the Updates entry has a dot for the hub and a count of outdated agents",
    await t.waitFor(`/hub update available/.test(document.querySelector('#nav a[href="#/updates"] .nav-count').textContent)`, 8000)
    && (await t.ev(`document.querySelector('#nav a[href="#/updates"] .nav-count').textContent`)).includes("5"));
  await t.click('#nav a[href="#/updates"]');
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
  t.check("updates-hub: Update hub is enabled and Check for updates too",
    await t.ev(`[...document.querySelectorAll("#up-hub button")].every((b) => !b.disabled)`));
  await t.shot("updates-hub-available");

  await t.click("#up-hub button", "Check for updates");
  await toast("Check for updates: checking");
  t.check("updates-check: Check for updates answers with a toast", true);
  await t.waitFor(`fetch("/api/state").then((r) => r.json()).then((s) => s.release.phase === "idle" && s.release.checked > ${rel.checked})`, 10000);
  t.check("updates-check: /api/state has a newer check, still 1 behind", ((s) => s.available && s.behind === 1)((await state()).release));

  t.check("updates-agents: mac-beta is outdated with an Update agent button", /2026\.10\.3 \(outdated\).*Update agent/.test(await rowText("mac-beta")), await rowText("mac-beta"));
  t.check("updates-agents: mac-zeta, too old to update itself, says to run cider-build add",
    (await rowText("mac-zeta")).includes("run cider-build add mac-zeta once"), await rowText("mac-zeta"));
  await t.click(`#up-agents tbody tr:nth-child(${await rowIndex("mac-beta")}) button`, "Update agent");
  await t.shot("updates-confirm-agent");
  await t.click("#confirm-no");
  t.check("updates-agent-refuse: Keep it changes nothing", !(await mac("mac-beta")).update && !(await mac("mac-beta")).agent_current);

  await watch();
  await t.click(`#up-agents tbody tr:nth-child(${await rowIndex("mac-beta")}) button`, "Update agent");
  await t.click("#confirm-yes");
  await toast("Update mac-beta: updating mac-beta");
  t.check("updates-agent: the toast confirms it", true);
  await t.waitFor(`window.sawUpdating.has("mac-beta")`, 5000);
  t.check("updates-agent: the row goes to updating", true);
  await t.waitFor(`${row("mac-beta")}.textContent.includes("current")`, 10000);
  const beta = await mac("mac-beta");
  t.check("updates-agent: then current, and /api/state agrees (version is the hub's agent, flag cleared, online)",
    beta.agent_current && !beta.update && beta.state === "online" && beta.version === (await state()).agent, JSON.stringify(beta));
  await t.shot("updates-beta-current");

  await t.click(`#up-agents tbody tr:nth-child(${await rowIndex("mac-epsilon")}) a`);
  await t.waitFor(`!document.getElementById("drawer").hidden && document.getElementById("drawer-body").textContent.includes("(outdated)")`, 5000);
  t.check("updates-drawer: the Mac's drawer marks its agent outdated", true);
  await t.click("#drawer-body button", "Update agent");
  await t.click("#confirm-yes");
  await toast("Update mac-epsilon: updating mac-epsilon");
  await t.waitFor(`!document.getElementById("drawer-body").textContent.includes("(outdated)")`, 10000);
  t.check("updates-drawer: Update agent from the drawer brings it current", (await mac("mac-epsilon")).agent_current);
  await t.shot("updates-drawer-epsilon");
  await t.click("#drawer-close");

  t.check("updates-all: one outdated Mac left that can update", await t.ev(`[...document.querySelectorAll("#up-agents button")].some((b) => b.textContent === "Update all outdated (1)")`));
  await t.click("#up-agents button", "Update all outdated (1)");
  await t.click("#confirm-yes");
  await toast("Update all: 1 updating");
  await t.waitFor(`${row("mac-alpha")}.textContent.includes("current")`, 10000);
  const s = await state();
  t.check("updates-all: every Mac that can update itself is current; mac-zeta still needs cider-build add",
    s.workers.filter((w) => w.self_update).every((w) => w.agent_current) && !s.workers.find((w) => w.label === "mac-zeta").agent_current,
    JSON.stringify(s.workers.map((w) => [w.label, w.agent_current])));
  t.check("updates-nav: the count drops to the Macs still outdated",
    (await t.ev(`document.querySelector('#nav a[href="#/updates"] .nav-count').textContent`)).includes("2"));
  await t.shot("updates-after");
  await t.aria("updates-after");
};
