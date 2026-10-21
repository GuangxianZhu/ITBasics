# -*- coding: utf-8 -*-
"""
迷你桌面金属车床 —— Blender 脚本建模 + 爆炸图

照着一台常见的 8 合 1 迷你桌面车床（铝合金底板 + 直线导轨床身）的产品图建的，没有图纸，尺寸都是按比例估的：
    整机长约 37 cm（含两个手轮把手和 DC 插头），高约 13.5 cm；
    卡盘 Φ50、中心高（主轴轴线离底板顶面）87 mm，手轮 Φ38。
估算依据见 README.md。

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_lathe.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    lathe.blend        Blender 工程，按空格播放：第 1~120 帧按拆机顺序拆开，第 150~270 帧反顺序装回
    lathe.glb          glTF 模型（单位米，每个零件一个节点，extras 里有零件号、中文名、材料、作用、爆炸路线），
                       虚幻工程 MyVRToyBox 的 Tools/import_model.py 直接导入
    render_*.png       加 --render 时用 Cycles 渲染装配 / 爆炸两张预览图

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    +X 指向主轴箱（右），-X 指向尾座（左）；-Y 是操作者站的正面（电机、手轮把手、刻度手轮朝这边）；+Z 向上
    Z = 0 是脚垫底面，底板顶面 Z = 13，主轴轴线在 (Y = 0, Z = 100)
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




def make_materials():
    # 金属度都压在 0.55 以下：虚幻工作室里没有反射探针，金属反射的是黑的环境，金属度 0.8 的铝在虚幻里已经发黑了（实测）。
    # 所以铝用"亮灰 + 低金属度"来近似，Blender 里看起来稍微偏塑料一点
    return dict(
        alu=principled('M_Alu', '#c3c8ce', .35, .38),
        alu_dark=principled('M_Alu_Anodized', '#8e949c', .35, .42),
        steel=principled('M_Steel', '#a9aeb4', .5, .32),
        brass=principled('M_Brass', '#d0a84e', .55, .35),
        copper=principled('M_Copper_Handle', '#c07a3e', .55, .36),
        black=principled('M_Black_Oxide', '#25272b', .2, .5),
        hole=principled('M_Hole', '#0b0b0c', 0, .8),
        rubber=principled('M_Rubber', '#141416', 0, .85),
        motor=principled('M_Motor_Can', '#4a4f56', .3, .45),
        belt=principled('M_Belt', '#1b1b1b', 0, .8),
        cable=principled('M_Cable', '#121212', 0, .55),
        tool=principled('M_HSS_Tool', '#7a8088', .5, .32),
        label=principled('M_Label', '#d9d4c3', 0, .6),
        lamination=principled('M_Lamination', '#5b6068', .45, .4),
        magnet_n=principled('M_Magnet_N', '#9a3b35', .1, .5),
        magnet_s=principled('M_Magnet_S', '#35529a', .1, .5),
        carbon=principled('M_Carbon_Brush', '#1d1d1f', 0, .7),
    )


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


def handwheel(bm, R, c, axis, mi_wheel, mi_handle, handle_len=22.0, handle_r=3.5):
    """铝手轮 + 铜手柄。局部 +Z = 手轮朝外的一面（把手伸出来的方向），c = 轮毂背面中心"""
    fs = []
    fs += revolve(bm, [(0, 0), (7, 0), (7, 1), (R - 1.5, 1), (R, 2.5), (R, 7.5), (R - 1.5, 9), (R - 5, 9),
                       (R - 6.5, 6), (8.5, 6), (7.5, 12), (0, 12)], mi_wheel, seg=56, closed=False)
    if mi_handle is not None:
        fs += revolve(bm, [(0, 9), (handle_r - 1, 9), (handle_r, 13), (handle_r, 9 + handle_len - 3),
                           (handle_r - 1.2, 9 + handle_len), (0, 9 + handle_len)], mi_handle, seg=20, closed=False,
                      cy=R * .68, cz=0.0)
    for k in range(3):                                          # 轮辐面上 3 个减重孔（深色）
        a = 2 * pi * k / 3 + pi / 3
        fs += revolve(bm, [(0, 6), (R * .17, 6), (R * .17, 6.25), (0, 6.25)], mi_wheel, seg=16, closed=False,
                      cy=R * .45 * cos(a), cz=R * .45 * sin(a))
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def handle(bm, R, c, axis, mi, handle_len=22.0, handle_r=3.5):
    """手轮上的铜手柄（单独一个零件）。坐标约定和 handwheel 一样"""
    fs = revolve(bm, [(0, 9), (handle_r - 1, 9), (handle_r, 13), (handle_r, 9 + handle_len - 3),
                      (handle_r - 1.2, 9 + handle_len), (0, 9 + handle_len)], mi, seg=20, closed=False,
                 cy=R * .68, cz=0.0)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def thread_rod(bm, r_core, depth, pitch, a0, a1, mi, axis='X', c=(0, 0, 0), seg=12, per_pitch=6):
    """真正的螺旋螺纹（梯形牙）：每一圈顶点的半径按 (轴向位置 / 螺距 + 角度 / 2π) 的小数部分取牙形"""
    n = max(2, int(round((a1 - a0) / pitch * per_pitch)))
    rings = []
    for i in range(n + 1):
        z = a0 + (a1 - a0) * i / n
        ring = []
        for k in range(seg):
            th = 2 * pi * k / seg
            ph = (z / pitch + k / seg) % 1.0
            t = abs(2 * ph - 1)                      # 0 = 牙顶中间，1 = 牙底中间
            r = r_core + depth * min(1.0, max(0.0, (1 - t) * 1.8 - .2))
            ring.append(bm.verts.new((r * cos(th), r * sin(th), z)))
        rings.append(ring)
    c0 = bm.verts.new((0, 0, a0))
    c1 = bm.verts.new((0, 0, a1))
    fs = _bridge(bm, [c0], rings[0])
    for i in range(n):
        fs += _bridge(bm, rings[i], rings[i + 1])
    fs += _bridge(bm, rings[-1], [c1])
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def socket_screw(bm, r, head_h, shank, mi_head, mi_hole, axis, c):
    """内六角圆柱头螺钉：c = 头部底面中心，局部 +Z = 头朝外的方向；螺杆往 -Z 伸 shank 长"""
    fs = revolve(bm, [(0, -shank), (r * .55, -shank), (r * .55, 0), (r, 0), (r, head_h - .4), (r - .4, head_h),
                      (0, head_h)], mi_head, seg=20, closed=False)
    fs += revolve(bm, [(0, head_h), (r * .45, head_h), (r * .45, head_h + .15), (0, head_h + .15)], mi_hole,
                  seg=6, closed=False)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def oriented(bm, faces, origin, x_dir, y_dir):
    """把局部 (x, y, z) 的几何摆到 origin，局部 x → x_dir，y → y_dir，z → x_dir × y_dir"""
    x, y = Vector(x_dir).normalized(), Vector(y_dir).normalized()
    z = x.cross(y)
    mt = Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))
    xform(bm, faces, mt)


def boxl(bm, lo, hi, mi):
    """和 boxf 一样，但返回面（给 oriented 用）"""
    before = set(bm.faces)
    boxf(bm, lo, hi, mi)
    return [f for f in bm.faces if f not in before]


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 Lathe
OBJS = []           # dict(ob, ex, no)

# 零件号 → (中文名, 材料, 作用)。信息牌上显示的就是这三行
INFO = {
    1: ('底板', '6061 铝合金板 8 mm，阳极氧化',
        '整台车床的地基。床身、主轴箱、电机座都用螺钉固定在它上面，底下 4 个橡胶脚垫防滑、减振。'),
    2: ('橡胶脚垫', '丁腈橡胶', '吸收切削振动，也防止车床在桌面上滑动。'),
    3: ('床身', '6061 铝合金型材', '一根长方铝块，顶上装直线导轨，前面装丝杠。床身的直和刚性决定了车出来的工件直不直。'),
    4: ('直线导轨', 'GCr15 轴承钢，淬火磨削', '拖板和尾座的滑块骑在这根导轨上左右滑动。一排沉孔里是固定导轨的螺钉。'),
    5: ('丝杠', '45 钢，梯形螺纹 T8 × 2', '转动左端手轮，丝杠带着拖板下面的铜螺母左右走，就是"纵向进给"：车刀沿工件轴线走一刀。'),
    6: ('纵向进给手轮', '铝合金', '装在丝杠左端。摇一圈拖板走 2 mm（一个螺距），手摇的快慢就是进给速度。'),
    7: ('主轴箱', '6061 铝合金主轴套 + 立板',
        '主轴套里前后各压一个轴承，把主轴撑住，让它只能转、不能晃。主轴套的轴线和导轨平行，车出来的才是圆柱而不是锥。'),
    8: ('主轴', '40Cr 钢，调质', '左端装卡盘，右端装皮带轮、用锁紧螺母压住。电机通过皮带带它转，工件跟着一起转。'),
    9: ('三爪卡盘（盘体）', '钢制盘体 + 黑色连接盘', '盘面上三条径向导槽，卡爪就在槽里滑。侧面的方孔插卡盘扳手，转的是里面的平面螺纹盘。'),
    10: ('卡爪', '45 钢，淬火', '背面一排弧形齿，啮合在平面螺纹盘的螺旋槽里。螺纹盘一转，三个卡爪同时往里或往外走，工件自动对中。'),
    11: ('工件（黄铜棒）', 'H59 黄铜 Φ18', '被卡盘夹住跟着主轴转，车刀从侧面切下一层层铜屑。黄铜软、切屑短，最适合小车床练手。'),
    12: ('拖板（大拖板）', '6061 铝合金', '装在导轨滑块上，下面挂着丝杠螺母，跟着丝杠左右走。顶上是安装十字滑台的螺孔。'),
    13: ('十字滑台（中拖板）', '6061 铝合金', '在拖板上前后移动，控制车刀切进工件多深（横向进给 = 吃刀深度）。'),
    14: ('横向进给手轮', '铝合金', '摇它，通过横向丝杠让十字滑台前后走。'),
    15: ('四方刀架', '6061 铝合金', '四个面都能夹车刀，松开中间的手柄螺母转 90° 就换一把刀，不用重新对刀。'),
    16: ('刀架压紧螺钉', '12.9 级内六角螺钉', '从上往下把车刀压在刀架里。车刀伸出越短越不容易振。'),
    17: ('外圆车刀', '高速钢 HSS 8 × 8', '车外圆、车端面。刀尖要对准主轴中心高：高了会顶、低了会啃。'),
    18: ('尾座', '6061 铝合金', '装在导轨滑块上，可以沿床身滑到任意位置再锁紧。里面的套筒能前后伸缩，用来顶住长工件或者钻孔。'),
    19: ('尾座手轮', '铝合金', '摇它，丝杆推着套筒伸出 / 缩回：钻孔时就是靠它把钻头推进工件。'),
    20: ('钻夹头（含过渡套、顶尖）', '钢制钻夹头 + 黄铜过渡套（B10 锥）', '插在尾座套筒前端。夹钻头就能在工件端面中心钻孔；换成顶尖可以顶住细长工件的另一头。'),
    21: ('尾座锁紧螺钉', '滚花铝头 + M6 钢螺杆', '拧紧后套筒就不会被切削力推回去。'),
    22: ('皮带罩', '6061 铝合金', '罩住皮带和皮带轮，防止手指、头发、衣服卷进去。拆皮带前先拆它。'),
    23: ('传动皮带', '聚氨酯圆带', '把电机的转动传给主轴。大轮带小轮：电机轮小、主轴轮大，转速降下来、扭矩变大。'),
    24: ('主轴皮带轮', '铝合金', 'Φ48，和电机皮带轮的直径比约 2.7 : 1，所以主轴比电机慢 2.7 倍、扭力大 2.7 倍。'),
    25: ('电机皮带轮', '铝合金', 'Φ18，装在电机轴上。'),
    26: ('电机座', '铝合金座 + 两道抱箍', '把电机抱在床身前面，电机轴和主轴平行，皮带才能对齐。'),
    27: ('直流电机外壳', '冷轧钢板机壳 · 喷塑', '机壳也是磁路的一部分：两块磁钢的磁力线从一块出来，穿过转子，再经机壳绕回另一块。'),
    28: ('电源线（DC 插头）', 'PVC 护套线 + DC 5.5 × 2.1 插头', '接 24 V 电源适配器，给电机供电。沿着床身前面走线，不挡拖板。'),
    29: ('底板锁紧螺丝', '滚花铝头 + M5 螺杆', '把床身锁在底板上。松开后床身可以微调对中。'),
    30: ('主轴前轴承', '6202 深沟球轴承', '离卡盘近，承受切削力的大头。轴承间隙大了，车出来的工件表面就有振纹。'),
    31: ('主轴后轴承', '6202 深沟球轴承', '和前轴承一起把主轴架成一根稳定的"两点支撑梁"。'),
    32: ('主轴锁紧螺母', '45 钢，M14 × 1', '把皮带轮和轴承压紧在主轴上，防止主轴前后窜动。'),
    33: ('油杯', '黄铜', '往主轴轴承里加润滑油的地方。'),
    34: ('平面螺纹盘', '45 钢', '正面是一条阿基米德螺旋槽，三个卡爪背面的齿都啮合在槽里；背面一圈伞齿，被扳手插进去的小伞齿轮带着转。'),
    35: ('卡盘扳手', '45 钢，发黑', '方头插进卡盘侧面的方孔，转一下三个卡爪就同时夹紧或松开。用完一定要拔下来，忘了就开机会把它甩出去。'),
    36: ('导轨滑块', '轴承钢，内含滚珠', '骑在直线导轨上，里面一圈圈滚珠循环滚动，所以推起来又轻又没有间隙。'),
    37: ('丝杠螺母', 'H62 黄铜', '挂在拖板下面，套在丝杠上。丝杠一转，螺母连同拖板一起沿轴线走。用铜做是因为铜和钢配对耐磨、不咬死。'),
    38: ('横向丝杠', '45 钢，M6 × 1', '藏在十字滑台里面，横向手轮转一圈，滑台前后走 1 mm。'),
    39: ('刀架中心螺柱', '45 钢', '四方刀架就套在这根螺柱上转，上面的手柄螺母把刀架压死在滑台上。'),
    40: ('刀架手柄螺母', '45 钢 + 胶木球', '松开它，刀架就能转 90° 换刀；拧紧它，刀架就纹丝不动。'),
    41: ('切断刀', '高速钢 HSS 刀片 3 mm', '很窄的刀片，从侧面切进去把工件切断。'),
    42: ('尾座套筒', '45 钢，镀铬', '在尾座里前后伸缩，前端是莫氏锥孔，插钻夹头或顶尖。上面的长槽卡着导向键，所以套筒只能直着走、不能转。'),
    43: ('尾座丝杆', '45 钢', '一头连手轮，一头拧在套筒尾部的螺母里：手轮转，套筒就直线伸缩。'),
    44: ('电机端盖', '压铸铝', '装着电刷架，中间是轴承。端面上的散热孔让转子转起来时把热风甩出去。'),
    45: ('电机转子（电枢）', '硅钢片铁芯 + 漆包铜线 + 铜换向器',
         '电流经电刷、换向器流进绕组，绕组在磁钢的磁场里受力转起来；每转过一格，换向器就把电流方向倒一次，所以能一直朝一个方向转。'),
    46: ('磁钢', '铁氧体永磁，一 N 一 S', '贴在机壳内壁上，给转子提供固定的磁场。'),
    47: ('电刷', '碳刷 + 黄铜刷架', '碳刷被弹簧压在换向器上，转子转着它也一直接触，把电流送进去。用久了会磨短，要换。'),
    48: ('端盖螺钉', 'M3 十字盘头螺钉', '把端盖固定在机壳上。'),
    49: ('导轨固定螺钉', 'M4 内六角螺钉', '藏在导轨顶面的沉孔里，把导轨拉紧在床身上。沉孔让螺钉头低于导轨面，滑块才能从上面滑过去。'),
    50: ('床身固定螺钉', 'M5 内六角螺钉', '从上往下把床身拉紧在底板上。'),
    51: ('铜手柄', 'H62 黄铜', '套在手轮的销子上，手捏着它摇，手柄自己会转，所以手不会被磨。'),
    52: ('刻度环', '铝合金，激光刻线', '一圈 50 格、一格 0.02 mm：车刀往里进 0.1 mm，工件直径就小 0.2 mm（两边都被车掉）。'),
    53: ('皮带罩螺钉', 'M4 内六角螺钉', '把皮带罩固定在主轴箱立板上。'),
}


def finish(name, no, bm, mats, ex=(), bevel=0.0, seg=2, angle=50, smooth=34):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('Lathe').objects.link(ob)
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
    ob.data.transform(Matrix.Scale(MM, 4))
    ob.parent = ROOT
    ob['name_cn'] = INFO[no][0]
    OBJS.append(dict(ob=ob, ex=list(ex), no=no))
    return ob


# ---------------------------------------------------------------- 主要尺寸 (mm)
BT = 13.0              # 底板顶面
CZ = 100.0             # 主轴中心高（离脚垫底面）
BED_TOP = 48.0         # 床身顶面
RAIL_TOP = 58.0        # 导轨顶面
SLIDE_TOP = 61.0       # 导轨滑块顶面（拖板、尾座底座的底面）
LS = (-27.0, 32.0)     # 丝杠轴线 (y, z)
MOT = (-50.0, 40.0)    # 电机轴线 (y, z)

# 爆炸路线（毫米，Blender 坐标；最后一个数 = 出场时刻 0~1，按真实拆机顺序：先拆刀具和小件，最后抬起主轴箱）
# 路线完全相同的零件在虚幻里会合成一个抓取单元，所以同一组件里的零件故意错开一点
M50 = (0, -50, 0, .74)          # 电机整体先往前抽出来
EX = dict(
    chuck_key=[(0, 0, 25, .01)],
    lever_nut=[(0, 0, 75, .02)],
    toolpost_screw=[(0, 0, 95, .04)],
    handwheel_z=[(-40, 0, 0, .06)],
    handle_z=[(-40, 0, 0, .06), (-18, 0, 0, .09)],
    toolpost=[(0, 0, 55, .10)],
    tool=[(0, 0, 55, .10), (0, -30, 0, .16)],
    parting=[(0, 0, 55, .10), (-25, 0, 0, .17)],
    cross_wheel=[(0, 35, 0, .14)],
    cross_handle=[(0, 35, 0, .14), (0, 12, 0, .17)],
    dial=[(0, 22, 0, .14)],
    cross_slide=[(0, 0, 30, .20)],
    stud=[(0, 0, 30, .20), (0, -25, 0, .23)],
    cross_screw=[(0, 0, 18, .22)],
    work=[(-20, -75, 0, .24)],
    carriage=[(0, 0, 10, .28)],
    nut=[(0, 0, 10, .28), (0, -28, 0, .32)],
    car_block=[(0, 0, 6, .31)],
    chuck=[(-25, 0, 0, .36)],
    scroll=[(-25, 0, 0, .36), (0, -55, 0, .40)],
    lock=[(0, 0, 60, .42)],
    drill=[(25, 0, 40, .40)],
    quill=[(35, 0, 0, .48), (0, -45, 0, .52)],
    tail_wheel=[(-35, 0, 0, .48)],
    tail_handle=[(-35, 0, 0, .48), (-18, 0, 0, .51)],
    tail_screw=[(-20, 0, 0, .50)],
    tailstock=[(-20, 0, 40, .52)],
    tail_block=[(0, 0, 8, .55)],
    cover_screw=[(100, 0, 0, .55)],
    cover=[(70, 0, 0, .58)],
    belt=[(40, 0, 0, .64)],
    spindle_nut=[(26, 0, 0, .67)],
    pulley_s=[(22, 0, 0, .70)],
    pulley_m=[(20, 0, 0, .70)],
    motor=[M50],
    end_screw=[M50, (-30, 0, 0, .80)],
    end_cap=[M50, (-20, 0, 0, .82), (0, 0, 45, .86)],
    rotor=[M50, (-110, 0, 0, .90)],
    leadscrew=[(0, -30, 0, .82)],
    knob=[(0, 0, 30, .86)],
    oil_cup=[(0, 0, 75, .88)],
    headstock=[(0, 0, 60, .90)],
    spindle=[(0, 0, 25, .94)],
    bearing_f=[(0, 0, 25, .94), (-25, 0, 0, .97)],
    bearing_r=[(0, 0, 25, .94), (20, 0, 0, .97)],
    rail_screw=[(0, 0, 22, .96)],
    bed_screw=[(0, 0, 20, .98)],
)


# ---------------------------------------------------------------- 各零件
def build_base(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    extrude(bm, [rrect(180, 70, 6, cx=-10, cy=-10)], 5, BT, 0)
    for x in (-180, 160):            # 四角的安装沉孔
        for y in (-72, 52):
            disk(bm, 3.6, (x, y, BT), 'Z', 1)
            disk(bm, 2.0, (x, y, BT + .3), 'Z', 1, h=.2, seg=6)
    finish('P01_BasePlate', 1, bm, mats, bevel=.8)
    for i, (x, y) in enumerate(((-170, -62), (150, -62), (-170, 42), (150, 42))):
        bm = bmesh.new()
        rev(bm, [(0, 0), (7.5, 0), (9, 1.2), (9, 5), (0, 5)], 0, 'Z', (x, y, 0), seg=28)
        finish(f'P02_Foot_{i + 1}', 2, bm, [M['rubber']])

    # 卡盘扳手：平放在底板后面（T 字：方头 + 杆 + 横柄）
    bm = bmesh.new()
    zc = BT + 3.5
    boxf(bm, (-102, 38.2, zc - 2.3), (-92, 42.8, zc + 2.3), 0)
    rod(bm, 3.5, -92, -52, 0, 'X', (0, 40.5, zc), seg=20)
    rod(bm, 3, 22, 59, 0, 'Y', (-50, 0, zc), seg=20)
    rod(bm, 4.5, -56, -46, 0, 'X', (0, 40.5, zc), seg=20)
    finish('P35_ChuckKey', 35, bm, [M['black']], ex=EX['chuck_key'], bevel=.4)


def build_bed(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (-178, -20, BT), (95, 20, BED_TOP), 0)
    # 丝杠两端的轴承座
    for x0, x1 in ((-178, -168), (78, 88)):
        boxf(bm, (x0, -34, 20), (x1, -20, 44), 0)
        disk(bm, 5, (x0 if x0 < 0 else x1, LS[0], LS[1]), '-X' if x0 < 0 else 'X', 1)
    # 床身前面的工艺孔
    for x in (-140, -60, 20):
        disk(bm, 3, (x, -20, 26), '-Y', 1)
    finish('P03_Bed', 3, bm, mats, bevel=1.0)

    bm = bmesh.new()
    boxf(bm, (-170, -8, BED_TOP), (90, 8, RAIL_TOP), 0)
    for y in (-8, 8):                 # 导轨两侧的滚道槽
        boxf(bm, (-170, y - .4, RAIL_TOP - 5), (90, y + .4, RAIL_TOP - 3), 1)
    for k in range(13):               # 一排沉孔（螺钉头在下面，P49）
        disk(bm, 3.2, (-160 + k * 20, 0, RAIL_TOP), 'Z', 1)
    finish('P04_Rail', 4, bm, [M['steel'], M['hole']], bevel=.5)

    # 导轨固定螺钉：9 颗一组。拖板正下方那 4 个沉孔（X -20 / 0 / 20 / 40）没放螺钉：
    # 拖板拆开只抬起 10mm，螺钉往上拔会顶进拖板里；装配状态下那几个孔本来就被拖板盖住
    for i, x in enumerate((-160, -140, -120, -100, -80, -60, -40, 60, 80)):
        bm = bmesh.new()
        socket_screw(bm, 2.8, 3.0, 9, 0, 1, 'Z', (x, 0, RAIL_TOP - 3.2))
        finish(f'P49_RailScrew_{i + 1}', 49, bm, [M['black'], M['hole']], ex=EX['rail_screw'])

    for i, (x, y) in enumerate(((-165, -14), (-60, -14), (70, -14), (-165, 14), (-60, 14), (70, 14))):
        bm = bmesh.new()
        socket_screw(bm, 3.2, 3.5, 12, 0, 1, 'Z', (x, y, BED_TOP))
        finish(f'P50_BedScrew_{i + 1}', 50, bm, [M['black'], M['hole']], ex=EX['bed_screw'])


def build_leadscrew(M):
    bm = bmesh.new()
    rod(bm, 3.4, -184, -176, 0, 'X', (0, LS[0], LS[1]), seg=16)        # 光轴端（装手轮）
    thread_rod(bm, 3.3, 1.0, 2.0, -176, 80, 0, 'X', (0, LS[0], LS[1]))
    rod(bm, 3.4, 80, 86, 0, 'X', (0, LS[0], LS[1]), seg=16)
    finish('P05_LeadScrew', 5, bm, [M['steel']], ex=EX['leadscrew'])

    bm = bmesh.new()
    handwheel(bm, 19, (-182, LS[0], LS[1]), '-X', 0, None)
    finish('P06_HandwheelZ', 6, bm, [M['alu']], ex=EX['handwheel_z'], smooth=40)
    bm = bmesh.new()
    handle(bm, 19, (-182, LS[0], LS[1]), '-X', 0)
    finish('P51_Handle_Z', 51, bm, [M['copper']], ex=EX['handle_z'], smooth=40)


def build_headstock(M):
    """照片里的主轴箱：一个横放的铝圆筒（主轴套），坐在皮带罩前面的立板上；里面前后两个轴承"""
    mats = [M['alu'], M['hole'], M['steel']]
    bm = bmesh.new()
    rev(bm, [(0, 92), (27, 92), (28, 93), (28, 149), (27, 150), (0, 150)], 0, 'X', (0, 0, CZ), seg=64)   # 主轴套
    rev(bm, [(15, 0), (20, 0), (20, .3), (15, .3)], 1, '-X', (92, 0, CZ), seg=48, closed=True)            # 前端轴承孔的暗圈
    boxf(bm, (100, 0, BT), (146, 26, CZ - 12), 0)                                                         # 立板
    for k in range(4):                                                                                    # 后面的锁紧螺钉孔
        disk(bm, 2.2, (104 + k * 12, 26, CZ - 30), 'Y', 1)
    disk(bm, 3.4, (120, 0, CZ + 28), 'Z', 1, h=.2)                                                        # 油杯座
    finish('P07_Headstock', 7, bm, mats, ex=EX['headstock'], bevel=1.0)

    bm = bmesh.new()
    rev(bm, [(0, 0), (7, 0), (8, 1), (8, 82), (7, 82), (7, 90), (0, 90)], 0, 'X', (70, 0, CZ), seg=32)
    boxf(bm, (128, -2, CZ + 6.6), (148, 2, CZ + 8.2), 1)                                                  # 键槽
    finish('P08_Spindle', 8, bm, [M['steel'], M['hole']], ex=EX['spindle'])

    for name, no, x0, ex in (('P30_BearingFront', 30, 93, EX['bearing_f']), ('P31_BearingRear', 31, 141, EX['bearing_r'])):
        bm = bmesh.new()
        rev(bm, [(8, 0), (14, 0), (14, 8), (8, 8)], 0, 'X', (x0, 0, CZ), seg=40, closed=True)             # 内外圈（看成一体）
        rev(bm, [(10, -.2), (12, -.2), (12, 8.2), (10, 8.2)], 1, 'X', (x0, 0, CZ), seg=40, closed=True)   # 黑色密封圈
        finish(name, no, bm, [M['steel'], M['black']], ex=ex)

    bm = bmesh.new()
    rev(bm, [(7, 0), (11, 0), (11, 2.5), (7, 2.5)], 0, 'X', (159, 0, CZ), seg=6, closed=True)                # 六角锁紧螺母
    finish('P32_SpindleNut', 32, bm, [M['steel']], ex=EX['spindle_nut'], bevel=.3)

    bm = bmesh.new()
    rod(bm, 2.6, CZ + 27, CZ + 32, 0, 'Z', (120, 0, 0), seg=6)
    rev(bm, [(0, CZ + 32), (4.5, CZ + 32), (4.5, CZ + 35), (3, CZ + 37), (0, CZ + 37)], 0, 'Z', (120, 0, 0), seg=24)
    finish('P33_OilCup', 33, bm, [M['brass']], ex=EX['oil_cup'])


def build_chuck(M):
    bm = bmesh.new()
    rev(bm, [(0, 86), (27, 86), (27, 92), (0, 92)], 1, 'Z', seg=64)                  # 黑色连接盘
    rev(bm, [(0, 68), (22, 68), (24.5, 69), (25, 71), (25, 86), (0, 86)], 0, 'Z', seg=64)   # 盘体
    xform(bm, bm.faces, Matrix.Translation(Vector((0, 0, CZ))) @ ROT['X'])
    disk(bm, 8, (67.7, 0, CZ), '-X', 2, h=.35)                                            # 中心孔
    for k in range(3):
        a = pi / 2 + 2 * pi * k / 3
        d = Vector((0, cos(a), sin(a)))
        t = Vector((0, -sin(a), cos(a)))
        fs = boxl(bm, (-.4, 8, -3.8), (0, 24.6, 3.8), 2)                                 # 盘面上的卡爪导槽
        oriented(bm, fs, (68, 0, CZ), (1, 0, 0), d)
        a2 = pi / 3 + 2 * pi * k / 3                                                      # 侧面 3 个扳手方孔
        d2 = Vector((0, cos(a2), sin(a2)))
        c = Vector((78, 0, CZ)) + d2 * 24.8
        fs = rod(bm, 2.4, 0, .5, 2, 'Z', (0, 0, 0), seg=4)
        xform(bm, fs, Matrix.Translation(c) @ d2.to_track_quat('Z', 'X').to_matrix().to_4x4())
    finish('P09_Chuck', 9, bm, [M['steel'], M['black'], M['hole']], ex=EX['chuck'], bevel=.6)

    # 平面螺纹盘：正面一条阿基米德螺旋凸棱，背面一圈伞齿
    bm = bmesh.new()
    rod(bm, 21, 75, 81, 0, 'X', (0, 0, CZ), seg=56)
    rev(bm, [(0, 74), (9, 74), (9, 75), (0, 75)], 1, 'X', (0, 0, CZ), seg=32)
    spiral = [Vector((74.6, (9.5 + 11 * u) * cos(6 * pi * u), CZ + (9.5 + 11 * u) * sin(6 * pi * u))) for u in
              [i / 180 for i in range(181)]]
    sweep(bm, spiral, .7, 0, sides=6)
    for k in range(36):
        a = 2 * pi * k / 36
        fs = boxl(bm, (0, 16, -1), (2.2, 20.5, 1), 0)
        oriented(bm, fs, (81, 0, CZ), (1, 0, 0), (0, cos(a), sin(a)))
    finish('P34_Scroll', 34, bm, [M['steel'], M['black']], ex=EX['scroll'])

    for k in range(3):
        a = pi / 2 + 2 * pi * k / 3
        d = (0, cos(a), sin(a))
        bm = bmesh.new()
        # 局部坐标：x = 轴向（主轴 X），y = 径向，z = 切向。台阶爪：越往外越短；背面（+x）一排弧形齿
        fs = boxl(bm, (58, 9, -3.5), (68, 16, 3.5), 0)
        fs += boxl(bm, (61, 16, -3.5), (68, 20, 3.5), 0)
        fs += boxl(bm, (64, 20, -3.5), (68, 23.5, 3.5), 0)
        for r0 in (10, 13, 16, 19):
            fs += boxl(bm, (68, r0, -3.2), (70.2, r0 + 1.6, 3.2), 0)
        oriented(bm, fs, (0, 0, CZ), (1, 0, 0), d)
        ex = [(0, 18 * d[1], 18 * d[2], .30)] + EX['chuck']
        finish(f'P10_Jaw_{k + 1}', 10, bm, [M['steel']], ex=ex, bevel=.3)

    bm = bmesh.new()
    rev(bm, [(0, 0), (8.5, 0), (9, .5), (9, 54), (0, 54)], 0, 'X', (10, 0, CZ), seg=40)
    finish('P11_Workpiece', 11, bm, [M['brass']], ex=EX['work'])


def build_carriage(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (-20, -40, SLIDE_TOP), (40, 40, 80), 0)
    boxf(bm, (0, -36, 40), (20, -20, SLIDE_TOP), 0)          # 前面下垂的丝杠螺母座
    boxf(bm, (3, -40.3, 64), (17, -40, 77), 1)               # 正面方孔
    for x in (-12, 28):                                     # 两个燕尾压板小块
        boxf(bm, (x - 4, -44, 65), (x + 4, -40, 75), 0)
        disk(bm, 1.6, (x, -44, 70), '-Y', 1)
    for x in (-15, 35):                                     # 顶面螺孔
        for y in (-34, -10, 14, 34):
            disk(bm, 2.4, (x, y, 80), 'Z', 1)
    finish('P12_Carriage', 12, bm, mats, ex=EX['carriage'], bevel=1.0)

    # 两个导轨滑块：U 形，骑在导轨上
    for name, (x0, x1), ex in (('P36_RailBlock_Carriage', (-15, 35), EX['car_block']),
                               ('P36_RailBlock_Tailstock', (-145, -110), EX['tail_block'])):
        bm = bmesh.new()
        boxf(bm, (x0, -13, RAIL_TOP), (x1, 13, SLIDE_TOP), 0)
        for y0, y1 in ((-13, -8.4), (8.4, 13)):
            boxf(bm, (x0, y0, RAIL_TOP - 7), (x1, y1, RAIL_TOP), 0)
        for xe in (x0 - 2, x1):                             # 两头的黑色防尘端盖
            boxf(bm, (xe, -13, RAIL_TOP - 7), (xe + 2, 13, SLIDE_TOP - .5), 1)
        finish(name, 36, bm, [M['steel'], M['black']], ex=ex, bevel=.4)

    bm = bmesh.new()                                        # 黄铜丝杠螺母
    boxf(bm, (2, -34, 26), (18, -20, 40), 0)
    for x in (5, 15):
        disk(bm, 1.6, (x, -34, 36), '-Y', 1)
    finish('P37_LeadNut', 37, bm, [M['brass'], M['hole']], ex=EX['nut'], bevel=.4)

    bm = bmesh.new()
    boxf(bm, (-12, -38, 80), (32, 30, 90), 0)
    for x in (-8, 28):
        for y in (-5, 25):
            disk(bm, 2.2, (x, y, 90), 'Z', 1)
    finish('P13_CrossSlide', 13, bm, mats, ex=EX['cross_slide'], bevel=.8)

    bm = bmesh.new()                                        # 横向丝杠（藏在滑台里）
    thread_rod(bm, 2.5, .7, 1.0, -32, 30, 0, 'Y', (10, 0, 85), seg=10, per_pitch=5)
    finish('P38_CrossScrew', 38, bm, [M['steel']], ex=EX['cross_screw'])

    bm = bmesh.new()
    rod(bm, 2.5, 0, 6, 1, 'Y', (10, 30, 85), seg=16)           # 轴
    handwheel(bm, 11, (10, 39, 85), 'Y', 0, None)
    finish('P14_CrossWheel', 14, bm, [M['alu'], M['black']], ex=EX['cross_wheel'], smooth=40)
    bm = bmesh.new()
    handle(bm, 11, (10, 39, 85), 'Y', 0, handle_len=12, handle_r=2.3)
    finish('P51_Handle_Cross', 51, bm, [M['copper']], ex=EX['cross_handle'], smooth=40)

    bm = bmesh.new()                                        # 刻度环 + 50 格刻线
    rev(bm, [(3, 0), (9, 0), (9, 5), (3, 5)], 0, 'Y', (10, 34, 85), seg=50, closed=True)
    for k in range(50):
        a = 2 * pi * k / 50
        L = 2.2 if k % 5 == 0 else 1.2
        bmt = bmesh.ops.create_cube(bm, size=1.0)
        vs = bmt['verts']
        bmesh.ops.scale(bm, vec=Vector((.3, 2.5, L)), verts=vs)
        bmesh.ops.translate(bm, vec=Vector((0, 0, 9 - L / 2 + .2)), verts=vs)
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(a, 3, 'Y'), verts=vs)
        bmesh.ops.translate(bm, vec=Vector((10, 36.5, 85)), verts=vs)
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = 1
    finish('P52_Dial', 52, bm, [M['alu_dark'], M['black']], ex=EX['dial'], smooth=40)

    bm = bmesh.new()
    boxf(bm, (5, -45, 90), (35, -15, 116), 0)
    boxf(bm, (5.5, -45.3, 92), (34.5, -45, 101), 1)            # 正面夹刀槽
    boxf(bm, (4.7, -44.5, 92), (5, -15.5, 101), 1)             # 左面夹刀槽（切断刀）
    disk(bm, 4.4, (20, -30, 116), 'Z', 1, h=.2)                # 中心孔
    finish('P15_ToolPost', 15, bm, [M['alu'], M['hole']], ex=EX['toolpost'], bevel=.8)

    for i, (x, y) in enumerate(((12, -38), (28, -38), (12, -22), (28, -22))):
        bm = bmesh.new()
        socket_screw(bm, 3.6, 4.5, 6, 0, 1, 'Z', (x, y, 116))
        finish(f'P16_ToolScrew_{i + 1}', 16, bm, [M['black'], M['hole']], ex=EX['toolpost_screw'])

    bm = bmesh.new()                                        # 中心螺柱（下端拧在滑台里）
    thread_rod(bm, 3.4, .6, 1.25, 84, 115, 0, 'Z', (20, -30, 0), seg=10, per_pitch=4)
    finish('P39_PostStud', 39, bm, [M['steel']], ex=EX['stud'])

    bm = bmesh.new()                                        # 手柄螺母：六角 + 杆 + 胶木球
    rev(bm, [(0, 116), (6.5, 116), (6.5, 122), (0, 122)], 0, 'Z', (20, -30, 0), seg=6)
    rod(bm, 2.2, -30, -4, 0, 'Y', (20, 0, 119), seg=12)
    rev(bm, [(0, -6), (3, -5.2), (4.2, -3), (4.5, 0), (4.2, 3), (3, 5.2), (0, 6)], 1, 'Y', (20, -1, 119), seg=20)
    finish('P40_LeverNut', 40, bm, [M['steel'], M['black']], ex=EX['lever_nut'], bevel=.3)

    bm = bmesh.new()
    boxf(bm, (18, -52, 93), (25, -12, 100), 0)
    # 刀尖：前端斜磨
    v = [bm.verts.new(p) for p in ((18, -12, 93), (25, -12, 93), (25, -12, 100), (18, -12, 100),
                                   (19, -9.5, 97), (23, -9.5, 97))]
    for f in ((v[0], v[1], v[5], v[4]), (v[1], v[2], v[5]), (v[2], v[3], v[4], v[5]), (v[3], v[0], v[4])):
        bm.faces.new(f).material_index = 0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=.01)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    finish('P17_ToolBit', 17, bm, [M['tool']], ex=EX['tool'])

    bm = bmesh.new()                                        # 切断刀：刀柄 + 窄刀片
    boxf(bm, (-6, -34, 93), (14, -26, 100), 0)
    boxf(bm, (-16, -31.5, 93.5), (-6, -28.5, 102), 1)
    finish('P41_PartingTool', 41, bm, [M['tool'], M['steel']], ex=EX['parting'], bevel=.3)


def build_tailstock(M):
    mats = [M['alu'], M['hole'], M['steel']]
    bm = bmesh.new()
    boxf(bm, (-150, -30, SLIDE_TOP), (-105, 30, 80), 0)           # 方底座（装在滑块上）
    for x in (-140, -115):                                       # 底座正面两个孔
        disk(bm, 3.5, (x, -30, 70), '-Y', 1)
    boxf(bm, (-145, -14, 80), (-110, 14, 86), 0)                  # 立柱
    rev(bm, [(0, -160), (17, -160), (18, -159), (18, -101), (17, -100), (0, -100)], 0, 'X', (0, 0, CZ), seg=56)  # 套筒座
    rev(bm, [(0, -169), (9, -169), (10, -168), (10, -160), (0, -160)], 0, 'X', (0, 0, CZ), seg=32)
    rev(bm, [(11, 0), (13.5, 0), (13.5, .3), (11, .3)], 1, 'X', (-100, 0, CZ), seg=40, closed=True)   # 套筒孔口的暗圈
    for k in range(2):
        disk(bm, 2.2, (-150 + 20 * k + 15, 0, CZ + 18), 'Z', 1)
    finish('P18_Tailstock', 18, bm, mats, ex=EX['tailstock'], bevel=1.0)

    bm = bmesh.new()                                             # 套筒：镀铬钢管，顶上一条导向键槽
    rev(bm, [(0, -158), (10.6, -158), (11, -157.5), (11, -87), (10.5, -86), (0, -86)], 0, 'X', (0, 0, CZ), seg=40)
    boxf(bm, (-150, -1.5, CZ + 10.7), (-104, 1.5, CZ + 11.1), 1)
    for k in range(6):                                           # 刻度
        boxf(bm, (-99 + k * 2.5, -.3, CZ + 10.95), (-98.4 + k * 2.5, .3, CZ + 11.15), 1)
    finish('P42_Quill', 42, bm, [M['steel'], M['black']], ex=EX['quill'])

    bm = bmesh.new()
    rod(bm, 4, -176, -150, 0, 'X', (0, 0, CZ), seg=16)
    thread_rod(bm, 3.4, .8, 1.5, -150, -112, 0, 'X', (0, 0, CZ), seg=12, per_pitch=5)
    finish('P43_TailScrew', 43, bm, [M['steel']], ex=EX['tail_screw'])

    bm = bmesh.new()
    handwheel(bm, 19, (-169, 0, CZ), '-X', 0, None)
    finish('P19_TailWheel', 19, bm, [M['alu']], ex=EX['tail_wheel'], smooth=40)
    bm = bmesh.new()
    handle(bm, 19, (-169, 0, CZ), '-X', 0)
    finish('P51_Handle_Tail', 51, bm, [M['copper']], ex=EX['tail_handle'], smooth=40)

    bm = bmesh.new()
    rev(bm, [(0, 0), (8.5, 0), (9, 1), (9, 8), (0, 8)], 1, '-X', (-78, 0, CZ), seg=40)          # 黄铜过渡套 X -86..-78
    rev(bm, [(0, 0), (13, 0), (14, 1), (14, 14), (12, 16), (10, 24), (5, 28), (0, 28)], 0, 'X', (-78, 0, CZ), seg=48)
    for k in range(24):                                          # 钻夹头外套的竖纹
        a = 2 * pi * k / 24
        c = Vector((-72, 14 * cos(a), CZ + 14 * sin(a)))
        boxf(bm, (c.x - 4, c.y - .5, c.z - .5), (c.x + 4, c.y + .5, c.z + .5), 0)
    for k in range(3):                                           # 扳手孔
        a = 2 * pi * k / 3
        c = Vector((-62.5, 13 * cos(a), CZ + 13 * sin(a)))
        fs = rod(bm, 1.3, 0, .4, 3, 'Z', (0, 0, 0), seg=10)
        d = Vector((0, cos(a), sin(a)))
        xform(bm, fs, Matrix.Translation(c) @ d.to_track_quat('Z', 'X').to_matrix().to_4x4())
    rev(bm, [(0, 28), (4, 28), (0, 40)], 2, 'X', (-78, 0, CZ), seg=24)                       # 顶尖
    finish('P20_DrillChuck', 20, bm, [M['steel'], M['brass'], M['steel'], M['hole']], ex=EX['drill'])

    bm = bmesh.new()
    rod(bm, 3, 116, 124, 1, 'Z', (-128, 0, 0), seg=16)
    knurl(bm, 7, 124, 132, 0, 'Z', (-128, 0, 0))
    finish('P21_TailLock', 21, bm, [M['alu'], M['steel']], ex=EX['lock'])


def build_drive(M):
    """皮带罩（3 颗螺钉）、皮带、两个皮带轮"""
    outer = hull(circle(0, CZ, 34, 48) + circle(MOT[0], MOT[1], 24, 32) + [(-80, BT), (36, BT)])
    inner = hull(circle(0, CZ, 31, 48) + circle(MOT[0], MOT[1], 21, 32) + [(-77, BT + 3), (33, BT + 3)])
    bm = bmesh.new()
    extrude(bm, [outer, inner[::-1]], 150, 161, 0, axis='X')
    extrude(bm, [outer], 161, 164, 0, axis='X')
    extrude(bm, [outer], 148.5, 150, 0, axis='X')
    finish('P22_BeltCover', 22, bm, [M['alu'], M['hole']], ex=EX['cover'], bevel=1.0)

    for i, (y, z) in enumerate(((0, CZ + 22), (-62, 24), (24, 24))):
        bm = bmesh.new()
        socket_screw(bm, 2.8, 3, 8, 0, 1, 'X', (164, y, z))
        finish(f'P53_CoverScrew_{i + 1}', 53, bm, [M['black'], M['hole']], ex=EX['cover_screw'])

    pts = hull(circle(0, CZ, 22.5, 64) + circle(MOT[0], MOT[1], 7.5, 32))
    path = [Vector((155.5, p[0], p[1])) for p in pts]
    bm = bmesh.new()
    sweep(bm, path, 2.2, 0, sides=10, closed=True, plane_n=Vector((1, 0, 0)))
    finish('P23_Belt', 23, bm, [M['belt']], ex=EX['belt'])

    for name, no, r, (y, z), ex in (('P24_SpindlePulley', 24, 24, (0, CZ), EX['pulley_s']),
                                    ('P25_MotorPulley', 25, 9, MOT, EX['pulley_m'])):
        bm = bmesh.new()
        rev(bm, [(0, 0), (r, 0), (r, 1.5), (r - 2.5, 3.5), (r, 5.5), (r, 7), (0, 7)], 0, 'X', (152, y, z), seg=56)
        if r > 15:                                                   # 大轮上的 4 个减重孔
            for k in range(4):
                a = pi / 4 + k * pi / 2
                disk(bm, 4, (151.7, y + 14 * cos(a), z + 14 * sin(a)), '-X', 1, h=.35)
        disk(bm, 1.2, (158.2, y, z + r), 'Z', 1, h=.2, seg=6)        # 顶丝孔
        finish(name, no, bm, [M['alu_dark'], M['hole']], ex=ex)


def build_motor(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (60, -72, BT), (130, -28, BT + 4), 0)
    for x in (70, 112):
        rev(bm, [(24, 0), (26.5, 0), (26.5, 8), (24, 8)], 0, 'X', (x, MOT[0], MOT[1]), seg=48, closed=True)
        rod(bm, 2, 0, 4, 1, 'Z', (x + 4, MOT[0] - 27, BT + 4), seg=12)
    finish('P26_MotorMount', 26, bm, mats, bevel=.5)

    my, mz = MOT
    # 机壳：空心，右端封口带轴承座；中间一圈标签
    bm = bmesh.new()
    rev(bm, [(0, 144.5), (22.5, 144.5), (22.5, 41.5), (24, 40), (24, 144), (22, 146), (7, 146), (7, 149), (0, 149)],
        0, 'X', (0, my, mz), seg=56)
    rev(bm, [(24, 70), (24.15, 70), (24.15, 112), (24, 112)], 1, 'X', (0, my, mz), seg=56, closed=True)
    rev(bm, [(24.15, 74), (24.25, 74), (24.25, 80), (24.15, 80)], 2, 'X', (0, my, mz), seg=56, closed=True)
    finish('P27_Motor', 27, bm, [M['motor'], M['label'], M['black']], ex=EX['motor'])

    # 端盖：卡进机壳口，端面散热孔 + 中间轴承
    bm = bmesh.new()
    rev(bm, [(0, 30), (23, 30), (25, 32), (25, 40), (22.4, 40), (22.4, 42), (0, 42)], 0, 'X', (0, my, mz), seg=56)
    for k in range(6):
        a = k * pi / 3
        disk(bm, 2.6, (29.7, my + 11 * cos(a), mz + 11 * sin(a)), '-X', 1)
    rev(bm, [(0, 29.4), (5, 29.4), (5, 30), (0, 30)], 2, 'X', (0, my, mz), seg=24)
    finish('P44_MotorEndCap', 44, bm, [M['alu'], M['hole'], M['steel']], ex=EX['end_cap'], bevel=.5)

    for i, a in enumerate((pi / 2, -pi / 2)):
        bm = bmesh.new()
        socket_screw(bm, 2, 1.6, 8, 0, 1, '-X', (30, my + 18 * cos(a), mz + 18 * sin(a)))
        finish(f'P48_EndCapScrew_{i + 1}', 48, bm, [M['steel'], M['hole']], ex=EX['end_screw'])

    # 转子：轴 + 12 槽铁芯 + 两头绕组 + 铜换向器
    bm = bmesh.new()
    rod(bm, 2.5, 34, 159, 0, 'X', (0, my, mz), seg=16)
    star = []
    for k in range(24):
        a = 2 * pi * k / 24
        r = 15 if k % 2 == 0 else 9.5
        star.append((my + r * cos(a), mz + r * sin(a)))
    extrude(bm, [star], 58, 122, 1, axis='X')
    for x0 in (52, 122):
        rev(bm, [(5, 0), (13, 0), (14, 3), (13, 6), (5, 6)], 2, 'X', (x0, my, mz), seg=24, closed=True)
    rev(bm, [(2.5, 0), (6, 0), (6, 8), (2.5, 8)], 2, 'X', (43, my, mz), seg=24, closed=True)
    for k in range(12):
        a = 2 * pi * k / 12
        fs = boxl(bm, (0, 5.5, -.35), (8, 6.15, .35), 3)
        oriented(bm, fs, (43, my, mz), (1, 0, 0), (0, cos(a), sin(a)))
    finish('P45_Rotor', 45, bm, [M['steel'], M['lamination'], M['copper'], M['black']], ex=EX['rotor'])

    # 两块磁钢：瓦片形，左右各一块（±Y）
    for i, sgn in enumerate((1, -1)):
        bm = bmesh.new()
        arc = []
        for k in range(17):
            a = (-50 + 100 * k / 16) * pi / 180 + (0 if sgn > 0 else pi)
            arc.append((my + 22.3 * cos(a), mz + 22.3 * sin(a)))
        for k in range(16, -1, -1):
            a = (-50 + 100 * k / 16) * pi / 180 + (0 if sgn > 0 else pi)
            arc.append((my + 16.5 * cos(a), mz + 16.5 * sin(a)))
        extrude(bm, [arc], 58, 122, 0, axis='X')
        ex = [M50, (-70, 0, 0, .94), (0, 14 * sgn, 0, .97)]
        finish(f'P46_Magnet_{i + 1}', 46, bm, [M['magnet_n'] if sgn > 0 else M['magnet_s']], ex=ex, bevel=.3)

    # 两个电刷：上下各一，碳刷压在换向器上，刷架装在端盖里
    for i, sgn in enumerate((1, -1)):
        bm = bmesh.new()
        fs = boxl(bm, (44, 6.1, -2.5), (50, 11, 2.5), 0)
        fs += boxl(bm, (41.5, 11, -3.5), (50.5, 16, 3.5), 1)
        oriented(bm, fs, (0, my, mz), (1, 0, 0), (0, 0, sgn))
        ex = EX['end_cap'] + [(0, 0, 12 * sgn, .91)]
        finish(f'P47_Brush_{i + 1}', 47, bm, [M['carbon'], M['brass']], ex=ex, bevel=.2)

    ctrl = [Vector(p) for p in ((32, my - 12, mz - 8), (28, -68, 26), (18, -73, 17), (-20, -74, 16),
                                (-100, -74, 16), (-170, -73, 16), (-196, -70, 16))]
    bm = bmesh.new()
    sweep(bm, catmull(ctrl, per=10), 2.2, 0, sides=10)
    rev(bm, [(0, 0), (4.5, 0), (4.5, 12), (3, 14), (0, 14)], 0, '-X', (-196, -70, 16), seg=24)   # DC 插头
    for k in range(5):                                                                          # 插头尾巴的防折纹
        rev(bm, [(4.5, 0), (4.9, 0), (4.9, 1), (4.5, 1)], 0, '-X', (-185 + k * 2.2, -70.5, 16), seg=20, closed=True)
    rev(bm, [(0, 0), (2.8, 0), (2.8, 8), (0, 8)], 1, '-X', (-210, -70, 16), seg=20)
    finish('P28_PowerCord', 28, bm, [M['cable'], M['steel']], ex=EX['motor'])


def build_knobs(M):
    for i, x in enumerate((-160, -100, -40)):
        bm = bmesh.new()
        rod(bm, 2.5, BT, BT + 3, 1, 'Z', (x, -48, 0), seg=16)
        knurl(bm, 7, BT + 3, BT + 11, 0, 'Z', (x, -48, 0))
        rev(bm, [(0, BT + 11), (5.5, BT + 11), (5, BT + 11.6), (0, BT + 11.6)], 0, 'Z', (x, -48, 0), seg=30)
        finish(f'P29_LockKnob_{i + 1}', 29, bm, [M['alu'], M['steel']], ex=EX['knob'])


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
                k = lambda s, u=u: prog(1 - u, s)     # 装回时顺序反过来：最后拆的最先装
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
        bg.inputs[1].default_value = .35
    # 桌面
    bm = bmesh.new()
    box(bm, (0, 0, -5), (1600, 1200, 10), 0)
    me = bpy.data.meshes.new('Table')
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Scale(MM, 4))
    me.materials.append(principled('M_Table', '#7a6650', 0, .6))
    table = bpy.data.objects.new('Table', me)
    collection('Scene').objects.link(table)
    for name, loc, power, size in (('Key', (-.5, -.7, .9), 90, 1.2), ('Fill', (.7, -.4, .5), 35, 1.5),
                                   ('Rim', (.2, .8, .7), 60, 1.0)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, (0, 0, .07))
        collection('Scene').objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 50
    cam = bpy.data.objects.new('Cam', cd)
    cam.location = (-.30, -.62, .40)
    look_at(cam, (0.0, 0, .085))
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


def render_still(name, frame, w=1280, h=720):
    sc = bpy.context.scene
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
    ROOT = bpy.data.objects.new('Lathe', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .05
    collection('Lathe').objects.link(ROOT)
    build_base(M)
    build_bed(M)
    build_leadscrew(M)
    build_headstock(M)
    build_chuck(M)
    build_carriage(M)
    build_tailstock(M)
    build_drive(M)
    build_motor(M)
    build_knobs(M)
    setup_world_and_cam(M)
    animate_explode()
    viewport_defaults()
    export_glb(os.path.join(OUT, 'lathe.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'lathe.blend'))
    print('[OK] saved lathe.blend')
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
    print(f'[OK] {len(OBJS)} lathe objects, {tris} triangles, size {size} mm')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_assembled.png', 1)
        render_still('render_exploded.png', F_EXP[1] + 10)
        set_engine('EEVEE')


main()
