# -*- coding: utf-8 -*-
"""
海边二层小别墅 —— Blender 场景生成脚本（给 Quest 3 / VR Scene Inspection 用）

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_villa.py -- 输出路径.blend

坐标约定（重要，VR 尺度全靠它）:
    1 个 Blender 单位 = 1 米
    +Y 方向是大海，+Z 向上，地面（沙滩）z = 0
    一楼地面 z = 0.3（房子坐在 30cm 高的台基上），二楼地面 z = 3.5，屋顶 z = 6.5

兼容: Blender 3.6 ~ 5.x（只用 from_pydata / bmesh 建模，不依赖版本专有的 bpy.ops）
"""
import math
import sys

import bpy
import bmesh

# ---------------------------------------------------------------- 尺寸参数
F1 = 0.30            # 一楼地面标高
F2 = 3.50            # 二楼地面标高（层高 3.2m）
ROOF = 6.50          # 二楼墙顶 / 屋面板底
SLAB = 0.25          # 楼板厚
WALL = 0.20          # 外墙厚
EYE = 1.65           # VR 点位的眼睛高度（相对所站地面）

# 楼梯: 18 级，总高 3.2m → 每级 17.8cm；踏面 28cm（常见住宅尺寸）
STAIR_N = 18
STAIR_X0 = -4.5      # 第一级起点 x
STAIR_RUN = 0.28
STAIR_Y = (-4.8, -3.7)
STAIR_X1 = STAIR_X0 + (STAIR_N - 1) * STAIR_RUN      # = 0.26，到二楼的位置
HOLE_X = (STAIR_X0 + 0.8, STAIR_X1)                  # 二楼楼板开洞（保证 2m 以上头顶净空）


# ---------------------------------------------------------------- 基础工具
def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def link(obj, c):
    c.objects.link(obj)
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mat, c):
    """轴对齐长方体，顶点直接用世界坐标（物体原点在 0,0,0，方便程序纹理按世界尺寸对齐）。"""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], f)
    me.update()
    me.materials.append(mat)
    return link(bpy.data.objects.new(name, me), c)


def mesh_obj(name, verts, faces, mat, c, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return link(bpy.data.objects.new(name, me), c)


def bm_obj(name, bm, mat, c, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return link(bpy.data.objects.new(name, me), c)


# ---------------------------------------------------------------- 材质（全部程序化，不需要外部贴图）
def principled(name, color, rough=0.5, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*color, alpha)          # 实体模式下的颜色
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):  # Blender 4.2+
            m.surface_render_method = "BLENDED"
        if hasattr(m, "blend_method"):            # 旧版 Eevee
            try:
                m.blend_method = "BLEND"
            except TypeError:
                pass
        if hasattr(m, "shadow_method"):          # 旧版: 玻璃不挡阳光
            m.shadow_method = "NONE"
        if hasattr(m, "use_transparent_shadow"):  # 4.2+
            m.use_transparent_shadow = True
        m.use_backface_culling = False
    return m, bsdf


def add_tex_color(m, bsdf, kind, scale, stretch, c_dark, c_light, bump=0.0):
    """给材质加一层程序纹理: 世界坐标 → 拉伸 → 噪波/波纹 → 色带 → Base Color (+ 凹凸)。"""
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = stretch
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    if kind == "wave":
        tx = nt.nodes.new("ShaderNodeTexWave")
        tx.inputs["Distortion"].default_value = 4.0
        tx.inputs["Detail"].default_value = 3.0
    else:
        tx = nt.nodes.new("ShaderNodeTexNoise")
        tx.inputs["Detail"].default_value = 6.0
    tx.inputs["Scale"].default_value = scale
    nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c_dark, 1)
    ramp.color_ramp.elements[1].color = (*c_light, 1)
    nt.links.new(tx.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if bump > 0:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(tx.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])


