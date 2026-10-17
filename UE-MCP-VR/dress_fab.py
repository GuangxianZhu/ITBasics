# -*- coding: utf-8 -*-
"""
第 3 步: 用 Fab 素材 (OLD OFFICE Interior / Classic_Office) 做软装。

思路:
  - build_study.py 生成的程序化"粗模"里, 扶手椅/盆栽/地毯/挂画这几件用 Fab 成品替换
    (程序化的那几件会被删掉; 重跑 build_study.py 会再生成, 之后再跑本脚本即可)。
  - Fab 模型的轴心位置各不相同 (有的在底部中心, 有的在角落), 所以不用硬编码 z,
    而是"先放下 -> 读包围盒 -> 平移到让包围盒底面贴地/背面贴墙"。
  - 所有 Fab 摆件打 tag "FabDressing", 重跑时先删旧的。
用法: py "dress_fab.py"
"""
import unreal

TAG = "FabDressing"
ROOT = "/Game/Classic_Office/Meshes"
HX, HY = 250.0, 200.0  # 房间内部半宽 (cm)
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
log = []


def find_mesh(name):
    for p in EAL.list_assets(ROOT, recursive=True, include_folder=False):
        if p.split("/")[-1].split(".")[0] == name:
            return unreal.load_asset(p)
    raise RuntimeError("mesh not found: " + name)


def bounds(a):
    o, e = a.get_actor_bounds(False)
    return o, e


def place(name, xy, yaw=0.0, mode="floor", z=0.0, fit=None, label=None):
    """mode: floor (底面贴 z) / wall_w / wall_n / wall_s (背面贴墙, 中心高度 z)"""
    mesh = find_mesh(name)
    a = sub.spawn_actor_from_object(mesh, unreal.Vector(xy[0], xy[1], 0), unreal.Rotator(0, 0, yaw))
    a.set_actor_label(label or name.replace("SM_", "Fab_"))
    a.set_folder_path("ClaudeStudy/Fab")
    a.tags = [TAG]
    if fit:  # 等比缩放到占地不超过 fit=(x, y)
        o, e = bounds(a)
        k = min(fit[0] / (2 * e.x), fit[1] / (2 * e.y), 1.0e9)
        a.set_actor_scale3d(unreal.Vector(k, k, k))
    o, e = bounds(a)
    loc = a.get_actor_location()
    dx, dy, dz = 0.0, 0.0, 0.0
    if mode == "floor":
        dx, dy, dz = xy[0] - o.x, xy[1] - o.y, z - (o.z - e.z)
    elif mode == "wall_w":
        dx, dy, dz = (-HX + 1) - (o.x - e.x), xy[1] - o.y, z - o.z
    elif mode == "wall_n":
        dx, dy, dz = xy[0] - o.x, (HY - 1) - (o.y + e.y), z - o.z
    elif mode == "wall_s":
        dx, dy, dz = xy[0] - o.x, (-HY + 1) - (o.y - e.y), z - o.z
    a.set_actor_location(unreal.Vector(loc.x + dx, loc.y + dy, loc.z + dz), False, True)
    o, e = bounds(a)
    log.append("{:<22} size=({:.0f},{:.0f},{:.0f})cm  bottom z={:.0f}".format(
        a.get_actor_label(), 2 * e.x, 2 * e.y, 2 * e.z, o.z - e.z))
    return a


