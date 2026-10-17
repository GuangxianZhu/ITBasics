# -*- coding: utf-8 -*-
"""
VR 书房 / 工作室 —— 程序化建模脚本 (UE 5.8 Editor Python)

用法 (二选一):
  1) UE 菜单 Tools > Execute Python Script... 选这个文件
  2) Output Log 底部把 "Cmd" 切到 "Python", 输入:  exec(open(r"<本文件路径>", encoding="utf-8").read())

原理:
  - UE 的编辑器对象 (Actor / 材质 / 关卡) 都通过反射暴露给 Python, 脚本调用的是对象 API,
    不是点界面, 所以结果精确且可重复运行。
  - 所有生成的 Actor 都放在大纲 "ClaudeStudy/..." 文件夹里, 并打上 tag "ClaudeStudy"。
    重跑脚本时只删除带这个 tag 的 Actor, 不会碰模板自带的东西。
  - 单位: UE 用厘米。房间内部 500 x 400 cm, 层高 280 cm, 地面 z = 0。
  - 引擎自带的 /Engine/BasicShapes/Cube 是 100cm 立方体、轴心在中心,
    所以 "缩放 = 尺寸/100", "位置 = 盒子中心"。

依赖的假设 (失效条件):
  - BasicShapeMaterial 有名为 "Color" 的向量参数 (UE5 至今如此)。
  - 光源统一设为 Movable, 不需要烘焙光照; 若项目强制静态光照, 画面会偏暗。
"""
import math
import random

import unreal

TAG = "ClaudeStudy"
MAT_DIR = "/Game/ClaudeVR/Materials"
ROOM_X, ROOM_Y, ROOM_H = 500.0, 400.0, 280.0  # 内部尺寸 (cm)
WALL_T = 20.0

# 灯光强度 (单位: 坎德拉 cd; 天光为倍率)。
# 模板关闭了自动曝光 (r.DefaultFeature.AutoExposure=False), 曝光固定, 太阳只有 ~2 lux,
# 所以室内灯也要用"真实量级"的小数值; 第一次用 1500cd 整个画面直接过曝成白色。
FLOOR_LAMP_XY = (-228, -176)  # 灯罩直径 40cm, 离南墙 >=2cm (MCP 复查发现 -182 时灯罩穿墙 2cm)

LIGHT = {
    "ceiling": 6.0,
    "desk": 8.0,
    "floor_lamp": 3.0,
    "window_fill": 0.6,
    "sky": 1.0,
}

actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary

CUBE = unreal.load_asset("/Engine/BasicShapes/Cube")
CYL = unreal.load_asset("/Engine/BasicShapes/Cylinder")
SPHERE = unreal.load_asset("/Engine/BasicShapes/Sphere")
CONE = unreal.load_asset("/Engine/BasicShapes/Cone")
PLANE = unreal.load_asset("/Engine/BasicShapes/Plane")
BASE_MAT = unreal.load_asset("/Engine/BasicShapes/BasicShapeMaterial")

log = []


def note(msg):
    log.append(msg)
    unreal.log("[ClaudeStudy] " + msg)


# ---------------------------------------------------------------- 材质
_mat_cache = {}


def mat(name, rgb):
    """创建 (或复用) 一个以 BasicShapeMaterial 为父的材质实例, 设置 Color。"""
    if name in _mat_cache:
        return _mat_cache[name]
    path = "{}/MI_{}".format(MAT_DIR, name)
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = asset_tools.create_asset("MI_" + name, MAT_DIR, unreal.MaterialInstanceConstant,
                                      unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, BASE_MAT)
    MEL.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    EAL.save_loaded_asset(mi)
    _mat_cache[name] = mi
    return mi


