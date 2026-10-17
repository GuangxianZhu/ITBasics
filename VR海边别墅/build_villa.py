# -*- coding: utf-8 -*-
"""
海边二层小别墅 —— Blender 场景生成脚本（给 Quest 3 / VR Scene Inspection 用）

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_villa.py -- 输出路径.blend

坐标约定（重要，VR 尺度全靠它）:
    1 个 Blender 单位 = 1 米
    +Y 方向是大海，+Z 向上，地面（草坪）z = 0，海平面 z = -2.8（石砌海堤）
    一楼地面 z = 0.3（房子坐在 30cm 高的台基上），二楼地面 z = 3.5，屋顶 z = 6.5

兼容: Blender 3.6 ~ 5.x（只用 from_pydata / bmesh 建模，不依赖版本专有的 bpy.ops）
"""
import math
import os
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
POOL_X = (-6.0, 6.0)  # 泳池（与海平行的长条池，像 BH19）
POOL_Y = (8.5, 11.0)
POOL_FLOOR = -2.25   # 泳池底（2.4m 深: 站在池底时头也在水下，才能潜水）
POOL_WATER = 0.15    # 泳池水面（比平台低 15cm）
WALL_Y = 12.6        # 海堤内侧（栏杆所在）；海堤厚 0.8m，外侧 y=13.4 就是海
SEA_LEVEL = -2.8     # 海平面: 比平台低约 3m（照片里 BH19 是石砌海堤，海水直接拍墙）
SEABED = -7.0        # 海堤脚下的海底
BAY_C = (4.25, 5.0)  # 二楼弧形玻璃卧室（半圆）的圆心和半径
BAY_R = 2.75
BALC_Y = 7.0         # 二楼西侧弧角阳台外沿
CORNER_C = (-5.0, 5.0)  # 阳台西南圆角的圆心（半径 2）


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
    # BH19 改造新增
    M["porcelain"], _ = principled("抛光地砖", (0.84, 0.83, 0.81), 0.08)
    M["marble"], _ = principled("大理石", (0.92, 0.91, 0.89), 0.15)
    M["paving"], _ = principled("露台石材", (0.62, 0.62, 0.60), 0.7)
    M["pooltile"], _ = principled("泳池条石", (0.20, 0.32, 0.36), 0.3)
    M["seawall"], _ = principled("海堤毛石", (0.50, 0.46, 0.40), 0.9)
    M["grass"], _ = principled("草坪", (0.22, 0.36, 0.10), 0.95)
    M["asphalt"], _ = principled("沥青", (0.12, 0.12, 0.13), 0.9)
    M["forest"], _ = principled("山林", (0.10, 0.22, 0.08), 1.0)
    M["tree"], _ = principled("树冠", (0.12, 0.26, 0.09), 1.0)
    M["redroof"], _ = principled("红瓦", (0.62, 0.20, 0.12), 0.8)
    M["darkglass"], _ = principled("深色玻璃", (0.10, 0.14, 0.18), 0.1, metal=0.3)
    M["bluewall"], _ = principled("蓝墙", (0.25, 0.42, 0.78), 0.8)
    M["hull"], _ = principled("船身漆", (0.30, 0.08, 0.06), 0.6)
    M["container"], _ = principled("集装箱", (0.55, 0.35, 0.20), 0.7)
    M["rock"], _ = principled("岩石", (0.38, 0.36, 0.33), 0.85)
    M["steel"], _ = principled("不锈钢", (0.75, 0.76, 0.78), 0.25, metal=1.0)
    M["led"], b2 = principled("LED灯带", (1.0, 0.85, 0.65), 0.5)
    b2.inputs["Emission Color" if "Emission Color" in b2.inputs else "Emission"].default_value = (1.0, 0.8, 0.55, 1)
    b2.inputs["Emission Strength"].default_value = 3.0
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


def arc_pts(c, r, a0, a1, n):
    """圆弧上的点（角度制，从 +X 逆时针）。"""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def prism(name, pts, z0, z1, mat, c):
    """任意（可凹）多边形挤出成厚板 —— 弧形楼板、屋顶都用它。"""
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm_obj(name, bm, mat, c)


def strip(name, pts, z0, z1, mat, c):
    """沿折线的竖直薄面（弧形玻璃、玻璃栏板）。"""
    v = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
    n = len(pts)
    return mesh_obj(name, v, [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)], mat, c)


def tube(bm, p0, p1, r, seg=8):
    from mathutils import Matrix, Vector
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    if d.length < 1e-6:
        return
    vs = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=d.length)["verts"]
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=vs)


