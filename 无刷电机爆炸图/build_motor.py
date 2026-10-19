# -*- coding: utf-8 -*-
"""
57 型内转子无刷直流电机（BLDC，3 相 / 8 极 12 槽 / 霍尔 120°）—— Blender 建模脚本

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_motor.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    motor.blend          可在 Blender 里打开；按空格播放 = 爆炸动画（第 1 帧装配，第 121 帧全爆开）
    motor.glb            给网页 / 虚幻 5 用（零件独立、带中文名和爆炸数据 extras）
    无刷电机_离线版.html  双击就能看的网页（需要同目录的 viewer_template.html）
    render_*.png         只有加 --render 时才渲染（Cycles，有显卡会自动用显卡）

坐标约定（重要）:
    脚本里尺寸全部按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    电机轴线 = +X（输出轴朝 +X），+Z 向上；所有零件的原点都在世界原点，方便做爆炸动画
    极坐标角 a 的位置 = (y, z) = (r·cos a, r·sin a)，0° 在 +Y

兼容: Blender 3.6 ~ 5.x（建模只用 bmesh，布尔/倒角用修改器并在内存里应用）
"""
import base64
import json
import math
import os
import sys
from math import asin, cos, pi, radians, sin, sqrt

import bpy  # 必须先于 bmesh 导入（作为 Python 模块运行时）
import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))
ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = next((a for a in ARGV if not a.startswith('--')), os.path.join(HERE, 'output'))
DO_RENDER = '--render' in ARGV
os.makedirs(OUT, exist_ok=True)

MM = 0.001
FRAMES = 120

# ---------------------------------------------------------------- 主要尺寸 (mm)
STACK = 20.0          # 定子叠片半长 → 叠厚 40
R_STATOR = 25.0       # 定子外径 Φ50
R_YOKE = 20.5         # 轭部内径
R_SHOE = 15.2         # 齿靴外缘
R_GAP = 14.0          # 定子内径（气隙面）
TOOTH_W = 2.1         # 齿身半宽
SHOE_HALF = radians(12.5)
R_CORE = 11.0         # 转子铁芯外径
R_MAG = 13.35         # 磁钢外径
HALF = 28.5           # 57 方
TIE = 19.8            # 贯穿螺钉位置 (±TIE, ±TIE)
FLANGE_HOLE = 23.57   # 安装孔 47.14 方
CABLE = (0.0, -19.5)  # 出线孔 (y, z)
PHASES = 'UVW'        # 12N8P 集中绕组: 齿 i 属于 PHASES[i % 3]
HALL_ANG = (15, 45, 75)   # 霍尔机械角（=电角度 60/180/300°，相邻 120° 电角）


