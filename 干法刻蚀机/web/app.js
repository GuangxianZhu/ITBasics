// ICP 刻蚀机 · 跑一片晶圆
// 机台在这里用代码搭（不读 glb），工艺用一个简化模型：趋势对、数量级对，系数是估计值。
// 坐标：米，+Y 向上；晶圆传送平面 Y = H；工艺腔 PM1 在传输腔后面（-Z）。

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

const $ = s => document.querySelector(s);
const H = 0.95;
const PM_Z = -1.05;
const POS = {
  foup: new THREE.Vector3(-0.55, H, 2.40),
  aligner: new THREE.Vector3(0.70, H, 1.80),
  ll: new THREE.Vector3(-0.32, H, 1.00),
  pm: new THREE.Vector3(0, H, PM_Z),
};
const ease = p => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

// ================= 配方和工艺模型 =================

const PRESETS = [
  { id: 'std', name: '标准（推荐）', r: { P: 10, Ws: 600, Wb: 80, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 30 } },
  { id: 'nobias', name: '不加偏压', r: { P: 10, Ws: 600, Wb: 0, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 30 } },
  { id: 'hibias', name: '偏压太高', r: { P: 10, Ws: 600, Wb: 350, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 60 } },
  { id: 'nopass', name: '只用 Cl₂', r: { P: 30, Ws: 600, Wb: 60, cl2: 180, hbr: 0, o2: 0, T: 60, oe: 30 } },
  { id: 'nooe', name: '不过刻', r: { P: 10, Ws: 600, Wb: 80, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 0 } },
];
const FIELDS = [
  { k: 'P', name: '腔压', unit: 'mTorr', min: 3, max: 80, step: 1, tip: '气压低，离子方向更直；气压高，自由基多，但更容易往侧面刻' },
  { k: 'Ws', name: '源功率（线圈）', unit: 'W', min: 0, max: 1500, step: 50, tip: '决定等离子体有多"浓"' },
  { k: 'Wb', name: '偏压功率（卡盘）', unit: 'W', min: 0, max: 400, step: 10, tip: '决定离子打下来有多猛（能量）' },
  { k: 'cl2', name: 'Cl₂', unit: 'sccm', min: 0, max: 200, step: 5, tip: '主要的刻蚀气体' },
  { k: 'hbr', name: 'HBr', unit: 'sccm', min: 0, max: 200, step: 5, tip: '刻得温和，产物会沉积在侧壁上保护侧壁，对栅氧的选择比高' },
  { k: 'o2', name: 'O₂', unit: 'sccm', min: 0, max: 20, step: 1, tip: '少量就够：加强侧壁保护；多了会把光刻胶吃掉' },
  { k: 'T', name: '卡盘温度', unit: '°C', min: 20, max: 80, step: 5, tip: '温度高，纯化学反应（往侧面刻）更快' },
  { k: 'oe', name: '过刻', unit: '%', min: 0, max: 100, step: 5, tip: '到终点以后再刻多久，按主刻时间的百分比' },
];
let R = { ...PRESETS[0].r };

// 刻蚀速率单位 nm/min。思路：
//   等离子体密度 n ∝ 源功率；离子能量 ≈ 偏压功率 ÷ 离子电流（离子电流 ∝ n）
//   往下刻 = 离子和自由基"串联"：哪个少就被哪个卡住（离子-自由基协同）
//   往侧面刻 = 自由基自己的化学反应，被侧壁钝化层挡掉一部分
function model(r) {
  const n = (r.Ws / 800) / (1 + r.P / 150);
  const Ei = Math.min(800, 15 + 0.9 * r.Wb / Math.max(n, 0.15));
  const Y = Math.max(0, Math.sqrt(Ei) - Math.sqrt(12)) / (Math.sqrt(115) - Math.sqrt(12));
  const Gn = (r.cl2 + 0.6 * r.hbr) / 100 * Math.sqrt(n) * Math.sqrt(r.P / 20);
  const ion = 1 / (1 / (Gn + 1e-6) + 1 / (1.2 * Y * n + 1e-6));
  const chem = 0.03 * Gn * Math.exp((r.T - 40) / 40);
  const hbrFrac = r.hbr / (r.cl2 + r.hbr + 1);
  const pass = Math.min(0.95, 0.7 * hbrFrac + 0.8 * r.o2 / 20);
  const ERv = 300 * (ion + chem);
  const ERl = 300 * chem * (1 - pass) + 300 * ion * 0.02 * (r.P / 20);
  const Yox = Math.max(0, Math.sqrt(Ei) - Math.sqrt(40)) / (Math.sqrt(115) - Math.sqrt(40));
  const ERox = 300 * 0.03 * Yox * n * (1 - 0.6 * hbrFrac) * (1 - 0.3 * r.o2 / 20) + 0.2;
  const ERmask = 300 * 0.12 * Y * n + 300 * 0.25 * (r.o2 / 20) * Math.sqrt(n) + 1;
  const u = 0.025 + 0.05 * Math.abs(r.P - 12) / 70 + (r.Ws > 1100 ? 0.02 : 0);
  const total = r.cl2 + r.hbr + r.o2;
  let problem = '';
  if (r.Ws < 150) problem = '源功率太低（< 150 W），点不着等离子体。';
  else if (total < 10) problem = '气体总流量太少（< 10 sccm），点不着等离子体。';
  else if (r.cl2 + r.hbr < 5) problem = '没有 Cl₂ 或 HBr，没有能刻多晶硅的气体。';
  return { n, Ei, Gn, ERv, ERl, ERox, ERmask, u, pass, sel: ERv / ERox, total, problem };
}
let MDL = model(R);

// ================= 三维场景 =================

const stage = $('#stage');
const canvas = $('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.localClippingEnabled = true;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.add(new THREE.HemisphereLight(0xffffff, 0x556070, 0.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.3);
sun.position.set(3, 6, 4);
scene.add(sun);

const camera = new THREE.PerspectiveCamera(40, 1, 0.02, 60);
camera.position.set(3.2, 4.3, 3.3);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.6, 0.3);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.49;
controls.minDistance = 0.3;
controls.maxDistance = 12;

const labelRenderer = new CSS2DRenderer();
labelRenderer.domElement.className = 'labels';
stage.insertBefore(labelRenderer.domElement, $('#caption'));

// ---------- 材质 ----------
const CUT = new THREE.Plane(new THREE.Vector3(0, 0, -1), PM_Z); // 剖开时只留 z ≤ PM_Z 的后半个腔
function std(color, metalness = 0.15, roughness = 0.55, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, metalness, roughness, ...extra });
}
function clipped(m) {
  const c = m.clone();
  c.side = THREE.DoubleSide;
  c.clippingPlanes = [CUT];
  c.userData.clip = true;
  return c;
}
const MAT = {
  floor: std(0xcfd5db, 0, 0.95),
  panel: std(0xe3e6e9, 0.1, 0.6),
  dark: std(0x555d67, 0.2, 0.6),
  alu: std(0xbcc3cb, 0.45, 0.35),
  anod: std(0x8e97a1, 0.3, 0.45),
  ceramic: std(0xefe9dc, 0, 0.45),
  quartz: std(0xf2f5f7, 0, 0.2, { transparent: true, opacity: 0.85 }),
  copper: std(0xcf8448, 0.55, 0.3),
  si: std(0x4b5261, 0.4, 0.3),
  white: std(0xf4f5f6, 0, 0.5),
  orange: std(0xe07a2e, 0.1, 0.5),
  green: std(0x3e9b62, 0.1, 0.5),
  liner: std(0x9fa8b2, 0.3, 0.5),
  blue: std(0x2f6fb3, 0.2, 0.5),
  glass: new THREE.MeshPhysicalMaterial({ color: 0xd8ecf5, roughness: 0.05, transparent: true, opacity: 0.13, depthWrite: false, side: THREE.DoubleSide }),
  foup: new THREE.MeshPhysicalMaterial({ color: 0x8fa4b8, roughness: 0.3, transparent: true, opacity: 0.38, depthWrite: false, side: THREE.DoubleSide }),
};
MAT.glass.userData.noPick = true;

// ---------- 几何体小工具 ----------
function mesh(geo, mat, x = 0, y = 0, z = 0) { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); return m; }
const box = (w, h, d, mat, x, y, z) => mesh(new THREE.BoxGeometry(w, h, d), mat, x, y, z);
const cyl = (r, h, mat, x, y, z, seg = 48) => mesh(new THREE.CylinderGeometry(r, r, h, seg), mat, x, y, z);
const cylY = (r, y0, y1, mat, x = 0, z = 0) => cyl(r, y1 - y0, mat, x, (y0 + y1) / 2, z);
function ring(rIn, rOut, y0, y1, mat, x = 0, z = 0) {
  const h = y1 - y0;
  const pts = [[rIn, 0], [rOut, 0], [rOut, h], [rIn, h], [rIn, 0]].map(p => new THREE.Vector2(p[0], p[1]));
  return mesh(new THREE.LatheGeometry(pts, 72), mat, x, y0, z);
}
function group(...objs) { const g = new THREE.Group(); objs.forEach(o => g.add(o)); return g; }
function spiral(r0, r1, turns, y, mat) {
  const pts = [];
  for (let i = 0; i <= 160; i++) {
    const t = i / 160, a = t * turns * Math.PI * 2, r = r0 + (r1 - r0) * t;
    pts.push(new THREE.Vector3(r * Math.cos(a), y, r * Math.sin(a)));
  }
  return new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 160, 0.008, 8, false), mat);
}
function pipe(points, r, mat) {
  const curve = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)), false, 'catmullrom', 0.05);
  return new THREE.Mesh(new THREE.TubeGeometry(curve, 64, r, 8, false), mat);
}

