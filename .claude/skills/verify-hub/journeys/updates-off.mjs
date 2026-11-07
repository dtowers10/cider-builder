export default async (t) => {
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const chip = () => t.ev(`document.querySelector('#summary a[href="#/updates"]')?.textContent`);

  await t.nav("/");
  const rel = (await state()).release;
  t.check("updates-off: /api/state has no update source and the hub never checked", rel.source === null && rel.checked === null,
    JSON.stringify(rel));
  await t.waitFor(`/5 agents outdated/.test(document.querySelector('#summary a[href="#/updates"]')?.textContent)`, 8000);
  t.check("updates-off-nav: the chip counts the outdated agents and names no hub update", (await chip()) === "5 agents outdated", await chip());

  await t.click('#nav a[href="#/fleet"]');
  await t.waitFor(`document.getElementById("up-hub").textContent.includes("Hub updates are off")`, 8000);
  const hub = await t.ev(`document.getElementById("up-hub").textContent`);
  t.check("updates-off: the Updates section says updates are off and names no git host",
    hub.includes("Hub updates are off: this hub has no update source.") && !/github/i.test(hub), hub);
  t.check("updates-off: it shows the command that turns them on, with a Copy button",
    await t.ev(`[...document.querySelectorAll("#up-hub .cmd")].some((c) => c.querySelector("code").textContent ===
      "bash ~/cider-build/bin/install.sh hub --set update_url=<git URL>" && c.querySelector("button").textContent === "Copy")`));
  t.check("updates-off: no Check for updates or Update hub button",
    await t.ev(`[...document.querySelectorAll("#up-hub button, #fleet-banner button")].every((b) => b.textContent === "Copy" || b.textContent.startsWith("Update all outdated"))`));
  t.check("updates-off: the banner only lists the outdated agents",
    await t.ev(`document.getElementById("fleet-banner").textContent.includes("5 agents outdated") && !document.getElementById("fleet-banner").textContent.includes("Hub update")`));
  await t.shot("updates-off-hub");

  await t.click('#maclist a[href="#mac/mac-beta"]');
  await t.waitFor(`!document.getElementById("drawer").hidden && document.getElementById("drawer-body").textContent.includes("(outdated)")`, 5000);
  await t.click("#drawer-body button", "Update agent");
  await t.click("#confirm-yes");
  await t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent.includes("Update mac-beta: updating mac-beta"))`, 5000);
  await t.waitFor(`!/outdated|updating/.test(document.querySelector('#maclist .card[data-id="mac-beta"]').textContent)`, 10000);
  const beta = (await state()).workers.find((w) => w.label === "mac-beta");
  t.check("updates-off-agent: Update agent on mac-beta still reaches current, and /api/state agrees",
    beta.agent_current && !beta.update && beta.version === (await state()).agent, JSON.stringify(beta));
  await t.shot("updates-off-after");
};
