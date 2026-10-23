import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { readFileSync } from 'node:fs';
const buf = readFileSync('../output/hand.glb');
const D = JSON.parse(readFileSync('../output/hand_data.json', 'utf8'));
const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
new GLTFLoader().parse(ab, '', gltf => {
  const joints = {}, ex = []; let meshes = 0;
  gltf.scene.traverse(o => {
    const ud = o.userData || {};
    if (ud.ex) ex.push(o);
    if (ud.joint) { const j = JSON.parse(ud.joint); (joints[j.f] ??= [])[j.k] = { obj: o, q0: o.quaternion.clone(), axis: new THREE.Vector3(...j.axis) }; }
    if (o.isMesh && ud.part_path) meshes++;
  });
  console.log('ex', ex.length, 'meshes w/ part', meshes, 'joints', Object.fromEntries(Object.entries(joints).map(([k, v]) => [k, v.filter(Boolean).length])));
  const q = new THREE.Quaternion();
  for (const pose of ['fist', 'pinch', 'spread']) {
    for (const f in joints) joints[f].forEach((j, k) => { q.setFromAxisAngle(j.axis, D.poses[pose][f][k] * Math.PI / 180); j.obj.quaternion.copy(j.q0).multiply(q); });
    gltf.scene.updateMatrixWorld(true);
    const out = {};
    for (const f of ['index', 'thumb']) { const p = new THREE.Vector3(); gltf.scene.getObjectByName(f + '_tip').getWorldPosition(p); out[f] = [p.x * 1000, -p.z * 1000, p.y * 1000].map(v => +v.toFixed(1)); }
    console.log(pose, JSON.stringify(out));
  }
}, e => console.error('ERR', e));
