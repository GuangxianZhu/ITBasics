/* ============================================================================
   0 · 场景 / 相机 / 灯光 / 材质 / 几何工具
   坐标约定：X = 介质流向，Y = 阀杆与齿轮轴方向，Z = 气缸与活塞行程方向。单位 mm。
   ========================================================================== */
const T = window.THREE;
const V2 = T.Vector2;
const V3 = T.Vector3;

const canvas = document.getElementById("c");
const renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = T.SRGBColorSpace;
renderer.toneMapping = T.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = T.PCFSoftShadowMap;
renderer.setClearColor(0x000000, 0);

const scene = new T.Scene();
const pmrem = new T.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new T.RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 1.02;

const camera = new T.PerspectiveCamera(30, 1, 2, 9000);
camera.position.set(520, 380, 620);

const controls = new T.OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.085;
controls.minDistance = 120;
controls.maxDistance = 6000;
controls.maxPolarAngle = Math.PI * 0.96;

/* 主光：工程图式的干净侧上方光 + 冷色轮廓光 */
const key = new T.DirectionalLight(0xffffff, 2.5);
key.position.set(300, 520, 340);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -460, right: 460, top: 460, bottom: -460, near: 10, far: 2000 });
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.6;
scene.add(key, key.target);

const rim = new T.DirectionalLight(0xdfe9ff, 1.0);
rim.position.set(-360, 200, -400);
scene.add(rim);

const fill = new T.HemisphereLight(0xffffff, 0x8b949c, 0.45);
scene.add(fill);

