# ITBasics — 给 Claude 的入口

这是用户（朱）的个人仓库，每个顶层文件夹是一个独立的小项目。动手前先读对应项目的交接文档：

| 项目 | 先读 |
|---|---|
| VR 海边别墅 · UE 5.8 院落别墅（VillaVR / L_Courtyard） | `VR海边别墅/ue_courtyard/交接_给新对话.md` |
| 无刷电机爆炸图（Blender 脚本建模 + 网页查看器） | `无刷电机爆炸图/README.md` |
| 三相电机爆炸图（三相异步电机：Blender 脚本建模 + 结构/原理/电动/发电网页） | `三相电机爆炸图/README.md` |
| 涵道无人机（原创 3 寸涵道机：Blender 脚本建模 + 飞行演示 + 爆炸图） | `涵道无人机/README.md` |
| E235 电车模型（Blender 脚本建模 + 网页查看器，门/灯可动） | `E235电车模型/README.md` |
| 迷你车床爆炸图（8 合 1 迷你桌面车床：Blender 脚本建模 + 爆炸图，导进 MyVRToyBox） | `迷你车床爆炸图/README.md` |
| 气动阀门爆炸图（three.js 网页：DN80 气动蝶阀 + 气动球阀原稿；蝶阀也导进了 VR 玩具箱） | `气动阀门爆炸图/README.md` |
| 万用表爆炸图（数字万用表，外观参考 SATA DO5054：Blender 脚本建模 + 原理爆炸图，导进 MyVRToyBox） | `万用表爆炸图/README.md` |
| AI 服务器爆炸图（8U 八卡 HGX 训练服务器，按 GPU 一级合并成 32 个部件（GPU 和散热器分开）：Blender 脚本建模 + 原理爆炸图，导进 MyVRToyBox） | `AI服务器爆炸图/README.md` |
| 四缸发动机爆炸图（通用 2.0L DOHC 16V 直列四缸：Blender 脚本建模 + 原理爆炸图，48 个可抓单元 + 缸体底座，导进 MyVRToyBox） | `四缸发动机爆炸图/README.md` |
| 五指灵巧手（20 自由度直驱手，关节布局参考 Wuji Hand 2 公开 URDF：零件树 + 共享参数表 params.json + 逐件建模，手势由求解器避开穿模，网页查看器；`export_ue.py` 导进 MyVRToyBox） | `五指灵巧手/README.md` |
| 干法刻蚀机（原创 ICP 刻蚀机教学：离线网页里操作机台跑完一次工艺；后续 Blender 建模 + VR 见搭建路线） | `干法刻蚀机/README.md` |

通用约定：
- 回答用中文；改完 push 到 `main`。
- 写程序要带 Windows 一键启动 `.bat`，bat 里先 `git pull --ff-only origin main` 检查更新。
- bat 文件只写 ASCII（中文注释会因为代码页乱码），CRLF 换行。