// ---------- 零件表 ----------
const PART_INFO = [
  ['foup', '整机', '晶圆盒（FOUP）', '一盒最多 25 片晶圆，前门密封。晶圆在厂里搬来搬去时一直关在盒子里，不接触车间空气。'],
  ['loadport', '整机', '装载口', '放晶圆盒的台子。自动对位，把盒门和设备的门对接后一起打开。'],
  ['efem', '整机', 'EFEM 前端模块', '大气压下的洁净小房间。顶上的风机过滤单元（FFU）一直往下吹洁净空气，颗粒落不到晶圆上。'],
  ['atmrobot', '整机', '大气机械手', '在晶圆盒、对准器、负载锁之间搬晶圆。'],
  ['aligner', '整机', '对准器', '转动晶圆，找到边上的缺口（notch），让每片晶圆以同样的方向、居中地进腔。'],
  ['loadlock', '整机', '负载锁 ×2', '大气和真空之间的"过渡间"。两扇门永远不会同时打开；每次只抽这个小腔，几十秒就好，也不会把空气带进真空。'],
  ['vtm', '整机', '真空传输腔', '一直保持真空。中间的真空机械手把晶圆送到各个工艺腔。'],
  ['vtmrobot', '整机', '真空机械手', '在真空里工作的双连杆机械手，通过闸阀进出工艺腔和负载锁。'],
  ['pm23', '整机', '工艺腔 PM2 / PM3', '和 PM1 同型号。几个腔可以同时各刻一片晶圆，提高产量。'],
  ['rack', '整机', '射频电源和控制柜', '13.56 MHz 射频电源、腔体控制器都装在这里。'],
  ['coil', '工艺腔 · 源', '平面线圈', '通 13.56 MHz 射频电流，交变磁场在腔里感应出电场，把电子加速、撞电离气体分子（电感耦合，ICP）。功率越大，等离子体越浓。分内外两组，调两组的功率比可以调中心和边缘的均匀性。'],
  ['window', '工艺腔 · 源', '陶瓷介质窗', '让线圈的电磁场透进腔里，同时把气体和等离子体挡在里面。用氧化铝陶瓷：不导电、耐腐蚀。'],
  ['rfcover', '工艺腔 · 源', '射频屏蔽罩', '罩住线圈，不让射频辐射到外面。'],
  ['srcmatch', '工艺腔 · 源', '源匹配器', '里面有两个可变电容，自动调到"阻抗匹配"，让电源的功率都送进等离子体，反射回来的接近 0。'],
  ['nozzle', '工艺腔 · 源', '中心进气喷嘴', '工艺气体从陶瓷窗中心喷进腔里。'],
  ['chamber', '工艺腔 · 腔体', '腔体', '铝做的真空容器，内壁有耐等离子体涂层（如氧化钇），减少腐蚀和掉颗粒。'],
  ['liner', '工艺腔 · 腔体', '内衬', '可以拆下来的保护套。脏了整个换下来清洗，不用清洗腔体本身。消耗件。'],
  ['baffle', '工艺腔 · 腔体', '约束环（挡板）', '把等离子体限制在晶圆上方，气体从缝隙流向下面的排气口。'],
  ['slit', '工艺腔 · 腔体', '闸阀', '工艺腔和传输腔之间的门。刻蚀时关着，腐蚀性气体跑不到传输腔里。'],
  ['oes', '工艺腔 · 腔体', '观察窗 + 光谱仪（OES）', '一直看着等离子体发的光。多晶硅刻穿时，含硅产物的谱线会突然变暗，用它判断"终点"。'],
  ['cmg', '工艺腔 · 腔体', '真空计（电容薄膜规）', '测腔压，读数和气体种类无关。摆阀按它的读数调开度。'],
  ['esc', '工艺腔 · 卡盘', '静电卡盘', '陶瓷里埋着电极，加高压用静电把晶圆吸平；底座通冷却液控温，晶圆背面通氦气导热。它也是下电极，偏压从这里加上去。'],
  ['edgering', '工艺腔 · 卡盘', '边缘环', '套在晶圆外圈，让晶圆边缘上方的电场和中间一样平，边缘也能刻直。会被等离子体慢慢吃掉，是消耗件。'],
  ['insring', '工艺腔 · 卡盘', '绝缘环', '石英做的，把带射频的卡盘和接地的腔体隔开。'],
  ['pins', '工艺腔 · 卡盘', '升降针 ×3', '把晶圆顶起来，机械手的叉子才能伸到晶圆下面接送。'],
  ['biasmatch', '工艺腔 · 卡盘', '偏压匹配器', '把偏压射频送到卡盘上。偏压决定离子打到晶圆上的能量。'],
  ['pendulum', '工艺腔 · 排气', '摆阀', '一块会摆动的阀板，调节抽气口开多大，把腔压稳在设定值。'],
  ['turbo', '工艺腔 · 排气', '分子泵', '转子每分钟几万转，把气体分子"打"向出口，把腔抽到高真空。后面还接着干泵和尾气处理（在楼下）。'],
  ['gasbox', '工艺腔 · 气路', '气体盒', '每路气体一个质量流量计（MFC），精确控制流量；还有阀门和过滤器。'],
  ['wafer', '晶圆', '晶圆', '300 mm 硅片，上面是 4 nm 栅氧 + 100 nm 多晶硅，再上面是 60 nm 宽的光刻胶线条。刻完剩下的多晶硅就是晶体管的栅极。'],
];
const PARTS = {};
for (const [id, grp, name, desc] of PART_INFO) PARTS[id] = { id, grp, name, desc, objs: [] };
function addPart(id, obj) {
  PARTS[id].objs.push(obj);
  obj.userData.baseY = obj.position.y;
  obj.traverse(o => {
    if (!o.isMesh) return;
    o.userData.part = id;
    o.material = o.material.clone();
    if (o.material.userData.clip) o.material.clippingPlanes = [CUT];
  });
  return obj;
}
const labels = [];
function label(text, x, y, z, main = false) {
  const d = document.createElement('div');
  d.className = 'lab' + (main ? ' main' : '');
  d.textContent = text;
  const o = new CSS2DObject(d);
  o.position.set(x, y, z);
  scene.add(o);
  labels.push(o);
}

// ---------- 地面 ----------
const floor = mesh(new THREE.PlaneGeometry(10, 10), MAT.floor);
floor.rotation.x = -Math.PI / 2;
scene.add(floor);
const grid = new THREE.GridHelper(10, 17, 0xa7b0b9, 0xbfc7ce);
grid.position.y = 0.002;
scene.add(grid);

// ---------- EFEM、晶圆盒、对准器 ----------
{
  const z0 = 1.4, z1 = 2.2, h = 2.0, cz = 1.8;
  const g = group(box(2.2, 0.04, 0.8, MAT.dark, 0, 0.02, cz), box(2.2, 0.2, 0.8, MAT.white, 0, h - 0.1, cz));
  for (const [x, z] of [[-1.1, z0], [1.1, z0], [-1.1, z1], [1.1, z1]]) g.add(box(0.05, h, 0.05, MAT.panel, x, h / 2, z));
  g.add(box(2.2, 0.55, 0.015, MAT.panel, 0, 0.275, z1), box(2.2, 0.55, 0.015, MAT.panel, 0, 0.275, z0));
  g.add(box(2.2, h - 0.75, 0.01, MAT.glass, 0, 0.55 + (h - 0.75) / 2, z1), box(2.2, h - 0.75, 0.01, MAT.glass, 0, 0.55 + (h - 0.75) / 2, z0));
  g.add(box(0.01, h - 0.2, 0.8, MAT.glass, -1.1, (h - 0.2) / 2, cz), box(0.01, h - 0.2, 0.8, MAT.glass, 1.1, (h - 0.2) / 2, cz));
  // FFU 格栅
  for (let i = -5; i <= 5; i++) g.add(box(0.01, 0.005, 0.7, MAT.dark, i * 0.18, h - 0.2, cz));
  scene.add(addPart('efem', g));
  label('EFEM 前端模块（大气）', 0, 2.12, cz);

  const al = group(box(0.18, 0.12, 0.18, MAT.panel, 0.7, H - 0.075, 1.8), cylY(0.04, H - 0.015, H - 0.004, MAT.dark, 0.7, 1.8),
    cylY(0.03, 0.02, H - 0.135, MAT.dark, 0.7, 1.8));
  scene.add(addPart('aligner', al));
  label('对准器', 0.7, 1.08, 1.8);
}
const foupDoors = [];
for (const x of [-0.55, 0.55]) {
  const lp = group(box(0.5, H - 0.17, 0.42, MAT.panel, x, (H - 0.17) / 2, 2.40), box(0.48, 0.5, 0.02, MAT.dark, x, 0.5, 2.205));
  scene.add(addPart('loadport', lp));
  const f = group(box(0.40, 0.34, 0.38, MAT.foup, x, H + 0.0, 2.40), box(0.22, 0.03, 0.10, MAT.dark, x, H + 0.185, 2.40));
  for (let i = 0; i < 7; i++) if (!(x < 0 && i === 3)) f.add(cyl(0.15, 0.003, std(0xa08a5c, 0.5, 0.2), x, H + (i - 3) * 0.01, 2.40, 48));
  const door = box(0.40, 0.33, 0.02, MAT.dark, x, H, 2.205);
  f.add(door);
  scene.add(addPart('foup', f));
  if (x < 0) foupDoors.push(door);
}
label('晶圆盒', -0.55, 1.25, 2.4, true);

