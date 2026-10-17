# -*- coding: utf-8 -*-
"""
场景丰富化: 室内陈设 + 室外扩展。由 build_villa.main() 调用（Blender 版和 Godot 版共用）。

坐标仍是 Blender 约定: 1 单位 = 1 米, +Y = 大海, +Z = 上。

Godot 版靠"物体名字"识别可交互的东西（名字就是接口，改名要同步改 godot/*.gd）:
    冰箱门 / 冰箱内壁      冰箱门绕铰链开合，开门时内壁亮
    收音机                 开关音乐（3D 声源）
    电视 / 电视屏幕         开关电视（屏幕是会动的着色器）
    吊扇叶                 开关吊扇
    窗帘_*                 随风摆动（阳台门开着时摆得更厉害）
    小船_*                 跟着海浪起伏
    灯塔灯位（空物体）       夜里转动的光束
    篝火柴堆 / 篝火位       点燃 / 熄灭篝火
    名字含 "座" 的椅面      坐下
    可拿_*（空物体）        Godot 在这里生成能抓起来扔的东西（沙滩球、椰子、杯子）
    吊灯_*_罩 / 落地灯罩    跟着一楼灯开关一起发光
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

V = None   # build_villa 模块（main 里注入，避免循环 import）


# ===================================================================== bmesh 小工具
def add_box(bm, x0, y0, z0, x1, y1, z1):
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r["verts"]
    bmesh.ops.scale(bm, vec=(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), verts=vs)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=vs)
    return vs


def add_cyl(bm, x, y, z0, z1, r0, r1=None, seg=16, caps=True):
    r1 = r0 if r1 is None else r1
    res = bmesh.ops.create_cone(bm, cap_ends=caps, segments=seg, radius1=r0, radius2=r1, depth=z1 - z0,
                                matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))
    return res["verts"]


def cyl(name, x, y, z0, z1, r0, mat, c, r1=None, seg=16, smooth=True):
    bm = bmesh.new()
    add_cyl(bm, x, y, z0, z1, r0, r1, seg)
    return V.bm_obj(name, bm, mat, c, smooth=smooth)


def log(bm, p0, p1, r, seg=10):
    """两点之间的圆柱（原木、栏杆）。"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    vs = add_cyl(bm, 0, 0, -d.length / 2, d.length / 2, r, seg=seg)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=vs)


