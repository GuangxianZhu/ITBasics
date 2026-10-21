# -*- coding: utf-8 -*-
"""
AI 训练服务器（8U · 8 卡 HGX H100 平台，原创简化）—— Blender 脚本建模 + 原理爆炸图

没有图纸。整体布局参考 NVIDIA DGX H100 / HGX H100 8-GPU 这一类 8U 风冷服务器的公开图片：
上半部是 GPU 托盘（HGX 基板 + 8 块 SXM5 GPU + 4 颗 NVSwitch），从前面抽出；
下半部是 CPU 主板托盘（双路 CPU + 32 根 DDR5 + 8 张 400G 网卡），从后面抽出；
前面是风扇墙和 NVMe 硬盘，后上方是 6 个 3000 W 电源。尺寸按 19 英寸机架、8U 高（355.6 mm）估的。
每个零件都配了"它在整台机器里干什么"的说明（见 INFO）。

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_ai_server.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    ai_server.blend   Blender 工程，按空格播放：第 1~120 帧按拆机顺序拆开，第 150~270 帧反顺序装回
    ai_server.glb     glTF 模型（单位米，每个零件一个节点，extras 里有零件号、中文名、材料、作用、爆炸路线），
                      虚幻工程 MyVRToyBox 的 Tools/import_model.py 直接导入
    parts.json        零件表
    render_*.png      加 --render 时用 Cycles 渲染装配 / 爆炸两张预览图

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    服务器平放：+Z 向上，-Y 是前面板（风扇、硬盘），+Y 是后面（电源、网卡），X 是左右（宽 446 mm，不含挂耳）
    Z = 0 是机箱底面，顶盖上表面 Z = 355.6
    所有零件都直接按装配位置建模（物体原点都在世界原点），爆炸动画只动物体位置

兼容: Blender 4.2 ~ 5.x
"""
import json
import math
import os
import sys
from math import cos, pi, radians, sin

import bpy  # 必须先于 bmesh 导入（作为 Python 模块运行时）
import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))
ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(next((a for a in ARGV if not a.startswith('--')), os.path.join(HERE, 'output')))
DO_RENDER = '--render' in ARGV
os.makedirs(OUT, exist_ok=True)

MM = 0.001

# ---------------------------------------------------------------- 时间线（帧）
F_EXP = (1, 120)       # 拆开
F_ASM = (150, 270)     # 装回
F_END = 300

def reset():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                 bpy.data.lights, bpy.data.worlds, bpy.data.images):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    try:  # 逐帧关键帧用线性插值，避免贝塞尔过冲
        bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    except Exception:
        pass


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


def _bsdf(m):
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
    return nt, b


def _put(b, names, v):
    for n in names:
        s = b.inputs.get(n)
        if s is not None:
            s.default_value = v
            return


def principled(name, hexc, metal=0.0, rough=0.5, coat=0.0, alpha=1.0, trans=0.0):
    m = bpy.data.materials.new(name)
    nt, b = _bsdf(m)
    col = hexcol(hexc)
    _put(b, ['Base Color'], (*col, 1.0))
    _put(b, ['Metallic'], metal)
    _put(b, ['Roughness'], rough)
    if coat > 0:
        _put(b, ['Coat Weight', 'Clearcoat'], coat)
        _put(b, ['Coat Roughness', 'Clearcoat Roughness'], .12)
    if trans > 0:
        _put(b, ['Transmission Weight', 'Transmission'], trans)
    if alpha < 1:
        _put(b, ['Alpha'], alpha)
        for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    m.diffuse_color = (*col, alpha)
    m.metallic = metal
    m.roughness = rough
    return m


def checker_mat(name, c1, c2, scale):
    m = bpy.data.materials.new(name)
    nt, b = _bsdf(m)
    tex = nt.nodes.new('ShaderNodeTexChecker')
    tex.inputs['Color1'].default_value = (*hexcol(c1), 1)
    tex.inputs['Color2'].default_value = (*hexcol(c2), 1)
    tex.inputs['Scale'].default_value = scale
    nt.links.new(tex.outputs['Color'], b.inputs['Base Color'])
    _put(b, ['Roughness'], .9)
    m.diffuse_color = (*hexcol(c1), 1)
    return m



# ---------------------------------------------------------------- 几何工具（bmesh）
def chamfer(pts, b, closed):
    """把折线的每个拐角切成 45° 倒角"""
    n, out = len(pts), []
    for i, p in enumerate(pts):
        if (not closed and i in (0, n - 1)) or b <= 0:
            out.append((p[0], p[1]))
            continue
        pp, pn = pts[(i - 1) % n], pts[(i + 1) % n]
        ax, ay = pp[0] - p[0], pp[1] - p[1]
        bx, by = pn[0] - p[0], pn[1] - p[1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        bb = min(b, la * .45, lb * .45)
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


def revolve(bm, prof, mi, seg=64, closed=True, b=0.0, cy=0.0, cz=0.0, axis='Z'):
    """绕轴回转。prof = [(r, 轴向坐标), ...]
    axis='Z': 绕过 (x=cy, y=cz) 的竖直轴；axis='X': 绕过 (y=cy, z=cz) 的 X 平行轴"""
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


def cyl(bm, r, z0, z1, mi, seg=32, cx=0.0, cy=0.0):
    return revolve(bm, [(0, z0), (r, z0), (r, z1), (0, z1)], mi, seg=seg, closed=False, cy=cx, cz=cy)


def extrude(bm, loops, a0, a1, mi, axis='Z'):
    """2D 轮廓（第 1 个是外轮廓，其余是孔）沿 axis 拉伸。
    axis='Z': (u,v)→(x,y)；'X': (u,v)→(y,z)；'Y': (u,v)→(x,z)"""
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


def box(bm, c, s, mi):
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r['verts']
    bmesh.ops.scale(bm, vec=Vector(s), verts=vs)
    bmesh.ops.translate(bm, vec=Vector(c), verts=vs)
    for f in {f for v in vs for f in v.link_faces}:
        f.material_index = mi


def xform(bm, faces, mtx):
    vs = list({v for f in faces for v in f.verts})
    bmesh.ops.transform(bm, matrix=mtx, verts=vs)


def circle(cx, cy, r, n=48):
    return [(cx + r * cos(2 * pi * k / n), cy + r * sin(2 * pi * k / n)) for k in range(n)]


def stadium(cx, cy, half_len, r, n=10):
    pts = []
    for k in range(n + 1):
        a = -pi / 2 + pi * k / n
        pts.append((cx + half_len + r * cos(a), cy + r * sin(a)))
    for k in range(n + 1):
        a = pi / 2 + pi * k / n
        pts.append((cx - half_len + r * cos(a), cy + r * sin(a)))
    return pts


def rrect(hw, hh, r, ns=8, cx=0.0, cy=0.0):
    pts = []
    for (cu, cv, a0) in ((hw - r, hh - r, 0), (-(hw - r), hh - r, pi / 2),
                         (-(hw - r), -(hh - r), pi), (hw - r, -(hh - r), 1.5 * pi)):
        for k in range(ns + 1):
            a = a0 + pi / 2 * k / ns
            pts.append((cx + cu + r * cos(a), cy + cv + r * sin(a)))
    return pts


def sweep(bm, path, radius, mi, sides=10, closed=False, plane_n=None):
    """圆截面沿路径扫掠（导线、天线、竞速门）"""
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


def set_engine(kind):
    sc = bpy.context.scene
    if kind == 'EEVEE':
        for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
            try:
                sc.render.engine = eng
                return eng
            except Exception:
                continue
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 48
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
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
    return 'CYCLES'

# ---------------------------------------------------------------- 几何工具（补充）
ROT = {
    'Z': Matrix.Identity(4),
    'X': Matrix.Rotation(pi / 2, 4, 'Y'),     # 局部 +Z → 世界 +X
    '-X': Matrix.Rotation(-pi / 2, 4, 'Y'),   # 局部 +Z → 世界 -X
    'Y': Matrix.Rotation(-pi / 2, 4, 'X'),    # 局部 +Z → 世界 +Y
    '-Y': Matrix.Rotation(pi / 2, 4, 'X'),    # 局部 +Z → 世界 -Y
}


def rev(bm, prof, mi, axis='X', c=(0, 0, 0), seg=48, b=0.0, closed=False):
    """回转体：prof = [(半径, 沿轴坐标), ...]，绕局部 Z 建好，再把局部 Z 转到 axis、原点挪到 c"""
    fs = revolve(bm, prof, mi, seg=seg, closed=closed, b=b)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def rod(bm, r, a0, a1, mi, axis='X', c=(0, 0, 0), seg=32):
    return rev(bm, [(0, a0), (r, a0), (r, a1), (0, a1)], mi, axis, c, seg)


def boxf(bm, lo, hi, mi):
    """按两个角点建长方体（毫米）"""
    c = [(a + b) * .5 for a, b in zip(lo, hi)]
    s = [b - a for a, b in zip(lo, hi)]
    box(bm, c, s, mi)


def disk(bm, r, c, axis, mi, h=.3, seg=20):
    """贴在表面上的薄圆片：沉孔、螺纹孔、内六角孔（深色）"""
    return rod(bm, r, 0, h, mi, axis, c, seg)


def knurl(bm, r, a0, a1, mi, axis='Z', c=(0, 0, 0), n=30, depth=.7):
    """滚花头：星形截面拉伸"""
    pts = []
    for k in range(n * 2):
        a = pi * k / n
        rr = r if k % 2 == 0 else r - depth
        pts.append((rr * cos(a), rr * sin(a)))
    fs = extrude(bm, [pts], a0, a1, mi)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def hull(pts):
    """二维凸包（单调链），逆时针"""
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]



# ---------------------------------------------------------------- 文字、线条（面板丝印、液晶段码、PCB 走线）
_FONT = []


