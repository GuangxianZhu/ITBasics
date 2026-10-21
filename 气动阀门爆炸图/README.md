# 气动阀门爆炸图（three.js 网页）

两个单文件、离线可用的网页爆炸图，双击 html 就能看（拖动旋转、滚轮缩放、点零件看说明、底部滑杆控制爆炸程度）：

| 文件 | 内容 |
|---|---|
| `气动蝶阀爆炸图.html` | **DN80 对夹式气动蝶阀** + 齿轮齿条单作用执行器，21 种零件（38 个），全部按毫米手写建模。源码在 `work/valve/` |
| `气动球阀爆炸图.html` | 更早的**气动球阀**，是蝶阀的参考原稿。只有打包好的单文件；`work/orig/app.pretty.js` 是从里面抽出来格式化的应用代码，供参考 |

原来放在电脑上的 `C:\work\codex_localAI`（不在 git 里），2026-10-20 搬进 ITBasics。

## 用法

双击 `启动.bat`：

1. `git pull --ff-only origin main` 检查更新（没网或没装 git 就跳过）
2. 第一次运行时在 `work\` 下 `npm install`（three、esbuild、puppeteer-core，约 90 MB，不提交到 git）
3. `node work\valve\build.mjs` 重新打包 `气动蝶阀爆炸图.html`
4. 打开两个 html

需要 Node.js。只想看不想改的话，不用跑 bat，直接双击 html。

## 改模型

蝶阀的工程说明（目录、怎么改尺寸 / 加零件 / 改爆炸幅度、调试用 URL 参数）见 [`work/valve/README.md`](work/valve/README.md)。

- `work/valve/tools/verify.mjs`、`mobile.mjs` 是交互回归 + 截图脚本，连的是已经开着远程调试端口（9222）的 Chrome；里面写死了原来的路径 `C:/work/codex_localAI/...`，在这里用要先改成本目录。

## 也进了 VR 玩具箱

蝶阀已经导进 UE 5.8 的 VR 玩具箱（GuangxianZhu/MyVRToyBox，`Content/Models/Valve`）：桌上能摆出来、爆炸 / 装配、零件能抓起来看。
那边的 `scripts/import_valve.bat` 会用无头 Chrome 跑这里的源码，把零件导成 glb 再导入；设置环境变量 `VALVE_DIR` 指向本目录下的 `work\valve` 即可。
