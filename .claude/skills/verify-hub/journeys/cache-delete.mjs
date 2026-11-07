// Cache invalidation and project deletion from Cache & affinity (bin/cider-build-hub delete_cache).
// It deletes from the cache of the run, so use a fresh run or one whose first listed project has 2+ artifacts.
const first = `document.querySelector("#cachelist .proj")`;
const firstName = `${first}.querySelector(".proj-head .mono").textContent`;
const rows = `${first}.querySelectorAll("tbody tr").length`;
const lastToast = `[...document.querySelectorAll("#toasts .toast")].map((e) => e.textContent).pop() || ""`;

export default async (t) => {
  await t.nav("/#/cache");
  await t.waitFor(`${first} && ${rows} >= 2`, 10000);
  const proj = await t.ev(firstName);
  const file = await t.ev(`${first}.querySelector("tbody td").textContent`);
  const before = await t.ev(rows);
  await t.click("#cachelist button", "Invalidate");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  const body = await t.ev(`document.getElementById("confirm-body").textContent`);
  t.check("cache-invalidate: the confirmation names the rebuild, the failed download and CIDER_BUILD_FORCE=1",
    body.includes("rebuilds it on a Mac") && body.includes("must run cider-build again") && body.includes("CIDER_BUILD_FORCE=1"), body);
  await t.shot("cache-invalidate-confirm");
  await t.click("#confirm-yes");
  await t.waitFor(`${rows} === ${before - 1}`, 10000);
  t.check("cache-invalidate: toast confirms the deletion", (await t.ev(lastToast)) === `Invalidate ${file}: deleted ${proj}/${file}`, await t.ev(lastToast));
  t.check("cache-invalidate: the artifact is gone from the list", !(await t.ev(`${first}.textContent`)).includes(file));

  const blocks = await t.ev(`document.querySelectorAll("#cachelist .proj").length`);
  const left = await t.ev(rows);
  await t.click("#cachelist .proj-head button", "Delete all");
  await t.waitFor(`document.getElementById("confirm").open`, 3000);
  await t.click("#confirm-yes");
  await t.waitFor(`document.querySelectorAll("#cachelist .proj").length === ${blocks - 1}`, 10000);
  const plural = left === 1 ? "" : "s";
  t.check("cache-delete-project: toast confirms the deletion",
    (await t.ev(lastToast)) === `Delete cache of ${proj}: deleted ${left} artifact${plural} of ${proj}`, await t.ev(lastToast));
  t.check("cache-delete-project: the project drops out of the list", (await t.ev(firstName)) !== proj);
  await t.shot("cache-after-delete");
};
