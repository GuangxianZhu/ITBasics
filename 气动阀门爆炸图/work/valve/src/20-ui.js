/* ============================================================================
   2 · 交互层：机位自适应、爆炸/动作动画、气泡编号、零件表、拾取与说明
   ========================================================================== */
const state = {
  t: 1,            // 爆炸进度 0 装配 / 1 全爆
  tTarget: null,   // 播放按钮驱动
  stroke: 0,       // 阀门动作 0 全关 / 1 全开
  strokeTarget: 0,
  labels: window.innerWidth >= 820,
  sel: null,
  hover: null,
  moved: false,
  shadowA: 0.22,
};
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* 缓动 + 依次入场：延迟 s 的零件在全爆进度后段才动，形成层次 */
const smooth = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const stagger = (t, s) => smooth(Math.min(1, Math.max(0, (t - s * 0.62) / 0.38)));

const tmpV = new V3();
function applyExplode() {
  const travel = state.stroke * STROKE;
  for (const p of PARTS) {
    for (const r of p.insts) {
      tmpV.set(0, 0, 0);
      for (const e of r.ex) tmpV.addScaledVector(e.v, stagger(state.t, e.s));
      if (r.slide) tmpV.z += r.slide * travel * 0.6;
      r.g.position.copy(r.base).add(tmpV);
      if (r.rot) r.g.rotation.y = r.baseRot + -r.rot * state.stroke * Math.PI * 0.5;
      if (r.spring) {
        const L = SPR_L0 - travel * 0.6;
        r.g.scale.z = L / SPR_L0;
      }
    }
  }
}

/* ------------------------------------------------------------- 版心与机位 */
const inset = { top: 0, bottom: 0, left: 0, right: 0 };
const elBom = document.getElementById("bom");
const elCtrl = document.getElementById("ctrl");
const elLeft = document.querySelector(".left");
const elTb = document.querySelector(".tb");
const elInfo = document.getElementById("info");

function measureInsets() {
  const app = document.getElementById("app").getBoundingClientRect();
  const ctrl = elCtrl.getBoundingClientRect();
  const tb = elTb.getBoundingClientRect();
  const narrow = app.width < 820;
  inset.bottom = Math.max(0, app.bottom - ctrl.top);
  inset.top = narrow ? Math.max(0, tb.bottom - app.top + 6) : 0;
  /* 窄屏时说明卡和零件表是盖在画布上的浮层：把被盖住的边算进内边距 */
  if (narrow && !elInfo.hidden) {
    inset.top = Math.max(inset.top, elInfo.getBoundingClientRect().bottom - app.top + 6);
  }
  if (narrow && !elBom.hidden) {
    inset.bottom = Math.max(inset.bottom, app.bottom - elBom.getBoundingClientRect().top + 6);
  }
  inset.right = !elBom.hidden && !narrow ? elBom.offsetWidth + 18 : 0;
  inset.left = !narrow && app.width >= 980 ? Math.min(app.width * 0.26, tb.right - app.left + 10) : 0;
}

const camDir = new V3(0.9, 0.86, 1.18).normalize();
let fitA = null;
let fitB = null;

/* 机位求解：把包围盒顶点投影到“安全区”（扣除标题栏/零件表/控制条后的矩形）里刚好装下。
   D ≥ (角点沿视线方向的深度) + (横向偏移换算出的距离)，一次解出，不再迭代试探。 */
