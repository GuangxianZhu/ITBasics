# -*- coding: utf-8 -*-
"""
数字万用表（外观参考 SATA 世达 DO5054 智能款）—— Blender 脚本建模 + 原理爆炸图

没有图纸，外形照产品图按比例估（护套外形约 150 × 76 × 38 mm），内部（主板、元件、LCD 叠层、电池）
按这类口袋式自动量程万用表的常见结构补的，每个元件都配了"它在电路里干什么"的说明（见 INFO）。

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_multimeter.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    multimeter.blend   Blender 工程，按空格播放：第 1~120 帧按拆机顺序拆开，第 150~270 帧反顺序装回
    multimeter.glb     glTF 模型（单位米，每个零件一个节点，extras 里有零件号、中文名、材料、作用、爆炸路线），
                       虚幻工程 MyVRToyBox 的 Tools/import_model.py 直接导入
    parts.json         零件表
    render_*.png       加 --render 时用 Cycles 渲染装配 / 爆炸两张预览图

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    万用表面朝上平放在桌上：+Z 向上（屏幕朝上），+Y 指向表的顶端（屏幕、NCV 那头），+X 指向右手边
    Z = 0 是护套背面；面壳表面 Z = 35，护套唇边 Z = 38；表笔插头竖着插在面板底部的插孔里
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


def make_materials():
    # 金属度都压在 0.55 以下：虚幻工作室里没有反射探针，金属反射的是黑的环境，金属度 0.8 在虚幻里就发黑了（车床实测）
    return dict(
        case=principled('M_Case_Black', '#1e1f22', 0, .5),
        face=principled('M_Face_Gloss', '#121315', 0, .28),
        rubber=principled('M_Holster_Rubber', '#141517', 0, .8),
        white=principled('M_Print_White', '#eeeeee', 0, .5),
        orange=principled('M_Print_Orange', '#e8552d', 0, .5),
        collar_red=principled('M_Jack_Red', '#c8231e', 0, .4),
        collar_blk=principled('M_Jack_Black', '#2e2f33', 0, .4),
        hole=principled('M_Hole', '#0a0a0b', 0, .8),
        led_red=principled('M_LED_Red', '#e0412f', 0, .25),
        screw=principled('M_Screw_Black', '#3a3c40', .45, .4),
        key_sheet=principled('M_Keypad_Sheet', '#3a3c40', 0, .8),
        key_yellow=principled('M_Key_Yellow', '#f2c316', 0, .55),
        key_gray=principled('M_Key_Gray', '#8a8e94', 0, .6),
        print_black=principled('M_Print_Black', '#151515', 0, .5),
        carbon=principled('M_Carbon_Pill', '#0e0e0e', 0, .6),
        lcd_bg=principled('M_LCD_Background', '#c7cec3', 0, .32),
        lcd_glass=principled('M_LCD_Glass_Edge', '#9fb0a8', 0, .2),
        lcd_seg=principled('M_LCD_Segment', '#191b19', 0, .4),
        pin=principled('M_Pin_Silver', '#c4c7cb', .5, .3),
        zebra=principled('M_Zebra', '#dcc8c3', 0, .7),
        zebra_dark=principled('M_Zebra_Conductive', '#2c2b2b', 0, .7),
        guide=principled('M_LightGuide', '#e8eef2', 0, .25),
        guide_dot=principled('M_LightGuide_Dots', '#c3ccd4', 0, .5),
        pcb=principled('M_PCB_Green', '#1b6a3c', 0, .45),
        trace=principled('M_PCB_Trace', '#46a866', 0, .45),
        gold=principled('M_Gold_Pad', '#d3ad4c', .5, .3),
        silk=principled('M_Silkscreen', '#f2f2ee', 0, .6),
        solder=principled('M_Solder', '#c9ccd0', .5, .3),
        chip=principled('M_Chip_Epoxy', '#18191c', 0, .5),
        chip_mark=principled('M_Chip_Marking', '#8d9196', 0, .6),
        brass=principled('M_Brass', '#c9a24a', .55, .32),
        nickel=principled('M_Nickel', '#bfc3c8', .5, .3),
        copper=principled('M_Copper', '#c4743c', .55, .32),
        ceramic=principled('M_Ceramic', '#ece8df', 0, .55),
        ptc=principled('M_PTC_Coating', '#c4822c', 0, .45),
        mov=principled('M_MOV_Blue', '#2d5ba8', 0, .4),
        res_body=principled('M_Resistor_Blue', '#5c9ed8', 0, .45),
        band_brown=principled('M_Band_Brown', '#6b3a1c', 0, .5),
        band_black=principled('M_Band_Black', '#141414', 0, .5),
        band_red=principled('M_Band_Red', '#c4231c', 0, .5),
        band_orange=principled('M_Band_Orange', '#e07a1a', 0, .5),
        band_yellow=principled('M_Band_Yellow', '#e8c81e', 0, .5),
        band_green=principled('M_Band_Green', '#2f8f3a', 0, .5),
        buzzer=principled('M_Buzzer', '#1a1b1d', 0, .5),
        led_white=principled('M_LED_Body', '#f3f1e8', 0, .4),
        led_yellow=principled('M_LED_Phosphor', '#f0d45a', 0, .35),
        bat_wrap=principled('M_Battery_Wrap', '#1f4fa6', 0, .35),
        bat_band=principled('M_Battery_Band', '#d6a21e', 0, .4),
        wire_red=principled('M_Wire_Red', '#c21d1d', 0, .5),
        wire_blk=principled('M_Wire_Black', '#141414', 0, .5),
        probe_red=principled('M_Probe_Red', '#c8161d', 0, .4),
        probe_blk=principled('M_Probe_Black', '#1a1b1d', 0, .4),
        steel=principled('M_Steel', '#b5b9be', .5, .3),
    )


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


def power_icon(bm, cx, cy, z, r, mi):
    """⏻ 电源符号：缺口朝上的圆环 + 竖杠"""
    flat(bm, [arc_ring(cx, cy, r * .72, r, pi / 2 + .62, pi / 2 + 2 * pi - .62)], z, mi)
    flat(bm, [rrect(r * .14, r * .62, r * .1, ns=3, cx=cx, cy=cy + r * .5)], z, mi)


def warn_triangle(bm, cx, cy, z, s, mi):
    o = triangle(cx, cy, s)
    i = triangle(cx, cy, s * .62)
    flat(bm, ring2d(o, i), z, mi)
    text(bm, '!', s * .5, cx, cy - s * .02, z, mi)


# ---------------------------------------------------------------- 七段数码
SEG_ON = {'2': 'abged', '6': 'afgedc', '7': 'abc', '8': 'abcdefg'}


def seg_poly(cx, cy, L, t, vertical):
    h = t / 2
    pts = [(-L / 2, 0), (-L / 2 + h, -h), (L / 2 - h, -h), (L / 2, 0), (L / 2 - h, h), (-L / 2 + h, h)]
    if vertical:
        pts = [(-y, x) for x, y in pts]
    return [(cx + x, cy + y) for x, y in pts]


def seven_seg(bm, ch, x0, y0, W, H, t, z, mi, slant=.08, gap=.35):
    w, h = W / 2, H / 2
    hl = W - t - 2 * gap
    vl = h - 2 * gap
    S = dict(
        a=(x0, y0 + h - t / 2, hl, False), g=(x0, y0, hl, False), d=(x0, y0 - h + t / 2, hl, False),
        f=(x0 - w + t / 2, y0 + (h - t / 2) / 2, vl - t / 2, True), b=(x0 + w - t / 2, y0 + (h - t / 2) / 2, vl - t / 2, True),
        e=(x0 - w + t / 2, y0 - (h - t / 2) / 2, vl - t / 2, True), c=(x0 + w - t / 2, y0 - (h - t / 2) / 2, vl - t / 2, True),
    )
    for k in SEG_ON[ch]:
        cx, cy, L, v = S[k]
        pts = [(x + slant * (y - y0), y) for x, y in seg_poly(cx, cy, L, t, v)]
        flat(bm, [pts], z, mi)


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 Multimeter
OBJS = []           # dict(ob, ex, no)

# 零件号 → (中文名, 材料, 作用)。信息牌上显示的就是这三行
INFO = {
    1: ('底壳', '黑色 ABS 注塑',
        '万用表的"下半身"。四角的螺丝柱让面壳的螺丝拧进来，中间的隔墙围出电池槽，几根小立柱托住主板。拆表时它不动，其他零件都从它上面拿走。'),
    2: ('电池弹片（含引线）', '镀镍弹簧钢片 + 红黑引线',
        '锥形弹簧顶住电池负极、平片顶住正极，右边那片把两节电池串起来成 3 V，左边两片经红黑引线送到主板。'
        '弹簧吃掉电池长度的公差，保证一直压紧。'),
    3: ('橡胶护套', 'TPE 软胶 · 侧面防滑凸棱',
        '包住整台表：摔到地上先撞的是软胶，不是外壳和屏幕。正面唇边比屏幕高 3 mm，表面朝下放也刮不到屏幕；它还盖住了四颗面壳螺丝。'),
    4: ('面壳（含面板印刷）', 'PC+ABS 注塑 · 丝印',
        '屏幕窗口、4 个按键孔、3 个表笔插孔都开在这里。橙色图标框是能测的项目：交直流电压 V、通断蜂鸣、电阻 Ω、电流 A、频率 Hz、'
        'LIVE 火线判断、NCV 非接触测电。"600V CAT III" 是安全等级：能在配电箱这类场合测 600 V 以内的电。'),
    5: ('面壳螺丝', '十字盘头自攻螺丝 M2.5 × 15 · 黑色镀锌',
        '从正面穿过面壳的螺丝柱，拧进底壳的螺丝柱。四颗都藏在护套唇边下面，不拆护套看不见。'),
    6: ('硅胶按键（导电胶）', '双色硅胶 · 底面导电碳粒',
        '按下去时，按键底面的黑色碳粒压到主板的金色梳状焊盘上，把两组梳齿短接，主控就知道哪个键被按了；松手后硅胶自己弹回。'
        '黄键开关机；SEL 切换功能（长按开背光）；HOLD 锁住读数；NCV/LIVE 非接触测电 / 火线判断。'),
    7: ('LCD 液晶屏', 'TN 段码液晶 · 两片玻璃 + 上下偏光片',
        '每一笔（段）都是一块透明电极。主控在某段上加交流方波，那里的液晶分子转向、挡住反射光，这一笔就变黑。'
        '下片玻璃比上片宽一圈，露出来的边上是一排引脚，靠斑马条连到主板。'),
    8: ('斑马条（导电胶条）', '硅胶 · 导电层 / 绝缘层交替（约 0.1 mm 一层）',
        '黑的是导电层、白的是绝缘层。夹在液晶屏引脚和主板焊盘中间：上下导通、左右绝缘，不用焊接就把几十个引脚一起接通。'),
    9: ('背光导光板', 'PMMA 亚克力 · 底面印网点',
        '两颗 LED 从侧面把光打进板里，光在板里全反射来回走，碰到网点就散射出来，整块屏幕均匀发亮。长按 SEL 开背光，暗处也能读数。'),
    10: ('LCD 支架', '黑色 ABS',
         '把液晶屏、导光板、斑马条摞在一起定位。面壳从上往下一压，屏幕压紧斑马条、斑马条压紧主板焊盘，全部接通。'),
    11: ('主板（PCB）', 'FR-4 双面板 · 绿油 · 沉金焊盘',
         '浅绿色的线是铜箔走线，按信号走向排的：V 插孔 → PTC → 分压电阻 → 模拟开关 → 主控；A 插孔 → 保险丝 → 锰铜分流器 → COM。'
         '金色圆盘是按键的梳状焊盘，上下两排金色细条是斑马条的焊盘，两个黄铜夹子是保险丝座。'),
    12: ('主控芯片 SoC', 'QFP-48 · 单片机 + 高精度 ADC + LCD 驱动',
         '整块表的大脑。不管测什么，最后都变成一个很小的电压交给里面的 ADC（模数转换器）去数：电压先分压；电流变成分流器上的压降；'
         '电阻是送一个已知电流再量压降。自动识别、自动换量程、驱动液晶、15 分钟自动关机也都是它管。'),
    13: ('自动量程模拟开关', 'SOIC-16 · CMOS 模拟开关',
         '代替老式万用表的旋钮。主控先在最大量程试测，读数太小就让它换到下一个分压抽头，直到读数落在最准的那一段，这就是"自动量程"。'
         '自动识别也是这样：先看 V 插孔上有没有交 / 直流电压，有就测电压，没有就送小电流测电阻 / 通断。'),
    14: ('EEPROM（校准数据）', 'SOP-8 · 24C02 串行存储器',
         '出厂校准时用标准源把各档测一遍，每档的误差系数写在这里。开机时主控读出来，算读数时修正掉，所以每块表都准。'),
    15: ('晶振', '32.768 kHz 石英晶体',
         '主控的"秒表"。测频率（Hz）就是数一秒钟里信号翻转了多少次；15 分钟自动关机也靠它计时。'),
    16: ('基准电压源', 'SOT-23 · 1.2 V 带隙基准',
         'ADC 的尺子：ADC 测出来的是"输入是基准的几倍"。基准差 0.1 %，读数就差 0.1 %，所以要求温漂很小。'),
    17: ('电源开关 MOS 管 + 稳压芯片', '2 × SOT-23 · P 沟道 MOS + 3.0 V LDO',
         '按黄键时 MOS 管导通给全板上电，之后主控自己"拉住"它保持开机；15 分钟没操作，主控松手，整块表断电（自动关机）。'
         '稳压芯片把电池电压稳成 3.0 V，电池电压往下掉读数也不受影响。'),
    18: ('分压电阻（精密）', '4 × 0.1 % 金属膜电阻（蓝色）',
         '一串电阻总共 10 MΩ（就是表的输入电阻），按 10 : 1 一级级分出抽头：600 V 进来，最后一级只剩零点几伏，ADC 才吃得下。'
         '输入电阻很大，接上去几乎不分走电流，不影响被测电路。'),
    19: ('PTC 热敏电阻（错档防烧）', '陶瓷 PTC 正温度系数热敏电阻',
         '"错档防烧"的关键。平时只有几百欧；要是在电阻 / 通断状态误碰 220 V，大电流让它发热，几毫秒内电阻涨到几十千欧，'
         '把电流卡住，后面的芯片就不会烧。冷下来自动恢复，不用换。'),
    20: ('压敏电阻', '金属氧化物压敏电阻（MOV）',
         '并在 V 插孔和 COM 之间。正常电压下几乎不导电；遇到雷击、开关浪涌这种几千伏的尖峰，瞬间导通把尖峰泄放掉。'),
    21: ('保险丝 4A', '陶瓷管快熔保险丝 5 × 20 mm · F4A 250V',
         'A 插孔进来的电流先过它。超过 4 A（或者表笔插在 A 孔去测电压，等于短路），几毫秒内熔断，保护分流器和人。'
         '陶瓷管比玻璃管分断能力大，熔断时不会炸。'),
    22: ('锰铜分流器', '锰铜合金丝 · 约 0.05 Ω',
         '测电流的"秤"：电流流过它产生压降 U = I × R，4 A 时约 0.2 V，主控量这个电压就知道电流。锰铜的电阻几乎不随温度变，'
         '电流大发热了读数也不漂。'),
    23: ('蜂鸣器', '电磁式蜂鸣器 Φ12',
         '通断档：两表笔之间小于约 50 Ω 就"嘀"，不看屏幕也知道线通不通。NCV 测到电、按键、自动关机前也会叫。'),
    24: ('V 插孔（红表笔）', '黄铜镀镍插座 · Φ4 mm',
         '红表笔插这里。测电压、电阻、通断、频率、火线判断都走它，信号进来先过 PTC 和分压电阻。'),
    25: ('COM 公共插孔（黑表笔）', '黄铜镀镍插座 · Φ4 mm',
         '黑表笔永远插这里。所有测量都以它为"零点"（参考地），电流也从这里流回去。'),
    26: ('A 电流插孔', '黄铜镀镍插座 · Φ4 mm',
         '测电流时红表笔改插这里（最大 4 A）。后面是保险丝和锰铜分流器，内阻只有零点几欧，所以千万别插在这里去测电压。'),
    27: ('背光 LED', '侧发光白光 SMD LED',
         '贴在导光板两侧下面，从侧边把光打进导光板。'),
    28: ('NCV 感应线圈', 'FR-4 小板 + 铜箔螺旋线',
         '装在表的顶端。靠近带电的电线时，电线周围的交流电场通过几皮法的电容耦合到这片铜箔上，感应出极小的电流，'
         '放大后点亮顶上的灯、让蜂鸣器叫，不用接触就知道有没有电。'),
    29: ('NCV 指示灯', 'Φ3 红绿双色 LED（面壳上有导光柱）',
         '测到电亮红灯，没电亮绿灯。LIVE 火线判断：只用红表笔碰电线，人手通过表壳和人体的电容当"地"，'
         '火线对地 220 V 会被测到，零线对地接近 0 V 就不亮。'),
    30: ('电池', '1.5 V AAA 碱性电池',
         '两节串联 3 V，给整块表供电。'),
    31: ('红表笔', 'PVC 笔杆 + 硅胶线 + 护套香蕉插头 · CAT III 600 V',
         '插 V 插孔（测电流时改插 A 孔）。护指挡圈挡住手指别滑到金属针上；插头带护套，插拔时手碰不到金属。'),
    32: ('黑表笔', 'PVC 笔杆 + 硅胶线 + 护套香蕉插头 · CAT III 600 V',
         '插 COM 孔，当测量的参考点。'),
}


def finish(name, no, bm, mats, ex=(), bevel=0.0, seg=2, angle=50, smooth=34, post=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('Multimeter').objects.link(ob)
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
        # 倒角之后再加文字、印刷（文字不倒角，免得面数爆炸）
        b2 = bmesh.new()
        b2.from_mesh(ob.data)
        post(b2)
        b2.to_mesh(ob.data)
        b2.free()
        shade(ob.data, smooth)
    ob.data.transform(Matrix.Scale(MM, 4))
    ob.parent = ROOT
    ob['name_cn'] = INFO[no][0]
    OBJS.append(dict(ob=ob, ex=list(ex), no=no))
    return ob


# ---------------------------------------------------------------- 主要尺寸 (mm)
FACE = 35.0            # 面壳表面
PCB_Z = (15.4, 17.0)   # 主板
BODY = (34.0, 71.0, 7.0)          # 表体（底壳 + 面壳）半宽、半长、圆角
KEYS_X = (-21.0, -7.0, 7.0, 21.0)
KEY_Y = -11.0
JACK_Y = -55.0
JACKS = ((20.0, 'V', 24), (0.0, 'COM', 25), (-20.0, 'A', 26))
SCREWS = ((-28.5, -65.5), (28.5, -65.5), (-28.5, 65.5), (28.5, 65.5))
BAT_Y = (-24.5, -35.5)
BAT_Z = 9.9
NCV_LED = (-27.5, 61.0)
SOC = (0.0, 30.0)

# 爆炸路线（毫米，Blender 坐标；最后一个数 = 出场时刻 0~1）。
# 按真实拆机顺序：拔表笔 → 剥护套 → 拧螺丝 → 掀面壳 → 拿按键 / 拆屏幕叠层 → 拔保险丝 → 抬主板 → 元件"浮"起来讲原理 → 取电池。
# 摆法按"人站在表前方往下看"来排，主板和元件在中间不被挡住：
#   中间：底壳不动，主板抬起，元件浮在各自焊盘正上方，保险丝浮在保险丝座上方
#   左边一列：屏幕叠层（支架、斑马条、导光板、液晶屏）从下往上摞，电池放在它前面
#   右边一列：面壳（正面朝上）+ 上面四颗螺丝；按键放在面壳前下方
#   护套：往上往后，是个空心框，挡不住什么；表笔：拔出来往前挪，躺在两边
SIDE = 110.0
BOARD_UP = 30.0        # 主板抬起
PART_UP = 14.0         # 主板上的元件再往上浮（停在自己焊盘的正上方，信息牌对得上位置）
EX = dict(
    holster=[(0, 80, 110, .10)],
    screw=[(SIDE, 25, 112, .16)],
    front=[(SIDE, 25, 80, .22)],
    keypad=[(SIDE, -40, 30, .30)],
    lcd=[(-SIDE, 16, 72, .34)],
    zebra=[(-SIDE, 8, 56, .40)],
    guide=[(-SIDE, 12, 62, .44)],
    holder=[(-SIDE, 0, 36, .48)],
    fuse=[(0, 0, BOARD_UP + PART_UP - 1, .52)],
    pcb=[(0, 0, BOARD_UP, .58)],
    battery=[(-SIDE, -60, 20, .80)],
)


_COMP = []


def comp_ex():
    """主板上元件的路线：跟主板一起抬起，再一个接一个往上浮一点。
    每个元件出场时刻错开一点点：既是依次"冒"出来的动画，也让每个元件的路线各不相同——
    虚幻那边按路线分抓取单元，路线一样的会被合成一个单元（就没法单独抓、单独看信息牌了）"""
    _COMP.append(1)
    return [(0, 0, BOARD_UP, .58), (0, 0, PART_UP, .64 + .008 * len(_COMP))]


# ---------------------------------------------------------------- 外壳
def build_back_case(M):
    mats = [M['case'], M['hole'], M['key_gray']]
    hw, hh, r = BODY
    bm = bmesh.new()
    extrude(bm, [rrect(hw, hh, r)], 3, 4.6, 0)
    extrude(bm, ring2d(rrect(hw, hh, r), rrect(hw - 2, hh - 2, r - 2)), 4.6, 17, 0)
    for x, y in SCREWS:                       # 螺丝柱
        rev(bm, [(1.0, 4.6), (3.0, 4.6), (3.0, PCB_Z[0]), (1.0, PCB_Z[0])], 0, 'Z', (x, y, 0), seg=20, closed=True)
        disk(bm, 1.0, (x, y, 4.62), 'Z', 1, h=.05, seg=12)
    # 电池槽：前后两道长墙、两头端墙、中间矮隔墙
    boxf(bm, (-26, -42.2, 4.6), (26, -41, 13), 0)
    boxf(bm, (-26, -19, 4.6), (26, -17.8, 13), 0)
    boxf(bm, (-26, -41, 4.6), (-24.8, -19, 13), 0)
    boxf(bm, (24.8, -41, 4.6), (26, -19, 13), 0)
    boxf(bm, (-24.8, -30.4, 4.6), (24.8, -29.6, 8.5), 0)
    for x, y in ((-30, 10), (30, 10), (-30, -52), (30, -52), (0, 62)):   # 托住主板的小立柱
        rod(bm, 1.6, 4.6, PCB_Z[0], 0, 'Z', (x, y, 0), seg=14)

    def post(b):
        for y, s in ((BAT_Y[0], 1), (BAT_Y[1], -1)):   # 电池槽底的 + / - 记号
            text(b, '+', 3.2, 18 * s, y, 4.6, 2)
            text(b, '-', 3.2, -18 * s, y, 4.6, 2)
    finish('P01_BackCase', 1, bm, mats, bevel=.6, post=post)


def build_contacts(M):
    mats = [M['nickel'], M['wire_red'], M['wire_blk']]
    bm = bmesh.new()
    xs = 24.2
    for y, neg_x in ((BAT_Y[0], -xs), (BAT_Y[1], xs)):
        s = 1 if neg_x > 0 else -1
        # 锥形弹簧（顶负极）：螺旋线扫掠
        pts = []
        for k in range(73):
            t = k / 72
            a = t * 2 * pi * 4
            rr = 4.0 - 2.0 * t
            pts.append(Vector((neg_x - s * 5.0 * t, y + rr * cos(a), BAT_Z + rr * sin(a))))
        sweep(bm, pts, .32, 0, sides=6)
        boxf(bm, (neg_x - .2 + .2 * s, y - 4.5, 5.5), (neg_x + .2 + .2 * s, y + 4.5, 14.2), 0)
        # 平片（顶正极）
        px = -neg_x
        boxf(bm, (px - .2, y - 4, 5.8), (px + .2, y + 4, 14), 0)
    # 右边：电池 1 正极和电池 2 负极连成一片（串联）
    boxf(bm, (xs - .2, BAT_Y[1] + 3, 12.6), (xs + .6, BAT_Y[0] - 3, 13.6), 0)
    # 左边两片是电池组的 + / -，红黑引线拉到主板底面
    for y, mi in ((BAT_Y[1], 1), (BAT_Y[0], 2)):
        ctrl = [Vector(p) for p in ((-xs, y, 14.0), (-xs + 1, y, 15.0), (-xs + 3.5, y + 2, 14.8), (-18, y + 5, 15.0))]
        sweep(bm, catmull(ctrl, per=6), .55, mi, sides=8)
    finish('P02_BatteryContacts', 2, bm, mats)


def build_holster(M):
    outer = rrect(38, 75, 11, ns=10)
    bm = bmesh.new()
    extrude(bm, ring2d(outer, rrect(*BODY)), 3, FACE, 0)
    extrude(bm, ring2d(outer, rrect(31, 68, 6)), FACE, 38, 0)
    extrude(bm, ring2d(outer, rrect(29, 60, 8)), 0, 3, 0)
    for k in range(13):                       # 侧面防滑凸棱
        y = -36 + k * 6
        boxf(bm, (37.4, y - 1, 9), (38.9, y + 1, 29), 0)
        boxf(bm, (-38.9, y - 1, 9), (-37.4, y + 1, 29), 0)
    finish('P03_Holster', 3, bm, [M['rubber']], ex=EX['holster'], bevel=.8)


ICONS = (('V~', 3.0), ('•)))', 2.5), ('Ω', 3.4), ('A~', 3.0), ('Hz', 3.0), ('LIVE', 1.8), ('NCV', 2.2))


def build_front_shell(M):
    mats = [M['face'], M['case'], M['white'], M['orange'], M['collar_red'], M['collar_blk'], M['led_red'], M['hole']]
    hw, hh, r = BODY
    holes = [rrect(28, 25, 2, cy=29)]                                    # 屏幕窗口 x ±28, y 4~54
    holes += [rrect(6.2, 5.2, 1.6, cx=x, cy=KEY_Y) for x in KEYS_X]      # 按键孔
    holes += [circle(x, JACK_Y, 4.2, 32) for x, _, _ in JACKS]          # 表笔插孔
    holes += [circle(x, y, 2.6, 20) for x, y in SCREWS]                  # 螺丝沉孔
    holes += [circle(*NCV_LED, 1.3, 12)]                                 # 指示灯导光柱
    bm = bmesh.new()
    extrude(bm, [rrect(hw, hh, r)] + [h[::-1] for h in holes], FACE - 2, FACE, 0)
    extrude(bm, ring2d(rrect(hw, hh, r), rrect(hw - 2, hh - 2, r - 2)), PCB_Z[1], FACE - 2, 1)
    for x, y in SCREWS:
        rev(bm, [(1.4, PCB_Z[1]), (3.0, PCB_Z[1]), (3.0, 33.4), (1.4, 33.4)], 1, 'Z', (x, y, 0), seg=20, closed=True)
    for x, name, _ in JACKS:                   # 插孔外圈：V、A 红色，COM 黑色
        rev(bm, [(4.2, FACE), (6.3, FACE), (6.3, FACE + .6), (5.8, FACE + 1.2), (4.2, FACE + 1.2)],
            5 if name == 'COM' else 4, 'Z', (x, JACK_Y, 0), seg=40, closed=True)
    rod(bm, 1.25, FACE - 2, FACE + .12, 6, 'Z', (NCV_LED[0], NCV_LED[1], 0), seg=14)
    # 屏幕窗口四周往下翻一圈边，从斜上方看不到面壳里面
    extrude(bm, ring2d(rrect(29.2, 26.2, 2.6, cy=29), rrect(28, 25, 2, cy=29)), 32.2, FACE - 2, 0)

    def post(b):
        z = FACE
        # 顶部：SATA 六边形标志 + 型号
        flat(b, ring2d(hexagon(-21.5, 61, 3.3, pi / 6), hexagon(-21.5, 61, 2.4, pi / 6)), z, 2, .08)
        flat(b, [hexagon(-21.5, 61, 1.3, pi / 6)], z, 3, .08)
        text(b, 'SATA', 4.4, -9.5, 61, z, 2)
        text(b, 'DO5054', 3.6, 16, 61, z, 2)
        # 按键下面一排橙色功能图标框
        for i, (s, size) in enumerate(ICONS):
            cx = -24.6 + i * 8.2
            flat(b, ring2d(rrect(3.7, 3.3, 1.0, ns=4, cx=cx, cy=-25.5), rrect(3.25, 2.85, .7, ns=4, cx=cx, cy=-25.5)), z, 3)
            text(b, s, size, cx, -25.6, z, 3)
        text(b, 'AUTO POWER OFF', 2.4, 0, -33.2, z, 2)
        # 插孔上方的标注
        text(b, 'FUSED 4A MAX', 1.75, -20, -39.0, z, 2)
        text(b, 'A', 3.4, -20, -44.4, z, 2)
        warn_triangle(b, -27.3, -44.4, z, 4.0, 3)
        text(b, 'COM', 2.8, 0, -44.4, z, 2)
        text(b, '600V CAT III', 1.75, 20, -39.0, z, 2)
        text(b, 'V', 3.4, 20, -44.4, z, 2)
        warn_triangle(b, 27.3, -44.4, z, 4.0, 3)
    finish('P04_FrontShell', 4, bm, mats, ex=EX['front'], bevel=.5, post=post)


def build_screws(M):
    for i, (x, y) in enumerate(SCREWS):
        bm = bmesh.new()
        rod(bm, 1.2, 20.0, 33.4, 0, 'Z', (x, y, 0), seg=12)
        rev(bm, [(0, 33.4), (2.2, 33.4), (2.25, 34.2), (1.8, 34.8), (0, 34.8)], 0, 'Z', (x, y, 0), seg=20)
        boxf(bm, (x - .9, y - .22, 34.78), (x + .9, y + .22, 34.84), 1)
        boxf(bm, (x - .22, y - .9, 34.78), (x + .22, y + .9, 34.84), 1)
        finish(f'P05_Screw_{i + 1}', 5, bm, [M['screw'], M['hole']], ex=EX['screw'])


def build_keypad(M):
    mats = [M['key_sheet'], M['key_yellow'], M['key_gray'], M['print_black'], M['white'], M['carbon']]
    bm = bmesh.new()
    extrude(bm, [rrect(28, 8, 2, cy=KEY_Y)], 17.3, 18.2, 0)
    for i, x in enumerate(KEYS_X):
        mi = 1 if i == 0 else 2
        extrude(bm, [rrect(5.9, 4.9, 1.6, cx=x, cy=KEY_Y)], 18.2, 19.6, mi)
        extrude(bm, [rrect(5.5, 4.5, 1.6, cx=x, cy=KEY_Y)], 19.6, 36.2, mi)
        extrude(bm, [rrect(5.2, 4.2, 1.4, cx=x, cy=KEY_Y)], 36.2, 36.6, mi)
        rod(bm, 2.4, 17.12, 17.3, 5, 'Z', (x, KEY_Y, 0), seg=16)      # 底面导电碳粒

    def post(b):
        z = 36.6
        power_icon(b, KEYS_X[0], KEY_Y, z, 2.1, 3)
        text(b, 'SEL', 2.2, KEYS_X[1], KEY_Y + 1.1, z, 4)
        flat(b, ring2d(circle(KEYS_X[1], KEY_Y - 2.0, .9, 16), circle(KEYS_X[1], KEY_Y - 2.0, .55, 16)), z, 4)   # 灯泡
        text(b, 'HOLD', 1.9, KEYS_X[2], KEY_Y + 1.1, z, 4)
        flat(b, [circle(KEYS_X[2], KEY_Y - 2.0, .55, 12)], z, 4)                                                  # 太阳
        for k in range(8):
            a = k * pi / 4
            c = (KEYS_X[2] + 1.15 * cos(a), KEY_Y - 2.0 + 1.15 * sin(a))
            flat(b, [strip_pts((c[0] - .3 * cos(a), c[1] - .3 * sin(a)), (c[0] + .3 * cos(a), c[1] + .3 * sin(a)), .22)], z, 4)
        text(b, 'NCV', 1.9, KEYS_X[3], KEY_Y + 1.1, z, 4)
        text(b, 'LIVE', 1.6, KEYS_X[3], KEY_Y - 1.5, z, 4)
    finish('P06_Keypad', 6, bm, mats, ex=EX['keypad'], bevel=.35, post=post)


# ---------------------------------------------------------------- 液晶屏叠层
def build_lcd(M):
    mats = [M['lcd_glass'], M['lcd_bg'], M['lcd_seg'], M['pin']]
    bm = bmesh.new()
    boxf(bm, (-30, 2, 29), (30, 56, 30.5), 0)           # 下片玻璃（两边露出引脚边）
    boxf(bm, (-29, 4, 30.5), (29, 54, 32), 1)           # 上片玻璃 + 偏光片
    for k in range(46):
        x = -22.5 + k
        boxf(bm, (x - .3, 2.3, 30.5), (x + .3, 3.7, 30.53), 3)
        boxf(bm, (x - .3, 54.3, 30.5), (x + .3, 55.7, 30.53), 3)
    z = 32.0
    # 读数 226.7 V（交流）：照产品图
    for ch, x in zip('2267', (-19.5, -6.5, 6.5, 19.5)):
        seven_seg(bm, ch, x, 33, 10, 20, 2.3, z, 2)
    flat(bm, [rrect(.9, .9, .3, ns=3, cx=12.6, cy=23.9)], z, 2)          # 小数点
    text(bm, 'AC', 3.6, -21.5, 48.3, z, 2)
    text(bm, '~', 4.4, -15.2, 48.6, z, 2)
    text(bm, 'AUTO', 2.4, -4.0, 48.3, z, 2)
    flat(bm, ring2d(rrect(3, 1.5, .3, ns=3, cx=21, cy=48.3), rrect(2.6, 1.1, .2, ns=3, cx=21, cy=48.3)), z, 2)   # 电池图标
    flat(bm, [rrect(.4, .7, .1, ns=2, cx=24.4, cy=48.3)], z, 2)
    for k in range(3):
        flat(bm, [rrect(.55, .8, .1, ns=2, cx=19.3 + k * 1.6, cy=48.3)], z, 2)
    text(bm, 'V', 7.2, 21.5, 14.6, z, 2)
    for k in range(24):                                   # 模拟条
        x = -25 + k * 1.55
        flat(bm, [rrect(.42, 1.3, .1, ns=2, cx=x, cy=10.4)], z, 2 if k < 15 else 0, .03)
    flat(bm, [rrect(13, .12, .05, ns=2, cx=-12.6, cy=8.4)], z, 2, .03)
    for k in range(5):
        flat(bm, [rrect(.12, .45, .05, ns=2, cx=-25 + k * 9.3, cy=7.9)], z, 2, .03)
    finish('P07_LCD', 7, bm, mats, ex=EX['lcd'])


def build_zebras(M):
    for i, (y0, y1) in enumerate(((2.2, 4.6), (53.4, 55.8))):
        bm = bmesh.new()
        boxf(bm, (-24, y0, PCB_Z[1]), (24, y1, 29), 0)
        for k in range(48):
            x = -23.5 + k
            boxf(bm, (x - .16, y0 - .05, PCB_Z[1]), (x + .16, y1 + .05, 29.05), 1)
        finish(f'P08_Zebra_{i + 1}', 8, bm, [M['zebra'], M['zebra_dark']], ex=EX['zebra'])


def build_guide(M):
    bm = bmesh.new()
    boxf(bm, (-27, 5.5, 26), (27, 52.5, 28.8), 0)
    for s in (-1, 1):                          # 往下伸到 LED 的入光脚
        boxf(bm, (min(24 * s, 27 * s), 27, 19.4), (max(24 * s, 27 * s), 31, 26), 0)
    for i in range(12):
        for j in range(10):
            x = -24.2 + i * 4.4
            y = 8.5 + j * 4.5
            disk(bm, .45 + .03 * abs(i - 5.5), (x, y, 28.8), 'Z', 1, h=.03, seg=8)
    finish('P09_LightGuide', 9, bm, [M['guide'], M['guide_dot']], ex=EX['guide'])


def build_holder(M):
    bm = bmesh.new()
    extrude(bm, ring2d(rrect(31, 29.2, 2, cy=29), rrect(28.5, 27, 1.2, cy=29)), PCB_Z[1], 29, 0)
    finish('P10_LCDHolder', 10, bm, [M['case']], ex=EX['holder'], bevel=.4)


# ---------------------------------------------------------------- 主板
SIG = [
    # (点列, 线宽) —— 浅绿色走线，按信号走向画（不是真实布线，是"原理图"）
    ([(20, -50.5), (20, -45), (13.5, -40.5), (12, -38.6)], 1.0),              # V 插孔 → PTC
    ([(8, -38.6), (5, -34), (4, -30.2)], 1.0),                                 # PTC → 分压电阻 R1
    ([(4, -21.8), (9, -21.8)], .7), ([(9, -30.2), (14, -30.2)], .7), ([(14, -21.8), (19, -21.8)], .7),
    ([(19, -30.2), (19, -32.4), (27.4, -32.4), (27.4, -47.5), (4, -48.6), (0, -50.5)], .9),   # R4 → COM
    ([(21, -38.6), (20, -45)], .7), ([(25, -38.6), (27.4, -41)], .7),          # 压敏电阻跨在 V、COM 之间
    ([(-20, -50.5), (-26, -45.5), (-26, -43)], 1.4),                           # A 插孔 → 保险丝
    ([(-10, -43), (-10, -46.5)], 1.4),                                         # 保险丝 → 分流器
    ([(-2, -46.5), (0, -48), (0, -50.5)], 1.4),                                # 分流器 → COM
    ([(-2, -46), (-2, -35), (-1.4, -20), (-1.4, -2), (-4, 20), (-3, 25.4)], .6),   # COM（地）→ 主控
    ([(6.5, -21.8), (6.5, -19.6), (1.3, -16.5), (1.3, -2), (-11, 10.5), (-11, 14.2)], .6),   # 分压抽头 → 模拟开关
    ([(-9.8, 17.6), (-7.2, 22.5), (-5.2, 27.2)], .5), ([(-9.8, 16.4), (-6.2, 21), (-4.6, 26.2)], .5),   # 模拟开关 → 主控
    ([(12.3, 17.6), (7.2, 22.5), (5.2, 27.2)], .5), ([(12.3, 16.4), (6.2, 21), (4.6, 26.2)], .5),       # EEPROM → 主控
    ([(10, 41), (6.4, 36), (5.2, 33)], .5),                                    # 晶振 → 主控
    ([(-11.2, 42), (-6.4, 36), (-5.2, 33)], .5),                               # 基准 → 主控
    ([(0, 58.4), (0, 34.6)], .6),                                              # NCV 线圈 → 主控
    ([(-27.5, 59.3), (-20, 52), (-3.6, 34.8)], .5),                            # NCV 指示灯 ← 主控
    ([(23.5, 29), (16.5, 29.6), (5.2, 31)], .5), ([(-23.5, 29), (-5.2, 31)], .5),   # 背光 LED ← 主控
    ([(15.6, 33), (5.2, 32)], .5),                                             # 电源 MOS
    ([(-21, -7.2), (-24, 2), (-24, 24), (-5.2, 29.4)], .5),                    # 按键 → 主控
    ([(-7, -7.2), (-7, 10), (-5.6, 24.6)], .5), ([(7, -7.2), (7, 10), (5.6, 24.6)], .5),
    ([(21, -7.2), (25.6, 1), (25.6, 22), (21, 26), (5.2, 28.6)], .5),
    ([(-25.2, -27), (-28, -22), (-28, 25.4), (-26.4, 27), (-5.2, 30.3)], .5),  # 蜂鸣器 ← 主控
]


def build_pcb(M):
    mats = [M['pcb'], M['trace'], M['gold'], M['silk'], M['solder'], M['brass']]
    bm = bmesh.new()
    z = PCB_Z[1]
    extrude(bm, [rrect(32, 69, 6)] + [circle(x, y, 3.3, 20)[::-1] for x, y in SCREWS], PCB_Z[0], z, 0)
    for pts, w in SIG:
        polyline(bm, pts, w, z, 1)
    for x in KEYS_X:                                       # 按键梳状焊盘：金色圆盘 + 绿油隔开的梳齿
        disk(bm, 3.9, (x, KEY_Y, z), 'Z', 2, h=.05, seg=28)
        for k in range(5):
            dy = -2.6 + k * 1.3
            L = math.sqrt(max(0.0, 3.9 ** 2 - dy ** 2)) - .5
            flat(bm, [strip_pts((x - L, KEY_Y + dy), (x + L, KEY_Y + dy), .32, False)], z + .05, 0, .02)
    for k in range(48):                                    # 斑马条焊盘
        x = -23.5 + k
        boxf(bm, (x - .3, 2.6, z), (x + .3, 4.2, z + .04), 2)
        boxf(bm, (x - .3, 53.8, z), (x + .3, 55.4, z + .04), 2)
    for x, _, _ in JACKS:                                  # 插孔焊盘
        flat(bm, ring2d(circle(x, JACK_Y, 5.0, 32), circle(x, JACK_Y, 3.4, 32)), z, 4, .1)
    for cx in (-26, -10):                                  # 保险丝座（两个黄铜夹子）
        boxf(bm, (cx - 2, -43.1, z), (cx + 2, -36.9, z + .6), 5)
        boxf(bm, (cx - 2, -43.1, z), (cx + 2, -42.5, 22.5), 5)
        boxf(bm, (cx - 2, -37.5, z), (cx + 2, -36.9, 22.5), 5)
    for s, x, y, size in (('U1', 0, 23.6, 1.5), ('U2', -15, 12.2, 1.4), ('U3', 15, 12.2, 1.4), ('Y1', 13, 43.6, 1.3),
                          ('VR1', -13, 44.2, 1.3), ('Q1 U4', 21.6, 37.4, 1.2), ('F1  4A 250V', -18, -46.0, 1.3),
                          ('PTC1', 10, -33.6, 1.3), ('RV1', 23, -33.6, 1.3), ('RS1', -6, -44.2, 1.3),
                          ('BZ1', -19, -35.0, 1.3), ('R1-R4', 11.5, -31.4, 1.2), ('NCV', 23.5, 62, 1.5),
                          ('LED1', -25.5, 32.6, 1.1), ('LED2', 25.5, 32.6, 1.1), ('DMM MAIN V1.0', 0, -64.0, 1.6)):
        text(bm, s, size, x, y, z, 3, h=.03)
    finish('P11_PCB', 11, bm, mats, ex=EX['pcb'])


def ic(bm, cx, cy, bw, bh, pins_x, pins_y, pitch, z0=PCB_Z[1], th=1.4, lead=1.1):
    """贴片芯片：本体 + 四边（或两边）的鸥翼引脚。pins_x = 上下两边每边几个脚，pins_y = 左右两边每边几个脚"""
    boxf(bm, (cx - bw / 2, cy - bh / 2, z0 + .2), (cx + bw / 2, cy + bh / 2, z0 + .2 + th), 0)
    for k in range(pins_x):
        x = cx - pitch * (pins_x - 1) / 2 + k * pitch
        for s in (-1, 1):
            y0 = cy + s * bh / 2
            boxf(bm, (x - .14, min(y0, y0 + s * lead), z0), (x + .14, max(y0, y0 + s * lead), z0 + .5), 1)
    for k in range(pins_y):
        y = cy - pitch * (pins_y - 1) / 2 + k * pitch
        for s in (-1, 1):
            x0 = cx + s * bw / 2
            boxf(bm, (min(x0, x0 + s * lead), y - .14, z0), (max(x0, x0 + s * lead), y + .14, z0 + .5), 1)
    return z0 + .2 + th


def build_chips(M):
    mats = [M['chip'], M['solder'], M['chip_mark']]
    bm = bmesh.new()
    top = ic(bm, *SOC, 8, 8, 12, 12, .6)
    disk(bm, .45, (SOC[0] - 3, SOC[1] + 3, top), 'Z', 2, h=.03, seg=12)
    text(bm, 'DMM SoC', 1.3, SOC[0], SOC[1] + .6, top, 2, h=.03)
    text(bm, 'ADC+MCU+LCD', .8, SOC[0], SOC[1] - 1.4, top, 2, h=.03)
    finish('P12_SoC', 12, bm, mats, ex=comp_ex())

    bm = bmesh.new()
    top = ic(bm, -15, 17, 10, 4, 8, 0, 1.27)
    disk(bm, .35, (-19.2, 15.8, top), 'Z', 2, h=.03, seg=10)
    text(bm, 'MUX', 1.3, -15, 17, top, 2, h=.03)
    finish('P13_AnalogSwitch', 13, bm, mats, ex=comp_ex())

    bm = bmesh.new()
    top = ic(bm, 15, 17, 5, 4, 4, 0, 1.27)
    disk(bm, .3, (13.1, 15.8, top), 'Z', 2, h=.03, seg=10)
    text(bm, '24C02', .9, 15, 17, top, 2, h=.03)
    finish('P14_EEPROM', 14, bm, mats, ex=comp_ex())

    bm = bmesh.new()
    rod(bm, 1.0, 10, 16, 0, 'X', (0, 41, 18.1), seg=16)
    for dy in (-.4, .4):
        boxf(bm, (9.2, 41 + dy - .12, PCB_Z[1]), (10, 41 + dy + .12, 18.3), 1)
    finish('P15_Crystal', 15, bm, [M['nickel'], M['solder']], ex=comp_ex())

    bm = bmesh.new()
    ic(bm, -13, 42, 2.9, 1.3, 0, 0, 1)
    for x, s in ((-13.95, -1), (-12.05, -1), (-13, 1)):
        y0 = 42 + s * .65
        boxf(bm, (x - .2, min(y0, y0 + s * .9), PCB_Z[1]), (x + .2, max(y0, y0 + s * .9), PCB_Z[1] + .5), 1)
    finish('P16_VoltageRef', 16, bm, mats, ex=comp_ex())

    bm = bmesh.new()
    for cy in (33.0, 37.4):
        ic(bm, 17, cy, 2.9, 1.3, 0, 0, 1)
        for x, s in ((16.05, -1), (17.95, -1), (17, 1)):
            y0 = cy + s * .65
            boxf(bm, (x - .2, min(y0, y0 + s * .9), PCB_Z[1]), (x + .2, max(y0, y0 + s * .9), PCB_Z[1] + .5), 1)
    finish('P17_PowerSwitch', 17, bm, mats, ex=comp_ex())


BANDS = ('band_brown', 'band_black', 'band_black')
MULT = ('band_green', 'band_yellow', 'band_orange', 'band_red')


def build_analog(M):
    """分压电阻、PTC、压敏电阻、分流器、蜂鸣器"""
    # 4 个精密电阻：沿 Y 卧放，两头的脚弯下去插进主板
    names = ['res_body', 'solder'] + list(dict.fromkeys(BANDS + MULT))
    mats = [M[n] for n in names]
    bm = bmesh.new()
    zc = 18.6
    for i, x in enumerate((4.0, 9.0, 14.0, 19.0)):
        rev(bm, [(0, -29), (.9, -29), (1.15, -28.6), (1.15, -23.4), (.9, -23), (0, -23)], 0, 'Y', (x, 0, zc), seg=16)
        colors = BANDS + (MULT[i], 'band_brown')
        for y, cname in zip((-24.0, -24.9, -25.8, -26.7, -28.0), colors):
            rev(bm, [(1.17, y - .3), (1.22, y - .3), (1.22, y + .3), (1.17, y + .3)], names.index(cname), 'Y', (x, 0, zc),
                seg=16, closed=True)
        for y0, y1, yv in ((-23, -21.6, -22.0), (-30.4, -29, -30.0)):
            boxf(bm, (x - .22, y0, zc - .22), (x + .22, y1, zc + .22), 1)
            boxf(bm, (x - .22, yv - .22, PCB_Z[1]), (x + .22, yv + .22, zc + .22), 1)
    finish('P18_DividerResistors', 18, bm, mats, ex=comp_ex())

    # PTC：竖着插的圆片（面朝 -Y），涂层是黄褐色
    for name, no, cx, r, th, mat in (('P19_PTC', 19, 10.0, 4.6, 3.6, 'ptc'), ('P20_Varistor', 20, 23.0, 3.6, 3.0, 'mov')):
        bm = bmesh.new()
        zc = PCB_Z[1] + 2.0 + r
        rev(bm, [(0, -th / 2), (r - .8, -th / 2), (r, -th / 4), (r, th / 4), (r - .8, th / 2), (0, th / 2)], 0, 'Y',
            (cx, -37.0, zc), seg=32)
        for dx in (-2.0, 2.0):
            boxf(bm, (cx + dx - .25, -37.25, PCB_Z[1]), (cx + dx + .25, -36.75, zc - r + 1), 1)
        finish(name, no, bm, [M[mat], M['solder']], ex=comp_ex())

    # 锰铜分流器：一根弯成门字形的粗丝，两头焊在主板上
    bm = bmesh.new()
    ctrl = [Vector(p) for p in ((-10, -46.5, 16.4), (-10, -46.5, 19.6), (-9.2, -46.5, 21.2), (-7, -46.5, 21.6),
                                (-5, -46.5, 21.6), (-2.8, -46.5, 21.2), (-2, -46.5, 19.6), (-2, -46.5, 16.4))]
    sweep(bm, catmull(ctrl, per=5), .65, 0, sides=10)
    for x in (-10, -2):
        rev(bm, [(0, PCB_Z[1]), (1.3, PCB_Z[1]), (.7, PCB_Z[1] + .7), (0, PCB_Z[1] + .9)], 1, 'Z', (x, -46.5, 0), seg=14)
    finish('P22_Shunt', 22, bm, [M['copper'], M['solder']], ex=comp_ex())

    bm = bmesh.new()
    rev(bm, [(0, PCB_Z[1]), (6, PCB_Z[1]), (6, 23.6), (5.6, 24.0), (1.3, 24.0), (1.3, 23.4), (0, 23.4)], 0, 'Z',
        (-19, -27, 0), seg=40)
    text(bm, '+', 2.2, -22.5, -24, 24.0, 1, h=.04)
    finish('P23_Buzzer', 23, bm, [M['buzzer'], M['white']], ex=comp_ex())


def build_fuse(M):
    bm = bmesh.new()
    zc = 20.5
    rev(bm, [(0, -23.5), (2.5, -23.5), (2.5, -12.5), (0, -12.5)], 0, 'X', (0, -40, zc), seg=32)
    for a0, a1 in ((-28, -23.3), (-12.7, -8)):
        rev(bm, [(0, a0), (2.4, a0), (2.65, a0 + .3), (2.65, a1 - .3), (2.4, a1), (0, a1)], 1, 'X', (0, -40, zc), seg=32)
    text(bm, 'F4AH 250V', 1.3, -18, -40, zc + 2.5, 2, h=.04)
    finish('P21_Fuse', 21, bm, [M['ceramic'], M['nickel'], M['print_black']], ex=EX['fuse'])


def build_jacks(M):
    for x, name, no in JACKS:
        bm = bmesh.new()
        rev(bm, [(2.1, 14.0), (3.0, 14.0), (3.0, PCB_Z[1]), (4.6, PCB_Z[1]), (4.6, 18.0), (3.5, 18.6), (3.5, 34.5),
                 (2.1, 34.5)], 0, 'Z', (x, JACK_Y, 0), seg=32, closed=True)
        disk(bm, 2.1, (x, JACK_Y, 20.0), 'Z', 1, h=.05, seg=20)
        for k in range(4):                                # 插座里的弹簧接触片的开缝
            a = k * pi / 2 + pi / 4
            c = Vector((x + 2.8 * cos(a), JACK_Y + 2.8 * sin(a), 30.0))
            boxf(bm, (c.x - .35, c.y - .35, 26.5), (c.x + .35, c.y + .35, 34.52), 1)
        finish(f'P{no}_Jack_{name}', no, bm, [M['brass'], M['hole']], ex=comp_ex())


def build_leds(M):
    for i, s in enumerate((-1, 1)):
        bm = bmesh.new()
        x = 25.5 * s
        boxf(bm, (x - 1.0, 27.5, PCB_Z[1]), (x + 1.0, 30.5, 18.3), 0)
        boxf(bm, (min(x - 1.02 * s, x - .8 * s), 28.0, 17.3), (max(x - 1.02 * s, x - .8 * s), 30.0, 18.1), 1)
        finish(f'P27_BacklightLED_{i + 1}', 27, bm, [M['led_white'], M['led_yellow']], ex=comp_ex())


def build_ncv(M):
    bm = bmesh.new()
    boxf(bm, (-16, 58.5, 20.0), (16, 65.8, 20.6), 0)
    for x in (-14, 14):                                   # 两只铜脚
        boxf(bm, (x - .6, 61.6, PCB_Z[1]), (x + .6, 62.6, 20.0), 1)
    # 矩形螺旋铜箔线圈
    pts = []
    for k in range(6):
        d = k * 1.0
        pts += [(-15 + d, 59.3 + d), (15 - d, 59.3 + d), (15 - d, 65.0 - d), (-14 + d, 65.0 - d)]
    pts = pts[:-1]
    polyline(bm, pts, .45, 20.6, 1, .04)
    finish('P28_NCVCoil', 28, bm, [M['pcb'], M['copper']], ex=comp_ex())

    bm = bmesh.new()
    x, y = NCV_LED
    rev(bm, [(0, 19.4), (1.8, 19.4), (1.8, 20.2), (1.5, 20.2), (1.5, 22.4), (1.3, 23.3), (.8, 23.8), (0, 23.95)], 0, 'Z',
        (x, y, 0), seg=24)
    for dx in (-.6, .6):
        boxf(bm, (x + dx - .2, y - .2, PCB_Z[1]), (x + dx + .2, y + .2, 19.4), 1)
    finish('P29_NCV_LED', 29, bm, [M['led_red'], M['solder']], ex=comp_ex())


def build_batteries(M):
    for i, (y, s) in enumerate(((BAT_Y[0], 1), (BAT_Y[1], -1))):
        bm = bmesh.new()
        r = 5.2
        rev(bm, [(0, -22.25), (r - .5, -22.25), (r, -21.8), (r, 21.8), (r - .5, 22.25), (0, 22.25)], 0, 'X',
            (0, y, BAT_Z), seg=40)
        rev(bm, [(r + .02, 12), (r + .05, 12), (r + .05, 20), (r + .02, 20)], 1, 'X', (0, y, BAT_Z), seg=40, closed=True)
        rev(bm, [(0, 22.2), (1.6, 22.2), (1.6, 23.0), (1.3, 23.3), (0, 23.3)], 2, 'X', (0, y, BAT_Z), seg=20)  # 正极凸点
        rev(bm, [(0, -22.3), (3.8, -22.3), (3.8, -22.2), (0, -22.2)], 2, 'X', (0, y, BAT_Z), seg=24)         # 负极平面
        ob_mesh = bm
        if s < 0:   # 第二节电池掉个头放（串联）
            xform(ob_mesh, ob_mesh.faces, Matrix.Translation((0, y, BAT_Z)) @ Matrix.Rotation(pi, 4, 'Z') @
                  Matrix.Translation((0, -y, -BAT_Z)))

        def post(b, y=y):
            text(b, '1.5V AAA', 3.0, -3, y, BAT_Z + r - .3, 3, h=.36)
        finish(f'P30_Battery_{i + 1}', 30, ob_mesh, [M['bat_wrap'], M['bat_band'], M['nickel'], M['white']],
               ex=EX['battery'], post=post)


# ---------------------------------------------------------------- 表笔
def build_probe(M, name, no, jack_x, side, mat):
    mats = [M[mat], M['steel'], M['probe_blk'] if mat == 'probe_red' else M['key_gray']]
    bm = bmesh.new()
    px, pz = 55.0 * side, 7.5
    # 笔杆：沿 +Y 平躺在桌上，针尖朝表的顶端
    rev(bm, [(0, -47), (2.0, -47), (3.0, -44), (4.2, -40.5), (5.0, -39.5), (5.0, 38.5), (5.4, 39.5), (7.5, 40.5),
             (7.5, 43.5), (4.4, 45), (3.6, 50), (2.2, 53), (0, 53)], 0, 'Y', (px, 0, pz), seg=36)
    for y in (-30, -24, -18, -12, -6, 0, 6):              # 防滑环
        rev(bm, [(5.0, y), (5.25, y + .4), (5.25, y + 1.6), (5.0, y + 2.0)], 2, 'Y', (px, 0, pz), seg=36, closed=True)
    rev(bm, [(0, 52.5), (.9, 52.5), (.9, 70), (.55, 72.5), (0, 73.6)], 1, 'Y', (px, 0, pz), seg=14)   # 金属针
    # 插头：竖着插在面板插孔里
    jx, jy = jack_x, JACK_Y
    rev(bm, [(0, 20.5), (2.0, 20.5), (2.0, 34.6), (0, 34.6)], 1, 'Z', (jx, jy, 0), seg=18)               # 插针
    rev(bm, [(0, 34.6), (4.0, 34.6), (4.0, 36.4), (4.8, 37.0), (4.8, 50.0), (4.0, 51.5), (3.0, 52.5), (2.6, 57.5),
             (2.0, 58.5), (0, 58.5)], 0, 'Z', (jx, jy, 0), seg=32)
    for z in (40, 43, 46):
        rev(bm, [(4.8, z), (5.05, z + .3), (5.05, z + 1.4), (4.8, z + 1.7)], 0, 'Z', (jx, jy, 0), seg=32, closed=True)
    # 表笔线：从插头顶上弯出去，落到桌上，接到笔尾
    ctrl = [Vector(p) for p in ((jx, jy, 57.5), (jx, jy, 64), (jx + 8 * side, jy - 7, 63), (side * 40, -70, 34),
                                (px, -69, 13), (px, -58, pz), (px, -47.5, pz))]
    sweep(bm, catmull(ctrl, per=10), 1.8, 0, sides=12)
    finish(name, no, bm, mats, ex=[(0, 0, 32, .00), (10 * side, -50, 0, .05)])


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
        bg.inputs[1].default_value = .35
    bm = bmesh.new()
    box(bm, (0, 0, -5), (1200, 1200, 10), 0)
    me = bpy.data.meshes.new('Table')
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Scale(MM, 4))
    me.materials.append(principled('M_Table', '#7a6650', 0, .6))
    table = bpy.data.objects.new('Table', me)
    collection('Scene').objects.link(table)
    for name, loc, power, size in (('Key', (-.35, -.45, .7), 60, 1.0), ('Fill', (.5, -.3, .4), 25, 1.2),
                                   ('Rim', (.15, .6, .5), 40, .8)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, (0, 0, .05))
        collection('Scene').objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 50
    cam = bpy.data.objects.new('Cam', cd)
    cam.location = (.22, -.42, .42)
    look_at(cam, (0.0, -.005, .075))
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
    ROOT = bpy.data.objects.new('Multimeter', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .03
    collection('Multimeter').objects.link(ROOT)
    build_back_case(M)
    build_contacts(M)
    build_holster(M)
    build_front_shell(M)
    build_screws(M)
    build_keypad(M)
    build_lcd(M)
    build_zebras(M)
    build_guide(M)
    build_holder(M)
    build_pcb(M)
    build_chips(M)
    build_analog(M)
    build_fuse(M)
    build_jacks(M)
    build_leds(M)
    build_ncv(M)
    build_batteries(M)
    build_probe(M, 'P31_ProbeRed', 31, JACKS[0][0], 1, 'probe_red')
    build_probe(M, 'P32_ProbeBlack', 32, JACKS[1][0], -1, 'probe_blk')
    setup_world_and_cam(M)
    animate_explode()
    viewport_defaults()
    export_glb(os.path.join(OUT, 'multimeter.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'multimeter.blend'))
    print('[OK] saved multimeter.blend')
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
    print(f'[OK] {len(OBJS)} multimeter objects, {tris} triangles, size {size} mm')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_assembled.png', 1, cam=(.13, -.24, .25), target=(0, -.002, .02))
        render_still('render_exploded.png', F_EXP[1] + 10, cam=(.32, -.52, .42), target=(0, .03, .09))
        set_engine('EEVEE')


main()