def make_materials():
    M = {}
    M["plaster"], _ = principled("白墙", (0.86, 0.85, 0.81), 0.85)
    M["concrete"], b = principled("清水混凝土", (0.55, 0.54, 0.52), 0.9)
    add_tex_color(M["concrete"], b, "noise", 3.0, (1, 1, 1), (0.45, 0.44, 0.42), (0.62, 0.61, 0.58), 0.05)
    M["floor"], b = principled("室内木地板", (0.55, 0.38, 0.22), 0.45)
    add_tex_color(M["floor"], b, "noise", 2.0, (0.6, 12.0, 1), (0.42, 0.27, 0.15), (0.66, 0.47, 0.29))
    M["deck"], b = principled("户外柚木", (0.42, 0.28, 0.17), 0.7)
    add_tex_color(M["deck"], b, "wave", 1.4, (1, 0.05, 1), (0.30, 0.19, 0.11), (0.52, 0.36, 0.22), 0.15)
    M["tile"], _ = principled("阳台石材", (0.78, 0.76, 0.72), 0.6)
    M["glass"], _ = principled("玻璃", (0.75, 0.88, 0.90), 0.02, alpha=0.15)
    M["frame"], _ = principled("黑色窗框", (0.04, 0.04, 0.045), 0.4, metal=0.8)
    M["sand"], b = principled("沙滩", (0.74, 0.58, 0.36), 0.95)
    add_tex_color(M["sand"], b, "noise", 0.8, (1, 1, 1), (0.64, 0.49, 0.29), (0.80, 0.65, 0.42), 0.3)
    M["sea"], b = principled("海水", (0.01, 0.16, 0.24), 0.12)
    add_tex_color(M["sea"], b, "noise", 0.15, (1, 2.5, 1), (0.005, 0.10, 0.18), (0.03, 0.30, 0.36), 0.35)
    M["pool"], _ = principled("泳池水", (0.10, 0.55, 0.62), 0.03)
    M["pooltile"], _ = principled("泳池瓷砖", (0.55, 0.80, 0.85), 0.3)
    M["fabric"], _ = principled("沙发布", (0.80, 0.77, 0.70), 0.95)
    M["cushion"], _ = principled("靠垫蓝", (0.12, 0.26, 0.40), 0.95)
    M["wood_furn"], _ = principled("家具木", (0.36, 0.23, 0.13), 0.5)
    M["counter"], _ = principled("台面", (0.93, 0.93, 0.92), 0.25)
    M["bed"], _ = principled("床品", (0.95, 0.95, 0.93), 0.9)
    M["rug"], _ = principled("地毯", (0.70, 0.64, 0.55), 1.0)
    M["trunk"], b = principled("椰树干", (0.38, 0.29, 0.20), 0.9)
    add_tex_color(M["trunk"], b, "wave", 3.0, (0.01, 0.01, 1), (0.28, 0.21, 0.14), (0.48, 0.38, 0.27), 0.4)
    M["leaf"], _ = principled("椰树叶", (0.12, 0.35, 0.10), 0.6)
    M["hill"], _ = principled("远山", (0.24, 0.33, 0.20), 1.0)
    M["umbrella"], _ = principled("遮阳伞", (0.93, 0.90, 0.82), 0.9)
    return M


# ---------------------------------------------------------------- 墙 + 门窗洞
def wall(name, x0, x1, y0, y1, z0, h, openings, M, C_struct, C_glass):
    """
    沿长边方向的直墙，openings = [(a0, a1, 窗台高, 窗顶高, 是否装玻璃), ...]
    a0/a1 是沿墙方向的绝对坐标，窗台/窗顶相对本层地面 z0。
    做法: 不用布尔运算，直接把墙切成 "窗间墙 + 窗下墙 + 窗上墙" 几块长方体 —— 网格干净、VR 里渲染便宜。
    """
    along_x = (x1 - x0) >= (y1 - y0)
    a_lo, a_hi = (x0, x1) if along_x else (y0, y1)
    t0, t1 = (y0, y1) if along_x else (x0, x1)    # 厚度方向

    def piece(tag, a, b, za, zb, mat=None, coll_=None, tt=None):
        if b - a < 1e-4 or zb - za < 1e-4:
            return
        u0, u1 = tt if tt else (t0, t1)
        if along_x:
            box(f"{name}_{tag}", a, u0, za, b, u1, zb, mat or M["plaster"], coll_ or C_struct)
        else:
            box(f"{name}_{tag}", u0, a, za, u1, b, zb, mat or M["plaster"], coll_ or C_struct)

    cur = a_lo
    for i, (a0, a1, sill, head, glazed) in enumerate(sorted(openings)):
        piece(f"墙{i}", cur, a0, z0, z0 + h)
        piece(f"窗下{i}", a0, a1, z0, z0 + sill)
        piece(f"窗上{i}", a0, a1, z0 + head, z0 + h)
        if glazed:
            mid = (t0 + t1) / 2
            fw = 0.05                                   # 窗框截面 5cm
            ft = (mid - 0.04, mid + 0.04)
            gt = (mid - 0.01, mid + 0.01)
            zs, zh = z0 + sill, z0 + head
            piece(f"框下{i}", a0, a1, zs, zs + fw, M["frame"], C_glass, ft)
            piece(f"框上{i}", a0, a1, zh - fw, zh, M["frame"], C_glass, ft)
            piece(f"框左{i}", a0, a0 + fw, zs, zh, M["frame"], C_glass, ft)
            piece(f"框右{i}", a1 - fw, a1, zs, zh, M["frame"], C_glass, ft)
            n = max(1, round((a1 - a0) / 2.2))           # 宽窗每 ~2.2m 一根竖梃
            for k in range(1, n):
                m = a0 + (a1 - a0) * k / n
                piece(f"竖梃{i}_{k}", m - fw / 2, m + fw / 2, zs, zh, M["frame"], C_glass, ft)
            piece(f"玻璃{i}", a0 + fw, a1 - fw, zs + fw, zh - fw, M["glass"], C_glass, gt)
        cur = a1
    piece("墙end", cur, a_hi, z0, z0 + h)


