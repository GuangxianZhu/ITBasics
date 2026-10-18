# -*- coding: utf-8 -*-
"""
第 2 步: 在 L_Courtyard 里按 "院落布局 v2" 搭整栋别墅 (可重复运行: 先删掉上次生成的, 再重建)。

坐标: 平面图米制 (x 向东, y 向北 = 大海方向) -> UE 厘米 (100x, -100y, 100z)。
      和 L_Villa 一样 "大海 = UE 的 -Y", 所以沿用的太阳/天空角度不用改。
标高: 室内地面 / 泳池平台 FL = 0.15 m, 院子碎石 0.05 m, 场地 0; 地下室地面 -2.85 m (下 3 m, 16 级台阶)。
做法: 建筑、院墙、地面全部用引擎自带的 1m 立方体/圆柱/球缩放拼出来 (自带碰撞, VR 瞬移能落地);
      材质用 L_Villa 的三向投影母材质 (世界坐标贴图, 立方体怎么缩放纹理密度都不变);
      家具复用 L_Villa 里 AI 生成的那批 (AI_*), 只挪位置, 其余全删。
精度分档 (见画布 "VR 玩家在哪 · 建模精度分区"): 这一版先把精细区摆满, 中等区成型, 配景用大体块。
"""
import json
import math
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
TAG = "Courtyard"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
CUBE = unreal.load_asset("/Engine/BasicShapes/Cube.Cube")
CYL = unreal.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
SPH = unreal.load_asset("/Engine/BasicShapes/Sphere.Sphere")
LOG = []
COUNT = {"n": 0}

# 几何模式:
#   RECORD 是 list 时 (云端 c2x_export_geom.py 用假的 unreal 模块导入本文件) -> box/cyl/sph 只记录不生成;
#   UE 里如果有 court_geom.glb (云端导出的带倒角合并网格) -> 不再生成 1000 多个立方体, 改为导入合并网格。
RECORD = None
MERGED = os.path.exists(os.path.join(D, "court_geom.glb"))
SPAWN_ALWAYS = {"Plants"}   # 这些组仍是单独 Actor (盆、土; 植物本身由 c8_trees.py 生成)
PLANTS = []                  # [种类, x, y, z, 缩放] (平面图米制), 给 c8_trees.py 用
TREES = os.path.exists(os.path.join(D, "court_plants.glb"))


def _skip(group):
    return MERGED and group not in SPAWN_ALWAYS


FL = 0.15      # 室内 / 平台地面
GR = 0.05      # 院子碎石面
WT = 3.85      # 外墙顶 (含女儿墙)
CEIL = 3.35    # 室内天花
BF = -2.85     # 地下室地面
SW = 2.2       # 院墙高


def V(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


# ------------------------------------------------------------------ 清场
def clean():
    keep_ai = []
    actors = EAS.get_all_level_actors()
    for a in actors:
        lab = a.get_actor_label()
        if lab.startswith("AI_"):
            try:
                a.detach_from_actor(unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD)
            except Exception:
                pass
            keep_ai.append(a)
    n = 0
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("AI_"):
            continue
        tags = [str(t) for t in a.tags]
        cls = a.get_class().get_name()
        if TAG in tags or "Villa" in tags or cls in ("PointLight", "SpotLight", "RectLight") or cls == "Actor":
            EAS.destroy_actor(a)
            n += 1
    LOG.append("cleaned %d actors, kept %d AI furniture" % (n, len(keep_ai)))


# ------------------------------------------------------------------ 材质
TRI = unreal.load_asset("/Game/Villa/Materials/M_VillaTriplanar")
MATDIR = "/Game/Courtyard/Materials"


def tex(n):
    return unreal.load_asset("/Game/Villa/Textures/" + n)


def mi(name, texset, tile_m, tint=(1, 1, 1), rough=1.0, metal=0.0):
    path = MATDIR + "/MI_C_" + name
    if EAL.does_asset_exist(path):
        m = unreal.load_asset(path)
    else:
        m = TOOLS.create_asset("MI_C_" + name, MATDIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(m, TRI)
    MEL.set_material_instance_scalar_parameter_value(m, "TileCM", tile_m * 100.0)
    MEL.set_material_instance_scalar_parameter_value(m, "RoughMul", rough)
    MEL.set_material_instance_scalar_parameter_value(m, "Metallic", metal)
    MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1))
    MEL.set_material_instance_texture_parameter_value(m, "Albedo", tex(texset + "_albedo"))
    MEL.set_material_instance_texture_parameter_value(m, "Rough", tex(texset + "_rough"))
    EAL.save_loaded_asset(m)
    return m


M = {}


def build_materials():
    spec = {
        "white": ("plaster", 2.0, (1.0, 1.0, 1.0)),
        "white_in": ("plaster", 2.0, (0.97, 0.95, 0.91)),
        "stone": ("seawall", 1.1, (0.96, 0.92, 0.84)),
        "terrace": ("stone_tile", 1.2, (0.98, 0.96, 0.92)),
        "coping": ("pool_stone", 1.2, (1.0, 1.0, 1.0)),
        "pooltile": ("porcelain", 0.6, (0.55, 0.82, 0.92)),
        "wood": ("wood_floor", 2.4, (1.0, 1.0, 1.0)),
        "teak": ("wood_floor", 1.6, (0.78, 0.58, 0.4)),
        "gravel": ("concrete", 0.8, (0.98, 0.93, 0.84), 1.2),
        "earth": ("grass", 5.0, (1.0, 0.8, 0.45)),
        "grass": ("grass", 3.0, (0.85, 0.85, 0.62)),
        "concrete": ("concrete", 2.0, (1.0, 1.0, 1.0)),
        "asphalt": ("concrete", 2.0, (0.32, 0.32, 0.33)),
        "marble": ("marble", 1.2, (1.0, 1.0, 1.0)),
        "porcelain": ("porcelain", 1.6, (1.0, 1.0, 1.0)),
        "rock": ("rock", 3.0, (1.0, 1.0, 1.0)),
        "hill": ("forest", 40.0, (1.0, 1.0, 1.0)),
        "bark": ("bark", 1.0, (0.72, 0.66, 0.6)),
        "olive": ("forest", 2.5, (0.78, 0.88, 0.62)),
        "leaf": ("forest", 2.5, (0.85, 1.15, 0.6)),
        "lavender": ("fabric", 0.3, (0.6, 0.48, 0.82)),
        "bouga": ("fabric", 0.3, (0.9, 0.22, 0.55)),
        "soil": ("sand", 1.0, (0.36, 0.26, 0.18)),
        "esd": ("plaster", 1.0, (0.22, 0.5, 0.34)),
        "metal": ("concrete", 1.0, (0.62, 0.64, 0.67), 0.5, 0.8),
        "black": ("concrete", 1.0, (0.06, 0.06, 0.07), 0.6),
        "cardboard": ("fabric", 0.6, (0.78, 0.62, 0.42)),
        "red": ("plaster", 1.0, (0.62, 0.1, 0.08), 0.6),
        "car_blue": ("plaster", 1.0, (0.12, 0.22, 0.38), 0.35, 0.6),
        "car_white": ("plaster", 1.0, (0.85, 0.85, 0.83), 0.35, 0.4),
        "terracotta": ("sand", 1.0, (0.8, 0.42, 0.26)),
        "linen": ("fabric", 0.4, (0.95, 0.93, 0.88)),
        "rug": ("fabric", 0.25, (0.9, 0.82, 0.7)),
        "yellow": ("plaster", 1.0, (0.95, 0.8, 0.15)),
        "pcb": ("plaster", 0.5, (0.05, 0.35, 0.12)),
    }
    for k, v in spec.items():
        texset, tile, tint = v[0], v[1], v[2]
        rough = v[3] if len(v) > 3 else 1.0
        metal = v[4] if len(v) > 4 else 0.0
        M[k] = mi(k, texset, tile, tint, rough, metal)
        pbr = "/Game/Courtyard/PBR/MI_P_" + k           # c7_pbr.py 生成的 PBR 材质优先
        if EAL.does_asset_exist(pbr):
            M[k] = unreal.load_asset(pbr)
    M["water"] = unreal.load_asset("/Game/Villa/Materials/M_VillaPoolWater")
    M["sea"] = unreal.load_asset("/Game/Villa/Materials/M_VillaSea")
    M["glass"] = court_glass()      # 旧的 M_VillaGlass 带贴图, 合并网格是米制 UV -> 每米一格, 像一面瓷砖墙
    M["screen"] = unreal.load_asset("/Game/Villa/Materials/M_VillaDarkGlass")
    M["lamp"] = unreal.load_asset("/Game/Villa/Materials/M_VillaLamp")