def railing_path(name, pts, z, M, C, closed=False):
    """沿任意折线（含圆弧）的玻璃栏板 + 不锈钢扶手。"""
    if closed:
        pts = list(pts) + [pts[0]]
    strip(name + "_玻璃", pts, z, z + 1.02, M["glass"], C)
    bm = bmesh.new()
    for a, b in zip(pts[:-1], pts[1:]):
        tube(bm, (a[0], a[1], z + 1.06), (b[0], b[1], z + 1.06), 0.025)
    bm_obj(name + "_扶手", bm, M["steel"], C, smooth=True)


def tray_ceiling(tag, floor_tag, x0, y0, x1, y1, zc, M, C):
    """吊顶: 四周下沉 22cm 的灯槽（宽 55cm），槽里一圈暖光 LED 灯带，槽底一排筒灯。
    名字 LED_<楼层>_* / 筒灯_<楼层>_* 在 Godot 里跟着该楼层的灯开关一起亮。"""
    w, d = 0.55, 0.22
    zb = zc - d
    for k, r in enumerate([(x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1), (x0, y0 + w, x0 + w, y1 - w), (x1 - w, y0 + w, x1, y1 - w)]):
        box(f"吊顶_{tag}_{k}", r[0], r[1], zb, r[2], r[3], zc, M["plaster"], C)
    bm = bmesh.new()
    i0, i1, j0, j1 = x0 + w, x1 - w, y0 + w, y1 - w
    for (a, b) in [((i0, j0), (i1, j0)), ((i0, j1), (i1, j1)), ((i0, j0), (i0, j1)), ((i1, j0), (i1, j1))]:
        cx = (a[0] + b[0]) / 2
        cy = (a[1] + b[1]) / 2
        hx = abs(b[0] - a[0]) / 2 + 0.02
        hy = abs(b[1] - a[1]) / 2 + 0.02
        from_x = cx - (hx if a[1] == b[1] else 0.02)
        to_x = cx + (hx if a[1] == b[1] else 0.02)
        from_y = cy - (hy if a[0] == b[0] else 0.02)
        to_y = cy + (hy if a[0] == b[0] else 0.02)
        vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=(to_x - from_x, to_y - from_y, 0.03), verts=vs)
        bmesh.ops.translate(bm, vec=((from_x + to_x) / 2, (from_y + to_y) / 2, zb + 0.02), verts=vs)
    bm_obj(f"LED_{floor_tag}_{tag}", bm, M["led"], C)
    bm = bmesh.new()
    from mathutils import Matrix
    for (a, b) in [((x0 + w / 2, y0 + w / 2), (x1 - w / 2, y0 + w / 2)), ((x0 + w / 2, y1 - w / 2), (x1 - w / 2, y1 - w / 2))]:
        n = max(2, int((b[0] - a[0]) / 1.2))
        for i in range(n + 1):
            x = a[0] + (b[0] - a[0]) * i / n
            bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.05, radius2=0.05, depth=0.01,
                                  matrix=Matrix.Translation((x, a[1], zb - 0.004)))
    bm_obj(f"筒灯_{floor_tag}_{tag}", bm, M["led"], C)