// ---------- 负载锁 ----------
const doorObjs = {};
for (const x of [-0.32, 0.32]) {
  const g = group(box(0.5, 0.78, 0.8, MAT.dark, x, 0.39, 1.0), box(0.5, 0.03, 0.8, MAT.alu, x, 0.795, 1.0),
    box(0.03, 0.32, 0.8, MAT.alu, x - 0.235, 0.97, 1.0), box(0.03, 0.32, 0.8, MAT.alu, x + 0.235, 0.97, 1.0),
    box(0.5, 0.02, 0.8, MAT.glass, x, 1.135, 1.0));
  for (let k = 0; k < 3; k++) {
    const a = k * Math.PI * 2 / 3 + Math.PI / 2;
    g.add(cylY(0.006, 0.81, H - 0.0015, MAT.ceramic, x + 0.09 * Math.cos(a), 1.0 + 0.09 * Math.sin(a)));
  }
  const outer = box(0.42, 0.16, 0.02, MAT.alu, x, H, 1.39), inner = box(0.42, 0.16, 0.02, MAT.alu, x, H, 0.61);
  g.add(outer, inner);
  scene.add(addPart('loadlock', g));
  if (x < 0) { doorObjs.llOuter = outer; doorObjs.llInner = inner; }
}
label('负载锁 ×2', 0, 1.3, 1.0);

// ---------- 真空传输腔 ----------
{
  const g = group(box(1.2, 0.75, 1.2, MAT.dark, 0, 0.375, 0), box(1.2, 0.03, 1.2, MAT.alu, 0, 0.765, 0),
    box(1.2, 0.02, 1.2, MAT.glass, 0, 1.15, 0));
  for (const s of [-1, 1]) {
    g.add(box(1.2, 0.36, 0.04, MAT.glass, 0, 0.96, s * 0.58), box(0.04, 0.36, 1.2, MAT.glass, s * 0.58, 0.96, 0));
    g.add(box(1.2, 0.04, 0.04, MAT.alu, 0, 1.14, s * 0.58), box(0.04, 0.04, 1.2, MAT.alu, s * 0.58, 1.14, 0));
  }
  for (const [x, z] of [[-0.58, -0.58], [0.58, -0.58], [-0.58, 0.58], [0.58, 0.58]]) g.add(box(0.05, 0.38, 0.05, MAT.alu, x, 0.96, z));
  scene.add(addPart('vtm', g));
  label('真空传输腔', 0.35, 1.28, 0.3);
}

// ---------- 机械手（双连杆，末端就是晶圆中心） ----------
function makeRobot(name, bx, bz, L, partId) {
  const g = new THREE.Group();
  g.add(cylY(0.09, name === 'atm' ? 0.04 : 0.78, 0.88, MAT.alu, bx, bz));
  const l1 = new THREE.Mesh(new THREE.BoxGeometry(L, 0.016, 0.07).translate(L / 2, 0, 0), std(0xd8dde2, 0.3, 0.4));
  const l2 = new THREE.Mesh(new THREE.BoxGeometry(L, 0.012, 0.055).translate(L / 2, 0, 0), std(0xc9cfd5, 0.3, 0.4));
  const blade = new THREE.Mesh(new THREE.BoxGeometry(0.27, 0.004, 0.09), MAT.ceramic);
  g.add(l1, l2, blade);
  scene.add(addPart(partId, g));
  const rb = { name, bx, bz, L, theta: Math.PI / 2, r: 0.18, y: H - 0.012, home: 0.18, end: new THREE.Vector3() };
  rb.update = () => {
    const d = clamp(rb.r, 0.06, 2 * L * 0.999);
    const a = Math.acos(d / (2 * L));
    const a1 = rb.theta + a, a2 = rb.theta - a;
    l1.position.set(bx, rb.y - 0.03, bz); l1.rotation.y = -a1;
    const ex = bx + L * Math.cos(a1), ez = bz + L * Math.sin(a1);
    l2.position.set(ex, rb.y - 0.015, ez); l2.rotation.y = -a2;
    rb.end.set(bx + d * Math.cos(rb.theta), rb.y, bz + d * Math.sin(rb.theta));
    blade.position.copy(rb.end); blade.rotation.y = -rb.theta;
  };
  rb.update();
  return rb;
}
const ATM = makeRobot('atm', 0, 1.8, 0.46, 'atmrobot');
const VTM = makeRobot('vtm', 0, 0, 0.55, 'vtmrobot');
ATM.theta = Math.PI / 2; ATM.update();
VTM.theta = -Math.PI / 2; VTM.update();
const ROB = { atm: ATM, vtm: VTM };
// 大气机械手的立柱
scene.add(cylY(0.12, 0.04, 0.84, MAT.dark, 0, 1.8));

// ---------- 工艺腔 ----------
// 局部坐标：腔中心在原点，闸阀朝 +Z。detailed 的那个（PM1）有全部内部零件，可以剖开。
let PM1 = null;
function buildPM(detailed) {
  const g = new THREE.Group();
  const P = (id, obj) => { g.add(obj); if (detailed) addPart(id, obj); return obj; };
  const sh = m => (detailed ? clipped(m) : m);
  const legs = new THREE.Group();
  for (const [x, z] of [[-0.3, -0.3], [0.3, -0.3], [-0.3, 0.3], [0.3, 0.3]]) legs.add(box(0.04, 0.77, 0.04, MAT.panel, x, 0.385, z));
  legs.add(box(0.66, 0.03, 0.04, MAT.panel, 0, 0.3, -0.3), box(0.66, 0.03, 0.04, MAT.panel, 0, 0.3, 0.3));
  g.add(legs);

  P('chamber', group(ring(0.32, 0.345, 0.78, 1.2, sh(MAT.anod)), cylY(0.345, 0.76, 0.78, sh(MAT.anod))));
  P('window', cylY(0.345, 1.2, 1.235, sh(MAT.ceramic)));
  P('coil', group(spiral(0.06, 0.12, 2, 1.255, MAT.copper), spiral(0.19, 0.27, 2, 1.255, MAT.copper),
    cylY(0.012, 1.255, 1.47, MAT.copper, 0.12, 0), cylY(0.012, 1.255, 1.47, MAT.copper, 0.27, 0)));
  P('rfcover', group(ring(0.333, 0.345, 1.235, 1.455, sh(MAT.panel)), cylY(0.345, 1.455, 1.467, sh(MAT.panel))));
  P('srcmatch', group(box(0.34, 0.16, 0.26, MAT.dark, 0, 1.55, 0), box(0.12, 0.02, 0.02, MAT.orange, -0.08, 1.55, 0.131)));
  P('nozzle', group(cylY(0.022, 1.2, 1.29, MAT.ceramic)));
  // 闸阀口（剖开时一起剖）和门
  P('slit', group(box(0.44, 0.17, 0.12, sh(MAT.anod), 0, H + 0.01, 0.39)));
  const door = box(0.40, 0.11, 0.02, MAT.dark, 0, H + 0.01, 0.457);
  g.add(door);
  if (detailed) { addPart('slit', door); doorObjs.slit = door; }
  // 排气
  P('pendulum', group(cylY(0.16, 0.70, 0.755, MAT.alu, 0.1, 0), box(0.08, 0.05, 0.12, MAT.dark, 0.28, 0.727, 0)));
  P('turbo', group(cylY(0.13, 0.44, 0.70, MAT.alu, 0.1, 0), cylY(0.15, 0.68, 0.70, MAT.alu, 0.1, 0), cylY(0.05, 0.36, 0.44, MAT.dark, 0.1, 0)));

  if (detailed) {
    P('liner', group(ring(0.30, 0.315, 0.87, 1.16, clipped(MAT.liner))));
    P('baffle', group(ring(0.19, 0.30, 0.86, 0.872, clipped(std(0x5b646e, 0.3, 0.5)))));
    P('esc', group(cylY(0.15, H - 0.013, H - 0.001, MAT.ceramic), cylY(0.165, H - 0.12, H - 0.013, MAT.alu), cylY(0.07, 0.78, H - 0.12, MAT.alu)));
    P('insring', group(ring(0.166, 0.19, H - 0.12, H - 0.014, MAT.quartz)));
    P('edgering', group(ring(0.151, 0.185, H - 0.014, H + 0.002, MAT.si)));
    const pins = new THREE.Group();
    for (let k = 0; k < 3; k++) {
      const a = k * Math.PI * 2 / 3 + Math.PI / 2;
      pins.add(cylY(0.004, H - 0.06, H - 0.004, MAT.ceramic, 0.1 * Math.cos(a), 0.1 * Math.sin(a), 12));
    }
    P('pins', pins);
    P('oes', group(mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.06, 24).rotateZ(Math.PI / 2), MAT.dark, -0.37, H + 0.08, 0.0),
      box(0.12, 0.08, 0.16, MAT.green, -0.52, H + 0.08, 0.06),
      pipe([[-0.40, H + 0.08, 0], [-0.44, H + 0.08, 0.02], [-0.46, H + 0.08, 0.06]], 0.006, MAT.orange)));
    P('cmg', group(mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.08, 16).rotateZ(Math.PI / 2), MAT.alu, 0.38, 1.12, -0.15),
      cylY(0.032, 1.08, 1.2, MAT.white, 0.44, -0.15), cylY(0.032, 1.08, 1.2, MAT.white, 0.44, -0.24),
      mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.1, 16).rotateZ(Math.PI / 2), MAT.alu, 0.39, 1.12, -0.24)));
    P('biasmatch', group(box(0.22, 0.18, 0.22, MAT.dark, -0.16, 0.6, -0.14), box(0.03, 0.12, 0.03, MAT.copper, -0.07, 0.72, -0.07)));
    P('gasbox', group(box(0.34, 0.5, 0.28, MAT.white, 0.66, 1.25, -0.15),
      ...[0, 1, 2].map(i => box(0.06, 0.12, 0.02, MAT.blue, 0.56 + i * 0.1, 1.3, -0.005)),
      pipe([[0.55, 1.45, -0.15], [0.45, 1.62, -0.10], [0.15, 1.66, -0.04], [0.02, 1.62, 0], [0.0, 1.30, 0]], 0.008, MAT.alu)));
    P('rack', group(box(0.42, 1.6, 0.6, MAT.panel, -0.78, 0.8, -0.12), box(0.36, 0.08, 0.01, MAT.dark, -0.78, 1.45, 0.181),
      box(0.36, 0.08, 0.01, MAT.dark, -0.78, 1.3, 0.181)));
  }
  return { g, door };
}
{
  const pm1 = buildPM(true);
  pm1.g.position.set(0, 0, PM_Z);
  scene.add(pm1.g);
  PM1 = pm1.g;
  label('工艺腔 PM1（这次用）', 0, 1.78, PM_Z, true);
  for (const [x, rot] of [[1.05, -Math.PI / 2], [-1.05, Math.PI / 2]]) {
    const pm = buildPM(false);
    pm.g.position.set(x, 0, 0);
    pm.g.rotation.y = rot;
    scene.add(addPart('pm23', pm.g));
    label(x > 0 ? 'PM2' : 'PM3', x, 1.75, 0);
  }
}

