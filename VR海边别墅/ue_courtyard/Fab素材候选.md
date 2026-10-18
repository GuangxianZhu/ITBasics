# Fab 素材候选（地中海庭院 · UE 5.8 · Quest 3 forward）

调研日期 2026-10-18。价格和许可会变，**下单前在浏览器里核对**。Fab 的价格是网页动态加载的，自动抓取看不到，所以很多条目写"未显示"。

**和现在场景的关系：**
- 橄榄、无花果、盆栽柠檬、薰衣草、迷迭香、九重葛已经用程序化植物 + 本地 Z-Image 叶片贴图做了（`c8x_trees.py`），Fab 上反而找不到合适的无花果、柠檬盆栽和三角梅。
- 最值得买的是**电子工作室、工作间的道具**（示波器、工具）和**柏树、棕榈**这类配景树。
- **不要用 Megaplants**（Nanite 植被，VR forward 下不合适）。

**说明：** Fab 的价格和许可是在浏览器里动态加载的，WebFetch 抓不到，所以下表很多价格只能写"未显示"。没有标"免费"的条目，请在浏览器里核对。Fab 的搜索页和 /i/ 接口被 robots 禁止抓取。

## 1. 树木
| 资产 / 卖家 | 价格 | UE 版本 | LOD / Nanite / 风 | 备注 |
|---|---|---|---|---|
| [Olive trees Collection](https://www.fab.com/listings/a2c1277e-0ecd-4376-a44a-507aa3dfd147) / gold3dlab | 未显示 | UE5 文件需向卖家索取；格式为 3ds Max/FBX | 1 万到 100 万面，未写 LOD 和风 | 唯一找到的橄榄树，有 45 个模型。面数偏高，VR 用要自己减面 |
| [Cypress Pack (Cupressus Pyramidalis)](https://www.fab.com/listings/8379d28f-4f00-43e1-901d-4bf55eb91c65) / Open World Development | 未显示 | 未列 | 有 Pivot Painter 动画和 FS Impostor | 地中海意大利柏木，适合 VR |
| [Foliage VOL.21 Cypress (Low Poly)](https://www.fab.com/listings/fb78f3b5-554f-4ce3-b610-0036250e44d8) / Dekogon | 未显示 | 写"UE5.0+ 支持 Lumen" | 低面数，风未写 | 11 个网格，4K 贴图 |
| [Palms Pack 02 (Phoenix canariensis)](https://www.fab.com/listings/cb98e62c-3d83-4c2a-9452-c594d4b18e9c) / Open World Development | 描述里写 "Free personal price until November 2026" | 未列 | Pivot Painter 2.0 | 加那利海枣，还附带草、石头和植物 |
| [STF3d Mediterranean 3D-Scanned Palm Tree Pack](https://www.fab.com/listings/16f24d9b-8a27-4604-8b46-e97b8ef21ec4) / STF3d | 未显示 | 未列 | 多级 LOD + Impostor，带风 shader | 38 棵树 |

- **无花果：** 只有 [Fig Tree](https://www.fab.com/listings/c6defe03-516d-4f63-a062-808d5d105b68)（Polygonal Miniatures），只有 fbx，价格未显示，没写 LOD 和风。
- **柠檬盆栽：** 没找到合适的。
- **官方免费 Megascans 树：** 免费的 [European Beech](https://www.fab.com/listings/d11cc01d-9422-41b7-950f-416c9ce79caf) 有独立 LOD，提供简单风和 Pivot Painter 两种风。不过是欧洲落叶树，不是地中海树种。
- **不要用 Megaplants：** [Megaplants: European Beech](https://www.fab.com/listings/cefe5722-9c31-4aa2-9ee2-e5426610d5e6) 虽然免费，但走 Nanite Foliage（实验功能）加 Dynamic Wind，不适合 VR 前向渲染。
- **地中海生物群系包：** 没找到官方的 Megascans 地中海包。

## 2. 灌木和地被
| 资产 / 卖家 | 价格 | LOD / 风 | 备注 |
|---|---|---|---|
| [Mediterranean Vegetation: Plant Pack I](https://www.fab.com/listings/41b3889d-1a98-41e1-850e-c8b417840da0) / Project Nature | 免费 | shader 风和交互，未写 LOD | 21 个网格，含龙舌兰和扫描地面材质。原 UE 商城版标注 UE4.19+ |
| [Mediterranean Vegetation: Plant Pack II](https://www.fab.com/listings/757b4a6b-a933-4da4-b712-6870b72badd6) / Project Nature | 免费 | 同上 | 21 个网格，含仙人掌（Opuntia） |
| [Rosmarinus officinalis - Rosemary](https://www.fab.com/listings/85c90db4-02de-4c13-8aae-600eeefe2961) / 3DTree | 未显示 | 未写 | 只有 3ds Max/fbx/glb |
| [Grass](https://www.fab.com/listings/f7aae95d-da2a-4db1-b8dc-71742913f262) / Quixel Megascans | 未显示 | 未写 | FBX/glTF |
| [Mediterranean Forest Scanned](https://www.fab.com/listings/f11cfc9c-9e01-415d-8ac3-d283e18342e2) / StudioD3D | 未显示 | 未写 | 32 棵树、50 种植物，要求 UE5.1 |

- **薰衣草：** Megascans 的 [Lavender](https://www.fab.com/listings/a0afc544-efba-4aca-9151-28fd21383c33) 只是贴图集，不是 3D 模型。
- **三角梅：** Fab 上没搜到。

## 3. 材质（以下都是 Quixel Megascans，价格都未显示）
| 用途 | 资产 | 规格 |
|---|---|---|
| 白灰泥墙 | [Plaster Wall](https://www.fab.com/listings/c8abaad6-05d4-4351-b537-7318df677968)、[Stucco Wall](https://www.fab.com/listings/0e6cc564-e072-4289-9d35-41e650a089ac) | 2×2 m，4096 px/m |
| 毛石墙 | [Stone Wall](https://www.fab.com/listings/67719de1-9ad2-416c-92a2-84722e50a795) | 2.7 m |
| 石板铺地 | [Stone Pavement](https://www.fab.com/listings/e03d170f-98f8-4e88-9eb7-63909411375d) | 2×2 m |
| 木甲板 | [Wood Plank](https://www.fab.com/listings/9dcd9635-47bd-4e61-a027-6b603db487d3) | 8192 px/m |
| 碎石 | [Gravel Ground](https://www.fab.com/listings/d874612e-da71-42e4-89c9-5de924b7726f) | 2×2 m |
| 陶土砖 | [Terracotta Tiles Pack](https://www.fab.com/listings/5de71a54-88da-4d67-b139-f287e815b73d) | 卖家 STW_Shop，不是 Megascans |

## 4. 道具（价格都未显示）
- 咖啡机：[Coffee Machines set](https://www.fab.com/listings/47a98ee1-a9da-40fc-9b29-e13eb822e14f)（Kobra Game Studios）和 [CLA - Coffee Maker](https://www.fab.com/listings/6eca2dbb-c946-468b-84ac-d75ffc39b7aa)（Dekogon，标注 "UE4 Optimized"）。
- 示波器：[Oscilloscope Game Ready Low Poly](https://www.fab.com/listings/8585013f-b1c0-4958-b67a-fab6d7e760c4)（HardSurface Lab，格式为 Blender/FBX）。
- 工作台和工具：[Workbench Tools Props Pack](https://www.fab.com/listings/f9b8863a-86df-490f-a76f-0249599e0f63)（EVOLVE Studio）。

## 许可
- 每个页面的 "License terms" 栏都是空的，所以单个资产用的是哪种许可都无法确认。按 [80.lv](https://80.lv/articles/megascans-no-longer-free-after-2024/) 的报道，Megascans 在 Fab 上用 Standard License。2025 年起 Megascans 不再免费，2024 年底前领取的资产可以永久保留。
- **Standard License**（来源：[Fab 许可摘要](https://www.fab.com/eula)）：
  - 可以商用或私用，可以修改，可以把资产放进项目里商业发行。
  - 不限于 Unreal，任何兼容工具都能用。
  - 不需要署名。
  - 不能单独转售资产，也不能单独免费再分发。
- **Personal 和 Professional 两档**（来源：[Fab 文档](https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab)）：
  - 两档权利完全相同，只按购买者近 12 个月的收入区分：不超过 10 万美元选 Personal，超过选 Professional。
  - 买了之后收入超过门槛也不用升级。
- **CC-BY：** 免费，但必须署名。
- **对你的影响：** 用这些资产做成 VR 程序拿去卖是可以的，但不能把原始模型文件单独打包出售。

## 推荐的起步组合
1. 灌木和地被用 Project Nature 两个免费地中海包（含龙舌兰、仙人掌，带 shader 风）。
2. 棕榈趁 2026 年 11 月前领 Palms Pack 02（Personal 档免费），柏木用 Open World Development 的 Cypress Pack。
3. 橄榄树只有 gold3dlab 这一套，面数很高，需要减面并自己做叶片卡。备选方案是用免费的 European Beech（有 LOD 和 Pivot Painter 风）改造成形状类似的树。
4. 材质优先检查 2024 年领过的 Megascans 库，里面可能已经有 Plaster、Stucco、Stone Wall、Gravel、Wood Plank。
5. 道具放到最后，在浏览器里比较价格再买。所有植物都不要用 Nanite-only 的 Megaplants。

Sources:
- https://www.fab.com/eula
- https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab
- https://80.lv/articles/megascans-no-longer-free-after-2024/
- https://www.cgchannel.com/?p=113929
- 上文表格中的各个 fab.com/listings 链接