# ---------------------------------------------------------------- 建筑本体
def build_house(M):
    S, G = coll("结构"), coll("玻璃与栏杆")
    I = coll("吊顶灯带")

    # 台基 + 一楼抛光地砖（BH19/P185 客厅那种会反光的大砖）
    box("台基", -7, -5, 0, 7, 5, F1 - 0.01, M["concrete"], S)
    box("一楼地板", -6.8, -4.8, F1 - 0.01, 6.8, 4.8, F1, M["porcelain"], S)

    # ---------- 一楼外墙（门窗: (起, 止, 窗台, 窗顶, 玻璃?)）
    h1 = F2 - F1
    wall("一楼南墙_海景", -7, 7, 4.8, 5.0, F1, h1, [(-6.6, 6.6, 0.0, 2.9, True)], M, S, G)
    wall("一楼北墙", -7, 7, -5.0, -4.8, F1, h1,
         [(0.8, 1.8, 0.9, 2.4, True), (2.4, 3.4, 0.0, 2.3, False), (4.9, 6.4, 1.6, 2.4, True)], M, S, G)
    wall("一楼西墙", -7.0, -6.8, -4.8, 4.8, F1, h1, [(-1.0, 2.0, 1.2, 2.4, True)], M, S, G)
    wall("一楼东墙", 6.8, 7.0, -4.8, 4.8, F1, h1, [(-1.5, 3.5, 0.4, 2.6, True)], M, S, G)
    wall("卫生间隔墙A", 4.45, 4.55, -4.8, -2.5, F1, h1, [(-3.6, -2.8, 0.0, 2.1, False)], M, S, G)
    wall("卫生间隔墙B", 4.55, 6.8, -2.55, -2.45, F1, h1, [], M, S, G)

    # ---------- 楼梯（实心踏步）
    rise = (F2 - F1) / STAIR_N
    for i in range(STAIR_N - 1):
        xa = STAIR_X0 + i * STAIR_RUN
        box(f"踏步{i + 1:02d}", xa, STAIR_Y[0], F1, xa + STAIR_RUN, STAIR_Y[1],
            F1 + (i + 1) * rise, M["wood_furn"], S)

    # ---------- 二楼楼板（整层 14×10m，挖楼梯洞）
    z0, z1 = F2 - SLAB, F2 - 0.01
    hx0, hx1 = HOLE_X
    hy0, hy1 = STAIR_Y
    for tag, r in {"A": (-7, hy1, 7, 5), "B": (-7, -5, hx0, hy1),
                   "C": (hx1, -5, 7, hy1), "D": (hx0, -5, hx1, hy0)}.items():
        box(f"二楼楼板{tag}", r[0], r[1], z0, r[2], r[3], z1, M["plaster"], S)
    for tag, r in {"A": (-6.8, hy1, 6.8, 4.8), "B": (-6.8, hy0, hx0, hy1),
                   "C": (hx1, hy0, 6.8, hy1)}.items():
        box(f"二楼地板{tag}", r[0], r[1], z1, r[2], r[3], F2, M["floor"], S)

    # ---------- 二楼挑出的弧形楼板（BH19 的标志: 一层层弧形悬挑板）
    #   西侧: 阳台，外沿 y=7，西南角是半径 2m 的圆角；东侧: 半圆形玻璃卧室凸出去
    balc = [(1.5, 5.0), (1.5, BALC_Y)] + arc_pts(CORNER_C, 2.0, 90, 180, 10) + [(-7.0, 5.0)]
    prism("二楼阳台板", balc, z0, z1, M["plaster"], S)
    prism("二楼阳台面", balc, z1, F2, M["tile"], S)
    bay = arc_pts(BAY_C, BAY_R, 0, 180, 24)
    prism("二楼弧形卧室板", bay, z0, z1, M["plaster"], S)
    prism("二楼弧形卧室地板", arc_pts(BAY_C, BAY_R - 0.05, 0, 180, 24), z1, F2, M["floor"], S)
    # 一楼外廊的大理石柱（托住悬挑）
    for k, (x, y) in enumerate([(-6.2, 6.2), (-3.0, 6.7), (0.4, 6.7), (2.55, 6.7), (5.95, 6.7)]):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.17, radius2=0.17, depth=F2 - SLAB - F1,
                              matrix=__import__("mathutils").Matrix.Translation((x, y, (F1 + F2 - SLAB) / 2)))
        bm_obj(f"大理石柱{k}", bm, M["marble"], S, smooth=True)

    # ---------- 二楼墙
    h2 = ROOF - F2
    wall("二楼南墙_海景", -7, 1.45, 4.8, 5.0, F2, h2, [(-6.6, 1.3, 0.0, 2.6, True)], M, S, G)
    wall("二楼北墙", -7, 7, -5.0, -4.8, F2, h2,
         [(-6.2, -4.8, 1.0, 2.3, True), (2.6, 4.0, 1.0, 2.3, True), (5.0, 6.4, 1.0, 2.3, True)], M, S, G)
    wall("二楼西墙", -7.0, -6.8, -4.8, 4.8, F2, h2, [(2.0, 4.0, 0.9, 2.4, True)], M, S, G)
    wall("二楼东墙", 6.8, 7.0, -4.8, 5.0, F2, h2, [(-1.5, 3.0, 0.8, 2.4, True)], M, S, G)
    wall("二楼隔墙", 1.45, 1.55, -4.8, 5.0, F2, h2, [(-4.7, -3.8, 0.0, 2.1, False)], M, S, G)
    # 弧形落地玻璃（卧室 180° 海景）: 玻璃面 + 竖框 + 上下弧形框
    gp = arc_pts(BAY_C, BAY_R - 0.1, 0, 180, 24)
    strip("弧形玻璃", gp, F2 + 0.04, ROOF - 0.04, M["glass"], G)
    bm = bmesh.new()
    for i, (x, y) in enumerate(gp):
        if i % 3 == 0:
            tube(bm, (x, y, F2), (x, y, ROOF), 0.03, 6)
    for a, b in zip(gp[:-1], gp[1:]):
        tube(bm, (a[0], a[1], F2 + 0.03), (b[0], b[1], F2 + 0.03), 0.035, 6)
        tube(bm, (a[0], a[1], ROOF - 0.03), (b[0], b[1], ROOF - 0.03), 0.035, 6)
    bm_obj("弧形玻璃框", bm, M["frame"], G)

    # 楼梯洞护栏
    railing("楼梯洞护栏_长", hx0, hy1, hx1, hy1, F2, M, G)
    railing("楼梯洞护栏_端", hx0, hy0, hx0, hy1, F2, M, G)
    # 阳台弧形玻璃栏杆
    railing_path("阳台栏杆", [(1.48, 5.05), (1.48, BALC_Y - 0.05)] + arc_pts(CORNER_C, 1.95, 90, 180, 12) + [(-6.95, 5.0)],
                 F2, M, G)

    # ---------- 屋顶: 轮廓 = 二楼轮廓外扩 25cm（层层弧形挑板的效果），上面一圈玻璃栏杆（屋顶露台）
    roof = ([(-7.25, -5.25), (7.25, -5.25), (7.25, 5.0)] + arc_pts(BAY_C, BAY_R + 0.3, 0, 180, 24)[1:-1]
            + [(BAY_C[0] - BAY_R - 0.3, 5.0), (1.2, BALC_Y + 0.25)]
            + arc_pts(CORNER_C, 2.25, 90, 180, 12) + [(-7.25, 5.0)])
    prism("屋顶板", roof, ROOF, ROOF + SLAB, M["plaster"], S)
    box("屋顶女儿墙面", -7.0, -5.0, ROOF + SLAB, 7.0, 4.8, ROOF + SLAB + 0.02, M["tile"], S)
    railing_path("屋顶栏杆", roof, ROOF + SLAB, M, G, closed=True)

    # ---------- 吊顶 + LED 灯带 + 筒灯
    tray_ceiling("客厅", "一楼", -0.4, -2.3, 6.7, 4.7, F2 - SLAB, M, I)
    tray_ceiling("餐厅", "一楼", -6.7, -3.4, -0.6, 4.7, F2 - SLAB, M, I)
    tray_ceiling("卧室", "二楼", 1.7, -4.6, 6.7, 4.8, ROOF, M, I)
    tray_ceiling("娱乐室", "二楼", -6.7, -3.4, 1.3, 4.7, ROOF, M, I)


