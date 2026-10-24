// 把 web/index.html + web/app.js（three.js 走 CDN，开发用）打包成一个离线 html：three.js 内嵌，双击就能打开。
//
//   cd tools && npm install --no-save esbuild@0.24.0 three@0.170.0 && node build_offline.mjs
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const html = readFileSync(join(root, 'web', 'index.html'), 'utf8');

const out = await build({
  entryPoints: [join(root, 'web', 'app.js')], bundle: true, format: 'iife', minify: true, write: false,
  target: ['es2017', 'chrome64', 'safari12'], nodePaths: [join(here, 'node_modules')], legalComments: 'none',
});
const js = out.outputFiles[0].text.replaceAll('</script', '<\\/script');

const page = html
  .replace(/<script type="importmap">[\s\S]*?<\/script>\s*/, '')
  .replace('<script type="module" src="./app.js"></script>', () => '<script>' + js + '</script>');
mkdirSync(join(root, 'output'), { recursive: true });
const dst = join(root, 'output', '干法刻蚀机_离线版.html');
writeFileSync(dst, page);
console.log(dst, (page.length / 1024).toFixed(0), 'KB');