function fitFor(t) {
  const prev = state.t;
  state.t = t;
  applyExplode();
  assembly.updateMatrixWorld(true);
  const w = canvas.clientWidth || 1;
  const h = canvas.clientHeight || 1;
  const pad = t > 0.5 ? (state.labels ? 34 : 18) : Math.min(48, w * 0.05);
  const safeW = Math.max(80, w - inset.left - inset.right - pad * 2);
  const safeH = Math.max(80, h - inset.top - inset.bottom - pad * 2);
  const cx = inset.left + safeW / 2 + pad;
  const cy = inset.top + safeH / 2 + pad;

  const box = new T.Box3();
  for (const m of MESHES) box.expandByObject(m);
  const C = box.getCenter(new V3());
  /* 逐网格取包围盒角点：比整体 AABB 贴合得多，斜放的爆炸图能占满画面 */
  const corners = [];
  for (const m of MESHES) {
    const g = m.geometry;
    if (!g.boundingBox) g.computeBoundingBox();
    const bb = g.boundingBox;
    for (const x of [bb.min.x, bb.max.x])
      for (const y of [bb.min.y, bb.max.y])
        for (const z of [bb.min.z, bb.max.z]) corners.push(new V3(x, y, z).applyMatrix4(m.matrixWorld));
  }

  const aspect = w / h;
  const tanHalf = Math.tan((camera.fov * Math.PI) / 360);
  const probe = new T.PerspectiveCamera(camera.fov, aspect, 1, 1e6);
  probe.position.copy(C).add(camDir);
  probe.lookAt(C);
  probe.updateMatrixWorld(true);
  const right = new V3().setFromMatrixColumn(probe.matrixWorld, 0);
  const up = new V3().setFromMatrixColumn(probe.matrixWorld, 1);

  const solve = (target) => {
    let D = 1;
    for (const c of corners) {
      const rx = c.x - target.x, ry = c.y - target.y, rz = c.z - target.z;
      const u = Math.abs(rx * right.x + ry * right.y + rz * right.z);
      const v = Math.abs(rx * up.x + ry * up.y + rz * up.z);
      const depth = rx * camDir.x + ry * camDir.y + rz * camDir.z;
      D = Math.max(D, depth + (u * w) / (safeW * tanHalf * aspect), depth + (v * h) / (safeH * tanHalf));
    }
    return D;
  };

  const target = C.clone();
  let dist = solve(target);
  for (let i = 0; i < 2; i++) {
    const wp = (2 * dist * tanHalf) / h;
    target.addScaledVector(right, (w / 2 - cx) * wp);
    target.addScaledVector(up, (cy - h / 2) * wp);
    dist = solve(target);
  }
  state.t = prev;
  applyExplode();
  return { target, dist: Math.max(dist * 1.02, 160), center: C, box };
}

function refit() {
  measureInsets();
  const o = fitA;
  fitA = fitFor(0);
  fitB = fitFor(1);
  state.t = o ? state.t : 1;
  applyExplode();
  camPlace(true);
  ground.position.y = fitA.box.min.y - 1;
  key.position.copy(fitA.box.getCenter(new V3())).add(new V3(240, 520, 300));
  key.target.position.copy(fitA.box.getCenter(new V3()));
  if (!state.moved) camera.position.copy(fitB.target).addScaledVector(camDir, fitB.dist);
}

const lerpT = new V3();
function camPlace(instant) {
  if (!fitA || !fitB) return;
  if (state.moved) return; // 用户接管视角后不抢镜头
  const k = smooth(Math.min(1, state.t / 0.82));
  lerpT.lerpVectors(fitA.target, fitB.target, k);
  const d = fitA.dist + (fitB.dist - fitA.dist) * k;
  controls.target.copy(lerpT);
  camera.position.copy(lerpT).addScaledVector(camDir, d);
  camera.near = Math.max(2, d / 60);
  camera.far = d * 8;
  camera.updateProjectionMatrix();
  if (instant) controls.update();
}

/* ------------------------------------------------------------------ 编号气泡 */
const SVG = "http://www.w3.org/2000/svg";
const elLeaders = document.getElementById("leaders");
const elBalloons = document.getElementById("balloons");
const bubble = PARTS.map((p) => {
  const b = document.createElement("button");
  b.className = "bln";
  b.type = "button";
  b.textContent = p.no;
  b.setAttribute("aria-label", `${p.no} ${p.cn}`);
  b.addEventListener("click", (e) => { e.stopPropagation(); select(p); });
  elBalloons.appendChild(b);
  const ln = document.createElementNS(SVG, "line");
  const dot = document.createElementNS(SVG, "circle");
  dot.setAttribute("r", "2");
  elLeaders.append(ln, dot);
  return { p, b, ln, dot, x: 0, y: 0, tx: 0, ty: 0, ax: 0, ay: 0, off: false, init: false };
});

