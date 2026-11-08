// features/updates.md, updates off: a run started with `hubctl.py up --no-updates`, whose hub.json has update_url off.
// The hub section says so and shows the command that turns updates on; agents still update from the hub.
export default async (t) => {
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const row = (label) => `[...document.querySelectorAll("#up-agents tbody tr")].find((r) => r.querySelector("td").textContent === ${JSON.stringify(label)})`;
  const navCount = () => t.ev(`document.querySelector('#nav a[href="#/updates"] .nav-count').textContent`);

  await t.nav("/");
  const rel = (await state()).release;
  t.check("updates-off: /api/state has no update source and the hub never checked", rel.source === null && rel.checked === null,
    JSON.stringify(rel));
  t.check("updates-off-nav: the Updates entry counts the outdated agents and has no hub dot",
    await t.waitFor(`/6/.test(document.querySelector('#nav a[href="#/updates"] .nav-count').textContent)`, 8000)
    && !(await navCount()).includes("hub update available"), await navCount());

  await t.click('#nav a[href="#/updates"]');
  await t.waitFor(`document.getElementById("up-hub").textContent.includes("Hub updates are off")`, 8000);
  const hub = await t.ev(`document.getElementById("up-hub").textContent`);
  t.check("updates-off: the hub section says updates are off and names no git host",
    hub.includes("Hub updates are off: this hub has no update source.") && !/github/i.test(hub), hub);
  t.check("updates-off: it shows the command that turns them on, with a Copy button",
    await t.ev(`[...document.querySelectorAll("#up-hub .cmd")].some((c) => c.querySelector("code").textContent ===
      "bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>" && c.querySelector("button").textContent === "Copy")`));
  t.check("updates-off: no Check for updates or Update hub button",
    await t.ev(`[...document.querySelectorAll("#up-hub button")].every((b) => b.textContent === "Copy")`));
  await t.shot("updates-off-hub");

  await t.click(`#up-agents tbody tr:nth-child(${await t.ev(`[...document.querySelectorAll("#up-agents tbody tr")].indexOf(${row("mac-beta")}) + 1`)}) button`, "Update agent");
  await t.click("#confirm-yes");
  await t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent.includes("Update mac-beta: updating mac-beta"))`, 5000);
  await t.waitFor(`${row("mac-beta")}.textContent.includes("current")`, 10000);
  const beta = (await state()).workers.find((w) => w.label === "mac-beta");
  t.check("updates-off-agent: Update agent on mac-beta still reaches current, and /api/state agrees",
    beta.agent_current && !beta.update && beta.version === (await state()).agent, JSON.stringify(beta));
  await t.shot("updates-off-after");
};