# ---------------------------------------------------------------- 场景清理
def reset():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                 bpy.data.lights, bpy.data.worlds, bpy.data.images):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def collection(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


# ---------------------------------------------------------------- 材质
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexcol(h):
    h = h.lstrip('#')
    return tuple(_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def principled(name, hexc, metal=0.0, rough=0.5, coat=0.0, coat_rough=0.15):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None:
        nt.nodes.clear()
        b = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(b.outputs[0], out.inputs[0])
    col = hexcol(hexc)

    def put(names, v):
        for n in names:
            s = b.inputs.get(n)
            if s is not None:
                s.default_value = v
                return

    put(['Base Color'], (*col, 1.0))
    put(['Metallic'], metal)
    put(['Roughness'], rough)
    if coat > 0:
        put(['Coat Weight', 'Clearcoat'], coat)
        put(['Coat Roughness', 'Clearcoat Roughness'], coat_rough)
    m.diffuse_color = (*col, 1.0)
    m.metallic = metal
    m.roughness = rough
    return m


def make_materials():
    return dict(
        shaft=principled('M_Shaft_Steel', '#c9cdd2', 1, .22),
        alu=principled('M_Al_Anodized', '#b6bcc4', .9, .36),
        diecast=principled('M_Al_DieCast', '#a9b0b9', .85, .5),
        lam=principled('M_Electrical_Steel', '#7c848f', .9, .34),
        core=principled('M_Rotor_Core', '#6d7580', .9, .38),
        copper=principled('M_Copper_Enamel', '#c56a33', 1, .24, coat=.8),
        magnet=principled('M_NdFeB_Nickel', '#d4d7dc', 1, .16),
        sleeve=principled('M_SUS_Sleeve', '#c4c8cd', 1, .28),
        bearing=principled('M_Bearing_Steel', '#d7dadf', 1, .14),
        shield=principled('M_Bearing_Shield', '#aab0b8', 1, .32),
        pa=principled('M_PA66_Natural', '#ebe5d4', 0, .55),
        pcb=principled('M_PCB_Green', '#1e6b3a', 0, .32, coat=.6),
        trace=principled('M_PCB_Trace', '#2e8a4e', 0, .3, coat=.6),
        gold=principled('M_PCB_Gold', '#d9b25a', 1, .25),
        silk=principled('M_Silkscreen', '#f2f2f2', 0, .6),
        ic=principled('M_IC_Black', '#1c1e21', 0, .45),
        tin=principled('M_Tin', '#cfd3d8', 1, .35),
        rubber=principled('M_Rubber', '#151515', 0, .72),
        screw=principled('M_Steel_BlackOxide', '#2a2d32', .6, .4),
        label=principled('M_Label', '#e6e8eb', .5, .38),
        ink=principled('M_Label_Ink', '#16191d', 0, .5),
        smd=principled('M_SMD_Body', '#3a3128', 0, .5),
        yel=principled('M_Wire_Yellow', '#f0c419', 0, .45),
        grn=principled('M_Wire_Green', '#2a9d4b', 0, .45),
        blu=principled('M_Wire_Blue', '#2f6fd6', 0, .45),
        red=principled('M_Wire_Red', '#d33a2c', 0, .45),
        blk=principled('M_Wire_Black', '#1d1d1f', 0, .45),
        shrink=principled('M_HeatShrink', '#121212', 0, .55),
    )


# ---------------------------------------------------------------- 几何工具（bmesh，单位 mm）
def pol(r, a):
    return (r * cos(a), r * sin(a))


def chamfer(pts, b, closed):
    """把折线的每个拐角切成 45° 倒角；点的第 3 个值可单独指定倒角（0 = 不倒）"""
    n, out = len(pts), []
    for i, p in enumerate(pts):
        bi = p[2] if len(p) > 2 else b
        if (not closed and i in (0, n - 1)) or bi <= 0:
            out.append((p[0], p[1]))
            continue
        pp, pn = pts[(i - 1) % n], pts[(i + 1) % n]
        ax, ay = pp[0] - p[0], pp[1] - p[1]
        bx, by = pn[0] - p[0], pn[1] - p[1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        bb = min(bi, la * .45, lb * .45)
        out.append((p[0] + ax / la * bb, p[1] + ay / la * bb))
        out.append((p[0] + bx / lb * bb, p[1] + by / lb * bb))
    return out


def _bridge(bm, a, c):
    fs = []
    if len(a) == 1 and len(c) == 1:
        return fs
    if len(a) == 1:
        n = len(c)
        for i in range(n):
            fs.append(bm.faces.new((a[0], c[i], c[(i + 1) % n])))
    elif len(c) == 1:
        n = len(a)
        for i in range(n):
            fs.append(bm.faces.new((a[i], a[(i + 1) % n], c[0])))
    else:
        n = len(a)
        for i in range(n):
            fs.append(bm.faces.new((a[i], a[(i + 1) % n], c[(i + 1) % n], c[i])))
    return fs


def revolve(bm, prof, mi, seg=64, closed=True, b=0.0, cy=0.0, cz=0.0, axis='X'):
    """绕轴回转。prof = [(r, 轴向坐标), ...]；axis='X' 绕 (y=cy, z=cz) 的 X 平行轴，'Z' 绕 (x=cy, y=cz) 的 Z 平行轴"""
    pts = chamfer(prof, b, closed) if b > 0 else [(p[0], p[1]) for p in prof]

    def V(r, h, k):
        a = 2 * pi * k / seg
        if axis == 'X':
            return (h, cy + r * cos(a), cz + r * sin(a))
        return (cy + r * cos(a), cz + r * sin(a), h)

    rings = []
    for (r, h) in pts:
        if r < 1e-6:
            rings.append([bm.verts.new(V(0, h, 0))])
        else:
            rings.append([bm.verts.new(V(r, h, k)) for k in range(seg)])
    fs = []
    for k in range(len(rings) - (0 if closed else 1)):
        fs += _bridge(bm, rings[k], rings[(k + 1) % len(rings)])
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def extrude(bm, loops, a0, a1, mi, axis='X'):
    """把 2D 轮廓（第 1 个是外轮廓，其余是孔）沿 axis 从 a0 拉伸到 a1。
    axis='X': (u,v)→(y,z)；'Z': (u,v)→(x,y)；'Y': (u,v)→(x,z)"""
    def V(u, v, a):
        if axis == 'X':
            return (a, u, v)
        if axis == 'Z':
            return (u, v, a)
        return (u, a, v)

    L0 = [[bm.verts.new(V(u, v, a0)) for (u, v) in L] for L in loops]
    L1 = [[bm.verts.new(V(u, v, a1)) for (u, v) in L] for L in loops]
    tris = tessellate_polygon([[Vector((u, v, 0)) for (u, v) in L] for L in loops])
    f0 = [v for L in L0 for v in L]
    f1 = [v for L in L1 for v in L]
    fs = []
    for t in tris:
        fs.append(bm.faces.new((f0[t[0]], f0[t[1]], f0[t[2]])))
        fs.append(bm.faces.new((f1[t[0]], f1[t[2]], f1[t[1]])))
    for A, C in zip(L0, L1):
        n = len(A)
        for i in range(n):
            fs.append(bm.faces.new((A[i], A[(i + 1) % n], C[(i + 1) % n], C[i])))
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def circle(cx, cy, r, n=48):
    return [(cx + r * cos(2 * pi * k / n), cy + r * sin(2 * pi * k / n)) for k in range(n)]


def stadium(cx, cy, half_len, r, n=12):
    pts = []
    for k in range(n + 1):
        a = -pi / 2 + pi * k / n
        pts.append((cx + half_len + r * cos(a), cy + r * sin(a)))
    for k in range(n + 1):
        a = pi / 2 + pi * k / n
        pts.append((cx - half_len + r * cos(a), cy + r * sin(a)))
    return pts


def rrect(hw, hh, r, ns=8, notches=()):
    """圆角矩形（u 方向半宽 hw，v 方向半高 hh），notches = 两侧 (u=±hw) 的散热槽 v 坐标"""
    pts = []
    side = sorted(notches)
    pts.append((hw, -(hh - r)))
    for v0 in side:
        pts += [(hw, v0 - .8), (hw - .8, v0 - .8), (hw - .8, v0 + .8), (hw, v0 + .8)]
    for (cu, cv, a0) in ((hw - r, hh - r, 0), (-(hw - r), hh - r, pi / 2),
                         (-(hw - r), -(hh - r), pi), (hw - r, -(hh - r), 1.5 * pi)):
        for k in range(ns + 1):
            if a0 == 0 and k == 0:
                continue
            a = a0 + pi / 2 * k / ns
            pts.append((cu + r * cos(a), cv + r * sin(a)))
        if a0 == pi / 2:
            for v0 in reversed(side):
                pts += [(-hw, v0 + .8), (-hw + .8, v0 + .8), (-hw + .8, v0 - .8), (-hw, v0 - .8)]
    pts.pop()  # 最后一点与起点重合
    return pts


def sweep(bm, path, radius, mi, sides=8, closed=False, plane_n=None):
    """圆截面沿路径扫掠（线圈、导线）。平面闭合回路给 plane_n，空间曲线用平行移动标架"""
    n = len(path)
    T = []
    for i in range(n):
        if closed:
            t = path[(i + 1) % n] - path[i - 1]
        else:
            t = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
        T.append(t.normalized())
    if plane_n is not None:
        N = [plane_n.cross(t).normalized() for t in T]
        Bv = [plane_n] * n
    else:
        ref = Vector((0, 0, 1)) if abs(T[0].z) < .9 else Vector((0, 1, 0))
        nr = T[0].cross(ref).normalized()
        N = [nr.copy()]
        for i in range(1, n):
            ax = T[i - 1].cross(T[i])
            if ax.length > 1e-9:
                nr = Matrix.Rotation(T[i - 1].angle(T[i]), 3, ax.normalized()) @ nr
            N.append(nr.copy())
        Bv = [T[i].cross(N[i]) for i in range(n)]
    rings = [[bm.verts.new(path[i] + radius * (cos(2 * pi * k / sides) * N[i] + sin(2 * pi * k / sides) * Bv[i]))
              for k in range(sides)] for i in range(n)]
    fs = []
    for i in range(n if closed else n - 1):
        a, c = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            fs.append(bm.faces.new((a[k], a[(k + 1) % sides], c[(k + 1) % sides], c[k])))
    if not closed:
        fs.append(bm.faces.new(rings[0][::-1]))
        fs.append(bm.faces.new(rings[-1]))
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def catmull(ctrl, per=8):
    P = [ctrl[0]] + ctrl + [ctrl[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(ctrl[-1])
    return out


def text_into(bm, body, size, mtx, mi, extrude_mm=0.05, align='CENTER'):
    """Blender 内置字体 → 网格，并入 bm（mtx 把文字局部 XY 平面放到世界里）"""
    cu = bpy.data.curves.new('txt', 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude_mm
    cu.align_x = align
    cu.align_y = 'CENTER'
    ob = bpy.data.objects.new('txt', cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.transform(mtx)
    for p in me.polygons:
        p.material_index = mi
    bm.from_mesh(me)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)


def _tmp_obj(bm):
    me = bpy.data.meshes.new('tmp')
    bm.to_mesh(me)
    ob = bpy.data.objects.new('tmp', me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def boolean(bm_a, bm_b, op='DIFFERENCE'):
    """精确布尔（EXACT），返回新的 bmesh；两个输入都会被释放"""
    a, b = _tmp_obj(bm_a), _tmp_obj(bm_b)
    bm_a.free()
    bm_b.free()
    md = a.modifiers.new('bool', 'BOOLEAN')
    md.object = b
    md.operation = op
    md.solver = 'EXACT'
    b.hide_render = True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(a.evaluated_get(dg))
    out = bmesh.new()
    out.from_mesh(me)
    for ob in (a, b):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(d)
    bpy.data.meshes.remove(me)
    return out


def shade(me, ang):
    try:
        me.shade_smooth()
    except AttributeError:
        for p in me.polygons:
            p.use_smooth = True
    if hasattr(me, 'set_sharp_from_angle'):
        me.set_sharp_from_angle(angle=radians(ang))
    else:
        me.use_auto_smooth = True
        me.auto_smooth_angle = radians(ang)


# ---------------------------------------------------------------- 零件登记
PARTS = []          # 用于网页 / 零件表
OBJS = []           # (object, explode list in Blender coords)


def part(no, cn, jp, en, mat_txt, qty, desc, group):
    p = dict(no=no, cn=cn, jp=jp, en=en, m=mat_txt, qty=qty, desc=desc, group=group)
    PARTS.append(p)
    return p


def finish(p, name, bm, mats, ex, bevel=0.0, seg=2, angle=50, smooth=34, extra=None, coll='Motor'):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection(coll).objects.link(ob)
    shade(me, smooth)
    if bevel > 0:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = bevel
        md.segments = seg
        md.limit_method = 'ANGLE'
        md.angle_limit = radians(angle)
        try:
            md.harden_normals = True
        except Exception:
            pass
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        old = ob.data
        ob.modifiers.clear()
        ob.data = new
        new.name = name
        bpy.data.meshes.remove(old)
    ob.data.transform(Matrix.Scale(MM, 4))
    ob['part_no'] = p['no']
    ob['name_cn'] = p['cn']
    ob['name_jp'] = p['jp']
    ob['group'] = p['group']
    ob['name_en'] = p['en']
    ob['material_spec'] = p['m']
    ob['qty'] = p['qty']
    ob['desc'] = p['desc']
    # 爆炸数据存成 glTF 坐标（x, z, -y），单位 mm，最后一个数是出场时刻 0~1
    ob['ex'] = json.dumps([[e[0], e[2], -e[1], e[3]] for e in ex])
    for k, v in (extra or {}).items():
        ob[k] = v
    OBJS.append((ob, ex))
    return ob


# 爆炸路线（Blender 坐标 mm，最后一个数 = 出场时刻）
ROTOR = (95, 0, 0, .45)
EX = dict(
    tie=[(-175, 0, 0, .00)],
    key=[ROTOR, (0, 0, 14, .05)],
    rear_cap=[(-85, 0, 0, .12)],
    washer=[(-70, 0, 0, .18)],
    rear_brg=[(-55, 0, 0, .24)],
    pcb=[(-30, 0, 0, .30)],
    flange=[(190, 0, 0, .30)],
    front_brg=[(150, 0, 0, .38)],
    rotor=[ROTOR],
    housing=[(0, 0, 80, .50)],
    sleeve=[ROTOR, (55, 0, 0, .62)],
    stator=[],
)


# ---------------------------------------------------------------- 各零件
def build_shaft(M):
    p = part(1, '输出轴', 'シャフト', 'Shaft', '40Cr 调质 磨削', 1,
             'Φ8 输出轴，中段 Φ10 台阶用来定位转子铁芯和两只轴承。前端开键槽，用平键把扭矩传给负载。', 'rotor')
    bm = bmesh.new()
    revolve(bm, [(0, -37.2), (4, -37.2), (4, -29), (5, -29), (5, 35.5), (4, 35.5), (4, 69.6), (0, 69.6)],
            0, seg=64, closed=False, b=.45)
    cut = bmesh.new()
    extrude(cut, [stadium(59, 0, 7, 1.5)], 2.2, 6.5, 0, 'Z')
    bm = boolean(bm, cut)
    finish(p, 'P01_Shaft', bm, [M['shaft']], EX['rotor'], extra=dict(spin=1))

    p = part(2, '平键', 'キー', 'Key', '45 钢 3×3×13', 1,
             '嵌在轴的键槽里，和联轴器上的键槽配合传递扭矩。', 'rotor')
    bm = bmesh.new()
    extrude(bm, [stadium(59, 0, 6.5, 1.5)], 2.25, 5.2, 0, 'Z')
    finish(p, 'P02_Key', bm, [M['shaft']], EX['key'], bevel=.3, extra=dict(spin=1))


def build_rotor(M):
    p = part(3, '转子铁芯', 'ロータコア', 'RotorCore', '硅钢片叠压', 1,
             '和轴过盈配合。用导磁的叠片做磁轭，让磁钢的磁通在背面闭合，叠片能减小涡流损耗。', 'rotor')
    prof = [(5.05, -23), (R_CORE, -23)]
    x = -22.2
    while x < 19.3:
        prof += [(R_CORE, x, 0), (R_CORE - .1, x + .08, 0), (R_CORE, x + .16, 0)]
        x += 1.5
    prof += [(R_CORE, 20), (5.05, 20)]
    bm = bmesh.new()
    revolve(bm, prof, 0, seg=72, closed=True, b=.3)
    finish(p, 'P03_RotorCore', bm, [M['core']], EX['rotor'], extra=dict(spin=1))

    p = part(4, '钕铁硼磁钢', '磁石（ネオジム）', 'Magnet', 'N42SH 镀镍', 8,
             '8 块瓦形磁钢 N/S 交替，组成 8 极（4 对极）。中间厚两边薄的“面包形”让气隙磁场更接近正弦，转矩更平顺。', 'rotor')
    half = radians(19)
    for i in range(8):
        ac = radians(45 * i)
        pts = []
        n = 16
        for k in range(n + 1):
            a = ac - half + 2 * half * k / n
            pts.append(pol(R_CORE + .02, a))
        for k in range(n, -1, -1):
            a = ac - half + 2 * half * k / n
            s = (a - ac) / half
            pts.append(pol(R_MAG - .55 * s * s, a))
        bm = bmesh.new()
        extrude(bm, [pts], -23, 20, 0, 'X')
        out = 7.0
        ex = EX['rotor'] + [(0, out * cos(ac), out * sin(ac), .72)]
        finish(p, f'P04_Magnet_{i + 1}', bm, [M['magnet']], ex, bevel=.25,
               extra=dict(spin=1, pole='N' if i % 2 == 0 else 'S', angle_deg=45 * i))

    p = part(5, '磁钢护套', 'マグネットスリーブ', 'MagnetSleeve', 'SUS304 0.3 mm', 1,
             '套在磁钢外面的薄不锈钢管，防止高速旋转时磁钢被离心力甩出来；不导磁，不影响磁路。', 'rotor')
    bm = bmesh.new()
    revolve(bm, [(13.45, -23.6), (13.75, -23.6), (13.75, 20.6), (13.45, 20.6)], 0, seg=96, b=.1)
    finish(p, 'P05_Sleeve', bm, [M['sleeve']], EX['sleeve'], extra=dict(spin=1))


def bearing_bm(xc, M_idx):
    bm = bmesh.new()
    revolve(bm, [(9.6, xc - 3.5), (11, xc - 3.5), (11, xc + 3.5), (9.6, xc + 3.5)], M_idx[0], seg=64, b=.45)
    revolve(bm, [(4, xc - 3.5), (5.6, xc - 3.5), (5.6, xc + 3.5), (4, xc + 3.5)], M_idx[0], seg=64, b=.45)
    for s in (-1, 1):
        x0 = xc + s * 3.1
        revolve(bm, [(5.7, x0 - .15), (9.5, x0 - .15), (9.5, x0 + .15), (5.7, x0 + .15)], M_idx[1], seg=64)
        revolve(bm, [(6.4, x0 + s * .15), (8.6, x0 + s * .15), (8.6, x0 + s * .32), (6.4, x0 + s * .32)],
                M_idx[1], seg=64)
    for k in range(7):
        a = 2 * pi * k / 7
        r = bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=1.98)
        bmesh.ops.translate(bm, verts=r['verts'], vec=(xc, 7.5 * cos(a), 7.5 * sin(a)))
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = M_idx[0]
    return bm


def build_bearings(M):
    p = part(6, '深沟球轴承', '玉軸受 608ZZ', 'Bearing', '608ZZ（8×22×7）', 2,
             '前后各一只，支撑转子旋转。ZZ = 两面钢制防尘盖，里面封了润滑脂，免维护。', 'bearing')
    finish(p, 'P06_Bearing_Front', bearing_bm(40.5, (0, 1)), [M['bearing'], M['shield']], EX['front_brg'])
    finish(p, 'P06_Bearing_Rear', bearing_bm(-33.5, (0, 1)), [M['bearing'], M['shield']], EX['rear_brg'])

    p = part(7, '波形垫圈', 'ウェーブワッシャ', 'WaveWasher', '65Mn 弹簧钢', 1,
             '装在后轴承外圈后面，给轴承一个轴向预压，消除游隙，降低运转噪音。', 'bearing')
    bm = bmesh.new()
    n, rings = 120, []
    for k in range(n):
        a = 2 * pi * k / n
        w = .28 * sin(3 * a)
        x0 = -37.35 + w
        rings.append([bm.verts.new((x0 - .13, 8.6 * cos(a), 8.6 * sin(a))),
                      bm.verts.new((x0 - .13, 10.8 * cos(a), 10.8 * sin(a))),
                      bm.verts.new((x0 + .13, 10.8 * cos(a), 10.8 * sin(a))),
                      bm.verts.new((x0 + .13, 8.6 * cos(a), 8.6 * sin(a)))])
    fs = []
    for k in range(n):
        a, c = rings[k], rings[(k + 1) % n]
        for j in range(4):
            fs.append(bm.faces.new((a[j], a[(j + 1) % 4], c[(j + 1) % 4], c[j])))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    finish(p, 'P07_WaveWasher', bm, [M['shield']], EX['washer'], smooth=40)


def build_flange(M):
    p = part(8, '前端盖（法兰）', 'フロントフランジ', 'FrontFlange', 'ADC12 压铸铝', 1,
             '57 方安装法兰，4 个 Φ5.2 安装孔（孔距 47.14），Φ38 止口用于和设备对中；内侧轴承室装前轴承。', 'housing')
    loops = [rrect(HALF, HALF, 4.5)] + [circle(sx * FLANGE_HOLE, sz * FLANGE_HOLE, 2.6, 32)
                                         for sx in (-1, 1) for sz in (-1, 1)] + [circle(0, 0, 11.05, 64)]
    bm = bmesh.new()
    extrude(bm, loops, 40, 48, 0, 'X')
    cut = bmesh.new()
    for sx in (-1, 1):
        for sz in (-1, 1):
            revolve(cut, [(0, 39), (1.7, 39), (1.7, 46.5), (0, 46.5)], 0, seg=24, closed=False,
                    cy=sx * TIE, cz=sz * TIE)
    bm = boolean(bm, cut)
    revolve(bm, [(6, 44), (11.1, 44), (11.1, 48), (19, 48), (19, 49.6), (6, 49.6)], 0, seg=96, b=.3)
    revolve(bm, [(11.05, 33), (14.5, 33), (14.5, 40.2), (11.05, 40.2)], 0, seg=96, b=.3)
    revolve(bm, [(22.5, 36), (24.95, 36), (24.95, 40.2), (22.5, 40.2)], 0, seg=96, b=.3)
    finish(p, 'P08_FrontFlange', bm, [M['diecast']], EX['flange'], bevel=.5)


def build_housing(M):
    p = part(9, '机壳', 'ハウジング', 'Housing', '6063 铝型材 阳极氧化', 1,
             '57 方铝型材，内孔和定子过盈配合，把绕组发的热传到外壳散掉；两侧的槽增加散热面积。', 'housing')
    loops = [rrect(HALF, HALF, 4.5, notches=(-12, -6, 0, 6, 12)), circle(0, 0, 25.02, 144)] + \
            [circle(sx * TIE, sz * TIE, 2.2, 24) for sx in (-1, 1) for sz in (-1, 1)]
    bm = bmesh.new()
    extrude(bm, loops, -30, 40, 0, 'X')
    finish(p, 'P09_Housing', bm, [M['alu']], EX['housing'], bevel=.6)

    p = part(10, '铭牌', '銘板', 'Nameplate', '铝箔不干胶', 1,
             '额定参数：24 V DC、3000 rpm、188 W、0.6 N·m。选驱动器时主要看电压、电流和极对数。', 'housing')
    bm = bmesh.new()
    extrude(bm, [[(-17, -10.5), (25, -10.5), (25, 10.5), (-17, 10.5)]], 28.5, 28.62, 0, 'Z')
    up = Matrix.Translation((4, 0, 28.6))
    lines = [('BRUSHLESS DC MOTOR', 2.3, 6.4), ('57BL75-24   24 V DC', 1.8, 2.9),
             ('3000 rpm   188 W   0.6 N·m', 1.8, -0.2), ('8 POLES   3 PHASE   HALL 120°', 1.8, -3.3),
             ('IP54   INS. CLASS B   S/N 2610-0457', 1.35, -6.9)]
    for body, size, y in lines:
        text_into(bm, body, size, up @ Matrix.Translation((0, y, 0)), 1, extrude_mm=.04)
    finish(p, 'P10_Nameplate', bm, [M['label'], M['ink']], EX['housing'], smooth=30)


def stator_loops(r_out=R_STATOR, notch=True):
    outer = []
    for k in range(144):
        a = 2 * pi * k / 144
        r = r_out
        if notch and min(abs(math.atan2(sin(a - q), cos(a - q))) for q in (pi / 4, 3 * pi / 4, 5 * pi / 4, 7 * pi / 4)) < radians(1.4):
            r = r_out - .5
        outer.append(pol(r, a))
    inner = []
    gy, gs = asin(TOOTH_W / R_YOKE), asin(TOOTH_W / R_SHOE)
    for i in range(12):
        f = radians(30 * i)
        inner += [pol(R_YOKE, f - gy), pol(R_SHOE, f - gs), pol(R_SHOE, f - SHOE_HALF), pol(R_GAP, f - SHOE_HALF)]
        inner += [pol(R_GAP, f - SHOE_HALF + 2 * SHOE_HALF * k / 10) for k in range(1, 10)]
        inner += [pol(R_GAP, f + SHOE_HALF), pol(R_SHOE, f + SHOE_HALF), pol(R_SHOE, f + gs), pol(R_YOKE, f + gy)]
        span = radians(30) - 2 * gy
        inner += [pol(R_YOKE, f + gy + span * k / 6) for k in range(1, 6)]
    return [outer, inner]


def build_stator(M):
    p = part(11, '定子铁芯', 'ステータコア', 'StatorCore', '0.5 mm 硅钢片 ×80 叠压', 1,
             '12 个齿的叠片铁芯（图上每片画成 2.5 mm 方便看）。线圈通电后齿被磁化，吸引/推动转子磁钢。外圆 4 道焊缝把叠片固定成一体。', 'stator')
    loops = stator_loops()
    bm = bmesh.new()
    n = 16
    t = 2 * STACK / n
    for k in range(n):
        x0 = -STACK + k * t
        extrude(bm, loops, x0 + .06, x0 + t - .06, 0, 'X')
    finish(p, 'P11_StatorCore', bm, [M['lam']], EX['stator'], bevel=.14, seg=1)

    p = part(12, '绝缘骨架', 'インシュレータ', 'Insulator', 'PA66 尼龙', 2,
             '装在铁芯两端，把漆包线和铁芯隔开（防止漆皮被铁芯棱角磨破短路），挡墙让线圈绕得整齐。', 'stator')
    for s in (1, -1):
        bm = bmesh.new()
        lo = stator_loops(23.6, notch=False)
        a0, a1 = (STACK, STACK + 1.2) if s > 0 else (-STACK - 1.2, -STACK)
        extrude(bm, lo, a0, a1, 0, 'X')
        w0, w1 = (STACK + 1.2, STACK + 4.4) if s > 0 else (-STACK - 4.4, -STACK - 1.2)
        ring = [circle(0, 0, 21.4, 120), circle(0, 0, 20.6, 120)]
        extrude(bm, ring, w0, w1, 0, 'X')
        for i in range(12):
            f = radians(30 * i)
            arc = [pol(14.5, f - SHOE_HALF + 2 * SHOE_HALF * k / 8) for k in range(9)] + \
                  [pol(15.15, f + SHOE_HALF - 2 * SHOE_HALF * k / 8) for k in range(9)]
            extrude(bm, [arc], w0, w1, 0, 'X')
        finish(p, f'P12_Insulator_{"Front" if s > 0 else "Rear"}', bm, [M['pa']], EX['stator'], bevel=.2)

    p = part(13, '绕组线圈', 'コイル（巻線）', 'Coil', 'Φ0.95 漆包铜线', 12,
             '12 个集中绕组，每个绕在一个齿上，按 U-V-W 循环分成三相，每相 4 个串联。通电方向决定这个齿是 N 还是 S。', 'stator')
    for i in range(12):
        f = radians(30 * i)
        d = Vector((0, cos(f), sin(f)))
        tv = Vector((0, -sin(f), cos(f)))
        X = Vector((1, 0, 0))
        bm = bmesh.new()
        for r in (15.7, 16.65, 17.6, 18.55, 19.5):
            slot_half = (2 * pi * r / 12 - 2 * TOOTH_W) / 2
            T = max(1, int((slot_half - .97) / .95) + 1)
            for k in range(T):
                hu = TOOTH_W + .5 + k * .95
                hv = STACK + 1.2 + .5 + k * .95
                rc = .55 + k * .95
                path = []
                for (cu, cv, a0) in ((hu - rc, hv - rc, 0), (-(hu - rc), hv - rc, pi / 2),
                                     (-(hu - rc), -(hv - rc), pi), (hu - rc, -(hv - rc), 1.5 * pi)):
                    for j in range(5):
                        a = a0 + pi / 2 * j / 4
                        path.append(d * r + tv * (cu + rc * cos(a)) + X * (cv + rc * sin(a)))
                sweep(bm, path, .47, 0, sides=6, closed=True, plane_n=d)
        ph = PHASES[i % 3]
        finish(p, f'P13_Coil_{i + 1:02d}_{ph}', bm, [M['copper']], EX['stator'], smooth=70,
               extra=dict(phase=ph, tooth=i, angle_deg=30 * i))


def build_pcb(M):
    p = part(14, '霍尔板', 'ホール基板', 'HallPCB', 'FR-4 1.6 mm', 1,
             '环形电路板，装在定子后端。3 个霍尔元件感应转子磁钢的极性，驱动器据此知道转子转到哪了，决定下一步给哪两相通电。', 'pcb')
    bm = bmesh.new()
    extrude(bm, [circle(0, 0, 23.6, 120), circle(0, 0, 8.6, 64)], -27, -25.4, 0, 'X')
    for k in range(3):                      # 背面走线（示意）：从各霍尔位置绕到焊盘
        a0, a1 = radians(HALL_ANG[k] + 180 - 360), radians(-95 + 5 * k)
        r0 = 15.8 + k * 1.1
        arc = [pol(r0, a0 + (a1 - a0) * j / 30) for j in range(31)] + \
              [pol(r0 + .55, a0 + (a1 - a0) * j / 30) for j in range(30, -1, -1)]
        extrude(bm, [arc], -27.05, -26.99, 1, 'X')
    for j in range(8):
        a = radians(-107.5 + 5 * j)
        y, z = pol(19.5, a)
        ty = (-sin(a), cos(a))
        r_ = (cos(a), sin(a))
        pad = [(y + ty[0] * s1 * .7 + r_[0] * s2 * 1.1, z + ty[1] * s1 * .7 + r_[1] * s2 * 1.1)
               for (s1, s2) in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        extrude(bm, [pad], -27.06, -26.98, 2, 'X')
    for (a_deg, rr) in ((200, 18.5), (215, 18.5), (330, 18.5), (130, 19.5)):
        a = radians(a_deg)
        y, z = pol(rr, a)
        ty, r_ = (-sin(a), cos(a)), (cos(a), sin(a))
        body = [(y + ty[0] * s1 * .8 + r_[0] * s2 * .4, z + ty[1] * s1 * .8 + r_[1] * s2 * .4)
                for (s1, s2) in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        extrude(bm, [body], -27.45, -27.0, 3, 'X')
        for s1 in (-1, 1):
            cap = [(y + ty[0] * (s1 * .8 + s1 * d1) + r_[0] * s2 * .41, z + ty[1] * (s1 * .8 + s1 * d1) + r_[1] * s2 * .41)
                   for (d1, s2) in ((-.18, -1), (.02, -1), (.02, 1), (-.18, 1))]
            extrude(bm, [cap], -27.46, -27.0, 2, 'X')
    rear = Matrix(((0, 0, -1, 0), (-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    front = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    for j, lab in enumerate(['U', 'V', 'W', '+5V', 'GND', 'H1', 'H2', 'H3']):
        a = radians(-107.5 + 5 * j)
        y, z = pol(22.4, a)
        text_into(bm, lab, .9 if len(lab) > 1 else 1.1, Matrix.Translation((-27.02, y, z)) @ rear, 4, extrude_mm=.02)
    text_into(bm, 'BLDC-HALL v2.1', 1.2, Matrix.Translation((-27.02, 0, 14.6)) @ rear, 4, extrude_mm=.02)
    for k in range(3):
        y, z = pol(16.3, radians(HALL_ANG[k]))
        text_into(bm, f'H{k + 1}', 1.0, Matrix.Translation((-25.38, y, z)) @ front, 4, extrude_mm=.02)
    finish(p, 'P14_HallPCB', bm, [M['pcb'], M['trace'], M['gold'], M['smd'], M['silk']], EX['pcb'], bevel=.12, seg=1)

    p = part(15, '霍尔元件', 'ホールセンサ', 'HallSensor', 'SOT-23 开关型霍尔', 3,
             '对着磁钢端面，N 极经过输出 1、S 极输出 0。三个元件相隔 30° 机械角（= 120° 电角度），转一对极输出 6 种组合，正好对应六步换相。', 'pcb')
    for k in range(3):
        a = radians(HALL_ANG[k])
        bm = bmesh.new()
        ty, r_ = (-sin(a), cos(a)), (cos(a), sin(a))
        y, z = pol(12.2, a)
        body = [(y + ty[0] * s1 * 1.45 + r_[0] * s2 * .7, z + ty[1] * s1 * 1.45 + r_[1] * s2 * .7)
                for (s1, s2) in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        extrude(bm, [body], -25.4, -24.35, 0, 'X')
        for (tt, rs) in ((-0.95, -1), (0.95, -1), (0, 1)):
            cy, cz = y + ty[0] * tt + r_[0] * rs * 1.05, z + ty[1] * tt + r_[1] * rs * 1.05
            leg = [(cy + ty[0] * s1 * .22 + r_[0] * s2 * .38, cz + ty[1] * s1 * .22 + r_[1] * s2 * .38)
                   for (s1, s2) in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            extrude(bm, [leg], -25.4, -25.25, 1, 'X')
        finish(p, f'P15_Hall_H{k + 1}', bm, [M['ic'], M['tin']], EX['pcb'], bevel=.12, seg=1,
               extra=dict(hall=k + 1, angle_deg=HALL_ANG[k]))

    p = part(16, '引出线', 'リード線', 'LeadWires', 'UL1007 18AWG×3 + 26AWG×5', 1,
             '粗线 3 根是相线 U/V/W（黄/绿/蓝），接驱动器功率输出；细线 5 根是霍尔：红 +5V、黑 GND、黄/绿/蓝 = H1/H2/H3。', 'pcb')
    wires = [('yel', .9, -2.0, 1.0), ('grn', .9, 0.0, 1.0), ('blu', .9, 2.0, 1.0),
             ('red', .5, -2.2, -1.35), ('blk', .5, -1.1, -1.35), ('yel', .5, 0.0, -1.35),
             ('grn', .5, 1.1, -1.35), ('blu', .5, 2.2, -1.35)]
    mats = [M['yel'], M['grn'], M['blu'], M['red'], M['blk'], M['tin'], M['shrink']]
    idx = dict(yel=0, grn=1, blu=2, red=3, blk=4)
    bm = bmesh.new()
    cy0, cz0 = CABLE
    for j, (col, r, by, bz) in enumerate(wires):
        a = radians(-107.5 + 5 * j)
        py, pz = pol(19.5, a)
        Y, Z = cy0 + by, cz0 + bz
        ctrl = [Vector((-27.0, py, pz)), Vector((-28.4, py * .5 + Y * .5, pz * .5 + Z * .5)), Vector((-30.6, Y, Z)),
                Vector((-52, Y, Z)), Vector((-57, Y, Z - 2)), Vector((-60, Y, Z - 9)), Vector((-61.5, Y, Z - 20)),
                Vector((-63, Y, Z - 34)), Vector((-68, Y * 1.3, Z - 46)), Vector((-78, Y * 1.7, Z - 52 - j * .6))]
        path = catmull(ctrl, per=7)
        sweep(bm, path, r, idx[col], sides=10 if r > .6 else 8)
        tdir = (path[-1] - path[-2]).normalized()
        sweep(bm, [path[-1] - tdir * .2, path[-1] + tdir * 3.5], r * .72, 5, sides=8)
    revolve(bm, [(3.0, -51.5), (3.95, -51.5), (3.95, -43.8), (3.0, -43.8)], 6, seg=32, b=.25, cy=cy0, cz=cz0)
    finish(p, 'P16_LeadWires', bm, mats, EX['pcb'], smooth=60)


def build_rear(M):
    p = part(17, '后端盖', 'リアカバー', 'RearCover', 'ADC12 压铸铝', 1,
             '封住电机尾部，轴承室装后轴承；4 根长螺钉从这里穿过机壳拧进前端盖，把整台电机夹紧。', 'housing')
    loops = [rrect(HALF, HALF, 4.5), circle(0, 0, 11.05, 64), circle(CABLE[0], CABLE[1], 4.6, 32)] + \
            [circle(sx * TIE, sz * TIE, 2.2, 24) for sx in (-1, 1) for sz in (-1, 1)]
    bm = bmesh.new()
    extrude(bm, loops, -40, -30, 0, 'X')
    revolve(bm, [(0, -40.2), (11.2, -40.2), (11.2, -37.6), (0, -37.6)], 0, seg=96, closed=False, b=.3)
    revolve(bm, [(11.05, -30.2), (14, -30.2), (14, -28.2), (11.05, -28.2)], 0, seg=96, b=.3)
    finish(p, 'P17_RearCover', bm, [M['diecast']], EX['rear_cap'], bevel=.5)

    p = part(18, '护线套', 'グロメット', 'Grommet', 'NBR 橡胶', 1,
             '出线孔里的橡胶圈，防止导线被铝壳孔口割破，也挡灰尘和水。', 'housing')
    bm = bmesh.new()
    revolve(bm, [(3.7, -43.5), (5.8, -43.5), (5.8, -40.6), (4.5, -40.6), (4.5, -30.4), (5.0, -30.4),
                 (5.0, -29.6), (3.7, -29.6)], 0, seg=48, b=.3, cy=CABLE[0], cz=CABLE[1])
    finish(p, 'P18_Grommet', bm, [M['rubber']], EX['rear_cap'])

    p = part(19, '贯穿螺钉', '通しボルト', 'TieScrew', 'M4×86 内六角 发黑', 4,
             '4 根长螺钉把后端盖、机壳、前端盖串起来拧紧。拆电机时先拆它们。', 'housing')
    for sx in (-1, 1):
        for sz in (-1, 1):
            cy, cz = sx * TIE, sz * TIE
            head = bmesh.new()
            revolve(head, [(0, -44), (3.4, -44), (3.4, -40), (0, -40)], 0, seg=48, closed=False, b=.45, cy=cy, cz=cz)
            cut = bmesh.new()
            hexl = [(cy + 1.73 * cos(k * pi / 3), cz + 1.73 * sin(k * pi / 3)) for k in range(6)]
            extrude(cut, [hexl], -44.5, -41.6, 0, 'X')
            bm = boolean(head, cut)
            prof = [(0, -40), (2, -40), (2, 31.8)]
            x = 32.0
            while x < 45.3:
                prof += [(1.62, x + .35, 0), (2, x + .7, 0)]
                x += .7
            prof += [(1.6, 46), (0, 46)]
            revolve(bm, prof, 0, seg=24, closed=False, cy=cy, cz=cz)
            finish(p, f'P19_TieScrew_{len([1 for o, _ in OBJS if o.name.startswith("P19")]) + 1}', bm,
                   [M['screw']], EX['tie'])


# ---------------------------------------------------------------- 爆炸动画（.blend 里按空格播放）
def ease(x):
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def prog(t, s):
    return ease(min(1.0, max(0.0, (t - s * .6) / .4)))


def animate():
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, FRAMES + 1
    for ob, ex in OBJS:
        for f in range(1, FRAMES + 2, 4):
            t = (f - 1) / FRAMES
            v = Vector((0, 0, 0))
            for e in ex:
                v += Vector(e[:3]) * prog(t, e[3])
            ob.location = v * MM
            ob.keyframe_insert('location', frame=f)
    sc.frame_set(1)


# ---------------------------------------------------------------- 相机 / 灯光 / 渲染
def setup_render():
    sc = bpy.context.scene
    world = bpy.data.worlds.new('World')
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    mix = nt.nodes.new('ShaderNodeMixShader')
    lp = nt.nodes.new('ShaderNodeLightPath')
    bg_env = nt.nodes.new('ShaderNodeBackground')
    bg_cam = nt.nodes.new('ShaderNodeBackground')
    bg_cam.inputs['Color'].default_value = (*hexcol('#eef1f4'), 1)
    hdri = None
    try:
        base = bpy.utils.system_resource('DATAFILES', path='studiolights/world')
        for nm in ('studio.exr', 'interior.exr', 'forest.exr'):
            if os.path.exists(os.path.join(base, nm)):
                hdri = os.path.join(base, nm)
                break
    except Exception:
        pass
    if hdri:
        tex = nt.nodes.new('ShaderNodeTexEnvironment')
        tex.image = bpy.data.images.load(hdri)
        nt.links.new(tex.outputs['Color'], bg_env.inputs['Color'])
        bg_env.inputs['Strength'].default_value = 0.8
    else:
        bg_env.inputs['Color'].default_value = (*hexcol('#dfe5ec'), 1)
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg_env.outputs[0], mix.inputs[1])
    nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    def light(name, kind, loc, energy, size):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == 'AREA':
            ld.size = size
        ob = bpy.data.objects.new(name, ld)
        collection('Studio').objects.link(ob)
        ob.location = loc
        d = Vector((0, 0, 0)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        return ob

    light('Key', 'AREA', (0.25, -0.35, 0.45), 6, .35)
    light('Rim', 'AREA', (-0.4, 0.35, 0.25), 4, .4)
    cam_d = bpy.data.cameras.new('Camera')
    cam_d.lens = 70
    cam = bpy.data.objects.new('Camera', cam_d)
    collection('Studio').objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in
                                                          sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dev in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.type == dev for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == dev
                    sc.cycles.device = 'GPU'
                    break
            except Exception:
                continue
    except Exception:
        pass
    return cam


def frame_camera(cam, frame, dist, target, elev=24, azim=-38):
    sc = bpy.context.scene
    sc.frame_set(frame)
    t = Vector(target) * MM
    a, e = radians(azim), radians(elev)
    cam.location = t + Vector((sin(-a) * cos(e), -cos(a) * cos(e), sin(e))) * dist
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()


def render(cam, name, frame, dist, target, w=1600, h=1000, **kw):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    frame_camera(cam, frame, dist, target, **kw)
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)
    print('[OK] rendered', name)


# ---------------------------------------------------------------- 导出
def export_glb(path):
    bpy.context.scene.frame_set(1)
    for ob in bpy.context.scene.objects:
        ob.select_set(ob.type == 'MESH')
    kw = dict(filepath=path, export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
              export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ('export_animations', 'export_cameras', 'export_lights'):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    print('[OK] exported', path)


def write_html(glb_path):
    tpl = os.path.join(HERE, 'viewer_template.html')
    if not os.path.exists(tpl):
        print('[WARN] viewer_template.html not found, skip html')
        return
    with open(tpl, encoding='utf-8') as f:
        html = f.read()
    with open(glb_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    html = html.replace('"__GLB_BASE64__"', '"' + b64 + '"')
    dst = os.path.join(OUT, '无刷电机_离线版.html')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[OK] wrote', dst)


def main():
    reset()
    M = make_materials()
    build_shaft(M)
    build_rotor(M)
    build_bearings(M)
    build_flange(M)
    build_housing(M)
    build_stator(M)
    build_pcb(M)
    build_rear(M)
    with open(os.path.join(OUT, 'parts.json'), 'w', encoding='utf-8') as f:
        json.dump(PARTS, f, ensure_ascii=False, indent=1)
    cam = setup_render()
    animate()
    glb = os.path.join(OUT, 'motor.glb')
    export_glb(glb)
    write_html(glb)
    frame_camera(cam, 1, .42, (8, 0, 0))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'motor.blend'))
    print('[OK] saved motor.blend')
    if DO_RENDER:
        render(cam, 'render_assembled.png', 1, .40, (8, 0, -2))
        render(cam, 'render_exploded.png', FRAMES + 1, 1.15, (10, 0, 15), elev=20, azim=-30)
    tris = 0
    for o, _ in OBJS:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    print(f'[OK] {len(OBJS)} objects, {tris} triangles')


main()
