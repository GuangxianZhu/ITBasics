// 把 viewer_src.html（three.js 走 CDN）打包成 viewer_template.html（three.js 内嵌，离线可用）。
// 只有改了网页源码才需要跑；普通使用不用装 Node。
//
//   cd tools && npm install --no-save esbuild@0.24.0 three@0.170.0 && node make_template.mjs
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, '..', 'viewer_src.html'), 'utf8');

const modRe = /<script type="module">([\s\S]*?)<\/script>/;
const mapRe = /<script type="importmap">[\s\S]*?<\/script>\s*/;
const m = src.match(modRe);
if (!m) throw new Error('module script not found');

const tmp = join(here, '.build');
mkdirSync(tmp, { recursive: true });
const entry = join(tmp, 'entry.js');
writeFileSync(entry, m[1].replaceAll("'three/addons/", "'three/examples/jsm/"));

const out = await build({
  entryPoints: [entry], bundle: true, format: 'iife', minify: true, write: false,
  target: 'es2020', nodePaths: [join(here, 'node_modules')], legalComments: 'none',
});
const js = out.outputFiles[0].text.replaceAll('</script', '<\\/script');

// 发布到 claude.ai 时平台会自动套上 doctype/head；离线文件要自己带。
// 数据占位符（__GLB_BASE64__ / __HAND_JSON__）在 viewer_src.html 里，build_hand.py 负责填。
const head = '<!doctype html>\n<html lang="zh-CN">\n<meta charset="utf-8">\n' +
  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n';
const html = head + src.replace(mapRe, '').replace(modRe, () => '<script>' + js + '</script>');
writeFileSync(join(here, '..', 'viewer_template.html'), html);
console.log('viewer_template.html', (html.length / 1024).toFixed(0), 'KB');
