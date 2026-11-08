// features/macs.md: cards, the drawer and its actions, on a fresh seeded run. The last part changes mac-beta's slots,
// disables and enables it, so run this journey on its own run or after the read-only ones.
const lastToast = `[...document.querySelectorAll("#toasts .toast")].map((e) => e.textContent).pop() || ""`;
const state = (label) => `fetch("/api/state").then((r) => r.json()).then((s) => s.workers.find((w) => w.label === ${JSON.stringify(label)}))`;
const badgeOf = (label) => `document.querySelector('#maclist a.card[href="#mac/${label}"] .badge')?.textContent`;
const input = "#drawer-body input[type=number]";

export default async (t) => {
  await t.nav("/#/macs");
  await t.waitFor(`document.querySelectorAll("#maclist .card").length === 6`, 5000);
  t.check("macs-cards: six machines, with the seeded badges",
    (await t.ev(badgeOf("mac-epsilon"))) === "missing tools" && (await t.ev(badgeOf("mac-gamma"))) === "no heartbeat"
    && (await t.ev(badgeOf("mac-zeta"))) === "disabled" && (await t.ev(badgeOf("linux-delta"))) === "online");
  t.check("macs-count: the sidebar Macs count reads 1 lost",
    (await t.ev(`document.querySelector('#nav a[href="#/macs"] .nav-count').textContent`)) === "1 lost");
  await t.shot("macs-cards");

  await t.ev(`location.hash = "#mac/mac-zeta"`);
  await t.waitFor(`document.getElementById("drawer-title").textContent === "Mac mac-zeta"`, 3000);
  const zeta = await t.ev(`document.getElementById("drawer-body").textContent`);
  t.check("macs-disabled: a disabled Mac offers Enable, says enable it first, and that its agent is too old",
    zeta.includes("enable it first") && zeta.includes("agent too old to update from here: run cider-build add mac-zeta once")
    && (await t.ev(`document.querySelector("${input}").disabled`)), zeta.slice(0, 300));
  await t.press("Escape");

  await t.ev(`location.hash = "#mac/nope"`);
  await t.waitFor(`!document.getElementById("drawer").hidden`, 3000);
  t.check("macs-unknown: the drawer for an unknown label says the hub doesn't list it",
    (await t.ev(`document.getElementById("drawer-body").textContent`)).includes("The hub doesn't list this Mac"));
  await t.press("Escape");

  await t.click(`#maclist a.card[href="#mac/mac-beta"]`);
  await t.waitFor(`document.getElementById("drawer-title").textContent === "Mac mac-beta"`, 3000);
  const beta = await t.ev(`document.getElementById("drawer-body").textContent`);
  t.check("macs-drawer: mac-beta's drawer has Building here with ledger, Last 20 jobs and Affinity",
    beta.includes("Building here") && beta.includes("ledger") && beta.includes("Last 20 jobs") && beta.includes("Affinity"));

  await t.type(input, "0");
  await t.click("#drawer-body button", "Change slots");
  t.check("macs-validate: 0 slots is refused", (await t.ev(lastToast)) === "Slots must be a number from 1 to 99.", await t.ev(lastToast));
  await t.type(input, "1");
  await t.click("#drawer-body button", "Change slots");
  t.check("macs-validate: the same number is a no-op", (await t.ev(lastToast)) === "It already has 1 slots.", await t.ev(lastToast));

  await t.type(input, "3");
  await t.click("#drawer-body button", "Change slots");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("macs-slots: the confirmation button reads Change to 3", (await t.ev(`document.getElementById("confirm-yes").textContent`)) === "Change to 3");
  await t.click("#confirm-no");
  t.check("macs-slots: Keep it changes nothing", (await t.ev(state("mac-beta"))).slots === 1);

  await t.type(input, "3");
  await t.click("#drawer-body button", "Change slots");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await t.waitFor(`(${lastToast}).startsWith("Slots on mac-beta")`, 5000);
  t.check("macs-slots: toast and /api/state show 3 slots",
    (await t.ev(lastToast)) === "Slots on mac-beta: mac-beta 3" && (await t.ev(state("mac-beta"))).slots === 3, await t.ev(lastToast));

  await t.click("#drawer-body button", "Disable");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("macs-remove: the Disable dialog points at cider-build remove",
    (await t.ev(`document.getElementById("confirm-body").textContent`)).includes("run cider-build remove mac-beta from a client"));
  await t.click("#confirm-yes");
  await t.waitFor(`(${lastToast}).startsWith("Disable mac-beta")`, 5000);
  t.check("macs-disable: toast reports its running build", (await t.ev(lastToast)) === "Disable mac-beta: running 1", await t.ev(lastToast));
  await t.waitFor(`[...document.querySelectorAll("#drawer-body button")].some((b) => b.textContent === "Enable")`, 5000);
  t.check("macs-disable: /api/state has it disabled and the drawer offers Enable", (await t.ev(state("mac-beta"))).enabled === false);
  await t.shot("macs-disabled");

  await t.click("#drawer-body button", "Enable");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  t.check("macs-enable: it comes back with its previous slots",
    (await t.ev(`document.getElementById("confirm-body").textContent`)).includes("With its previous 3 slots."));
  await t.click("#confirm-yes");
  await t.waitFor(`(${lastToast}).startsWith("Enable mac-beta")`, 5000);
  const back = await t.ev(state("mac-beta"));
  t.check("macs-enable: toast and /api/state show it enabled with 3 slots",
    (await t.ev(lastToast)) === "Enable mac-beta: mac-beta 3" && back.enabled && back.slots === 3, await t.ev(lastToast));
  await t.waitFor(`${badgeOf("mac-beta")} === "online"`, 5000);
  t.check("macs-enable: its card is online again", true);
};
