// Builds a single self-contained HTML: inlined three.js (minified IIFE) + app code (readable) + CSS.
// esbuild is called as a child process with inherited stdio (the sandbox forbids piped stdio).
import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = (p) => path.join(here, "src", p);
const outFile = process.argv[2] || path.join(here, "..", "..", "气动蝶阀爆炸图.html");
const esbuild = path.join(here, "..", "node_modules", "@esbuild", "win32-x64", "esbuild.exe");
const buildDir = path.join(here, ".build");
await mkdir(buildDir, { recursive: true });

const t0 = Date.now();
const vendorOut = path.join(buildDir, "vendor.js");
const r = spawnSync(
  esbuild,
  [src("vendor.js"), "--bundle", "--minify", "--format=iife", "--target=es2020",
    "--legal-comments=none", "--charset=utf8", `--outfile=${vendorOut}`],
  { stdio: "inherit" },
);
if (r.status !== 0) process.exit(r.status ?? 1);
const vendorJs = await readFile(vendorOut, "utf8");

const parts = ["00-scene.js", "10-parts.js", "20-ui.js"];
let appJs = "";
for (const f of parts) appJs += (await readFile(src(f), "utf8")).replace(/\n+$/, "") + "\n\n";
appJs =
  "(() => {\n'use strict';\ntry {\n" +
  appJs +
  "\n} catch (e) { document.documentElement.dataset.fatal = (e && e.stack) || String(e); console.error(e); }\n})();\n";

const css = await readFile(src("style.css"), "utf8");
let html = await readFile(src("index.html"), "utf8");
html = html
  .replace("{{CSS}}", () => css.trim())
  .replace("{{VENDOR}}", () => vendorJs.trim())
  .replace("{{APP}}", () => appJs.trim());

await writeFile(outFile, html, "utf8");
const kb = (s) => Math.round(s.length / 1024);
console.log(
  `built ${path.relative(process.cwd(), outFile)}  total ${kb(html)}KB  (vendor ${kb(vendorJs)}KB, app ${kb(appJs)}KB, css ${kb(css)}KB)  ${Date.now() - t0}ms`,
);