# ---------------------------------------------------------------- 家具（全是方块，够在 VR 里建立尺度感）
def build_furniture(M):
    """固定家具（橱柜、岛台、地毯）。沙发、餐桌、床等"可换成 AI 模型"的家具在 furniture_slots.py 里。"""
    C = coll("家具")
    box("地毯", -0.6, 0.2, F1, 4.0, 3.6, F1 + 0.015, M["rug"], C)
    box("岛台", -5.5, -2.5, F1, -2.3, -1.6, F1 + 0.88, M["wood_furn"], C)
    box("岛台面", -5.55, -2.55, F1 + 0.88, -2.25, -1.55, F1 + 0.92, M["marble"], C)
    box("靠墙橱柜", -6.8, -3.0, F1, -6.2, 1.0, F1 + 0.88, M["wood_furn"], C)
    box("橱柜台面", -6.8, -3.0, F1 + 0.88, -6.15, 1.0, F1 + 0.92, M["marble"], C)
    box("卧室地毯", 2.2, 1.2, F2, 6.3, 5.6, F2 + 0.012, M["rug"], C)


def lounger(name, x, y, z, M, C):
    """躺椅: 0.7 宽 × 1.9 长，靠背朝 -Y（人面朝大海）。"""
    box(name + "_座", x, y - 0.6, z, x + 0.7, y + 1.3, z + 0.32, M["wood_furn"], C)
    box(name + "_垫", x + 0.03, y - 0.6, z + 0.32, x + 0.67, y + 1.27, z + 0.38, M["fabric"], C)
    bm = bmesh.new()
    pts = [(x, y - 0.6, z + 0.38), (x + 0.7, y - 0.6, z + 0.38), (x + 0.7, y + 0.05, z + 0.38),
           (x, y + 0.05, z + 0.38), (x, y - 0.6, z + 0.95), (x + 0.7, y - 0.6, z + 0.95)]
    v = [bm.verts.new(p) for p in pts]
    for f in ((0, 1, 2, 3), (0, 4, 5, 1), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2)):
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm_obj(name + "_背", bm, M["fabric"], C)