def quad_uv(name, corners, mat, c):
    """带 UV 的四边形（画布、电视屏幕需要正确的贴图坐标）。corners 顺序: 左下、右下、右上、左上（从正面看）。"""
    me = bpy.data.meshes.new(name)
    me.from_pydata(corners, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = (u, v)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    return ob


def empty(name, x, y, z, c):
    e = bpy.data.objects.new(name, None)
    e.location = (x, y, z)
    c.objects.link(e)
    return e


def rock(name, x, y, z, sx, sy, sz, seed, mat, c):
    """礁石: 二十面体细分后按伪随机噪声沿法线推拉，再压扁。"""
    rnd = random.Random(seed)
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
    return V.bm_obj(name, bm, mat, c, smooth=False)


def plant(name, x, y, z, height, M, c, seed):
    """盆栽: 陶土盆 + 一圈向上再外翻的叶片。"""
    rnd = random.Random(seed)
    cyl(name + "_盆", x, y, z, z + 0.42, 0.2, M["pot"], c, r1=0.25)
    verts, faces = [], []
    for k in range(14):
        a = rnd.uniform(0, 6.283)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        L = height * rnd.uniform(0.6, 1.0)
        lean = rnd.uniform(0.25, 0.6)
        base = len(verts)
        for s in range(6):
            t = s / 5
            w = 0.07 * math.sin(math.pi * (0.1 + 0.9 * t)) + 0.005
            r_out = lean * L * t * t
            cx, cy = x + dx * r_out, y + dy * r_out
            cz = z + 0.4 + L * math.sin(t * 1.3) * 0.9
            verts += [(cx + px * w, cy + py * w, cz), (cx - px * w, cy - py * w, cz)]
        for s in range(5):
            i = base + 2 * s
            faces.append((i, i + 1, i + 3, i + 2))
    V.mesh_obj(name + "_叶", verts, faces, M["plantleaf"], c)


# ===================================================================== 材质
def materials(M):
    P = V.principled
    M["metal"], _ = P("不锈钢", (0.75, 0.76, 0.78), 0.25, metal=1.0)
    M["fridge"], _ = P("冰箱白", (0.92, 0.92, 0.91), 0.3)
    M["fridge_in"], _ = P("冰箱内壁", (0.95, 0.97, 1.0), 0.4)
    M["ceramic"], _ = P("陶瓷", (0.96, 0.96, 0.95), 0.1)
    M["screen"], _ = P("电视屏幕", (0.01, 0.01, 0.012), 0.08)
    M["tv"], _ = P("电视外壳", (0.03, 0.03, 0.035), 0.4)
    M["pot"], _ = P("花盆", (0.62, 0.33, 0.22), 0.8)
    M["plantleaf"], _ = P("绿植叶", (0.10, 0.32, 0.12), 0.5)
    M["rock"], _ = P("岩石", (0.38, 0.36, 0.33), 0.85)
    M["grass"], _ = P("海岬草地", (0.22, 0.34, 0.15), 0.95)
    M["lh_white"], _ = P("灯塔白", (0.92, 0.91, 0.88), 0.6)
    M["lh_red"], _ = P("灯塔红", (0.62, 0.08, 0.06), 0.6)
    M["lh_glass"], _ = P("灯室玻璃", (0.95, 0.92, 0.70), 0.05)
    M["boat"], _ = P("船身", (0.88, 0.86, 0.80), 0.5)
    M["boat_trim"], _ = P("船沿", (0.10, 0.25, 0.45), 0.5)
    M["shade"], _ = P("灯罩", (0.95, 0.90, 0.78), 0.9)
    M["towel_a"], _ = P("浴巾条纹", (0.85, 0.35, 0.25), 0.95)
    M["towel_b"], _ = P("浴巾蓝", (0.20, 0.45, 0.70), 0.95)
    M["curtain"], _ = P("窗帘", (0.93, 0.90, 0.84), 0.95)
    M["charred"], _ = P("烧焦木", (0.08, 0.06, 0.05), 0.9)
    for k, col in enumerate([(0.55, 0.12, 0.10), (0.12, 0.25, 0.45), (0.18, 0.38, 0.22), (0.80, 0.72, 0.55)]):
        M[f"book{k}"], _ = P(f"书{k}", col, 0.7)
    for k in range(3):
        M[f"canvas{k}"], _ = P(f"画布_{k}", (0.7, 0.7, 0.7), 0.8)


# ===================================================================== 室内
def interior(M):
    C = V.coll("陈设")
    F1, F2, ROOF, SLAB = V.F1, V.F2, V.ROOF, V.SLAB
    box = V.box

    # ---- 厨房: 冰箱（门可开）、水槽、灶台、吊灯、吧凳
    box("冰箱", -6.80, -4.78, F1, -6.13, -4.05, F1 + 1.85, M["fridge"], C)
    box("冰箱内壁", -6.13, -4.74, F1 + 0.05, -6.125, -4.09, F1 + 1.80, M["fridge_in"], C)
    for k, z in enumerate((0.55, 1.0, 1.4)):
        box(f"冰箱隔板{k}", -6.30, -4.74, F1 + z, -6.124, -4.09, F1 + z + 0.015, M["glass"], C)
    for k, (y, z, col) in enumerate([(-4.6, 0.57, "book0"), (-4.3, 0.57, "book2"), (-4.5, 1.02, "book3"),
                                     (-4.25, 1.42, "book1")]):
        box(f"冰箱食材{k}", -6.30, y, F1 + z, -6.18, y + 0.14, F1 + z + 0.18, M[col], C)
    box("冰箱门", -6.13, -4.78, F1 + 0.02, -6.07, -4.05, F1 + 1.83, M["fridge"], C)
    box("冰箱门_把手", -6.07, -4.18, F1 + 0.9, -6.04, -4.15, F1 + 1.5, M["metal"], C)
    top = F1 + 0.92
    box("水槽", -6.70, -1.6, top - 0.18, -6.25, -0.9, top + 0.002, M["metal"], C)
    bm = bmesh.new()
    add_cyl(bm, -6.72, -1.25, top, top + 0.32, 0.015)
    add_box(bm, -6.72, -1.265, top + 0.30, -6.48, -1.235, top + 0.33)
    V.bm_obj("水龙头", bm, M["metal"], C)
    box("灶台", -4.40, -2.40, F1 + 0.92, -3.70, -1.70, F1 + 0.925, M["screen"], C)
    for k, x in enumerate((-5.0, -3.9, -2.8)):
        bm = bmesh.new()
        add_cyl(bm, x, -2.05, F2 - SLAB - 0.9, F2 - SLAB, 0.004)
        V.bm_obj(f"吊灯_{k}_线", bm, M["frame"], C)
        cyl(f"吊灯_{k}_罩", x, -2.05, F2 - SLAB - 1.15, F2 - SLAB - 0.9, 0.18, M["shade"], C, r1=0.05)
        bm = bmesh.new()
        add_cyl(bm, x, -1.30, F1, F1 + 0.70, 0.025)
        add_cyl(bm, x, -1.30, F1, F1 + 0.02, 0.18)
        V.bm_obj(f"吧凳{k}_腿", bm, M["metal"], C)
        cyl(f"吧凳{k}_座", x, -1.30, F1 + 0.70, F1 + 0.76, 0.19, M["wood_furn"], C)
    # 餐桌上: 花瓶 + 果盘
    cyl("花瓶", -4.2, 1.5, F1 + 0.76, F1 + 1.05, 0.06, M["ceramic"], C, r1=0.04)
    cyl("果盘", -3.5, 1.5, F1 + 0.76, F1 + 0.82, 0.16, M["wood_furn"], C, r1=0.2)

    # ---- 客厅: 边柜 + 收音机、落地灯、书架、绿植、电视角
    box("边柜", 0.2, -0.05, F1, 3.0, 0.40, F1 + 0.75, M["wood_furn"], C)
    box("收音机", 2.30, 0.05, F1 + 0.75, 2.68, 0.27, F1 + 0.95, M["wood_furn"], C)
    box("收音机_喇叭", 2.34, 0.04, F1 + 0.78, 2.52, 0.05, F1 + 0.92, M["fabric"], C)
    cyl("收音机_旋钮", 2.60, 0.045, F1 + 0.84, F1 + 0.87, 0.02, M["metal"], C)
    cyl("边柜陶碗", 0.7, 0.18, F1 + 0.75, F1 + 0.85, 0.11, M["ceramic"], C, r1=0.15)
    bm = bmesh.new()
    add_cyl(bm, 3.85, 0.9, F1, F1 + 0.03, 0.18)
    add_cyl(bm, 3.85, 0.9, F1, F1 + 1.45, 0.012)
    V.bm_obj("落地灯杆", bm, M["frame"], C)
    cyl("落地灯罩", 3.85, 0.9, F1 + 1.4, F1 + 1.68, 0.22, M["shade"], C, r1=0.16)
    # 书架（西墙，窗户以南）+ 书
    box("书架", -6.80, 2.25, F1, -6.45, 4.45, F1 + 2.1, M["wood_furn"], C)
    rnd = random.Random(7)
    groups = {k: bmesh.new() for k in range(4)}
    for s, zs in enumerate((0.05, 0.47, 0.89, 1.31, 1.73)):
        y = 2.30
        while y < 4.35:
            w = rnd.uniform(0.025, 0.055)
            h = rnd.uniform(0.2, 0.32)
            if rnd.random() < 0.08:
                y += rnd.uniform(0.1, 0.25)        # 留空
                continue
            add_box(groups[rnd.randrange(4)], -6.44, y, F1 + zs, -6.44 + rnd.uniform(0.17, 0.22), y + w, F1 + zs + h)
            y += w + 0.002
    for k, g in groups.items():
        V.bm_obj(f"书_{k}", g, M[f"book{k}"], C)
    for k, z in enumerate((0.45, 0.87, 1.29, 1.71)):
        box(f"书架隔板{k}", -6.45, 2.25, F1 + z, -6.10, 4.45, F1 + z + 0.02, M["wood_furn"], C)
    for k, (x, y) in enumerate([(6.25, 4.25), (-6.1, 4.55), (-3.2, 4.4)]):
        plant(f"大盆栽{k}", x, y, F1, 1.3, M, C, 10 + k)
    # 电视角: 电视挂在卫生间外墙上，对面一张单人沙发
    box("电视", 5.00, -2.45, F1 + 0.95, 6.40, -2.40, F1 + 1.75, M["tv"], C)
    # 注意顶点顺序决定正面朝向: 从观看者角度"左下→右下→右上→左上"（这面墙朝 +y，观看者面朝 -y，所以 x 从大到小）
    quad_uv("电视屏幕", [(6.36, -2.395, F1 + 0.99), (5.04, -2.395, F1 + 0.99),
                     (5.04, -2.395, F1 + 1.71), (6.36, -2.395, F1 + 1.71)], M["screen"], C)
    box("电视柜", 4.9, -2.45, F1, 6.5, -2.05, F1 + 0.4, M["wood_furn"], C)
    box("单人沙发_座", 5.25, 0.15, F1, 6.15, 1.05, F1 + 0.42, M["fabric"], C)
    box("单人沙发_背", 5.25, 0.80, F1 + 0.42, 6.15, 1.05, F1 + 0.95, M["fabric"], C)
    box("单人沙发_扶手L", 5.10, 0.15, F1, 5.25, 1.05, F1 + 0.62, M["fabric"], C)
    box("单人沙发_扶手R", 6.15, 0.15, F1, 6.30, 1.05, F1 + 0.62, M["fabric"], C)
    box("电视角地毯", 4.9, -1.6, F1, 6.6, 1.3, F1 + 0.012, M["rug"], C)
    # 画（一楼北墙 冰箱和楼梯之间）
    quad_uv("画_1", [(-4.95, -4.785, F1 + 1.1), (-5.7, -4.785, F1 + 1.1),
                    (-5.7, -4.785, F1 + 2.1), (-4.95, -4.785, F1 + 2.1)], M["canvas1"], C)
    box("画框_1", -5.74, -4.80, F1 + 1.06, -4.91, -4.79, F1 + 2.14, M["frame"], C)

    # ---- 卫生间
    box("马桶_水箱", 6.10, -4.78, F1 + 0.40, 6.55, -4.58, F1 + 0.80, M["ceramic"], C)
    cyl("马桶", 6.32, -4.30, F1, F1 + 0.42, 0.2, M["ceramic"], C, r1=0.22)
    box("洗手台", 4.62, -4.78, F1 + 0.75, 5.45, -4.30, F1 + 0.88, M["counter"], C)
    box("洗手台柜", 4.65, -4.75, F1, 5.42, -4.33, F1 + 0.75, M["wood_furn"], C)
    cyl("洗手盆", 5.03, -4.55, F1 + 0.88, F1 + 1.0, 0.2, M["ceramic"], C, r1=0.16)
    box("浴室镜", 4.70, -4.79, F1 + 1.15, 5.38, -4.78, F1 + 1.95, M["metal"], C)
    box("淋浴玻璃", 5.95, -3.42, F1, 5.97, -2.55, F1 + 2.1, M["glass"], C)
    box("淋浴底盘", 5.97, -3.42, F1, 6.80, -2.55, F1 + 0.03, M["ceramic"], C)
    cyl("花洒", 6.5, -3.0, F1 + 2.05, F1 + 2.08, 0.12, M["metal"], C)

    # ---- 二楼卧室: 衣柜、书桌、吊扇、窗帘、地毯、绿植、画
    box("衣柜", -6.80, -4.70, F2, -6.20, -2.40, F2 + 2.2, M["wood_furn"], C)
    box("衣柜缝", -6.199, -3.56, F2 + 0.05, -6.195, -3.54, F2 + 2.15, M["frame"], C)
    box("卧室地毯", -5.8, -1.0, F2, -2.2, 1.6, F2 + 0.012, M["rug"], C)
    box("书桌", 2.0, 0.6, F2 + 0.72, 2.75, 2.0, F2 + 0.76, M["wood_furn"], C)
    for k, (x, y) in enumerate([(2.05, 0.65), (2.65, 0.65), (2.05, 1.9), (2.65, 1.9)]):
        box(f"书桌腿{k}", x, y, F2, x + 0.05, y + 0.05, F2 + 0.72, M["frame"], C)
    box("书桌椅_座", 1.40, 1.05, F2 + 0.45, 1.85, 1.50, F2 + 0.50, M["wood_furn"], C)
    box("书桌椅_背", 1.40, 1.05, F2 + 0.50, 1.45, 1.50, F2 + 0.95, M["wood_furn"], C)
    box("书桌椅_腿", 1.58, 1.23, F2, 1.67, 1.32, F2 + 0.45, M["frame"], C)
    cyl("台灯罩", 2.5, 1.7, F2 + 1.05, F2 + 1.2, 0.12, M["shade"], C, r1=0.08)
    box("台灯杆", 2.49, 1.69, F2 + 0.76, 2.51, 1.71, F2 + 1.05, M["frame"], C)
    cyl("吊扇电机", -4.0, -0.6, ROOF - 0.45, ROOF, 0.09, M["frame"], C)
    bm = bmesh.new()
    for k in range(4):
        a = k * math.pi / 2
        vs = add_box(bm, 0.12, -0.07, -0.006, 0.75, 0.07, 0.006)
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, "Z"))
    bmesh.ops.translate(bm, vec=(-4.0, -0.6, ROOF - 0.42), verts=bm.verts)
    V.bm_obj("吊扇叶", bm, M["wood_furn"], C)
    plant("卧室盆栽", -1.2, 2.3, F2, 1.1, M, C, 21)
    quad_uv("画_0", [(-2.0, -4.785, F2 + 1.2), (-3.4, -4.785, F2 + 1.2),
                    (-3.4, -4.785, F2 + 2.25), (-2.0, -4.785, F2 + 2.25)], M["canvas0"], C)
    box("画框_0", -3.44, -4.80, F2 + 1.16, -1.96, -4.79, F2 + 2.29, M["frame"], C)
    quad_uv("画_2", [(2.785, -2.8, F2 + 1.2), (2.785, -4.2, F2 + 1.2),
                    (2.785, -4.2, F2 + 2.25), (2.785, -2.8, F2 + 2.25)], M["canvas2"], C)
    box("画框_2", 2.79, -4.24, F2 + 1.16, 2.80, -2.76, F2 + 2.29, M["frame"], C)
    # 窗帘: 带褶皱的细分面（Godot 里用顶点着色器让它飘）
    for k, (xa, xb) in enumerate([(-6.75, -6.0)]):
        nx, nz = 24, 20
        verts, faces = [], []
        for j in range(nz + 1):
            z = F2 + 0.05 + (2.55 * j / nz)
            for i in range(nx + 1):
                x = xa + (xb - xa) * i / nx
                verts.append((x, 2.66 + 0.04 * math.sin(i * math.pi / 2), z))
        for j in range(nz):
            for i in range(nx):
                a = j * (nx + 1) + i
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
        V.mesh_obj(f"窗帘_{k}", verts, faces, M["curtain"], C)
    box("窗帘杆", -6.8, 2.62, F2 + 2.62, -5.9, 2.70, F2 + 2.65, M["frame"], C)


