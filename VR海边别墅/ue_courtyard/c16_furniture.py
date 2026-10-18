# -*- coding: utf-8 -*-
"""第 16 步: 硬装家具 = 免费 Fab 网格 (2026-10-19 替换 c2_build.py 里的方块, 那边 FAB_FURN = True 后不再生成)。
可重复运行 (先删掉上次放的, 标签 CourtFurn)。c2_build.py 重跑时会在最后自动调用本脚本。

摆放方法 (不用猜网格枢轴在哪):
  1. 按 "网格正面朝 UE 哪个轴" + "希望正面朝平面图哪个方向" 算 yaw
  2. 生成后读 Actor 包围盒, 平移到: 包围盒中心 = 平面图 (cx, cy), 底面 = z (米) 或 某件家具的顶面 (on=标签)
网格正面方向是 c15_lineup.py 四面近拍确认的 (方向名 = 相机在物体哪一侧能看到正面)。
小件 (最长边 < 0.6 m) 打 CourtyardMovable 标签 -> c9_bake.py 设为 Movable, 不占光照贴图。
50+ 资源包有 18 个网格的材质槽是空的 (导出时丢了引用, 显示灰格子), 按槽名补上包里自带的材质实例。"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
LOG = []
TAG = "CourtFurn"
FL, GR, BF = 0.15, 0.05, -2.85

P50 = "/Game/50+FreeAssetPack/Geometries/"
MH = "/Game/Modern_House_V1/Mesh/"
OF = "/Game/Office_Pack_Vol_1/Models/"
DK = "/Game/Deko_MatrixDemo/Apartment/Meshes/"
CS = "/Game/Construction_VOL2/Meshes/"

AXIS = {"+X": 0, "+Y": 90, "-X": 180, "-Y": 270}          # 网格正面朝 UE 的哪个轴
FACE = {"E": 0, "S": 90, "W": 180, "N": 270}              # 平面图方向 -> UE yaw (平面图北 = UE -Y)

# 空材质槽 -> 50+ 包里的材质实例
MP = "/Game/50+FreeAssetPack/Materials/"
SLOT_FIX = {
    "Worktop": "MI_PolishedOak", "Furniture": "MI_CarpentryB5", "Porcelain": "MI_Ceramic1",
    "Satin_Chrome": "MI_SteelGrey", "Plastic": "MI_BlackPlastic", "Trim": "MI_SteelGrey",
    "SteelGrilles": "MI_SteelBlack1", "CookerBody": "MI_SteelWhite", "Burners": "MI_SteelBlack1",
    "BurnersTop": "MI_SteelBlack1", "Handle": "MI_SteelGrey", "Display": "MI_CookerDisplay",
    "GlassFront": "MI_SteelBlack1", "Glass": "MI_Glass_Clean", "Cherry_Polished": "MI_CherryPolished",
    "Satin_Brass": "MI_Brass_1K", "Oak2": "MI_PolishedOak1", "Carpentry": "MI_CarpentryA2",
    "Carpentry2": "MI_CarpentryB3", "Carpentry_001": "MI_CarpentryA1_Polished",
    "Satin_Yellow_Gold_001": "MI_Brass_1K", "Undefined": "MI_SteelGrey", "WorldGridMaterial": "MI_Duvet1",
    "Leather": "MI_LeatherB", "Sofa1": "MI_ChairFabric", "Material_84": "MI_SteelBlack1",
}

# 标签, 区域, 网格, 网格正面, 朝向, cx, cy, 底面 z (数字) 或 "on:<标签>", 缩放 (网格本地 xyz)
ITEMS = [
    # ---- 厨房靠墙一排 (南墙 y=10.75 前, x21..26.2, 面朝北): 冰箱 | 地柜 | 水槽柜 | 地柜 | 灶台 | 地柜
    ("K_Fridge", "Kitchen", P50 + "SM_Fridge", "-X", "N", 21.30, 11.065, FL),
    ("K_Unit1", "Kitchen", P50 + "SM_OldUnit1", "-Y", "N", 22.09, 11.07, FL),
    ("K_Sink", "Kitchen", P50 + "SM_OldSinkUnit", "-Y", "N", 23.03, 11.07, FL),
    ("K_Unit2", "Kitchen", P50 + "SM_OldUnit1", "-Y", "N", 23.97, 11.07, FL),
    ("K_Cooker", "Kitchen", P50 + "SM_Cooker", "-X", "N", 24.84, 11.07, FL),
    ("K_Unit3", "Kitchen", P50 + "SM_OldUnit1", "-Y", "N", 25.71, 11.07, FL),
    ("K_Hood", "Kitchen", MH + "SM_Extractor__Hood", "+X", "N", 24.84, 11.005, FL + 1.55),
    # 岛台: 三个柜子门朝南 (做饭那侧), 北半边空着给吧凳放腿; 高度拉到 0.9 m 顶住保留的大理石台面
    ("K_Island1", "Kitchen", P50 + "SM_Cupboard1", "-Y", "S", 19.6, 12.53, FL, (1, 1, 1.084)),
    ("K_Island2", "Kitchen", P50 + "SM_Cupboard1", "-Y", "S", 20.8, 12.53, FL, (1, 1, 1.084)),
    ("K_Island3", "Kitchen", P50 + "SM_Cupboard1", "-Y", "S", 22.0, 12.53, FL, (1, 1, 1.084)),
    # ---- 次卧: 整张床 (带被子枕头), 床头 (网格 -X 端) 靠南墙, 房间居中。原尺寸 2.42 x 2.83 m 太大:
    #      床尾/东侧只剩 0.9 m, NavMesh 两边各腐蚀 0.35 m 后没了 (瞬移不过去) -> 整体缩到 0.9 (还是 2.2 m 宽的大床)
    ("B_Bed", "GuestRoom", MH + "SM_Bed", "-X", "S", 11.525, 4.035, FL, (0.9, 0.9, 0.9)),
    # ---- 卫浴: 洗手台 (水龙头在网格 +X 侧 -> 正面 -X) + 马桶, 都靠南墙面朝北
    ("W_Vanity", "Bath", MH + "SM_Cabinet_11", "-X", "N", 15.05, 3.06, FL),
    ("W_WC", "Bath", P50 + "SM_Toilet1", "-Y", "N", 16.45, 3.04, FL),
    # ---- 地下室: 东墙一排 5 个木书架当酒架 / 储物架
    ("J_Shelf1", "Basement", P50 + "SM_Shelving1", "-X", "W", 27.04, 3.6, BF),
    ("J_Shelf2", "Basement", P50 + "SM_Shelving1", "-X", "W", 27.04, 4.8, BF),
    ("J_Shelf3", "Basement", P50 + "SM_Shelving1", "-X", "W", 27.04, 6.0, BF),
    ("J_Shelf4", "Basement", P50 + "SM_Shelving1", "-X", "W", 27.04, 7.2, BF),
    ("J_Shelf5", "Basement", P50 + "SM_Shelving1", "-X", "W", 27.04, 8.4, BF),
    ("J_Bucket1", "Basement", CS + "SM_PaintBucket_01", "+X", "E", 17.5, 3.3, BF),
    ("J_Bucket2", "Basement", CS + "SM_PaintBucket_02", "+X", "E", 17.98, 3.3, BF),
    ("J_Canister", "Basement", CS + "SM_Canister", "+X", "E", 17.6, 3.8, BF),
    # ---- 工作间 (车库东头): 北墙两张工作台 (北墙门 x31..32 让开), 东墙金属层架, 南墙矮柜 + 梯子, 西墙书架
    ("I_Bench1", "Workshop", CS + "SM_PlywoodTable_01a", "+X", "E", 28.425, 6.14, GR),
    ("I_Bench2", "Workshop", CS + "SM_PlywoodTable_01a", "+X", "E", 30.035, 6.14, GR),
    ("I_Toolbox", "Workshop", DK + "SM_Toolbox_Prestaged_A01_N1", "+X", "E", 28.0, 6.2, "on:I_Bench1"),
    ("I_Drill", "Workshop", CS + "SM_ElectricDrill_01a", "+X", "E", 30.6, 6.0, "on:I_Bench2"),
    ("I_Rack", "Workshop", OF + "SM_Cabinet_2", "-X", "W", 32.475, 4.0, GR),
    ("I_Cabinet", "Workshop", MH + "SM_Cabinet_5", "+Y", "N", 29.95, 2.06, GR),
    ("I_Ladder", "Workshop", CS + "SM_Ladder_01a", "+X", "E", 28.2, 1.95, GR),
    ("I_Canister", "Workshop", CS + "SM_Canister", "+X", "E", 28.2, 2.3, GR),
    ("I_Shelf", "Workshop", P50 + "SM_Shelving1", "-X", "E", 27.76, 4.7, GR),
    ("I_Gas", "Workshop", CS + "SM_TallGasCanister_01", "+X", "E", 32.45, 2.15, GR),
    ("I_Spool", "Workshop", CS + "SM_Spool_01a", "+X", "E", 31.6, 2.3, GR),
    # ---- 电子工作室: 东墙两张 3 m 长桌 (进深压到 0.75 m), 北窗下写代码的桌子, 南墙金属层架 + 打印机小桌
    ("S_Bench1", "Studio", MH + "SM_Table_1", "+X", "S", 36.865, 12.7, FL, (1, 0.75, 1)),
    ("S_Bench2", "Studio", MH + "SM_Table_1", "+X", "S", 36.865, 15.7, FL, (1, 0.75, 1)),
    ("S_BenchMonitor", "Studio", OF + "SM_Monitor_1", "-Y", "W", 37.05, 15.2, "on:S_Bench2"),
    ("S_Keyboard", "Studio", DK + "SM_ComputerKeyboard_A01_N1", "+Y", "W", 36.7, 15.2, "on:S_Bench2"),
    ("S_Lamp", "Studio", DK + "SM_DeskLamp_A01_N1", "-Y", "W", 37.05, 16.8, "on:S_Bench2"),
    ("S_Toolbox", "Studio", DK + "SM_Toolbox_Prestaged_B01_N1", "+X", "S", 37.0, 11.7, "on:S_Bench1"),
    ("S_Desk", "Studio", MH + "SM_Table_3", "+X", "S", 34.9, 17.39, FL, (0.7, 1, 1)),
    ("S_Monitor1", "Studio", OF + "SM_Monitor_1", "-Y", "S", 34.4, 17.56, "on:S_Desk"),
    ("S_Monitor2", "Studio", OF + "SM_Monitor_1", "-Y", "S", 35.4, 17.56, "on:S_Desk"),
    ("S_Chair", "Studio", OF + "SM_Chair_1", "-Y", "N", 34.9, 16.5, FL),
    ("S_BenchChair", "Studio", DK + "SM_DeskChair_A01_N1", "+Y", "E", 36.05, 13.0, FL),
    ("S_Rack", "Studio", OF + "SM_Cabinet_2", "-X", "N", 34.27, 11.03, FL),
    ("S_PrinterTable", "Studio", DK + "SM_Desk_B01_N1", "+X", "E", 35.825, 11.07, FL),
    ("S_Printer", "Studio", DK + "SM_ComputerPrinter_A01_N1", "-Y", "N", 35.8, 11.05, "on:S_PrinterTable"),
]


def plan_box(a):
    o, e = a.get_actor_bounds(False)
    return (round((o.x - e.x) / 100, 2), round((o.x + e.x) / 100, 2), round(-(o.y + e.y) / 100, 2),
            round(-(o.y - e.y) / 100, 2), round((o.z - e.z) / 100, 2), round((o.z + e.z) / 100, 2))


def fix_mesh(mesh, big):
    """Nanite 关掉 (VR 前向渲染里不稳); 大件用复杂碰撞当简单碰撞 (导航和放东西都按真实形状)。"""
    changed = False
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", ns)
        changed = True
    if big:
        bs = mesh.get_editor_property("body_setup")
        if bs and bs.get_editor_property("collision_trace_flag") != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            changed = True
    if changed:
        EAL.save_loaded_asset(mesh)
    return changed


def main():
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
    placed = {}
    fixed = set()
    for it in ITEMS:
        label, area, path, front, face, cx, cy, z = it[:8]
        scale = it[8] if len(it) > 8 else (1, 1, 1)
        mesh = unreal.load_asset(path)
        if mesh is None:
            LOG.append("MISSING " + path)
            continue
        b = mesh.get_bounding_box()
        size = max(b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z) / 100.0
        big = size >= 0.6
        if path not in fixed:
            if fix_mesh(mesh, big):
                LOG.append("  mesh fixed (nanite off / complex collision): " + mesh.get_name())
            fixed.add(path)
        yaw = (FACE[face] - AXIS[front]) % 360
        a = EAS.spawn_actor_from_object(mesh, unreal.Vector(cx * 100, -cy * 100, 0), unreal.Rotator(0, 0, yaw))
        a.set_actor_scale3d(unreal.Vector(*scale))
        smc = a.static_mesh_component
        for i, sm in enumerate(mesh.static_materials):
            mi = sm.material_interface
            if mi is None or "WorldGrid" in mi.get_path_name():
                k = SLOT_FIX.get(str(sm.material_slot_name))
                if k:
                    smc.set_material(i, unreal.load_asset(MP + k))
        if isinstance(z, str):
            o2, e2 = placed[z[3:]].get_actor_bounds(False)
            zc = o2.z + e2.z
        else:
            zc = z * 100
        o, e = a.get_actor_bounds(False)
        loc = a.get_actor_location()
        a.set_actor_location(unreal.Vector(loc.x + cx * 100 - o.x, loc.y - cy * 100 - o.y, loc.z + zc - (o.z - e.z)), False, False)
        tags = ["Courtyard", TAG] + ([] if big else ["CourtyardMovable"])
        a.set_editor_property("tags", [unreal.Name(t) for t in tags])
        smc.set_mobility(unreal.ComponentMobility.STATIC if big else unreal.ComponentMobility.MOVABLE)
        a.set_actor_label("FF_" + label)
        a.set_folder_path("Courtyard/Furniture/" + area)
        placed[label] = a
        LOG.append("%-15s yaw %3d  x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f  %s" % ((label, yaw) + plan_box(a) + (mesh.get_name(),)))
    LOG.append("furniture placed: %d" % len(placed))


if __name__ == "__main__":
    main()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    open(os.path.join(D, "c16_report.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    print("\n".join(LOG))