def railing(name, x0, y0, x1, y1, z, M, C):
    """玻璃栏板 1.1m + 顶部扶手（建筑规范常见高度 1.05~1.1m）。"""
    along_x = abs(x1 - x0) >= abs(y1 - y0)
    if along_x:
        box(name + "_玻璃", x0, y0 - 0.01, z, x1, y0 + 0.01, z + 1.05, M["glass"], C)
        box(name + "_扶手", x0, y0 - 0.03, z + 1.05, x1, y0 + 0.03, z + 1.1, M["frame"], C)
    else:
        box(name + "_玻璃", x0 - 0.01, y0, z, x0 + 0.01, y1, z + 1.05, M["glass"], C)
        box(name + "_扶手", x0 - 0.03, y0, z + 1.05, x0 + 0.03, y1, z + 1.1, M["frame"], C)


# ---------------------------------------------------------------- 建筑本体
def build_house(M):
    S, G = coll("结构"), coll("玻璃与栏杆")

    # 台基 + 一楼木地板
    box("台基", -7, -5, 0, 7, 5, F1 - 0.01, M["concrete"], S)
    box("一楼地板", -6.8, -4.8, F1 - 0.01, 6.8, 4.8, F1, M["floor"], S)

    # ---------- 一楼外墙（门窗: (起, 止, 窗台, 窗顶, 玻璃?)）
    h1 = F2 - F1
    wall("一楼南墙_海景", -7, 7, 4.8, 5.0, F1, h1, [(-6.6, 6.6, 0.0, 2.9, True)], M, S, G)
    wall("一楼北墙", -7, 7, -5.0, -4.8, F1, h1,
         [(0.8, 1.8, 0.9, 2.4, True), (2.4, 3.4, 0.0, 2.3, False), (4.9, 6.4, 1.6, 2.4, True)], M, S, G)
    wall("一楼西墙", -7.0, -6.8, -4.8, 4.8, F1, h1, [(-1.0, 2.0, 1.2, 2.4, True)], M, S, G)
    wall("一楼东墙", 6.8, 7.0, -4.8, 4.8, F1, h1, [(-1.5, 3.5, 0.4, 2.6, True)], M, S, G)
    # 卫生间隔墙
    wall("卫生间隔墙A", 4.45, 4.55, -4.8, -2.5, F1, h1, [(-3.6, -2.8, 0.0, 2.1, False)], M, S, G)
    wall("卫生间隔墙B", 4.55, 6.8, -2.55, -2.45, F1, h1, [], M, S, G)

    # ---------- 楼梯（实心踏步）
    rise = (F2 - F1) / STAIR_N
    for i in range(STAIR_N - 1):
        xa = STAIR_X0 + i * STAIR_RUN
        box(f"踏步{i + 1:02d}", xa, STAIR_Y[0], F1, xa + STAIR_RUN, STAIR_Y[1],
            F1 + (i + 1) * rise, M["wood_furn"], S)

    # ---------- 二楼楼板（= 一楼屋顶 / 阳台），挖出楼梯洞
    z0, z1 = F2 - SLAB, F2 - 0.01
    hx0, hx1 = HOLE_X
    hy0, hy1 = STAIR_Y
    for tag, r in {"A": (-7, hy1, 7, 5), "B": (-7, -5, hx0, hy1),
                   "C": (hx1, -5, 7, hy1), "D": (hx0, -5, hx1, hy0)}.items():
        box(f"二楼楼板{tag}", r[0], r[1], z0, r[2], r[3], z1, M["plaster"], S)
    # 室内木地板（避开楼梯洞）
    for tag, r in {"A": (-6.8, hy1, 2.8, 2.8), "B": (-6.8, hy0, hx0, hy1),
                   "C": (hx1, hy0, 2.8, hy1)}.items():
        box(f"二楼地板{tag}", r[0], r[1], z1, r[2], r[3], F2, M["floor"], S)
    # 阳台石材（二楼外墙以外的屋面）
    box("阳台面_海侧", -7, 3.0, z1, 7, 5, F2, M["tile"], S)
    box("阳台面_东侧", 3.0, -5, z1, 7, 3.0, F2, M["tile"], S)

    # ---------- 二楼外墙（二楼退进: x -7~3, y -5~3，外面一圈就是 L 形大阳台）
    h2 = ROOF - F2
    wall("二楼南墙_海景", -7, 3, 2.8, 3.0, F2, h2, [(-6.6, 2.6, 0.0, 2.6, True)], M, S, G)
    wall("二楼北墙", -7, 3, -5.0, -4.8, F2, h2,
         [(-6.2, -4.8, 1.0, 2.3, True), (1.0, 2.4, 1.0, 2.3, True)], M, S, G)
    wall("二楼西墙", -7.0, -6.8, -4.8, 2.8, F2, h2, [(-2.0, 1.5, 0.8, 2.4, True)], M, S, G)
    wall("二楼东墙", 2.8, 3.0, -4.8, 2.8, F2, h2,
         [(-1.2, -0.2, 0.0, 2.3, False), (0.5, 2.2, 0.8, 2.4, True)], M, S, G)

    # 楼梯洞护栏
    railing("楼梯洞护栏_长", hx0, hy1, hx1, hy1, F2, M, G)
    railing("楼梯洞护栏_端", hx0, hy0, hx0, hy1, F2, M, G)

    # 阳台栏杆
    railing("阳台栏杆_南", -7, 4.97, 7, 4.97, F2, M, G)
    railing("阳台栏杆_东", 6.97, -5, 6.97, 5, F2, M, G)
    railing("阳台栏杆_北", 3, -4.97, 7, -4.97, F2, M, G)
    railing("阳台栏杆_西", -6.97, 3, -6.97, 5, F2, M, G)

    # 屋顶（向海一侧多挑出 0.9m，给阳台遮阳）
    box("屋顶板", -7.2, -5.2, ROOF, 3.2, 3.9, ROOF + SLAB, M["plaster"], S)
    box("屋顶檐口", -7.2, 3.85, ROOF - 0.15, 3.2, 3.9, ROOF, M["plaster"], S)


