# 海边别墅 → Unreal Engine 5.8 迁移方案（草案，未动代码）

## 现状：两段流水线
```
Blender Python（几何 + 资产）                        Godot（运行时）
build_villa.py 893 行 / scene_extras.py 384        main.gd 1041   材质、碰撞、门、灯、GI、点位
furniture_slots.py 445（AI 家具清理）              player.gd 587  走/跑/游泳/潜水/瞬移/坐/抓/扔
make_assets.py 494（程序贴图 + 声音）               world_fx.gd 306、audio_fx.gd 112
export_godot.py 158 → villa.glb + villa_meta.json   water.gdshader + water_math.gd（Gerstner 浪）
                                                    tests.gd 199（23 项自动测试）
```
接口：**物体名字就是接口**（滑门_* / 开关_* / 碰撞_* / 灯位_* / 可拿_* / 名字含"座"…）。

## 复用 / 重写对照
| 部分 | 结论 | 说明 |
|---|---|---|
| 几何（build_villa + scene_extras） | **直接复用** | 继续在 Blender 生成，导出 glb/FBX 给 UE。尺寸仍然只改一处 |
| AI 家具（Hunyuan3D + furniture_slots） | **直接复用** | 输出本来就是 glb，与引擎无关 |
| 程序贴图、声音（make_assets） | **复用文件** | png / wav 直接导入；材质要在 UE 里重新连 |
| villa_meta.json（点位、灯位） | **复用数据** | UE Python 读它摆 Actor |
| 命名约定（名字=接口） | **复用规则** | UE 导入脚本按名字把物体换成对应的蓝图/组件 |
| 浪的数学（water_math） | 复用公式，代码重写 | 或直接用 UE Water 插件（自带 Gerstner + 浮力） |
| 材质（main.gd 里 ~300 行） | **重写** | UE 母材质 + 材质实例，Python 批量生成 |
| 天空、昼夜 | **重写，但更省事** | SkyAtmosphere + 体积云 + 太阳角度 |
| 全局光照 | **重写，且是最大风险** | VR 模板是前向渲染，Lumen 关；昼夜切换要动态 GI → 必须先实测 |
| 玩家（player.gd） | **重写** | VR 模板自带瞬移、抓取；游泳/潜水/平滑移动/坐下要自己写 |
| 交互（门、冰箱、电视、KTV、烧烤炉…） | **重写** | 一个"可交互"接口 + 各自的 Actor |
| 声音效果（闷音、分地面脚步） | **重写，但更省事** | 物理材质 + 声音衰减/遮挡是 UE 内置功能 |
| 自动测试 23 项 | **重写** | UE 自动化测试 / 功能测试；MCP 有 AutomationTest 工具集 |

粗算：Blender 侧约 2400 行**全留**；Godot 侧约 2500 行**全部换写法**。

## 三个方向
- **A（推荐，主流做法）Blender 管几何，UE 管运行时**：DCC → 引擎的标准流水线。Godot 版不受影响，两边共用一份几何。
- **B 全部搬进 UE Python**：几何也在 UE 里生成。单一工具链，MCP 能实时改；但 1300 行建模要重写，Godot 版脱钩。
- **C 先做"看房版"**：只导入 + 材质 + 光照 + VR 模板瞬移，不做游泳/KTV。最快看到 UE 画质，用来决定值不值得做 A 的完整版。

## 必须先验证的三件事（决定成败）
1. **GI**：前向渲染 + 补光 / 延迟渲染 + Lumen（VR 下帧率？）/ 烘焙（失去昼夜动态）三选一，用 Quest 3 实测。
2. **glTF 导入是否保留层级和名字**（尤其中文名）；不行就在导出时改成 ASCII 名 + 映射表。
3. **游戏逻辑用 C++ 还是蓝图**：AI 写 C++ 是文本、可 diff、可 git；蓝图是二进制图，AI 通过 MCP 编辑能力有限。C++ 需要装 VS 2022 生成工具。
