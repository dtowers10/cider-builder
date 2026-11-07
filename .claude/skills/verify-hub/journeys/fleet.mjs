export default async (t) => {
  const text = (sel) => t.ev(`document.querySelector(${JSON.stringify(sel)})?.textContent.replace(/\\s+/g, " ").trim()`);
  const state = () => t.ev(`fetch("/api/state").then((r) => r.json())`);
  const beta = async () => (await state()).workers.find((w) => w.label === "mac-beta");
  const toast = (s) => t.waitFor(`[...document.querySelectorAll("#toasts .toast")].some((e) => e.textContent === ${JSON.stringify(s)})`, 5000);
  const badge = () => text("#drawer-body .kv .badge");

  await t.nav("/#/fleet");
  await t.waitFor(`document.querySelectorAll("#maclist .card").length === 5`, 8000);
  const cards = await t.ev(`[...document.querySelectorAll("#maclist .card")].map((c) => [c.dataset.id, c.querySelector(".badge").textContent, c.textContent.replace(/\\s+/g, " ").trim()])`);
  t.check("fleet-cards: one two-line card per Mac with its state badge",
    cards.map((c) => c[0] + ":" + c[1]).join() === "mac-alpha:online,mac-beta:online,mac-epsilon:missing tools,mac-gamma:no heartbeat,mac-zeta:disabled", JSON.stringify(cards));
  t.check("fleet-cards: an online card says slots, RAM, Xcode and what it builds",
    cards[0][2] === "mac-alpha online 2/2 slots · 22 GB free · Xcode 16.4 · building demo ios, shop android agent outdated", cards[0][2]);
  t.check("fleet-cards: a Mac that takes no builds says why, with Why or Enable",
    cards[2][2].includes("missing tools · Why") && /no heartbeat · lost 1 h ago · Why/.test(cards[3][2]) && cards[4][2].includes("disabled · Enable"), JSON.stringify(cards.slice(2)));
  t.check("fleet-cards: an agent that cannot update itself says to run cider-build add",
    cards[4][2].includes("agent outdated: run cider-build add mac-zeta once"), cards[4][2]);
  await t.shot("fleet");

  await t.click('#maclist a[href="#mac/mac-beta"]');
  await t.waitFor(`!document.getElementById("drawer").hidden && document.getElementById("drawer-body").textContent.includes("Change slots")`, 5000);
  t.check("fleet-drawer: the card opens the Mac over Fleet",
    (await text("#drawer-title")) === "Mac mac-beta" && (await t.ev("location.hash")) === "#/fleet/mac/mac-beta");
  const body = await text("#drawer-body");
  t.check("fleet-drawer: it lists what it builds, its last jobs and its affinity",
    body.includes("Building here") && body.includes("ledger") && body.includes("Last 20 jobs") && body.includes("Affinity"), body.slice(0, 200));
  t.check("fleet-drawer: an online Mac has no reason paragraph", !(await t.ev(`!!document.querySelector("#drawer-body p.note")`)));

  await t.type("#drawer-body input[type=number]", "3");
  await t.click("#drawer-body button", "Change slots");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("fleet-slots: the confirmation names the change", (await text("#confirm-title")) === "Change slots on mac-beta" && (await text("#confirm-body")).includes("From 1 to 3 slots"));
  await t.shot("slots-confirm");
  await t.click("#confirm-no");
  t.check("fleet-slots: Keep it changes nothing", (await beta()).slots === 1);
  t.check("fleet-slots: the typed value survives the poll", (await t.ev(`document.querySelector("#drawer-body input[type=number]").value`)) === "3");
  await t.click("#drawer-body button", "Disable");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await toast("Disable mac-beta: running 1");
  await t.waitFor(`document.querySelector("#drawer-body .kv .badge")?.textContent === "disabled"`, 6000);
  t.check("fleet-disable: the drawer badge reads disabled and the slots field locks",
    (await badge()) === "disabled" && await t.ev(`document.querySelector("#drawer-body input[type=number]").disabled`)
    && (await text("#drawer-body .toolbar")).includes("enable it first") && !(await beta()).enabled);
  t.check("fleet-disable: the Board shows the build it still finishes, plus the Enable action",
    (await t.ev(`document.querySelector('#board-lanes .lane[data-id="mac-beta"] .cell.off')?.textContent`)) === "disabled · Enable"
    && (await t.ev(`document.querySelectorAll('#board-lanes .lane[data-id="mac-beta"] .cell.job').length`)) === 1);
  await t.shot("disable-after");

  await t.click("#drawer-body button", "Enable");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("fleet-enable: it offers the previous slots", (await text("#confirm-body")).includes("With its previous 1 slots."));
  await t.click("#confirm-yes");
  await toast("Enable mac-beta: mac-beta 1");
  await t.waitFor(`document.querySelector("#drawer-body .kv .badge")?.textContent === "online"`, 6000);
  t.check("fleet-enable: the badge returns to online and /api/state agrees", (await beta()).enabled && (await beta()).slots === 1);

  await t.type("#drawer-body input[type=number]", "3");
  await t.click("#drawer-body button", "Change slots");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await toast("Slots on mac-beta: mac-beta 3");
  await t.waitFor(`fetch("/api/state").then((r) => r.json()).then((s) => s.workers.find((w) => w.label === "mac-beta").slots === 3)`, 5000);
  t.check("fleet-slots: /api/state has 3 slots", true);
  await t.waitFor(`/\\d in use of 3/.test(document.getElementById("drawer-body").textContent)`, 5000);
  t.check("fleet-slots: the drawer shows them (and the hub may give the free slots queued builds at once)", true);
  await t.shot("slots-after");

  await t.type("#drawer-body input[type=number]", "1");
  await t.click("#drawer-body button", "Change slots");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await toast("Slots on mac-beta: mac-beta 1");
  await t.waitFor(`fetch("/api/state").then((r) => r.json()).then((s) => s.workers.find((w) => w.label === "mac-beta").slots === 1)`, 5000);
  t.check("fleet-slots: restored to 1", true);
  await t.click("#drawer-close");
  t.check("fleet-drawer: Close returns focus to the card link",
    (await t.ev(`document.activeElement.getAttribute("href")`)) === "#mac/mac-beta");
};
