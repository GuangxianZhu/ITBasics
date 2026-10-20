# -*- coding: utf-8 -*-
"""
迷你桌面金属车床 —— Blender 脚本建模 + 爆炸图

照着一台常见的 8 合 1 迷你桌面车床（铝合金底板 + 直线导轨床身）的产品图建的，没有图纸，尺寸都是按比例估的：
    整机长约 37 cm（含两个手轮把手和 DC 插头），高约 13.5 cm；
    卡盘 Φ64、中心高（主轴轴线离底板顶面）87 mm，手轮 Φ38（约为卡盘的 0.6 倍）。
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


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 Drone（飞行动画只动它）
OBJS = []           # dict(ob, base, ex)  base/ex 单位 mm（Drone 局部坐标）
PROPS = []          # (prop_ob, disc_ob, spin)


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
    # 金属度封顶 0.8、粗糙度至少 0.3：虚幻工作室里没有反射探针，金属度 1 的镜面铝会反射成黑块
    return dict(
        alu=principled('M_Alu', '#b8bdc4', .8, .34),
        alu_dark=principled('M_Alu_Anodized', '#8e949c', .7, .4),
        steel=principled('M_Steel', '#a3a8ae', .8, .3),
        brass=principled('M_Brass', '#c9a24a', .8, .32),
        copper=principled('M_Copper_Handle', '#b8743a', .8, .34),
        black=principled('M_Black_Oxide', '#1e1f22', .3, .45),
        hole=principled('M_Hole', '#0b0b0c', 0, .8),
        rubber=principled('M_Rubber', '#141416', 0, .85),
        motor=principled('M_Motor_Can', '#3b3f45', .6, .42),
        belt=principled('M_Belt', '#1b1b1b', 0, .8),
        cable=principled('M_Cable', '#121212', 0, .55),
        tool=principled('M_HSS_Tool', '#6f757c', .8, .3),
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
    hx, hy = R * .68, 0.0
    fs += revolve(bm, [(0, 9), (handle_r - 1, 9), (handle_r, 13), (handle_r, 9 + handle_len - 3),
                       (handle_r - 1.2, 9 + handle_len), (0, 9 + handle_len)], mi_handle, seg=20, closed=False,
                  cy=hx, cz=hy)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 Lathe
OBJS = []           # dict(ob, ex, no)

# 零件号 → (中文名, 材料, 作用)。信息牌上显示的就是这三行
INFO = {
    1: ('底板', '6061 铝合金板 8 mm，阳极氧化',
        '整台车床的地基。床身、主轴箱、电机座都用螺钉固定在它上面，底下 4 个橡胶脚垫防滑、减振。'),
    2: ('橡胶脚垫', '丁腈橡胶', '吸收切削振动，也防止车床在桌面上滑动。'),
    3: ('床身', '6061 铝合金型材', '一根长方铝块，顶上装直线导轨，前面装丝杠。床身的直和刚性决定了车出来的工件直不直。'),
    4: ('直线导轨', 'GCr15 轴承钢，淬火磨削', '拖板和尾座都骑在这根导轨上左右滑动。一排沉孔是固定导轨的螺钉孔。'),
    5: ('丝杠', '45 钢，梯形螺纹 T8 × 2', '转动左端手轮，丝杠带着拖板下面的螺母左右走，就是"纵向进给"：车刀沿工件轴线走一刀。'),
    6: ('纵向进给手轮', '铝合金手轮 + 黄铜手柄', '装在丝杠左端。摇一圈拖板走 2 mm（一个螺距），手摇的快慢就是进给速度。'),
    7: ('主轴箱', '6061 铝合金', '里面一对轴承撑住主轴，让主轴只能转、不能晃。主轴箱和床身的对中决定了车出来的是圆柱还是锥。'),
    8: ('主轴', '40Cr 钢，调质', '左端装卡盘，右端装皮带轮。电机通过皮带带它转，工件跟着一起转。'),
    9: ('三爪卡盘', '铝合金盘体 + 黑色钢背板', '拧卡盘侧面的方孔，三个卡爪同步向中心收紧，工件自动对中夹牢。'),
    10: ('卡爪', '45 钢，淬火', '三个卡爪由卡盘里的平面螺纹盘同时推动，所以总是一起进、一起退，自动定心。台阶面可以反夹大直径工件。'),
    11: ('工件（黄铜棒）', 'H59 黄铜 Φ18', '被卡盘夹住跟着主轴转，车刀从侧面切下一层层铜屑。黄铜软、切屑短，最适合小车床练手。'),
    12: ('拖板（大拖板）', '6061 铝合金', '骑在导轨上，由丝杠带着左右走。前面的方孔和两个小块是燕尾滑块的压板，顶上是安装十字滑台的螺孔。'),
    13: ('十字滑台（中拖板）', '6061 铝合金', '在拖板上前后移动，控制车刀切进工件多深（横向进给 = 吃刀深度）。'),
    14: ('横向刻度手轮', '铝合金 + 刻度环', '摇它让十字滑台前后走。刻度环一格 0.02 mm：车刀往里进 0.1 mm，工件直径就小 0.2 mm。'),
    15: ('四方刀架', '45 钢，发黑', '四个面都能夹车刀，转 90° 就换一把刀，不用重新对刀。'),
    16: ('刀架压紧螺钉', '12.9 级内六角螺钉', '从上往下把车刀压在刀架里。车刀伸出越短越不容易振。'),
    17: ('车刀', '高速钢 HSS 8 × 8', '刀尖要对准主轴中心高：高了会顶、低了会啃。'),
    18: ('尾座', '6061 铝合金', '骑在导轨上，可以沿床身滑到任意位置再锁紧。里面的套筒能前后伸缩，用来顶住长工件或者钻孔。'),
    19: ('尾座手轮', '铝合金手轮 + 黄铜手柄', '摇它让尾座套筒伸出 / 缩回：钻孔时就是靠它把钻头推进工件。'),
    20: ('钻夹头（含过渡套、顶尖）', '钢制钻夹头 + 黄铜过渡套（B10 锥）', '插在尾座套筒前端。夹钻头就能在工件端面中心钻孔；换成顶尖可以顶住细长工件的另一头。'),
    21: ('尾座锁紧螺钉', '滚花铝头 + M6 钢螺杆', '拧紧后套筒就不会被切削力推回去。'),
    22: ('皮带罩', '6061 铝合金', '罩住皮带和皮带轮，防止手指、头发、衣服卷进去。拆皮带前先拆它。'),
    23: ('传动皮带', '聚氨酯圆带', '把电机的转动传给主轴。大轮带小轮：电机轮小、主轴轮大，转速降下来、扭矩变大。'),
    24: ('主轴皮带轮', '铝合金', 'Φ48，和电机皮带轮的直径比约 2.7 : 1，所以主轴比电机慢 2.7 倍、扭力大 2.7 倍。'),
    25: ('电机皮带轮', '铝合金', 'Φ18，装在电机轴上。'),
    26: ('电机座', '铝合金座 + 两道抱箍', '把电机抱在床身前面，电机轴和主轴平行，皮带才能对齐。'),
    27: ('直流电机', '775 直流电机 24 V · 铝端盖', '有刷直流电机：电压越高转得越快，调速器改电压就能无级调速。'),
    28: ('电源线（DC 插头）', 'PVC 护套线 + DC 5.5 × 2.1 插头', '接 24 V 电源适配器，给电机供电。沿着床身前面走线，不挡拖板。'),
    29: ('底板锁紧螺丝', '滚花铝头 + M5 螺杆', '把床身锁在底板上。松开后床身可以微调对中。'),
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
LS = (-27.0, 32.0)     # 丝杠轴线 (y, z)
MOT = (-50.0, 40.0)    # 电机轴线 (y, z)

# 爆炸路线（毫米，Blender 坐标；最后一个数 = 出场时刻 0~1，按真实拆机顺序：先拆刀具和小件，最后抬起主轴箱）
EX = dict(
    toolpost_screw=[(0, 0, 95, .04)],
    handwheel_z=[(-40, 0, 0, .06)],
    toolpost=[(0, 0, 55, .10)],
    tool=[(0, 0, 55, .10), (0, -30, 0, .16)],
    cross_wheel=[(0, -35, 0, .14)],
    cross_slide=[(0, 0, 30, .20)],
    work=[(0, -60, 0, .24)],
    carriage=[(0, 0, 10, .28)],
    chuck=[(-20, 0, 0, .36)],
    lock=[(0, 0, 60, .42)],
    drill=[(25, 0, 0, .44)],
    tail_wheel=[(-35, 0, 0, .48)],
    tailstock=[(-20, 0, 40, .52)],
    cover=[(70, 0, 0, .58)],
    belt=[(40, 0, 0, .64)],
    pulley_s=[(22, 0, 0, .70)],
    pulley_m=[(20, 0, 0, .70)],
    motor=[(0, -50, 0, .76)],
    leadscrew=[(0, -30, 0, .82)],
    knob=[(0, 0, 30, .86)],
    headstock=[(0, 0, 60, .92)],
)


# ---------------------------------------------------------------- 各零件
def build_base(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    extrude(bm, [rrect(180, 70, 6, cx=-10, cy=-10)], 5, BT, 0)
    for x in (-180, 160):            # 四角的安装孔
        for y in (-72, 52):
            disk(bm, 3.2, (x, y, BT), 'Z', 1)
    finish('P01_BasePlate', 1, bm, mats, bevel=.8)
    for i, (x, y) in enumerate(((-170, -62), (150, -62), (-170, 42), (150, 42))):
        bm = bmesh.new()
        rev(bm, [(0, 0), (7.5, 0), (9, 1.2), (9, 5), (0, 5)], 0, 'Z', (x, y, 0), seg=28)
        finish(f'P02_Foot_{i + 1}', 2, bm, [M['rubber']])


def build_bed(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (-178, -20, BT), (95, 20, BED_TOP), 0)
    # 丝杠两端的轴承座
    for x0, x1 in ((-178, -168), (78, 88)):
        boxf(bm, (x0, -34, 20), (x1, -20, 44), 0)
        disk(bm, 5, (x0 if x0 < 0 else x1, LS[0], LS[1]), '-X' if x0 < 0 else 'X', 1)
    # 床身前面固定螺钉
    for x in (-140, -60, 20):
        disk(bm, 3, (x, -20, 26), '-Y', 1)
    finish('P03_Bed', 3, bm, mats, bevel=1.0)

    bm = bmesh.new()
    boxf(bm, (-170, -8, BED_TOP), (90, 8, RAIL_TOP), 0)
    for y in (-8, 8):                 # 导轨两侧的滚道槽
        boxf(bm, (-170, y - .4, RAIL_TOP - 5), (90, y + .4, RAIL_TOP - 3), 1)
    for k in range(13):               # 一排沉孔
        x = -160 + k * 20
        disk(bm, 3.2, (x, 0, RAIL_TOP), 'Z', 1)
        disk(bm, 1.8, (x, 0, RAIL_TOP + .2), 'Z', 1, h=.25)
    finish('P04_Rail', 4, bm, [M['steel'], M['hole']], bevel=.5)


def build_leadscrew(M):
    bm = bmesh.new()
    prof = [(0, -184), (3.4, -184)]
    x = -182.0
    while x < 84:                    # 梯形螺纹：一圈圈牙
        prof += [(3.4, x), (4.2, x + .6), (4.2, x + 1.4), (3.4, x + 2)]
        x += 2
    prof += [(3.4, 86), (0, 86)]
    rev(bm, prof, 0, 'Z', (0, 0, 0), seg=14)
    xform(bm, bm.faces, Matrix.Translation(Vector((0, LS[0], LS[1]))) @ ROT['X'])
    finish('P05_LeadScrew', 5, bm, [M['steel']], ex=EX['leadscrew'])

    bm = bmesh.new()
    handwheel(bm, 19, (-182, LS[0], LS[1]), '-X', 0, 1)
    finish('P06_HandwheelZ', 6, bm, [M['alu'], M['copper']], ex=EX['handwheel_z'], smooth=40)


def build_headstock(M):
    mats = [M['alu'], M['hole'], M['steel']]
    bm = bmesh.new()
    boxf(bm, (95, -25, BT), (150, 35, 130), 0)
    rev(bm, [(16, 0), (23, 0), (23, 2.5), (16, 2.5)], 0, '-X', (95, 0, CZ), seg=48, closed=True)   # 轴承压盖
    for k in range(4):
        a = pi / 4 + k * pi / 2
        disk(bm, 2, (92.5, 19.5 * cos(a), CZ + 19.5 * sin(a)), '-X', 1)
    for y, z in ((-12, 30), (22, 30), (-12, 118), (22, 118)):     # 前面、顶面的螺钉
        disk(bm, 2.8, (95, y, z), '-X', 1)
    for x in (105, 140):
        disk(bm, 2.8, (x, 5, 130), 'Z', 1)
    finish('P07_Headstock', 7, bm, mats, ex=EX['headstock'], bevel=1.5)

    bm = bmesh.new()
    rev(bm, [(0, 0), (7, 0), (8, 1), (8, 88), (0, 88)], 0, 'X', (70, 0, CZ), seg=32)
    finish('P08_Spindle', 8, bm, [M['steel']], ex=EX['headstock'])


def build_chuck(M):
    bm = bmesh.new()
    rev(bm, [(0, 85), (33, 85), (33, 95), (0, 95)], 1, 'Z', seg=64)                 # 黑色背板
    rev(bm, [(0, 64), (28, 64), (31.5, 65), (32, 67), (32, 85), (0, 85)], 0, 'Z', seg=64)   # 盘体
    xform(bm, bm.faces, Matrix.Translation(Vector((0, 0, CZ))) @ ROT['X'] @ Matrix.Translation(Vector((0, 0, 0))))
    # ROT['X'] 把局部 Z 转成 X：上面两段沿轴坐标就是 X
    disk(bm, 9.5, (63.7, 0, CZ), '-X', 2, h=.35)                                          # 中心孔
    for k in range(3):                                                                    # 侧面 3 个扳手方孔
        a = pi / 3 + 2 * pi * k / 3
        d = Vector((0, cos(a), sin(a)))
        c = Vector((76, 0, CZ)) + d * 31.8
        fs = rod(bm, 2.6, 0, .5, 2, 'Z', (0, 0, 0), seg=4)
        mt = Matrix.Translation(c) @ d.to_track_quat('Z', 'X').to_matrix().to_4x4()
        xform(bm, fs, mt)
    finish('P09_Chuck', 9, bm, [M['alu'], M['black'], M['hole']], ex=EX['chuck'], bevel=.6)

    for k in range(3):
        a = pi / 2 + 2 * pi * k / 3
        d = Vector((0, cos(a), sin(a)))
        t = Vector((0, -sin(a), cos(a)))
        bm = bmesh.new()
        # 局部坐标：x = 轴向（主轴 X），y = 径向，z = 切向
        boxf(bm, (55, 9, -4), (64, 18, 4), 0)
        boxf(bm, (58, 18, -4), (64, 25, 4), 0)
        boxf(bm, (61, 25, -4), (64, 30, 4), 0)
        mt = Matrix(((1, 0, 0, 0), (0, d.y, t.y, 0), (0, d.z, t.z, CZ), (0, 0, 0, 1)))
        xform(bm, bm.faces, mt)
        ex = [(0, 18 * d.y, 18 * d.z, .30)] + EX['chuck']
        finish(f'P10_Jaw_{k + 1}', 10, bm, [M['steel']], ex=ex, bevel=.4)

    bm = bmesh.new()
    rev(bm, [(0, 0), (8.5, 0), (9, .5), (9, 54), (0, 54)], 0, 'X', (10, 0, CZ), seg=40)
    finish('P11_Workpiece', 11, bm, [M['brass']], ex=EX['work'])


def build_carriage(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (-20, -40, RAIL_TOP), (40, 40, 80), 0)
    boxf(bm, (0, -36, 40), (20, -20, RAIL_TOP), 0)          # 前面下垂的丝杠螺母座
    boxf(bm, (3, -40.3, 62), (17, -40, 76), 1)               # 正面方孔
    for x in (-12, 28):                                     # 两个燕尾压板小块
        boxf(bm, (x - 4, -44, 64), (x + 4, -40, 74), 0)
        disk(bm, 1.6, (x, -44, 69), '-Y', 1)
    for x in (-15, 35):                                     # 顶面螺孔
        for y in (-34, -10, 14, 34):
            disk(bm, 2.4, (x, y, 80), 'Z', 1)
    finish('P12_Carriage', 12, bm, mats, ex=EX['carriage'], bevel=1.0)

    bm = bmesh.new()
    boxf(bm, (-12, -38, 80), (32, 30, 90), 0)
    for x in (-8, 28):
        for y in (-5, 25):
            disk(bm, 2.2, (x, y, 90), 'Z', 1)
    finish('P13_CrossSlide', 13, bm, mats, ex=EX['cross_slide'], bevel=.8)

    bm = bmesh.new()
    rod(bm, 2.5, 0, 6, 1, '-Y', (10, -38, 85), seg=16)           # 轴
    rev(bm, [(0, 0), (9, 0), (9, 5), (0, 5)], 2, '-Y', (10, -42, 85), seg=48)    # 刻度环
    fs = []
    for k in range(25):                                          # 刻度线
        a = 2 * pi * k / 25
        L = 2.2 if k % 5 == 0 else 1.2
        bmt = bmesh.ops.create_cube(bm, size=1.0)
        vs = bmt['verts']
        bmesh.ops.scale(bm, vec=Vector((.35, 2.5, L)), verts=vs)
        bmesh.ops.translate(bm, vec=Vector((0, 0, 9 - L / 2 + .2)), verts=vs)
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(a, 3, 'Y'), verts=vs)
        bmesh.ops.translate(bm, vec=Vector((10, -43.5, 85)), verts=vs)
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = 1
    handwheel(bm, 11, (10, -47, 85), '-Y', 0, 3, handle_len=12, handle_r=2.3)
    finish('P14_CrossWheel', 14, bm, [M['alu'], M['black'], M['alu_dark'], M['copper']], ex=EX['cross_wheel'], smooth=40)

    bm = bmesh.new()
    boxf(bm, (5, -45, 90), (35, -15, 116), 0)
    boxf(bm, (5.5, -45.3, 92), (34.5, -45, 101), 1)            # 正面夹刀槽
    finish('P15_ToolPost', 15, bm, [M['black'], M['hole']], ex=EX['toolpost'], bevel=.8)

    for i, (x, y) in enumerate(((12, -38), (28, -38), (12, -22), (28, -22))):
        bm = bmesh.new()
        rod(bm, 2, 110, 116, 0, 'Z', (x, y, 0), seg=16)
        rev(bm, [(0, 116), (3.6, 116), (3.6, 120.5), (3.2, 121), (0, 121)], 0, 'Z', (x, y, 0), seg=24)
        disk(bm, 1.6, (x, y, 121), 'Z', 1, h=.2, seg=6)
        finish(f'P16_ToolScrew_{i + 1}', 16, bm, [M['black'], M['hole']], ex=EX['toolpost_screw'])

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


def build_tailstock(M):
    mats = [M['alu'], M['hole'], M['steel']]
    bm = bmesh.new()
    boxf(bm, (-150, -30, RAIL_TOP), (-105, 30, 80), 0)            # 方底座
    for x in (-140, -115):                                       # 底座正面两个孔
        disk(bm, 3.5, (x, -30, 69), '-Y', 1)
    boxf(bm, (-145, -14, 80), (-110, 14, 86), 0)                  # 立柱
    rev(bm, [(0, -160), (17, -160), (18, -159), (18, -101), (17, -100), (0, -100)], 0, 'X', (0, 0, CZ), seg=56)  # 套筒座
    rev(bm, [(0, -169), (9, -169), (10, -168), (10, -160), (0, -160)], 0, 'X', (0, 0, CZ), seg=32)
    rev(bm, [(0, -100), (11, -100), (11, -87), (10.5, -86), (0, -86)], 2, 'X', (0, 0, CZ), seg=40)              # 伸出的套筒
    for k in range(2):
        disk(bm, 2.2, (-150 + 20 * k + 15, 0, CZ + 18), 'Z', 1)
    finish('P18_Tailstock', 18, bm, mats, ex=EX['tailstock'], bevel=1.0)

    bm = bmesh.new()
    handwheel(bm, 19, (-169, 0, CZ), '-X', 0, 1)
    finish('P19_TailWheel', 19, bm, [M['alu'], M['copper']], ex=EX['tail_wheel'], smooth=40)

    bm = bmesh.new()
    rev(bm, [(0, 0), (8.5, 0), (9, 1), (9, 8), (0, 8)], 1, '-X', (-78, 0, CZ), seg=40)          # 黄铜过渡套 X -86..-78
    rev(bm, [(0, 0), (13, 0), (14, 1), (14, 14), (12, 16), (10, 24), (5, 28), (0, 28)], 0, 'X', (-78, 0, CZ), seg=48)
    for k in range(24):                                          # 钻夹头外套的竖纹
        a = 2 * pi * k / 24
        c = Vector((-72, 14 * cos(a), CZ + 14 * sin(a)))
        boxf(bm, (c.x - 4, c.y - .5, c.z - .5), (c.x + 4, c.y + .5, c.z + .5), 0)
    rev(bm, [(0, 28), (4, 28), (0, 40)], 2, 'X', (-78, 0, CZ), seg=24)                       # 顶尖
    finish('P20_DrillChuck', 20, bm, [M['steel'], M['brass'], M['steel']], ex=EX['drill'])

    bm = bmesh.new()
    rod(bm, 3, 116, 124, 1, 'Z', (-128, 0, 0), seg=16)
    knurl(bm, 7, 124, 132, 0, 'Z', (-128, 0, 0))
    finish('P21_TailLock', 21, bm, [M['alu'], M['steel']], ex=EX['lock'])


def build_drive(M):
    """皮带罩、皮带、两个皮带轮"""
    outer = hull(circle(0, CZ, 34, 48) + circle(MOT[0], MOT[1], 24, 32) + [(-80, BT), (36, BT)])
    inner = hull(circle(0, CZ, 31, 48) + circle(MOT[0], MOT[1], 21, 32) + [(-77, BT + 3), (33, BT + 3)])
    bm = bmesh.new()
    extrude(bm, [outer, inner[::-1]], 150, 161, 0, axis='X')
    extrude(bm, [outer], 161, 164, 0, axis='X')
    for y, z in ((0, CZ), (MOT[0], MOT[1])):
        disk(bm, 2.6, (164, y, z), 'X', 1)
    finish('P22_BeltCover', 22, bm, [M['alu'], M['hole']], ex=EX['cover'], bevel=1.0)

    pts = hull(circle(0, CZ, 22.5, 64) + circle(MOT[0], MOT[1], 7.5, 32))
    path = [Vector((155.5, p[0], p[1])) for p in pts]
    bm = bmesh.new()
    sweep(bm, path, 2.2, 0, sides=10, closed=True, plane_n=Vector((1, 0, 0)))
    finish('P23_Belt', 23, bm, [M['belt']], ex=EX['belt'])

    for name, no, r, (y, z), ex in (('P24_SpindlePulley', 24, 24, (0, CZ), EX['pulley_s']),
                                    ('P25_MotorPulley', 25, 9, MOT, EX['pulley_m'])):
        bm = bmesh.new()
        rev(bm, [(0, 0), (r, 0), (r, 1.5), (r - 2.5, 3.5), (r, 5.5), (r, 7), (0, 7)], 0, 'X', (152, y, z), seg=56)
        finish(name, no, bm, [M['alu_dark']], ex=ex)


def build_motor(M):
    mats = [M['alu'], M['hole']]
    bm = bmesh.new()
    boxf(bm, (60, -72, BT), (130, -28, BT + 4), 0)
    for x in (70, 112):
        rev(bm, [(24, 0), (26.5, 0), (26.5, 8), (24, 8)], 0, 'X', (x, MOT[0], MOT[1]), seg=48, closed=True)
        rod(bm, 2, 0, 4, 1, 'Z', (x + 4, MOT[0] - 27, BT + 4), seg=12)
    finish('P26_MotorMount', 26, bm, mats, bevel=.5)

    bm = bmesh.new()
    rev(bm, [(0, 0), (22, 0), (24, 2), (24, 104), (22, 106), (0, 106)], 0, 'X', (40, MOT[0], MOT[1]), seg=56)
    for x in (50, 136):                                                   # 机壳两道压痕
        rev(bm, [(24, 0), (24.4, 0), (24.4, 1.2), (24, 1.2)], 3, 'X', (x, MOT[0], MOT[1]), seg=56, closed=True)
    rev(bm, [(0, 0), (23, 0), (25, 2), (25, 10), (0, 10)], 1, 'X', (30, MOT[0], MOT[1]), seg=56)   # 铝端盖
    for k in range(4):
        a = pi / 4 + k * pi / 2
        disk(bm, 1.8, (29.7, MOT[0] + 17 * cos(a), MOT[1] + 17 * sin(a)), '-X', 2)
    for k in range(6):                                                    # 端盖散热孔
        a = k * pi / 3
        disk(bm, 2.6, (29.7, MOT[0] + 9 * cos(a), MOT[1] + 9 * sin(a)), '-X', 2)
    rod(bm, 2.5, 146, 159, 4, 'X', (0, MOT[0], MOT[1]), seg=16)            # 电机轴
    finish('P27_Motor', 27, bm, [M['motor'], M['alu'], M['hole'], M['black'], M['steel']], ex=EX['motor'])

    ctrl = [Vector(p) for p in ((32, MOT[0] - 12, MOT[1] - 8), (28, -68, 26), (18, -73, 17), (-20, -74, 16),
                                (-100, -74, 16), (-170, -73, 16), (-196, -70, 16))]
    bm = bmesh.new()
    sweep(bm, catmull(ctrl, per=10), 2.2, 0, sides=10)
    rev(bm, [(0, 0), (4.5, 0), (4.5, 12), (3, 14), (0, 14)], 0, '-X', (-196, -70, 16), seg=24)   # DC 插头
    rev(bm, [(0, 0), (2.8, 0), (2.8, 8), (0, 8)], 1, '-X', (-210, -70, 16), seg=20)
    finish('P28_PowerCord', 28, bm, [M['cable'], M['steel']], ex=EX['motor'])


def build_knobs(M):
    for i, x in enumerate((-160, -100, -40)):
        bm = bmesh.new()
        rod(bm, 2.5, BT, BT + 3, 1, 'Z', (x, -48, 0), seg=16)
        knurl(bm, 7, BT + 3, BT + 11, 0, 'Z', (x, -48, 0))
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