// ---------- 等离子体 ----------
const plasmaMat = new THREE.MeshBasicMaterial({ color: 0x8f6cff, transparent: true, opacity: 0, depthWrite: false });
plasmaMat.userData.noPick = true;
const plasma = cylY(0.29, H + 0.016, 1.198, plasmaMat);
const plasmaCore = mesh(new THREE.TorusGeometry(0.19, 0.045, 16, 64), plasmaMat.clone(), 0, 1.155, 0);
plasmaCore.material.userData.noPick = true;
plasmaCore.rotation.x = Math.PI / 2;
const plasmaLight = new THREE.PointLight(0xa58cff, 0, 1.4, 1.5);
plasmaLight.position.set(0, 1.08, 0);
PM1.add(plasma, plasmaCore, plasmaLight);
plasma.visible = plasmaCore.visible = false;

// ---------- 晶圆 ----------
const waferMat = std(0xa08a5c, 0.5, 0.2);
const wafer = group(cyl(0.15, 0.003, waferMat, 0, 0, 0, 64), box(0.01, 0.004, 0.006, MAT.dark, 0.146, 0, 0));
scene.add(addPart('wafer', wafer));
const waferBody = wafer.children[0];

// ================= 状态和动画 =================

const S = {};
const E = {};
function resetState() {
  Object.assign(S, {
    holder: 'foup', foupOpen: 0, llOuter: 0, llInner: 0, slit: 0, pinH: 0, alignRot: 0,
    llP: 760, chP: 0.02, valve: 100, cl2: 0, hbr: 0, o2: 0, srcF: 0, srcR: 0, biasF: 0, escV: 0, he: 0, wT: 22,
    plasma: 0, oes: 0, etching: false, explode: 0,
  });
  Object.assign(E, { Dc: 0, De: 0, r: new Float32Array(101), maskH: 60, ox: 4, si: 0, gateLoss: 0, t: 0, tEp: null, tMain: 0, timeout: false, uncleared: 1, oesF: 0, pass: 0 });
  ATM.theta = Math.PI / 2; ATM.r = ATM.home; ATM.y = H - 0.012; ATM.update();
  VTM.theta = -Math.PI / 2; VTM.r = VTM.home; VTM.y = H - 0.012; VTM.update();
}
resetState();

let simT = 0, procT0 = null, speed = 2, paused = false;
const timers = [];
function wait(dur, fn) { return new Promise(res => timers.push({ t0: simT, dur: Math.max(dur, 1e-3), fn, res })); }
function until(cond) { return new Promise(res => timers.push({ cond, res })); }
function runTimers() {
  for (const t of timers.slice()) {
    if (t.cond) { if (t.cond()) { timers.splice(timers.indexOf(t), 1); t.res(); } continue; }
    const p = clamp((simT - t.t0) / t.dur, 0, 1);
    if (t.fn) t.fn(p);
    if (p >= 1) { timers.splice(timers.indexOf(t), 1); t.res(); }
  }
}
const angTo = (rb, p) => Math.atan2(p.z - rb.bz, p.x - rb.bx);
const distTo = (rb, p) => Math.hypot(p.x - rb.bx, p.z - rb.bz);
function lerpAngle(a, b, t) { const d = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI; return a + d * t; }
function robotMove(rb, theta, r, y, dur) {
  const t0 = rb.theta, r0 = rb.r, y0 = rb.y;
  return wait(dur, p => { const e = ease(p); rb.theta = lerpAngle(t0, theta, e); rb.r = lerp(r0, r, e); rb.y = lerp(y0, y, e); rb.update(); });
}
async function pick(rb, pos, yLow, yHigh) {
  const th = angTo(rb, pos), d = distTo(rb, pos);
  await robotMove(rb, th, rb.home, yLow, 0.8);
  await robotMove(rb, th, d, yLow, 1.0);
  await robotMove(rb, th, d, yHigh, 0.4);
  S.holder = rb.name;
  await robotMove(rb, th, rb.home, yHigh, 1.0);
}
async function place(rb, pos, yHigh, yLow, holder) {
  const th = angTo(rb, pos), d = distTo(rb, pos);
  await robotMove(rb, th, rb.home, yHigh, 0.8);
  await robotMove(rb, th, d, yHigh, 1.0);
  await robotMove(rb, th, d, yLow, 0.4);
  S.holder = holder;
  await robotMove(rb, th, rb.home, yLow, 1.0);
}
function door(key, target, dur = 0.8) { const v0 = S[key]; return wait(dur, p => { S[key] = lerp(v0, target, ease(p)); }); }
const vtTarget = () => clamp(100 * MDL.total / (MDL.total + 18 * R.P), 5, 95);