def add_canvas(frame):
    """Fab 的画框素材里面是空的 (白墙透出来), 补一块程序化"画布": 深蓝底 + 三条色带, 像一幅抽象风景。"""
    o, e = frame.get_actor_bounds(False)
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    base = unreal.load_asset("/Engine/BasicShapes/BasicShapeMaterial")
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mel = unreal.MaterialEditingLibrary

    def mi(name, rgb):
        path = "/Game/ClaudeVR/Materials/MI_" + name
        m = unreal.load_asset(path) if EAL.does_asset_exist(path) else tools.create_asset(
            "MI_" + name, "/Game/ClaudeVR/Materials", unreal.MaterialInstanceConstant,
            unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(m, base)
        mel.set_material_instance_vector_parameter_value(m, "Color", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
        EAL.save_loaded_asset(m)
        return m

    w, h = 2 * e.y * 0.78, 2 * e.z * 0.70  # 画框内口大约是外框的 78% x 70%
    x = -HX + 1.5
    bands = [("Canvas_Sky", (0.10, 0.18, 0.35), 0.55), ("Canvas_Hill", (0.20, 0.30, 0.12), 0.25),
             ("Canvas_Field", (0.45, 0.33, 0.12), 0.20)]
    ztop = o.z + h / 2
    for i, (name, rgb, frac) in enumerate(bands):
        hh = h * frac
        a = sub.spawn_actor_from_object(cube, unreal.Vector(x, o.y, ztop - hh / 2), unreal.Rotator(0, 0, 0))
        a.set_actor_scale3d(unreal.Vector(0.01, w / 100.0, hh / 100.0))
        a.static_mesh_component.set_material(0, mi(name, rgb))
        a.set_actor_label("Fab_Picture_Canvas_{}".format(i))
        a.set_folder_path("ClaudeStudy/Fab")
        a.tags = [TAG]
        ztop -= hh


def remove_procedural(labels):
    """删掉被 Fab 成品替换的程序化粗模 (只删带 ClaudeStudy tag 的, 重跑 build_study.py 会再生成)。"""
    for a in sub.get_all_level_actors():
        if a.get_actor_label() in labels and "ClaudeStudy" in [str(t) for t in a.tags]:
            sub.destroy_actor(a)


def main():
    with unreal.ScopedEditorTransaction("Fab dressing"):
        for a in sub.get_all_level_actors():
            if TAG in [str(t) for t in a.tags]:
                sub.destroy_actor(a)
        remove_procedural({"Armchair_Seat", "Armchair_Back", "Plant_Pot", "Plant_Leaves", "Rug", "Frame", "Canvas"})
        # 扶手椅 (阅读角, 朝向房间中央)
        place("SM_Leather_Armchair", (-165, -115), yaw=YAW["armchair"], fit=(95, 95))
        # 盆栽 (窗边东南角)
        place("SM_Ficus_02", (200, -155), fit=(100, 100))
        # 地毯 (书桌和房间中央)
        place("SM_Carpet_01", (40, 0), yaw=YAW["carpet"], fit=(280, 200), z=0.0)
        # 挂画 (西墙)
        pic = place(PICTURE, (0, 40), yaw=YAW["picture_w"], mode="wall_w", z=150)
        add_canvas(pic)
        # 落地钟 (素材是 1.2m 高的落地座钟, 不是挂钟) —— 靠北墙, 书架东边
        place("SM_Clock", (60, 0), yaw=YAW["clock_n"], mode="wall_n", z=61)
        # 地球仪 (书架东侧的地上)
        place("SM_Globe_01", (-205, 40), yaw=20, fit=(60, 60))
        # 地毯有 4cm 厚, PlayerStart 胶囊体底部 (z=0) 会和它相交 -> 编辑器显示 BADsize; 抬高 8cm
        for a in sub.get_all_level_actors():
            if isinstance(a, unreal.PlayerStart):
                p = a.get_actor_location()
                a.set_actor_location(unreal.Vector(p.x, p.y, 100), False, True)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print("\n".join(log))


# 朝向 (度): 不同素材的"正面"轴向不一致, 截图检查后在这里调
# 第一版 armchair=35 时椅面朝着南墙 (该素材"正面"是本地 -Y), 改 135 让它朝向房间中央
YAW = {"armchair": 135.0, "carpet": 0.0, "picture_w": 90.0, "clock_n": 0.0}
PICTURE = "SM_Picture_04"  # SM_Picture_02 是空画框

main()