PALETTE = {
    "Floor_Oak": (0.32, 0.20, 0.11),
    "Wall_Plaster": (0.78, 0.75, 0.70),
    "Ceiling_White": (0.85, 0.85, 0.83),
    "Trim_Walnut": (0.16, 0.09, 0.05),
    "Desk_Walnut": (0.22, 0.12, 0.06),
    "Metal_Black": (0.02, 0.02, 0.02),
    "Fabric_Green": (0.08, 0.20, 0.12),
    "Rug_Red": (0.35, 0.07, 0.06),
    "Shelf_Oak": (0.40, 0.26, 0.14),
    "Lamp_Brass": (0.55, 0.40, 0.12),
    "Lamp_Shade": (0.90, 0.85, 0.70),
    "Paper_White": (0.90, 0.90, 0.88),
    "Screen_Black": (0.01, 0.01, 0.015),
    "Plant_Green": (0.05, 0.25, 0.06),
    "Pot_Terracotta": (0.45, 0.18, 0.08),
    "Book_1": (0.40, 0.05, 0.05),
    "Book_2": (0.05, 0.12, 0.35),
    "Book_3": (0.06, 0.25, 0.10),
    "Book_4": (0.50, 0.40, 0.15),
    "Book_5": (0.12, 0.12, 0.12),
    "Book_6": (0.55, 0.30, 0.10),
}


# ---------------------------------------------------------------- 生成工具
def box(label, folder, center, size, material, rot=(0, 0, 0), mesh=None):
    """center/size 单位 cm; size 是 (X, Y, Z) 尺寸。"""
    mesh = mesh or CUBE
    a = actor_sub.spawn_actor_from_object(mesh, unreal.Vector(*center), unreal.Rotator(*rot))
    a.set_actor_scale3d(unreal.Vector(size[0] / 100.0, size[1] / 100.0, size[2] / 100.0))
    a.set_actor_label(label)
    a.set_folder_path("ClaudeStudy/" + folder)
    a.tags = [TAG]
    a.static_mesh_component.set_material(0, mat(material, PALETTE[material]))
    return a


def cyl(label, folder, center, diameter, height, material, rot=(0, 0, 0)):
    return box(label, folder, center, (diameter, diameter, height), material, rot, mesh=CYL)


def light(cls, label, loc, rot=(0, 0, 0)):
    a = actor_sub.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(*rot))
    a.set_actor_label(label)
    a.set_folder_path("ClaudeStudy/Lighting")
    a.tags = [TAG]
    comp = a.get_component_by_class(unreal.LightComponentBase) or a.root_component
    try:
        comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    except Exception:
        pass
    return a, comp


# ---------------------------------------------------------------- 清理旧结果
def clear_previous():
    n = 0
    for a in actor_sub.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            actor_sub.destroy_actor(a)
            n += 1
    note("removed {} previous ClaudeStudy actors".format(n))