const projTmp = new V3();
function project(p) {
  projTmp.copy(p).project(camera);
  return [((projTmp.x + 1) / 2) * (canvas.clientWidth || 1), ((1 - projTmp.y) / 2) * (canvas.clientHeight || 1)];
}

const boxTmp = new T.Box3();
function updateBalloons() {
  const vis = state.labels ? Math.min(1, Math.max(0, (state.t - 0.5) / 0.28)) : 0;
  elBalloons.style.opacity = vis;
  elLeaders.style.opacity = vis;
  elBalloons.style.visibility = elLeaders.style.visibility = vis > 0 ? "visible" : "hidden";
  if (vis <= 0) {
    for (const l of bubble) l.init = false;
    return;
  }
  const w = canvas.clientWidth || 1;
  const h = canvas.clientHeight || 1;
  const [cx, cy] = project(boxTmp.copy(box).getCenter(new V3()));

  for (const l of bubble) {
    const inst = l.p.insts[0];
    boxTmp.makeEmpty().expandByObject(inst.g);
    const [ax, ay] = project(boxTmp.getCenter(new V3()));
    l.ax = ax; l.ay = ay;
    l.off = ax < -40 || ax > w + 40 || ay < -40 || ay > h + 40;
    let dx = ax - cx, dy = ay - cy;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len; dy /= len;
    l.tx = ax + dx * 52;
    l.ty = ay + dy * 46;
    if (!l.init) { l.x = l.tx; l.y = l.ty; }
    l.nx = l.x + (l.tx - l.x) * 0.55;
    l.ny = l.y + (l.ty - l.y) * 0.55;
  }
  const m = 16;
  const x0 = m, x1 = w - inset.right - m, y0 = inset.top + m, y1 = h - inset.bottom - m;
  for (let iter = 0; iter < 8; iter++) {
    for (let i = 0; i < bubble.length; i++) {
      for (let j = i + 1; j < bubble.length; j++) {
        const a = bubble[i], b = bubble[j];
        if (a.off || b.off) continue;
        let dx = b.nx - a.nx, dy = b.ny - a.ny;
        const d = Math.hypot(dx, dy);
        if (d < 30) {
          if (d < 0.01) { dx = 1; dy = 0; }
          const push = (30 - d) / 2 / (d || 1);
          a.nx -= dx * push; a.ny -= dy * push;
          b.nx += dx * push; b.ny += dy * push;
        }
      }
    }
    for (const l of bubble) {
      l.nx = Math.min(x1, Math.max(x0, l.nx));
      l.ny = Math.min(y1, Math.max(y0, l.ny));
    }
  }
  for (const l of bubble) {
    l.x = l.nx; l.y = l.ny; l.init = true;
    l.b.hidden = l.off;
    l.ln.style.display = l.dot.style.display = l.off ? "none" : "";
    l.b.style.transform = `translate(${l.x.toFixed(1)}px,${l.y.toFixed(1)}px)`;
    const dx = l.x - l.ax, dy = l.y - l.ay;
    const d = Math.hypot(dx, dy) || 1;
    const ex = l.x - (dx / d) * 11.5, ey = l.y - (dy / d) * 11.5;
    l.ln.setAttribute("x1", l.ax.toFixed(1)); l.ln.setAttribute("y1", l.ay.toFixed(1));
    l.ln.setAttribute("x2", ex.toFixed(1)); l.ln.setAttribute("y2", ey.toFixed(1));
    l.dot.setAttribute("cx", l.ax.toFixed(1)); l.dot.setAttribute("cy", l.ay.toFixed(1));
    const on = state.sel === l.p;
    l.b.classList.toggle("sel", on);
    l.ln.classList.toggle("sel", on);
    l.dot.classList.toggle("sel", on);
  }
}
let box = new T.Box3();

