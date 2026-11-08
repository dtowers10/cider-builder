// features/macs.md, Linux builders: a Linux machine shows what it builds and no Xcode, Android stays off the Macs
// while it is in the pool, and Add a Mac explains Linux.
export default async (t) => {
  const card = (label) => `[...document.querySelectorAll("#maclist .card")].find((c) => c.querySelector("strong").textContent === ${JSON.stringify(label)})`;
  const row = (label, key) => t.ev(`(() => { const c = ${card(label)}; if (!c) return null;
    const dt = [...c.querySelectorAll("dt")].find((d) => d.textContent === ${JSON.stringify(key)}); return dt ? dt.nextElementSibling.textContent : null; })()`);

  await t.nav("/");
  await t.click(`#nav a[href="#/macs"]`);
  await t.waitFor(`!!(${card("linux-delta")})`, 5000);
  t.check("linux-card: the Linux machine builds Android only", (await row("linux-delta", "Builds")) === "Android (Linux)");
  t.check("linux-card: and shows no Xcode row", (await row("linux-delta", "Xcode")) === null);
  t.check("linux-card: its details name the distribution",
    await t.ev(`${card("linux-delta")}.querySelector(".info").textContent.includes("Ubuntu 24.04.3 LTS")`));
  t.check("linux-card: a Mac builds iOS and Android and keeps its Xcode row",
    (await row("mac-alpha", "Builds")) === "iOS, Android" && (await row("mac-alpha", "Xcode")) === "16.4");
  t.check("linux-card: a Mac without tools builds nothing yet", (await row("mac-epsilon", "Builds")) === "nothing yet");
  await t.shot("macs-with-linux");

  await t.click(`#maclist .card[href="#mac/linux-delta"]`);
  await t.waitFor(`!document.getElementById("drawer").hidden`, 3000);
  const drawer = await t.ev(`document.getElementById("drawer-body").textContent`);
  t.check("linux-drawer: the drawer shows Builds Android (Linux) and its build", drawer.includes("Android (Linux)") && drawer.includes("scanner"));
  await t.shot("drawer-linux");
  await t.press("Escape");

  const state = JSON.parse(await t.ev(`fetch("/api/state").then((r) => r.text())`));
  const android = state.active.filter((j) => j.plat === "android");
  t.check("linux-sched: no Android job runs on a Mac that was not already building it",
    android.every((j) => j.state === "queued" || j.worker === "linux-delta" || j.proj === "shop"),
    JSON.stringify(android.map((j) => [j.proj, j.state, j.worker])));
  t.check("linux-sched: Android jobs wait for the full Linux machine",
    android.filter((j) => j.state === "queued").length >= 1);

  await t.click(`#nav a[href="#/add"]`);
  t.check("linux-add: Add a Mac explains Linux builders",
    await t.ev(`document.getElementById("join").textContent.includes("A Linux machine (x86-64, with apt) builds Android only")`));
  await t.shot("add-linux");
};