// ---------- 工艺步骤 ----------
const STEPS = [
  {
    name: '打开晶圆盒', cam: 'efem',
    now: '晶圆盒放在装载口上，盒门和设备的门对接后一起打开。',
    why: '晶圆一直关在盒子里，开门也是对着设备里的洁净空间开，不接触车间空气里的颗粒。',
    run: () => door('foupOpen', 1, 1.6),
  },
  {
    name: '取片、对准', cam: 'efem',
    now: 'EFEM 里的大气机械手从盒里取出这一片，放到对准器上转一圈，找晶圆边上的缺口（notch）。',
    why: '让每片晶圆都以同样的方向、正好居中地进腔。',
    run: async () => {
      await pick(ATM, POS.foup, H - 0.006, H - 0.003);
      await place(ATM, POS.aligner, H - 0.003, H - 0.012, 'aligner');
      await wait(2, p => { S.alignRot = ease(p) * Math.PI * 2; });
      S.alignRot = 0;
    },
  },
  {
    name: '放进负载锁', cam: 'll',
    now: '负载锁现在是大气压。外门打开，机械手把晶圆放到里面的支撑针上，关门。',
    why: '负载锁是大气和真空之间的"过渡间"，两扇门永远不会同时打开。',
    run: async () => {
      await door('llOuter', 1);
      await pick(ATM, POS.aligner, H - 0.012, H - 0.003);
      await place(ATM, POS.ll, H - 0.003, H - 0.012, 'll');
      await robotMove(ATM, Math.PI / 2, ATM.home, H - 0.012, 0.8);
      await door('llOuter', 0);
    },
  },
  {
    name: '负载锁抽真空', cam: 'll',
    now: '把负载锁从 760 Torr（一个大气压）抽到约 0.1 Torr。',
    why: '传输腔和工艺腔一直是真空。每次只抽这个小腔，几十秒就好，也不会把空气和水汽带进去。',
    run: () => wait(10, p => { S.llP = 760 * Math.exp(-9 * p); }),
  },
  {
    name: '送进工艺腔', cam: 'vtm',
    now: '内门打开，真空机械手取片；工艺腔闸阀打开，机械手伸进去，三根升降针把晶圆接过去；机械手退出，关闸阀，针降下，晶圆落到卡盘上。',
    why: '机械手的叉子托在晶圆下面，所以要靠升降针"接力"，叉子才抽得出来。',
    run: async () => {
      await door('llInner', 1);
      await pick(VTM, POS.ll, H - 0.012, H - 0.003);
      await door('llInner', 0);
      await door('slit', 1);
      if (follow()) camTo('chamber');
      const th = angTo(VTM, POS.pm), d = distTo(VTM, POS.pm);
      await robotMove(VTM, th, VTM.home, H + 0.020, 0.8);
      await robotMove(VTM, th, d, H + 0.020, 1.4);
      await wait(0.8, p => { S.pinH = p; if (p > 0.85 && S.holder === 'vtm') S.holder = 'pm'; });
      await robotMove(VTM, th, VTM.home, H + 0.020, 1.2);
      await door('slit', 0);
      await wait(0.9, p => { S.pinH = 1 - p; });
    },
  },
  {
    name: '吸附晶圆、通背氦', cam: 'chamber',
    now: '卡盘里的电极加上约 1200 V 高压（估计值），静电把晶圆吸平；晶圆背面通氦气，约 10 Torr。',
    why: '真空里没有空气导热。背面的氦气把晶圆的热传给通着冷却液的卡盘，晶圆温度才控得住。',
    run: async () => {
      await wait(1.2, p => { S.escV = 1200 * ease(p); });
      await wait(1.8, p => { S.he = 10 * ease(p); });
    },
  },
  {
    name: '通气、稳压', cam: 'chamber',
    now: () => `质量流量计按配方通入 Cl₂ ${R.cl2} / HBr ${R.hbr} / O₂ ${R.o2} sccm；摆阀关到约 ${Math.round(vtTarget())}%，把腔压稳在 ${R.P} mTorr。`,
    why: '气压低，离子一路上很少撞到别的分子，打下来的方向更直；气压高，自由基多，但方向性变差。',
    run: () => wait(4, p => {
      const e = ease(Math.min(1, p * 2));
      S.cl2 = R.cl2 * e; S.hbr = R.hbr * e; S.o2 = R.o2 * e;
      S.valve = lerp(100, vtTarget(), ease(p));
      S.chP = lerp(0.02, R.P, 1 - Math.exp(-5 * p)) + R.P * 0.08 * Math.sin(p * Math.PI) * (1 - p);
    }),
  },
  {
    name: '起辉', cam: 'chamber',
    now: () => `线圈加 ${R.Ws} W、13.56 MHz 射频，电磁场穿过陶瓷窗把气体电离，腔里亮起来。匹配器自动调谐，反射功率很快降到接近 0。`,
    why: '源功率只决定等离子体有多"浓"（离子和自由基有多少），基本不决定离子打下来有多猛。',
    run: async () => {
      await wait(0.6, p => { S.srcF = R.Ws * p; S.srcR = S.srcF * 0.35; S.plasma = p * 0.7; });
      await wait(2.2, p => { S.srcR = R.Ws * (0.35 * Math.exp(-5 * p) + 0.01); S.plasma = 0.7 + 0.3 * p; });
    },
  },
  {
    name: '主刻蚀（到终点）', cam: 'chamber', chain: true,
    now: () => `卡盘加 ${R.Wb} W 偏压，晶圆上方形成一层"鞘层"，离子被加速到约 ${Math.round(MDL.Ei)} eV，垂直打下来；氯自由基和离子一起，把多晶硅变成 SiCl₄ 气体抽走。光谱仪盯着含硅产物的谱线，刻穿时谱线变暗，就是终点。`,
    why: '离子负责"往下打"，自由基负责"化学反应"，两个一起比各自单干快得多，而且主要往下刻（各向异性）。',
    run: async () => {
      await wait(0.5, p => { S.biasF = R.Wb * p; });
      S.etching = true;
      await until(() => E.tEp !== null || E.t > 180);
      if (E.tEp === null) E.timeout = true;
      E.tMain = E.t;
    },
  },
  {
    name: '过刻蚀', cam: 'chamber', chain: true,
    now: () => E.timeout ? '主刻了 180 秒还没到终点，不再等了。' : `到终点后按配方再刻 ${R.oe}%（约 ${Math.round(E.tMain * R.oe / 100)} 秒），把边缘刻得慢的地方清干净。`,
    why: '晶圆中间和边缘的刻蚀速率差几个百分点。这时下面的栅氧已经露出来，靠 HBr / O₂ 带来的高选择比，栅氧几乎不被刻。',
    run: () => wait(E.timeout ? 0.01 : E.tMain * R.oe / 100),
  },
  {
    name: '关射频、停气', cam: 'chamber',
    now: '关掉偏压和源功率，等离子体熄灭；停气，摆阀全开，把腔抽回本底真空。',
    why: '先把残留的腐蚀性气体抽干净，等会儿开闸阀时才不会跑进传输腔。',
    run: async () => {
      S.etching = false;
      const f = S.srcF, b = S.biasF, rr = S.srcR;
      await wait(0.8, p => { S.biasF = b * (1 - p); S.srcF = f * (1 - p); S.srcR = rr * (1 - p); S.plasma = 1 - p; });
      const c = S.chP, v = S.valve;
      await wait(2.5, p => {
        const e = ease(Math.min(1, p * 2));
        S.cl2 = R.cl2 * (1 - e); S.hbr = R.hbr * (1 - e); S.o2 = R.o2 * (1 - e);
        S.valve = lerp(v, 100, e); S.chP = lerp(c, 0.02, 1 - Math.exp(-6 * p));
      });
    },
  },
  {
    name: '去吸附', cam: 'chamber',
    now: '抽掉背面的氦气，关掉卡盘高压，等残余电荷放掉。',
    why: '电荷没放干净就顶升降针，晶圆可能会跳片甚至碎掉。',
    run: async () => {
      await wait(1, p => { S.he = 10 * (1 - p); });
      await wait(1.4, p => { S.escV = 1200 * (1 - ease(p)); });
    },
  },
  {
    name: '传出到负载锁', cam: 'vtm',
    now: '升降针顶起晶圆，闸阀打开，真空机械手伸到晶圆下面接走，送回负载锁。',
    why: '和送进来是反过来的动作。',
    run: async () => {
      await wait(0.8, p => { S.pinH = p; });
      await door('slit', 1);
      const th = angTo(VTM, POS.pm), d = distTo(VTM, POS.pm);
      await robotMove(VTM, th, VTM.home, H + 0.020, 0.8);
      await robotMove(VTM, th, d, H + 0.020, 1.4);
      await wait(0.8, p => { S.pinH = 1 - p; if (p > 0.15 && S.holder === 'pm') S.holder = 'vtm'; });
      await robotMove(VTM, th, VTM.home, H + 0.020, 1.2);
      await door('slit', 0);
      if (follow()) camTo('ll');
      await door('llInner', 1);
      await place(VTM, POS.ll, H - 0.003, H - 0.012, 'll');
      await door('llInner', 0);
      await robotMove(VTM, -Math.PI / 2, VTM.home, H - 0.012, 0.8);
    },
  },
  {
    name: '负载锁回大气', cam: 'll',
    now: '往负载锁里充氮气，从 0.1 Torr 回到 760 Torr。',
    why: '充的是干燥氮气而不是空气：晶圆表面还带着少量氯，碰到水汽会腐蚀。',
    run: () => wait(6, p => { S.llP = 0.1 * Math.pow(7600, p); }),
  },
  {
    name: '放回晶圆盒', cam: 'efem',
    now: '外门打开，大气机械手把刻好的晶圆放回原来的槽，关上盒门。',
    why: '一盒 25 片就这样一片接一片地跑；几个工艺腔可以同时各刻一片。',
    run: async () => {
      await door('llOuter', 1);
      await pick(ATM, POS.ll, H - 0.012, H - 0.003);
      await door('llOuter', 0, 0.6);
      await place(ATM, POS.foup, H - 0.003, H - 0.006, 'foup');
      await robotMove(ATM, Math.PI / 2, ATM.home, H - 0.012, 0.6);
      await door('foupOpen', 0, 1.4);
    },
  },
];

// ---------- 刻蚀模型的时间推进 ----------
function etchTick(dt) {
  const k = dt / 60;
  E.t += dt;
  const fc = 1 + MDL.u, fe = 1 - MDL.u;
  if (E.Dc < 100) E.Dc = Math.min(100, E.Dc + MDL.ERv * fc * k);
  else if (E.ox > 0) E.ox = Math.max(0, E.ox - MDL.ERox * fc * k);
  else E.si += MDL.ERv * 0.8 * fc * k;
  E.De = Math.min(100, E.De + MDL.ERv * fe * k);
  const reach = Math.min(100, Math.floor(E.Dc));
  for (let i = 0; i <= reach; i++) E.r[i] = Math.min(30, E.r[i] + MDL.ERl * k);
  if (E.maskH > 0) E.maskH = Math.max(0, E.maskH - MDL.ERmask * k);
  else E.gateLoss = Math.min(100, E.gateLoss + MDL.ERv * 0.9 * k);
  // 晶圆上已经刻穿的面积：刻蚀速率从中心 (1+u) 到边缘 (1-u)，按面积均匀分布
  const s = (1 + MDL.u - 100 / Math.max(1e-6, MDL.ERv / 60 * E.t)) / (2 * MDL.u);
  E.uncleared = 1 - clamp(s, 0, 1);
}

function physicsTick(dt) {
  if (S.etching) etchTick(dt);
  // 光谱：等离子体本身有一点底光；刻多晶硅时含硅产物的谱线和刻蚀速率成正比
  const amp = 0.86 * clamp(MDL.ERv / 150, 0.15, 1);
  const target = S.plasma > 0 ? S.plasma * 0.12 + (S.etching ? amp * E.uncleared : 0) : 0;
  S.oes = target + (S.plasma > 0 ? (Math.random() - 0.5) * 0.02 : 0);
  E.oesF = lerp(E.oesF, S.oes, Math.min(1, dt * 3));
  if (S.etching && E.tEp === null && E.t > 3 && E.oesF < 0.12 + amp * 0.5) { E.tEp = E.t; E.epT = simT - procT0; }
  // 晶圆温度：有背氦时贴着卡盘温度，等离子体会再加热一点
  if (S.holder === 'pm' && S.he > 5) S.wT += (R.T + S.plasma * R.Ws / 300 - S.wT) * Math.min(1, dt / 1.5);
  else if (S.holder === 'pm' && S.plasma > 0) S.wT += dt * 2;
  else S.wT += (22 - S.wT) * Math.min(1, dt / 20);
  E.pass = MDL.pass;
}