/* ------------------------------------------------------------------ 高亮 */
function paint() {
  for (const m of MESHES) {
    const p = m.userData.part;
    if (p === state.sel) { m.material.emissive.copy(hlColor); m.material.emissiveIntensity = 0.6; }
    else if (p === state.hover) { m.material.emissive.copy(hlColor); m.material.emissiveIntensity = 0.22; }
    else m.material.emissiveIntensity = 0;
  }
}

/* ------------------------------------------------------------------ 零件表 */
const elList = document.getElementById("bom-list");
document.getElementById("bom-count").textContent = `${PARTS.length} 种 · ${PARTS.reduce((n, p) => n + p.qty, 0)} 件`;
const rows = PARTS.map((p) => {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "row";
  b.innerHTML = `<span class="n">${p.no}</span><span class="nm"><b>${p.cn}</b><span>${p.jp}</span></span><span class="q">×${p.qty}</span><span class="m">${p.mat}</span>`;
  b.addEventListener("click", () => select(p));
  elList.appendChild(b);
  return { p, el: b };
});

/* ------------------------------------------------------------------ 选中 */
const elHint = document.getElementById("hint");
function select(p) {
  state.sel = p;
  paint();
  for (const r of rows) r.el.classList.toggle("sel", r.p === p);
  const wasHidden = elInfo.hidden;
  if (!p) {
    elInfo.hidden = true;
    elHint.hidden = false;
    if (!wasHidden && innerWidth < 820) refit();
    return;
  }
  document.getElementById("i-no").textContent = p.no;
  document.getElementById("i-cn").textContent = p.cn;
  document.getElementById("i-jp").textContent = p.jp;
  document.getElementById("i-en").textContent = p.en;
  document.getElementById("i-mat").textContent = p.mat;
  document.getElementById("i-qty").textContent = p.qty + " 件";
  document.getElementById("i-desc").textContent = p.desc;
  elInfo.hidden = false;
  elHint.hidden = true;
  if (innerWidth < 820) { if (elBom.hidden) refit(); else toggleBom(false); }
}
document.getElementById("i-close").addEventListener("click", () => select(null));

/* ------------------------------------------------------------------ 拾取 */
const ray = new T.Raycaster();
const ndc = new V2();
function pickAt(ev) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects(MESHES, false)[0];
  return hit ? hit.object.userData.part : null;
}
let down = null;
canvas.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener("pointerup", (e) => {
  if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 6) select(pickAt(e));
  down = null;
});
canvas.addEventListener("pointermove", (e) => {
  if (e.pointerType !== "mouse" || e.buttons) return;
  const p = pickAt(e);
  if (p !== state.hover) {
    state.hover = p;
    paint();
    canvas.style.cursor = p ? "pointer" : "";
  }
});
canvas.addEventListener("pointerleave", () => {
  if (state.hover) { state.hover = null; paint(); canvas.style.cursor = ""; }
});

/* ------------------------------------------------------------------ 控件 */
const elBomBtn = document.getElementById("b-bom");
function toggleBom(on) {
  elBom.hidden = !on;
  elBomBtn.setAttribute("aria-pressed", String(on));
  measureInsets();
  refit();
}
elBomBtn.addEventListener("click", () => toggleBom(elBom.hidden));
document.getElementById("bom-close").addEventListener("click", () => toggleBom(false));