# ---------------------------------------------------------------- 室外: BH19 式海堤地块
def ground_with_hole(name, xa, ya, xb, yb, z, hole, mat, c):
    """一块平地，中间挖一个矩形洞（给空心泳池用）。"""
    hx0, hy0, hx1, hy1 = hole
    sv, sf = [], []
    for (a0, b0, a1, b1) in [(xa, ya, xb, hy0), (xa, hy1, xb, yb), (xa, hy0, hx0, hy1), (hx1, hy0, xb, hy1)]:
        i = len(sv)
        sv += [(a0, b0, z), (a1, b0, z), (a1, b1, z), (a0, b1, z)]
        sf.append((i, i + 1, i + 2, i + 3))
    return mesh_obj(name, sv, sf, mat, c)


def building(name, x0, y0, x1, y1, floors, fh, wall_m, glass_m, c, balcony=False):
    """邻居楼: 每层 = 一圈实墙带 + 一圈内缩的玻璃带（远看就是一层层的窗）。"""
    bw = bmesh.new()
    bg = bmesh.new()
    from mathutils import Matrix

    def cube(bm, a, b):
        vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=(b[0] - a[0], b[1] - a[1], b[2] - a[2]), verts=vs)
        bmesh.ops.translate(bm, vec=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2), verts=vs)
    for f in range(floors):
        z = f * fh
        cube(bw, (x0, y0, z), (x1, y1, z + fh * 0.35))
        cube(bg, (x0 + 0.15, y0 + 0.15, z + fh * 0.35), (x1 - 0.15, y1 - 0.15, z + fh))
        if balcony:
            cube(bw, (x0 + 0.5, y1, z + fh * 0.3), (x1 - 0.5, y1 + 1.2, z + fh * 0.35))
    cube(bw, (x0 - 0.2, y0 - 0.2, floors * fh), (x1 + 0.2, y1 + 0.2, floors * fh + 0.6))
    bm_obj(name + "_墙", bw, wall_m, c)
    bm_obj(name + "_窗", bg, glass_m, c)