# ---------------------------------------------------------------- 家具（全是方块，够在 VR 里建立尺度感）
def build_furniture(M):
    C = coll("家具")
    # 客厅: 沙发朝海
    box("地毯", -0.6, 0.2, F1, 4.0, 3.6, F1 + 0.015, M["rug"], C)
    box("沙发座", 0.0, 0.5, F1, 3.2, 1.4, F1 + 0.42, M["fabric"], C)
    box("沙发背", 0.0, 0.5, F1 + 0.42, 3.2, 0.75, F1 + 0.85, M["fabric"], C)
    box("沙发扶手L", -0.2, 0.5, F1, 0.0, 1.4, F1 + 0.62, M["fabric"], C)
    box("沙发扶手R", 3.2, 0.5, F1, 3.4, 1.4, F1 + 0.62, M["fabric"], C)
    for k, x in enumerate((0.4, 1.4, 2.4)):
        box(f"靠垫{k}", x, 0.78, F1 + 0.42, x + 0.45, 0.95, F1 + 0.85, M["cushion"], C)
    box("茶几", 0.8, 2.0, F1, 2.4, 2.8, F1 + 0.40, M["wood_furn"], C)
    # 厨房 + 餐厅
    box("岛台", -5.5, -2.5, F1, -2.3, -1.6, F1 + 0.88, M["wood_furn"], C)
    box("岛台面", -5.55, -2.55, F1 + 0.88, -2.25, -1.55, F1 + 0.92, M["counter"], C)
    box("靠墙橱柜", -6.8, -3.0, F1, -6.2, 1.0, F1 + 0.88, M["wood_furn"], C)
    box("橱柜台面", -6.8, -3.0, F1 + 0.88, -6.15, 1.0, F1 + 0.92, M["counter"], C)
    box("餐桌面", -5.0, 1.0, F1 + 0.72, -2.8, 2.0, F1 + 0.76, M["wood_furn"], C)
    box("餐桌腿L", -4.9, 1.1, F1, -4.8, 1.9, F1 + 0.72, M["frame"], C)
    box("餐桌腿R", -3.0, 1.1, F1, -2.9, 1.9, F1 + 0.72, M["frame"], C)
    box("长凳A", -4.9, 0.55, F1, -2.9, 0.85, F1 + 0.45, M["wood_furn"], C)
    box("长凳B", -4.9, 2.15, F1, -2.9, 2.45, F1 + 0.45, M["wood_furn"], C)
    # 二楼卧室: 床头朝北，躺着看海
    box("床架", -5.0, -1.6, F2, -3.0, 0.6, F2 + 0.30, M["wood_furn"], C)
    box("床垫", -4.95, -1.55, F2 + 0.30, -3.05, 0.55, F2 + 0.52, M["bed"], C)
    box("床头板", -5.0, -1.8, F2, -3.0, -1.6, F2 + 1.1, M["wood_furn"], C)
    for k, x in enumerate((-4.85, -3.95)):
        box(f"枕头{k}", x, -1.5, F2 + 0.52, x + 0.8, -1.05, F2 + 0.66, M["bed"], C)
    box("床头柜L", -5.6, -1.6, F2, -5.15, -1.15, F2 + 0.5, M["wood_furn"], C)
    box("床头柜R", -2.85, -1.6, F2, -2.4, -1.15, F2 + 0.5, M["wood_furn"], C)
    # 阳台躺椅 + 小桌
    for k, x in enumerate((4.2, 5.4)):
        lounger(f"阳台躺椅{k}", x, 2.6, F2, M, C)
    box("阳台小桌", 4.95, 3.3, F2, 5.25, 3.6, F2 + 0.45, M["wood_furn"], C)


