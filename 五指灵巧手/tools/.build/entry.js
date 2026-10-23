
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const D = window.__HAND;
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const DEG = Math.PI / 180;
const FN = D.fingers.map(f => f[0]);
const CNF = Object.fromEntries(D.fingers);

$('sSize').textContent = D.stats.size.join(' × ');
$('sParts').textContent = D.stats.parts;

// ---------- renderer / scene
const canvas = $('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, .5));
const key = new THREE.DirectionalLight(0xfff4e8, 1.7); key.position.set(-1.5, 2.5, 2.2); scene.add(key);
const rim = new THREE.DirectionalLight(0xdfeeff, 1.1); rim.position.set(1.2, 1.5, -2.5); scene.add(rim);
const camera = new THREE.PerspectiveCamera(32, 1, .005, 50);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = .08;
controls.minDistance = .14; controls.maxDistance = 1.6;
const TGT = new THREE.Vector3(0, .112, 0);
controls.target.copy(TGT);

// 展示台：一块浅色圆盘
const stand = new THREE.Mesh(new THREE.CylinderGeometry(.075, .085, .012, 64), new THREE.MeshStandardMaterial({ roughness: .55, metalness: .1 }));
stand.position.y = -.008; scene.add(stand);
function applyTheme() { stand.material.color.set(css('--line')); }
applyTheme();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

// ---------- hand
const outer = new THREE.Group(); scene.add(outer);
const exNodes = [];            // {obj, base, ex}
const joints = {};             // f -> [ {obj, q0, axis} ×4 ]
const meshesByKey = new Map(); // group key -> [mesh]
const groupInfo = new Map(D.groups.map(g => [g.key, g]));
const cur = {}, tgt = {};
for (const f of FN) { cur[f] = [...D.poses.rest[f]]; tgt[f] = [...D.poses.rest[f]]; }

function b64ToBuf(b64) {
  const s = atob(b64), u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return u.buffer;
}
new GLTFLoader().parse(b64ToBuf(window.__GLB_B64), '', gltf => {
  outer.add(gltf.scene);
  gltf.scene.traverse(o => {
    const ud = o.userData || {};
    if (ud.ex) exNodes.push({ obj: o, base: o.position.clone(), ex: JSON.parse(ud.ex) });
    if (ud.joint) {
      const j = JSON.parse(ud.joint);
      (joints[j.f] ??= [])[j.k] = { obj: o, q0: o.quaternion.clone(), axis: new THREE.Vector3(...j.axis) };
    }
    if (o.isMesh && ud.part_path) {
      o.material = o.material.clone();
      if (!meshesByKey.has(ud.part_path)) meshesByKey.set(ud.part_path, []);
      meshesByKey.get(ud.part_path).push(o);
    }
  });
  buildTree(); buildJointTable(); buildPoses();
  applyJoints();
  $('loading').hidden = true;
}, err => { $('loading').textContent = '模型载入失败：' + (err && err.message || err); });

// ---------- part tree
let selected = null;
function buildTree() {
  const ul = $('tree');
  const tops = [], byFinger = new Map();
  for (const g of D.groups) {
    const parts = g.key.split('/');
    const finger = FN.find(f => parts[1] === CNF[f]);
    if (finger) { if (!byFinger.has(finger)) byFinger.set(finger, []); byFinger.get(finger).push(g); }
    else tops.push(g);
  }
  const mk = (g, label) => {
    const b = document.createElement('button');
    b.dataset.key = g.key; b.setAttribute('aria-pressed', 'false');
    b.innerHTML = '<span></span><span class="q"></span>';
    b.children[0].textContent = label;
    b.children[1].textContent = g.n > 1 ? g.n + ' 件' : '';
    b.addEventListener('click', () => select(selected === g.key ? null : g.key));
    return b;
  };
  for (const g of tops) {
    const li = document.createElement('li'); li.className = 'top';
    const depth = g.key.split('/').length - 2;
    const b = mk(g, (depth > 0 ? '　' : '') + g.name);
    li.appendChild(b); ul.appendChild(li);
  }
  for (const f of FN) {
    const li = document.createElement('li');
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    const n = byFinger.get(f).reduce((a, g) => a + g.n, 0);
    sum.innerHTML = `<span>${CNF[f]}</span>`;
    sum.title = n + ' 件';
    det.appendChild(sum);
    for (const g of byFinger.get(f)) det.appendChild(mk(g, g.name));
    if (f === 'index') det.open = true;
    li.appendChild(det); ul.appendChild(li);
  }
}
function select(key) {
  selected = key;
  for (const b of document.querySelectorAll('#tree button')) b.setAttribute('aria-pressed', String(b.dataset.key === key));
  const hl = new THREE.Color(css('--hl'));
  for (const [k, list] of meshesByKey) for (const m of list) {
    if (!m.material.emissive) continue;
    const on = key && k === key;
    m.material.emissive.copy(on ? hl : new THREE.Color(0));
    m.material.emissiveIntensity = on ? .5 : 1;
  }
  if (key) {
    const g = groupInfo.get(key);
    $('cardT').textContent = g.key.split('/').slice(1).join(' · ');
    $('cardP').textContent = g.info || g.items.join('、');
    $('cardM').textContent = g.items.join(' / ') + (g.n > 1 ? `　共 ${g.n} 件` : '');
    const btn = document.querySelector(`#tree button[data-key="${CSS.escape(key)}"]`);
    if (btn) { const d = btn.closest('details'); if (d) d.open = true; btn.scrollIntoView({ block: 'nearest' }); }
  } else {
    $('cardT').textContent = '点零件看说明';
    $('cardP').textContent = '在模型上或零件树里点一个零件。下面可以切换手势、拖“拆开”看爆炸图。';
    $('cardM').textContent = '';
  }
}
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
let downAt = null;
canvas.addEventListener('pointerdown', e => { downAt = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', e => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  const r = canvas.getBoundingClientRect();
  ndc.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObject(outer, true).find(h => h.object.userData.part_path);
  select(hit ? hit.object.userData.part_path : null);
  if (hit) showTab('tree');
});

// ---------- side tabs
function showTab(t) {
  $('tabTree').setAttribute('aria-selected', String(t === 'tree'));
  $('tabJoint').setAttribute('aria-selected', String(t === 'joint'));
  $('treeBox').hidden = t !== 'tree'; $('jointBox').hidden = t !== 'joint';
  $('sideT').textContent = t === 'tree' ? '零件树' : '关节角 °';
}
$('tabTree').addEventListener('click', () => showTab('tree'));
$('tabJoint').addEventListener('click', () => showTab('joint'));

// ---------- joint table
const cells = {};
function buildJointTable() {
  const tb = document.querySelector('#jt tbody');
  for (const f of FN) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${CNF[f]}</td>` + [0, 1, 2, 3].map(() => '<td><span class="v">0</span><div class="m"><s></s><i></i></div></td>').join('');
    tb.appendChild(tr);
    cells[f] = [...tr.querySelectorAll('td')].slice(1).map(td => ({ v: td.querySelector('.v'), i: td.querySelector('i'), s: td.querySelector('s') }));
    const lim = D.limits[f === 'thumb' ? 'thumb' : 'finger'];
    cells[f].forEach((c, k) => {
      const [lo, hi] = lim['J' + (k + 1)];
      c.lo = lo; c.hi = hi; c.s.style.left = ((0 - lo) / (hi - lo) * 100) + '%';
    });
  }
}
function updateJointTable() {
  for (const f of FN) if (cells[f]) cells[f].forEach((c, k) => {
    const a = cur[f][k];
    c.v.textContent = (a >= 0 ? '' : '−') + Math.abs(a).toFixed(0);
    const z = (0 - c.lo) / (c.hi - c.lo), p = (a - c.lo) / (c.hi - c.lo);
    c.i.style.left = Math.min(z, p) * 100 + '%'; c.i.style.width = Math.abs(p - z) * 100 + '%';
  });
}

// ---------- poses / demo
let playing = true, seqIdx = 0, seqT = 0, poseNow = 'rest';
function buildPoses() {
  const host = $('poses');
  for (const [k, label] of D.poseNames) {
    const b = document.createElement('button');
    b.textContent = label; b.dataset.pose = k; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => { setPlaying(false); setPose(k); });
    host.appendChild(b);
  }
}
function setPose(k) {
  poseNow = k;
  for (const f of FN) tgt[f] = [...D.poses[k][f]];
  for (const b of document.querySelectorAll('#poses button')) b.setAttribute('aria-pressed', String(b.dataset.pose === k));
}
function setPlaying(p) {
  playing = p; $('play').setAttribute('aria-pressed', String(p));
  if (p) { seqIdx = 0; seqT = 0; setPose(D.seq[0][0]); }
}
$('play').addEventListener('click', () => setPlaying(!playing));
setPose('rest');

function applyJoints() {
  const q = new THREE.Quaternion();
  for (const f of FN) {
    const js = joints[f]; if (!js) continue;
    js.forEach((j, k) => { q.setFromAxisAngle(j.axis, cur[f][k] * DEG); j.obj.quaternion.copy(j.q0).multiply(q); });
  }
}

// ---------- explode / spin
let explode = 0, explodeTarget = 0, spinOn = false;
$('explode').addEventListener('input', e => { explodeTarget = e.target.value / 1000; });
$('spin').addEventListener('click', () => { spinOn = !spinOn; $('spin').setAttribute('aria-pressed', String(spinOn)); });
function applyExplode(t) {
  for (const n of exNodes) n.obj.position.set(n.base.x + n.ex[0] * t, n.base.y + n.ex[1] * t, n.base.z + n.ex[2] * t);
}

// ---------- camera / loop
function frameCamera() {
  const narrow = innerWidth < 760;
  camera.position.set(.2, narrow ? .19 : .17, narrow ? .58 : .46);
  controls.target.set(0, narrow ? .085 : .112, 0);
}
frameCamera();
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener('resize', resize); resize();

const clock = new THREE.Clock();
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), .1);
  if (exNodes.length) {
    if (playing) {
      seqT += dt;
      if (seqT > .9 + D.seq[seqIdx][1]) { seqIdx = (seqIdx + 1) % D.seq.length; seqT = 0; setPose(D.seq[seqIdx][0]); }
    }
    const k = reduce ? 1 : Math.min(1, dt * 6);
    for (const f of FN) for (let i = 0; i < 4; i++) cur[f][i] += (tgt[f][i] - cur[f][i]) * k;
    applyJoints(); updateJointTable();
    explode += (explodeTarget - explode) * (reduce ? 1 : Math.min(1, dt * 8));
    applyExplode(explode);
    if (spinOn && !reduce) outer.rotation.y += dt * .3;
  }
  controls.update();
  renderer.render(scene, camera);
});
