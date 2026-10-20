import puppeteer from "puppeteer-core";
const html = "file:///C:/work/codex_localAI/" + encodeURIComponent("气动蝶阀爆炸图.html");
const browser = await puppeteer.connect({ browserURL: "http://127.0.0.1:9222", defaultViewport: null });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
await page.goto(html + "#t=1", { waitUntil: "load" });
await new Promise(r => setTimeout(r, 2500));
const out = await page.evaluate(() => {
  const T = window.THREE, b = new T.Box3();
  for (const m of window.__dbv.MESHES) b.expandByObject(m);
  const c = b.getCenter(new T.Vector3());
  const p = c.clone().project(window.__dbv.camera);
  const cv = document.getElementById("c").getBoundingClientRect();
  return {
    diag: window.__diag(),
    box: [b.min.toArray().map(Math.round), b.max.toArray().map(Math.round)],
    centerPx: [Math.round(cv.left + (p.x + 1) / 2 * cv.width), Math.round(cv.top + (1 - p.y) / 2 * cv.height)],
    canvasRect: [cv.left, cv.top, cv.width, cv.height],
    infoTop: document.getElementById("info").getBoundingClientRect().top,
    infoBottom: document.getElementById("info").getBoundingClientRect().bottom,
  };
});
console.log(JSON.stringify(out, null, 1));
await page.screenshot({ path: ".shots/m1.png" });
await page.close(); await browser.disconnect();