# ---------------------------------------------------------------- 房间壳体
def build_shell():
    hx, hy = ROOM_X / 2, ROOM_Y / 2
    # 地板 / 天花
    box("Floor", "Shell", (0, 0, -5), (ROOM_X + 2 * WALL_T, ROOM_Y + 2 * WALL_T, 10), "Floor_Oak")
    box("Ceiling", "Shell", (0, 0, ROOM_H + 5), (ROOM_X + 2 * WALL_T, ROOM_Y + 2 * WALL_T, 10), "Ceiling_White")
    # 北墙 (书架那面) / 南墙 / 西墙
    box("Wall_N", "Shell", (0, hy + WALL_T / 2, ROOM_H / 2), (ROOM_X + 2 * WALL_T, WALL_T, ROOM_H), "Wall_Plaster")
    box("Wall_S", "Shell", (0, -hy - WALL_T / 2, ROOM_H / 2), (ROOM_X + 2 * WALL_T, WALL_T, ROOM_H), "Wall_Plaster")
    box("Wall_W", "Shell", (-hx - WALL_T / 2, 0, ROOM_H / 2), (WALL_T, ROOM_Y, ROOM_H), "Wall_Plaster")
    # 东墙: 中间留 160w x 110h 的窗洞 (窗台 90cm)
    wx = hx + WALL_T / 2
    win_w, sill, head = 160.0, 90.0, 200.0
    box("Wall_E_Low", "Shell", (wx, 0, sill / 2), (WALL_T, ROOM_Y, sill), "Wall_Plaster")
    box("Wall_E_High", "Shell", (wx, 0, (head + ROOM_H) / 2), (WALL_T, ROOM_Y, ROOM_H - head), "Wall_Plaster")
    side = (ROOM_Y - win_w) / 2
    for s, name in ((-1, "Wall_E_L"), (1, "Wall_E_R")):
        box(name, "Shell", (wx, s * (win_w / 2 + side / 2), (sill + head) / 2), (WALL_T, side, head - sill), "Wall_Plaster")
    # 窗框 + 十字窗棂 (不放玻璃: 不透明材质会挡住窗外)
    t = 6.0
    box("Win_Sill", "Window", (wx - 4, 0, sill + t / 2), (WALL_T + 10, win_w, t), "Trim_Walnut")
    box("Win_Head", "Window", (wx, 0, head - t / 2), (WALL_T, win_w, t), "Trim_Walnut")
    for s in (-1, 1):
        box("Win_Jamb_{}".format("L" if s < 0 else "R"), "Window", (wx, s * (win_w / 2 - t / 2), (sill + head) / 2),
            (WALL_T, t, head - sill), "Trim_Walnut")
    box("Win_Mullion_V", "Window", (wx, 0, (sill + head) / 2), (4, 4, head - sill), "Trim_Walnut")
    box("Win_Mullion_H", "Window", (wx, 0, (sill + head) / 2), (4, win_w, 4), "Trim_Walnut")
    # 踢脚线
    for name, c, s in (("Base_N", (0, hy - 1, 6), (ROOM_X, 2, 12)), ("Base_S", (0, -hy + 1, 6), (ROOM_X, 2, 12)),
                       ("Base_W", (-hx + 1, 0, 6), (2, ROOM_Y, 12))):
        box(name, "Shell", c, s, "Trim_Walnut")
    note("shell: room {}x{}x{} cm, window 160x110 on east wall".format(ROOM_X, ROOM_Y, ROOM_H))