const elRange = document.getElementById("r-ex");
const elOut = document.getElementById("o-ex");
const elPlayT = document.getElementById("b-play-t");
function syncSlider() {
  const v = Math.round(state.t * 100);
  elRange.value = v;
  elOut.textContent = v + "%";
  elPlayT.textContent = state.t > 0.5 ? "装配" : "爆炸";
}
elRange.addEventListener("input", () => {
  state.tTarget = null;
  state.t = elRange.value / 100;
  syncSlider();
});
document.getElementById("b-play").addEventListener("click", () => {
  const to = state.t > 0.5 ? 0 : 1;
  if (reduce) { state.t = to; syncSlider(); applyExplode(); camPlace(true); return; }
  state.tTarget = to;
});
document.getElementById("b-lbl").addEventListener("click", (e) => {
  state.labels = !state.labels;
  e.currentTarget.setAttribute("aria-pressed", String(state.labels));
  document.getElementById("app").classList.toggle("no-lbl", !state.labels);
  measureInsets();
  refit();
});
document.getElementById("b-view").addEventListener("click", () => {
  state.moved = false;
  refit();
});

/* 阀门动作 */
const elChip = document.getElementById("chip");
const elCap = document.getElementById("cap");
const elActT = document.getElementById("b-act-t");
const CAP = {
  closed: "<b>当前全关。</b>弹簧把两只活塞推向中间，齿条带动齿轮轴把蝶板转成与流向垂直，橡胶衬里被压紧。断气后靠弹簧保持关闭，所以停电、断气会自动关阀（失气关 FC）。",
  opening: "<b>开阀中：</b>线圈通电、电磁阀换向，压缩空气进入执行器中间腔 → 两只活塞被推向两端并压缩弹簧 → 齿条带动齿轮轴转 90° → 蝶板转到与流向平行。",
  open: "<b>当前全开。</b>蝶板与流向平行，流道几乎无阻挡。此时弹簧被压到最短，储能最多——一旦断气或断电，阀门会立刻自行关闭。",
  closing: "<b>关阀中：</b>电磁阀断电，中间腔经消声器排气 → 弹簧把两只活塞推回中间 → 齿轮轴反向转 90° → 蝶板压住衬里，流道被封死。",
};
function caption(kind) {
  elChip.className = "chip " + (kind === "opening" || kind === "closing" ? "moving" : kind);
  elChip.textContent = kind === "open" ? "全开" : kind === "closed" ? "全关" : "动作中";
  elCap.innerHTML = CAP[kind];
}
function setStrokeTarget(to) {
  state.strokeTarget = to;
  elActT.textContent = to ? "关阀" : "开阀";
  if (reduce) {
    state.stroke = to;
    caption(to ? "open" : "closed");
    applyExplode();
    return;
  }
  caption(to ? "opening" : "closing");
}
document.getElementById("b-act").addEventListener("click", () => setStrokeTarget(state.strokeTarget === 0 ? 1 : 0));
caption("closed");

