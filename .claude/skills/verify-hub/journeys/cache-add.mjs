// features/cache-and-add.md, the read-only half: the cache list, downloads, affinity and Add a Mac.
// cache-delete.mjs and cache-eviction.mjs cover the mutations.
export default async (t) => {
  await t.nav("/#cache");
  await t.waitFor(`location.hash === "#/cache" && document.querySelectorAll("#cachelist .proj").length === 4`, 10000);
  const projs = await t.ev(`[...document.querySelectorAll("#cachelist .proj")].map((p) => p.dataset.proj + ":" + p.querySelectorAll("tr.file").length).join()`);
  t.check("cache-list: four projects with two artifacts each", projs === "demo:2,ledger:2,scanner:2,shop:2", projs);
  t.check("cache-list: newest by use first, and the head row counts versions",
    (await t.ev(`document.querySelector("#cachelist .proj tr.file").dataset.file`)) === "k0002-ios.app.tar.gz"
    && (await t.ev(`document.querySelector("#cachelist .proj").textContent`)).includes("2 versions"));
  const href = await t.ev(`document.querySelector("#cachelist a[download]").getAttribute("href")`);
  const got = await t.ev(`fetch(${JSON.stringify(href)}).then((r) => [r.status, r.headers.get("content-type")])`);
  t.check("cache-download: the Download link serves the artifact", href === "/cache/demo/k0002-ios.app.tar.gz" && got[0] === 200
    && got[1] === "application/octet-stream", JSON.stringify([href, got]));

  const aff = await t.ev(`[...document.querySelectorAll("#afflist tbody tr")].map((r) => [...r.cells].map((c) => c.textContent).join(" ")).join("|")`);
  t.check("cache-affinity: one row per project and platform",
    aff === "demo ios mac-alpha|ledger ios mac-beta|scanner android mac-alpha|shop ios mac-beta", aff);
  await t.shot("cache-view");
  await t.click(`#afflist a[href="#mac/mac-alpha"]`);
  await t.waitFor(`document.getElementById("drawer-title").textContent === "Mac mac-alpha"`, 3000);
  t.check("cache-affinity: a Mac link opens its drawer over Cache", (await t.ev("location.hash")) === "#/cache/mac/mac-alpha");
  await t.press("Escape");

  await t.nav("/#unir");
  await t.waitFor(`location.hash === "#/add" && document.querySelectorAll("#join code").length === 4`, 5000);
  const codes = await t.ev(`[...document.querySelectorAll("#join code")].map((c) => c.textContent)`);
  const st = await t.ev(`fetch("/api/state").then((r) => r.json()).then((s) => s.hub)`);
  t.check("add-commands: the two /join commands and the client add and remove",
    codes[0] === `curl -fsSL http://127.0.0.1:${st.tailnet_port}/join | bash`
    && codes[1] === `curl -fsSL http://${st.label}:${st.tailnet_port}/join | bash -s -- --slots 2`
    && codes[2] === "cider-build add <mac> [slots]" && codes[3] === "cider-build remove <mac>", JSON.stringify(codes));
  const notes = await t.ev(`[...document.querySelectorAll("#join p.note")].map((p) => p.textContent)`);
  t.check("add-commands: the intro names Macs and Linux machines", notes[0].startsWith("On the new Mac or Linux machine"), notes[0]);
  t.check("add-refused: the second-to-last note names who is refused",
    notes[notes.length - 2].endsWith(`The hub itself (${st.label}) refuses to join.`), notes[notes.length - 2]);
  t.check("add-linux: the last note explains Linux builders",
    notes[notes.length - 1].startsWith("A Linux machine (x86-64, with apt) builds Android only."), notes[notes.length - 1]);
  await t.click("#join .cmd button", "Copy");
  await t.waitFor(`document.querySelector("#toasts .toast")`, 3000);
  t.check("add-copy: Copy confirms with a toast",
    /^(Copied\.|Selected: copy it with Ctrl\+C)/.test(await t.ev(`document.querySelector("#toasts .toast").textContent`)));
  await t.shot("add-view");
};