// ---------- 每帧更新三维 ----------
const tmpColor = new THREE.Color();
const C_POLY = new THREE.Color(0xa08a5c), C_OX = new THREE.Color(0x4f6fb0);
function visualsTick(dtR) {
  foupDoors[0].position.set(-0.55, H - 0.4 * S.foupOpen, 2.205 + 0.04 * S.foupOpen);
  doorObjs.llOuter.position.y = H - 0.17 * S.llOuter;
  doorObjs.llInner.position.y = H - 0.17 * S.llInner;
  doorObjs.slit.position.y = (H + 0.01) - 0.12 * S.slit;
  // 拆开（只有不在运行时可以）
  const OFF = { srcmatch: 0.80, rfcover: 0.66, coil: 0.55, nozzle: 0.47, window: 0.40, liner: 0.25, baffle: 0.12, edgering: 0.10, pendulum: -0.10, turbo: -0.26 };
  for (const [id, off] of Object.entries(OFF)) for (const o of PARTS[id].objs) o.position.y = o.userData.baseY + off * S.explode;
  const pins = PARTS.pins.objs[0];
  pins.position.y = pins.userData.baseY + 0.031 * S.pinH;
  // 晶圆
  switch (S.holder) {
    case 'foup': wafer.position.copy(POS.foup); break;
    case 'aligner': wafer.position.copy(POS.aligner); break;
    case 'll': wafer.position.copy(POS.ll); break;
    case 'pm': wafer.position.set(0, H + 0.001 + 0.027 * S.pinH, PM_Z); break;
    default: { const rb = ROB[S.holder]; wafer.position.set(rb.end.x, rb.y + 0.004, rb.end.z); }
  }
  wafer.rotation.y = S.alignRot;
  tmpColor.copy(C_POLY).lerp(C_OX, clamp(E.Dc / 100, 0, 1) * (1 - E.uncleared));
  waferBody.material.color.copy(tmpColor);
  // 等离子体
  const on = S.plasma > 0.01;
  plasma.visible = plasmaCore.visible = on;
  if (on) {
    const f = S.plasma * clamp(0.35 + MDL.n * 0.6, 0.3, 1.3) * (0.93 + 0.07 * Math.random());
    plasma.material.opacity = 0.22 * f;
    plasmaCore.material.opacity = 0.4 * f;
    plasmaLight.intensity = 2.2 * f;
  } else plasmaLight.intensity = 0;
}

// ================= 镜头 =================
const VIEWS = {
  overview: { p: [3.2, 4.3, 3.3], t: [0, 0.6, 0.3] },
  efem: { p: [1.4, 2.0, 4.0], t: [0, 0.9, 1.9] },
  ll: { p: [2.3, 1.9, 1.15], t: [-0.15, 0.9, 0.9] },
  vtm: { p: [1.5, 2.6, 1.0], t: [0, 0.9, -0.4] },
  chamber: { p: [0.35, 1.62, 0.5], t: [0, 0.98, PM_Z] },
  explode: { p: [1.5, 2.1, 1.0], t: [0, 1.35, PM_Z] },
};
let camAnim = null;
function camTo(name) {
  const v = VIEWS[name];
  camAnim = { p0: camera.position.clone(), t0: controls.target.clone(), p1: new THREE.Vector3(...v.p), t1: new THREE.Vector3(...v.t), k: 0 };
  document.querySelectorAll('#views button').forEach(b => b.classList.toggle('on', b.dataset.v === name || (name === 'explode' && b.dataset.v === 'chamber')));
}
const follow = () => $('#follow').checked;

// ================= 剖面图 =================
const prof = $('#prof'), pctx = prof.getContext('2d');
const chart = $('#chart'), cctx = chart.getContext('2d');
function fitCanvas(c) {
  const dpr = Math.min(devicePixelRatio, 2), w = c.clientWidth, h = c.clientHeight;
  if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
  c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  return [w, h];
}
const parts2d = [];
function drawProfile(dtR) {
  const [w, h] = fitCanvas(prof);
  const g = pctx;
  const X = x => w / 2 + x;           // 1 px = 1 nm
  const Y0 = 78, Yp = y => Y0 + y;    // y：多晶硅顶面往下的深度（nm）
  const oxTop = Yp(100), oxPx = 2;    // 栅氧放大画：1 nm = 2 px
  const siTop = oxTop + 4 * oxPx;
  g.fillStyle = '#1a2030'; g.fillRect(0, 0, w, h);
  // 硅
  g.fillStyle = '#6b7487'; g.fillRect(0, siTop, w, h - siTop);
  if (E.si > 0) { g.fillStyle = '#1a2030'; g.fillRect(0, siTop, X(-30), E.si); g.fillRect(X(30), siTop, w - X(30), E.si);
    g.strokeStyle = '#ff6b6b'; g.lineWidth = 1.5; g.strokeRect(1, siTop, X(-30) - 1, E.si); g.strokeRect(X(30), siTop, w - X(30) - 1, E.si); }
  // 栅氧
  g.fillStyle = '#c9d6f0';
  g.fillRect(X(-30), oxTop, 60, 4 * oxPx);
  const oxPxNow = E.ox * oxPx;
  g.fillRect(0, siTop - oxPxNow, X(-30), oxPxNow); g.fillRect(X(30), siTop - oxPxNow, w - X(30), oxPxNow);
  // 两边没刻完的多晶硅
  const POLY = '#c6a86c';
  g.fillStyle = POLY;
  if (E.Dc < 100) { g.fillRect(0, Yp(E.Dc), X(-30) + 0.5, 100 - E.Dc); g.fillRect(X(30) - 0.5, Yp(E.Dc), w - X(30), 100 - E.Dc); }
  // 栅极（侧壁按每个深度的侧向刻蚀量往里缩）
  const i0 = Math.floor(E.gateLoss);
  if (i0 < 100) {
    g.beginPath();
    g.moveTo(X(-30 + E.r[i0]), Yp(i0));
    for (let i = i0; i <= 100; i++) g.lineTo(X(-30 + E.r[i]), Yp(i));
    for (let i = 100; i >= i0; i--) g.lineTo(X(30 - E.r[i]), Yp(i));
    g.closePath(); g.fill();
    if (S.etching && E.pass > 0.2) {
      g.strokeStyle = 'rgba(255,170,90,' + (0.4 + E.pass * 0.6) + ')'; g.lineWidth = 1 + E.pass * 1.5;
      const reach = Math.min(100, Math.floor(E.Dc));
      g.beginPath(); for (let i = i0; i <= reach; i++) g.lineTo(X(-30 + E.r[i]) - 0.8, Yp(i)); g.stroke();
      g.beginPath(); for (let i = i0; i <= reach; i++) g.lineTo(X(30 - E.r[i]) + 0.8, Yp(i)); g.stroke();
    }
  }
  // 光刻胶
  if (E.maskH > 0) { g.fillStyle = '#c4455a'; g.fillRect(X(-30), Yp(-E.maskH), 60, E.maskH); }
  // 离子（往下的短线）和自由基（点）
  const dtv = dtR * Math.min(speed, 3) * (paused ? 0 : 1);
  if (S.plasma > 0.05 && !paused) {
    const ionRate = S.plasma * clamp(MDL.n, 0.2, 1.4) * 60, radRate = S.plasma * clamp(MDL.Gn, 0.1, 2) * 25;
    for (let n = 0; n < ionRate * dtv; n++) {
      const sigma = (2 + R.P * 0.35) * Math.PI / 180 * (S.biasF > 1 ? 1 : 4);
      const a = (Math.random() + Math.random() + Math.random() - 1.5) * sigma * 1.4;
      const v = S.biasF > 1 ? 260 + Math.sqrt(MDL.Ei) * 25 : 120;
      parts2d.push({ ion: true, x: (Math.random() - 0.5) * w, y: -5, vx: Math.sin(a) * v, vy: Math.cos(a) * v, life: 3 });
    }
    for (let n = 0; n < radRate * dtv; n++) parts2d.push({ ion: false, x: (Math.random() - 0.5) * w, y: Math.random() * 60, vx: 0, vy: 0, life: 1.5 + Math.random() });
  }
  const surf = x => {
    const ax = Math.abs(x);
    if (ax < 30 - E.r[0]) return E.maskH > 0 ? Yp(-E.maskH) : Yp(E.gateLoss);
    if (E.Dc < 100) return Yp(E.Dc);
    return siTop - E.ox * oxPx + E.si;
  };
  for (let i = parts2d.length - 1; i >= 0; i--) {
    const p = parts2d[i];
    p.life -= dtv;
    if (p.ion) { p.x += p.vx * dtv; p.y += p.vy * dtv; }
    else { p.x += (Math.random() - 0.5) * 140 * dtv; p.y += (Math.random() - 0.45) * 140 * dtv; }
    if (p.life <= 0 || p.y > surf(p.x) || p.y > h || Math.abs(p.x) > w / 2) { parts2d.splice(i, 1); continue; }
    if (p.ion) { g.strokeStyle = '#7fd8ff'; g.lineWidth = 1.2; g.beginPath(); g.moveTo(X(p.x), p.y); g.lineTo(X(p.x - p.vx * 0.02), p.y - p.vy * 0.02); g.stroke(); }
    else { g.fillStyle = '#ffb347'; g.fillRect(X(p.x) - 1, p.y - 1, 2.2, 2.2); }
  }
  if (parts2d.length > 1500) parts2d.splice(0, parts2d.length - 1500);
  // 图例
  g.font = '11px ' + getComputedStyle(document.body).fontFamily;
  const leg = [['#c4455a', '光刻胶'], [POLY, '多晶硅'], ['#c9d6f0', '栅氧（放大）'], ['#6b7487', '硅'], ['#7fd8ff', '离子'], ['#ffb347', '自由基']];
  let lx = 6;
  for (const [c, t] of leg) { g.fillStyle = c; g.fillRect(lx, h - 12, 8, 8); g.fillStyle = '#d6dde8'; g.fillText(t, lx + 11, h - 4.5); lx += g.measureText(t).width + 20; }
  const rmax = Math.max(...E.r);
  $('#depth').textContent = `刻深 ${E.Dc.toFixed(0)}/100 nm · 钻蚀 ${rmax.toFixed(1)} nm`;
}

