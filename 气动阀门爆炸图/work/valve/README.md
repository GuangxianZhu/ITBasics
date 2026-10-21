# 气动蝶阀爆炸图 · 工程实现说明

成品是工作目录根下的 **`气动蝶阀爆炸图.html`**（单文件、离线可用、约 750 KB）。
双击即可打开；拖动旋转、滚轮缩放、点零件或编号看说明、底部滑杆控制爆炸程度。

## 目录

```
气动蝶阀爆炸图.html      产物：three.js（压缩）+ 应用代码（未压缩）+ CSS 全内联
shots/                   无头 Chrome 截图（爆炸 / 选中 / 装配全开 / 手机）
work/orig/
  pbv.html               用户给的原始参考文件（气动球阀）
  app.pretty.js          从参考文件里抽出来并格式化的应用代码（约 1500 行，拆解用）
work/valve/
  src/00-scene.js        渲染器、相机、灯光、材质库、几何工具（回转/拉伸/齿轮/螺旋线）
  src/10-parts.js        21 个零件的建模与爆炸位移（全部按 mm 手写尺寸）
  src/20-ui.js           取景、爆炸动画、阀门动作、气泡编号、零件表、拾取
  src/style.css          图纸风格的 UI
  src/index.html         页面骨架（构建时注入 CSS/JS）
  build.mjs              esbuild 打包 three.js → 拼装单文件 HTML
  tools/verify.mjs       通过 CDP 驱动真实页面做交互回归 + 截图
  tools/mobile.mjs       手机视口下的取景检查
```

## 构建

```powershell
cd work\valve
node build.mjs            # 输出 ..\..\气动蝶阀爆炸图.html
```

依赖已在 `work/node_modules`（three 0.170、esbuild、puppeteer-core）。
esbuild 用子进程（`stdio: inherit`）调用，避免沙箱禁止管道 stdio。

## 怎么改

- **改尺寸**：`10-parts.js` 顶部一组常量（`R_BORE / R_OD / FACE / YA / Y_MID / CYL …`），
  零件的轮廓点都写成 `[半径, 高度, 圆角?]` 的数组，改数字即可。
- **加零件**：`part({no, cn, en, jp, mat, qty, desc})` 注册文字信息，
  `place(零件, group([几何, "材质名"]), [[x, y, z, 延迟]])` 放进装配体。
  `ex` 的第 4 项是错峰延迟（0–1），爆炸时不同零件依次入场。
- **改爆炸幅度**：`EX_X / EX_Y / EX_Z` 按轴缩放所有位移；单个零件的位移写在 `place(...)` 里。
- **加材质**：`00-scene.js` 的 `PRESET` 表，键名即 `group([[geo, "键名"]])` 里用的名字。
- **换产品**：`10-parts.js` 整体替换，`20-ui.js` 里的 `PARTS` 驱动部分（气泡、零件表、拾取）不用改。

## 调试 / 截图用的 URL 参数

`气动蝶阀爆炸图.html#t=1&stroke=0&sel=3&bom=0&lbl=1&cam=x,y,z,tx,ty,tz&fov=26&only=1,2,3`

| 参数 | 作用 |
|---|---|
| `t` | 爆炸进度 0–1（省略则播放开场动画） |
| `stroke` | 阀门动作 0 全关 / 1 全开 |
| `sel` | 直接选中某个零件号 |
| `bom` / `lbl` | 0/1 开关零件表和编号 |
| `cam` / `fov` | 固定机位与视场角（调试或出图） |
| `only` | 只显示指定零件号，其余隐藏（排查几何用） |
