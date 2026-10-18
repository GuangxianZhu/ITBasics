# 硬装替换：免费 Fab 素材候选（2026-10-18）

> 条件：只用免费；只选 **UE 原生格式**（材质现成，不用像 FBX 那样修材质，见 README 坑 16）。
> 来源：Fab 搜索接口（`is_free=1`），下表全部起价 0。"免费"里有一部分是 Personal 档 0 元（个人使用免费）。
> ⚠️ 面数 / LOD / Nanite 页面上大多没写，进工程后用清单脚本实测再决定用哪些（VR forward 下不用 Nanite-only 的）。

## 推荐核心组合（7 个包）

| 包 | 卖家 | 用在哪 | 说明 |
|---|---|---|---|
| [ArchViz Interior](https://www.fab.com/listings/62e0fe0f-3fd7-4d40-993a-cae13e8199f4) | Epic Games 官方 | 厨房（带岛台）、客厅细节 | 照片级公寓样例；原本是光追演示，面数可能偏高，挑件用 |
| [50+ Interior Props & Furniture Starter Kit (UE5)](https://www.fab.com/listings/3230e8b4-a63a-44c6-8d8d-5ea3630c5627) | mVision | 厨房、**浴室（马桶、洗手台、浴缸）** | 真实建筑尺度、统一 PBR；还没有评价 |
| [Modern House Pack Vol.1](https://www.fab.com/listings/47ebf30c-a2a8-45f8-b282-7c5f424ced4f) | MeikWModels | 橱柜、家电、浴室补充 | 84 个网格 |
| [Apartment Tech Props](https://www.fab.com/listings/1d9edbd4-9869-4f4b-9242-8fcfec52c43d) | Dekogon（4.8 分 / 65 评） | **电子工作室**：显示器、电脑、键盘、小家电 | 139 个网格，Matrix Awakens 同款道具，AAA 品质 |
| [ElectronicProps_Vol1](https://www.fab.com/listings/bb893120-8334-4019-b728-7492e4ef5a9d) | Defect | 电子工作室：仪器、电源、焊台类 | 11 个写实道具 |
| [Construction Site VOL.2 – Tools, Parts, Machine Props](https://www.fab.com/listings/079a0cd7-72e5-40d3-bc91-2ffff6bf1782) | Dekogon（4.81 / 42） | **车库工作间**：工具、工具柜、机器 | 52 个网格 |
| [Office Pack Vol.1](https://www.fab.com/listings/ce136033-3265-46d3-ac4d-fdbd5c9d0462) | MeikWModels | 写代码桌、办公椅、白板 | 47 个网格 |

## 备选

| 包 | 用途 |
|---|---|
| [Free Furniture Pack](https://www.fab.com/listings/baece383-bc75-4de8-971d-25110a169a36)（Next Level 3D，4.74 / 188 评） | 37 件，部分抽屉/柜门能开；床、马桶等 |
| [Modern Japanese Furniture Pack](https://www.fab.com/listings/203d7d9c-b883-49c2-b646-6e76f4b221fa)（Nimikko） | 76 件原木家具，风格和白墙院落搭；客房床、柜子 |
| [Modern Luxury Bed 1](https://www.fab.com/listings/bb7fe4c1-1882-4c52-8db0-dc09a0e8302c) | 客房床 |
| [Home Interior](https://www.fab.com/listings/8791677b-0186-49d0-9847-785bc934d33a) | 厨房 / 餐厅 / 客厅一整套 |
| [Wabi Sabi Boutique Guesthouse Interior](https://www.fab.com/listings/b63d0b74-a177-4768-8364-719764b1d788) | 弧形灰泥墙、原木、藤编，风格最接近基克拉泽斯院落；没有评价 |
| [Garage](https://www.fab.com/listings/b225b181-1eae-4df5-ad7c-4d49eeb7a6e8)、[Warehouse & Storage 免费样品](https://www.fab.com/listings/683de298-9ce5-4d85-b8bd-dbdf47f83304) | 车库补充、货架 |
| [Coffee Shop Environment](https://www.fab.com/listings/a0c7819e-a61d-4a19-8d3b-f0f5e584e6e0)（Leartes，4.84 / 31） | 咖啡机、吧台类小家电 |

## 要替换的硬装（c2_build.py 里的方块）→ 对应

| 区域 | 方块 | 候选来源 |
|---|---|---|
| 厨房 | Island、BackCounter（+ 补水槽、灶台、冰箱） | ArchViz / 50+ Kit / Modern House |
| 客房 | GuestBed、Vanity | Modern Japanese / Luxury Bed / 50+ Kit |
| 浴室 | WC、Tub、ShowerHead | 50+ Kit / Modern House / Free Furniture |
| 地下室 | WineRack、Dehumidifier | Modern House / Apartment Tech（没有就保留方块换材质） |
| 车库 | Workbench、Vise、Pegboard、DrillPress、ToolCabinet、Shelf | Construction Site VOL.2 / Warehouse 样品 / Garage |
| 电子工作室 | ESDBench、BenchPegboard、CodeDesk、Monitor、ComponentDrawers、Printer3D、BenchMonitor、Keyboard、Breadboard、BenchLamp、OfficeChair、Whiteboard | Apartment Tech / ElectronicProps / Office Pack |
| 不换 | 户外厨房、石凳、水渠、石水槽、车身等建筑/景观体块 | — |