def lounger(name, x, y, z, M, C):
    """躺椅: 0.7 宽 × 1.9 长，靠背朝 -Y（人面朝大海）。"""
    box(name + "_座", x, y - 0.6, z, x + 0.7, y + 1.3, z + 0.32, M["wood_furn"], C)
    box(name + "_垫", x + 0.03, y - 0.6, z + 0.32, x + 0.67, y + 1.27, z + 0.38, M["fabric"], C)
    bm = bmesh.new()   # 斜靠背: 一个楔形
    pts = [(x, y - 0.6, z + 0.38), (x + 0.7, y - 0.6, z + 0.38), (x + 0.7, y + 0.05, z + 0.38),
           (x, y + 0.05, z + 0.38), (x, y - 0.6, z + 0.95), (x + 0.7, y - 0.6, z + 0.95)]
    v = [bm.verts.new(p) for p in pts]
    for f in ((0, 1, 2, 3), (0, 4, 5, 1), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2)):
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm_obj(name + "_背", bm, M["fabric"], C)


# ---------------------------------------------------------------- 室外: 木平台、泳池、沙滩、海、椰树、远山
def build_outdoor(M):
    C = coll("室外")
    # 木平台 x -8~8, y 5~10，中间挖泳池 x 1~7, y 6~9
    for tag, r in {"前": (-8, 5, 8, 6), "后": (-8, 9, 8, 10), "左": (-8, 6, 1, 9), "右": (7, 6, 8, 9)}.items():
        box(f"木平台{tag}", r[0], r[1], 0, r[2], r[3], F1, M["deck"], C)
    box("下沙滩台阶", -3, 10, 0, 3, 10.4, 0.15, M["deck"], C)
    box("泳池池体", 1, 6, -1.2, 7, 9, 0.0, M["pooltile"], C)
    box("泳池水面", 1, 6, 0.0, 7, 9, 0.22, M["pool"], C)
    for k, x in enumerate((-2.5, -1.3)):
        lounger(f"池边躺椅{k}", x, 6.8, F1, M, C)
    # 遮阳伞
    box("伞杆", -0.65, 8.15, F1, -0.6, 8.2, F1 + 2.65, M["frame"], C)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=16, radius1=1.4, radius2=0.02, depth=0.5,
                          matrix=__import__("mathutils").Matrix.Translation((-0.625, 8.175, F1 + 2.45)))
    bm_obj("伞面", bm, M["umbrella"], C, smooth=True)

    # 沙滩: 平地 + 往海里的缓坡（海平面 z=-0.3，与坡面相交处自然形成海岸线，约 y≈33）
    mesh_obj("沙滩", [(-400, -300, 0), (400, -300, 0), (400, 30, 0), (-400, 30, 0)],
             [(0, 1, 2, 3)], M["sand"], C)
    mesh_obj("沙滩入水坡", [(-400, 30, 0), (400, 30, 0), (400, 60, -3), (-400, 60, -3)],
             [(0, 1, 2, 3)], M["sand"], C)
    # 海: 一张大平面 + 程序凹凸（不用 Ocean 修改器，VR 帧率友好）
    mesh_obj("海面", [(-3000, 25, -0.3), (3000, 25, -0.3), (3000, 3000, -0.3), (-3000, 3000, -0.3)],
             [(0, 1, 2, 3)], M["sea"], C)

    # 椰树
    for k, (x, y, tilt, yaw) in enumerate([(-11, 12, 12, 30), (-13.5, 7, 8, 160), (-7, 17, 15, 80),
                                           (10.5, 13, 10, -40), (13, 6.5, 7, 200), (16, 18, 14, -10)]):
        palm(f"椰树{k}", x, y, 6.5 + (k % 3) * 0.8, tilt, yaw, M, C)

    # 远山（房子背后 / 两侧海岬），只是压扁的球
    for k, (x, y, sx, sy, sz) in enumerate([(-60, -180, 120, 60, 28), (90, -220, 150, 70, 40),
                                            (-260, 40, 80, 120, 22), (280, 60, 90, 140, 30)]):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(x, y, -sz * 0.3), verts=bm.verts)
        bm_obj(f"远山{k}", bm, M["hill"], C, smooth=True)