// ================= 趋势图 =================
const samples = [];
const SERIES = [
  { k: 'llP', name: '负载锁', unit: 'Torr', log: true, min: 0.05, max: 1000, color: '#8a7dd8' },
  { k: 'chP', name: '腔压', unit: 'mTorr', max: 90, color: '#3a8fd6' },
  { k: 'srcF', name: '源功率', unit: 'W', max: 1600, color: '#e0761c' },
  { k: 'srcR', name: '反射功率', unit: 'W', max: 400, color: '#d64545' },
  { k: 'biasF', name: '偏压', unit: 'W', max: 420, color: '#14968f' },
  { k: 'oes', name: '光谱（含硅产物）', unit: '', max: 1.05, color: '#b8a400' },
];
function fmt(v, k) {
  if (k === 'llP') return v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2);
  if (k === 'chP') return v < 1 ? v.toFixed(2) : v.toFixed(1);
  if (k === 'oes') return v.toFixed(2);
  return v.toFixed(0);
}
let lastSample = -1;
function recordSample() {
  if (procT0 === null || simT - lastSample < 0.2) return;
  lastSample = simT;
  samples.push({ t: simT - procT0, llP: S.llP, chP: S.chP, srcF: S.srcF, srcR: S.srcR, biasF: S.biasF, oes: E.oesF });
  if (samples.length > 3000) samples.shift();
}
function drawChart() {
  const [w, h] = fitCanvas(chart);
  const g = cctx, cs = getComputedStyle(document.documentElement);
  const bg = cs.getPropertyValue('--chart-bg'), gridC = cs.getPropertyValue('--grid'), fg = cs.getPropertyValue('--fg'), muted = cs.getPropertyValue('--muted');
  g.clearRect(0, 0, w, h);
  const now = samples.length ? samples[samples.length - 1].t : 0;
  const win = Math.max(120, now), t0 = 0;
  const left = 118, rowH = (h - 14) / SERIES.length;
  g.font = '11px ' + getComputedStyle(document.body).fontFamily;
  SERIES.forEach((s, i) => {
    const y0 = i * rowH, y1 = y0 + rowH - 3;
    g.fillStyle = bg; g.fillRect(left, y0, w - left, rowH - 3);
    g.fillStyle = muted; g.fillText(s.name, 2, y0 + 12);
    const cur = samples.length ? samples[samples.length - 1][s.k] : (s.k === 'llP' ? 760 : 0);
    g.fillStyle = fg; g.fillText(`${fmt(cur, s.k)} ${s.unit}`, 2, y0 + 25);
    const yv = v => s.log ? y1 - (Math.log10(clamp(v, s.min, s.max)) - Math.log10(s.min)) / (Math.log10(s.max) - Math.log10(s.min)) * (y1 - y0 - 4) : y1 - clamp(v / s.max, 0, 1) * (y1 - y0 - 4);
    g.strokeStyle = s.color; g.lineWidth = 1.5; g.beginPath();
    let started = false;
    for (const p of samples) {
      if (p.t < t0) continue;
      const x = left + (p.t - t0) / win * (w - left);
      if (!started) { g.moveTo(x, yv(p[s.k])); started = true; } else g.lineTo(x, yv(p[s.k]));
    }
    g.stroke();
  });
  // 终点标记
  if (E.tEp !== null && E.epT !== undefined && E.epT >= t0) {
    const x = left + (E.epT - t0) / win * (w - left);
    g.strokeStyle = '#d64545'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h - 14); g.stroke(); g.setLineDash([]);
    g.fillStyle = '#d64545'; g.fillText('终点', x + 3, h - 16);
  }
  g.fillStyle = muted;
  g.fillText(`0 ~ ${win.toFixed(0)} 秒（整个工艺）`, left, h - 2);
  $('#endp').textContent = E.tEp !== null ? `终点 @ 主刻 ${E.tEp.toFixed(1)} s` : (S.etching ? '等终点…' : '');
}

// ================= 界面 =================
const stepsEl = $('#steps');
STEPS.forEach(s => { const li = document.createElement('li'); li.textContent = s.name; stepsEl.appendChild(li); });
let stepIdx = -1, busy = false, done = false;
function renderSteps() {
  [...stepsEl.children].forEach((li, i) => { li.className = i < stepIdx || (done && i <= stepIdx) ? 'done' : i === stepIdx && busy ? 'cur' : ''; });
  const go = $('#go');
  if (done) { go.textContent = '↻ 再跑一片'; go.disabled = false; }
  else if (busy) { go.textContent = '进行中：' + STEPS[stepIdx].name + ' …'; go.disabled = true; }
  else { const n = STEPS[stepIdx + 1]; go.textContent = (stepIdx < 0 ? '▶ 开始：' : '▶ 下一步：') + n.name; go.disabled = false; }
  const st = $('#state');
  st.className = 'pill' + (busy || (stepIdx >= 0 && !done) ? ' run' : done ? ' ok' : '');
  st.textContent = done ? '完成' : stepIdx < 0 ? '待机' : busy ? `第 ${stepIdx + 1}/${STEPS.length} 步` : `等待第 ${stepIdx + 2} 步`;
  const locked = stepIdx >= 0 && !done;
  document.querySelectorAll('#fields input, #presets button').forEach(el => { el.disabled = locked; });
  $('#lockNote').hidden = !locked;
  $('#explode').disabled = locked;
}
function explain(title, now, why, err = false) {
  const ex = $('#explain');
  ex.classList.toggle('err', err);
  ex.querySelector('.t').textContent = title;
  ex.querySelector('.now').textContent = now;
  const w = ex.querySelector('.why');
  w.textContent = why || '';
  w.hidden = !why;
}
async function runStep(i) {
  busy = true; stepIdx = i;
  const st = STEPS[i];
  const now = typeof st.now === 'function' ? st.now() : st.now;
  explain(`第 ${i + 1} 步 · ${st.name}`, now, st.why);
  $('#caption').innerHTML = `<b>第 ${i + 1}/${STEPS.length} 步</b> · ${st.name}`;
  if (follow()) camTo(st.cam);
  renderSteps();
  await st.run();
  busy = false;
  if (i === STEPS.length - 1) { done = true; renderSteps(); finish(); return; }
  renderSteps();
  if (st.chain || $('#auto').checked) { await wait(st.chain ? 0.05 : 0.6); if (!busy && stepIdx === i) runStep(i + 1); }
}
function startOrNext() {
  if (busy) return;
  if (done) { resetAll(); return; }
  if (stepIdx < 0) {
    MDL = model(R);
    if (MDL.problem) { explain('配方检查没通过', MDL.problem + '到"配方"里改一下再开始。', '', true); return; }
    procT0 = simT; samples.length = 0; lastSample = -1;
    $('#explode').value = 0; S.explode = 0;
  }
  runStep(stepIdx + 1);
}
$('#go').addEventListener('click', startOrNext);
$('#auto').addEventListener('change', () => { if ($('#auto').checked && !busy && stepIdx >= 0 && !done) runStep(stepIdx + 1); });
$('#speed').addEventListener('change', e => { speed = +e.target.value; });
$('#pause').addEventListener('click', () => { paused = !paused; $('#pause').textContent = paused ? '▶ 继续' : '⏸ 暂停'; });

function resetAll() {
  resetState();
  stepIdx = -1; busy = false; done = false; procT0 = null; samples.length = 0; parts2d.length = 0;
  E.epT = undefined;
  explain('准备好了', '晶圆盒里又放了一片新的晶圆。可以先到"配方"里改参数，再点"开始"。', '每次只改一两个参数，对比结果最容易看出它的作用。');
  $('#caption').innerHTML = '点右边的 <b>▶ 开始</b>，一步一步把一片晶圆刻完。';
  if (follow()) camTo('overview');
  renderSteps();
}

// ---------- 结果 ----------
function finish() {
  const rmax = Math.max(...E.r);
  const residue = E.De < 99.9;
  const items = [
    { ok: !E.timeout && !residue, label: '多晶硅刻干净了', val: E.timeout ? '没刻完' : residue ? `边缘还剩 ${(100 - E.De).toFixed(0)} nm` : '干净',
      hint: E.timeout ? '主刻 180 秒还没到终点：偏压太低，离子没力气，氯几乎刻不动多晶硅。' : '过刻不够：中间先刻穿就判了终点，边缘还没刻完。过刻一般给 20~40%。' },
    { ok: rmax <= 6, label: '侧壁直（钻蚀 ≤ 6 nm）', val: `${rmax.toFixed(1)} nm`, hint: '往侧面刻掉太多：加 HBr / O₂ 保护侧壁，降低气压或温度。' },
    { ok: E.ox >= 2 && E.si === 0, label: '栅氧保住了（剩 ≥ 2 nm）', val: E.si > 0 ? `刻穿了，硅被挖下 ${E.si.toFixed(1)} nm` : `剩 ${E.ox.toFixed(1)} / 4 nm`, hint: '偏压太高，离子太猛，对栅氧的选择比下降；或者过刻太长。' },
    { ok: E.maskH >= 10, label: '光刻胶还有余量（≥ 10 nm）', val: `剩 ${E.maskH.toFixed(0)} / 60 nm`, hint: '光刻胶被打光了，栅极顶部也被刻掉：偏压太高或 O₂ 太多。' },
    { ok: E.tMain <= 120, label: '刻得够快（主刻 ≤ 120 秒）', val: `${E.tMain.toFixed(0)} 秒`, hint: '太慢，产量低：加源功率或偏压。' },
  ];
  const bad = items.filter(i => !i.ok).length;
  const v = $('#verdict');
  v.className = 'verdict ' + (bad ? 'bad' : 'ok');
  v.textContent = bad ? `有 ${bad} 项不合格` : '合格：这片晶圆的栅极刻得很好 ✓';
  $('#resList').innerHTML = items.map(i => `<li class="${i.ok ? 'ok' : 'bad'}"><div class="h"><span>${i.label}</span><span class="v">${i.val}</span></div>${i.ok ? '' : `<div class="hint">${i.hint}</div>`}</li>`).join('');
  $('#resStats').textContent = `多晶硅刻蚀速率 ${MDL.ERv.toFixed(0)} nm/min · 离子能量约 ${MDL.Ei.toFixed(0)} eV · 对栅氧选择比 ${MDL.sel.toFixed(0)} : 1 · 终点 ${E.timeout ? '未到' : E.tEp.toFixed(1) + ' s'} · 过刻 ${E.timeout ? 0 : (E.tMain * R.oe / 100).toFixed(1)} s`;
  $('#result').hidden = false;
  explain('完成', '晶圆已经放回晶圆盒。结果在弹窗里；关掉弹窗还能看左下角的剖面和曲线。', '');
  $('#caption').innerHTML = '<b>完成</b> · 点右边"再跑一片"，或者改配方再试';
}
$('#again').addEventListener('click', () => { $('#result').hidden = true; resetAll(); });
$('#tweak').addEventListener('click', () => { $('#result').hidden = true; resetAll(); showTab('recipe'); });
$('#resClose').addEventListener('click', () => { $('#result').hidden = true; });

