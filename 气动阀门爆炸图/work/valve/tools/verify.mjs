// End-to-end check against a running Chrome (CDP). Drives the real UI: balloons, BOM,
// valve-action button, slider, mobile layout — and screenshots each state.
import puppeteer from "puppeteer-core";
import path from "node:path";

const html = "file:///C:/work/codex_localAI/" + encodeURIComponent("气动蝶阀爆炸图.html");
const outDir = path.resolve(".shots");
const browser = await puppeteer.connect({ browserURL: "http://127.0.0.1:9222", defaultViewport: null });
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
const logs = [];
page.on("console", (m) => { if (m.type() !== "log") logs.push(`[${m.type()}] ${m.text()}`); });
page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));

await page.goto(html, { waitUntil: "load", timeout: 60000 });
await new Promise((r) => setTimeout(r, 2600)); // 开场动画 + 稳定
const report = {};

/* 1. 默认：爆炸 + 编号 */
report.default = await page.evaluate(() => ({
  diag: window.__diag(),
  bomOpen: !document.getElementById("bom").hidden,
  infoOpen: !document.getElementById("info").hidden,
  balloonTexts: [...document.querySelectorAll(".bln")].map((b) => b.textContent).join(","),
  chip: document.getElementById("chip").textContent,
  caption: document.getElementById("cap").textContent.slice(0, 40),
}));
await page.screenshot({ path: path.join(outDir, "i1-default.png") });

/* 2. 点第三个编号气泡 → 零件说明卡 */
await page.evaluate(() => document.querySelectorAll(".bln")[2].click());
await new Promise((r) => setTimeout(r, 900));
report.selectBalloon = await page.evaluate(() => ({
  infoOpen: !document.getElementById("info").hidden,
  title: document.getElementById("i-cn").textContent,
  mat: document.getElementById("i-mat").textContent,
  qty: document.getElementById("i-qty").textContent,
  desc: document.getElementById("i-desc").textContent.slice(0, 24),
  selRows: document.querySelectorAll("#bom-list .row.sel").length,
  selBalloons: document.querySelectorAll(".bln.sel").length,
}));
await page.screenshot({ path: path.join(outDir, "i2-select.png") });

/* 3. 点零件表里的「复位弹簧」一行 */
await page.evaluate(() => [...document.querySelectorAll("#bom-list .row")].find((r) => r.textContent.includes("复位弹簧")).click());
await new Promise((r) => setTimeout(r, 700));
report.selectRow = await page.evaluate(() => ({ title: document.getElementById("i-cn").textContent, no: document.getElementById("i-no").textContent }));

/* 4. 动作演示：开阀 */
await page.evaluate(() => document.getElementById("i-close").click());
await page.evaluate(() => document.getElementById("b-act").click());
await new Promise((r) => setTimeout(r, 2200));
report.open = await page.evaluate(() => ({
  chip: document.getElementById("chip").textContent,
  stroke: window.__dbv.state.stroke,
  caption: document.getElementById("cap").textContent.slice(0, 26),
  btn: document.getElementById("b-act-t").textContent,
}));
await page.screenshot({ path: path.join(outDir, "i3-open.png") });

/* 5. 装配态（滑到 0） */
await page.evaluate(() => {
  const r = document.getElementById("r-ex");
  r.value = "0";
  r.dispatchEvent(new Event("input", { bubbles: true }));
});
await new Promise((r) => setTimeout(r, 1200));
report.assembled = await page.evaluate(() => ({ t: window.__dbv.state.t, labelsVisible: getComputedStyle(document.getElementById("balloons")).visibility }));
await page.screenshot({ path: path.join(outDir, "i4-assembled.png") });

/* 6. 关掉零件表，看点击画布拾取 */
await page.evaluate(() => document.getElementById("b-bom").click());
await new Promise((r) => setTimeout(r, 600));
const geo = await page.evaluate(() => {
  const c = document.getElementById("c").getBoundingClientRect();
  // 取「阀体」第一个实例中心的屏幕坐标
  const T = window.THREE, b = new T.Box3(), part = window.__dbv.PARTS[0];
  b.expandByObject(part.insts[0].g);
  const p = b.getCenter(new T.Vector3()).project(window.__dbv.camera);
  return { x: c.left + ((p.x + 1) / 2) * c.width, y: c.top + ((1 - p.y) / 2) * c.height };
});
await page.mouse.click(geo.x, geo.y);
await new Promise((r) => setTimeout(r, 800));
report.pickCanvas = await page.evaluate(() => ({ title: document.getElementById("i-cn").textContent, open: !document.getElementById("info").hidden }));

/* 7. 手机布局 */
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await new Promise((r) => setTimeout(r, 1600));
await page.screenshot({ path: path.join(outDir, "i5-mobile.png") });
report.mobile = await page.evaluate(() => ({
  canvas: [document.getElementById("c").clientWidth, document.getElementById("c").clientHeight],
  bomHidden: document.getElementById("bom").hidden,
  ctrl: document.getElementById("ctrl").getBoundingClientRect().height,
}));

report.logs = logs;
console.log(JSON.stringify(report, null, 1));
await page.close();
await browser.disconnect();