def palm(name, x, y, height, tilt_deg, yaw_deg, M, C):
    from mathutils import Matrix
    # 树干: 锥体，从 z=0 到 z=height
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.22, radius2=0.13, depth=height,
                          matrix=Matrix.Translation((0, 0, height / 2)))
    trunk = bm_obj(name + "_干", bm, M["trunk"], C, smooth=True)
    # 叶冠: 9 片下垂的叶子，每片 4 段
    verts, faces = [], []
    for k in range(9):
        a = 2 * math.pi * k / 9 + 0.3 * (k % 2)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        L = 2.6 + 0.4 * (k % 3)
        base = len(verts)
        for s in range(5):
            t = s / 4
            w = 0.38 * math.sin(math.pi * (0.15 + 0.85 * t)) + 0.02
            cx, cy = dx * L * t, dy * L * t
            cz = height + 0.35 * t - 1.6 * t * t
            verts += [(cx + px * w, cy + py * w, cz), (cx - px * w, cy - py * w, cz)]
        for s in range(4):
            i = base + 2 * s
            faces.append((i, i + 1, i + 3, i + 2))
    crown = mesh_obj(name + "_叶", verts, faces, M["leaf"], C)
    for ob in (trunk, crown):
        ob.location = (x, y, 0)
        ob.rotation_euler = (math.radians(tilt_deg), 0, math.radians(yaw_deg))