/* 主题色 → 高亮色 */
function readTheme() {
  const c = getComputedStyle(document.documentElement).getPropertyValue("--hl").trim();
  if (c) hlColor.set(c);
  state.shadowA = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--shadow-a")) || 0.22;
  paint();
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", readTheme);
new MutationObserver(readTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

/* ------------------------------------------------------------------ 主循环 */
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;

  if (state.tTarget !== null) {
    const dir = Math.sign(state.tTarget - state.t);
    state.t += dir * dt * 0.55;
    if ((dir > 0 && state.t >= state.tTarget) || (dir < 0 && state.t <= state.tTarget) || dir === 0) {
      state.t = state.tTarget;
      state.tTarget = null;
    }
    syncSlider();
  }
  if (state.stroke !== state.strokeTarget) {
    const dir = Math.sign(state.strokeTarget - state.stroke);
    state.stroke += dir * dt * 1.15;
    if ((dir > 0 && state.stroke >= state.strokeTarget) || (dir < 0 && state.stroke <= state.strokeTarget)) {
      state.stroke = state.strokeTarget;
      caption(state.strokeTarget === 0 ? "closed" : "open");
    }
  }

  applyExplode();
  camPlace(false);
  controls.update();

  /* 包围盒跟随，地面与主光跟着模型走 */
  box.makeEmpty();
  for (const m of MESHES) box.expandByObject(m);
  ground.position.y = box.min.y - 1;
  ground.material.opacity = (state.shadowA || 0.22) * (1 - Math.min(1, state.t * 1.4));
  const c = box.getCenter(new V3());
  key.position.set(c.x + 240, c.y + 520, c.z + 300);
  key.target.position.copy(c);
  key.target.updateMatrixWorld();

  renderer.render(scene, camera);
  updateBalloons();
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------ 尺寸 */
function resize() {
  const w = canvas.clientWidth || 1;
  const h = canvas.clientHeight || 1;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  measureInsets();
  state.moved = false; // 尺寸/版式变化后重新取景，避免旋转过视角就被“锁死”
  refit();
}
new ResizeObserver(() => resize()).observe(canvas);

/* 启动：支持 #t=0.5&stroke=1&sel=3&bom=1&lbl=0 直接进入某个状态（截图/分享用） */
const qs = new URLSearchParams(location.hash.replace(/^#/, ""));
measureInsets();
readTheme();
if (qs.has("lbl")) state.labels = qs.get("lbl") === "1";
document.getElementById("app").classList.toggle("no-lbl", !state.labels);
document.getElementById("b-lbl").setAttribute("aria-pressed", String(state.labels));
refit();
if (qs.has("t")) {
  state.t = Math.min(1, Math.max(0, +qs.get("t")));
  state.tTarget = null;
} else {
  state.t = 0;
  state.tTarget = 1; // 开场：从装配状态推出来
}
if (qs.has("stroke")) {
  state.stroke = state.strokeTarget = Math.min(1, Math.max(0, +qs.get("stroke")));
  caption(state.stroke > 0.5 ? "open" : "closed");
}
if (qs.has("bom")) toggleBom(qs.get("bom") !== "0");
else if (window.innerWidth >= 960) toggleBom(true);
if (qs.has("sel")) {
  const p = PARTS.find((v) => v.no === +qs.get("sel"));
  if (p) select(p);
}
if (qs.has("cam")) {
  const v = qs.get("cam").split(",").map(Number);
  camera.position.set(v[0], v[1], v[2]);
  controls.target.set(v[3] || 0, v[4] || 0, v[5] || 0);
  state.moved = true;
}
if (qs.has("fov")) {
  camera.fov = +qs.get("fov");
  camera.updateProjectionMatrix();
}
if (qs.has("only")) {
  const keep = new Set(qs.get("only").split(",").map(Number));
  for (const p of PARTS) if (!keep.has(p.no)) for (const r of p.insts) r.g.visible = false;
}
syncSlider();
applyExplode();
camPlace(true);
box.makeEmpty();
for (const m of MESHES) box.expandByObject(m);
requestAnimationFrame(frame);

window.addEventListener("error", (e) => (document.documentElement.dataset.err = e.message));
setTimeout(() => {
  if (window.__diag) document.documentElement.dataset.diag = JSON.stringify(window.__diag());
}, 800);

/* 调试/截图用 */
window.__dbv = {
  state, PARTS, MESHES, camera, controls, refit,
  setExplode(v) { state.tTarget = null; state.t = v; syncSlider(); applyExplode(); camPlace(true); },
  setStroke(v) { state.strokeTarget = v; state.stroke = v; caption(v ? "open" : "closed"); applyExplode(); },
  select,
  toggleBom,
};
window.__diag = () => ({
  t: +state.t.toFixed(3), stroke: +state.stroke.toFixed(3),
  parts: PARTS.length, meshes: MESHES.length,
  balloons: document.querySelectorAll(".bln").length,
  cam: camera.position.toArray().map((v) => Math.round(v)),
  dist: Math.round(camera.position.distanceTo(controls.target)),
  fitB: fitB ? { d: Math.round(fitB.dist), min: fitB.box.min.toArray().map(Math.round), max: fitB.box.max.toArray().map(Math.round) } : null,
  inset: { ...inset }, aspect: +camera.aspect.toFixed(2), size: [canvas.clientWidth, canvas.clientHeight],
});
