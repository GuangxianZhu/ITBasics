# -*- coding: utf-8 -*-
"""
球形漂浮机器人 ORB-1（科幻原创）—— Blender 脚本建模 + 原理爆炸图

设定：直径 36 cm 的白色球形浮游机器人，悬停在一块停机加注坪上方。
动力路线是"真实骨架 + 科幻外皮"：
    液体燃料（航空煤油）→ 微型燃气涡轮发电机 → 电 → 球心竖直涵道里的共轴反转风扇往下吹气 → 升力；
    涵道出口的 6 片导流舵片偏转气流控制俯仰 / 横滚，赤道 4 个小喷口管偏航。
真实的部分：布雷顿循环涡轮发电、油电混动、共轴反转抵消扭矩、舵片偏流、IMU 闭环控制都是真实工程做法。
科幻的部分：把这一切塞进 36 cm 的球里还能长时间悬停（真机做不到这么小）、浮游光环、发光灯带。
每个零件的信息牌都标了【真实原理】或【科幻设定】。

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_orb_bot.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    orb_bot.blend   Blender 工程，按空格播放：第 1~120 帧拆开，第 150~270 帧装回
    orb_bot.glb     glTF 模型（单位米，每个零件一个节点，extras 里有零件号、中文名、材料、作用、爆炸路线），
                    虚幻工程 MyVRToyBox 的 Tools/import_model.py 直接导入
    parts.json      零件表
    render_*.png    加 --render 时用 Cycles 渲染预览图

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    +Z 向上，-Y 是正面（主眼），+X 是右侧（涡轮发电机），-X 是左侧（电子舱），+Y 是背面（电池、加注口）
    Z = 0 是停机坪底面；球心在 Z = 380（球底离坪面约 18 cm，"漂"着）
    所有零件都直接按装配位置建模（物体原点都在世界原点），爆炸动画只动物体位置

兼容: Blender 4.2 ~ 5.x（也能用 pip 装的 bpy 模块跑）
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


def principled(name, hexc, metal=0.0, rough=0.5, coat=0.0, alpha=1.0, trans=0.0, emit=0.0):
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
    if emit > 0:   # 自发光（灯带、光环）：glTF 导出成 emissive，虚幻导入后也会亮
        _put(b, ['Emission Color', 'Emission'], (*col, 1.0))
        _put(b, ['Emission Strength'], emit)
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



def fins(bm, x0, x1, y0, y1, z0, z1, pitch, t, mi):
    """一排竖直鳍片（片面平行于 YZ，沿 X 排开；风沿 Y 方向从片缝里吹过）"""
    n = max(2, int((x1 - x0 - t) / pitch) + 1)
    step = (x1 - x0 - t) / (n - 1)
    for k in range(n):
        x = x0 + k * step
        boxf(bm, (x, y0, z0), (x + t, y1, z1), mi)


def smd_caps(bm, pts, z, r, h, mi_body, mi_top):
    """一排贴片电解电容（圆柱 + 银色顶）"""
    for x, y in pts:
        cyl(bm, r, z, z + h, mi_body, seg=14, cx=x, cy=y)
        cyl(bm, r * .8, z + h, z + h + .3, mi_top, seg=14, cx=x, cy=y)




def make_materials():
    # 金属度都压在 0.55 以下：虚幻工作室里没有反射探针，金属度高的在虚幻里发黑（车床实测）
    P = principled
    return dict(
        shell=P('M_Shell_White', '#eceef0', 0, .32, coat=.4),
        orange=P('M_Accent_Orange', '#ff6a13', 0, .38, coat=.3),
        glow=P('M_Glow_Orange', '#ff7a1a', 0, .4, emit=8.0),
        graphite=P('M_Graphite', '#2c2f35', .2, .45),
        dark=P('M_Dark', '#131416', 0, .6),
        hole=P('M_Hole', '#07080a', 0, .9),
        ti=P('M_Titanium', '#a7abb1', .5, .34),
        steel=P('M_Steel_Dark', '#5b6067', .45, .4),
        alu=P('M_Aluminium', '#c4c8cc', .5, .36),
        hot=P('M_Inconel_Hot', '#7c6a5a', .5, .42),
        copper=P('M_Copper', '#c4743c', .55, .32),
        magnet=P('M_Magnet', '#3d4148', .4, .3),
        tank=P('M_Tank_Composite', '#e4e0d8', 0, .4, coat=.2),
        pcb=P('M_PCB_Black', '#15181c', 0, .45),
        chip=P('M_Chip', '#1b1c1f', 0, .5),
        gold=P('M_Gold', '#d3ad4c', .5, .3),
        inductor=P('M_Inductor', '#8f949a', .45, .4),
        glass=P('M_Lens_Glass', '#1a3550', .2, .05, coat=1.0),
        glass_dark=P('M_Sensor_Glass', '#0d1218', .1, .08, coat=1.0),
        die=P('M_Sensor_Die', '#3b4160', .3, .18),
        rubber=P('M_Rubber', '#1a1a1a', 0, .75),
        line=P('M_Braided_Line', '#a5aab0', .4, .5),
        ceramic=P('M_Ceramic', '#f2efe8', 0, .45),
        ink=P('M_Print_Dark', '#2a2c30', 0, .5),
    )


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 OrbBot
OBJS = []           # dict(ob, ex, no)
R_TAG, S_TAG, M_TAG = '【真实原理】', '【科幻设定】', '【真实原理 + 科幻缩小】'

# 零件号 → (中文名, 材料 / 规格, 作用)。信息牌上显示的就是这三行
INFO = {
    1: ('停机加注坪', '碳纤维底座 · 环形导引灯 · 底部燃油加注接口',
        S_TAG + '机器人不工作时停在这里加油、充电。坪面的橙色导引环给机器人的底部测高雷达当"降落靶"。'
        '爆炸图里它不动，机器人悬在它上方约 15 cm。'),
    2: ('赤道承力带（含 4 根辐条）', '钛合金环 + 碳纤维蒙皮 · 4 根辐条连到中央涵道',
        R_TAG + '整台机器人的"脊梁"：所有装甲瓣、燃料舱、涡轮和电子舱都挂在它和中央涵道上。'
        '4 根辐条把涵道里风扇的推力传到外环，所以推力是"推着骨架"走的，外壳只负责挡风。拆机时它不动。'),
    3: ('中央涵道', '碳纤维管 · 内径 124 mm · 上下翻边',
        R_TAG + '从球顶一直通到球底的竖直风道。风扇装在管子里面：桨尖和管壁间隙很小，桨尖不会"漏风"（桨尖涡），'
        '同样功率下推力比裸桨大 20~30%，而且转着的桨叶被包住了，靠近人也安全。'),
    4: ('主眼镜筒', '铝合金镜筒 + 球面眼眶',
        R_TAG + '固定主眼的镜片、光圈和图像传感器，保证它们同轴、间距准确（差零点几毫米就会对不上焦）。'),
    5: ('上装甲瓣', '白色碳纤维复合材料 · 橙色警示条 · 6 瓣',
        R_TAG + '球壳分成 6 瓣，每瓣单独拆下就能检修里面。球形外壳没有棱角，被风吹时受力均匀，撞到东西也会滑开。'
        '瓣与瓣之间留了 4 mm 缝，热胀冷缩不会顶在一起。'),
    6: ('下装甲瓣', '白色碳纤维复合材料 · 6 瓣',
        R_TAG + '和上半球一样分 6 瓣。下面两瓣开了孔，给测高雷达"看"地面。'),
    7: ('顶部进气格栅', '铝合金冲压 · 4 圈弧形进气缝',
        R_TAG + '涵道风扇从这里吸气。格栅挡住树叶、手指，开口面积要够大，不然风扇"吸不到气"，推力下降。'),
    8: ('底部出风格栅', '铝合金冲压 · 4 圈弧形出风缝',
        R_TAG + '风扇往下吹的气流从这里出去，产生向上的反作用力——这就是升力的来源（牛顿第三定律）。'),
    9: ('激光雷达环', '360° 固态激光雷达 · 深色滤光窗',
        R_TAG + '一圈 360° 测距：每秒几十万个激光点，算出周围墙壁、障碍物和人的距离，避障和建图都靠它。'),
    10: ('浮游光环', '白色陶瓷环 · 内圈橙色灯带 · 3 个节点',
         S_TAG + '绕着赤道斜挂的一圈光环，和机身没有任何连接——纯粹的科幻装饰（现实里没有能让它"自己漂着"的物理）。'
         '可以把它想成机器人的"状态指示器"：橙色常亮 = 正常悬停。'),
    11: ('赤道灯带', '导光条 + 橙色 LED · 3 段',
         S_TAG + '嵌在赤道凹槽里的发光带，告诉周围的人"它在工作"。现实中的无人机也有航行灯，这里做得更夸张。'),
    12: ('环形燃料舱', '碳纤维缠绕复合材料储罐 · 橙色箍带 · 3 段（前面留给主眼）',
         R_TAG + '燃料（航空煤油）装在绕赤道一圈的弧形舱里，重量均匀分布在一圈上，烧掉燃料时重心几乎不偏（卫星、火箭也爱用环形 / 球形储罐）。'
         '三段之间用跨接油管连通。拿起来想想开头的预测题：直接把燃料喷出去悬停，一分钟就要烧掉约 2 kg。'),
    13: ('加注管', '不锈钢波纹管 + 法兰',
         R_TAG + '从背后的加注口通到燃料舱。机器人停在加注坪上时，坪里的加注臂就从这里加油。'),
    14: ('加注口盖', '铝合金 · 橙色阳极氧化 · 带密封圈',
         R_TAG + '拧紧后密封，防止油气挥发。盖子是橙色的，一眼就能找到。'),
    15: ('液位传感器', '电容式液位探针',
         R_TAG + '测燃料还剩多少：探针在油里和在空气里电容不一样，飞控据此算剩余悬停时间，油不够了自动回坪。'),
    16: ('燃油滤清器', '不锈钢滤网 · 10 μm',
         R_TAG + '燃油先过滤再进泵：涡轮的喷油嘴孔只有零点几毫米，一粒灰就能堵住，一边喷不出油燃烧就会偏、烧坏涡轮。'),
    17: ('燃油泵', '无刷电机驱动的齿轮泵',
         R_TAG + '把燃油加压送去喷油嘴。泵的转速由飞控调：要更大推力就多送油、涡轮转得更快、发电更多。'),
    18: ('电磁截止阀', '常闭电磁阀 · 橙色线圈罩',
         R_TAG + '断电就关（常闭）：一旦失控或摔落，飞控断开它，燃油立刻停止供给，涡轮熄火——这是最重要的安全件。'),
    19: ('调压阀', '膜片式减压阀 · 橙色调节旋钮',
         R_TAG + '让送到喷油嘴的油压保持稳定。油压忽高忽低，喷出的油雾就不均匀，燃烧温度跟着乱跳。'),
    20: ('油管', '不锈钢编织软管 · 7 根（含 2 根跨接管）',
         R_TAG + '燃料舱 → 滤清器 → 泵 → 截止阀 → 调压阀 → 喷油嘴，一路串起来。两根跨接管把三段燃料舱连通，油面自动拉平。'),
    21: ('发电机定子', '硅钢片 + 铜绕组 · 带散热鳍',
         R_TAG + '涡轮带着转子高速旋转（每分钟十万转以上），转子的磁铁扫过这些铜线圈，感应出电——和自行车发电机同一个原理，只是转得快得多。'),
    22: ('发电机转子', '钐钴永磁体 + 碳纤维护套',
         R_TAG + '装在主轴上的永磁体。转速太高，磁铁会被离心力甩碎，所以外面要用碳纤维绑紧。'),
    23: ('进气口', '铝合金喇叭口',
         R_TAG + '把空气平顺地引进压气机。喇叭口的圆弧让气流不"撞墙"，进气阻力更小。'),
    24: ('压气机叶轮', '钛合金离心叶轮 · 12 片叶片',
         R_TAG + '布雷顿循环第 1 步：把空气甩到外圈压缩，压力升到 3~4 倍。空气越密，同样体积里能烧的燃料越多。'),
    25: ('环形燃烧室', '镍基高温合金 · 表面一圈圈稀释孔',
         R_TAG + '第 2 步：压缩空气和燃油在这里混合燃烧，温度上千度。外壁的小孔补进冷空气，把燃气温度降到涡轮叶片能承受的范围。'),
    26: ('喷油嘴（6 个，带环形油路）', '不锈钢 · 雾化孔径约 0.3 mm',
         R_TAG + '把燃油喷成细雾，雾越细烧得越快越干净。6 个均匀分布，火焰才不会偏到一边。'),
    27: ('点火器', '陶瓷绝缘火花塞',
         R_TAG + '启动时打火点燃油雾，火焰稳定后就关掉——之后燃烧室里的火是自己维持的。'),
    28: ('涡轮转子', '镍基高温合金 · 16 片叶片',
         R_TAG + '第 3 步：高温燃气冲过叶片推动它旋转。涡轮和压气机、发电机在同一根轴上：涡轮的力一部分带压气机，剩下的拿去发电。'),
    29: ('排气管', '高温合金 · 接到右上方的排气口',
         R_TAG + '第 4 步：做完功的燃气从这里排出机外。排气口开在侧上方，热气不会被风扇吸回去。'),
    30: ('主轴', '高强度合金钢',
         R_TAG + '把发电机、压气机、涡轮串在一起。转速极高，轴必须做"动平衡"，偏一点点都会剧烈振动。'),
    31: ('轴承', '陶瓷球轴承',
         R_TAG + '支撑主轴高速旋转。陶瓷球比钢球轻、耐热，适合十万转级别的转速。'),
    32: ('涡轮支架', '钛合金支架',
         R_TAG + '把涡轮发电机固定在骨架上，中间有减振垫，涡轮的振动不会传给相机。'),
    33: ('缓冲电池包', '锂电池 · 48 V 6 Ah',
         R_TAG + '涡轮加速需要一两秒，风扇却要在几毫秒内改推力。电池负责"救急"：突然要大推力时先放电顶上，涡轮跟上后再给电池充回去——油电混动汽车也是这个思路。'),
    34: ('上风扇', '7 叶碳纤维桨 · 顺时针',
         R_TAG + '和下风扇一起把空气往下压，产生升力。'),
    35: ('上电机', '外转子无刷电机',
         R_TAG + '带动上风扇。无刷电机靠电调按顺序给线圈通电，转速可以非常精确地调。'),
    36: ('电机支架', '铝合金中柱 + 4 根支臂',
         R_TAG + '把上下两个电机固定在涵道正中央，支臂做成薄片，挡风越少越好。'),
    37: ('下电机', '外转子无刷电机',
         R_TAG + '带动下风扇，和上电机反着转。'),
    38: ('下风扇', '5 叶碳纤维桨 · 逆时针',
         R_TAG + '为什么要两个反着转的风扇？风扇转起来，机身会被反作用力往反方向拧（直升机为此加了尾桨）。'
         '上下两个反转，扭矩互相抵消，机身就不会自转；下风扇还能把上风扇甩出来的"旋转气流"拉直，多拿一点推力。'),
    39: ('导流舵片', '碳纤维舵片 · 6 片',
         R_TAG + '装在涵道出口，偏转往下吹的气流：气流往左偏，机身就受到往右的力。6 片配合就能控制俯仰和横滚。'),
    40: ('舵机', '数字舵机 · 6 个',
         R_TAG + '转动舵片。飞控每秒几百次给它们下指令。'),
    41: ('偏航喷口', '小型引气喷口 · 4 个',
         R_TAG + '从涵道里引一点高压气从赤道喷出去，左右喷口一开一关，机身就原地转向（偏航）。'),
    42: ('电子舱支架', '碳纤维板 + 铜柱',
         R_TAG + '电子板一层层叠在这块板上，靠铜柱隔开，方便散热和拆装。'),
    43: ('电源管理板', '大电流 PCB · 电感 + 电容',
         R_TAG + '把发电机的电和电池的电合在一起，分配给风扇电机、舵机、传感器，并管理电池充放电。'),
    44: ('电调', '三相 MOSFET 驱动板 · 2 块',
         R_TAG + '一块管一个风扇电机：按顺序给电机三相线圈通电，让它转起来，并按飞控的指令调转速。'),
    45: ('散热片', '铝合金鳍片',
         R_TAG + '电调里的 MOSFET 开关大电流会发热，鳍片把热量散到涵道旁边的气流里。'),
    46: ('飞控板', '主控 MCU + 状态 LED',
         R_TAG + '机器人的"小脑"。悬停天生不稳定（推力跟着机身一起歪），必须每秒几百次读 IMU、算偏差、调舵片和转速，才能稳稳停在空中。'
         '注意"把重的放下面就稳"是错觉（钟摆谬误），真正让它稳的是这块板。'),
    47: ('IMU 惯性测量单元', '三轴陀螺仪 + 三轴加速度计',
         R_TAG + '感知机身的倾斜和转动。它就像人的内耳前庭：闭上眼也知道自己歪没歪。'),
    48: ('线束', '硅胶软线 · 橙色护套',
         R_TAG + '电调到涵道里两台电机的三相动力线。'),
    49: ('前镜片', '光学玻璃 · 镀增透膜',
         R_TAG + '主眼的第一片镜片，把光线收进来。'),
    50: ('光圈', '8 片钢制叶片',
         R_TAG + '叶片收拢或张开，控制进光量：太亮时缩小，暗处放大。和相机、人眼的瞳孔一样。'),
    51: ('中镜片', '光学玻璃',
         R_TAG + '多片镜片组合起来修正色差和畸变，单片镜片做不到边缘也清晰。'),
    52: ('后镜片', '光学玻璃',
         R_TAG + '把光线最终聚焦到图像传感器上。'),
    53: ('图像传感器', 'CMOS 传感器板',
         R_TAG + '把光变成电信号，就是机器人"看到"的画面。'),
    54: ('遮光罩', '白色复合材料 · 橙色前缘',
         R_TAG + '挡住侧面射来的杂光，画面不发白。'),
    55: ('眼圈光环', '橙色导光环',
         S_TAG + '主眼周围的发光环，让人知道"它正在看你"。'),
    56: ('立体相机', '广角相机 · 2 个',
         R_TAG + '两个相机隔开一段距离拍同一个场景，比较两张图的差别就能算出物体的远近——和人用两只眼睛判断距离一样。'),
    57: ('测高雷达', '毫米波测距模块 · 2 个',
         R_TAG + '朝下测离地高度，悬停时保持高度、降落时对准停机坪都靠它。'),
    58: ('天线', '数传 / 图传天线 · 2 根',
         R_TAG + '和遥控器、基站通信。两根天线方向不同，机身怎么转都至少有一根信号好。'),
}


def finish(name, no, bm, mats, ex=(), bevel=0.0, seg=2, angle=50, smooth=34, mtx=None):
    """bm 里是毫米坐标的零件。mtx：建好后整体变换（局部坐标里建的零件，比如主眼镜片、相机）"""
    if mtx is not None:
        bmesh.ops.transform(bm, matrix=mtx, verts=bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('OrbBot').objects.link(ob)
    shade(me, smooth)
    if bevel > 0:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = bevel
        md.segments = seg
        md.limit_method = 'ANGLE'
        md.angle_limit = radians(angle)
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        old = ob.data
        ob.modifiers.clear()
        ob.data = new
        bpy.data.meshes.remove(old)
        new.name = name
    ob.data.transform(Matrix.Scale(MM, 4))
    ob.parent = ROOT
    ob['name_cn'] = INFO[no][0]
    OBJS.append(dict(ob=ob, ex=[tuple(e) for e in ex], no=no))
    return ob


# ---------------------------------------------------------------- 球面工具
ZC = 380.0                       # 球心高度（停机坪底面 Z = 0）
CEN = Vector((0.0, 0.0, ZC))
R_IN, R_OUT = 171.0, 177.0       # 装甲瓣内外半径
R_BAND = (170.0, 182.0)          # 赤道承力带（比装甲瓣凸出 5 mm）
BAND_LAT = 12.0                  # 承力带上下边的纬度（±12°）
EYE_DIR = Vector((0.0, -1.0, 0.0))


def sdir(lat, lon):
    la, lo = radians(lat), radians(lon)
    return Vector((cos(la) * cos(lo), cos(la) * sin(lo), sin(la)))


def spt(r, lat, lon):
    return CEN + r * sdir(lat, lon)


def pol(r, lon, z):
    """柱坐标点：半径 r、方位角 lon（度）、高度 z（相对球心）"""
    return Vector((r * cos(radians(lon)), r * sin(radians(lon)), ZC + z))


def orient(d, c):
    """局部 +Z → 方向 d，局部原点 → c"""
    q = Vector((0, 0, 1)).rotation_difference(Vector(d).normalized())
    return Matrix.Translation(Vector(c)) @ q.to_matrix().to_4x4()


def rev_d(bm, prof, mi, d, c, seg=48, closed=False):
    fs = revolve(bm, prof, mi, seg=seg, closed=closed)
    xform(bm, fs, orient(d, c))
    return fs


def ang(la, lo, d):
    """球面上 (la, lo) 方向和向量 d 的夹角（度）"""
    return math.degrees(sdir(la, lo).angle(Vector(d).normalized()))


def sph_grid(bm, r0, r1, lat0, lat1, lon0, lon1, mat_fn, step=1.5, lat_step=None):
    """球面上的一块有厚度的壳（内半径 r0、外半径 r1），按经纬网格划分。
    mat_fn(纬度, 经度) 返回这一格的材质序号，返回 None 就挖掉（开孔、开缝），挖开的地方自动补侧壁"""
    wrap = abs(lon1 - lon0 - 360) < 1e-6
    nlo = max(1, round((lon1 - lon0) / step))
    nla = max(1, round((lat1 - lat0) / (lat_step or step)))
    V = {}

    def lat_of(j):
        return lat0 + (lat1 - lat0) * j / nla

    def vert(i, j, k):
        if wrap:
            i %= nlo
        la = lat_of(j)
        key = ('pole', j, k) if abs(abs(la) - 90) < 1e-6 else (i, j, k)
        if key not in V:
            V[key] = bm.verts.new(spt((r0, r1)[k], la, lon0 + (lon1 - lon0) * i / nlo))
        return V[key]

    cells = {}
    for i in range(nlo):
        for j in range(nla):
            m = mat_fn(lat0 + (lat1 - lat0) * (j + .5) / nla, lon0 + (lon1 - lon0) * (i + .5) / nlo)
            if m is not None:
                cells[(i, j)] = m

    def has(i, j):
        if wrap:
            i %= nlo
        return (i, j) in cells

    fs = []

    def face(vs, m):
        out = []
        for v in vs:
            if v not in out:
                out.append(v)
        if len(out) < 3:
            return
        try:
            f = bm.faces.new(out)
        except ValueError:
            return
        f.material_index = m
        fs.append(f)

    for (i, j), m in cells.items():
        face([vert(i, j, 1), vert(i + 1, j, 1), vert(i + 1, j + 1, 1), vert(i, j + 1, 1)], m)
        face([vert(i, j + 1, 0), vert(i + 1, j + 1, 0), vert(i + 1, j, 0), vert(i, j, 0)], m)
        for (ni, nj, a, b) in ((i - 1, j, (i, j), (i, j + 1)), (i + 1, j, (i + 1, j), (i + 1, j + 1)),
                               (i, j - 1, (i, j), (i + 1, j)), (i, j + 1, (i, j + 1), (i + 1, j + 1))):
            if (not wrap and not 0 <= ni < nlo) or not 0 <= nj < nla or not has(ni, nj):
                face([vert(*a, 1), vert(*b, 1), vert(*b, 0), vert(*a, 0)], m)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def to_bm(bm, other):
    """把另一个 bmesh 合进 bm（局部坐标建好、变换过的小零件）"""
    me = bpy.data.meshes.new('tmp')
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def local_part(bm, build, mtx):
    """在局部坐标里建一块（build(b)），变换 mtx 后合进 bm"""
    b = bmesh.new()
    build(b)
    bmesh.ops.transform(b, matrix=mtx, verts=b.verts)
    to_bm(bm, b)


# 球面上的开孔位置（纬度, 经度）
EXHAUST = (30.0, 30.0)
FILLER = (40.0, 105.0)
ANTENNAS = ((56.0, 72.0), (56.0, 108.0))
ALTIS = ((-58.0, 30.0), (-58.0, 210.0))
CAMS = ((7.0, -52.0), (7.0, -128.0))
NOZZLES = ((-7.0, 45.0), (-7.0, 135.0), (-7.0, -45.0), (-7.0, -135.0))
EYE_HOLE = 17.0


def holes_fn(holes):
    """holes: [(方向向量, 半角)]；返回判断"这一格在不在孔里"的函数"""
    def inside(la, lo):
        return any(ang(la, lo, d) < a for d, a in holes)
    return inside


# ---------------------------------------------------------------- 爆炸路线（毫米，Blender 坐标；最后一个数 = 出场时刻 0~1）
# 拆机顺序：光环上浮 → 外面的小件（口盖、天线、相机、喷口、灯带）→ 顶 / 底格栅、雷达环 → 12 片装甲瓣 → 主眼镜片往前一片片排开
# → 下半球的油路 → 电池、涡轮发电机（往右）、电子舱（往左）→ 风扇、电机、舵片沿涵道上下抽出 → 燃料舱最后往上提
# 赤道承力带、涵道、主眼镜筒和停机坪不动（基座）。燃料舱在承力带高度里，只能往上提；其他东西都从承力带上下方进出
def radial(lon, d, z=0.0, s=0.0):
    return (d * cos(radians(lon)), d * sin(radians(lon)), z, s)


def along(v, d, s):
    v = Vector(v).normalized() * d
    return (v.x, v.y, v.z, s)


TURB = [(170, 110, 0, .32)]      # 往右再往后让：右手边靠前是虚幻工作室的触屏
ELEC = [(-220, 0, 0, .34)]


# ---------------------------------------------------------------- 基座：停机坪、承力带、涵道、主眼镜筒
def build_pad(M):
    mats = [M['graphite'], M['glow'], M['orange'], M['dark']]
    bm = bmesh.new()
    revolve(bm, [(0, 0), (150, 0), (150, 9), (143, 16), (0, 16)], 0, seg=96, closed=False)
    revolve(bm, [(116, 16), (125, 16), (125, 17.6), (116, 17.6)], 1, seg=96, closed=True)
    revolve(bm, [(0, 16), (46, 16), (46, 17), (0, 17)], 3, seg=64, closed=False)
    revolve(bm, [(40, 17), (46, 17), (46, 18), (40, 18)], 2, seg=64, closed=True)
    for k in range(3):                                   # 三条橙色引导线
        a = radians(90 + 120 * k)
        b = bmesh.new()
        boxf(b, (52, -2.5, 16), (110, 2.5, 17.2), 2)
        bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, 'Z'))
        to_bm(bm, b)
    text(bm, 'ORB-01', 13, 0, -134, 16, 2)
    # 加注接口（坪面背后）
    rod(bm, 9, 16, 26, 2, 'Z', (0, 128, 0), seg=24)
    rod(bm, 5, 26, 29, 3, 'Z', (0, 128, 0), seg=20)
    finish('P01_Pad', 1, bm, mats, bevel=.8)


def build_band(M):
    mats = [M['graphite'], M['dark']]
    bm = bmesh.new()
    eye = [(EYE_DIR, EYE_HOLE)]
    holes = holes_fn(eye + [(sdir(*c), 3.6) for c in CAMS] + [(sdir(*n), 3.4) for n in NOZZLES])

    def band(la, lo):
        return None if holes(la, lo) or abs(la) < 3 else 0

    def floor(la, lo):
        return None if holes(la, lo) else 1
    sph_grid(bm, R_BAND[0], R_BAND[1], -BAND_LAT, BAND_LAT, 0, 360, band, step=1.5, lat_step=1.0)
    sph_grid(bm, R_BAND[0], R_BAND[0] + 3.5, -3, 3, 0, 360, floor, step=1.5, lat_step=1.0)
    # 4 根辐条：承力带 → 涵道（避开前面的主眼、三段燃料舱之间的缝）
    for k in range(4):
        b = bmesh.new()
        boxf(b, (66, -7, -6), (171, 7, 6), 0)
        boxf(b, (66, -2, -14), (171, 2, 14), 0)
        bmesh.ops.transform(b, verts=b.verts,
                            matrix=Matrix.Translation((0, 0, ZC)) @ Matrix.Rotation(radians(45 + 90 * k), 4, 'Z'))
        to_bm(bm, b)
    finish('P02_EquatorFrame', 2, bm, mats)


def build_duct(M):
    mats = [M['graphite'], M['orange'], M['dark']]
    bm = bmesh.new()
    rev(bm, [(62, -152), (72, -152), (72, -147), (66, -145), (66, 145), (72, 147), (72, 152), (62, 152)],
        0, 'Z', (0, 0, ZC), seg=96, closed=True)
    for z in (-140.0, 140.0):
        rev(bm, [(66, z - 2), (67.5, z - 2), (67.5, z + 2), (66, z + 2)], 1, 'Z', (0, 0, ZC), seg=96, closed=True)
    finish('P03_Duct', 3, bm, mats)


def build_eye_housing(M):
    mats = [M['graphite'], M['dark'], M['shell']]
    bm = bmesh.new()
    ring = [(183 * sin(radians(a)), 183 * cos(radians(a))) for a in (10.5, 12, 14, 16, 18.5)]
    ring += [(176 * sin(radians(a)), 176 * cos(radians(a))) for a in (18.5, 16, 14, 12, 10.5)]
    rev_d(bm, ring, 2, EYE_DIR, CEN, seg=72, closed=True)
    rev_d(bm, [(31, 118), (35, 118), (35, 175), (31, 175)], 0, EYE_DIR, CEN, seg=48, closed=True)
    rev_d(bm, [(0, 114), (35, 114), (35, 118), (0, 118)], 1, EYE_DIR, CEN, seg=48)
    finish('P04_EyeHousing', 4, bm, mats)


# ---------------------------------------------------------------- 外壳
def build_petals(M):
    mats = [M['shell'], M['orange']]
    for upper in (True, False):
        for k in range(6):
            lon0, lon1 = 60 * k + .7, 60 * (k + 1) - .7
            lat0, lat1 = (BAND_LAT + .5, 63.4) if upper else (-63.4, -BAND_LAT - .5)
            hs = [(EYE_DIR, EYE_HOLE)]
            if upper:
                hs += [(sdir(*EXHAUST), 5.8), (sdir(*FILLER), 4.0)]
            else:
                hs += [(sdir(*a), 3.4) for a in ALTIS]
            inside = holes_fn(hs)

            def fn(la, lo, upper=upper, inside=inside):
                if inside(la, lo):
                    return None
                edge = la - BAND_LAT if upper else -BAND_LAT - la
                return 1 if 1.0 < edge < 4.0 else 0
            bm = bmesh.new()
            sph_grid(bm, R_IN, R_OUT, lat0, lat1, lon0, lon1, fn, step=1.5)
            c = 60 * k + 30
            if upper:
                ex = [along(sdir(45, c), 270, .09)]
                finish(f'P05_UpperPetal_{k + 1}', 5, bm, mats, ex=ex)
            else:
                ex = [radial(c, 270, -120, .12)]
                finish(f'P06_LowerPetal_{k + 1}', 6, bm, mats, ex=ex)


def grille_fn(sign):
    slots = ((72.5, 74.0), (76.0, 77.5), (79.5, 81.0), (83.0, 84.5))

    def fn(la, lo):
        a = abs(la)
        if a < 71.6:
            return 1
        for s0, s1 in slots:
            if s0 < a < s1 and min(lo % 45, 45 - lo % 45) > 3.5:
                return None
        return 0
    return fn


def build_grilles(M):
    mats = [M['alu'], M['orange']]
    bm = bmesh.new()
    sph_grid(bm, R_IN, R_OUT, 70.6, 90, 0, 360, grille_fn(1), step=3.0, lat_step=.5)
    finish('P07_TopGrille', 7, bm, mats, ex=[(0, 0, 220, .04)])
    bm = bmesh.new()
    sph_grid(bm, R_IN, R_OUT, -90, -70.6, 0, 360, grille_fn(-1), step=3.0, lat_step=.5)
    finish('P08_BottomGrille', 8, bm, mats, ex=[(0, 0, -140, .1)])


def build_lidar(M):
    mats = [M['graphite'], M['glass_dark'], M['orange']]
    bm = bmesh.new()
    sph_grid(bm, 172, 180, 63.8, 70.4, 0, 360,
             lambda la, lo: 1 if 65.6 < la < 68.4 else (2 if la < 64.6 else 0), step=3.0, lat_step=.6)
    finish('P09_LidarRing', 9, bm, mats, ex=[(0, 0, 160, .07)])


def build_halo(M):
    mats = [M['shell'], M['glow'], M['orange']]
    bm = bmesh.new()
    tilt = Matrix.Translation((0, 0, ZC)) @ Matrix.Rotation(radians(9), 4, 'X')
    path = [tilt @ Vector((218 * cos(2 * pi * k / 160), 218 * sin(2 * pi * k / 160), 0)) for k in range(160)]
    sweep(bm, path, 5.0, 0, sides=16, closed=True)
    path = [tilt @ Vector((211.5 * cos(2 * pi * k / 160), 211.5 * sin(2 * pi * k / 160), 0)) for k in range(160)]
    sweep(bm, path, 1.8, 1, sides=10, closed=True)
    for lon in (90.0, 210.0, 330.0):
        a = radians(lon)
        b = bmesh.new()
        boxf(b, (-8, -9, -9), (8, 9, 9), 2)
        bmesh.ops.transform(b, verts=b.verts,
                            matrix=tilt @ Matrix.Translation((218 * cos(a), 218 * sin(a), 0)) @ Matrix.Rotation(a, 4, 'Z'))
        to_bm(bm, b)
    finish('P10_Halo', 10, bm, mats, ex=[(0, 0, 60, 0.0)])


def build_light_strips(M):
    mats = [M['glow']]
    for k, (lo0, lo1) in enumerate(((-71.0, 33.0), (35.0, 145.0), (147.0, 251.0))):
        bm = bmesh.new()
        sph_grid(bm, R_BAND[0] + 3.5, R_BAND[1] - 2.5, -3, 3, lo0, lo1, lambda la, lo: 0, step=1.0)
        finish(f'P11_LightStrip_{k + 1}', 11, bm, mats, ex=[radial((lo0 + lo1) / 2, 130, 0, .05)])


# ---------------------------------------------------------------- 燃料系统
TANK_LON = (0.0, 90.0, 180.0)
TANK_R, TANK_T = 118.0, 30.0
ZL = -75.0           # 下半球油路的高度（相对球心）


def tank_route(c):
    return [radial(c, 100, 140, .72)]


def build_tanks(M):
    mats = [M['tank'], M['orange'], M['steel']]
    for k, c in enumerate(TANK_LON):
        bm = bmesh.new()
        lons = [c - 34 + 2 * i for i in range(35)]
        sweep(bm, [pol(TANK_R, lo, 0) for lo in lons], TANK_T, 0, sides=28)
        for lo, sgn in ((lons[0], -1), (lons[-1], 1)):
            t = Vector((-sin(radians(lo)), cos(radians(lo)), 0)) * sgn
            rev_d(bm, [(TANK_T, 0), (28, 8), (21, 21), (11, 28), (0, TANK_T)], 0, t, pol(TANK_R, lo, 0), seg=28)
        for lo in (c - 17, c + 17):
            rad = Vector((cos(radians(lo)), sin(radians(lo)), 0))
            ctr = pol(TANK_R, lo, 0)
            ring = [ctr + 31.6 * (cos(2 * pi * i / 32) * rad + Vector((0, 0, sin(2 * pi * i / 32)))) for i in range(32)]
            sweep(bm, ring, 2.0, 1, sides=8, closed=True)
        finish(f'P12_FuelTank_{k + 1}', 12, bm, mats, ex=tank_route(c))


def build_filler(M):
    mats = [M['line'], M['steel'], M['orange'], M['rubber']]
    d = sdir(*FILLER)
    bm = bmesh.new()
    a = pol(TANK_R, FILLER[1], 24)
    b = CEN + d * 171
    mid = Vector((a.x * .9 + b.x * .1, a.y * .9 + b.y * .1, (a.z + b.z) * .5 + 10))
    sweep(bm, catmull([a, mid, b], 8), 9.0, 0, sides=16)
    rev_d(bm, [(9, 0), (14, 0), (14, 3), (9, 3)], 1, d, b - d * 8, seg=24, closed=True)
    finish('P13_FillerNeck', 13, bm, mats, ex=tank_route(90.0) + [(0, 0, 45, .8)])
    bm = bmesh.new()
    rev_d(bm, [(0, 0), (13.5, 0), (13.5, 4), (11.5, 6.5), (0, 6.5)], 2, d, CEN + d * 175.5, seg=32)
    rev_d(bm, [(9, -3), (12, -3), (12, 0), (9, 0)], 3, d, CEN + d * 175.5, seg=24, closed=True)
    local_part(bm, lambda b: boxf(b, (-1.6, -9, 6), (1.6, 9, 10), 2), orient(d, CEN + d * 175.5))   # 握把
    finish('P14_FillerCap', 14, bm, mats, ex=[along(d, 120, .02)])


def build_level_sensor(M):
    mats = [M['steel'], M['graphite'], M['orange']]
    p = pol(TANK_R, 196, 26)
    bm = bmesh.new()
    rod(bm, 5.5, p.z, p.z + 16, 0, 'Z', (p.x, p.y, 0), seg=20)
    boxf(bm, (p.x - 8, p.y - 6, p.z + 16), (p.x + 8, p.y + 6, p.z + 26), 1)
    boxf(bm, (p.x - 8.2, p.y - 6.2, p.z + 20), (p.x + 8.2, p.y + 6.2, p.z + 22), 2)
    finish('P15_LevelSensor', 15, bm, mats, bevel=.6, ex=tank_route(180.0) + [(0, 0, 40, .82)])


def lower_route(lon):
    return [radial(lon, 200, -30, .26)]


def build_fuel_parts(M):
    mats = [M['alu'], M['orange'], M['graphite'], M['steel'], M['copper']]
    # 滤清器
    p = pol(108, 122, ZL)
    bm = bmesh.new()
    rod(bm, 14, p.z - 28, p.z + 22, 0, 'Z', (p.x, p.y, 0), seg=32)
    rod(bm, 14.6, p.z - 6, p.z + 2, 1, 'Z', (p.x, p.y, 0), seg=32)
    rod(bm, 15, p.z + 18, p.z + 24, 2, 'Z', (p.x, p.y, 0), seg=32)
    rod(bm, 15, p.z - 30, p.z - 25, 2, 'Z', (p.x, p.y, 0), seg=32)
    finish('P16_FuelFilter', 16, bm, mats, bevel=.6, ex=lower_route(122))
    # 燃油泵
    p = pol(108, 90, ZL)
    bm = bmesh.new()
    rod(bm, 16, p.z - 25, p.z + 12, 2, 'Z', (p.x, p.y, 0), seg=32)
    rod(bm, 19, p.z + 12, p.z + 26, 0, 'Z', (p.x, p.y, 0), seg=32)
    rod(bm, 16.6, p.z - 4, p.z, 1, 'Z', (p.x, p.y, 0), seg=32)
    for lo in (82.0, 98.0):
        q = pol(119, lo, ZL + 19)
        rod(bm, 5, q.z - 5, q.z + 5, 3, 'Z', (q.x, q.y, 0), seg=16)
    finish('P17_FuelPump', 17, bm, mats, bevel=.6, ex=lower_route(90))
    # 电磁截止阀
    p = pol(106, 62, ZL)
    bm = bmesh.new()
    t = Matrix.Translation(p) @ Matrix.Rotation(radians(62), 4, 'Z')
    b = bmesh.new()
    boxf(b, (-9, -13, -14), (9, 13, 2), 0)
    rod(b, 10, 2, 22, 1, 'Z', (0, 0, 0), seg=28)
    rod(b, 4, 22, 26, 2, 'Z', (0, 0, 0), seg=16)
    boxf(b, (-14, -5, 8), (-10, 5, 16), 2)
    bmesh.ops.transform(b, verts=b.verts, matrix=t)
    to_bm(bm, b)
    finish('P18_ShutoffValve', 18, bm, mats, bevel=.6, ex=lower_route(62))
    # 调压阀
    p = pol(104, 32, ZL)
    bm = bmesh.new()
    rev(bm, [(0, -18), (13, -18), (13, 4), (15, 6), (15, 12), (8, 18), (0, 18)], 0, 'Z', p, seg=32)
    rod(bm, 5, 18, 27, 1, 'Z', p, seg=20)
    rev(bm, [(0, 27), (8, 27), (8, 31), (0, 31)], 1, 'Z', p, seg=24)
    finish('P19_Regulator', 19, bm, mats, bevel=.5, ex=lower_route(32))


def build_lines(M):
    mats = [M['line'], M['orange']]
    T = Vector((100.0, 0.0, ZC + 74.0))             # 涡轮轴线中心
    runs = [
        # (点列, 爆炸路线)
        ([pol(118, 112, -30), pol(114, 117, -48), pol(108, 122, ZL + 26)],
         [(0, 0, -25, .2), radial(117, 170, -30, .3)]),
        ([pol(94, 122, ZL), pol(90, 106, ZL + 10), pol(92, 92, ZL + 19)], [radial(106, 170, -10, .24)]),
        ([pol(119, 82, ZL + 19), pol(114, 72, ZL + 10), pol(110, 64, ZL - 3)], [radial(72, 170, -10, .24)]),
        ([pol(104, 58, ZL - 5), pol(104, 45, ZL - 8), pol(104, 38, ZL - 6)], [radial(45, 170, -10, .24)]),
        ([pol(104, 32, ZL + 32), pol(92, 25, ZL + 44), pol(77, 15, -20), pol(77, 8, 30),
          Vector((86, -2, ZC + 40)), Vector((97, -6, T.z - 28))], [(0, 0, -200, .28), radial(15, 220, 0, .5)]),
        ([pol(118, 30, 27), pol(118, 38, 40), pol(118, 45, 44), pol(118, 52, 40), pol(118, 60, 27)],
         [radial(45, 100, 175, .74)]),
        ([pol(118, 120, 27), pol(118, 128, 40), pol(118, 135, 44), pol(118, 142, 40), pol(118, 150, 27)],
         [radial(135, 100, 175, .74)]),
    ]
    for k, (pts, ex) in enumerate(runs):
        bm = bmesh.new()
        path = catmull(pts, 10)
        sweep(bm, path, 3.2, 0, sides=10)
        for end, nxt in ((path[0], path[1]), (path[-1], path[-2])):
            rev_d(bm, [(0, 0), (5, 0), (5, 7), (0, 7)], 1, end - nxt, end - (end - nxt).normalized() * 6, seg=6)
        finish(f'P20_FuelLine_{k + 1}', 20, bm, mats, ex=ex)


# ---------------------------------------------------------------- 涡轮发电机（轴线沿 +Y，在右侧 +X）
TC = Vector((100.0, 0.0, ZC + 74.0))
TMX = Matrix.Translation(TC) @ ROT['Y']       # 局部 +Z（轴向）→ 世界 +Y


def tpart(name, no, mats, build, ex, bevel=0.0):
    bm = bmesh.new()
    build(bm)
    finish(name, no, bm, mats, ex=TURB + ex, bevel=bevel, mtx=TMX)


def build_turbine(M):
    def stator(bm):
        revolve(bm, [(9.5, -58), (24, -58), (24, -36), (9.5, -36)], 0, seg=48, closed=True)
        for h in (-55, -51, -47, -43, -39):
            revolve(bm, [(24, h), (27.5, h), (27.5, h + 1.6), (24, h + 1.6)], 0, seg=48, closed=True)
        for h0 in (-60.0, -36.0):
            revolve(bm, [(12, h0), (21, h0), (21, h0 + 2), (12, h0 + 2)], 1, seg=40, closed=True)
    tpart('P21_GenStator', 21, [M['steel'], M['copper']], stator, [(0, -120, 0, .55)])

    def rotor(bm):
        revolve(bm, [(4.2, -57), (8.8, -57), (8.8, -37), (4.2, -37)], 0, seg=32, closed=True)
        revolve(bm, [(8.8, -50), (9.0, -50), (9.0, -44), (8.8, -44)], 1, seg=32, closed=True)
    tpart('P22_GenRotor', 22, [M['magnet'], M['orange']], rotor, [(0, -85, 45, .6)])

    def intake(bm):
        revolve(bm, [(14, -36), (30, -36), (31.5, -32), (29, -28), (14, -28)], 0, seg=48, closed=True)
        for k in range(6):
            a = 2 * pi * k / 6
            b = bmesh.new()
            boxf(b, (5, -1, -35), (14, 1, -29), 1)
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, 'Z'))
            to_bm(bm, b)
    tpart('P23_Intake', 23, [M['alu'], M['steel']], intake, [(0, -58, 0, .58)])

    def compressor(bm):
        revolve(bm, [(4.2, -28), (8, -28), (20, -20), (20, -18), (4.2, -18)], 0, seg=48, closed=True)
        for k in range(12):
            b = bmesh.new()
            boxf(b, (6, -.7, -27.5), (21.5, .7, -19), 0)
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, -23), matrix=Matrix.Rotation(radians(30), 3, 'X'))
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * pi * k / 12, 3, 'Z'))
            to_bm(bm, b)
    tpart('P24_Compressor', 24, [M['ti']], compressor, [(0, -32, 45, .62)])

    def combustor(bm):
        revolve(bm, [(13, -18), (28, -18), (28, 18), (13, 18)], 0, seg=48, closed=True)
        for h in (-7.0, 6.0):
            for k in range(12):
                a = 2 * pi * (k + .5 * (h > 0)) / 12
                b = bmesh.new()
                rod(b, 2.4, 0, .5, 1, 'Z', (0, 0, 0), seg=12)
                bmesh.ops.transform(b, verts=b.verts, matrix=Matrix.Rotation(a, 4, 'Z') @ Matrix.Translation((28, 0, h))
                                    @ Matrix.Rotation(pi / 2, 4, 'Y'))
                to_bm(bm, b)
    tpart('P25_Combustor', 25, [M['hot'], M['hole']], combustor, [])

    def injectors(bm):
        path = [Vector((36 * cos(2 * pi * k / 48), 36 * sin(2 * pi * k / 48), -13)) for k in range(48)]
        sweep(bm, path, 1.8, 1, sides=8, closed=True)
        for k in range(6):
            b = bmesh.new()
            rod(b, 2.2, 27, 36, 0, 'X', (0, 0, -13), seg=12)
            rev(b, [(0, 36), (3.6, 36), (3.6, 39), (0, 39)], 0, 'X', (0, 0, -13), seg=6)
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * pi * k / 6 + pi / 6, 3, 'Z'))
            to_bm(bm, b)
    tpart('P26_Injectors', 26, [M['steel'], M['line']], injectors, [(45, 0, 0, .62)])

    def igniter(bm):
        b = bmesh.new()
        rod(b, 3.4, 26, 34, 1, 'Z', (0, 0, 0), seg=16)
        rev(b, [(0, 34), (5, 34), (5, 42), (0, 42)], 0, 'Z', (0, 0, 0), seg=6)
        rev(b, [(0, 42), (3, 42), (3, 47), (0, 47)], 2, 'Z', (0, 0, 0), seg=16)
        bmesh.ops.transform(b, verts=b.verts, matrix=Matrix.Rotation(pi / 2, 4, 'X'))   # 局部 +Z → 局部 -Y（世界 +Z）
        to_bm(bm, b)
    tpart('P27_Igniter', 27, [M['steel'], M['ceramic'], M['orange']], igniter, [(0, 0, 65, .64)])

    def turbine(bm):
        revolve(bm, [(4.2, 18), (14, 18), (17, 22), (17, 25), (4.2, 26)], 0, seg=48, closed=True)
        for k in range(16):
            b = bmesh.new()
            boxf(b, (13, -.8, 19), (22.5, .8, 25), 0)
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 22), matrix=Matrix.Rotation(radians(-35), 3, 'X'))
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * pi * k / 16, 3, 'Z'))
            to_bm(bm, b)
    tpart('P28_TurbineWheel', 28, [M['hot']], turbine, [(0, 42, 45, .62)])

    def shaft(bm):
        rod(bm, 4.2, -60, 28, 0, 'Z', (0, 0, 0), seg=20)
    tpart('P30_Shaft', 30, [M['ti']], shaft, [(0, 0, 95, .66)])

    for k, h in enumerate((-33.0, 10.0)):
        def bearing(bm, h=h):
            revolve(bm, [(4.2, h), (9, h), (9, h + 5), (4.2, h + 5)], 0, seg=32, closed=True)
            revolve(bm, [(6.2, h - .2), (7.2, h - .2), (7.2, h + 5.2), (6.2, h + 5.2)], 1, seg=32, closed=True)
        tpart(f'P31_Bearing_{k + 1}', 31, [M['steel'], M['ceramic']], bearing, [(0, -12 + 30 * k, 130, .7)])

    # 排气管（世界坐标里扫掠）+ 排气口
    mats = [M['hot'], M['orange']]
    bm = bmesh.new()
    d = sdir(*EXHAUST)
    end = CEN + d * 177
    path = catmull([TC + Vector((0, 24, 0)), TC + Vector((0, 40, 0)), TC + Vector((10, 54, 4)), CEN + d * 160, end], 8)
    sweep(bm, path, 15.0, 0, sides=28)
    rev_d(bm, [(13.5, -1), (18, -1), (18, 2), (13.5, 2)], 1, d, end, seg=32, closed=True)
    finish('P29_Exhaust', 29, bm, mats, ex=TURB + [(0, 95, 0, .58)])

    # 支架
    bm = bmesh.new()
    boxf(bm, (78, -46, ZC + 40), (122, 22, ZC + 43.5), 0)
    for y in (-42.0, 12.0):
        boxf(bm, (80, y, ZC + 43.5), (120, y + 3, ZC + 54), 0)
    finish('P32_TurbineMount', 32, bm, [M['ti']], bevel=.6, ex=TURB + [(0, 0, -80, .5)])


# ---------------------------------------------------------------- 电池（背面）、电子舱（左侧 -X）
def build_battery(M):
    mats = [M['graphite'], M['orange'], M['shell'], M['dark']]
    bm = bmesh.new()
    boxf(bm, (2, 82, ZC + 45), (58, 118, ZC + 90), 0)
    boxf(bm, (1.6, 81.6, ZC + 80), (58.4, 118.4, ZC + 84), 1)
    boxf(bm, (14, 76, ZC + 52), (46, 82, ZC + 64), 3)
    flat_b = bmesh.new()
    text(flat_b, '48V 6Ah', 7, 0, 0, 0, 2)
    bmesh.ops.transform(flat_b, verts=flat_b.verts,
                        matrix=Matrix.Translation((30, 81.9, ZC + 70)) @ Matrix.Rotation(pi / 2, 4, 'X'))
    to_bm(bm, flat_b)
    finish('P33_Battery', 33, bm, mats, bevel=1.2, ex=[radial(73, 220, 0, .3)])


def build_electronics(M):
    # 支架 + 铜柱
    bm = bmesh.new()
    boxf(bm, (-134, -40, ZC + 40), (-70, 40, ZC + 43), 0)
    for x in (-128.0, -76.0):
        for y in (-34.0, 34.0):
            rod(bm, 2.4, ZC + 43, ZC + 76, 1, 'Z', (x, y, 0), seg=12)
    finish('P42_ElecTray', 42, bm, [M['graphite'], M['gold']], ex=ELEC + [(0, 0, -70, .5)])
    # 电源管理板
    bm = bmesh.new()
    boxf(bm, (-126, -32, ZC + 46), (-78, 32, ZC + 47.6), 0)
    for i, x in enumerate((-118.0, -104.0, -90.0)):
        boxf(bm, (x - 5, -26, ZC + 47.6), (x + 5, -16, ZC + 54), 1)
        boxf(bm, (x - 5, 16, ZC + 47.6), (x + 5, 26, ZC + 54), 1)
    smd_caps(bm, [(-120 + 9 * i, 0) for i in range(5)], ZC + 47.6, 3, 7, 2, 1)
    boxf(bm, (-90, -8, ZC + 47.6), (-82, 8, ZC + 49), 3)
    finish('P43_PowerBoard', 43, bm, [M['pcb'], M['inductor'], M['chip'], M['gold']],
           ex=ELEC + [(0, 0, 0, .5)])
    # 电调 ×2（上面一层）
    for k, (y0, y1) in enumerate(((-30.0, -4.0), (4.0, 30.0))):
        bm = bmesh.new()
        boxf(bm, (-124, y0, ZC + 57), (-80, y1, ZC + 58.6), 0)
        for i in range(4):
            for j in range(2):
                x = -118 + 9 * i
                y = y0 + 7 + 12 * j
                boxf(bm, (x - 3, y - 3, ZC + 58.6), (x + 3, y + 3, ZC + 59.6), 1)
        boxf(bm, (-80, (y0 + y1) / 2 - 5, ZC + 58.6), (-76, (y0 + y1) / 2 + 5, ZC + 62), 2)
        finish(f'P44_ESC_{k + 1}', 44, bm, [M['pcb'], M['chip'], M['orange']],
               ex=ELEC + [(0, (-40, 40)[k], 40, .55)])
    # 散热片
    bm = bmesh.new()
    boxf(bm, (-122, -28, ZC + 60), (-82, 28, ZC + 62), 0)
    fins(bm, -122, -82, -28, 28, ZC + 62, ZC + 70, 3.6, 1.0, 0)
    finish('P45_Heatsink', 45, bm, [M['alu']], ex=ELEC + [(0, 0, 80, .58)])
    # 飞控板 + IMU
    bm = bmesh.new()
    boxf(bm, (-130, -36, ZC + 76), (-74, 36, ZC + 77.6), 0)
    boxf(bm, (-96, -9, ZC + 77.6), (-82, 9, ZC + 79), 1)
    for i in range(3):
        boxf(bm, (-126 + 7 * i, 28, ZC + 77.6), (-122 + 7 * i, 32, ZC + 79), 2)
    text(bm, 'ORB FC', 4, -100, 22, ZC + 77.6, 3)
    finish('P46_FlightCtrl', 46, bm, [M['pcb'], M['chip'], M['glow'], M['ink']], ex=ELEC + [(0, 0, 115, .6)])
    bm = bmesh.new()
    boxf(bm, (-116, -6, ZC + 77.6), (-104, 6, ZC + 80), 0)
    boxf(bm, (-114, -4, ZC + 80), (-106, 4, ZC + 81.4), 1)
    finish('P47_IMU', 47, bm, [M['pcb'], M['gold']], ex=ELEC + [(0, 0, 150, .63)])
    # 线束：电调 → 涵道壁上的接口（再沿电机支臂进去）
    bm = bmesh.new()
    for y in (-20.0, -14.0, 14.0, 20.0):
        p0 = Vector((-80, y, ZC + 59))
        sweep(bm, catmull([p0, Vector((-74, y, ZC + 62)), Vector((-70, y * .8, ZC + 56)),
                           Vector((-67.5, y * .7, ZC + 48))], 8), 2.0, 0, sides=8)
        rev_d(bm, [(0, 0), (3, 0), (3, 5), (0, 5)], 1, Vector((1, 0, 0)), Vector((-68, y * .7, ZC + 48)), seg=10)
    finish('P48_Harness', 48, bm, [M['rubber'], M['orange']], ex=ELEC + [(0, 0, -30, .5)])


# ---------------------------------------------------------------- 推进：共轴风扇、电机、支架、舵片、舵机、偏航喷口
def fan(bm, z, nb, tilt, r_tip, mats_idx=(0, 1)):
    revolve(bm, [(0, z - 5), (16, z - 5), (16, z + 5), (0, z + 5)], mats_idx[1], seg=40)
    for k in range(nb):
        b = bmesh.new()
        extrude(b, [[(15, -9), (r_tip, -6), (r_tip, 6), (15, 9)]], -1, 1, mats_idx[0])
        bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(radians(tilt), 3, 'X'))
        bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * pi * k / nb, 3, 'Z'))
        bmesh.ops.translate(b, verts=b.verts, vec=(0, 0, z))
        to_bm(bm, b)


def build_propulsion(M):
    bm = bmesh.new()
    fan(bm, ZC + 67, 7, 24, 58)
    finish('P34_UpperFan', 34, bm, [M['graphite'], M['shell']], ex=[(0, 0, 200, .4)])
    bm = bmesh.new()
    rev(bm, [(0, 40), (20, 40), (20, 58), (17, 62), (0, 62)], 0, 'Z', (0, 0, ZC), seg=40)
    rev(bm, [(20, 49), (20.6, 49), (20.6, 53), (20, 53)], 1, 'Z', (0, 0, ZC), seg=40, closed=True)
    finish('P35_UpperMotor', 35, bm, [M['steel'], M['orange']], ex=[(0, 0, 150, .46)])
    bm = bmesh.new()
    rod(bm, 13, ZC - 18, ZC + 40, 0, 'Z', (0, 0, 0), seg=32)
    for k in range(4):
        b = bmesh.new()
        boxf(b, (13, -2.5, ZC + 4), (62, 2.5, ZC + 14), 0)
        bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(pi / 2 * k, 3, 'Z'))
        to_bm(bm, b)
    finish('P36_MotorMount', 36, bm, [M['alu']], bevel=.6, ex=[(0, 0, 105, .52)])
    bm = bmesh.new()
    rev(bm, [(0, -40), (17, -40), (20, -36), (20, -18), (0, -18)], 0, 'Z', (0, 0, ZC), seg=40)
    rev(bm, [(20, -31), (20.6, -31), (20.6, -27), (20, -27)], 1, 'Z', (0, 0, ZC), seg=40, closed=True)
    finish('P37_LowerMotor', 37, bm, [M['steel'], M['orange']], ex=[(0, 0, -105, .62)])
    bm = bmesh.new()
    fan(bm, ZC - 49, 5, -24, 58)
    finish('P38_LowerFan', 38, bm, [M['graphite'], M['shell']], ex=[(0, 0, -150, .56)])
    # 舵片 + 舵机（6 组，方位 0、60……）
    for k in range(6):
        lon = 60.0 * k
        rz = Matrix.Rotation(radians(lon), 4, 'Z')
        bm = bmesh.new()
        boxf(bm, (14, -1.2, ZC - 148), (60, 1.2, ZC - 112), 0)
        rod(bm, 1.8, 10, 74, 1, 'X', (0, 0, ZC - 128), seg=10)
        xform(bm, bm.faces, rz)
        finish(f'P39_Vane_{k + 1}', 39, bm, [M['orange'], M['steel']],
               ex=[(0, 0, -70, .42), radial(lon, 80, 0, .52)])
        bm = bmesh.new()
        boxf(bm, (68, -9, ZC - 142), (88, 9, ZC - 116), 0)
        boxf(bm, (66, -11, ZC - 122), (90, 11, ZC - 119), 0)
        rod(bm, 4, 64, 68, 1, 'X', (0, 0, ZC - 128), seg=16)
        xform(bm, bm.faces, rz)
        finish(f'P40_Servo_{k + 1}', 40, bm, [M['dark'], M['orange']], bevel=.6, ex=[radial(lon, 150, 0, .36)])
    # 偏航喷口
    for k, n in enumerate(NOZZLES):
        d = sdir(*n)
        bm = bmesh.new()
        rev_d(bm, [(0, 0), (7, 0), (7, 8), (9, 13), (9, 18), (0, 18)], 0, d, CEN + d * 168, seg=28)
        rev_d(bm, [(5, 18), (9, 18), (9, 19.5), (5, 19.5)], 1, d, CEN + d * 168, seg=28, closed=True)
        rev_d(bm, [(0, 17), (5, 17), (5, 18.2), (0, 18.2)], 2, d, CEN + d * 168, seg=20)
        finish(f'P41_YawNozzle_{k + 1}', 41, bm, [M['steel'], M['orange'], M['hole']], ex=[along(d, 130, .04)])


# ---------------------------------------------------------------- 传感器：主眼（沿 -Y）、立体相机、测高雷达、天线
def build_eye(M):
    def axial(prof, mi, mats, name, no, dy, closed=False, extra=None):
        bm = bmesh.new()
        rev_d(bm, prof, mi, EYE_DIR, CEN, seg=64, closed=closed)
        if extra:
            extra(bm)
        finish(name, no, bm, mats, ex=[(0, -dy, 0, .14)])

    axial([(0, 169), (30, 172), (30, 175), (0, 179)], 0, [M['glass']], 'P49_FrontLens', 49, 180)

    def iris_blades(bm):
        for k in range(8):
            b = bmesh.new()
            extrude(b, [[(11, -3), (30, -9), (30, 7), (14, 4)]], -.5, .5, 0)
            bmesh.ops.rotate(b, verts=b.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * pi * k / 8, 3, 'Z'))
            bmesh.ops.transform(b, verts=b.verts, matrix=orient(EYE_DIR, CEN + EYE_DIR * (160 + .3 * (k % 2))))
            to_bm(bm, b)
    axial([(28, 158.5), (31, 158.5), (31, 162), (28, 162)], 1, [M['steel'], M['orange']], 'P50_Iris', 50, 150,
          closed=True, extra=iris_blades)
    axial([(0, 148), (27, 150), (27, 153), (0, 155)], 0, [M['glass']], 'P51_MidLens', 51, 120)
    axial([(0, 134), (24, 136), (24, 139), (0, 141)], 0, [M['glass']], 'P52_RearLens', 52, 90)

    bm = bmesh.new()
    boxf(bm, (-19, -19, 0), (19, 19, 2), 0)
    boxf(bm, (-9, -7, 2), (9, 7, 3.2), 1)
    boxf(bm, (-14, -16, -3), (14, -12, 0), 2)
    finish('P53_ImageSensor', 53, bm, [M['pcb'], M['die'], M['gold']], ex=[(0, -60, 0, .14)],
           mtx=orient(EYE_DIR, CEN + EYE_DIR * 122))
    axial([(41, 176), (45, 176), (45, 191), (41, 191)], 0, [M['shell'], M['orange']], 'P54_LensHood', 54, 205,
          closed=True,
          extra=lambda bm: rev_d(bm, [(40.6, 191), (45.6, 191), (45.6, 193), (40.6, 193)], 1, EYE_DIR, CEN,
                                 seg=64, closed=True))
    axial([(36, 182), (40.4, 182), (40.4, 184.5), (36, 184.5)], 0, [M['glow']], 'P55_EyeGlow', 55, 230, closed=True)


def build_sensors(M):
    for k, c in enumerate(CAMS):
        d = sdir(*c)
        bm = bmesh.new()
        rev_d(bm, [(0, 0), (10, 0), (10, 15), (0, 15)], 0, d, CEN + d * 166, seg=32)
        rev_d(bm, [(0, 15), (6, 15), (6, 16.5), (0, 16.5)], 1, d, CEN + d * 166, seg=32)
        rev_d(bm, [(6, 14.8), (10, 14.8), (10, 16), (6, 16)], 2, d, CEN + d * 166, seg=32, closed=True)
        finish(f'P56_StereoCam_{k + 1}', 56, bm, [M['graphite'], M['glass_dark'], M['orange']],
               ex=[along(d, 140, .04)])
    for k, c in enumerate(ALTIS):
        d = sdir(*c)
        bm = bmesh.new()
        rev_d(bm, [(0, 0), (9, 0), (9, 18), (0, 18)], 0, d, CEN + d * 160, seg=32)
        rev_d(bm, [(0, 18), (7, 18), (7, 19), (0, 19)], 1, d, CEN + d * 160, seg=32)
        finish(f'P57_Altimeter_{k + 1}', 57, bm, [M['graphite'], M['glass_dark']], ex=[along(d, 110, .16)])
    for k, c in enumerate(ANTENNAS):
        d = sdir(*c)
        bm = bmesh.new()

        def blade(b):
            rev(b, [(0, -2), (6, -2), (6, 3), (0, 3)], 0, 'Z', (0, 0, 0), seg=20)
            extrude(b, [[(-9, 0), (9, 0), (3, 40), (-2, 40)]], -1.2, 1.2, 1, axis='X')
            rev(b, [(0, 40), (2.4, 40), (2.4, 44), (0, 44)], 2, 'Z', (0, 0, 0), seg=12)
        # 天线片沿经线方向（局部 Y 朝东）
        east = Vector((-sin(radians(c[1])), cos(radians(c[1])), 0))
        q = Vector((0, 0, 1)).rotation_difference(d)
        y_now = q @ Vector((0, 1, 0))
        twist = y_now.rotation_difference(east) if abs(y_now.dot(d)) < 1e-3 else None
        m = orient(d, CEN + d * 176)
        if twist is not None:
            m = Matrix.Translation(CEN + d * 176) @ (twist @ q).to_matrix().to_4x4()
        local_part(bm, blade, m)
        finish(f'P58_Antenna_{k + 1}', 58, bm, [M['orange'], M['shell'], M['glow']],
               ex=[along(d + Vector((0, 0, .6)), 150, .02)])


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
    for name, loc, power, size in (('Key', (1.6, -1.8, 2.2), 260, 2.0), ('Fill', (-1.8, -1.0, 1.2), 90, 2.4),
                                   ('Rim', (.4, 2.0, 1.8), 150, 1.6)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, (0, 0, .35))
        collection('Scene').objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 40
    cam = bpy.data.objects.new('Cam', cd)
    cam.location = (.75, -1.15, .7)
    look_at(cam, (0, 0, .3))
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
    ROOT = bpy.data.objects.new('OrbBot', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .1
    collection('OrbBot').objects.link(ROOT)
    build_pad(M)
    build_band(M)
    build_duct(M)
    build_eye_housing(M)
    build_petals(M)
    build_grilles(M)
    build_lidar(M)
    build_halo(M)
    build_light_strips(M)
    build_tanks(M)
    build_filler(M)
    build_level_sensor(M)
    build_fuel_parts(M)
    build_lines(M)
    build_turbine(M)
    build_battery(M)
    build_electronics(M)
    build_propulsion(M)
    build_eye(M)
    build_sensors(M)
    setup_world_and_cam(M)
    animate_explode()
    viewport_defaults()
    export_glb(os.path.join(OUT, 'orb_bot.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'orb_bot.blend'))
    print('[OK] saved orb_bot.blend')
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
    print(f'[OK] {len(OBJS)} robot objects, {len(INFO)} kinds, {tris} triangles, size {size} mm')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_assembled.png', 1, cam=(.75, -1.15, .7), target=(0, 0, .3))
        render_still('render_exploded.png', F_EXP[1] + 10, cam=(1.5, -2.0, 1.35), target=(0, 0, .42))
        render_still('render_inside.png', F_EXP[1] + 10, cam=(.55, -.85, .75), target=(0, 0, .4))
        set_engine('EEVEE')


main()