# ---------------------------------------------------------------- 灯光与天空
def build_lighting():
    C = coll("灯光")
    sc = bpy.context.scene
    # 天空: 物理天空，按 Blender 版本选可用的类型
    w = bpy.data.worlds.new("海边天空")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.new("ShaderNodeTexSky")
    types = sky.bl_rna.properties["sky_type"].enum_items.keys()
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        if t in types:
            sky.sky_type = t
            break
    for prop, val in (("sun_disc", False), ("sun_elevation", math.radians(32)),
                      ("sun_rotation", math.radians(210))):
        if hasattr(sky, prop):
            setattr(sky, prop, val)
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.12 if sky.sky_type != "HOSEK_WILKIE" else 0.6

    # 太阳: 下午，从海的方向斜照进屋（窗前会有光斑）
    sun_d = bpy.data.lights.new("太阳", "SUN")
    sun_d.energy = 3.2
    sun_d.angle = math.radians(1.5)
    sun_d.color = (1.0, 0.95, 0.88)
    sun = link(bpy.data.objects.new("太阳", sun_d), C)
    sun.rotation_euler = (math.radians(58), 0, math.radians(200))

    # 室内补光（Eevee 实时 GI 有限，室内会偏暗，加几盏暖色面光）
    for k, (x, y, z, e) in enumerate([(1.5, 1.5, F2 - SLAB - 0.05, 120), (-4.0, -0.5, F2 - SLAB - 0.05, 100),
                                      (5.6, -3.6, F2 - SLAB - 0.05, 40), (-4.0, -0.5, ROOF - 0.05, 100),
                                      (0.5, -1.5, ROOF - 0.05, 80)]):
        ld = bpy.data.lights.new(f"室内灯{k}", "AREA")
        ld.energy = e
        ld.size = 1.5
        ld.color = (1.0, 0.86, 0.70)
        ob = link(bpy.data.objects.new(f"室内灯{k}", ld), C)
        ob.location = (x, y, z)

    # 渲染引擎: Eevee（VR 只能用实时引擎）
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    ev = sc.eevee
    for prop, val in (("use_shadows", True), ("use_raytracing", False),     # 光追对 VR 太贵，默认关
                      ("use_gtao", True), ("use_ssr", True), ("use_soft_shadows", True)):
        if hasattr(ev, prop):
            try:
                setattr(ev, prop, val)
            except Exception:
                pass


# ---------------------------------------------------------------- VR 点位（摄像机 + VR 插件的 Landmark）
VR_POINTS = [
    # 名字, x, y, 地面高, 朝向(度, 0 = 看 +Y 大海)
    ("01_客厅看海", 0.5, -1.2, F1, 0),
    ("02_泳池边回望", 7.6, 9.6, F1, 150),
    ("03_二楼阳台", 5.2, 4.2, F2, 10),
    ("04_卧室床边", -2.2, -2.2, F2, 20),
    ("05_楼梯口", -5.6, -3.0, F1, -90),
    ("06_沙滩回望", 3.0, 30.0, 0.0, 180),
]


def build_vr_points():
    C = coll("VR点位")
    sc = bpy.context.scene
    cams = []
    for name, x, y, floor, yaw in VR_POINTS:
        cd = bpy.data.cameras.new(name)
        cd.lens = 18                      # 广角，桌面上切相机看时接近 VR 的视野感
        cd.clip_start, cd.clip_end = 0.05, 5000
        ob = link(bpy.data.objects.new(name, cd), C)
        ob.location = (x, y, floor + EYE)
        # 相机 (90°,0,0) 时看向 +Y；VR 插件只取 Z 轴转角（自动保持水平）
        ob.rotation_euler = (math.radians(90), 0, math.radians(yaw))
        cams.append(ob)
    sc.camera = cams[0]

    # VR Scene Inspection 插件的 landmark（插件启用后在侧边栏 VR 标签里点选就能瞬移）
    try:
        import addon_utils
        addon_utils.enable("viewport_vr_preview", default_set=False)
        if hasattr(sc, "vr_landmarks"):
            sc.vr_landmarks.clear()
            for ob in cams:
                lm = sc.vr_landmarks.add()
                lm.name = ob.name
                lm.type = "OBJECT"
                lm.base_pose_object = ob
            sc.vr_landmarks_active = 0
            sc.vr_landmarks_selected = 0
    except Exception as e:  # 插件不可用时只是少了 landmark 列表，相机仍然可用
        print("[villa] VR landmarks skipped:", e)

    # VR 会话设置（保存在 .blend 里）
    try:
        xs = bpy.context.window_manager.xr_session_settings
        xs.base_pose_type = "OBJECT"
        xs.base_pose_object = cams[0]
        xs.shading.type = "RENDERED"       # 看 Eevee 实时效果；嫌卡可在 VR 标签里改成 Material/Solid
        xs.clip_start, xs.clip_end = 0.05, 5000
        xs.show_floor = False
        xs.show_annotation = False
    except Exception as e:
        print("[villa] XR session settings skipped:", e)


# ---------------------------------------------------------------- 主流程
def main():
    out = None
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args:
            out = args[0]

    # 清空默认场景（方块、灯、相机）
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0

    M = make_materials()
    build_house(M)
    build_furniture(M)
    build_outdoor(M)
    build_lighting()
    build_vr_points()

    n = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print(f"[villa] objects={len(bpy.data.objects)} faces={n}")
    if out:
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print("[villa] saved:", out)


if __name__ == "__main__":
    main()