// ---------- 配方页 ----------
const presetsEl = $('#presets'), fieldsEl = $('#fields');
function renderPresets() {
  presetsEl.innerHTML = '';
  for (const p of PRESETS) {
    const b = document.createElement('button');
    b.className = 'btn' + (FIELDS.every(f => R[f.k] === p.r[f.k]) ? ' on' : '');
    b.textContent = p.name;
    b.onclick = () => { R = { ...p.r }; syncFields(); };
    presetsEl.appendChild(b);
  }
}
for (const f of FIELDS) {
  const d = document.createElement('div');
  d.className = 'field';
  d.innerHTML = `<div class="top"><span>${f.name}</span><b><span data-v="${f.k}"></span> ${f.unit}</b></div>
    <input type="range" min="${f.min}" max="${f.max}" step="${f.step}" data-k="${f.k}"><div class="tip">${f.tip}</div>`;
  fieldsEl.appendChild(d);
}
fieldsEl.addEventListener('input', e => { const k = e.target.dataset.k; if (!k) return; R[k] = +e.target.value; syncFields(true); });
function syncFields(fromInput = false) {
  for (const f of FIELDS) {
    if (!fromInput) fieldsEl.querySelector(`input[data-k="${f.k}"]`).value = R[f.k];
    fieldsEl.querySelector(`[data-v="${f.k}"]`).textContent = R[f.k];
  }
  MDL = model(R);
  const m = MDL;
  const rows = m.problem ? [['问题', m.problem]] : [
    ['等离子体密度（相对）', m.n.toFixed(2)],
    ['离子能量', `约 ${m.Ei.toFixed(0)} eV`],
    ['多晶硅往下刻', `${m.ERv.toFixed(0)} nm/min`],
    ['往侧面刻', `${m.ERl.toFixed(1)} nm/min`],
    ['对栅氧选择比', `${m.sel.toFixed(0)} : 1`],
    ['光刻胶消耗', `${m.ERmask.toFixed(0)} nm/min`],
    ['预计主刻时间', m.ERv > 0.5 ? `${(100 / m.ERv * 60).toFixed(0)} s` : '刻不动'],
    ['中心/边缘速率差', `±${(m.u * 100).toFixed(1)}%`],
  ];
  $('#predict').innerHTML = rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join('');
  renderPresets();
}
syncFields();

// ---------- 零件页 ----------
{
  const byGroup = {};
  for (const p of Object.values(PARTS)) (byGroup[p.grp] ||= []).push(p);
  const pl = $('#plist');
  for (const [grp, list] of Object.entries(byGroup)) {
    const d = document.createElement('div');
    d.className = 'pgroup';
    d.innerHTML = `<h4>${grp}</h4><div class="plist">${list.map(p => `<button data-p="${p.id}">${p.name}</button>`).join('')}</div>`;
    pl.appendChild(d);
  }
  pl.addEventListener('click', e => { const id = e.target.dataset.p; if (id) selectPart(id, true); });
}
let selected = null;
function setHL(id, on) {
  if (!id) return;
  for (const o of PARTS[id].objs) o.traverse(m => {
    if (m.isMesh && m.material.emissive) { m.material.emissive.setHex(on ? 0xff7a1a : 0x000000); m.material.emissiveIntensity = on ? 0.55 : 1; }
  });
}
function selectPart(id, fromList = false) {
  setHL(selected, false);
  selected = id;
  setHL(id, true);
  document.querySelectorAll('#plist button').forEach(b => b.classList.toggle('on', b.dataset.p === id));
  const card = $('#partcard');
  if (!id) { card.hidden = true; return; }
  const p = PARTS[id];
  card.querySelector('h3').textContent = p.name;
  card.querySelector('.g').textContent = p.grp;
  card.querySelector('p').textContent = p.desc;
  card.hidden = false;
  if (fromList && p.grp.startsWith('工艺腔') && !busy) camTo(S.explode > 0.05 ? 'explode' : 'chamber');
}
$('#pcClose').addEventListener('click', () => selectPart(null));

// ---------- 页签、顶栏 ----------
function showTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => { t.hidden = t.id !== 'tab-' + name; });
}
document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
document.querySelectorAll('#views button').forEach(b => b.addEventListener('click', () => camTo(b.dataset.v)));
$('#cut').addEventListener('change', e => { CUT.constant = e.target.checked ? PM_Z : 1000; });
$('#labels').addEventListener('change', e => { labelRenderer.domElement.style.display = e.target.checked ? '' : 'none'; });
$('#explode').addEventListener('input', e => {
  S.explode = +e.target.value;
  if (S.explode > 0.05 && follow() && !camAnim) {
    const tgt = new THREE.Vector3(...VIEWS.explode.t);
    if (controls.target.distanceTo(tgt) > 0.2) camTo('explode');
  }
});
$('#dockToggle').addEventListener('click', () => { const d = $('#dock'); d.hidden = !d.hidden; $('#dockToggle').textContent = d.hidden ? '显示图表' : '隐藏图表'; });

// ---------- 实时数值 ----------
const VALS = [
  ['负载锁压力', () => `${fmt(S.llP, 'llP')} Torr`],
  ['腔压', () => `${fmt(S.chP, 'chP')} mTorr`],
  ['摆阀开度', () => `${S.valve.toFixed(0)} %`],
  ['Cl₂ / HBr / O₂', () => `${S.cl2.toFixed(0)} / ${S.hbr.toFixed(0)} / ${S.o2.toFixed(0)} sccm`],
  ['源功率 正向 / 反射', () => `${S.srcF.toFixed(0)} / ${S.srcR.toFixed(0)} W`],
  ['偏压功率', () => `${S.biasF.toFixed(0)} W`],
  ['离子能量', () => S.plasma > 0.05 ? `约 ${(S.biasF > 1 ? 15 + (MDL.Ei - 15) * S.biasF / Math.max(R.Wb, 1) : 15).toFixed(0)} eV` : '—'],
  ['卡盘电压', () => `${S.escV.toFixed(0)} V`],
  ['背面氦气', () => `${S.he.toFixed(1)} Torr`],
  ['晶圆温度', () => `${S.wT.toFixed(0)} °C`],
  ['刻蚀深度（中心）', () => `${E.Dc.toFixed(0)} / 100 nm`],
];
const valsEl = $('#vals');
valsEl.innerHTML = VALS.map(([a], i) => `<dt>${a}</dt><dd id="v${i}"></dd>`).join('');
const valEls = VALS.map((_, i) => $('#v' + i));
function updateVals() { VALS.forEach(([, f], i) => { valEls[i].textContent = f(); }); }

// ---------- 主题 ----------
function applyTheme() {
  const dark = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase() === '#101419';
  MAT.floor.color.setHex(dark ? 0x232a32 : 0xcfd5db);
  grid.material.color.setHex(dark ? 0x3a434d : 0xb3bcc4);
}
applyTheme();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
floor.material = MAT.floor;

// ---------- 点选 ----------
const ray = new THREE.Raycaster();
let downXY = null;
canvas.addEventListener('pointerdown', e => { downXY = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', e => {
  if (!downXY || Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1]) > 5) return;
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), camera);
  for (const h of ray.intersectObjects(scene.children, true)) {
    const o = h.object;
    if (!o.isMesh || !o.visible) continue;
    const m = o.material;
    if (m.userData.noPick || (m.transparent && m.opacity < 0.3)) continue;
    if (m.userData.clip && CUT.distanceToPoint(h.point) < 0) continue;
    selectPart(o.userData.part || null);
    return;
  }
  selectPart(null);
});

// ---------- 主循环 ----------
function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  labelRenderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);
resize();
renderSteps();

let last = performance.now(), chartAcc = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dtR = Math.min(0.05, (now - last) / 1000);
  last = now;
  const dt = paused ? 0 : dtR * speed;
  simT += dt;
  runTimers();
  physicsTick(dt);
  recordSample();
  visualsTick(dtR);
  if (camAnim) {
    camAnim.k = Math.min(1, camAnim.k + dtR / 1.2);
    const e = ease(camAnim.k);
    camera.position.lerpVectors(camAnim.p0, camAnim.p1, e);
    controls.target.lerpVectors(camAnim.t0, camAnim.t1, e);
    if (camAnim.k >= 1) camAnim = null;
  }
  controls.update();
  renderer.render(scene, camera);
  if ($('#labels').checked) labelRenderer.render(scene, camera);
  if (!$('#dock').hidden) drawProfile(dtR);
  chartAcc += dtR;
  if (chartAcc > 0.1) {
    chartAcc = 0;
    if (!$('#dock').hidden) drawChart();
    updateVals();
    $('#time').textContent = `${procT0 === null ? '0.0' : (simT - procT0).toFixed(1)} s`;
  }
}
requestAnimationFrame(frame);
