// Cache eviction (bin/cider-build-hub prune_cache): after a prune, Cache & affinity lists exactly what
// /api/cache and the disk hold, newest by use first, and none of the pruned artifacts.
// Run after pruning demo on a hub started with CIDER_BUILD_CACHE_KEEP=3; set PRUNED to the names pruned
// (comma-separated) and KEPT to the ios artifacts expected, newest first. Check that a pruned
// artifact's /cache/demo/<name> is 404 with curl: a 404 fetched from the page counts as a console error.
const PRUNED = (process.env.PRUNED || "").split(",").filter(Boolean);
const KEPT = (process.env.KEPT || "").split(",").filter(Boolean);

export default async (t) => {
  await t.nav("/");
  await t.click('#nav a[href="#/cache"]');
  await t.waitFor(`document.querySelectorAll("#cachelist .proj").length > 0`, 10000);
  const rows = `[...document.querySelectorAll("#cachelist .proj")].find((p) => p.querySelector(".proj-head .mono").textContent === "demo")`;
  const shown = await t.ev(`[...${rows}.querySelectorAll("tbody tr td:first-child")].map((td) => td.textContent)`);
  const api = await t.ev(`fetch("/api/cache").then((r) => r.json()).then((c) => c.projects.find((p) => p.proj === "demo").files.map((f) => f.name))`);
  t.check("cache-eviction: the panel lists the same demo files as /api/cache, in the same order", JSON.stringify(shown) === JSON.stringify(api), JSON.stringify(shown));
  t.check("cache-eviction: no pruned artifact is listed", PRUNED.every((n) => !shown.includes(n)), PRUNED.join());
  const ios = shown.filter((n) => n.endsWith("-ios.app.tar.gz"));
  t.check("cache-eviction: the kept ios artifacts, newest by use first", JSON.stringify(ios) === JSON.stringify(KEPT), JSON.stringify(ios));
  await t.ev(`${rows}.scrollIntoView()`);
  await t.shot("cache-after-prune");
};