/* 地面：只接收阴影，不画实体 */
const ground = new T.Mesh(new T.PlaneGeometry(7000, 7000), new T.ShadowMaterial({ opacity: 0.22 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

/* ---------------------------------------------------------------- 材质库 */
const PRESET = {
  body: { color: 0x64717d, metalness: 0.45, roughness: 0.5 }, // 球铁环氧涂层
  bodyDark: { color: 0x505b66, metalness: 0.45, roughness: 0.55 },
  iron: { color: 0x7d858d, metalness: 0.9, roughness: 0.44 },
  ss: { color: 0xc7ccd1, metalness: 1, roughness: 0.3 },
  mirror: { color: 0xeef1f3, metalness: 1, roughness: 0.07 },
  epdm: { color: 0x2a2e33, metalness: 0, roughness: 0.74 },
  ptfe: { color: 0xf2efe6, metalness: 0, roughness: 0.6, sheen: 0.35, sheenColor: 0xffffff },
  nbr: { color: 0x1c1f22, metalness: 0, roughness: 0.82 },
  alu: { color: 0xb9bfc5, metalness: 0.9, roughness: 0.4 },
  aluDark: { color: 0x8d949b, metalness: 0.85, roughness: 0.5 },
  blue: { color: 0x2f4f7d, metalness: 0.25, roughness: 0.4, clearcoat: 0.5, clearcoatRoughness: 0.28 },
  zinc: { color: 0xb2b8bf, metalness: 1, roughness: 0.27 },
  black: { color: 0x24282c, metalness: 0.5, roughness: 0.42 },
  nickel: { color: 0xd2d7dc, metalness: 1, roughness: 0.19 },
  spring: { color: 0x8d9297, metalness: 0.85, roughness: 0.34 },
  brass: { color: 0xc7a12c, metalness: 1, roughness: 0.45 },
  coil: { color: 0x1b1e22, metalness: 0, roughness: 0.38, clearcoat: 0.6, clearcoatRoughness: 0.24 },
  red: { color: 0xbb3b2c, metalness: 0, roughness: 0.4, clearcoat: 0.4 },
  yellow: { color: 0xe0ae2e, metalness: 0, roughness: 0.34, clearcoat: 0.6 },
  hole: { color: 0x080a0c, metalness: 0, roughness: 0.95 },
  sealBlue: { color: 0x2b6ea8, metalness: 0, roughness: 0.42 },
};
const mat = (k) => {
  if (!PRESET[k]) throw new Error("unknown material: " + k);
  return new T.MeshPhysicalMaterial({ ...PRESET[k], side: T.DoubleSide });
};
/* 选中/悬停时加自发光，每个网格独立材质，避免互相串色 */
const hlColor = new T.Color(0xc9761a);

/* ---------------------------------------------------------------- 几何工具 */
/* 折线轮廓 → 带圆角的内外点列。点格式 [r, y, 圆角半径?]（圆角半径可逐点覆盖） */
function outline(pts, radius = 0.6, closed = true) {
  const n = pts.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    const p = pts[i];
    const rr = p.length > 2 ? p[2] : radius;
    const end = !closed && (i === 0 || i === n - 1);
    if (end || rr <= 0) {
      out.push(new V2(p[0], p[1]));
      continue;
    }
    const a = pts[(i - 1 + n) % n];
    const b = pts[(i + 1) % n];
    const ax = a[0] - p[0], ay = a[1] - p[1];
    const bx = b[0] - p[0], by = b[1] - p[1];
    const la = Math.hypot(ax, ay) || 1, lb = Math.hypot(bx, by) || 1;
    const m = Math.min(rr, la * 0.45, lb * 0.45);
    out.push(new V2(p[0] + (ax / la) * m, p[1] + (ay / la) * m));
    out.push(new V2(p[0] + (bx / lb) * m, p[1] + (by / lb) * m));
  }
  if (closed) out.push(out[0].clone());
  return out;
}

/* 回转体：轮廓点 [r, y] 绕 Y 轴回转；折边法线让端面与倒角保持锐利 */
function lathe(pts, opts = {}) {
  const { segments = 96, radius = 0.6, closed = true } = opts;
  return T.toCreasedNormals(new T.LatheGeometry(outline(pts, radius, closed), segments), 0.5);
}
/* 绕 X 轴的回转体（管道方向：法兰、阀座、蝶板） */
const latheX = (g) => g.rotateZ(-Math.PI / 2);
/* 绕 Z 轴的回转体（活塞、端盖中心体） */
const latheZ = (g) => g.rotateX(Math.PI / 2);

/* 拉伸：默认沿 +Z，深度含倒角；折边法线让平面保持锐利 */
function extrude(shape, depth, bevel = 0.6, curveSegments = 32) {
  const g = new T.ExtrudeGeometry(shape, {
    depth: Math.max(depth - 2 * bevel, 0.01),
    bevelEnabled: bevel > 0,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelOffset: -bevel,
    bevelSegments: 1,
    curveSegments,
    steps: 1,
  });
  g.translate(0, 0, bevel);
  return T.toCreasedNormals(g, 0.55);
}
const extrudeX = (shape, depth, x, bevel = 0.6, cs = 32) =>
  extrude(shape, depth, bevel, cs).rotateY(Math.PI / 2).translate(x, 0, 0);
const extrudeY = (shape, depth, y, bevel = 0.6, cs = 32) =>
  extrude(shape, depth, bevel, cs).rotateX(-Math.PI / 2).translate(0, y, 0);
const extrudeZ = (shape, depth, z, bevel = 0.6, cs = 32) => extrude(shape, depth, bevel, cs).translate(0, 0, z);

/* 2D 图形 */
function circlePath(x, y, r) {
  const p = new T.Path();
  p.absarc(x, y, r, 0, Math.PI * 2, true);
  return p;
}
function ringShape(rOuter, rInner, cx = 0, cy = 0) {
  const s = new T.Shape();
  s.absarc(cx, cy, rOuter, 0, Math.PI * 2, false);
  s.holes.push(circlePath(cx, cy, rInner));
  return s;
}
function roundRectShape(hx, hy, r, cx = 0, cy = 0) {
  const s = new T.Shape();
  const x0 = cx - hx, x1 = cx + hx, y0 = cy - hy, y1 = cy + hy;
  s.moveTo(x0 + r, y0);
  s.lineTo(x1 - r, y0);
  s.absarc(x1 - r, y0 + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x1, y1 - r);
  s.absarc(x1 - r, y1 - r, r, 0, Math.PI / 2, false);
  s.lineTo(x0 + r, y1);
  s.absarc(x0 + r, y1 - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x0, y0 + r);
  s.absarc(x0 + r, y0 + r, r, Math.PI, Math.PI * 1.5, false);
  return s;
}
function hexShape(acrossFlats, holeR = 0, rot = 0) {
  const R = acrossFlats / Math.sqrt(3);
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = rot + (i * Math.PI) / 3;
    pts.push(new V2(R * Math.cos(a), R * Math.sin(a)));
  }
  const s = new T.Shape(pts);
  if (holeR > 0) s.holes.push(circlePath(0, 0, holeR));
  return s;
}
/* 齿轮轮廓：齿数、齿根半径、齿顶半径 */
function gearShape(teeth, rRoot, rTip, holeR = 0) {
  const pts = [];
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    const step = (Math.PI * 2) / teeth;
    pts.push(new V2(rTip * Math.cos(a), rTip * Math.sin(a)));
    pts.push(new V2(rRoot * Math.cos(a + step * 0.5), rRoot * Math.sin(a + step * 0.5)));
  }
  const s = new T.Shape(pts);
  if (holeR > 0) s.holes.push(circlePath(0, 0, holeR));
  return s;
}

/* 螺旋线（弹簧）：沿 +Z 生长 */
class Helix extends T.Curve {
  constructor(radius, turns, length) {
    super();
    this.radius = radius;
    this.turns = turns;
    this.length = length;
  }
  getPoint(t, target = new V3()) {
    const a = t * this.turns * Math.PI * 2;
    return target.set(this.radius * Math.cos(a), this.radius * Math.sin(a), t * this.length);
  }
}
const helixGeo = (r, turns, len, wire = 1.4) =>
  new T.TubeGeometry(new Helix(r, turns, len), Math.ceil(turns * 24), wire, 7, false);

/* 一个小工具：把若干 [geometry, material] 打进一个 Group */
function group(...items) {
  const g = new T.Group();
  for (const [geo, m] of items) g.add(new T.Mesh(geo, mat(m)));
  return g;
}
/* Z 向镜像（对称零件：左右活塞、两端盖） */
function mirrorZ(g) {
  const out = new T.Group();
  g.rotation.y = Math.PI;
  out.add(g);
  return out;
}