def court_glass():
    """不用 UV 的透明玻璃: 半透明 + 低粗糙度, 前向渲染下用 Surface ForwardShading 才有高光反射。"""
    path = "/Game/Courtyard/Materials/M_CourtGlass"
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    m = TOOLS.create_asset("M_CourtGlass", "/Game/Courtyard/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    try:
        m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_FORWARD_SHADING)
    except Exception as e:
        LOG.append("glass lighting mode: %s" % e)
    m.set_editor_property("two_sided", True)

    def const(v, x, y):
        e = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, x, y)
        e.set_editor_property("r", v)
        return e
    col = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -400, -200)
    col.set_editor_property("constant", unreal.LinearColor(0.85, 0.93, 0.95, 1))
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(const(0.05, -400, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(const(0.8, -400, 80), "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.connect_material_property(const(0.12, -400, 160), "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


# ------------------------------------------------------------------ 生成工具
def finish(a, mat, group, collide, label):
    COUNT["n"] += 1
    a.set_editor_property("tags", [unreal.Name(TAG)])
    a.set_folder_path("Courtyard/" + group)
    if label:
        a.set_actor_label(label)
    smc = a.static_mesh_component
    if mat is not None:
        smc.set_material(0, mat)
    if not collide:
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        smc.set_editor_property("can_ever_affect_navigation", False)
    return a


def box(x0, x1, y0, y1, z0, z1, mat, group="Misc", collide=True, label=None, yaw=0.0):
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    if x1 - x0 < 1e-3 or y1 - y0 < 1e-3 or z1 - z0 < 1e-3:
        return None
    # 防 Z-fighting (闪烁): 地面层的板子 (顶面在室内地面标高附近、底面在地下) 四边各缩 1.5 cm,
    # 否则它的侧面和外墙外表面重合在同一个平面上, 两个材质抢同一批像素, VR 里一动就闪
    if -0.01 <= z1 <= FL + 0.001 and z0 < -0.05 and (x1 - x0) > 0.2 and (y1 - y0) > 0.2:
        x0, x1, y0, y1 = x0 + 0.015, x1 - 0.015, y0 + 0.015, y1 - 0.015
    if RECORD is not None:
        RECORD.append(("box", (x0, x1, y0, y1, z0, z1, yaw), mat, group, collide))
        return None
    if _skip(group):
        return None
    a = EAS.spawn_actor_from_object(CUBE, V((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), unreal.Rotator(0, 0, yaw))
    a.set_actor_scale3d(unreal.Vector(x1 - x0, y1 - y0, z1 - z0))
    return finish(a, M.get(mat) if isinstance(mat, str) else mat, group, collide, label)


def cyl(x, y, z0, z1, d, mat, group="Misc", collide=True, dy=None, pitch=0.0, roll=0.0):
    if RECORD is not None:
        RECORD.append(("cyl", (x, y, z0, z1, d, dy or d, pitch, roll), mat, group, collide))
        return None
    if _skip(group):
        return None
    a = EAS.spawn_actor_from_object(CYL, V(x, y, (z0 + z1) / 2), unreal.Rotator(roll, pitch, 0))
    a.set_actor_scale3d(unreal.Vector(d, dy or d, z1 - z0))
    return finish(a, M[mat], group, collide, None)


def sph(x, y, z, sx, sy, sz, mat, group="Plants", collide=False):
    if RECORD is not None:
        RECORD.append(("sph", (x, y, z, sx, sy, sz), mat, group, collide))
        return None
    if _skip(group):
        return None
    a = EAS.spawn_actor_from_object(SPH, V(x, y, z), unreal.Rotator(0, 0, 0))
    a.set_actor_scale3d(unreal.Vector(sx, sy, sz))
    return finish(a, M[mat], group, collide, None)


def wall(axis, a0, a1, c0, c1, z0, z1, mat, holes=(), group="Walls"):
    """axis='x': 墙沿 x 从 a0 到 a1, 厚度占 y 的 c0..c1; axis='y' 反过来。
    holes: (h0, h1, hz0, hz1, kind) kind = 'open' 空洞 / 'glass' 玻璃 / 'win' 带框玻璃窗"""
    def seg(p0, p1, q0, q1, m=mat, collide=True):
        if axis == "x":
            return box(p0, p1, c0, c1, q0, q1, m, group, collide)
        return box(c0, c1, p0, p1, q0, q1, m, group, collide)

    cur = a0
    for h0, h1, hz0, hz1, kind in sorted(holes):
        seg(cur, h0, z0, z1)
        seg(h0, h1, z0, hz0)
        seg(h0, h1, hz1, z1)
        if kind in ("glass", "win"):
            mid0, mid1 = (c0 + c1) / 2 - 0.015, (c0 + c1) / 2 + 0.015
            if axis == "x":
                box(h0, h1, mid0, mid1, hz0, hz1, "glass", group)
            else:
                box(mid0, mid1, h0, h1, hz0, hz1, "glass", group)
            # 竖梃 (每 ~1.6 m 一根) + 上下框
            n = max(1, int(round((h1 - h0) / 1.6)))
            for i in range(n + 1):
                p = h0 + (h1 - h0) * i / n
                seg(max(h0, p - 0.03), min(h1, p + 0.03), hz0, hz1, "black")
            seg(h0, h1, hz0, hz0 + 0.04, "black")
            seg(h0, h1, hz1 - 0.04, hz1, "black")
        cur = h1
    seg(cur, a1, z0, z1)


def roof(x0, x1, y0, y1):
    # 屋面板比外轮廓每边缩 2 cm, 侧面藏进墙里, 不和外墙外表面共面 (同样是防闪烁)
    box(x0 + 0.02, x1 - 0.02, y0 + 0.02, y1 - 0.02, CEIL, CEIL + 0.25, "white", "Roof")


def plight(x, y, z, cd=6.0, radius=800, color=(1.0, 0.86, 0.7), lamp=True):
    a = EAS.spawn_actor_from_class(unreal.PointLight, V(x, y, z))
    c = a.point_light_component
    c.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
    c.set_intensity(cd)
    c.set_attenuation_radius(radius)
    c.set_cast_shadows(False)
    c.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1))
    a.set_editor_property("tags", [unreal.Name(TAG)])
    a.set_folder_path("Courtyard/Lights")
    if lamp:
        box(x - 0.2, x + 0.2, y - 0.2, y + 0.2, CEIL - 0.02, CEIL, "lamp", "Lights", False) if z > 2.0 else None


# ------------------------------------------------------------------ 植物 (中等: 程序化低模)
def olive(x, y, s=1.0, z0=GR):
    PLANTS.append(["Olive", x, y, z0, s])
    if TREES:
        return
    cyl(x, y, z0, z0 + 1.5 * s, 0.32 * s, "bark", "Plants", True, pitch=6)
    cyl(x + 0.25 * s, y, z0 + 1.1 * s, z0 + 2.2 * s, 0.18 * s, "bark", "Plants", False, pitch=-18)
    sph(x, y, z0 + 2.5 * s, 3.0 * s, 2.7 * s, 1.5 * s, "olive")
    for dx, dy, dz, r in ((0.9, 0.5, 2.2, 1.6), (-0.9, -0.4, 2.3, 1.7), (0.3, -0.9, 2.8, 1.4), (-0.4, 0.9, 2.9, 1.3)):
        sph(x + dx * s, y + dy * s, z0 + dz * s, r * s, r * s, r * 0.6 * s, "olive")


def fig(x, y, s=1.0, z0=GR):
    PLANTS.append(["Fig", x, y, z0, s])
    if TREES:
        return
    cyl(x, y, z0, z0 + 1.3 * s, 0.22 * s, "bark", "Plants", True)
    sph(x, y, z0 + 1.9 * s, 2.2 * s, 2.2 * s, 1.4 * s, "leaf")
    sph(x + 0.5 * s, y - 0.3 * s, z0 + 2.3 * s, 1.3 * s, 1.3 * s, 0.9 * s, "leaf")


def lemon_pot(x, y, z0=GR):
    cyl(x, y, z0, z0 + 0.55, 0.6, "terracotta", "Plants", True)
    box(x - 0.26, x + 0.26, y - 0.26, y + 0.26, z0 + 0.5, z0 + 0.53, "soil", "Plants", False)
    PLANTS.append(["Lemon", x, y, z0 + 0.53, 1.0])
    if TREES:
        return
    cyl(x, y, z0 + 0.5, z0 + 1.2, 0.06, "bark", "Plants", False)
    sph(x, y, z0 + 1.45, 0.95, 0.95, 0.85, "leaf")
    for dx, dy, dz in ((0.3, 0.2, 1.4), (-0.25, 0.3, 1.55), (0.1, -0.35, 1.3), (-0.3, -0.15, 1.6)):
        sph(x + dx, y + dy, z0 + dz, 0.09, 0.09, 0.1, "yellow")


BUSH_KIND = {"olive": ("OliveShrub", 0.6), "lavender": ("Lavender", 0.36), "leaf": ("Rosemary", 0.36)}


def bush(x, y, z, d, mat, h=None, kind=None):
    k, ref = (kind, 0.5) if kind else BUSH_KIND.get(mat, ("OliveShrub", 0.6))
    PLANTS.append([k, x, y, z, round(d / ref, 3)])
    if TREES:
        return
    sph(x, y, z + (h or d * 0.6) / 2, d, d, h or d * 0.6, mat)


# ------------------------------------------------------------------ 场地与配景 (粗)
def build_site():
    g = "Site"
    # 地面 (地下室上方挖空, 否则会把楼梯井堵住)
    box(-150, 200, -150, 2.5, -0.3, 0.0, "earth", g, label="Ground")
    box(-150, 200, 10.0, 23, -0.3, 0.0, "earth", g)
    box(-150, 17.0, 2.5, 10.0, -0.3, 0.0, "earth", g)
    box(27.5, 200, 2.5, 10.0, -0.3, 0.0, "earth", g)
    box(-150, 200, 23, 28.5, -0.3, 0.02, "grass", g, label="SeaLawn")
    box(-150, 200, -0.3, 1.4, 0.0, 0.03, "asphalt", g, label="Road")
    box(22.5, 26.5, 1.4, 1.62, 0.0, GR, "concrete", g, label="Driveway")
    # 海岸: 草坡边缘下去是岩石, 再下去是海
    box(-150, 200, 28.5, 31, -3.2, 0.0, "rock", g, label="Cliff")
    for i in range(-14, 26):
        x = i * 6.5 + ((i * 7) % 5) * 1.3
        sx = 7 + ((i * 13) % 5) * 1.6
        sph(x, 30.6 + ((i * 3) % 4) * 0.6, -2.3 + ((i * 11) % 3) * 0.4, sx, 4 + (i % 3), 2.2 + ((i * 5) % 3) * 0.8, "rock", g, True)
    box(-2500, 2500, 30, 3000, -2.7, -2.62, "sea", g, collide=False, label="Sea")
    # 远景 (只看轮廓): 两个海岬 + 灯塔 + 远岛; 南边的山; 邻居房子
    sph(-120, 210, -8, 160, 70, 45, "rock", "Far", False)
    sph(-130, 205, 5, 120, 50, 25, "grass", "Far", False)
    sph(170, 240, -10, 180, 80, 50, "rock", "Far", False)
    sph(160, 236, 6, 140, 60, 28, "grass", "Far", False)
    cyl(150, 225, 18, 33, 3.2, "white", "Far", False)
    cyl(150, 225, 33, 35, 2.4, "lamp", "Far", False)
    sph(30, 700, -20, 500, 120, 60, "hill", "Far", False)
    for x, y, sx, sy, sz in ((-60, -110, 160, 90, 60), (40, -140, 200, 100, 80), (130, -100, 160, 90, 55), (-150, -40, 120, 140, 40)):
        sph(x, y, -6, sx, sy, sz, "hill", "Far", False)
    for x, y, w, d, h in ((-55, -38, 9, 7, 4), (-38, -55, 7, 6, 3.5), (75, -45, 10, 7, 4), (92, -62, 8, 6, 3.5)):
        box(x, x + w, y, y + d, 0, h, "white", "Far", False)


# ------------------------------------------------------------------ 泳池平台 A + 凉棚餐台 B
def build_terrace():
    g = "A_Terrace"
    box(4, 28, 18, 23, -0.2, FL, "terrace", g, label="Terrace")
    # 两个种植池 + 橄榄
    for x0 in (7.5, 14.1):
        box(x0, x0 + 3.2, 18.5, 20.2, -0.2, FL + 0.02, "soil", g)
        olive(x0 + 1.6, 19.35, 0.55, FL)
    # 泳池: 池壁 (瓷砖) + 压顶石 + 池底 + 水
    gp = "A_Pool"
    box(14.4, 22.6, 23.4, 26.1, -1.6, -1.45, "pooltile", gp, label="PoolFloor")
    for (x0, x1, y0, y1) in ((14, 23, 23, 23.4), (14, 23, 26.1, 26.5), (14, 14.4, 23.4, 26.1), (22.6, 23, 23.4, 26.1)):
        box(x0, x1, y0, y1, -1.6, FL - 0.05, "pooltile", gp)
        box(x0, x1, y0, y1, FL - 0.05, FL, "coping", gp)
    box(14.4, 22.6, 23.4, 26.1, -0.02, 0.03, "water", gp, collide=False, label="PoolWater")
    # 低墙 (平台和院子之间), 两处开口下台阶进院子
    wall("x", 3.7, 17.0, 17.5, 17.8, 0, 0.6, "stone", [(6.0, 7.5, 0, 0.6, "open"), (13.5, 15.0, 0, 0.6, "open")], g)
    # 凉棚餐台 B
    gb = "B_Deck"
    box(28, 34, 18, 26.5, -0.2, FL, "teak", gb, label="Deck")
    for x in (28.2, 33.8):
        for y in (18.2, 22.3, 26.3):
            box(x - 0.08, x + 0.08, y - 0.08, y + 0.08, FL, 2.9, "teak", gb)
        box(x - 0.1, x + 0.1, 18.1, 26.4, 2.9, 3.1, "teak", gb)
    y = 18.25
    while y < 26.4:
        box(28.0, 34.0, y - 0.03, y + 0.03, 3.1, 3.25, "teak", gb, collide=False)
        y += 0.5
    box(33.35, 33.95, 21.0, 25.0, FL, FL + 0.9, "stone", gb, label="OutdoorKitchen")
    box(33.3, 34.0, 21.0, 25.0, FL + 0.9, FL + 0.95, "marble", gb)
    plight(31.0, 22.3, 2.8, 5, 700, lamp=False)


# ------------------------------------------------------------------ 院子 ①②③
def build_courts():
    # 院墙
    wall("y", 10.5, 17.5, 3.7, 4.0, 0, SW, "stone", (), "Courts")
    wall("y", 10.5, 17.5, 9.35, 9.65, 0, SW, "stone", (), "Courts")
    wall("y", 10.5, 17.5, 11.35, 11.65, 0, SW, "stone", (), "Courts")
    # ① 橄榄树院
    g = "C1_Olive"
    box(4.0, 9.35, 10.5, 17.5, -0.1, GR, "gravel", g)
    olive(6.7, 14.2, 1.15)
    box(4.6, 7.6, 10.75, 11.25, GR, 0.47, "stone", g, label="StoneBench")
    for i, (x, y) in enumerate(((6.7, 17.0), (6.4, 16.1), (6.9, 15.3))):
        box(x - 0.35, x + 0.35, y - 0.3, y + 0.3, GR, GR + 0.04, "terrace", g)
    for x in (4.3, 9.0):
        for y in (11.5, 13.0, 14.5, 16.0):
            bush(x, y, GR, 0.6, "olive")
    # ② 水渠窄院
    g = "C2_Rill"
    box(9.65, 11.35, 10.5, 17.5, -0.1, GR + 0.03, "terrace", g)
    box(10.05, 10.95, 11.0, 17.2, GR + 0.03, GR + 0.05, "water", g, collide=False, label="Rill")
    box(10.4, 10.6, 10.75, 10.95, 1.25, 1.35, "metal", g, label="WallSpout")
    fig(10.5, 17.0, 0.7, GR + 0.03)
    # ③ 香草厨园
    g = "C3_Herb"
    box(11.65, 17.0, 10.5, 17.5, -0.1, GR, "gravel", g)
    # 种植池之间留 1.1 m 走道 (VR 瞬移的导航网格需要 >= 2 x 0.35 m 的宽度, 0.7 m 太窄)
    beds = [(11.95, 13.75, 11.4, 13.35, "olive"), (14.85, 16.65, 11.4, 13.35, "lavender"),
            (11.95, 13.75, 14.45, 16.6, "leaf"), (14.85, 16.65, 14.45, 16.6, "leaf")]
    for x0, x1, y0, y1, pm in beds:
        box(x0, x1, y0, y1, GR, 0.5, "stone", g)
        box(x0 + 0.1, x1 - 0.1, y0 + 0.1, y1 - 0.1, 0.5, 0.52, "soil", g, False)
        for i in range(3):
            for j in range(3):
                bush(x0 + 0.35 + i * (x1 - x0 - 0.7) / 2, y0 + 0.35 + j * (y1 - y0 - 0.7) / 2, 0.5, 0.42, pm)
    box(12.0, 13.2, 10.75, 11.05, GR, 0.85, "stone", g, label="StoneSink")
    box(12.4, 12.8, 10.78, 10.85, 0.85, 1.15, "metal", g, label="Tap")


# ------------------------------------------------------------------ 客厅 C + 门厅 D (+ 地下室入口)
def build_living():
    g = "C_Living"
    box(17, 30, 10.5, 18, -0.2, FL, "wood", g, label="LivingFloor")
    # 北面整面玻璃 (中间 3 m 开着通平台), 西面玻璃 (对香草院, 中间一扇门)
    wall("x", 17, 30, 17.75, 18.0, 0, WT, "white", [(17.3, 24.0, FL, 3.1, "glass"), (24.0, 27.0, FL, 3.1, "open"), (27.0, 29.7, FL, 3.1, "glass")], g)
    wall("y", 10.75, 17.75, 17.0, 17.25, 0, WT, "white", [(10.9, 13.5, FL, 3.1, "glass"), (13.5, 14.6, FL, 2.5, "open"), (14.6, 17.6, FL, 3.1, "glass")], g)
    wall("y", 10.5, 17.75, 29.75, 30.0, 0, WT, "white", [(16.0, 17.0, FL, 2.4, "open")], g)
    wall("x", 21.0, 30.0, 10.5, 10.75, 0, WT, "white", (), g)
    roof(17, 30, 10.5, 18)
    # 厨房: 靠墙台面 + 岛台
    # 2026-10-18: 靠墙台面原来在 x18..23, 但后墙只有 x21..30 -> 左边 3 m 背后是门厅, 看着像隔断。挪到真墙前 x21..26
    box(21.0, 26.0, 10.75, 11.4, FL, FL + 0.9, "concrete", g, label="BackCounter")
    box(21.0, 26.0, 10.75, 11.45, FL + 0.9, FL + 0.95, "marble", g)
    box(19.0, 22.6, 12.3, 13.2, FL, FL + 0.9, "wood", g, label="Island")
    box(18.95, 22.65, 12.25, 13.25, FL + 0.9, FL + 0.96, "marble", g)
    box(23.7, 27.3, 14.6, 16.4, FL, FL + 0.01, "rug", g, False)
    for x, y in ((19.5, 11.9), (24.5, 12.5), (27.5, 15.0), (21.0, 15.5)):
        plight(x, y, CEIL - 0.3, 6.0)
    # 门厅 D: x17..21, y2.5..10.5; 楼梯洞 x19.5..20.6, y4.0..8.0
    # 楼梯从门厅南头的平台 (y2.75..4.0) 往北下, 下到底正对地下室通道 (旧版往南下, 走到底是一面墙)
    g = "D_Hall"
    # 楼梯井 x19.3..20.75 (宽 1.45 m, 东边直接贴门厅东墙), 两侧有墙一直到地下室地面:
    # 开敞的窄楼梯两边都是"悬崖", NavMesh 从两边各腐蚀 0.35 m 后中间断开, VR 瞬移下不去
    box(17.0, 19.3, 2.5, 10.5, -0.25, FL, "porcelain", g, label="HallFloor")
    box(20.75, 21.0, 2.5, 10.5, -0.25, FL, "porcelain", g)
    box(19.3, 20.75, 8.0, 10.5, -0.25, FL, "porcelain", g)
    # 平台入口净宽 1.25 m: VR 导航代理半径 0.35 m, 两边各腐蚀 0.35, 0.85 m 的口子会被切断
    box(19.3, 20.75, 2.5, 4.0, -0.25, FL, "porcelain", g, label="StairLanding")
    wall("y", 2.5, 10.5, 17.0, 17.25, 0, WT, "white", [(5.2, 6.3, FL, 2.3, "open"), (9.0, 10.0, FL, 2.3, "open")], g)
    wall("y", 2.5, 10.5, 20.75, 21.0, 0, WT, "white", [(8.0, 9.2, FL, 2.4, "open")], g)
    wall("x", 17.0, 21.0, 2.5, 2.75, 0, WT, "white", (), g)
    roof(17, 21, 2.5, 10.5)
    # 楼梯边玻璃栏杆
    # 西侧 (y4.0..8.0) + 北头横一段; 南头 y2.75..4.0 留口从门厅走上平台
    box(19.25, 19.3, 4.0, 8.0, FL, FL + 1.0, "glass", g)
    box(19.24, 19.31, 4.0, 8.0, FL + 1.0, FL + 1.05, "black", g)
    box(19.3, 20.75, 7.95, 8.0, FL, FL + 1.0, "glass", g)
    box(19.3, 20.75, 7.94, 8.01, FL + 1.0, FL + 1.05, "black", g)
    plight(19.0, 8.5, CEIL - 0.3, 5.0)
    plight(18.2, 4.0, CEIL - 0.3, 5.0)


def build_basement():
    g = "J_Basement"
    box(17.0, 27.5, 2.5, 10.0, BF - 0.15, BF, "concrete", g, label="BasementFloor")
    wall("x", 17.0, 27.5, 2.5, 2.75, BF, -0.25, "concrete", (), g)
    wall("x", 17.0, 27.5, 9.75, 10.0, BF, -0.25, "concrete", (), g)
    wall("y", 2.75, 9.75, 17.0, 17.25, BF, -0.25, "concrete", (), g)
    wall("y", 2.75, 9.75, 27.25, 27.5, BF, -0.25, "concrete", (), g)
    # 天花 (留楼梯洞)
    box(20.75, 27.5, 2.5, 10.0, -0.4, -0.25, "concrete", g)
    box(17.0, 19.3, 2.5, 10.0, -0.4, -0.25, "concrete", g)
    box(19.3, 20.75, 8.0, 10.0, -0.4, -0.25, "concrete", g)
    box(19.3, 20.75, 2.5, 4.0, -0.4, -0.25, "concrete", g)
    # 楼梯井两侧墙 (地下室地面 -> 顶板)
    box(19.15, 19.3, 4.0, 8.0, BF, -0.4, "concrete", g)
    box(20.75, 20.9, 4.0, 8.0, BF, -0.25, "concrete", g)
    # 楼梯 16 级 (每级高 0.1875, 深 0.25), 顶在南头平台 y=4.0, 往北下, 底在 y=8.0 (前面是 1.75 m 空地)
    for i in range(16):
        top = FL - (i + 1) * 0.1875
        y0 = 4.0 + i * 0.25
        box(19.3, 20.75, y0, y0 + 0.25, BF, top, "concrete", g)
    # 三排钢货架 + 纸箱
    k = 0
    for yc in (4.0, 5.8, 7.6):
        for x0 in (22.3, 24.6):                  # 楼梯井东墙 (20.9) 和货架之间留 1.4 m 通道 (VR 导航代理要 > 0.7 m 才不被腐蚀断)
            x1 = x0 + 2.0
            for xx in (x0, x1 - 0.05):
                for yy in (yc - 0.25, yc + 0.2):
                    box(xx, xx + 0.05, yy, yy + 0.05, BF, BF + 2.1, "metal", g)
            for lv in range(4):
                z = BF + 0.15 + lv * 0.6
                box(x0, x1, yc - 0.25, yc + 0.25, z, z + 0.03, "metal", g)
                xb = x0 + 0.1
                while xb < x1 - 0.5:
                    w = 0.35 + ((k * 37) % 5) * 0.06
                    h = 0.25 + ((k * 13) % 4) * 0.06
                    box(xb, xb + w, yc - 0.2, yc + 0.18, z + 0.03, z + 0.03 + h, "cardboard", g, False)
                    xb += w + 0.08
                    k += 1
    box(26.75, 27.25, 3.0, 9.4, BF, BF + 2.0, "teak", g, label="WineRack")
    box(17.4, 17.9, 3.0, 3.5, BF, BF + 0.7, "white", g, label="Dehumidifier")
    for x, y in ((18.5, 8.5), (22.5, 4.9), (22.5, 6.7), (25.5, 8.5)):
        plight(x, y, -0.6, 6.0, 700, lamp=False)
        box(x - 0.6, x + 0.6, y - 0.06, y + 0.06, -0.42, -0.4, "lamp", g, False)


# ------------------------------------------------------------------ 卧室翼 E/F + 私院 ④⑤
def build_wing():
    g = "E_F_Wing"
    box(9.1, 17.0, 2.5, 10.5, -0.2, FL, "wood", g, label="WingFloor")
    box(14.05, 16.9, 2.75, 4.95, FL, FL + 0.01, "porcelain", g, False)
    wall("x", 4.0, 17.0, 10.25, 10.5, 0, WT, "white", [(12.0, 16.0, 0.9, 2.6, "win")], g)
    wall("x", 4.0, 17.0, 2.5, 2.75, 0, WT, "white", [(10.0, 13.0, 0.9, 2.4, "win"), (15.0, 16.5, 1.6, 2.2, "win")], g)
    wall("y", 2.75, 10.25, 4.0, 4.25, 0, WT, "white", (), g)
    wall("y", 6.6, 10.25, 8.9, 9.1, 0, WT, "white", [(6.8, 8.0, FL, 2.7, "open"), (8.0, 10.1, FL, 2.7, "glass")], g)
    wall("y", 2.75, 6.4, 8.9, 9.1, 0, WT, "white", [(2.9, 4.0, FL, 2.7, "glass"), (4.0, 5.2, FL, 2.7, "open"), (5.2, 6.3, FL, 2.7, "glass")], g)
    box(8.9, 9.1, 6.4, 6.6, 0, WT, "white", g)
    box(4.25, 8.9, 6.4, 6.6, 0, 2.6, "white", g, label="PatioDivider")
    wall("x", 9.1, 17.0, 6.45, 6.55, FL, CEIL, "white_in", (), g)
    wall("y", 2.75, 6.45, 13.95, 14.05, FL, CEIL, "white_in", [(5.2, 6.2, FL, 2.2, "open")], g)
    wall("x", 14.05, 17.0, 4.95, 5.05, FL, CEIL, "white_in", [(15.0, 15.9, FL, 2.2, "open")], g)
    roof(9.0, 17.0, 2.5, 10.5)
    # 主卧
    box(10.0, 11.6, 6.6, 7.0, FL, FL + 0.55, "teak", g, label="Bench")
    plight(13.0, 8.5, CEIL - 0.3, 5.0)
    # 次卧: 床 (程序化) 床头靠南墙
    box(10.2, 11.8, 2.8, 4.8, FL, FL + 0.35, "teak", g, label="GuestBed")
    box(10.25, 11.75, 2.85, 4.75, FL + 0.35, FL + 0.55, "linen", g)
    box(10.4, 11.6, 2.9, 3.3, FL + 0.55, FL + 0.68, "linen", g, False)
    box(10.2, 11.8, 2.75, 2.85, FL, FL + 1.1, "teak", g)
    plight(11.5, 4.5, CEIL - 0.3, 5.0)
    # 卫浴
    box(14.3, 15.8, 2.8, 3.3, FL, FL + 0.85, "marble", g, label="Vanity")
    box(16.2, 16.7, 2.8, 3.5, FL, FL + 0.42, "white", g, label="WC")
    plight(15.5, 3.9, CEIL - 0.3, 4.0)
    plight(15.5, 5.7, CEIL - 0.3, 3.0)
    # ④ 主卧私院: 柚木平台 + 泡池 + 九重葛墙
    g = "C4_MasterPatio"
    box(4.25, 8.9, 6.6, 10.25, -0.2, FL, "teak", g)
    box(5.4, 7.6, 7.9, 9.5, FL, FL + 0.55, "white", g, label="Tub")
    box(5.5, 7.5, 8.0, 9.4, FL + 0.45, FL + 0.5, "water", g, False)
    # 九重葛: 有程序化植物时是一整片贴墙的叶片卡 (c8x_trees.py 的 BougaWall), 没有时退回一层扁椭球
    PLANTS.append(["BougaWall", 4.4, 10.17, 0.0, 1.0])
    for i in range(0 if TREES else 24):
        for j in range(11):
            k = i * 11 + j
            jx = ((k * 37) % 11) / 11.0 - 0.5
            jz = ((k * 53) % 13) / 13.0 - 0.5
            x = 4.4 + i * 0.19 + jx * 0.12
            z = 0.8 + j * 0.25 + jz * 0.15 + 0.4 * math.sin(i * 0.7)
            if z > 3.55 or z < 0.5:
                continue
            m = "leaf" if (k * 7) % 10 < 5 else "bouga"
            d = 0.24 + ((k * 17) % 5) * 0.03
            sph(x, 10.17 - ((k * 3) % 4) * 0.03, z, d, 0.12, d * 0.85, m)
    plight(6.5, 8.5, 2.0, 2.5, 500, lamp=False)
    # ⑤ 次卧私院: 碎石 + 柠檬树
    g = "C5_GuestPatio"
    box(4.25, 8.9, 2.75, 6.4, -0.2, GR + 0.07, "gravel", g)
    olive_like = fig
    olive_like(5.2, 5.4, 0.8, GR + 0.07)
    # 吊床已删除 (2026-10-18, 用户要求; 原来是一块平板 + 两根黑柱, 看着像长凳)


# ------------------------------------------------------------------ 入口长巷 ⑥ + 门院 ⑦ + 柠檬巷 ⑧ + 访客停车 G
def build_entry():
    g = "C6_EntryLane"
    box(21.0, 30.0, 7.1, 10.1, -0.1, GR, "gravel", g)
    box(21.0, 30.0, 9.75, 10.05, GR, GR + 0.02, "water", g, False, label="LaneRill")
    for i in range(10):
        x = 21.5 + i * 0.85
        box(x - 0.3, x + 0.3, 8.3, 9.0, GR, GR + 0.05, "terrace", g)
    box(21.0, 30.0, 10.1, 10.5, 0, 2.6, "stone", g, label="LaneWallN")
    box(21.0, 30.0, 6.8, 7.1, 0, 2.6, "stone", g, label="LaneWallS")
    for x in (23.0, 25.5, 28.0):
        cyl(x, 9.95, GR, GR + 0.7, 0.45, "terracotta", g, True)
        bush(x, 9.95, GR + 0.7, 0.45, "leaf", 0.5, kind="PotShrub")
    g = "C7_GateCourt"
    box(30.0, 33.0, 7.0, 10.5, -0.1, GR, "gravel", g)
    cyl(31.5, 8.5, GR, GR + 0.04, 1.2, "terrace", g, True)
    wall("y", 6.8, 10.5, 33.0, 33.3, 0, SW, "stone", [(8.0, 9.0, 0, 2.1, "open")], g)
    fig(30.8, 9.6, 0.9)
    cyl(32.4, 7.6, GR, GR + 0.6, 0.6, "stone", g, True)
    cyl(32.4, 7.6, GR + 0.55, GR + 0.62, 0.48, "water", g, False)
    g = "C8_LemonLane"
    box(30.0, 33.0, 10.5, 18.0, -0.2, FL - 0.05, "terrace", g)
    for y in (11.5, 13.0, 14.5):
        lemon_pot(30.5, y, FL - 0.05)
    box(32.0, 32.95, 16.8, 17.9, FL - 0.05, FL - 0.02, "porcelain", g, label="ShowerFloor")
    cyl(32.85, 17.6, FL, 2.4, 0.05, "metal", g, True)
    box(32.4, 32.85, 17.5, 17.7, 2.3, 2.36, "metal", g, label="ShowerHead")
    plight(32.4, 17.3, 2.6, 3.0, 400, lamp=False)
    g = "G_GuestParking"
    box(33.5, 37.5, 1.6, 10.0, -0.1, GR, "gravel", g)
    olive(36.2, 8.4, 0.8)
    for y in (3.0, 4.2, 5.4, 6.6, 7.8):
        box(34.0, 34.6, y, y + 0.6, GR, GR + 0.04, "terrace", g)


# ------------------------------------------------------------------ 车库 H + 工作间 I
def build_garage():
    g = "H_Garage"
    box(21.5, 33.0, 1.6, 6.8, -0.2, GR, "concrete", g, label="GarageFloor")
    wall("x", 21.5, 33.0, 1.6, 1.85, 0, WT, "white", [(22.5, 26.5, GR, 2.5, "open"), (29.0, 31.0, 1.1, 2.2, "win")], g)
    wall("x", 21.5, 33.0, 6.55, 6.8, 0, WT, "white", [(31.0, 32.0, GR, 2.3, "open")], g)
    wall("y", 1.85, 6.55, 21.5, 21.75, 0, WT, "white", (), g)
    wall("y", 1.85, 6.55, 32.75, 33.0, 0, WT, "white", (), g)
    wall("y", 1.85, 6.55, 27.45, 27.55, GR, CEIL, "white_in", [(3.0, 4.0, GR, 2.2, "open")], g)
    box(21.0, 21.5, 2.5, 6.8, 0, WT, "white", g)
    roof(21.5, 33.0, 1.6, 6.8)
    box(22.5, 26.5, 1.62, 1.84, 2.5, 2.75, "metal", g, label="RollerDoorBox")
    for x0, paint in ((22.3, "car_blue"), (24.95, "car_white")):
        w, L, y0 = 1.85, 4.4, 2.0
        box(x0, x0 + w, y0, y0 + L, 0.32, 0.85, paint, g, label="CarBody")
        box(x0 + 0.12, x0 + w - 0.12, y0 + 1.2, y0 + 3.4, 0.85, 1.32, "screen", g)
        box(x0 + 0.15, x0 + w - 0.15, y0 + 1.3, y0 + 3.3, 1.32, 1.4, paint, g)
        for dx in (0.1, w - 0.1):
            for dy in (0.9, L - 0.9):
                cyl(x0 + dx, y0 + dy, 0.22, 0.44, 0.66, "black", g, True, pitch=90)
    plight(24.5, 4.2, CEIL - 0.3, 5.0)
    # 工作间
    g = "I_Workshop"
    box(27.8, 30.8, 5.9, 6.5, GR, GR + 0.88, "teak", g, label="Workbench")
    box(27.75, 30.85, 5.85, 6.55, GR + 0.88, GR + 0.94, "teak", g)
    box(28.1, 28.5, 5.95, 6.25, GR + 0.94, GR + 1.12, "metal", g, label="Vise")
    box(32.6, 32.72, 2.3, 5.7, 1.0, 2.3, "concrete", g, label="Pegboard")
    tools = [(2.6, 1.6, 2.0, "red"), (3.1, 1.5, 2.1, "metal"), (3.6, 1.7, 2.15, "metal"), (4.1, 1.4, 2.0, "red"),
             (4.6, 1.6, 2.1, "black"), (5.1, 1.5, 2.15, "metal"), (2.8, 1.15, 1.35, "yellow"), (3.8, 1.1, 1.4, "metal"), (4.8, 1.2, 1.4, "red")]
    for y, z0, z1, m in tools:
        box(32.5, 32.6, y - 0.06, y + 0.06, z0, z1, m, g, False)
    cyl(28.3, 2.4, GR, GR + 0.08, 0.45, "metal", g, True)
    cyl(28.3, 2.25, GR, GR + 1.6, 0.08, "metal", g, True)
    box(28.1, 28.5, 2.15, 2.6, GR + 1.3, GR + 1.6, "red", g, label="DrillPress")
    box(29.3, 30.6, 1.9, 2.5, GR, GR + 1.0, "red", g, label="ToolCabinet")
    # 更多工具: 锤子、扳手、锯、螺丝刀 (洞洞板), 墙架上的油漆罐
    for k in range(14):
        y = 2.45 + k * 0.23
        zc = 1.25 + (k % 3) * 0.32
        m = ("red", "metal", "black", "yellow")[k % 4]
        box(32.52, 32.6, y - 0.03, y + 0.03, zc, zc + 0.22 + (k % 2) * 0.1, m, g, False)
        if k % 3 == 0:
            box(32.52, 32.6, y - 0.07, y + 0.07, zc + 0.22, zc + 0.27, "metal", g, False)
    box(27.7, 28.0, 2.2, 5.6, GR, GR + 2.0, "metal", g, label="Shelf")
    for lv in range(4):
        z = GR + 0.3 + lv * 0.5
        box(27.6, 28.05, 2.2, 5.6, z, z + 0.03, "teak", g, False)
        for k in range(5):
            y = 2.5 + k * 0.62
            cyl(27.82, y, z + 0.03, z + 0.25, 0.2, ("red", "white", "metal", "yellow", "esd")[(k + lv) % 5], g, True)
    plight(30.2, 4.2, CEIL - 0.3, 7.0)


# ------------------------------------------------------------------ 电子工作室 K
def build_studio():
    g = "K_Studio"
    box(33.0, 37.5, 10.5, 18.0, -0.2, FL, "wood", g, label="StudioFloor")
    wall("y", 10.5, 18.0, 33.0, 33.25, 0, WT, "white", [(12.0, 13.0, FL, 2.3, "open")], g)
    wall("y", 10.5, 18.0, 37.25, 37.5, 0, WT, "white", (), g)  # 东墙不开窗: 零件盒层架靠这面墙
    wall("x", 33.25, 37.25, 17.75, 18.0, 0, WT, "white", [(34.0, 36.8, 0.9, 2.6, "win")], g)
    wall("x", 33.25, 37.25, 10.5, 10.75, 0, WT, "white", (), g)
    roof(33.0, 37.5, 10.5, 18.0)
    T = FL + 0.92
    # 东墙 6 m 防静电工作台
    box(36.45, 37.2, 11.2, 17.2, FL, T - 0.03, "metal", g, label="ESDBench")
    box(36.45, 37.2, 11.2, 17.2, T - 0.03, T, "esd", g)
    box(37.12, 37.25, 11.2, 17.2, T, T + 0.9, "concrete", g, label="BenchPegboard")
    # 仪器 (精细区: 先做成比例准确的体块, 屏幕用深色玻璃)
    inst = [  # y0, y1, h, depth, name, mat
        (11.6, 12.05, 0.25, 0.45, "Oscilloscope", "metal"),
        (12.25, 12.6, 0.16, 0.35, "PowerSupply", "black"),
        (12.8, 13.0, 0.12, 0.25, "Multimeter", "yellow"),
        (13.3, 13.6, 0.12, 0.3, "SolderStation", "red"),
        (15.6, 16.0, 0.3, 0.4, "FumeExtractor", "black"),
        (16.3, 16.75, 0.18, 0.35, "LogicAnalyzer", "black")]
    for y0, y1, h, dep, nm, m in inst:
        box(37.15 - dep, 37.15, y0, y1, T, T + h, m, g, label=nm)
        if nm in ("Oscilloscope", "PowerSupply", "LogicAnalyzer"):
            box(37.15 - dep - 0.01, 37.15 - dep, y0 + 0.04, y1 - 0.04, T + 0.04, T + h - 0.03, "screen", g, False)
    cyl(36.85, 14.4, T, T + 0.05, 0.3, "black", g, True)
    cyl(36.95, 14.4, T + 0.05, T + 0.45, 0.05, "metal", g, True)
    cyl(36.8, 14.4, T + 0.3, T + 0.42, 0.12, "black", g, True)
    for i, y in enumerate((13.9, 14.9, 15.2)):
        box(36.55, 36.75, y, y + 0.15, T, T + 0.015, "pcb", g, False)
    box(36.6, 36.7, 15.0, 15.1, T, T + 0.04, "black", g, False, label="Servo")
    # 北窗下写代码的桌子 + 两台显示器
    box(33.6, 36.2, 17.1, 17.7, FL, FL + 0.72, "teak", g, label="CodeDesk")
    for x0 in (34.0, 35.0):
        box(x0, x0 + 0.6, 17.5, 17.53, FL + 0.95, FL + 1.32, "screen", g, label="Monitor")
        box(x0 + 0.27, x0 + 0.33, 17.53, 17.6, FL + 0.72, FL + 0.95, "black", g, False)
    cyl(35.0, 16.4, FL, FL + 0.45, 0.45, "black", g, True)
    cyl(36.0, 13.0, FL, FL + 0.6, 0.42, "black", g, True)
    # 南墙: 元件抽屉柜 + 3D 打印机
    box(33.5, 35.5, 10.8, 11.25, FL, FL + 1.2, "metal", g, label="ComponentDrawers")
    for r in range(6):
        for c in range(5):
            box(33.55 + c * 0.39, 33.55 + c * 0.39 + 0.33, 11.25, 11.27, FL + 0.08 + r * 0.19, FL + 0.08 + r * 0.19 + 0.14, "white", g, False)
    box(35.8, 36.4, 10.85, 11.45, FL, FL + 0.7, "teak", g)
    box(35.85, 36.35, 10.9, 11.4, FL + 0.7, FL + 1.2, "black", g, label="Printer3D")
    # 示波器屏幕上的方波 (黄线), 显示器上的"代码行"
    sx = 37.15 - 0.45 - 0.012
    ys = [11.66 + i * 0.045 for i in range(8)]
    for i in range(7):
        zl = T + (0.08 if i % 2 == 0 else 0.17)
        box(sx - 0.004, sx, ys[i], ys[i + 1], zl, zl + 0.008, "yellow", g, False)
        box(sx - 0.004, sx, ys[i + 1] - 0.004, ys[i + 1], T + 0.08, T + 0.178, "yellow", g, False)
    code = ["esd", "yellow", "white", "esd", "white", "red", "white", "esd", "yellow", "white"]
    for x0 in (34.0, 35.0):
        for r, cm in enumerate(code):
            ind = 0.04 + (r % 3) * 0.05
            ln = 0.18 + ((r * 7) % 5) * 0.06
            z = FL + 1.28 - r * 0.033
            box(x0 + ind, x0 + min(0.57, ind + ln), 17.494, 17.499, z, z + 0.012, cm, g, False)
    # 工作台上: 第三台显示器 + 键盘, 面包板 + 跳线, 焊锡卷, 台灯
    box(36.95, 36.98, 14.9, 15.5, T + 0.18, T + 0.52, "screen", g, label="BenchMonitor")
    box(36.98, 37.05, 15.17, 15.23, T, T + 0.2, "black", g, False)
    box(36.5, 36.68, 14.95, 15.45, T, T + 0.02, "black", g, False, label="Keyboard")
    box(36.55, 36.8, 13.95, 14.12, T, T + 0.012, "white", g, False, label="Breadboard")
    for i, cm in enumerate(("red", "black", "yellow", "esd", "red", "white")):
        y = 13.97 + i * 0.025
        box(36.58 + (i % 3) * 0.05, 36.7 + (i % 2) * 0.05, y, y + 0.006, T + 0.012, T + 0.02, cm, g, False)
    for k, (y, cm) in enumerate(((13.92, "black"), (13.96, "black"), (14.0, "yellow"), (14.04, "red"))):
        box(36.57 + k * 0.02, 36.59 + k * 0.02, y, y + 0.02, T + 0.015, T + 0.035, cm, g, False)
    cyl(36.62, 13.75, T, T + 0.04, 0.09, "metal", g, True)
    cyl(37.05, 16.9, T, T + 0.6, 0.03, "black", g, True)
    box(36.8, 37.05, 16.8, 17.0, T + 0.56, T + 0.62, "white", g, False, label="BenchLamp")
    # 工作台上方: 零件盒层架 (三层, 彩色小盒)
    for lv in range(3):
        z = T + 0.75 + lv * 0.28
        box(36.95, 37.12, 11.2, 17.2, z, z + 0.02, "teak", g, False)
        y = 11.25
        k = 0
        while y < 17.1:
            cm = ("red", "white", "yellow", "esd", "metal")[(k + lv) % 5]
            box(36.97, 37.11, y, y + 0.11, z + 0.02, z + 0.12, cm, g, False)
            y += 0.14
            k += 1
    # 办公椅 + 西墙白板
    cyl(36.0, 13.0, FL, FL + 0.06, 0.6, "black", g, True)
    cyl(36.0, 13.0, FL + 0.06, FL + 0.45, 0.06, "metal", g, True)
    box(35.75, 36.25, 12.75, 13.25, FL + 0.45, FL + 0.53, "black", g, label="OfficeChair")
    box(35.75, 35.82, 12.75, 13.25, FL + 0.53, FL + 1.1, "black", g)
    box(33.25, 33.28, 14.0, 16.6, 1.0, 2.1, "white", g, label="Whiteboard")
    box(33.25, 33.3, 13.97, 16.63, 0.97, 1.0, "black", g, False)
    for i in range(4):
        box(33.28, 33.285, 14.3, 14.9 + i * 0.3, 1.8 - i * 0.18, 1.81 - i * 0.18, "black", g, False)
    plight(35.0, 12.5, CEIL - 0.3, 8.0)
    plight(35.0, 15.8, CEIL - 0.3, 8.0)


# ------------------------------------------------------------------ AI 家具 (复用 L_Villa 的, 只挪位置)
# 朝向: 大多数 AI 家具 yaw 0 = 正面朝大海 (-Y); 但沙发的网格正面相反 (俯视截图实测), 所以沙发给 180
PLACE = {
    "sofa": [(25.5, 14.2, FL, 180)],
    "coffee_table": [(25.5, 15.5, FL, 0)],
    "armchair": [(23.9, 15.4, FL, 90), (27.1, 15.4, FL, -90)],
    "bar_stool": [(19.9, 13.75, FL, 180), (20.8, 13.75, FL, 180), (21.7, 13.75, FL, 180)],
    "plant": [(29.3, 17.3, FL, 0), (17.7, 17.2, FL, 0), (17.6, 9.8, FL, 0), (16.4, 9.9, FL, 0)],
    "round_bed": [(14.0, 8.4, FL, 0)],
    "sun_lounger": [(15.6, 22.0, FL, 0), (16.7, 22.0, FL, 0), (20.3, 22.0, FL, 0), (21.4, 22.0, FL, 0), (8.25, 8.6, FL, -90)],
    "umbrella": [(13.0, 21.9, FL, 0), (24.6, 21.6, FL, 0)],
    "dining_table": [(31.0, 22.3, FL, 0)],
    "dining_chair": [(30.35, 21.6, FL, 0), (31.0, 21.6, FL, 0), (31.65, 21.6, FL, 0),
                     (30.35, 23.0, FL, 180), (31.0, 23.0, FL, 180), (31.65, 23.0, FL, 180)],
    "bbq_grill": [(33.0, 19.2, FL, -90)],
    "egg_chair": [(5.4, 21.2, FL, 0)],
    "flamingo_float": [(17.2, 24.6, 0.0, -30)],
}


def place_ai():
    """导入的 AI_* Actor 改旋转不生效 (实测), 所以按它的网格和材质重新生成一个普通 StaticMeshActor, 再删掉原来的。
    重新生成的标签叫 CF_<种类>_<序号>, 带 Courtyard 标签, 下次重跑会被清掉, 所以第一次运行时记下网格和材质。"""
    import re
    cache_p = os.path.join(D, "ai_furniture_cache.json")
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        m = re.match(r"AI_([a-z_]+?)_(\d+)", lab)
        if not m:
            continue
        kind = m.group(1)
        if kind not in cache and isinstance(a, unreal.StaticMeshActor):
            smc = a.static_mesh_component
            cache[kind] = {"mesh": smc.static_mesh.get_path_name(),
                           "mats": [smc.get_material(i).get_path_name() if smc.get_material(i) else "" for i in range(smc.get_num_materials())]}
        EAS.destroy_actor(a)
    json.dump(cache, open(cache_p, "w", encoding="utf-8"), indent=1)
    used = {}
    for kind, spots in PLACE.items():
        if kind not in cache:
            LOG.append("no mesh for " + kind)
            continue
        mesh = unreal.load_asset(cache[kind]["mesh"])
        mats = [unreal.load_asset(p) if p else None for p in cache[kind]["mats"]]
        for i, (x, y, z, yaw) in enumerate(spots):
            a = EAS.spawn_actor_from_object(mesh, V(x, y, z), unreal.Rotator(0, 0, yaw))
            for k, mt in enumerate(mats):
                if mt:
                    a.static_mesh_component.set_material(k, mt)
            o, e = a.get_actor_bounds(False)
            a.set_actor_location(unreal.Vector(x * 100 - (o.x - x * 100), -y * 100 - (o.y + y * 100), z * 100 + (z * 100 - (o.z - e.z))), False, False)
            a.set_editor_property("tags", [unreal.Name(TAG)])
            a.set_folder_path("Courtyard/Furniture")
            a.set_actor_label("CF_%s_%d" % (kind, i))
            used[kind] = i + 1
    LOG.append("AI furniture placed: %s" % used)


# ------------------------------------------------------------------ 出生点 + 导航
def player_and_nav():
    for a in EAS.get_all_level_actors():
        cls = a.get_class().get_name()
        if cls == "PlayerStart":
            a.set_actor_location(V(29.3, 8.6, 1.0), False, False)
            a.set_actor_rotation(unreal.Rotator(0, 0, 180), False)
            LOG.append("PlayerStart -> entry lane")
        if cls == "NavMeshBoundsVolume":
            center = V(19.0, 13.0, 0.4)
            half = unreal.Vector(2100, 1650, 380)
            o, e = a.get_actor_bounds(False)
            s = a.get_actor_scale3d()
            rc = a.root_component
            rc.set_editor_property("relative_location", center)
            rc.set_editor_property("relative_scale3d", unreal.Vector(s.x * half.x / max(e.x, 1), s.y * half.y / max(e.y, 1), s.z * half.z / max(e.z, 1)))
            LOG.append("NavMeshBounds -> %s" % center)


def import_merged():
    """导入云端生成的 court_geom.glb: 每个 (区域, 材质) 一个静态网格, 顶点已经是世界坐标, 所以 Actor 放在原点。"""
    if not MERGED:
        return
    dst = "/Game/Courtyard/Geom"
    t = unreal.AssetImportTask()
    t.filename = os.path.join(D, "court_geom.glb")
    t.destination_path = dst
    t.automated = True
    t.save = True
    t.replace_existing = True
    TOOLS.import_asset_tasks([t])
    n = 0
    for path in EAL.list_assets(dst, recursive=True, include_folder=False):
        a0 = EAL.load_asset(path)
        if not isinstance(a0, unreal.StaticMesh):
            continue
        name = a0.get_name()
        key = name[3:] if name.startswith("SM_") else name
        parts = key.split("__")               # <区域>__<材质>[__nc]
        if len(parts) < 2:
            continue
        group, mat = parts[0], parts[1]
        collide = not (len(parts) > 2 and parts[2] == "nc")
        # 导入时会自动生成凸包碰撞; 导航按简单碰撞算, 墙+天花板的凸包会把整间屋子填实 -> 屋里没有 NavMesh
        unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(a0)
        bs = a0.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(a0)
        a = EAS.spawn_actor_from_object(a0, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        mm = M.get(mat)
        if mm:
            for i in range(a.static_mesh_component.get_num_materials()):
                a.static_mesh_component.set_material(i, mm)
        finish(a, None, "Geom/" + group, collide, "G_" + name)
        n += 1
    LOG.append("merged geometry actors: %d" % n)


def main():
    clean()
    build_materials()
    build_site()
    build_terrace()
    build_courts()
    build_living()
    build_basement()
    build_wing()
    build_entry()
    build_garage()
    build_studio()
    import_merged()
    place_ai()
    if TREES:                                   # 程序化植物 (叶片卡) 由 c8_trees.py 摆放
        import importlib.util
        spec = importlib.util.spec_from_file_location("c8_trees", os.path.join(D, "c8_trees.py"))
        c8 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c8)
        c8.main(PLANTS)
        LOG.extend(c8.LOG)
    if os.path.exists(os.path.join(D, "c10_plants.py")):   # Fab 植物 (c10_plants.py 自己会先删掉上次放的)
        import importlib.util
        spec = importlib.util.spec_from_file_location("c10_plants", os.path.join(D, "c10_plants.py"))
        c10 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(c10)
        c10.main()
        LOG.extend(c10.LOG)
    player_and_nav()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    LOG.append("spawned %d meshes; saved %s" % (COUNT["n"], les.save_current_level()))
    open(os.path.join(D, "c2_report.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    print(" | ".join(LOG))


if __name__ == "__main__":
    main()