# ===================================================================== 室外
def exterior(M):
    C = V.coll("室外扩展")
    rnd = random.Random(42)

    # ---- 栈桥: 沙滩上的坡道 → 伸进海里 45m，桥面高 1m
    deck_z = 1.0
    V.mesh_obj("栈桥坡道", [(12, 18, 0.02), (14, 18, 0.02), (14, 24, deck_z), (12, 24, deck_z),
                         (12, 18, -0.2), (14, 18, -0.2), (14, 24, deck_z - 0.2), (12, 24, deck_z - 0.2)],
               [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (3, 2, 6, 7), (0, 3, 7, 4)], M["deck"], C)
    V.box("栈桥桥面", 12, 24, deck_z - 0.12, 14, 70, deck_z, M["deck"], C)
    V.box("栈桥平台", 14, 62, deck_z - 0.12, 16.5, 70, deck_z, M["deck"], C)
    bm = bmesh.new()
    for y in range(24, 71, 3):
        for x in (12.1, 13.9):
            add_cyl(bm, x, y, -3.5, deck_z + (0.9 if y % 6 == 0 else -0.1), 0.12, seg=10)
    for y in (62, 66, 70):
        add_cyl(bm, 16.4, y, -3.5, deck_z + 0.5, 0.12, seg=10)
    V.bm_obj("栈桥桩", bm, M["trunk"], C, smooth=True)
    # 小船（系在栈桥平台边）: 按截面放样的开口船壳
    boat(M, C, 17.6, 66.0, -0.55)

    # ---- 礁石区（沙滩西侧，一半泡在水里）
    for k in range(14):
        x = -20 + rnd.uniform(-5, 5)
        y = 33 + rnd.uniform(-4, 6)
        s = rnd.uniform(0.6, 2.2)
        rock(f"礁石_{k}", x, y, -0.2 - (y - 30) * 0.08, s * rnd.uniform(1, 1.6), s, s * rnd.uniform(0.5, 0.9),
             100 + k, M["rock"], C)
    for k in range(6):                                     # 栈桥脚下几块
        rock(f"礁石_桥{k}", 11 + rnd.uniform(-2, 0), 36 + k * 4, -0.8 - k * 0.3, 0.8, 0.6, 0.5, 200 + k, M["rock"], C)

    # ---- 海岬 + 灯塔（右前方 ~100m）
    rock("海岬", 78, 92, -2.0, 26, 18, 9, 300, M["rock"], C)
    rock("海岬草顶", 78, 92, 1.8, 18, 12, 4, 301, M["grass"], C)
    lx, ly, lz = 80, 94, 5.2
    h = 1.6
    for k in range(8):                                     # 红白相间的塔身
        r0 = 1.6 - 0.07 * k
        cyl(f"灯塔_{k}", lx, ly, lz + k * h, lz + (k + 1) * h, r0, M["lh_red" if k % 2 else "lh_white"], C,
            r1=r0 - 0.07, seg=20)
    top = lz + 8 * h
    cyl("灯塔_回廊", lx, ly, top, top + 0.15, 1.5, M["frame"], C, seg=20)
    cyl("灯塔灯室", lx, ly, top + 0.15, top + 1.6, 0.85, M["lh_glass"], C, seg=16)
    cyl("灯塔_顶", lx, ly, top + 1.6, top + 2.6, 1.0, M["lh_red"], C, r1=0.05, seg=16)
    empty("灯塔灯位", lx, ly, top + 0.9, C)

    # ---- 篝火（沙滩上，房子西南）: 石圈 + 柴堆 + 三根坐的原木
    fx, fy = -7.0, 22.0
    bm = bmesh.new()
    for k in range(12):
        a = k / 12 * 2 * math.pi
        vs = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.16)["verts"]
        bmesh.ops.scale(bm, vec=(1.2, 1.0, 0.7), verts=vs)
        bmesh.ops.translate(bm, vec=(fx + 0.75 * math.cos(a), fy + 0.75 * math.sin(a), 0.06), verts=vs)
    V.bm_obj("篝火石圈", bm, M["rock"], C)
    bm = bmesh.new()
    for k in range(5):
        a = k / 5 * 2 * math.pi
        log(bm, (fx + 0.5 * math.cos(a), fy + 0.5 * math.sin(a), 0.03), (fx + 0.05 * math.cos(a), fy + 0.05 * math.sin(a), 0.45), 0.06)
    V.bm_obj("篝火柴堆", bm, M["charred"], C)
    empty("篝火位", fx, fy, 0.25, C)
    for k, a in enumerate((200, 270, 340)):
        r = math.radians(a)
        cx, cy = fx + 2.1 * math.cos(r), fy + 2.1 * math.sin(r)
        t = (-math.sin(r) * 0.9, math.cos(r) * 0.9)
        bm = bmesh.new()
        log(bm, (cx - t[0], cy - t[1], 0.2), (cx + t[0], cy + t[1], 0.2), 0.2, seg=12)
        V.bm_obj(f"篝火坐木{k}_座", bm, M["trunk"], C, smooth=True)

    # ---- 沙滩遮阳伞 + 浴巾
    for k, (x, y) in enumerate([(4.5, 23.5), (8.0, 25.5)]):
        V.box(f"沙滩伞杆{k}", x - 0.025, y - 0.025, 0, x + 0.025, y + 0.025, 2.4, M["frame"], C)
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, segments=12, radius1=1.3, radius2=0.02, depth=0.45,
                              matrix=Matrix.Translation((x, y, 2.25)))
        V.bm_obj(f"沙滩伞面{k}", bm, M["towel_a" if k else "towel_b"], C, smooth=False)
        V.box(f"浴巾{k}", x + 0.3, y - 1.0, 0, x + 1.1, y + 0.9, 0.015, M["towel_a" if k == 0 else "towel_b"], C)

    # ---- 更多椰树
    for k, (x, y, tilt, yaw) in enumerate([(-20, 20, 14, 60), (-17, 26, 10, 120), (21, 21, 12, -60),
                                           (25, 14, 9, 30), (-26, 11, 11, 200), (29, 27, 15, -100)]):
        V.palm(f"椰树{6 + k}", x, y, 6.0 + (k % 3), tilt, yaw, M, V.coll("室外"))

    # ---- 沙草（房子两侧和后面，一丛丛细叶）
    verts, faces = [], []
    for k in range(70):
        side = rnd.choice([(-12, -8, -6, 8), (9, 13, -6, 8), (-10, 10, -9, -6)])
        cx, cy = rnd.uniform(side[0], side[1]), rnd.uniform(side[2], side[3])
        for b in range(9):
            a = rnd.uniform(0, 6.28)
            hgt = rnd.uniform(0.35, 0.7)
            lean = rnd.uniform(0.1, 0.35)
            dx, dy = math.cos(a), math.sin(a)
            i = len(verts)
            verts += [(cx - dy * 0.015, cy + dx * 0.015, 0), (cx + dy * 0.015, cy - dx * 0.015, 0),
                      (cx + dx * lean, cy + dy * lean, hgt)]
            faces.append((i, i + 1, i + 2))
    V.mesh_obj("沙草", verts, faces, M["leaf"], C)

    # ---- 可拿起来的东西（Godot 在这些空物体位置生成刚体）
    empty("可拿_沙滩球", -1.0, 15.0, 0.4, C)
    empty("可拿_沙滩球2", 6.0, 24.0, 0.4, C)
    for k, (x, y) in enumerate([(-11, 12.6), (-7.4, 17.5), (10.8, 13.4), (21.4, 21.5)]):
        empty(f"可拿_椰子_{k}", x, y, 0.3, C)
    for k, x in enumerate((-4.4, -3.8, -3.2)):
        empty(f"可拿_杯子_{k}", x, 1.2 + 0.2 * k, V.F1 + 0.85, C)


