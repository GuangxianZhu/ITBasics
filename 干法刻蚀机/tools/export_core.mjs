// 把 web/etch_core.js 里的配方、讲解文字导出成 JSON，给虚幻工程 MyVRToyBox 用；再用 simulateEtch() 算一组标准答案。
//
//   node export_core.mjs        → output/etcher_content.json、output/etcher_golden.json
//
// MyVRToyBox 的 scripts/import_etcher.bat 会把这两个文件拷到 Content/Etcher/；
// 那边的 C++（ToyEtchCore）照 etch_core.js 翻译，toy.EtchSelfTest 拿 etcher_golden.json 对答案。
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as C from '../web/etch_core.js';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..', 'output');
mkdirSync(out, { recursive: true });

const content = {
  source: '干法刻蚀机/web/etch_core.js',
  mainTimeout: C.MAIN_TIMEOUT,
  presets: C.PRESETS,
  fields: C.FIELDS,
  problems: C.PROBLEMS,
  steps: C.STEP_TEXT,
  explain: C.EXPLAIN,
  results: C.RESULT_TEXT,
  verdict: C.VERDICT,
  particles: C.PARTICLE_NAMES,
  series: C.SERIES_TEXT,
  parts: C.PART_INFO.map(([id, group, name, desc]) => ({ id, group, name, desc })),
};
writeFileSync(join(out, 'etcher_content.json'), JSON.stringify(content, null, 1) + '\n');

// 标准答案：5 个预置配方 + 一批随机配方（固定种子，每次一样），按 FIELDS 的范围和步长取值
let seed = 20261025;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const recipes = C.PRESETS.map(p => ({ id: p.id, r: { ...p.r } }));
for (let i = 0; i < 60; i++) {
  const r = {};
  for (const f of C.FIELDS) r[f.k] = f.min + Math.round(rnd() * (f.max - f.min) / f.step) * f.step;
  recipes.push({ id: 'rnd' + i, r });
}
const round = x => (x === null ? null : typeof x === 'number' ? +x.toPrecision(10) : x);
const cases = recipes.map(({ id, r }) => {
  const { M, E, res } = C.simulateEtch(r);
  const m = Object.fromEntries(['n', 'Ei', 'Gn', 'ERv', 'ERl', 'ERox', 'ERmask', 'u', 'pass', 'sel', 'total'].map(k => [k, round(M[k])]));
  const c = { id, r, problemCode: M.problemCode, model: m };
  if (E) {
    c.etch = Object.fromEntries(['Dc', 'De', 'maskH', 'ox', 'si', 'gateLoss', 'tEp', 'tMain', 'uncleared', 'oesF'].map(k => [k, round(E[k])]));
    c.etch.timeout = E.timeout;
    c.etch.rmax = round(res.rmax);
    c.ok = res.ok;
  }
  return c;
});
writeFileSync(join(out, 'etcher_golden.json'), JSON.stringify({ dt: 0.05, cases }, null, 1) + '\n');
const bad = cases.filter(c => c.ok && c.ok.includes(false)).length;
console.log(`etcher_content.json：${content.steps.length} 步、${content.parts.length} 个零件；etcher_golden.json：${cases.length} 组（${cases.filter(c => c.problemCode).length} 组点不着，${bad} 组有不合格项）`);
