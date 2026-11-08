const PROJ = "warmproj";

export default async (t) => {
  await t.nav("/#/board");
  await t.waitFor(`document.querySelectorAll("#board-queue li, #board-lanes .cell.job").length > 0`, 5000);
  const rows = () => t.ev(`[...document.querySelectorAll("#board-queue li, #board-lanes .cell.job")]
    .filter((r) => r.textContent.includes(${JSON.stringify(PROJ)})).map((r) => r.textContent.replace(/\\s+/g, " ").trim())`);
  const found = await rows();
  t.check("warm-queue: both warmed platforms are on the Board, in the queue or in a slot",
    found.length === 2 && found.some((r) => r.includes("ios")) && found.some((r) => r.includes("android")), JSON.stringify(found));
  t.check("warm-queue: neither is marked as missing its source", found.every((r) => !r.includes("no source")), JSON.stringify(found));
  await t.shot("warm-queue");

  const id = await t.ev(`[...document.querySelectorAll("#board-queue li, #board-lanes .cell.job")]
    .find((r) => r.textContent.includes(${JSON.stringify(PROJ)}) && r.textContent.includes("ios"))?.dataset.id`);
  await t.click(`a[href="#job/${id}"]`);
  await t.waitFor(`!document.getElementById("drawer").hidden`, 5000);
  const title = await t.ev(`document.getElementById("drawer-title").textContent`);
  const body = await t.ev(`document.getElementById("drawer-body").textContent`);
  t.check("warm-drawer: the warmed job opens in the drawer", title.includes(id), title);
  t.check("warm-drawer: it shows the project and that the source is uploaded",
    body.includes(PROJ) && /Source uploaded\s*yes/.test(body), body.slice(0, 300));
  await t.shot("warm-drawer");
};