def font():
    if not _FONT:
        f = None
        for p in (r'C:\Windows\Fonts\arialbd.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
            if os.path.exists(p):
                try:
                    f = bpy.data.fonts.load(p, check_existing=True)
                    break
                except Exception:
                    pass
        _FONT.append(f)
    return _FONT[0]


def text(bm, s, size, x, y, z, mi, align='CENTER', h=.08):
    """平放在 z 平面上的一行字（字底面在 z，厚 h），追加进 bm"""
    cu = bpy.data.curves.new('Txt', 'FONT')
    cu.body = s
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = h / 2
    cu.resolution_u = 3
    if font():
        cu.font = font()
    ob = bpy.data.objects.new('Txt', cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.transform(Matrix.Translation((x, y, z + h / 2)))
    for p in me.polygons:
        p.material_index = mi
    bm.from_mesh(me)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)


def flat(bm, loops, z, mi, h=.06):
    """贴在 z 平面上的薄片（印刷、段码、焊盘）"""
    return extrude(bm, loops, z, z + h, mi)


def ring2d(outer, inner):
    return [outer, inner[::-1]]


def strip_pts(p0, p1, w, ext=True):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    e = w / 2 if ext else 0
    a = (p0[0] - ux * e, p0[1] - uy * e)
    b = (p1[0] + ux * e, p1[1] + uy * e)
    nx, ny = -uy * w / 2, ux * w / 2
    return [(a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny), (b[0] + nx, b[1] + ny), (a[0] + nx, a[1] + ny)]


def polyline(bm, pts, w, z, mi, h=.035):
    for p0, p1 in zip(pts, pts[1:]):
        flat(bm, [strip_pts(p0, p1, w)], z, mi, h)


def hexagon(cx, cy, r, rot=0.0):
    return [(cx + r * cos(rot + k * pi / 3), cy + r * sin(rot + k * pi / 3)) for k in range(6)]


def triangle(cx, cy, s):
    h = s * math.sqrt(3) / 2
    return [(cx - s / 2, cy - h / 3), (cx + s / 2, cy - h / 3), (cx, cy + 2 * h / 3)]


def arc_ring(cx, cy, r0, r1, a0, a1, n=24):
    out = [(cx + r1 * cos(a0 + (a1 - a0) * k / n), cy + r1 * sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    inn = [(cx + r0 * cos(a1 - (a1 - a0) * k / n), cy + r0 * sin(a1 - (a1 - a0) * k / n)) for k in range(n + 1)]
    return out + inn



def make_materials():
    # 金属度都压在 0.55 以下：虚幻工作室里没有反射探针，金属度高的在虚幻里发黑（车床实测）
    P = principled
    return dict(
        chassis=P('M_Chassis_Steel', '#9aa0a6', .35, .45),
        chassis_dark=P('M_Chassis_Dark', '#2b2e33', .2, .5),
        lid=P('M_Lid_Steel', '#a9afb5', .35, .42),
        hole=P('M_Hole', '#0a0b0d', 0, .85),
        plastic=P('M_Plastic_Black', '#17181b', 0, .55),
        blade=P('M_Fan_Blade', '#202226', 0, .45),
        touch=P('M_Touch_Green', '#46b04f', 0, .5),
        label=P('M_Label_White', '#efefec', 0, .55),
        ink=P('M_Print_Black', '#151515', 0, .5),
        print_w=P('M_Print_White', '#f4f4f2', 0, .5),
        warn=P('M_Label_Yellow', '#f2c316', 0, .5),
        nv=P('M_Accent_Green', '#76b900', 0, .4),
        pcb=P('M_PCB_Green', '#1b5e3a', 0, .45),
        pcb_dark=P('M_PCB_Dark', '#173b2b', 0, .45),
        pcb_blue=P('M_PCB_Blue', '#1d3f73', 0, .45),
        trace=P('M_PCB_Trace', '#3f9a62', 0, .45),
        gold=P('M_Gold', '#d3ad4c', .5, .3),
        silk=P('M_Silkscreen', '#f2f2ee', 0, .6),
        copper=P('M_Copper', '#c4743c', .55, .32),
        alu=P('M_Aluminium_Fin', '#c6cace', .5, .38),
        alu_dark=P('M_Aluminium_Dark', '#55595f', .45, .42),
        nickel=P('M_Nickel', '#bfc3c8', .5, .3),
        chip=P('M_Chip_Epoxy', '#18191c', 0, .5),
        chip_mark=P('M_Chip_Marking', '#9a9ea3', 0, .6),
        die=P('M_Silicon_Die', '#3b4160', .3, .18),
        hbm=P('M_HBM', '#262a31', .2, .3),
        interposer=P('M_Interposer', '#6b6f78', .4, .3),
        substrate=P('M_Package_Substrate', '#3c6e4c', 0, .5),
        stiffener=P('M_Stiffener', '#b0b4b9', .5, .35),
        inductor=P('M_Inductor', '#8f949a', .45, .4),
        cap=P('M_Capacitor', '#2a2a2c', 0, .45),
        cap_top=P('M_Capacitor_Top', '#b8bcc0', .45, .35),
        slot_blue=P('M_DIMM_Slot_Blue', '#2a5db0', 0, .45),
        slot_black=P('M_Slot_Black', '#1a1a1c', 0, .5),
        latch=P('M_Latch_White', '#e6e6e3', 0, .5),
        psu=P('M_PSU_Case', '#8c9196', .45, .4),
        led_g=P('M_LED_Green', '#3be070', 0, .3),
        led_a=P('M_LED_Amber', '#f0a020', 0, .3),
        led_b=P('M_LED_Blue', '#3a86f0', 0, .3),
        ihs=P('M_CPU_IHS', '#c3c6ca', .5, .32),
        drive=P('M_Drive_Alu', '#b7bbc0', .45, .38),
        caddy=P('M_Drive_Caddy', '#2c2f34', 0, .5),
        cable=P('M_Cable_Black', '#141414', 0, .6),
        cr2032=P('M_Coin_Cell', '#cfd2d6', .5, .3),
    )


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 AIServer
OBJS = []           # dict(ob, ex, no)

# 零件号 → (中文名, 材料 / 规格, 作用)。信息牌上显示的就是这三行
INFO = {
    1: ('机箱', '镀锌钢板冲压 · 8U（355.6 mm 高）· 19 英寸机架挂耳',
        '整台服务器的骨架：前面是风扇墙和硬盘笼，后面上方是电源插槽和出风网孔，两侧有托盘导轨。'
        '拆机时它不动，其他零件都从它上面拿走。挂耳用螺丝固定在机柜立柱上，一个 42U 机柜一般只放 4 台这样的机器（散热和供电跟不上）。'),
    2: ('顶盖', '镀锌钢板 · 顶面贴维修示意图',
        '盖住整个机箱，除了防尘，更重要的是把风"关"在里面：风扇吸进来的冷风必须穿过散热片才能从后面出去，'
        '开着盖子跑，风会从上面漏掉，GPU 几分钟就过热降频。'),
    3: ('GPU 区风扇（热插拔）', '80 mm 双转子对旋风扇 · 12 V · 约 16000 rpm',
        '十个风扇排成两排，把冷风从前面吸进来、压过 8 块 GPU 的散热片。8 块 GPU 满载约 5.6 kW，热量几乎全靠这面风扇墙带走。'
        '前后两个转子反着转，风压更大；坏一个其他风扇自动提速，绿色把手一拉就能带电更换。'),
    4: ('CPU 区风扇（热插拔）', '80 mm 风扇 · 12 V',
        '给下层的 CPU、内存和网卡吹风。和 GPU 区是两个风道，互不抢风。'),
    5: ('NVMe 固态硬盘', 'U.2 2.5 英寸 · 7.68 TB · PCIe 5.0 ×4',
        '放训练数据和模型检查点（checkpoint）。训练时每隔一段时间把几百 GB 的模型状态存一份，断电或出错能从这里接着训。'
        'NVMe 直接走 PCIe 通道，一块盘就有约 10 GB/s 读速，8 块加起来喂数据才跟得上 GPU。'),
    6: ('前控制面板', 'ABS 面板 + 小 PCB · 电源键 / ID 灯 / USB',
        '电源键、状态灯（绿 = 正常、橙 = 告警）、定位灯（机房里按一下远程就能找到是哪台机器）、USB 口。'),
    7: ('电源模块（热插拔）', 'CRPS 3000 W · 钛金级效率 96 % · 54 V / 12 V 输出',
        '6 个电源，平时 4 个就够、2 个冗余（4+2）：任何两个坏了机器照常跑。整机满载约 10 kW，'
        '相当于 5 台家用空调同时开。每个电源自带风扇，把手一拉就能带电更换。'),
    8: ('配电板 PDB', '厚铜 PCB + 铜排',
        '6 个电源插在这块板上，输出并在一起，再经铜排送到 GPU 基板和主板。几百安培的电流靠厚铜层和铜排走，普通导线会发烫。'),
    9: ('GPU 托盘', '钢板冲压托盘 + 前拉手',
        '整个 GPU 部分装在这个托盘上，从机箱前面整体抽出来维修。托盘底板同时把上层 GPU 风道和下层 CPU 风道隔开。'),
    10: ('HGX 基板', '多层高速 PCB（约 20 层以上）· NVLink 走线',
         '8 块 GPU 和 4 颗 NVSwitch 都插在这块板上。浅绿色的线代表 NVLink 走线：每块 GPU 拉 18 条 NVLink 到 4 颗 NVSwitch，'
         '任意两块 GPU 之间都能以 900 GB/s 直接交换数据，8 块卡用起来像一块大 GPU。后端的接口经线缆连到下层主板的 PCIe 交换芯片。'),
    11: ('SXM5 模组载板', '高速 PCB · 背面两个高密度板对板连接器',
         'GPU 芯片不是插在 PCIe 插槽里，而是焊在这块载板上，再整块压在基板的两个连接器上（SXM 接口）。'
         '这样供电能到 700 W、NVLink 不用绕线，PCIe 显卡做不到。'),
    12: ('GPU 芯片（H100）', 'TSMC 4N 工艺 · 800 亿晶体管 · 芯片面积 814 mm² · CoWoS 封装',
         'AI 训练真正干活的地方：里面有 132 个 SM（流式多处理器），每个 SM 里的 Tensor Core 专门做矩阵乘法——'
         '神经网络的计算 90% 以上都是矩阵乘法。FP8 下每秒能算约 2000 万亿次。芯片下面那层灰色的是硅中介层（interposer），'
         '芯片和 6 颗 HBM 都坐在它上面，靠里面几千条极细的走线互连。'),
    13: ('HBM3 显存堆栈（一组 6 颗）', '8 层 DRAM 芯片垂直堆叠 · 硅通孔（TSV）互连 · 每颗 16 GB',
         '把 8 片内存芯片叠起来、用硅通孔从上到下打通，贴在 GPU 芯片旁边。离得近、位宽大（每颗 1024 位），'
         '6 颗（5 颗启用）合计 80 GB、带宽 3.35 TB/s，大约是普通显卡显存的 3 倍。大模型训练常常卡在"数据搬不过来"，所以 HBM 很关键。'),
    14: ('GPU 供电模块（VRM）', '多相 DrMOS 功率级 + 贴片电感',
         '基板送来的是 54 V / 12 V，GPU 芯片只要 0.7~1 V 左右，但电流高达 700 A 以上。这些功率级（黑色小方块）和电感（银色方块）'
         '分成几十相轮流开关，把电压降下来，电流平均分摊，单个元件才不会烧。'),
    15: ('GPU 散热器', '铜底均热板（Vapor Chamber）+ 铜热管 + 铝鳍片',
         '一块 GPU 满载 700 W，比电磁炉一个灶眼还热。铜底里是抽了真空的腔体，里面的水在芯片上方蒸发、到边上冷凝，'
         '把热量迅速铺开到整块底板；热管再把热量送上鳍片，风扇吹来的风从鳍片缝里带走热量。'),
    16: ('NVSwitch 芯片', 'NVLink 交换芯片 · 64 个 NVLink4 端口',
         '相当于 GPU 之间的"交换机"。4 颗 NVSwitch 把 8 块 GPU 全部互连，任意两块之间都能满速通信，'
         '多块卡一起训练一个大模型时，同步梯度（每一步都要做）就靠它。'),
    17: ('NVSwitch 散热器', '铝鳍片 + 铜底',
         '每颗 NVSwitch 也有几十瓦发热，用一个矮一点的散热器，同样被 GPU 区风扇的风吹着。'),
    19: ('PCIe 交换芯片', 'PCIe 5.0 交换芯片 · 带小散热片',
         '把 CPU 的 PCIe 通道"分叉"：每颗交换芯片连 2 块 GPU、2 张网卡和 NVMe 硬盘，让网卡可以直接把数据写进 GPU 显存'
         '（GPUDirect RDMA），不用先绕到 CPU 内存里，省时间也省 CPU。'),
    21: ('主板托盘', '钢板冲压托盘 + 后面板 + 拉手',
         '下层整块主板装在这个托盘上，从机箱后面整体抽出来。后面板上开着网卡、管理口、USB 的孔。'),
    22: ('主板（双路）', '多层 PCB · 2 个 LGA4677 插座 · 32 个内存插槽 · PCIe 5.0 插槽',
         '服务器的"指挥中心"：两颗 CPU、内存、网卡、硬盘、管理芯片都连在这块板上。CPU 旁边成排的银色方块是 CPU 供电电感，'
         '后部的黑色插槽是网卡用的 PCIe x16 插槽，中间几排小接口经线缆连到上层 GPU 基板。'),
    23: ('CPU 处理器', '至强级服务器 CPU · 56 核 · LGA4677 封装',
         '训练时 GPU 负责算，CPU 负责"打杂"：读硬盘、解码和预处理训练数据、调度任务、管网络。'
         '两颗 CPU 一共 112 核，数据预处理跟不上的话 GPU 就要空等。'),
    24: ('CPU 散热器', '铜底 + 4 根热管 + 铝鳍片 · 2U 高',
         'CPU 满载约 350 W。热管把热量从铜底送到上面的鳍片，CPU 区风扇的风从鳍片缝里吹过去带走。'),
    25: ('DDR5 内存条（一组 8 根）', 'DDR5-4800 RDIMM · 64 GB/根 · 带 ECC',
         '每颗 CPU 两边各 8 根，一共 32 根 2 TB。训练数据先读进内存、预处理好再送进 GPU。'
         '服务器内存带 ECC 纠错：每 64 位数据多存 8 位校验，偶尔有位翻转能自动纠正，几周不停机的训练不会因为一个比特出错而崩掉。'
         '中间的小芯片是 RCD（地址缓冲）和 PMIC（内存条自带的电源芯片）。'),
    26: ('400G 网卡（ConnectX-7）', 'PCIe 5.0 x16 · 1 × OSFP 400 Gb/s · InfiniBand / 以太网',
         '每块 GPU 配一张网卡，8 张合计 3.2 Tb/s。几十上百台服务器一起训练一个大模型时，每一步都要和其他机器交换梯度，'
         '网卡用 RDMA 直接读写对方 GPU 的显存，CPU 不用插手。'),
    27: ('OCP 3.0 网卡', '双口 25G 以太网 · OCP 3.0 小卡',
         '存储和管理用的普通网络：从共享存储读训练数据、给运维登录。和 GPU 训练用的 400G 网络分开，互不抢带宽。'),
    28: ('M.2 启动盘', 'M.2 2280 NVMe SSD · 960 GB',
         '装操作系统和驱动。两块做 RAID 1 镜像，坏一块照样开机。'),
    29: ('BMC 管理芯片', 'AST2600 · ARM 核心 + 独立网口',
         '服务器里的"小电脑"，只要插着电源就在运行，主机关机也能用：远程开关机、看温度和风扇转速、远程看屏幕、'
         '刷固件。机房里成百上千台机器，靠它不用人跑到机器前。'),
    30: ('CMOS 纽扣电池', 'CR2032 · 3 V 锂电池',
         '拔掉电源后给主板上的实时时钟和 BIOS 设置供电，几年换一次。'),
    31: ('TPM 安全模块', 'TPM 2.0 小板',
         '存加密密钥、校验开机过程有没有被篡改（安全启动），硬盘加密的钥匙也放在这里。'),
    33: ('PCH 芯片组', '平台控制芯片 + 小散热片',
         '管"慢速"设备：USB、SATA、BIOS 闪存、BMC 的连接等。高速的内存和 PCIe 已经直接连在 CPU 上了。'),
    35: ('硬盘背板', 'PCB · 8 个 U.2 插座',
         '硬盘插进来就接上了电和 PCIe 信号，不用接线；背板再经线缆连到主板。所以硬盘能从前面直接拔插（热插拔）。'),
}


def finish(name, no, bm, mats, ex=(), bevel=0.0, seg=2, angle=50, smooth=34, post=None, mtx=None):
    """bm 里是毫米坐标的零件。mtx：建好后整体变换（局部坐标里建的零件，比如竖着的网卡、朝前的风扇）"""
    if mtx is not None:
        bmesh.ops.transform(bm, matrix=mtx, verts=bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('AIServer').objects.link(ob)
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
        bpy.data.meshes.remove(old)
        new.name = name
    if post:
        b2 = bmesh.new()
        b2.from_mesh(ob.data)
        post(b2)
        if mtx is not None:
            pass
        b2.to_mesh(ob.data)
        b2.free()
        shade(ob.data, smooth)
    ob.data.transform(Matrix.Scale(MM, 4))
    ob.parent = ROOT
    ob['name_cn'] = INFO[no][0]
    OBJS.append(dict(ob=ob, ex=[tuple(e) for e in ex], no=no))
    return ob


def frame(cx, cy, cz, kind):
    """局部坐标 → 世界坐标的矩阵（毫米）。
    'front'：局部 XY 是迎风面、+Z 往机箱里（-Y 朝前的风扇、硬盘面板）：(x, y, z) → (cx - x, cy + z, cz + y)
    'cardx'：竖着插的板卡，局部 X 沿 +Y、局部 Y 朝上、局部 Z 沿 +X：(x, y, z) → (cx + z, cy + x, cz + y)"""
    if kind == 'front':
        return Matrix(((-1, 0, 0, cx), (0, 0, 1, cy), (0, 1, 0, cz), (0, 0, 0, 1)))
    return Matrix(((0, 0, 1, cx), (1, 0, 0, cy), (0, 1, 0, cz), (0, 0, 0, 1)))


def fins(bm, x0, x1, y0, y1, z0, z1, pitch, t, mi):
    """一排竖直鳍片（片面平行于 YZ，沿 X 排开；风沿 Y 方向从片缝里吹过）"""
    n = max(2, int((x1 - x0 - t) / pitch) + 1)
    step = (x1 - x0 - t) / (n - 1)
    for k in range(n):
        x = x0 + k * step
        boxf(bm, (x, y0, z0), (x + t, y1, z1), mi)


def hole_grid(x0, x1, y0, y1, r, pitch, n=10, stagger=True):
    """矩形区域里的一片圆孔（返回孔轮廓列表），stagger = 蜂窝错位排"""
    out = []
    rows = int((y1 - y0) / (pitch * .866)) if stagger else int((y1 - y0) / pitch)
    cols = int((x1 - x0) / pitch)
    dy = pitch * .866 if stagger else pitch
    for j in range(rows):
        off = pitch / 2 if (stagger and j % 2) else 0
        for i in range(cols):
            cx = x0 + pitch / 2 + i * pitch + off
            cy = y0 + dy / 2 + j * dy
            if cx + r < x1 and cy + r < y1:
                out.append(circle(cx, cy, r, n)[::-1])
    return out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def screw_head(bm, x, y, z, r, mi_head, mi_slot, up=True):
    """平放的十字盘头螺丝头"""
    rev(bm, [(0, 0), (r, 0), (r * .92, r * .55), (0, r * .62)], mi_head, 'Z', (x, y, z), seg=16, closed=False)
    boxf(bm, (x - r * .6, y - r * .12, z + r * .5), (x + r * .6, y + r * .12, z + r * .66), mi_slot)
    boxf(bm, (x - r * .12, y - r * .6, z + r * .5), (x + r * .12, y + r * .6, z + r * .66), mi_slot)


def smd_caps(bm, pts, z, r, h, mi_body, mi_top):
    """一排贴片电解电容（圆柱 + 银色顶）"""
    for x, y in pts:
        cyl(bm, r, z, z + h, mi_body, seg=14, cx=x, cy=y)
        cyl(bm, r * .8, z + h, z + h + .3, mi_top, seg=14, cx=x, cy=y)


# ---------------------------------------------------------------- 主要尺寸 (mm)
HW = 223.0             # 机箱半宽（446 mm）
YF, YR = -425.0, 425.0 # 前 / 后面板
H = 355.6              # 8U
PAN_Z = (176.0, 179.0) # GPU 托盘底板
BB_Z = (183.0, 185.6)  # HGX 基板
MZ_TOP = 193.0         # 基板上的 SXM 连接器顶面
SXM_Z = (193.0, 195.4) # SXM 载板
SUB_Z = 197.4          # 封装基板顶面
DIE_Z = 199.6          # GPU 芯片 / HBM 顶面
HS_Z0 = 200.4          # GPU 散热器底面
HS_Z1 = 340.0          # GPU 散热器顶面
GPU_X = (-157.5, -52.5, 52.5, 157.5)
GPU_Y = (-190.0, 110.0)
NVS_Y = -40.0
MB_Z = (10.0, 12.0)    # 主板
CPU_X = (-110.0, 110.0)
CPU_Y = -60.0
NIC_X = (-200.0, -181.0, -162.0, -143.0, 143.0, 162.0, 181.0, 200.0)
PSU_X = (-75.5, 0.0, 75.5)
PSU_Z = (190.0, 231.0)  # 两层电源的底面
PSU_Y = (240.0, 425.0)

# 爆炸路线（毫米，Blender 坐标；最后一个数 = 出场时刻 0~1）。拆机顺序和摆法：
#   1 掀顶盖（往上）  2 拔前面的风扇、硬盘、面板（往前）  3 电源从后面拔出再往上抬，配电板跟着往上
#   4 GPU 托盘先抬高、再整个往前抽出（到桌子左边），上面的散热器、GPU 模组、芯片、HBM 一层层往上浮
#   5 主板托盘从后面抽出（到桌子右边）再往里让一点，CPU 散热器、CPU、内存、网卡、各种小芯片往上浮
# 虚幻里服务器转 180°：前面板朝左手边、后面朝右手边、+X 那一侧朝着玩家（-X 往远处）
LID_UP = 520.0
GPU_TRAY = [(0, 0, 280, .18), (0, -500, 0, .40)]
MB_TRAY = [(0, 690, 0, .46), (-320, 0, 0, .90)]


def gpu_route(*more):
    return GPU_TRAY + list(more)


def mb_route(*more):
    return MB_TRAY + list(more)


# ---------------------------------------------------------------- 机箱
def build_chassis(M):
    mats = [M['chassis'], M['chassis_dark'], M['hole'], M['touch'], M['label'], M['ink']]
    bm = bmesh.new()
    boxf(bm, (-HW, YF, 0), (HW, YR, 1.5), 0)                       # 底板
    for s in (-1, 1):
        x0, x1 = sorted((s * HW, s * (HW - 1.5)))
        boxf(bm, (x0, YF, 1.5), (x1, YR, H - 3.5), 0)               # 侧板
        x0, x1 = sorted((s * (HW - 1.5), s * (HW - 7)))
        boxf(bm, (x0, YF + 10, H - 7), (x1, YR, H - 3.5), 0)        # 顶部翻边（顶盖压在上面）
        boxf(bm, (x0, YF + 80, PAN_Z[0] - 4), (x1, YR - 4, PAN_Z[0]), 1)   # GPU 托盘导轨
        boxf(bm, (x0, -250, 3), (x1, YR - 4, 6), 1)                 # 主板托盘导轨
        # 挂耳 + 把手
        x0, x1 = sorted((s * HW, s * (HW + 18)))
        boxf(bm, (x0, YF - 4, 2), (x1, YF, H - 6), 0)
        hx = s * (HW + 10)
        for z in (70.0, 285.0):
            rod(bm, 5, YF - 30, YF - 4, 1, 'Y', (hx, 0, z), seg=16)
        rod(bm, 5.5, 70 - 5, 285 + 5, 1, 'Z', (hx, YF - 30, 0), seg=16)
        for z in (30.0, H - 40):                                     # 挂耳上的机柜螺丝
            rod(bm, 4.5, YF - 6, YF - 4, 2, 'Y', (s * (HW + 9), 0, z), seg=14)
    # 上层风扇笼：横梁、竖隔板，后面一块带 10 个圆孔的隔板
    boxf(bm, (-HW + 1.5, YF, PAN_Z[0] - 2), (HW - 1.5, YF + 82, PAN_Z[0] + 2), 0)
    boxf(bm, (-HW + 1.5, YF, H - 9), (HW - 1.5, YF + 82, H - 3.5), 0)
    plate = [rect(-HW + 1.5, PAN_Z[0] + 2, HW - 1.5, H - 9)] + [circle(cx, cz, 37, 40)[::-1]
                                                                 for cx in FAN_X for cz in FAN_Z]
    extrude(bm, plate, YF + 82, YF + 84, 0, axis='Y')
    # 下层：风扇笼（右半边）+ 硬盘笼（左半边）+ 面板下面的进风网孔
    plate = [rect(4, 4, HW - 1.5, PAN_Z[0] - 4)] + [circle(cx, cz, 37, 40)[::-1] for cx in LFAN_X for cz in LFAN_Z]
    extrude(bm, plate, YF + 82, YF + 84, 0, axis='Y')
    boxf(bm, (-HW + 1.5, YF, 100), (-62, YF + 128, 102.5), 0)       # 硬盘笼顶板
    boxf(bm, (-HW + 1.5, YF, 1.5), (-62, YF + 128, 4), 0)
    boxf(bm, (-64.5, YF, 1.5), (-62, YF + 128, 100), 0)
    for k in range(9):                                              # 硬盘导轨
        x = -214.0 + 18 * k
        boxf(bm, (x - .6, YF + 6, 4), (x + .6, YF + 120, 9), 1)
        boxf(bm, (x - .6, YF + 6, 95), (x + .6, YF + 120, 100), 1)
    vent = [rect(-HW + 1.5, 103, -2, PAN_Z[0] - 4)] + hole_grid(-HW + 4, -70, 106, PAN_Z[0] - 7, 2.6, 7.5)
    extrude(bm, vent, YF, YF + 1.5, 0, axis='Y')
    vent = [rect(-60, 4, 2, 100)] + hole_grid(-58, 0, 7, 97, 2.6, 7.5)
    extrude(bm, vent, YF, YF + 1.5, 0, axis='Y')
    # 后面板上半部：电源插口 + 两边、上面的出风网孔
    back = ([rect(-HW + 1.5, PAN_Z[0], HW - 1.5, H - 3.5), rect(-114, PSU_Z[0] - 2, 114, PSU_Z[1] + 43)[::-1]]
            + hole_grid(-HW + 6, -118, PAN_Z[0] + 6, H - 10, 3.6, 10.5)
            + hole_grid(118, HW - 6, PAN_Z[0] + 6, H - 10, 3.6, 10.5)
            + hole_grid(-110, 110, PSU_Z[1] + 48, H - 10, 3.6, 10.5))
    extrude(bm, back, YR - 2, YR, 0, axis='Y')
    boxf(bm, (-HW + 1.5, YR - 30, PAN_Z[0] - 6), (HW - 1.5, YR, PAN_Z[0]), 0)   # 后面板横梁（主板托盘从下面抽出）

    def post(b):
        # 侧面的型号铭牌
        lb = bmesh.new()
        flat(lb, [rect(-60, -14, 60, 14)], 0, 4, h=.15)
        text(lb, 'HGX H100 8-GPU', 9, 0, 3, .15, 5)
        text(lb, '8U AI TRAINING SERVER', 5.5, 0, -8, .15, 5)
        bmesh.ops.transform(lb, matrix=Matrix(((0, 0, 1, HW), (1, 0, 0, -250), (0, 1, 0, 120), (0, 0, 0, 1))),
                            verts=lb.verts)
        me = bpy.data.meshes.new('tmp')
        lb.to_mesh(me)
        lb.free()
        b.from_mesh(me)
        bpy.data.meshes.remove(me)
    finish('P01_Chassis', 1, bm, mats, post=post)


FAN_X = (-172.0, -86.0, 0.0, 86.0, 172.0)   # GPU 区 10 个风扇：5 列 × 2 排
FAN_Z = (223.0, 309.0)
LFAN_X = (62.0, 160.0)                      # CPU 区 4 个风扇：2 × 2
LFAN_Z = (47.0, 131.0)


def build_lid(M):
    mats = [M['lid'], M['label'], M['ink'], M['warn'], M['nv'], M['chassis_dark']]
    bm = bmesh.new()
    boxf(bm, (-HW + .5, YF + 2, H - 3.5), (HW - .5, YR, H), 0)
    for s in (-1, 1):                                              # 两侧往下的翻边
        x0, x1 = sorted((s * (HW - .5), s * (HW - 2.5)))
        boxf(bm, (x0, YF + 2, H - 22), (x1, YR, H - 3.5), 0)
    for y in (-200.0, 0.0, 200.0):                                 # 冲压加强筋
        boxf(bm, (-200, y - 4, H), (200, y + 4, H + 1.2), 0)
    boxf(bm, (-30, YF + 6, H), (30, YF + 24, H + 4), 5)            # 前端的开盖拉扣
    boxf(bm, (-18, YF + 10, H + 4), (18, YF + 20, H + 5), 4)

    def post(b):
        flat(b, [rect(-150, 40, 150, 180)], H + .01, 1, h=.12)     # 维修示意图贴纸
        text(b, 'SERVICE GUIDE', 12, 0, 165, H + .13, 2)
        for i, (cx, cy) in enumerate(((-90, 120), (-30, 120), (30, 120), (90, 120))):
            flat(b, [rect(cx - 24, cy - 32, cx + 24, cy + 30)], H + .13, 2, h=.05)
            flat(b, [rect(cx - 22, cy - 30, cx + 22, cy + 28)], H + .18, 1, h=.05)
            text(b, f'GPU{i * 2}/{i * 2 + 1}', 7, cx, cy, H + .23, 2)
        text(b, '1  REMOVE FANS   2  PULL GPU TRAY   3  PULL CPU TRAY', 6.5, 0, 62, H + .13, 2)
        flat(b, [rect(-150, -170, -40, -120)], H + .01, 3, h=.12) # 黄色警告贴纸
        warn = triangle(-130, -145, 30)
        flat(b, ring2d(warn, triangle(-130, -145, 19)), H + .13, 2, h=.05)
        text(b, 'HOT SURFACE', 7, -85, -140, H + .13, 2)
        text(b, '10 kW', 7, -85, -155, H + .13, 2)
        flat(b, [rect(60, -170, 180, -120)], H + .01, 4, h=.12)   # 绿色品牌条
        text(b, 'HGX', 22, 120, -146, H + .13, 2)
    finish('P02_Lid', 2, bm, mats, post=post, bevel=.6, ex=[(0, 0, LID_UP, .00)])


def fan_mesh(M, size=80.0, depth=56.0, label='DUAL ROTOR'):
    """局部坐标：迎风面在 z = 0，往 +z 是机箱里；返回 bmesh 和材质表"""
    mats = [M['plastic'], M['blade'], M['touch'], M['nickel'], M['label'], M['ink'], M['led_g']]
    bm = bmesh.new()
    h = size / 2
    r = h - 3
    extrude(bm, [rrect(h, h, 4, 4), circle(0, 0, r, 40)[::-1]], 4, depth, 0)   # 风扇框
    extrude(bm, [rrect(h + 1.5, h + 1.5, 3, 3), rrect(h - 4, h - 4, 3, 3)[::-1]], 0, 4, 0)  # 前面的模组外框
    hub = 14.0
    for z0, z1, tw in ((7, depth / 2 - 2, 1), (depth / 2 + 2, depth - 4, -1)):     # 两个转子，反向
        cyl(bm, hub, z0, z1, 0, seg=24)
        for k in range(7):
            a = 2 * pi * k / 7
            bl = bmesh.ops.create_cube(bm, size=1.0)['verts']
            bmesh.ops.scale(bm, vec=Vector((r - hub - 1.5, 15, 1.4)), verts=bl)
            mtx = (Matrix.Rotation(a, 4, 'Z') @ Matrix.Translation(((r + hub) / 2, 0, (z0 + z1) / 2))
                   @ Matrix.Rotation(radians(55) * tw, 4, 'X'))
            bmesh.ops.transform(bm, matrix=mtx, verts=bl)
            for f in {f for v in bl for f in v.link_faces}:
                f.material_index = 1
        for k in range(4):                                          # 电机支架
            a = pi / 4 + pi / 2 * k
            p0 = Vector((hub * cos(a), hub * sin(a), z1 + 1))
            p1 = Vector(((r + 1) * cos(a), (r + 1) * sin(a), z1 + 1))
            sweep(bm, [p0, p1], 1.2, 0, sides=6)
    flat(bm, [circle(0, 0, hub * .8, 24)], 6.9 - .1, 4, h=.1)       # 轮毂标签（朝外那面）
    for rr in (11.0, 22.0, 33.0):                                   # 防护网
        sweep(bm, [Vector((rr * cos(2 * pi * k / 32), rr * sin(2 * pi * k / 32), -.5)) for k in range(32)],
              .7, 3, sides=5, closed=True)
    for k in range(4):
        a = pi / 4 + pi / 2 * k
        sweep(bm, [Vector((4 * cos(a), 4 * sin(a), -.5)), Vector(((r + 1) * cos(a), (r + 1) * sin(a), -.5))],
              .8, 3, sides=5)
    boxf(bm, (-14, h - 1, -6), (14, h + 3, 4), 2)                   # 绿色热插拔把手
    boxf(bm, (-14, h - 6, -6), (-10, h + 3, -2), 2)
    boxf(bm, (10, h - 6, -6), (14, h + 3, -2), 2)
    cyl(bm, 1.3, -1, 0, 6, seg=10, cx=h - 6, cy=-h + 6)              # 状态灯
    return bm, mats


def build_fans(M):
    k = 0
    for row, cz in enumerate(FAN_Z[::-1]):
        for cx in FAN_X:
            bm, mats = fan_mesh(M)
            finish(f'P03_GpuFan_{k + 1}', 3, bm, mats, ex=[(0, -130, 0, .04 + .006 * k)],
                   mtx=frame(cx, YF - 6, cz, 'front'))
            k += 1
    k = 0
    for cz in LFAN_Z[::-1]:
        for cx in LFAN_X:
            bm, mats = fan_mesh(M, depth=40)
            finish(f'P04_CpuFan_{k + 1}', 4, bm, mats, ex=[(0, -120, 0, .10 + .006 * k)],
                   mtx=frame(cx, YF - 6, cz, 'front'))
            k += 1


DRV_X = [-205.0 + 18 * k for k in range(8)]


def build_drives(M):
    mats = [M['drive'], M['caddy'], M['touch'], M['label'], M['ink'], M['led_g'], M['led_b'], M['gold'], M['hole']]
    for k, x in enumerate(DRV_X):
        bm = bmesh.new()
        # 局部：x 沿 +Y（往机箱里）、y 朝上、z 沿 +X（盘厚）
        boxf(bm, (6, 0, -7.5), (106, 69.85, 7.5), 0)                # 盘体（U.2 2.5"，15 mm 厚）
        boxf(bm, (106, 8, -5), (109, 42, 5), 1)                     # 后端 SFF-8639 接口
        boxf(bm, (106.5, 10, -2), (109.2, 40, 2), 7)
        boxf(bm, (-8, -3, -8.2), (6, 73, 8.2), 1)                   # 托架前面板
        extrude(bm, [rect(-8.2, 4, -8, 66)] + [circle(cy, cz, 1.2, 8)[::-1] for cy in (12, 18, 24, 30, 36, 42)
                                                for cz in (-4, 0, 4)], -8.4, -8.2, 8, axis='X')
        boxf(bm, (-12, 50, -6), (-8, 72, 6), 2)                     # 绿色拉杆
        cyl(bm, 1.2, -8.6, -8, 5, seg=10)
        xform(bm, [f for f in bm.faces if f.calc_center_median().x < -8.3 and f.calc_center_median().y < 2],
              Matrix.Identity(4))
        for cy, mi in ((62.0, 5), (56.0, 6)):                        # 状态灯（绿 = 在位，蓝 = 定位）
            rod(bm, 1.1, -8.8, -8, mi, '-X', (0, cy, -3.5 if mi == 5 else 3.5), seg=10)
        for s in (-1, 1):                                            # 托架侧轨
            boxf(bm, (0, -2, s * 7.5), (100, 4, s * 8.3), 1)

        def post(b):
            flat(b, [rect(20, 10, 96, 60)], 7.5, 3, h=.1)
            text(b, 'NVMe U.2', 7, 58, 46, 7.6, 4)
            text(b, '7.68 TB  PCIe 5.0', 5, 58, 32, 7.6, 4)
            text(b, f'BAY {k}', 6, 58, 18, 7.6, 4)
        # 标签印在 z = 7.5 面上，post 里文字朝 +z：先在局部建，统一变换
        post(bm)
        finish(f'P05_Drive_{k + 1}', 5, bm, mats, ex=[(0, -150, 0, .12 + .006 * k)],
               mtx=frame(x, YF - 4, 18, 'cardx'))


def build_backplane(M):
    mats = [M['pcb'], M['slot_black'], M['gold'], M['cap'], M['cap_top'], M['silk'], M['trace']]
    bm = bmesh.new()
    # 局部：x 沿 X（宽）、y 朝上、z 沿 +Y（厚）
    boxf(bm, (-216, 6, 0), (-66, 98, 1.6), 0)
    for x in DRV_X:
        boxf(bm, (x - 7, 26, -6), (x + 7, 60, 0), 1)                # U.2 插座（朝前）
        boxf(bm, (x - 4, 28, -6.2), (x + 4, 58, -5.9), 2)
    for k in range(4):
        boxf(bm, (-200 + 36 * k, 75, 1.6), (-180 + 36 * k, 86, 9), 1)   # 后面的线缆接口
    smd_caps(bm, [(-205 + 14 * k, 92) for k in range(10)], 1.6, 2.5, 5, 3, 4)
    for k in range(6):
        boxf(bm, (-214, 64 + k * 1.6, 1.6), (-70, 64.6 + k * 1.6, 1.65), 6)
    mtx = Matrix(((1, 0, 0, 0), (0, 0, 1, YF + 118), (0, 1, 0, 0), (0, 0, 0, 1)))
    finish('P35_Backplane', 35, bm, mats, ex=[(0, -95, 0, .20)], mtx=mtx)


def build_panel(M):
    mats = [M['plastic'], M['chassis_dark'], M['led_g'], M['led_a'], M['led_b'], M['hole'], M['print_w'], M['nickel']]
    bm = bmesh.new()
    # 局部（front 坐标）：x 向左为正（镜像）、y 朝上、z 往里
    boxf(bm, (-34, -28, 0), (34, 28, 3), 0)
    boxf(bm, (-30, -24, 3), (30, 24, 40), 1)                        # 面板后面的小 PCB 盒
    rev(bm, [(0, -2.5), (6, -2.5), (6.5, 0), (0, 0)], 7, 'Z', (14, 8, 0), seg=24)   # 电源键
    for x, mi in ((-2, 2), (-10, 3), (-18, 4)):
        cyl(bm, 1.6, -1, 0, mi, seg=10, cx=x, cy=12)
    rev(bm, [(0, -1.5), (3.5, -1.5), (3.5, 0), (0, 0)], 4, 'Z', (-26, 12, 0), seg=16)  # ID 键
    for x in (-18.0, 2.0):                                          # 两个 USB 口
        boxf(bm, (x - 7, -20, -.5), (x + 7, -13, 0), 7)
        boxf(bm, (x - 6, -19, -.6), (x + 6, -14, -.4), 5)

    def post(b):
        pass
    finish('P06_FrontPanel', 6, bm, mats, ex=[(0, -85, 0, .17)], mtx=frame(-30, YF - 4, 140, 'front'))


# ---------------------------------------------------------------- 电源 + 配电板
def build_psus(M):
    mats = [M['psu'], M['plastic'], M['hole'], M['led_g'], M['gold'], M['pcb'], M['label'], M['ink'], M['touch']]
    k = 0
    for z0 in PSU_Z:
        for x in PSU_X:
            bm = bmesh.new()
            y0, y1 = PSU_Y
            boxf(bm, (x - 36.5, y0 + 6, z0), (x + 36.5, y1, z0 + 39.5), 0)   # 外壳 73.5 × 39.5 × 185
            boxf(bm, (x - 30, y0, z0 + 10), (x + 30, y0 + 6, z0 + 13), 5)    # 金手指卡边
            for i in range(14):
                boxf(bm, (x - 28 + 4 * i, y0 - .1, z0 + 10.2), (x - 26 + 4 * i, y0 + 5, z0 + 12.8), 4)
            # 后端：风扇格栅、AC 插座、把手、灯
            face = ([rect(x - 36.5, z0, x + 36.5, z0 + 39.5)] + [circle(x - 14, z0 + 19.75, 16.5, 40)[::-1]])
            extrude(bm, face, y1, y1 + 1.5, 0, axis='Y')
            for rr in (6.0, 11.0, 15.5):
                sweep(bm, [Vector((x - 14 + rr * cos(2 * pi * j / 28), y1 + .8, z0 + 19.75 + rr * sin(2 * pi * j / 28)))
                           for j in range(28)], .6, 1, sides=5, closed=True)
            cyl(bm, 5, y1 - 20, y1 - 2, 1, seg=16, cx=x - 14, cy=0) if False else None
            rod(bm, 5.5, y1 - 20, y1 + .5, 1, 'Y', (x - 14, 0, z0 + 19.75), seg=16)   # 风扇轮毂
            boxf(bm, (x + 6, y1 + 1.5, z0 + 6), (x + 30, y1 + 10, z0 + 30), 1)       # C20 插座
            boxf(bm, (x + 9, y1 + 9.9, z0 + 10), (x + 27, y1 + 10.2, z0 + 26), 2)
            for zz in (z0 + 4, z0 + 35.5):                                          # 把手
                boxf(bm, (x + 32, y1 + 1.5, zz - 1.5), (x + 35, y1 + 22, zz + 1.5), 1)
            boxf(bm, (x + 31.5, y1 + 18, z0 + 3), (x + 35.5, y1 + 22, z0 + 37), 8)
            rod(bm, 1.4, y1 + 1.5, y1 + 2.3, 3, 'Y', (x + 21, 0, z0 + 34), seg=10)  # 状态灯
            for i in range(10):                                                      # 顶面散热孔条
                boxf(bm, (x - 30 + 6 * i, y1 - 40, z0 + 39.5), (x - 27 + 6 * i, y1 - 10, z0 + 39.6), 2)

            def post(b, x=x, z0=z0):
                flat(b, [rect(x - 30, y0 + 30, x + 30, y0 + 110)], z0 + 39.5, 6, h=.1)
                text(b, '3000 W', 10, x, y0 + 90, z0 + 39.6, 7)
                text(b, 'CRPS TITANIUM', 5, x, y0 + 72, z0 + 39.6, 7)
                text(b, f'PSU {k}', 7, x, y0 + 52, z0 + 39.6, 7)
            post(bm)
            finish(f'P07_PSU_{k + 1}', 7, bm, mats,
                   ex=[(0, 110, 0, .10 + .008 * k), (0, 0, 220, .17 + .008 * k)])
            k += 1


def build_pdb(M):
    mats = [M['pcb_dark'], M['copper'], M['slot_black'], M['gold'], M['cap'], M['cap_top'], M['silk']]
    bm = bmesh.new()
    z0 = PAN_Z[0] + 1
    boxf(bm, (-HW + 8, PSU_Y[0] - 4, z0), (HW - 8, YR - 6, z0 + 2.4), 0)
    for x in PSU_X:                                                 # 电源插座（两层电源各一排）
        boxf(bm, (x - 32, PSU_Y[0] - 4, z0 + 2.4), (x + 32, PSU_Y[0] + 3, z0 + 12), 2)
    for s in (-1, 1):                                               # 铜排：往前接到 GPU 基板
        for i in range(2):
            x = s * (150 + 16 * i)
            boxf(bm, (x - 5, PSU_Y[0] - 20, z0 + 2.4), (x + 5, YR - 20, z0 + 5.4), 1)
            for yy in (PSU_Y[0] + 20, YR - 30):
                cyl(bm, 3.2, z0 + 5.4, z0 + 7, 3, seg=12, cx=x, cy=yy)
    smd_caps(bm, [(-100 + 20 * i, 330) for i in range(11)], z0 + 2.4, 5, 12, 4, 5)
    smd_caps(bm, [(-90 + 20 * i, 360) for i in range(10)], z0 + 2.4, 5, 12, 4, 5)

    def post(b):
        text(b, 'PDB  54V / 12V', 9, 0, 400, z0 + 2.4, 6)
    post(bm)
    finish('P08_PDB', 8, bm, mats, ex=[(0, 0, 190, .26)])


# ---------------------------------------------------------------- GPU 托盘
def build_gpu_tray(M):
    mats = [M['chassis'], M['chassis_dark'], M['touch'], M['hole'], M['label'], M['ink']]
    bm = bmesh.new()
    y0, y1 = -332.0, 236.0
    boxf(bm, (-HW + 8, y0, PAN_Z[0]), (HW - 8, y1, PAN_Z[1]), 0)
    for s in (-1, 1):
        x0, x1 = sorted((s * (HW - 8), s * (HW - 10)))
        boxf(bm, (x0, y0, PAN_Z[1]), (x1, y1, PAN_Z[1] + 22), 0)       # 侧边翻边
        x0, x1 = sorted((s * (HW - 7.6), s * (HW - 1.6)))
        boxf(bm, (x0, y0 + 40, PAN_Z[0] - 2), (x1, y1, PAN_Z[0] + 3), 1)   # 滑轨
    boxf(bm, (-HW + 8, y0, PAN_Z[1]), (HW - 8, y0 + 2, PAN_Z[1] + 12), 0)  # 前挡边
    for s in (-1, 1):                                               # 前面两个绿色拉手（风扇拆掉后才露出来）
        for z in (PAN_Z[1] + 3, PAN_Z[1] + 9):
            pass
        rod(bm, 3, y0 - 20, y0, 2, 'Y', (s * 150, 0, PAN_Z[1] + 6), seg=12)
        rod(bm, 3, y0 - 20, y0, 2, 'Y', (s * 110, 0, PAN_Z[1] + 6), seg=12)
        rod(bm, 3.4, s * 108 if s < 0 else 108, s * 152 if s < 0 else 152, 2, 'X', (0, y0 - 20, PAN_Z[1] + 6), seg=12)
    for x in (-190, -105, 0, 105, 190):                              # 基板铜柱
        for y in (-300, -40, 200):
            cyl(bm, 3, PAN_Z[1], BB_Z[0], 1, seg=12, cx=x, cy=y)
    finish('P09_GpuTray', 9, bm, mats, ex=gpu_route())


def build_baseboard(M):
    mats = [M['pcb'], M['trace'], M['slot_black'], M['gold'], M['silk'], M['cap'], M['cap_top'],
            M['inductor'], M['copper'], M['chip'], M['plastic']]
    bm = bmesh.new()
    y0, y1 = -322.0, 228.0
    z1 = BB_Z[1]
    boxf(bm, (-208, y0, BB_Z[0]), (208, y1, z1), 0)
    # NVLink 走线示意：每块 GPU 到 4 颗 NVSwitch
    for gx in GPU_X:
        for gy in GPU_Y:
            for k, nx in enumerate(GPU_X):
                p0 = (gx + (k - 1.5) * 9, gy + (-60 if gy > 0 else 60))
                p1 = (nx + (gx - nx) * .06 + (k - 1.5) * 3, NVS_Y + (24 if gy > 0 else -24))
                polyline(bm, [p0, (p0[0], (p0[1] + p1[1]) / 2), (p1[0], (p0[1] + p1[1]) / 2), p1], 1.1, z1, 1)
    # SXM 连接器（每块 GPU 两个）
    for gx in GPU_X:
        for gy in GPU_Y:
            for dy in (-40.0, 40.0):
                boxf(bm, (gx - 30, gy + dy - 6, z1), (gx + 30, gy + dy + 6, MZ_TOP), 2)
                boxf(bm, (gx - 28, gy + dy - 4, MZ_TOP - .1), (gx + 28, gy + dy + 4, MZ_TOP + .05), 3)
            for dx, dy in ((-36, -66), (36, -66), (-36, 66), (36, 66)):   # 模组的固定螺柱
                cyl(bm, 2.6, z1, MZ_TOP, 3, seg=12, cx=gx + dx, cy=gy + dy)
    # NVSwitch 插座区 + 供电
    for nx in GPU_X:
        boxf(bm, (nx - 28, NVS_Y - 28, z1), (nx + 28, NVS_Y + 28, z1 + .6), 3)
        for i in range(4):
            boxf(bm, (nx - 30 + 15 * i, NVS_Y + 33, z1), (nx - 20 + 15 * i, NVS_Y + 41, z1 + 5), 7)
    # 后端：电源输入、PCIe 线缆接口（到下层 PCIe 交换芯片）
    for s in (-1, 1):
        for i in range(2):
            x = s * (150 + 16 * i)
            boxf(bm, (x - 6, 196, z1), (x + 6, y1, z1 + 14), 10)
            boxf(bm, (x - 4, 198, z1 + 14), (x + 4, y1 - 2, z1 + 14.3), 8)
    for i in range(8):
        x = -105 + 30 * i
        boxf(bm, (x - 10, 200, z1), (x + 10, 214, z1 + 9), 2)
        boxf(bm, (x - 8, 213, z1 + 2), (x + 8, 214.2, z1 + 7), 3)
    smd_caps(bm, [(-200 + 16 * i, -310) for i in range(26)], z1, 3.2, 7, 5, 6)
    smd_caps(bm, [(-200 + 16 * i, 186) for i in range(26) if abs(-200 + 16 * i) > 125], z1, 3.2, 7, 5, 6)
    for i in range(10):
        boxf(bm, (-80 + 16 * i, 180, z1), (-70 + 16 * i, 190, z1 + 5), 7)
    boxf(bm, (-12, -6, z1), (12, 18, z1 + 2), 9)                     # 基板管理芯片（FPGA）

    def post(b):
        text(b, 'HGX H100 8-GPU BASEBOARD', 8, 0, 3, z1, 4)
        for i, gx in enumerate(GPU_X):
            for j, gy in enumerate(GPU_Y):
                text(b, f'GPU{j * 4 + i}', 6, gx, gy - 52 if gy > 0 else gy + 52, z1, 4)
    post(bm)
    finish('P10_HGXBaseboard', 10, bm, mats, ex=gpu_route((0, 0, 10, .98)))


def gpu_index_xy():
    out = []
    for gy in GPU_Y:
        for gx in GPU_X:
            out.append((gx, gy))
    return out


def build_gpus(M):
    for i, (gx, gy) in enumerate(gpu_index_xy()):
        n = i + 1
        lift = (0, 0, 95, .54 + .006 * i)
        # SXM 载板
        mats = [M['pcb_dark'], M['gold'], M['slot_black'], M['silk'], M['cap'], M['cap_top'], M['trace']]
        bm = bmesh.new()
        boxf(bm, (gx - 39, gy - 70.5, SXM_Z[0]), (gx + 39, gy + 70.5, SXM_Z[1]), 0)
        for dy in (-40.0, 40.0):                                     # 背面板对板连接器
            boxf(bm, (gx - 29, gy + dy - 5, SXM_Z[0] - 2.5), (gx + 29, gy + dy + 5, SXM_Z[0]), 2)
        for dx, dy in ((-36, -66), (36, -66), (-36, 66), (36, 66)):  # 四个固定孔
            rev(bm, [(1.6, SXM_Z[1]), (3.2, SXM_Z[1]), (3.2, SXM_Z[1] + .1), (1.6, SXM_Z[1] + .1)], 1, 'Z',
                (gx + dx, gy + dy, 0), seg=16, closed=True)
        smd_caps(bm, [(gx - 34 + 7 * k, gy + (-31 if k % 2 else 31) * 1.0) for k in range(0)], SXM_Z[1], 1, 1, 4, 5)
        for k in range(16):                                          # 去耦电容阵列（封装四周）
            a = 2 * pi * k / 16
            boxf(bm, (gx + 33 * cos(a) - 1, gy + 33 * sin(a) - .6, SXM_Z[1]),
                 (gx + 33 * cos(a) + 1, gy + 33 * sin(a) + .6, SXM_Z[1] + .8), 4)

        def post(b, gx=gx, gy=gy, n=n):
            text(b, 'H100 SXM5', 4.5, gx - 18, gy + 66, SXM_Z[1], 3)
            text(b, f'GPU {n - 1}', 4.5, gx + 22, gy + 66, SXM_Z[1], 3)
        post(bm)
        finish(f'P11_SXM_{n}', 11, bm, mats, ex=gpu_route(lift))

        # GPU 封装：基板 + 加强框 + 硅中介层 + 芯片
        mats = [M['substrate'], M['stiffener'], M['interposer'], M['die'], M['chip_mark'], M['cap']]
        bm = bmesh.new()
        boxf(bm, (gx - 30, gy - 30, SXM_Z[1]), (gx + 30, gy + 30, SUB_Z - .6), 0)
        extrude(bm, [rect(gx - 30, gy - 30, gx + 30, gy + 30), rect(gx - 27, gy - 27, gx + 27, gy + 27)[::-1]],
                SUB_Z - .6, SUB_Z + 1.2, 1)
        boxf(bm, (gx - 25, gy - 17, SUB_Z - .6), (gx + 25, gy + 17, SUB_Z + .4), 2)   # 硅中介层
        boxf(bm, (gx - 13, gy - 15.5, SUB_Z + .4), (gx + 13, gy + 15.5, DIE_Z), 3)    # GPU 芯片 26 × 31
        for k in range(12):                                          # 封装上的小电容
            boxf(bm, (gx - 24 + 4 * k, gy - 24, SUB_Z - .6), (gx - 22.5 + 4 * k, gy - 22, SUB_Z), 5)
            boxf(bm, (gx - 24 + 4 * k, gy + 22, SUB_Z - .6), (gx - 22.5 + 4 * k, gy + 24, SUB_Z), 5)

        def post(b, gx=gx, gy=gy):
            text(b, 'GH100', 4, gx, gy + 3, DIE_Z, 4, h=.03)
            text(b, '4N', 3, gx, gy - 4, DIE_Z, 4, h=.03)
        post(bm)
        finish(f'P12_GPU_{n}', 12, bm, mats, ex=gpu_route(lift, (0, 0, 30, .66 + .004 * i)))

        # HBM3：芯片左右各 3 颗
        for j, (dx, dy) in enumerate((sx * 19.5, sy * 11.0) for sx in (-1, 1) for sy in (-1, 0, 1)):
            mats = [M['hbm'], M['chip_mark']]
            bm = bmesh.new()
            boxf(bm, (gx + dx - 5.5, gy + dy - 5, SUB_Z + .4), (gx + dx + 5.5, gy + dy + 5, DIE_Z), 0)
            for L in range(7):                                       # 侧面看得见的 8 层叠片
                z = SUB_Z + .4 + (DIE_Z - SUB_Z - .4) * (L + 1) / 8
                boxf(bm, (gx + dx - 5.55, gy + dy - 5.05, z - .02), (gx + dx + 5.55, gy + dy + 5.05, z + .02), 1)
            finish(f'P13_HBM_G{n}{"ABCDEF"[j]}', 13, bm, mats,
                   ex=gpu_route(lift, (0, 0, 46, .70 + .004 * i)))

        # 供电模块：载板两端的功率级 + 电感
        mats = [M['inductor'], M['chip'], M['chip_mark'], M['cap'], M['cap_top']]
        bm = bmesh.new()
        for side in (-1, 1):
            for row in range(2):
                yy = gy + side * (40 + 12 * row)
                for c in range(8):
                    xx = gx - 31.5 + 9 * c
                    boxf(bm, (xx - 3.6, yy - 3.6, SXM_Z[1]), (xx + 3.6, yy + 3.6, SXM_Z[1] + 4.5), 0)
                    boxf(bm, (xx - 2.5, yy + side * 5.2 - 1.8, SXM_Z[1]), (xx + 2.5, yy + side * 5.2 + 1.8, SXM_Z[1] + 1), 1)
            smd_caps(bm, [(gx - 31 + 10.3 * c, gy + side * 65) for c in range(7)], SXM_Z[1], 2.4, 4, 3, 4)
        finish(f'P14_VRM_{n}', 14, bm, mats, ex=gpu_route(lift, (0, 0, 14, .62 + .004 * i)))

        # 散热器：铜底均热板 + 热管 + 铝鳍片 + 顶部绿条
        mats = [M['copper'], M['alu'], M['nickel'], M['nv'], M['alu_dark'], M['print_w'], M['plastic']]
        bm = bmesh.new()
        boxf(bm, (gx - 47, gy - 79, HS_Z0), (gx + 47, gy + 79, HS_Z0 + 7), 0)
        boxf(bm, (gx - 47, gy - 79, HS_Z0 + 7), (gx + 47, gy + 79, HS_Z0 + 9), 4)
        fins(bm, gx - 46.5, gx + 46.5, gy - 77, gy + 77, HS_Z0 + 9, HS_Z1 - 3, 2.9, .5, 1)
        for yy in (gy - 79, gy + 71):                                # 鳍片两头的扣条（顶面敞开，看得见鳍片）
            boxf(bm, (gx - 47, yy, HS_Z1 - 3), (gx + 47, yy + 8, HS_Z1), 4)
        boxf(bm, (gx - 47.2, gy - 12, HS_Z1 - 1.5), (gx + 47.2, gy + 12, HS_Z1 + .3), 3)   # 中间一条绿色压条
        for k, hx in enumerate((-30, -10, 10, 30)):                  # 4 根 U 形热管从铜底穿上鳍片
            pts = [Vector((gx + hx, gy - 60, HS_Z0 + 4)), Vector((gx + hx, gy - 70, HS_Z0 + 30)),
                   Vector((gx + hx, gy - 72, HS_Z1 - 20))]
            sweep(bm, catmull(pts, 5), 3, 0, sides=10)
            pts = [Vector((gx + hx, gy + 60, HS_Z0 + 4)), Vector((gx + hx, gy + 70, HS_Z0 + 30)),
                   Vector((gx + hx, gy + 72, HS_Z1 - 20))]
            sweep(bm, catmull(pts, 5), 3, 0, sides=10)
        for dx, dy in ((-36, -66), (36, -66), (-36, 66), (36, 66)):  # 弹簧螺丝
            rod(bm, 2.4, HS_Z0 - 4, HS_Z0 + 18, 2, 'Z', (gx + dx, gy + dy, 0), seg=12)
            rod(bm, 3.6, HS_Z0 + 18, HS_Z0 + 22, 6, 'Z', (gx + dx, gy + dy, 0), seg=16)

        def post(b, gx=gx, gy=gy, n=n):
            text(b, f'GPU{n - 1}', 6, gx, gy + 75, HS_Z1, 5)
            text(b, 'H100', 10, gx, gy, HS_Z1 + .3, 6)
        post(bm)
        finish(f'P15_GpuHeatsink_{n}', 15, bm, mats, ex=gpu_route((0, 0, 230, .45 + .008 * i)))


def build_nvswitch(M):
    for i, nx in enumerate(GPU_X):
        n = i + 1
        mats = [M['substrate'], M['die'], M['chip_mark'], M['stiffener'], M['cap']]
        bm = bmesh.new()
        z0 = BB_Z[1] + .6
        boxf(bm, (nx - 25, NVS_Y - 25, z0), (nx + 25, NVS_Y + 25, z0 + 2), 0)
        extrude(bm, [rect(nx - 25, NVS_Y - 25, nx + 25, NVS_Y + 25), rect(nx - 22, NVS_Y - 22, nx + 22, NVS_Y + 22)[::-1]],
                z0 + 2, z0 + 3.2, 3)
        boxf(bm, (nx - 12.5, NVS_Y - 12.5, z0 + 2), (nx + 12.5, NVS_Y + 12.5, z0 + 3.4), 1)
        for k in range(8):
            boxf(bm, (nx - 18 + 5 * k, NVS_Y - 20, z0 + 2), (nx - 16.5 + 5 * k, NVS_Y - 18.5, z0 + 2.6), 4)

        def post(b, nx=nx):
            text(b, 'NVSWITCH', 3.2, nx, NVS_Y + 2, z0 + 3.4, 2, h=.03)
        post(bm)
        finish(f'P16_NVSwitch_{n}', 16, bm, mats, ex=gpu_route((0, 0, 55, .60 + .006 * i)))

        mats = [M['copper'], M['alu'], M['alu_dark'], M['nickel'], M['print_w']]
        bm = bmesh.new()
        h0 = z0 + 3.6
        boxf(bm, (nx - 36, NVS_Y - 34, h0), (nx + 36, NVS_Y + 34, h0 + 5), 0)
        fins(bm, nx - 35.5, nx + 35.5, NVS_Y - 33, NVS_Y + 33, h0 + 5, h0 + 75, 2.7, .5, 1)
        boxf(bm, (nx - 36, NVS_Y - 34, h0 + 75), (nx + 36, NVS_Y + 34, h0 + 77), 2)
        for dx, dy in ((-31, -29), (31, -29), (-31, 29), (31, 29)):
            rod(bm, 2.2, h0 - 2, h0 + 8, 3, 'Z', (nx + dx, NVS_Y + dy, 0), seg=12)

        def post(b, nx=nx, h0=h0, n=n):
            text(b, f'NVSWITCH {n - 1}', 6, nx, NVS_Y, h0 + 77, 4)
        post(bm)
        finish(f'P17_NVSHeatsink_{n}', 17, bm, mats, ex=gpu_route((0, 0, 150, .50 + .008 * i)))


# ---------------------------------------------------------------- 主板托盘
MB_Y = (-238.0, 412.0)


def build_mb_tray(M):
    mats = [M['chassis'], M['chassis_dark'], M['touch'], M['hole'], M['label'], M['ink']]
    bm = bmesh.new()
    y0, y1 = -246.0, 419.0
    boxf(bm, (-HW + 8, y0, 3), (HW - 8, y1, 6), 0)
    for s in (-1, 1):
        x0, x1 = sorted((s * (HW - 8), s * (HW - 10)))
        boxf(bm, (x0, y0, 6), (x1, y1, 30), 0)
    for x in (-195, -110, 0, 110, 195):
        for y in (-220, 0, 200, 390):
            cyl(bm, 3, 6, MB_Z[0], 1, seg=12, cx=x, cy=y)
    # 后面板：8 个网卡口、OCP 口、管理口、USB、VGA
    holes = [rect(x - 8, 22, x + 8, 92)[::-1] for x in NIC_X]
    holes += [rect(-52, 26, 52, 44)[::-1], rect(-30, 100, -12, 114)[::-1], rect(-6, 100, 8, 106)[::-1],
              rect(14, 100, 28, 106)[::-1], rect(40, 98, 70, 110)[::-1]]
    holes += hole_grid(-120, -60, 60, 160, 2.5, 7) + hole_grid(60, 120, 60, 160, 2.5, 7)
    holes += hole_grid(-HW + 14, -112, 100, 165, 2.5, 7) + hole_grid(112, HW - 14, 100, 165, 2.5, 7)
    extrude(bm, [rect(-HW + 8, 3, HW - 8, PAN_Z[0] - 7)] + holes, y1, y1 + 2, 0, axis='Y')
    for s in (-1, 1):                                               # 后面两个拉手
        rod(bm, 4, y1 + 2, y1 + 24, 2, 'Y', (s * 120, 0, 130), seg=12)
        rod(bm, 4, y1 + 2, y1 + 24, 2, 'Y', (s * 120, 0, 85), seg=12)
        rod(bm, 4.5, 81, 134, 2, 'Z', (s * 120, y1 + 24, 0), seg=12)
    finish('P21_MbTray', 21, bm, mats, ex=mb_route())


DIMM_PITCH = 7.2


def dimm_xs(cx):
    s = 1 if cx > 0 else -1
    inner = [cx - s * (44 + DIMM_PITCH * i) for i in range(8)]
    outer = [cx + s * (44 + DIMM_PITCH * i) for i in range(8)]
    return inner, outer


def build_motherboard(M):
    mats = [M['pcb'], M['trace'], M['slot_black'], M['slot_blue'], M['latch'], M['inductor'], M['chip'],
            M['cap'], M['cap_top'], M['stiffener'], M['gold'], M['silk'], M['nickel']]
    bm = bmesh.new()
    z1 = MB_Z[1]
    boxf(bm, (-208, MB_Y[0], MB_Z[0]), (208, MB_Y[1], z1), 0)
    for cx in CPU_X:
        # LGA4677 插座：加强框 + 触点区
        extrude(bm, [rect(cx - 42, CPU_Y - 52, cx + 42, CPU_Y + 52), rect(cx - 31, CPU_Y - 41, cx + 31, CPU_Y + 41)[::-1]],
                z1, z1 + 4, 9)
        boxf(bm, (cx - 31, CPU_Y - 41, z1), (cx + 31, CPU_Y + 41, z1 + 2), 6)
        for dx, dy in ((-38, -48), (38, -48), (-38, 48), (38, 48)):
            cyl(bm, 2.4, z1 + 4, z1 + 14, 12, seg=12, cx=cx + dx, cy=CPU_Y + dy)
        # 内存插槽：交替蓝 / 黑
        for bank in dimm_xs(cx):
            for i, x in enumerate(bank):
                mi = 3 if i % 2 == 0 else 2
                boxf(bm, (x - 2.7, CPU_Y - 72, z1), (x + 2.7, CPU_Y + 72, z1 + 7), mi)
                for yy in (CPU_Y - 72, CPU_Y + 72):
                    boxf(bm, (x - 2.9, yy - 4 if yy < CPU_Y else yy, z1), (x + 2.9, yy if yy < CPU_Y else yy + 4, z1 + 12), 4)
        # CPU 供电电感（插座前后两排）
        for side in (-1, 1):
            for k in range(8):
                xx = cx - 31.5 + 9 * k
                boxf(bm, (xx - 3.8, CPU_Y + side * 82 - 3.8, z1), (xx + 3.8, CPU_Y + side * 82 + 3.8, z1 + 6), 5)
                boxf(bm, (xx - 2.5, CPU_Y + side * 92 - 2, z1), (xx + 2.5, CPU_Y + side * 92 + 2, z1 + 1), 6)
        smd_caps(bm, [(cx - 33 + 11 * k, CPU_Y + 102) for k in range(7)], z1, 3.2, 8, 7, 8)
    # 网卡用 PCIe x16 插槽
    for x in NIC_X:
        boxf(bm, (x - 3.5, 248, z1), (x + 3.5, 337, z1 + 11), 2)
        boxf(bm, (x - 3.7, 334, z1), (x + 3.7, 340, z1 + 13), 4)
    # OCP 接口、M.2 插座、MCIO（到 GPU 基板的线缆接口）
    boxf(bm, (-40, 326, z1), (40, 336, z1 + 8), 2)
    for x in (-25.0, 25.0):
        boxf(bm, (x - 11, 26, z1), (x + 11, 32, z1 + 4), 2)
        cyl(bm, 2, z1, z1 + 4, 12, seg=10, cx=x, cy=138)
    for k in range(8):
        x = -105 + 30 * k
        boxf(bm, (x - 10, 270, z1), (x + 10, 282, z1 + 9), 2)
        boxf(bm, (x - 8, 281.9, z1 + 2), (x + 8, 282.2, z1 + 7), 10)
    # 走线示意
    for cx in CPU_X:
        for k in range(6):
            polyline(bm, [(cx + (k - 2.5) * 6, CPU_Y + 52), (cx + (k - 2.5) * 6, 150), ((k - 2.5) * 12, 230), ((k - 2.5) * 12, 268)], 1, z1, 1)
    smd_caps(bm, [(-200 + 14 * i, 226) for i in range(29) if abs(-200 + 14 * i) > 130], z1, 3, 7, 7, 8)

    def post(b):
        text(b, 'DUAL SOCKET  LGA4677', 7, 0, 395, z1, 11)
        text(b, 'CPU0', 8, CPU_X[0], CPU_Y + 112, z1, 11)
        text(b, 'CPU1', 8, CPU_X[1], CPU_Y + 112, z1, 11)
        text(b, 'MCIO TO HGX', 5, 0, 292, z1, 11)
    post(bm)
    finish('P22_Motherboard', 22, bm, mats, ex=mb_route((0, 0, 12, .97)))


def build_cpus(M):
    for i, cx in enumerate(CPU_X):
        mats = [M['substrate'], M['ihs'], M['print_w'], M['ink'], M['cap']]
        bm = bmesh.new()
        z0 = MB_Z[1] + 2
        boxf(bm, (cx - 28.25, CPU_Y - 38.75, z0), (cx + 28.25, CPU_Y + 38.75, z0 + 1.6), 0)
        rev(bm, [(0, 0)], 0, 'Z') if False else None
        boxf(bm, (cx - 24, CPU_Y - 32, z0 + 1.6), (cx + 24, CPU_Y + 32, z0 + 2.4), 1)
        boxf(bm, (cx - 21, CPU_Y - 29, z0 + 2.4), (cx + 21, CPU_Y + 29, z0 + 5.2), 1)   # 顶盖 IHS
        for k in range(10):
            boxf(bm, (cx - 26.5, CPU_Y - 35 + 7 * k, z0 + 1.6), (cx - 25, CPU_Y - 33.5 + 7 * k, z0 + 2), 4)

        def post(b, cx=cx):
            text(b, 'XEON', 9, cx, CPU_Y + 8, z0 + 5.2, 3, h=.04)
            text(b, '56C  350W', 4.5, cx, CPU_Y - 6, z0 + 5.2, 3, h=.04)
            text(b, f'CPU{i}', 4.5, cx, CPU_Y - 18, z0 + 5.2, 3, h=.04)
        post(bm)
        finish(f'P23_CPU_{i + 1}', 23, bm, mats, ex=mb_route((0, 0, 70, .70 + .01 * i)))

        mats = [M['copper'], M['alu'], M['nickel'], M['alu_dark'], M['print_w'], M['plastic']]
        bm = bmesh.new()
        h0 = z0 + 5.2
        boxf(bm, (cx - 40, CPU_Y - 50, h0), (cx + 40, CPU_Y + 50, h0 + 6), 0)
        fins(bm, cx - 41.5, cx + 41.5, CPU_Y - 50, CPU_Y + 50, h0 + 22, h0 + 86, 2.4, .45, 1)
        boxf(bm, (cx - 42, CPU_Y - 51, h0 + 86), (cx + 42, CPU_Y + 51, h0 + 87.5), 3)
        for k, hx in enumerate((-24, -8, 8, 24)):                    # 4 根热管：铜底 → 鳍片
            pts = [Vector((cx + hx, CPU_Y - 20, h0 + 3)), Vector((cx + hx, CPU_Y - 40, h0 + 12)),
                   Vector((cx + hx, CPU_Y - 44, h0 + 40)), Vector((cx + hx, CPU_Y - 44, h0 + 82))]
            sweep(bm, catmull(pts, 5), 3, 0, sides=10)
            pts = [Vector((cx + hx, CPU_Y + 20, h0 + 3)), Vector((cx + hx, CPU_Y + 40, h0 + 12)),
                   Vector((cx + hx, CPU_Y + 44, h0 + 40)), Vector((cx + hx, CPU_Y + 44, h0 + 82))]
            sweep(bm, catmull(pts, 5), 3, 0, sides=10)
        for dx, dy in ((-38, -48), (38, -48), (-38, 48), (38, 48)):  # 4 颗压紧螺母
            rod(bm, 3.4, h0 + 6, h0 + 13, 5, 'Z', (cx + dx, CPU_Y + dy, 0), seg=6)

        def post(b, cx=cx):
            text(b, '1 3 2 4', 6, cx, CPU_Y, h0 + 87.5, 4)
        post(bm)
        finish(f'P24_CpuHeatsink_{i + 1}', 24, bm, mats, ex=mb_route((0, 0, 140, .62 + .01 * i)))


def build_dimms(M):
    banks = []
    for cx in CPU_X:
        banks += list(dimm_xs(cx))
    for b, xs in enumerate(banks):
        for i, x in enumerate(xs):
            mats = [M['pcb'], M['chip'], M['gold'], M['chip_mark'], M['label'], M['ink']]
            bm = bmesh.new()
            z0 = MB_Z[1] + 3
            y0, y1 = CPU_Y - 66.7, CPU_Y + 66.7
            boxf(bm, (x - .65, y0, z0), (x + .65, y1, z0 + 31.25), 0)
            boxf(bm, (x - .7, y0 + 2, z0), (x + .7, y1 - 2, z0 + 3), 2)    # 金手指
            for s in (-1, 1):
                for k in range(5):                                       # 每面 10 颗 DRAM 颗粒（中间留给 RCD）
                    for half in (-1, 1):
                        yy = CPU_Y + half * (16 + 11 * k)
                        boxf(bm, (x + s * .65, yy - 4.5, z0 + 8), (x + s * 1.55, yy + 4.5, z0 + 19), 1)
                boxf(bm, (x + s * .65, CPU_Y - 6.5, z0 + 9), (x + s * 1.9, CPU_Y + 6.5, z0 + 20), 1)   # RCD
            boxf(bm, (x + .65, CPU_Y - 4, z0 + 22), (x + 1.6, CPU_Y + 4, z0 + 27), 1)                  # PMIC
            boxf(bm, (x - 1.2, CPU_Y + 20, z0 + 21.5), (x - .65, CPU_Y + 60, z0 + 29), 4)              # 标签
            finish(f'P25_DIMM_{"ABCD"[b]}{i + 1}', 25, bm, mats,
                   ex=mb_route((0, 0, 60, .74 + .012 * b)))


def build_nics(M):
    for k, x in enumerate(NIC_X):
        mats = [M['pcb'], M['gold'], M['alu_dark'], M['nickel'], M['chip'], M['chassis'], M['print_w'],
                M['led_g'], M['plastic']]
        bm = bmesh.new()
        # 局部：x 沿 +Y（卡长），y 朝上，z 沿 +X（元件面朝 +X）
        L = 166.0
        boxf(bm, (0, 6, -.8), (L, 69, .8), 0)                       # 半高卡 PCB
        boxf(bm, (6, 0, -.85), (85, 6, .85), 1)                     # PCIe x16 金手指
        boxf(bm, (35, 18, .8), (95, 60, 2.8), 2)                    # 芯片散热片底座
        for j in range(12):
            boxf(bm, (35, 18 + 3.5 * j, 2.8), (95, 19.2 + 3.5 * j, 12), 2)
        boxf(bm, (98, 22, .8), (120, 56, 1.6), 4)
        boxf(bm, (128, 20, .8), (L + 1, 58, 14), 3)                 # OSFP 笼子
        boxf(bm, (L + .2, 0, -3), (L + 1.4, 82, 15), 5)             # 挡板（在后面板里面）
        boxf(bm, (L + 1.4, 22, -.5), (L + 2, 56, 14), 8)
        rod(bm, 1, L + 1.4, L + 2, 7, 'X', (0, 65, 7), seg=8)

        def post(b, k=k):
            pass
        bmx = bmesh.new()
        text(bmx, 'ConnectX-7', 6, 65, 0, 12.05, 6)
        bmx2 = bmx
        me = bpy.data.meshes.new('t')
        bmx2.to_mesh(me)
        bmx2.free()
        me.transform(Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1))) if False else Matrix.Identity(4))
        # 字印在散热片顶面（z = 12，朝 +z），文字本身沿局部 x 方向
        me.transform(Matrix.Translation((0, 39, 0)))
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        finish(f'P26_NIC_{k + 1}', 26, bm, mats, ex=mb_route((0, 0, 100, .78 + .007 * k)),
               mtx=frame(x - 4 if x > 0 else x + 4, 251, MB_Z[1] + 4, 'cardx') if x < 0 else
               frame(x + 4, 251, MB_Z[1] + 4, 'cardx') @ Matrix.Scale(-1, 4, Vector((0, 0, 1))))


def build_small_parts(M):
    z1 = MB_Z[1]
    # OCP 3.0 网卡
    mats = [M['pcb'], M['nickel'], M['alu_dark'], M['chassis'], M['gold'], M['print_w'], M['led_g']]
    bm = bmesh.new()
    boxf(bm, (-48, 336, z1 + 12), (48, 417, z1 + 13.6), 0)
    boxf(bm, (-40, 330, z1 + 9), (40, 337, z1 + 12), 4)
    for x in (-20.0, 20.0):
        boxf(bm, (x - 8, 395, z1 + 13.6), (x + 8, 418, z1 + 24), 1)
    boxf(bm, (-40, 345, z1 + 13.6), (0, 380, z1 + 16), 2)
    for j in range(8):
        boxf(bm, (-40 + 5 * j, 345, z1 + 16), (-38.8 + 5 * j, 380, z1 + 26), 2)
    boxf(bm, (-50, 416, z1 + 10), (50, 417.5, z1 + 30), 3)

    def post(b):
        text(b, 'OCP 3.0  2x25G', 5, 25, 360, z1 + 13.6, 5)
    post(bm)
    finish('P27_OCPNic', 27, bm, mats, ex=mb_route((0, 0, 60, .84)))
    # M.2 启动盘 × 2
    for i, x in enumerate((-25.0, 25.0)):
        mats = [M['pcb'], M['chip'], M['gold'], M['label'], M['ink']]
        bm = bmesh.new()
        boxf(bm, (x - 11, 30, z1 + 2.5), (x + 11, 140, z1 + 3.3), 0)
        boxf(bm, (x - 10, 26, z1 + 2.5), (x + 10, 30, z1 + 3.3), 2)
        for k in range(3):
            boxf(bm, (x - 8, 45 + 28 * k, z1 + 3.3), (x + 8, 66 + 28 * k, z1 + 4.5), 1)

        def post(b, x=x, i=i):
            flat(b, [rect(x - 9, 100, x + 9, 134)], z1 + 4.5, 3, h=.08)
            text(b, 'M.2', 5, x, 124, z1 + 4.6, 4)
            text(b, f'BOOT{i}', 3.5, x, 112, z1 + 4.6, 4)
        post(bm)
        finish(f'P28_M2_{i + 1}', 28, bm, mats, ex=mb_route((0, 0, 40, .86 + .01 * i)))
    # PCIe 交换芯片 × 4（带小散热片）
    for i, x in enumerate((-150.0, -70.0, 70.0, 150.0)):
        mats = [M['substrate'], M['chip'], M['alu_dark'], M['print_w']]
        bm = bmesh.new()
        y = 110.0
        boxf(bm, (x - 20, y - 20, z1), (x + 20, y + 20, z1 + 2), 0)
        boxf(bm, (x - 15, y - 15, z1 + 2), (x + 15, y + 15, z1 + 3.4), 1)
        boxf(bm, (x - 19, y - 19, z1 + 3.4), (x + 19, y + 19, z1 + 6), 2)
        fins(bm, x - 19, x + 19, y - 19, y + 19, z1 + 6, z1 + 22, 3.2, .8, 2)

        def post(b, x=x, y=y, i=i):
            text(b, f'PCIe SW{i}', 4, x, y - 25, z1, 3)
        post(bm)
        finish(f'P19_PCIeSwitch_{i + 1}', 19, bm, mats, ex=mb_route((0, 0, 45, .88 + .006 * i)))
    # PCH
    mats = [M['substrate'], M['chip'], M['alu_dark']]
    bm = bmesh.new()
    boxf(bm, (-15, 185, z1), (15, 215, z1 + 1.6), 0)
    boxf(bm, (-17, 183, z1 + 1.6), (17, 217, z1 + 4), 2)
    fins(bm, -17, 17, 183, 217, z1 + 4, z1 + 14, 3.4, .8, 2)
    finish('P33_PCH', 33, bm, mats, ex=mb_route((0, 0, 45, .92)))
    # BMC
    mats = [M['chip'], M['chip_mark'], M['substrate']]
    bm = bmesh.new()
    boxf(bm, (-92, 228, z1), (-68, 252, z1 + .8), 2)
    boxf(bm, (-89.5, 230.5, z1 + .8), (-70.5, 249.5, z1 + 2.2), 0)

    def post(b):
        text(b, 'AST2600', 3.2, -80, 242, z1 + 2.2, 1, h=.03)
        text(b, 'BMC', 3.2, -80, 236, z1 + 2.2, 1, h=.03)
    post(bm)
    finish('P29_BMC', 29, bm, mats, ex=mb_route((0, 0, 40, .93)))
    # CMOS 电池
    mats = [M['cr2032'], M['slot_black'], M['ink']]
    bm = bmesh.new()
    cyl(bm, 12, z1, z1 + 2.5, 1, seg=28, cx=62, cy=250)
    cyl(bm, 10, z1 + 2.5, z1 + 5.7, 0, seg=28, cx=62, cy=250)

    def post(b):
        text(b, 'CR2032', 3.2, 62, 250, z1 + 5.7, 2, h=.03)
    post(bm)
    finish('P30_CMOS', 30, bm, mats, ex=mb_route((0, 0, 40, .95)))
    # TPM（竖插的小板）
    mats = [M['pcb'], M['chip'], M['slot_black'], M['print_w']]
    bm = bmesh.new()
    boxf(bm, (98, 230, z1), (122, 238, z1 + 7), 2)
    boxf(bm, (100, 233.4, z1 + 7), (120, 235, z1 + 30), 0)
    boxf(bm, (104, 235, z1 + 14), (116, 236.2, z1 + 24), 1)
    finish('P31_TPM', 31, bm, mats, ex=mb_route((0, 0, 40, .94)))


# ---------------------------------------------------------------- 爆炸动画（和网页 / 虚幻同一个公式）
def ease(x):
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def prog(t, s):
    return ease(min(1.0, max(0.0, (t - s * .6) / .4)))


def animate_explode():
    for d in OBJS:
        ob, ex = d['ob'], d['ex']
        ob.location = (0, 0, 0)
        ob.keyframe_insert('location', frame=1)
        if not ex:
            continue
        for f in list(range(F_EXP[0], F_END + 1, 2)) + [F_END]:
            if f <= F_EXP[1]:
                t = (f - F_EXP[0]) / (F_EXP[1] - F_EXP[0])
                k = lambda s, t=t: prog(t, s)
            elif f < F_ASM[0]:
                k = lambda s: 1.0
            else:
                u = min(1.0, (f - F_ASM[0]) / (F_ASM[1] - F_ASM[0]))
                k = lambda s, u=u: prog(1 - u, s)
            v = Vector((0, 0, 0))
            for e in ex:
                v += Vector(e[:3]) * k(e[3])
            ob.location = v * MM
            ob.keyframe_insert('location', frame=f)


# ---------------------------------------------------------------- 相机 / 灯光
def look_at(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat('-Z', 'Y').to_euler()


def setup_world_and_cam(M):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, F_END
    sc.render.fps = 30
    w = bpy.data.worlds.new('World')
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes.get('Background') if w.node_tree else None
    if bg:
        bg.inputs[0].default_value = (*hexcol('#dfe3e8'), 1)
        bg.inputs[1].default_value = .25
    bm = bmesh.new()
    box(bm, (0, 0, -5), (5000, 5000, 10), 0)
    me = bpy.data.meshes.new('Table')
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Scale(MM, 4))
    me.materials.append(principled('M_Table', '#7a6650', 0, .6))
    table = bpy.data.objects.new('Table', me)
    collection('Scene').objects.link(table)
    for name, loc, power, size in (('Key', (1.8, -1.6, 2.4), 260, 2.0), ('Fill', (-1.6, -1.2, 1.4), 90, 2.4),
                                   ('Rim', (.4, 2.0, 1.8), 150, 1.6)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, (0, 0, .2))
        collection('Scene').objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 40
    cam = bpy.data.objects.new('Cam', cd)
    cam.location = (1.5, -1.2, 1.1)
    look_at(cam, (0, 0, .17))
    collection('Scene').objects.link(cam)
    sc.camera = cam
    return cam


def viewport_defaults():
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type != 'VIEW_3D':
                continue
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    try:
                        sp.shading.type = 'MATERIAL'
                        sp.region_3d.view_perspective = 'CAMERA'
                        sp.overlay.show_relationship_lines = False
                    except Exception:
                        pass


def render_still(name, frame, w=1280, h=720, cam=None, target=None):
    sc = bpy.context.scene
    if cam:
        sc.camera.location = cam
        look_at(sc.camera, target)
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.frame_set(frame)
    sc.render.filepath = os.path.join(OUT, name)
    try:
        sc.render.image_settings.file_format = 'PNG'
    except Exception:
        pass
    bpy.ops.render.render(write_still=True)
    print('[OK] rendered', name)


# ---------------------------------------------------------------- 导出 glb（虚幻工程 MyVRToyBox 用）
def export_glb(glb_path):
    sc = bpy.context.scene
    sc.frame_set(1)
    for ob in sc.objects:
        ob.select_set(False)
    for d in OBJS:
        ob = d['ob']
        cn, mat, desc = INFO[d['no']]
        ob['part_no'] = d['no']
        ob['name_cn'] = cn
        ob['material_spec'] = mat
        ob['desc'] = desc
        ob['ex'] = json.dumps([[e[0], e[2], -e[1], e[3]] for e in d['ex']])   # glTF 坐标 (x, z, -y)，mm
        ob.select_set(True)
    kw = dict(filepath=glb_path, export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
              export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ('export_animations', 'export_cameras', 'export_lights'):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    print('[OK] exported', glb_path)
    rows = [dict(name=d['ob'].name, no=d['no'], name_cn=INFO[d['no']][0], material=INFO[d['no']][1],
                 desc=INFO[d['no']][2], ex=d['ex']) for d in OBJS]
    with open(os.path.join(OUT, 'parts.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def main():
    global ROOT
    reset()
    M = make_materials()
    ROOT = bpy.data.objects.new('AIServer', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .1
    collection('AIServer').objects.link(ROOT)
    build_chassis(M)
    build_lid(M)
    build_fans(M)
    build_drives(M)
    build_backplane(M)
    build_panel(M)
    build_psus(M)
    build_pdb(M)
    build_gpu_tray(M)
    build_baseboard(M)
    build_gpus(M)
    build_nvswitch(M)
    build_mb_tray(M)
    build_motherboard(M)
    build_cpus(M)
    build_dimms(M)
    build_nics(M)
    build_small_parts(M)
    setup_world_and_cam(M)
    animate_explode()
    viewport_defaults()
    export_glb(os.path.join(OUT, 'ai_server.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'ai_server.blend'))
    print('[OK] saved ai_server.blend')
    tris = 0
    lo, hi = [1e9] * 3, [-1e9] * 3
    for d in OBJS:
        me = d['ob'].data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        for v in me.vertices:
            lo = [min(a, b) for a, b in zip(lo, v.co)]
            hi = [max(a, b) for a, b in zip(hi, v.co)]
    size = [round((b - a) * 1000, 1) for a, b in zip(lo, hi)]
    print(f'[OK] {len(OBJS)} server objects, {tris} triangles, size {size} mm')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_assembled.png', 1, cam=(1.3, -1.0, 1.0), target=(0, 0, .16))
        render_still('render_exploded.png', F_EXP[1] + 10, cam=(2.4, .1, 1.5), target=(0, .05, .3))
        render_still('render_gpu_tray.png', F_EXP[1] + 10, cam=(.9, -.75, 1.15), target=(0, -.45, .45))
        render_still('render_cpu_tray.png', F_EXP[1] + 10, cam=(.5, .9, .7), target=(-.1, .7, .05))
        set_engine('EEVEE')


main()