def build_site(M):
    from mathutils import Matrix
    C = coll("室外")
    rnd = __import__("random").Random(7)
    px0, px1 = POOL_X
    py0, py1 = POOL_Y

    # 地面: 草坪（在泳池处留洞），后面一条马路
    ground_with_hole("草地", -400, -14, 400, WALL_Y, 0.0, (px0, py0, px1, py1), M["grass"], C)
    mesh_obj("马路", [(-400, -20, 0.01), (400, -20, 0.01), (400, -14, 0.01), (-400, -14, 0.01)],
             [(0, 1, 2, 3)], M["asphalt"], C)
    # 平台（石材，z 0~0.3）: 房前外廊 + 泳池四周 + 海边步道，中间挖泳池
    for tag, r in {"前": (-9, 5, 9, py0), "后": (-9, py1, 9, WALL_Y), "左": (-9, py0, px0, py1), "右": (px1, py0, 9, py1),
                   "东侧": (9, 5, 15, WALL_Y)}.items():
        box(f"平台{tag}", r[0], r[1], 0, r[2], r[3], F1, M["paving"], C)
    box("侧院步道", 7, -5, 0, 9, 5, F1, M["paving"], C)
    # 泳池: 深 2.4m，池壁和池底铺深蓝灰条石；东头 7 级入水台阶
    box("泳池池底", px0, py0, POOL_FLOOR - 0.1, px1, py1, POOL_FLOOR, M["pooltile"], C)
    for tag, r in {"西": (px0 - 0.2, py0 - 0.2, px0, py1 + 0.2), "东": (px1, py0 - 0.2, px1 + 0.2, py1 + 0.2),
                   "南": (px0, py0 - 0.2, px1, py0), "北": (px0, py1, px1, py1 + 0.2)}.items():
        box(f"泳池壁{tag}", r[0], r[1], POOL_FLOOR - 0.1, r[2], r[3], 0.0, M["pooltile"], C)
    for i in range(7):
        box(f"泳池台阶{i}", px1 - 0.3 * (i + 1), py0, POOL_FLOOR, px1 - 0.3 * i, py0 + 0.9,
            -0.02 - 0.32 * i, M["pooltile"], C)
    mesh_obj("泳池水面", [(px0, py0, POOL_WATER), (px1, py0, POOL_WATER), (px1, py1, POOL_WATER), (px0, py1, POOL_WATER)],
             [(0, 1, 2, 3)], M["pool"], C)

    # 海堤: 石砌，从海底到平台面；顶上压一道石材压顶；外侧就是海
    for tag, (xa, xb) in {"西": (-70, 7.0), "东": (8.2, 70)}.items():       # 下水台阶处断开
        box(f"海堤{tag}", xa, WALL_Y, SEABED, xb, WALL_Y + 0.8, F1, M["seawall"], C)
        box(f"海堤压顶{tag}", xa, WALL_Y - 0.05, F1, xb, WALL_Y + 0.85, F1 + 0.08, M["paving"], C)
    mesh_obj("海底", [(-600, WALL_Y + 0.8, SEABED), (600, WALL_Y + 0.8, SEABED), (600, 3000, SEABED), (-600, 3000, SEABED)],
             [(0, 1, 2, 3)], M["sand"], C)
    mesh_obj("海面", [(-3000, WALL_Y + 0.8, SEA_LEVEL), (3000, WALL_Y + 0.8, SEA_LEVEL), (3000, 3000, SEA_LEVEL),
                     (-3000, 3000, SEA_LEVEL)], [(0, 1, 2, 3)], M["sea"], C)
    # 海边步道的玻璃栏杆（在 x 7~8.2 留口，下水台阶从这里下去）
    railing_path("海边栏杆西", [(-9.0, WALL_Y - 0.03), (7.0, WALL_Y - 0.03)], F1 + 0.08, M, C)
    railing_path("海边栏杆东", [(8.2, WALL_Y - 0.03), (15.0, WALL_Y - 0.03)], F1 + 0.08, M, C)
    # 下水台阶: 从平台一直下到水面以下 1.4m（游泳的人能踩着上来），每级 30cm
    for i in range(15):
        y0 = WALL_Y + 0.3 * i
        top = F1 - 0.3 * (i + 1)
        box(f"下水台阶{i:02d}", 7.0, y0, SEABED, 8.2, y0 + 0.3, top, M["seawall"], C)
    for x in (6.8, 8.2):
        box(f"下水台阶侧墙{x}", x, WALL_Y + 0.8, SEABED, x + 0.2, WALL_Y + 4.5, -2.4, M["seawall"], C)
    # 堤脚抛石（一半露出水面，浪拍在上面）
    for k in range(80):
        x = rnd.uniform(-68, 68)
        if 5.5 < x < 9.5:
            continue
        y = WALL_Y + 0.8 + rnd.uniform(0.3, 2.8)
        s = rnd.uniform(0.6, 1.6)
        rock_mesh(f"堤脚石{k}", x, y, SEA_LEVEL - rnd.uniform(0.2, 0.9), s * 1.3, s, s * 0.7, 500 + k, M["rock"], C)

    # 院墙（白色）+ 东侧烧烤凉亭
    for x in (-10.2, 15.2):
        box(f"院墙{x}", x, -9, 0, x + 0.2, WALL_Y, 1.8, M["plaster"], C)
    box("院墙后", -10.2, -9.2, 0, 15.4, -9.0, 1.8, M["plaster"], C)
    for k, (x, y) in enumerate([(10.8, 8.0), (13.8, 8.0), (10.8, 11.0), (13.8, 11.0)]):
        box(f"凉亭柱{k}", x - 0.1, y - 0.1, F1, x + 0.1, y + 0.1, F1 + 2.6, M["plaster"], C)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=2.6, radius2=0.05, depth=1.1,
                          matrix=Matrix.Translation((12.3, 9.5, F1 + 3.15)) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    bm_obj("凉亭顶", bm, M["plaster"], C)
    box("凉亭顶梁", 10.6, 7.8, F1 + 2.6, 14.0, 11.2, F1 + 2.62, M["plaster"], C)
    box("烧烤台", 12.6, 10.4, F1, 14.2, 11.0, F1 + 0.88, M["paving"], C)
    box("凉亭长桌", 10.9, 8.9, F1 + 0.72, 12.6, 9.9, F1 + 0.76, M["wood_furn"], C)

    # 花园: 椰树 + 观赏草
    for k, (x, y, tilt, yaw) in enumerate([(-8.6, 2.0, 8, 30), (-8.8, -3.5, 5, 160), (9.8, 3.0, 9, -40),
                                           (14.0, 1.5, 7, 200), (10.0, -5.0, 6, 80), (14.2, -6.0, 10, -10),
                                           (-8.5, 9.5, 12, 60), (16.5, 11.5, 14, -60)]):
        palm(f"椰树{k}", x, y, 6.5 + (k % 3) * 0.8, tilt, yaw, M, C)
    verts, faces = [], []
    for k in range(60):
        cx, cy = rnd.choice([(rnd.uniform(-9.8, -7.4), rnd.uniform(-8.5, 4.5)), (rnd.uniform(9.3, 14.8), rnd.uniform(-8.5, 4.5)),
                             (rnd.uniform(-9, 14), rnd.uniform(-8.8, -6.0))])
        for b in range(9):
            a = rnd.uniform(0, 6.28)
            hgt = rnd.uniform(0.35, 0.8)
            lean = rnd.uniform(0.1, 0.35)
            dx, dy = math.cos(a), math.sin(a)
            i = len(verts)
            verts += [(cx - dy * 0.015, cy + dx * 0.015, 0), (cx + dy * 0.015, cy - dx * 0.015, 0),
                      (cx + dx * lean, cy + dy * lean, hgt)]
            faces.append((i, i + 1, i + 2))
    mesh_obj("沙草", verts, faces, M["leaf"], C)

    # 屋后的山坡（照片里 BH19 背后是长满树的山）: 高度场网格 + 一团团树冠
    N_X, N_Y = 100, 50
    def hill_z(x, y):
        t = max(0.0, -y - 22.0)
        base = t * 0.32 * (0.75 + 0.25 * math.sin(x * 0.013 + 1.0)) - 0.0004 * x * x * min(1.0, t / 60)
        bump = 3.0 * math.sin(x * 0.07) * math.sin(y * 0.09) + 1.5 * math.sin(x * 0.17 + y * 0.11)
        return max(0.0, base + bump * min(1.0, t / 15.0))
    hv, hf = [], []
    for j in range(N_Y + 1):
        y = -18 - j * 6.0
        for i in range(N_X + 1):
            x = -300 + i * 6.0
            hv.append((x, y, hill_z(x, y)))
    for j in range(N_Y):
        for i in range(N_X):
            a = j * (N_X + 1) + i
            hf.append((a, a + N_X + 1, a + N_X + 2, a + 1))
    mesh_obj("山坡", hv, hf, M["forest"], C, smooth=True)
    tv, tf = [], []
    for k in range(700):
        x = rnd.uniform(-260, 260)
        y = rnd.uniform(-30, -280)
        if abs(x) < 45 and y > -45:
            continue
        r = rnd.uniform(2.0, 4.5)
        z = hill_z(x, y) + r * 0.6
        i0 = len(tv)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r)
        bmesh.ops.scale(bm, vec=(1, 1, 0.8), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(x, y, z), verts=bm.verts)
        tv += [tuple(v.co) for v in bm.verts]
        tf += [tuple(i0 + v.index for v in f.verts) for f in bm.faces]
        bm.free()
    mesh_obj("山上树木", tv, tf, M["tree"], C)
    # 山脚的小房子（白墙红瓦）
    for k, (x, y) in enumerate([(-40, -26), (-28, -30), (24, -27), (36, -24), (52, -31), (-55, -28), (8, -34)]):
        z = hill_z(x, y)
        box(f"山脚房子{k}", x - 4, y - 3, z - 1, x + 4, y + 3, z + 5.5, M["plaster"], C)
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=6.2, radius2=0.1, depth=2.2,
                              matrix=Matrix.Rotation(math.pi / 4, 4, "Z"))
        bmesh.ops.scale(bm, vec=(1.0, 0.75, 1.0), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(x, y, z + 6.6), verts=bm.verts)
        bm_obj(f"山脚房子{k}_屋顶", bm, M["redroof"], C)

    # 邻居: 左边一栋酒店高楼、一栋白色别墅；右边蓝色公寓楼、红瓦房
    building("邻居酒店", -40, -12, -24, 2, 18, 3.1, M["plaster"], M["darkglass"], C, balcony=True)
    building("邻居白别墅", -22, -4, -12, 6, 2, 3.4, M["plaster"], M["darkglass"], C)
    building("邻居蓝楼", 19, -6, 29, 5, 5, 3.2, M["bluewall"], M["darkglass"], C, balcony=True)
    box("邻居红瓦房", 31, -2, 0, 39, 6, 6.0, M["plaster"], C)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=6.4, radius2=0.1, depth=2.6,
                          matrix=Matrix.Translation((35, 2, 7.3)) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    bm_obj("邻居红瓦房_屋顶", bm, M["redroof"], C)
    for x0, x1 in ((-70, -10.4), (15.4, 70)):            # 邻居家的海边围栏（白色矮墙）
        box(f"邻居海边矮墙{x0}", x0, WALL_Y - 0.25, F1, x1, WALL_Y, F1 + 0.9, M["plaster"], C)

    # 远处: 海湾对面的山和城市、海平线上停着的货轮
    for k, (x, y, sx, sy, sz) in enumerate([(-700, 900, 420, 160, 80), (-260, 1100, 300, 140, 45),
                                            (650, 1300, 500, 200, 95), (-1400, 600, 500, 300, 120)]):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=14, radius=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(x, y, -sz * 0.25), verts=bm.verts)
        bm_obj(f"远山{k}", bm, M["hill"], C, smooth=True)
    bc = bmesh.new()
    for k in range(90):
        x = rnd.uniform(-900, -450)
        y = rnd.uniform(700, 780)
        w, d, h = rnd.uniform(15, 40), rnd.uniform(15, 30), rnd.uniform(10, 60)
        vs = bmesh.ops.create_cube(bc, size=1.0)["verts"]
        bmesh.ops.scale(bc, vec=(w, d, h), verts=vs)
        bmesh.ops.translate(bc, vec=(x, y, h / 2), verts=vs)
    bm_obj("对岸城市", bc, M["plaster"], C)
    for k, (x, y, yaw) in enumerate([(-300, 900, 10), (200, 1500, -20), (650, 1100, 5), (-750, 1700, 30),
                                     (1100, 1900, -10), (-60, 2300, 0), (420, 650, 15)]):
        ship(f"货轮{k}", x, y, yaw, M, C, rnd)