def boat(M, C, x, y, z):
    """小船: 7 个截面放样（船尾平、船头尖），船身内外都可见；两条座板。"""
    L, B, H = 4.2, 1.5, 0.75
    S = 10
    secs = []
    for i in range(S + 1):
        t = i / S
        w = B / 2 * max(0.0, 1 - t ** 2.2) ** 0.5
        yy = y - L / 2 + L * t
        keel = z + 0.25 * t ** 3                       # 船头翘起
        gun = z + H + 0.12 * t ** 2
        secs.append([(x - w, yy, gun), (x - w * 0.8, yy, z + 0.12 + 0.25 * t ** 3), (x, yy, keel),
                     (x + w * 0.8, yy, z + 0.12 + 0.25 * t ** 3), (x + w, yy, gun)])
    verts = [p for s in secs for p in s]
    faces = []
    for i in range(S):
        a, b = i * 5, (i + 1) * 5
        for j in range(4):
            faces.append((a + j, a + j + 1, b + j + 1, b + j))
    faces.append((4, 3, 2, 1, 0))                      # 船尾板
    V.mesh_obj("小船_壳", verts, faces, M["boat"], C)
    bm = bmesh.new()
    for i in range(S):
        log(bm, secs[i][0], secs[i + 1][0], 0.04, seg=6)
        log(bm, secs[i][4], secs[i + 1][4], 0.04, seg=6)
    V.bm_obj("小船_船沿", bm, M["boat_trim"], C, smooth=True)
    for k, t in enumerate((0.3, 0.62)):
        yy = y - L / 2 + L * t
        w = B / 2 * max(0.0, 1 - t ** 2.2) ** 0.5 * 0.9
        V.box(f"小船_座板{k}", x - w, yy - 0.15, z + H * 0.55, x + w, yy + 0.15, z + H * 0.55 + 0.04, M["wood_furn"], C)


def build(M, villa_module):
    global V
    V = villa_module
    materials(M)
    interior(M)
    exterior(M)