# ---------------------------------------------------------------- 家具
def build_desk(origin=(170, 0)):
    """书桌靠窗, 人面朝 +X 坐。桌面 140x70, 高 75 (人体工学标准)。"""
    ox, oy = origin
    W, D, H, T = 70.0, 140.0, 75.0, 4.0  # X 方向是进深
    box("Desk_Top", "Furniture/Desk", (ox, oy, H - T / 2), (W, D, T), "Desk_Walnut")
    for i, (dx, dy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        box("Desk_Leg_{}".format(i), "Furniture/Desk",
            (ox + dx * (W / 2 - 4), oy + dy * (D / 2 - 4), (H - T) / 2), (5, 5, H - T), "Metal_Black")
    # 抽屉柜
    box("Desk_Drawer", "Furniture/Desk", (ox, oy - D / 2 + 22, H - T - 6), (W - 6, 40, 12), "Desk_Walnut")
    # 显示器 + 键盘 + 纸 + 杯子
    box("Monitor_Stand", "Furniture/Desk", (ox + 20, oy + 10, H + 10), (8, 20, 20), "Metal_Black")
    box("Monitor", "Furniture/Desk", (ox + 18, oy + 10, H + 38), (3, 62, 36), "Screen_Black")
    box("Keyboard", "Furniture/Desk", (ox - 12, oy + 10, H + 1), (14, 44, 2), "Metal_Black")
    box("Paper", "Furniture/Desk", (ox - 10, oy - 35, H + 0.3), (30, 21, 0.6), "Paper_White", rot=(0, 0, 12))
    cyl("Mug", "Furniture/Desk", (ox - 15, oy + 50, H + 5), 8, 10, "Lamp_Shade")
    note("desk at x={}, top height {} cm".format(ox, H))
    return ox, oy, H


def build_chair(origin=(95, 10)):
    ox, oy = origin
    S = 46.0
    box("Chair_Seat", "Furniture/Chair", (ox, oy, 46), (S, S, 6), "Fabric_Green")
    box("Chair_Back", "Furniture/Chair", (ox - S / 2 + 3, oy, 46 + 25), (6, S, 44), "Fabric_Green", rot=(0, -8, 0))
    cyl("Chair_Post", "Furniture/Chair", (ox, oy, 22), 6, 40, "Metal_Black")
    for i in range(5):
        ang = math.radians(72 * i)
        box("Chair_Foot_{}".format(i), "Furniture/Chair",
            (ox + 15 * math.cos(ang), oy + 15 * math.sin(ang), 3), (30, 4, 4), "Metal_Black", rot=(0, 0, 72 * i))


def build_bookshelf(origin=(-60, 182)):
    """靠北墙, 宽 160, 深 32, 高 195, 5 层。书本随机颜色/高度 (固定种子 → 可复现)。
    高度 195: 站立用户 (身高 ~170) 伸手能够到顶层 —— MCP 检查第一版 210cm 报了 WARN。"""
    ox, oy = origin
    W, D, H, T = 160.0, 32.0, 195.0, 3.0
    f = "Furniture/Bookshelf"
    for s in (-1, 1):
        box("Shelf_Side_{}".format("L" if s < 0 else "R"), f, (ox + s * (W / 2 - T / 2), oy, H / 2), (T, D, H), "Shelf_Oak")
    box("Shelf_Back", f, (ox, oy + D / 2 - 1, H / 2), (W, 2, H), "Shelf_Oak")
    levels = [8, 46, 84, 122, 160, H - T / 2]
    for i, z in enumerate(levels):
        box("Shelf_Board_{}".format(i), f, (ox, oy, z), (W - 2 * T, D, T), "Shelf_Oak")
    rnd = random.Random(42)
    books = 0
    for li in range(len(levels) - 1):
        z0 = levels[li] + T / 2
        x = ox - W / 2 + T + 2
        while True:
            w = rnd.uniform(2.5, 5.5)
            if x + w > ox + W / 2 - T - 2:
                break
            if rnd.random() < 0.08:  # 偶尔留空隙
                x += rnd.uniform(6, 14)
                continue
            gap = levels[li + 1] - levels[li] - T - 2  # 书不能顶穿上一层隔板 (第一版顶层书穿模)
            h = min(rnd.uniform(22, 34), gap)
            d = rnd.uniform(17, 24)
            tilt = rnd.uniform(-6, 0) if rnd.random() < 0.1 else 0
            box("Book_{:03d}".format(books), f + "/Books", (x + w / 2, oy + D / 2 - 3 - d / 2, z0 + h / 2),
                (w, d, h), "Book_{}".format(rnd.randint(1, 6)), rot=(tilt, 0, 0))
            x += w + 0.3
            books += 1
    note("bookshelf with {} books".format(books))


def build_extras():
    # 地毯
    box("Rug", "Furniture/Decor", (60, 0, 0.6), (240, 170, 1.2), "Rug_Red")
    # 落地灯 (西南角, 阅读角)
    # (第一版落地灯放在 (-200,-150), MCP 检查发现灯杆插进了扶手椅 -> 挪到墙角)
    lx, ly = FLOOR_LAMP_XY
    cyl("FloorLamp_Base", "Furniture/Decor", (lx, ly, 2), 30, 4, "Lamp_Brass")
    cyl("FloorLamp_Pole", "Furniture/Decor", (lx, ly, 80), 3, 156, "Lamp_Brass")
    box("FloorLamp_Shade", "Furniture/Decor", (lx, ly, 160), (40, 40, 30), "Lamp_Shade", mesh=CONE)
    # 阅读椅 (简化的单人沙发)
    f = "Furniture/Armchair"
    box("Armchair_Seat", f, (-160, -110, 22), (75, 75, 44), "Fabric_Green", rot=(0, 0, 35))
    box("Armchair_Back", f, (-187, -129, 62), (20, 75, 50), "Fabric_Green", rot=(0, 0, 35))
    # 盆栽 (窗边)
    cyl("Plant_Pot", "Furniture/Decor", (215, -165, 20), 34, 40, "Pot_Terracotta")
    box("Plant_Leaves", "Furniture/Decor", (215, -165, 75), (55, 55, 70), "Plant_Green", mesh=SPHERE)
    # 墙上挂画 (西墙)
    box("Frame", "Furniture/Decor", (-ROOM_X / 2 + 2, 60, 160), (3, 90, 60), "Trim_Walnut")
    box("Canvas", "Furniture/Decor", (-ROOM_X / 2 + 4, 60, 160), (2, 80, 50), "Book_2")


# ---------------------------------------------------------------- 灯光
def build_lighting(desk):
    ox, oy, H = desk
    # 吸顶灯
    cyl("CeilingLamp", "Furniture/Decor", (0, 0, ROOM_H - 3), 50, 4, "Lamp_Shade")
    a, c = light(unreal.PointLight, "L_Ceiling", (0, 0, ROOM_H - 20))
    c.set_intensity(LIGHT["ceiling"])
    c.set_light_color(unreal.LinearColor(1.0, 0.86, 0.68, 1))
    c.set_attenuation_radius(900.0)
    # 台灯 (桌面左侧)
    lx, ly = ox + 10, oy - 55
    cyl("DeskLamp_Base", "Furniture/Desk", (lx, ly, H + 1.5), 14, 3, "Lamp_Brass")
    cyl("DeskLamp_Arm", "Furniture/Desk", (lx, ly, H + 22), 2, 40, "Lamp_Brass")
    box("DeskLamp_Shade", "Furniture/Desk", (lx - 6, ly, H + 44), (18, 18, 14), "Lamp_Shade", mesh=CONE)
    a, c = light(unreal.SpotLight, "L_DeskLamp", (lx - 6, ly, H + 40), rot=(-70, 0, 180))
    c.set_intensity(LIGHT["desk"])
    c.set_light_color(unreal.LinearColor(1.0, 0.8, 0.55, 1))
    c.set_editor_property("outer_cone_angle", 50.0)
    c.set_attenuation_radius(300.0)
    # 落地灯
    a, c = light(unreal.PointLight, "L_FloorLamp", (FLOOR_LAMP_XY[0], FLOOR_LAMP_XY[1], 150))
    c.set_intensity(LIGHT["floor_lamp"])
    c.set_light_color(unreal.LinearColor(1.0, 0.78, 0.5, 1))
    c.set_attenuation_radius(400.0)
    c.set_cast_shadows(False)  # 前向渲染: 重叠的投影可移动光源最多 4 个, 落地灯和补光不投影
    # 窗口补光 (模拟天光从窗户进来)
    a, c = light(unreal.RectLight, "L_WindowFill", (ROOM_X / 2 - 5, 0, 145), rot=(0, 180, 0))
    c.set_intensity(LIGHT["window_fill"])
    c.set_cast_shadows(False)
    c.set_light_color(unreal.LinearColor(0.75, 0.85, 1.0, 1))
    c.set_editor_property("source_width", 160.0)
    c.set_editor_property("source_height", 110.0)
    # 太阳 + 天空 (窗外); 已有的就不重复放
    have = {type(x).__name__ for x in actor_sub.get_all_level_actors()}
    if "DirectionalLight" not in have:
        a, c = light(unreal.DirectionalLight, "Sun", (0, 0, 600), rot=(0, -25, 200))
        c.set_intensity(6.0)
        try:
            c.set_editor_property("atmosphere_sun_light", True)
        except Exception:
            pass
    if "SkyAtmosphere" not in have and "BP_Sky_Sphere_C" not in {x.get_class().get_name() for x in actor_sub.get_all_level_actors()}:
        s = actor_sub.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
        s.set_actor_label("SkyAtmosphere"); s.set_folder_path("ClaudeStudy/Lighting"); s.tags = [TAG]
    if "SkyLight" not in have:
        a, c = light(unreal.SkyLight, "SkyLight", (0, 0, 400))
        pass
    # 模板自带的太阳/天光是 Stationary(需要烘焙); 改成 Movable, 不烘焙也有正确的阴影
    for x in actor_sub.get_all_level_actors():
        if isinstance(x, (unreal.DirectionalLight, unreal.SkyLight)):
            comp = x.get_component_by_class(unreal.LightComponentBase)
            try:
                comp.set_mobility(unreal.ComponentMobility.MOVABLE)
            except Exception:
                pass
            if isinstance(x, unreal.SkyLight):
                # 实时捕获需要 SkyAtmosphere/体积云/IsSky 网格; 模板用的是天空球, 改回静态捕获
                try:
                    comp.set_editor_property("real_time_capture", False)
                    comp.set_intensity(LIGHT["sky"])
                    comp.recapture_sky()
                except Exception:
                    pass
    note("lighting: ceiling point, desk spot, floor lamp, window rect fill, sun/sky")


# ---------------------------------------------------------------- 玩家 / 导航
def build_player():
    have = [x for x in actor_sub.get_all_level_actors() if isinstance(x, unreal.PlayerStart)]
    if have:
        ps = have[0]
        ps.set_actor_location(unreal.Vector(-40, -130, 92), False, False)
        ps.set_actor_rotation(unreal.Rotator(0, 0, 25), False)
        note("moved existing PlayerStart into the study")
    else:
        ps = actor_sub.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(-40, -130, 92), unreal.Rotator(0, 0, 25))
        ps.set_folder_path("ClaudeStudy"); ps.tags = [TAG]
        note("spawned PlayerStart")
    navs = [x for x in actor_sub.get_all_level_actors() if isinstance(x, unreal.NavMeshBoundsVolume)]
    if navs:
        nv = navs[0]
        nv.set_actor_location(unreal.Vector(0, 0, 100), False, False)
        b = nv.get_actor_bounds(False)[1]  # half extents (cm)
        sx = (ROOM_X / 2) / max(b.x, 1) * nv.get_actor_scale3d().x
        sy = (ROOM_Y / 2) / max(b.y, 1) * nv.get_actor_scale3d().y
        sz = 150.0 / max(b.z, 1) * nv.get_actor_scale3d().z
        nv.set_actor_scale3d(unreal.Vector(sx, sy, sz))
        note("fitted NavMeshBoundsVolume to the room (VR teleport needs a navmesh)")
    else:
        note("WARNING: no NavMeshBoundsVolume in level -> VR teleport will not work here")


def arrange_grabbables(desk):
    """模板里的可抓取小方块 (VR 手柄能拿起来) 摆到书架旁的地上, 当作积木玩具。
    (书桌上已经有键盘/台灯, 放上去会和物理碰撞互相顶开。)"""
    grabs = [x for x in actor_sub.get_all_level_actors() if x.get_class().get_name().startswith("BP_Grabbable")]
    for i, g in enumerate(grabs):
        row, col = divmod(i, 4)
        g.set_actor_location(unreal.Vector(-175 + col * 26, 110 - row * 26, 12), False, True)
        g.set_actor_rotation(unreal.Rotator(0, 0, i * 17), True)
        g.set_folder_path("ClaudeStudy/Grabbables")
    note("arranged {} grabbable cubes on the floor by the bookshelf".format(len(grabs)))


def main():
    with unreal.ScopedEditorTransaction("ClaudeStudy build"):  # 一步 Ctrl+Z 可撤销整次生成
        clear_previous()
        build_shell()
        desk = build_desk()
        build_chair()
        build_bookshelf()
        build_extras()
        build_lighting(desk)
        build_player()
        arrange_grabbables(desk)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    note("done; level saved")
    return "\n".join(log)


if __name__ == "__main__" or True:
    print(main())