def rock_mesh(name, x, y, z, sx, sy, sz, seed, mat, c):
    """礁石: 二十面体细分后按伪随机噪声沿法线推拉，再压扁。"""
    import random as _r
    from mathutils import Matrix
    rnd = _r.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    k = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(1.5, 3.5)) for _ in range(6)]
    for v in bm.verts:
        n = v.co.normalized()
        d = sum(0.12 * math.sin(f * (n.x * a + n.y * b + n.z * cc) + i) for i, (a, b, cc, f) in enumerate(k))
        v.co = n * (1.0 + d)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rnd.uniform(0, 6.3), 3, "Z"))
    bmesh.ops.translate(bm, vec=(x, y, z), verts=bm.verts)
    return bm_obj(name, bm, mat, c)


def ship(name, x, y, yaw, M, C, rnd):
    """货轮: 船身 + 船尾白色上层建筑 + 甲板上一排彩色集装箱（几百米外看，轮廓对就像）。"""
    from mathutils import Matrix
    L, B = rnd.uniform(140, 220), rnd.uniform(22, 32)
    bh = bmesh.new()
    vs = bmesh.ops.create_cube(bh, size=1.0)["verts"]
    bmesh.ops.scale(bh, vec=(B, L, 12), verts=vs)
    bmesh.ops.translate(bh, vec=(0, 0, SEA_LEVEL + 3), verts=vs)
    vs = bmesh.ops.create_cube(bh, size=1.0)["verts"]                 # 船头尖一点
    bmesh.ops.scale(bh, vec=(B * 0.7, 12, 10), verts=vs)
    bmesh.ops.translate(bh, vec=(0, L / 2 + 5, SEA_LEVEL + 4), verts=vs)
    bs = bmesh.new()
    vs = bmesh.ops.create_cube(bs, size=1.0)["verts"]
    bmesh.ops.scale(bs, vec=(B * 0.8, 14, 18), verts=vs)
    bmesh.ops.translate(bs, vec=(0, -L / 2 + 10, SEA_LEVEL + 18), verts=vs)
    bk = bmesh.new()
    for i in range(int(L / 16)):
        vs = bmesh.ops.create_cube(bk, size=1.0)["verts"]
        bmesh.ops.scale(bk, vec=(B * 0.85, 13, rnd.choice([5, 8, 10])), verts=vs)
        bmesh.ops.translate(bk, vec=(0, -L / 2 + 25 + i * 15, SEA_LEVEL + 11), verts=vs)
    mat = Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    for bm, part, m in ((bh, "船身", M["hull"]), (bs, "舱楼", M["plaster"]), (bk, "集装箱", M["container"])):
        bmesh.ops.transform(bm, matrix=mat, verts=bm.verts)
        bm_obj(f"{name}_{part}", bm, m, C)


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
    ("02_海边步道回望", 4.0, 11.9, F1, 165),
    ("03_二楼阳台", -2.0, 6.0, F2, 10),
    ("04_弧形卧室", 4.25, 1.5, F2, 0),
    ("05_楼梯口", -5.6, -3.0, F1, -90),
    ("06_下水台阶", 7.6, 14.1, F1 - 1.5, 175),
    ("07_烧烤凉亭", 11.5, 8.4, F1, -40),
    ("08_台球KTV室", -0.5, -0.5, F2, -60),
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
    build_site(M)
    # 陈设和室外扩展在单独的文件里（scene_extras.py），这里注入本模块的工具函数给它用
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import scene_extras
    scene_extras.build(M, sys.modules[__name__])
    import furniture_slots                      # 沙发、床、台球桌…: 有 AI 模型用 AI 的，没有用占位
    furniture_slots.build(M, sys.modules[__name__])
    build_lighting()
    build_vr_points()

    n = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print(f"[villa] objects={len(bpy.data.objects)} faces={n}")
    if out:
        bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
        print("[villa] saved:", out)


if __name__ == "__main__":
    main()
