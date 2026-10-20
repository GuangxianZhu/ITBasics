# -*- coding: utf-8 -*-
"""
原创 3 寸涵道穿越机（cinewhoop）—— Blender 建模 + 飞行演示 + 爆炸图

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_drone.py -- [输出目录] [--render] [--video]

输出（默认在 output/ 下）:
    drone.blend        Blender 工程，按空格播放：
                         第 1~449 帧    飞行演示（起飞 → 8 字穿过两个竞速门 → 降落）
                         第 450~894 帧  差速原理（油门 → 偏航 → 横滚 → 俯仰；画面左下角是四个电机的推力差）
                         第 895~1195 帧 爆炸图（展示台转圈：拆开 → 停留 → 装回）
                       时间线上的标记（Marker）会自动切换相机
    render_*.png       加 --render 时用 Cycles 渲染 4 张预览图
    drone_demo.mp4     加 --video 时用 EEVEE 把整段动画渲染成视频（1280×720）

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    机头朝 -Y（Blender 前视图 Numpad1 正对机头），+Z 向上，+X 是机身右侧
    所有零件都挂在空物体 Drone 下面：飞行/差速动画只动 Drone，爆炸动画只动零件的相对位置

兼容: Blender 4.2 ~ 5.x
"""
import base64
import json
import math
import os
import sys
from math import atan, atan2, cos, pi, radians, sin, sqrt

import bpy  # 必须先于 bmesh 导入（作为 Python 模块运行时）
import bmesh
from mathutils import Matrix, Quaternion, Vector
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))
ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = next((a for a in ARGV if not a.startswith('--')), os.path.join(HERE, 'output'))
DO_RENDER = '--render' in ARGV
DO_VIDEO = '--video' in ARGV
os.makedirs(OUT, exist_ok=True)

MM = 0.001
FPS = 30
G = 9.81

# ---------------------------------------------------------------- 主要尺寸 (mm)
MOTOR_XY = 52.0        # 电机中心 (±52, ±52) → 对角轴距 147
DUCT_R_IN = 39.0       # 涵道内径 Φ78（3 寸桨 Φ76，单边留 1 mm）
DUCT_R_OUT = 43.0      # 涵道外径 Φ86
DUCT_H = 22.0
PROP_R = 38.0
PROP_Z = 17.2          # 桨叶所在高度
PROP_PITCH = 50.0      # 螺距 (mm)，决定每个截面的安装角
STACK_HOLE = 12.75     # 飞控/电调 25.5 mm 孔距
CAM_PIVOT = (-42.0, 19.0)   # 相机转轴 (y, z)
CAM_TILT = 15.0        # 相机上仰角（度）

# 四个电机：(名字, 位置, 转向 +1=俯视逆时针)。对角线两只同向，相邻两只反向，反扭矩互相抵消
MOTORS = [('FR', (MOTOR_XY, -MOTOR_XY), +1), ('FL', (-MOTOR_XY, -MOTOR_XY), -1),
          ('RR', (MOTOR_XY, MOTOR_XY), -1), ('RL', (-MOTOR_XY, MOTOR_XY), +1)]

# ---------------------------------------------------------------- 时间线（帧）
F_CLIMB = (30, 70)       # 1~30 地面怠速，30~70 起飞爬升
F_LOOP = (70, 370)       # 8 字航线（10 秒）
F_LAND = (370, 410)      # 下降落地
F_STOP = (410, 435)      # 停桨
F_DEMO = 450             # 差速原理演示（在起降垫上原地做）
D_UP = (475, 515)        # 油门：起飞到 DEMO_H
D_YAW = (530, 585)       # 偏航：转出去 / 转回来 的起始帧（各 40 帧）
D_ROLL = (640, 690)      # 横滚：右移 / 移回 的起始帧
D_PITCH = (735, 785)     # 俯仰：前移 / 移回 的起始帧
D_SHIFT = 36             # 横移、前移各用多少帧
D_DOWN = (830, 865)      # 降落
D_STOP = (867, 883)      # 停桨
F_CUT = 895              # 切到展示台
F_EXP = (905, 1025)      # 拆开
F_ASM = (1055, 1175)     # 装回
F_END = 1195

H = 1.30                 # 巡航高度 (m)
Z0 = 0.009               # 停在起降垫上时 Drone 原点高度（脚垫 4 mm + 垫子 5 mm）
LOOP_A, LOOP_B = 2.6, 2.4    # 8 字航线尺寸 (m)
DISPLAY_Z = 0.22         # 爆炸展示时的展示台高度 (m)
DEMO_H = 0.30            # 差速演示时的悬停高度 (m)
DEMO_MOVE = 0.7          # 横滚/俯仰演示时平移多远 (m)
GATE_X = LOOP_A          # 两个竞速门放在 x = ±A
IDLE_DEG = 22.0          # 怠速：桨每帧转多少度
HOVER_DEG = 42.0         # 悬停：桨每帧转多少度（30 fps 下故意取“看得出在转”的值，真实转速快得多）

# 动力学参数（3 寸 4S 涵道机的量级估计，不是实测）
MASS = 0.38              # 整机质量 (kg)
INERTIA = (1.1e-3, 1.1e-3, 2.0e-3)   # 绕机身 x/y/z 的转动惯量 (kg·m²)
KQ = 0.012               # 反扭矩系数 = 桨的扭矩 / 推力 (m)
F_MAX = MASS * G         # 单个电机最大推力 (N)，相当于推重比 4


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


def make_materials():
    return dict(
        carbon=principled('M_Carbon', '#1c1e22', .2, .38, coat=.6),
        duct=principled('M_Duct_PA', '#2e3238', 0, .62),
        canopy=principled('M_Canopy_TPU', '#e8742c', 0, .55),
        mount=principled('M_Mount_TPU', '#d9662a', 0, .58),
        bell=principled('M_Motor_Bell', '#8d949e', 1, .32),
        accent=principled('M_Motor_Accent', '#2fa4a0', 1, .3),
        steel=principled('M_Steel', '#c9cdd2', 1, .22),
        prop_f=principled('M_Prop_Front', '#ff8a2a', 0, .3, alpha=.92),
        prop_r=principled('M_Prop_Rear', '#c9d2dc', 0, .3, alpha=.92),
        disc=principled('M_Prop_Blur', '#d8dde3', 0, .4, alpha=.16),
        pcb=principled('M_PCB_Black', '#15171a', 0, .35, coat=.5),
        chip=principled('M_Chip', '#232428', 0, .45),
        gold=principled('M_Gold', '#d9b25a', 1, .25),
        shield=principled('M_Shield_Can', '#c4c8cd', 1, .3),
        jst=principled('M_JST_White', '#ece8dc', 0, .5),
        cam=principled('M_Camera_Body', '#25272b', .3, .45),
        glass=principled('M_Lens_Glass', '#0d1420', 0, .04, coat=1),
        batt=principled('M_Battery_Wrap', '#202226', 0, .5),
        label=principled('M_Battery_Label', '#f2c230', 0, .45),
        white=principled('M_White_Print', '#f2f2f2', 0, .5),
        red=principled('M_Wire_Red', '#c8322c', 0, .4),
        black=principled('M_Wire_Black', '#141414', 0, .4),
        xt=principled('M_XT30_Yellow', '#e9c43a', 0, .45),
        strap=principled('M_Strap', '#26282c', 0, .8),
        buckle=principled('M_Strap_Buckle', '#c8322c', 0, .5),
        rubber=principled('M_Rubber', '#121212', 0, .85),
        nylon=principled('M_Nylon', '#e4e0d4', 0, .5),
        ant=principled('M_Antenna', '#1a1a1a', 0, .5),
        ant_sleeve=principled('M_Antenna_Sleeve', '#2fa4a0', 0, .45),
        # 场景
        ground=checker_mat('M_Ground', '#6f8f52', '#7a9a5c', 40),
        pad=principled('M_Pad', '#30343a', 0, .7),
        gate=principled('M_Gate', '#ff7a1a', 0, .5),
        gate_dark=principled('M_Gate_Dark', '#24262a', 0, .6),
        cone=principled('M_Cone', '#ff6a1a', 0, .5),
        acrylic=principled('M_Acrylic', '#dfe8f0', 0, .05, coat=1, alpha=.35),
    )


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


def text_into(bm, body, size, mtx, mi, extrude=0.05, font=None):
    """文字 → 网格，并入 bm（mtx 把文字局部 XY 平面放到世界里）。font=None 用 Blender 内置字体"""
    cu = bpy.data.curves.new('txt', 'FONT')
    if font is not None:
        cu.font = font
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = 'CENTER'
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
    try:
        md.use_self = True          # 刀具里几块可能互相重叠
    except Exception:
        pass
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
ROOT = None         # 空物体 Drone（飞行动画只动它）
OBJS = []           # dict(ob, base, ex)  base/ex 单位 mm（Drone 局部坐标）
PROPS = []          # (prop_ob, disc_ob, spin)


def finish(name, cn, bm, mats, base=(0, 0, 0), ex=(), bevel=0.0, seg=2, angle=50, smooth=34):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('Drone').objects.link(ob)
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
    ob.parent = ROOT
    ob.location = Vector(base) * MM
    ob['name_cn'] = cn
    OBJS.append(dict(ob=ob, base=Vector(base), ex=list(ex)))
    return ob


def diag(mx, my):
    d = Vector((mx, my, 0)).normalized()
    return d, Vector((-d.y, d.x, 0))


# 爆炸路线（Drone 局部坐标 mm，最后一个数 = 出场时刻 0~1，按真实拆机顺序）
EX = dict(
    strap=[(0, 0, 165, .00)],
    battery=[(0, 0, 112, .08)],
    antenna=[(0, 58, 62, .14)],
    prop=[(0, 0, 48, .20)],           # 桨再沿对角线往外移，见 build_props
    canopy=[(0, 40, 85, .28)],       # 往后上方让开，露出里面的飞控塔
    camera=[(0, -55, 0, .36)],
    mount=[(0, -28, 0, .42)],
    vtx=[(0, 0, 44, .46)],
    fc=[(0, 0, 28, .52)],
    esc=[(0, 0, 12, .58)],
    motor=[(0, 0, 28, .64)],
    feet=[(0, 0, -25, .80)],
)


# ---------------------------------------------------------------- 各零件
def build_frame(M):
    """碳板：中央板 + 4 条臂 + 电机座，3 mm 厚"""
    T = 3.0
    bm = bmesh.new()
    extrude(bm, [rrect(24, 41, 7, cy=-7)], 0, T, 0)
    for _, (mx, my), _ in MOTORS:
        d, n = diag(mx, my)
        end = Vector((mx, my, 0)) + d * 40
        st = d * 10
        poly = [tuple((st + n * 5.5)[:2]), tuple((end + n * 5.5)[:2]),
                tuple((end - n * 5.5)[:2]), tuple((st - n * 5.5)[:2])]
        arm = bmesh.new()
        extrude(arm, [poly], 0, T, 0)
        extrude(arm, [circle(mx, my, 10.5, 48)], 0, T, 0)
        bm = boolean(bm, arm, 'UNION')
    # 电机座的 4 个 M2 孔 + 中央减重孔
    holes = bmesh.new()
    for _, (mx, my), _ in MOTORS:
        for k in range(4):
            a = pi / 4 + k * pi / 2
            extrude(holes, [circle(mx + 4.5 * cos(a), my + 4.5 * sin(a), 1.05, 16)], -1, T + 1, 0)
        extrude(holes, [circle(mx, my, 2.6, 24)], -1, T + 1, 0)
    for (cx, cy) in ((0, -38), (0, 27)):
        extrude(holes, [stadium(cx, cy, 8, 3)], -1, T + 1, 0)
    bm = boolean(bm, holes, 'DIFFERENCE')
    finish('P01_Frame', '碳纤维机架', bm, [M['carbon']], bevel=.4)


def build_standoffs(M):
    bm = bmesh.new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * STACK_HOLE, sy * STACK_HOLE
            cyl(bm, 1.5, 3.0, 22.0, 0, 16, x, y)
            revolve(bm, [(0, 20.6), (2.7, 20.6), (2.7, 22.6), (0, 22.6)], 0, seg=6, closed=False, cy=x, cz=y)
    finish('P02_Standoffs', '尼龙立柱 ×4', bm, [M['nylon']])


def build_feet(M):
    for tag, (mx, my), _ in MOTORS:
        bm = bmesh.new()
        revolve(bm, [(0, -4), (3.5, -4), (5, -2.6), (5, 0), (0, 0)], 0, seg=32, closed=False)
        finish(f'P03_Foot_{tag}', '橡胶脚垫', bm, [M['rubber']], base=(mx, my, 0), ex=EX['feet'])


def build_ducts(M):
    prof = [(39.0, 0.0), (41.5, 0.0), (41.5, 16.0), (43.4, 20.5), (42.6, 22.0), (40.6, 21.6),
            (39.0, 18.0), (39.0, 4.5), (36.5, 4.5), (36.5, 3.0), (39.0, 3.0)]
    for tag, (mx, my), _ in MOTORS:
        d, n = diag(mx, my)
        bm = bmesh.new()
        revolve(bm, prof, 0, seg=96, closed=True, b=.35)
        revolve(bm, [(41.3, 0.0), (42.6, 0.0), (42.6, 1.6), (41.3, 1.6)], 0, seg=96, closed=True, b=.3)  # 底部加厚唇
        for k in range(8):                     # 外侧竖向加强筋，避开机臂方向
            a = pi / 8 + k * pi / 4
            c, s = cos(a), sin(a)
            pts = [(41.2 * c - .6 * -s, 41.2 * s - .6 * c), (42.9 * c - .6 * -s, 42.9 * s - .6 * c),
                   (42.9 * c + .6 * -s, 42.9 * s + .6 * c), (41.2 * c + .6 * -s, 41.2 * s + .6 * c)]
            extrude(bm, [pts], 1.6, 15.2, 0)
        c = -d * 37.75     # 涵道底法兰压在机臂末端，用两颗螺丝固定
        for k in (-2.5, 2.5):
            p = c + n * k
            cyl(bm, 1.3, 4.5, 5.4, 1, 12, p.x, p.y)
        ex = [(d.x * 45, d.y * 45, 0, .72)]
        finish(f'P04_Duct_{tag}', '涵道（桨保护圈）', bm, [M['duct'], M['steel']], base=(mx, my, 0), ex=ex,
               bevel=.25, angle=60, smooth=40)


def esc_pads(mx, my):
    """电调上某个电机的 3 个焊盘（世界坐标 mm）。焊盘偏向左右外侧，避开中间的排线插座和角上的立柱"""
    d, n = diag(mx, my)
    sgn = 1 if n.x * mx > 0 else -1
    return [d * 13 + n * sgn * (4.4 + 1.6 * k) for k in range(3)], sgn


def build_motors(M):
    for tag, (mx, my), _ in MOTORS:
        d, n = diag(mx, my)
        mpos = Vector((mx, my, 0))
        bm = bmesh.new()
        revolve(bm, [(0, 3.0), (9.0, 3.0), (9.0, 5.0), (8.2, 5.5), (0, 5.5)], 0, closed=False)   # 底座
        revolve(bm, [(0, 5.7), (9.0, 5.7), (9.0, 12.6), (8.0, 14.0), (2.2, 14.0), (2.2, 14.6), (0, 14.6)],
                0, closed=False)                                                                     # 外转子钟罩
        revolve(bm, [(9.0, 7.2), (9.15, 7.2), (9.15, 9.6), (9.0, 9.6)], 1, closed=True)              # 色环
        cyl(bm, .75, 14.6, 20.6, 2, 16)                                                               # 轴
        for k in range(6):                                                                            # 顶部散热窗
            a = k * pi / 3 + pi / 6
            box(bm, (5.2 * cos(a), 5.2 * sin(a), 14.02), (3.2, 1.6, .1), 3)
        # 三根相线：沿机臂走，越过涵道法兰时抬高，到电调前绕开立柱，焊到电调焊盘上
        pads, sgn = esc_pads(mx, my)
        for k, o in enumerate((-.9, 0, .9)):
            off = n * sgn * o
            pad = pads[k] - mpos
            ctrl = [(-d * 9 + off, 3.8), (-d * 22 + off, 3.8), (-d * 33 + off, 3.8), (-d * 37.5 + off, 6.0),
                    (-d * 42 + off, 3.8), (-d * 48 + off, 4.6), (-d * 52 + n * sgn * (o + 3.2), 7.6),
                    (pad - d * 1.5, 7.4), (pad, 6.9)]
            pts = catmull([Vector((p.x, p.y, z)) for p, z in ctrl], 6)
            sweep(bm, pts, .42, 4, sides=6)
        finish(f'P05_Motor_{tag}', '1404 外转子无刷电机', bm,
               [M['bell'], M['accent'], M['steel'], M['chip'], M['black']], base=(mx, my, 0), ex=EX['motor'])


def chord(r):
    if r <= 20:
        return 7 + 4 * (r - 4) / 16
    if r <= 31:
        return 11 - (r - 20) * .15
    return max(1.2, 9.35 * sqrt(max(0.0, 1 - ((r - 31) / 7.0) ** 2)))


def blade(bm, ang0, spin, mi):
    """一片桨叶：沿半径取若干截面，每个截面按 atan(螺距 / 2πr) 扭转。spin=+1 俯视逆时针"""
    R0 = Matrix.Rotation(ang0, 3, 'Z')
    loops = []
    for r in (4.0, 6, 8, 10, 13, 16, 19, 22, 25, 28, 31, 33, 35, 36.5, 37.5, 37.95):
        c = chord(r)
        beta = min(radians(40), atan(PROP_PITCH / (2 * pi * r)))
        th = 1.6 - (r - 4) / 34
        camber = .07 * c
        u0 = -3 * (r / PROP_R) ** 2               # 桨叶向后掠
        C = Vector((0, spin * cos(beta), sin(beta)))
        N = Vector((0, -spin * sin(beta), cos(beta)))
        L = []
        for k in range(12):
            t = 2 * pi * k / 12
            u = c / 2 * cos(t)
            w = th / 2 * sin(t) * (.6 + .4 * cos(t)) + camber * (1 - (2 * u / c) ** 2)
            p = Vector((r, 0, 0)) + (u + u0) * C + w * N
            L.append(bm.verts.new(R0 @ p))
        loops.append(L)
    fs = []
    for a, b in zip(loops, loops[1:]):
        fs += _bridge(bm, a, b)
    fs.append(bm.faces.new(loops[0][::-1]))
    fs.append(bm.faces.new(loops[-1]))
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)


def build_props(M):
    for tag, (mx, my), spin in MOTORS:
        front = my < 0       # 前桨橙色、后桨浅灰：一眼看出机头方向
        bm = bmesh.new()
        revolve(bm, [(0, -2.4), (4.6, -2.4), (4.6, 2.2), (3.4, 3.0), (0, 3.0)], 0, closed=False)
        for k in range(3):
            blade(bm, k * 2 * pi / 3 + pi / 6, spin, 0)
        revolve(bm, [(0, 2.8), (2.7, 2.8), (2.7, 4.8), (0, 4.8)], 1, seg=6, closed=False)   # 桨螺母
        d, _n = diag(mx, my)
        ex = EX['prop'] + [(d.x * 30, d.y * 30, 0, EX['prop'][0][3])]
        prop = finish(f'P06_Prop_{tag}', '3 寸三叶桨（%s）' % ('正桨 CCW' if spin > 0 else '反桨 CW'), bm,
                      [M['prop_f'] if front else M['prop_r'], M['steel']], base=(mx, my, PROP_Z),
                      ex=ex, smooth=60)
        prop['spin'] = spin
        bm = bmesh.new()
        revolve(bm, [(0, -.12), (37.6, -.12), (37.6, .12), (0, .12)], 0, seg=64, closed=False)
        disc = finish(f'FX_PropBlur_{tag}', '桨盘虚影（只在高速时显示）', bm, [M['disc']],
                      base=(mx, my, PROP_Z), ex=ex)
        PROPS.append((prop, disc, spin))


def board(bm, hw, z0, z1, mi):
    holes = [circle(sx * STACK_HOLE, sy * STACK_HOLE, 1.6, 16)[::-1] for sx in (-1, 1) for sy in (-1, 1)]
    extrude(bm, [rrect(hw, hw, 3)] + holes, z0, z1, mi)


def ribbon(bm, xs, ctrl_yz, r, mis):
    """板间排线：每根线一条扫掠，颜色轮换"""
    for i, x in enumerate(xs):
        pts = catmull([Vector((x, y, z)) for (y, z) in ctrl_yz], 6)
        sweep(bm, pts, r, mis[i % len(mis)], sides=6)


def build_stack(M):
    # ---- 四合一电调：每个电机 6 颗 MOS 管（3 个半桥）+ 1 颗驱动 MCU + 3 个电机焊盘
    bm = bmesh.new()
    board(bm, 16, 5.0, 6.6, 0)
    for _, (mx, my), _s in MOTORS:
        d, n = diag(mx, my)
        for a in (5.2, 8.6):
            for b in (-3.4, 0, 3.4):
                p = d * a + n * b
                box(bm, (p.x, p.y, 7.05), (2.9, 2.9, .9), 1)
        pads, sgn = esc_pads(mx, my)
        p = d * 12 - n * sgn * 4.0
        box(bm, (p.x, p.y, 7.0), (3, 3, .8), 1)
        for p in pads:
            box(bm, (p.x, p.y, 6.7), (1.5, 1.5, .2), 2)
    box(bm, (0, 0, 6.9), (3.2, 1.6, .6), 1)                 # 电流检测电阻
    for x in (-2.6, 2.6):                                   # 电源焊盘
        box(bm, (x, 13.6, 6.7), (2.4, 3.2, .2), 2)
    box(bm, (0, -12.2, 7.4), (6.5, 3, 1.6), 6)              # 8P 排线插座
    for j, x in enumerate((-1.4, 1.4)):                     # 电源线 → XT30 母头
        pts = catmull([Vector((x, 14, 6.8)), Vector((x, 26, 7)), Vector((x, 36, 10)), Vector((x, 42, 17)),
                       Vector((x, 42, 20))], 6)
        sweep(bm, pts, 1.1, 3 if j else 4, sides=8)
    box(bm, (0, 42, 24), (8, 5, 6), 5)
    cap = revolve(bm, [(0, 0), (4.0, 0), (4.0, 11.2), (3.6, 12), (0, 12)], 7, seg=24, closed=False)
    top = revolve(bm, [(0, 12), (3.6, 12), (3.6, 12.1), (0, 12.1)], 8, seg=24, closed=False)
    xform(bm, cap + top, Matrix.Translation((9, 34, 7.2)) @ Matrix.Rotation(-pi / 2, 4, 'X'))  # 低 ESR 电解电容
    for j, x in enumerate((8, 10)):                         # 电容引线接到电源线上
        pts = catmull([Vector((x, 34, 7.2)), Vector((x - 2, 31, 8)), Vector((2.2 if j else 1.8, 30, 8.4))], 6)
        sweep(bm, pts, .35, 3 if j else 4, sides=6)
    finish('P07_ESC', '四合一电调（含电源线、电容、XT30 母头）', bm,
           [M['pcb'], M['chip'], M['gold'], M['red'], M['black'], M['xt'], M['jst'], M['batt'], M['shield']],
           ex=EX['esc'], bevel=.15)

    # ---- 飞控
    bm = bmesh.new()
    board(bm, 16, 12.0, 13.6, 0)
    box(bm, (0, 1, 13.75), (8.4, 8.4, .3), 2)               # MCU 引脚
    box(bm, (0, 1, 14.2), (7, 7, 1.2), 1)                   # MCU
    box(bm, (0, -6.5, 14.0), (3, 3, .8), 1)                 # 陀螺仪
    box(bm, (5.5, -6.5, 14.0), (2.5, 2.5, .8), 1)           # 气压计
    box(bm, (-5.5, -6.5, 14.0), (3, 4, .8), 1)              # 黑匣子 Flash
    box(bm, (5.5, 7.5, 14.0), (3.2, 1.6, .8), 2)            # 晶振
    box(bm, (6, 10.5, 14.1), (2.5, 2.5, 1), 3)              # BOOT 键
    box(bm, (-3, 12.5, 13.9), (1.4, 1, .6), 4)              # LED
    box(bm, (-1, 12.5, 13.9), (1.4, 1, .6), 5)
    box(bm, (10.5, 0, 15.1), (3, 6, 3), 3)                  # 接收机插座
    box(bm, (-13.5, -1, 15.2), (7.5, 9.0, 3.2), 2)          # USB-C
    box(bm, (-17.3, -1, 15.2), (.3, 7.2, 1.8), 1)
    box(bm, (0, -12.2, 11.2), (6.5, 3, 1.6), 3)             # 底面 8P（接电调）
    box(bm, (0, -12.2, 14.4), (5.5, 3, 1.6), 3)             # 顶面 6P（接图传）
    ribbon(bm, [-2.45 + .7 * i for i in range(8)],
           [(-12.8, 7.8), (-16.5, 8.6), (-18.2, 9.8), (-16.5, 11.0), (-12.8, 10.4)], .28, [6, 7, 8, 9])
    finish('P08_FC', '飞控（含到电调的 8P 排线）', bm,
           [M['pcb'], M['chip'], M['steel'], M['jst'], M['accent'], M['red'],
            M['black'], M['red'], M['white'], M['xt']], ex=EX['fc'], bevel=.15)

    # ---- 图传：屏蔽罩 + 铝散热片
    bm = bmesh.new()
    board(bm, 15, 19.0, 20.6, 0)
    box(bm, (0, -2, 21.6), (18, 16, 2), 1)
    for k in range(7):
        box(bm, (-7.5 + 2.5 * k, -2, 24.1), (.8, 15, 3), 1)
    for x in (-6, 6):                                       # MMCX 天线座
        cyl(bm, 1.6, 20.6, 22.4, 2, 16, x, 12)
    box(bm, (-11, 9, 21.0), (3, 4, .8), 3)
    box(bm, (0, -12.5, 21.2), (4, 2.4, 1.2), 4)             # 相机插座
    box(bm, (0, -12.2, 18.2), (5.5, 3, 1.6), 4)             # 底面 6P（接飞控）
    ribbon(bm, [-1.75 + .7 * i for i in range(6)],
           [(-12.8, 15.0), (-16.0, 15.8), (-17.2, 16.8), (-16.0, 17.8), (-12.8, 17.6)], .28, [5, 6, 7])
    finish('P09_VTX', '数字图传（含到飞控的 6P 排线）', bm,
           [M['pcb'], M['shield'], M['gold'], M['chip'], M['jst'], M['black'], M['red'], M['white']],
           ex=EX['vtx'], bevel=.15)


def loft_block(zs, hw, yf, yb, rad, rp, ns=8):
    """由一层层水平圆角矩形放样成实体：yf(z)/yb(z) 是前/后端的 y，顶部 rad 范围内四周按圆弧收进去（=顶边圆角）"""
    z1 = zs[-1]
    bm = bmesh.new()
    rings = []
    for z in zs:
        dz = z - (z1 - rad)
        ins = rad - sqrt(max(0.0, rad * rad - dz * dz)) if dz > 0 else 0.0
        w, f, b = hw - ins, yf(z) + ins, yb(z) - ins
        r = max(.8, min(rp - .6 * ins, w - .1, (b - f) / 2 - .1))
        rings.append([bm.verts.new((u, v, z)) for (u, v) in rrect(w, (b - f) / 2, r, ns, 0, (b + f) / 2)])
    fs = []
    for a, c in zip(rings, rings[1:]):
        fs += _bridge(bm, a, c)
    fs.append(bm.faces.new(rings[0][::-1]))
    fs.append(bm.faces.new(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return bm


def _ramp(z, z0, z1, v0, v1):
    return v0 if z <= z0 else v1 if z >= z1 else v0 + (v1 - v0) * (z - z0) / (z1 - z0)


def build_canopy(M):
    # 外形：前端上沿斜切（给相机让视野）、后端上沿小倒角，顶面四周 5 mm 圆角
    zs = [3, 10, 18, 22, 24.5, 26, 26.8, 27.6, 28.4, 29.1, 29.7, 30.2, 30.6, 30.85, 31]
    bm = loft_block(zs, 22.0, lambda z: _ramp(z, 24.5, 31, -30, -24), lambda z: _ramp(z, 27, 31, 30, 27), 5.0, 8.0)
    zi = [1, 10, 18, 22.5, 24.5, 25.8, 26.6, 27.4, 28.1, 28.7, 29.1, 29.4]
    cut = loft_block(zi, 20.5, lambda z: _ramp(z, 23.3, 29.4, -28.5, -23.4),
                     lambda z: _ramp(z, 25.8, 29.4, 28.5, 26.3), 3.6, 6.5)
    for x in (-6, 6):                                          # 后壁天线孔
        extrude(cut, [circle(x, 24, 2.1, 20)], 26, 34, 0, axis='Y')
    extrude(cut, [[(-5, 1), (5, 1), (5, 11), (-5, 11)]], 26, 34, 0, axis='Y')    # 后下方电源线缺口
    extrude(cut, [stadium(0, 17.5, 1.6, 1.8)], -34, -26, 0, axis='Y')            # 前壁相机线孔
    extrude(cut, [stadium(-1, 15.2, 3.4, 2.2)], -25, -18, 0, axis='X')          # 左侧 USB-C 口
    for z in (9, 12.5, 16, 19.5):                              # 右侧散热格栅
        extrude(cut, [stadium(4, z, 7, .9)], 18, 25, 0, axis='X')
    for z in (19.5, 23):                                       # 左侧格栅（让开 USB 口）
        extrude(cut, [stadium(4, z, 7, .9)], -25, -18, 0, axis='X')
    bm = boolean(bm, cut, 'DIFFERENCE')
    finish('P10_Canopy', 'TPU 机身罩', bm, [M['canopy']], ex=EX['canopy'], bevel=.6, seg=2, angle=40, smooth=40)


def build_camera(M):
    py, pz = CAM_PIVOT
    # TPU 支架：底板 + 两侧夹板 + 转轴螺丝
    bm = bmesh.new()
    box(bm, (0, -41, 4), (26, 18, 2), 0)
    for (a0, a1) in ((10, 12), (-12, -10)):
        extrude(bm, [[(-50, 5), (-34, 5), (-36, 28), (-48, 28)]], a0, a1, 0, axis='X')
    for s in (-1, 1):
        revolve(bm, [(0, 12 * s), (1.9, 12 * s), (1.9, 13.6 * s), (0, 13.6 * s)], 1, seg=16,
                closed=False, cy=py, cz=pz, axis='X')
    finish('P11_CamMount', 'TPU 相机支架', bm, [M['mount'], M['steel']], ex=EX['mount'], bevel=.5)
    # 相机：局部坐标建好，再上仰 CAM_TILT° 并移到转轴处
    bm = bmesh.new()
    box(bm, (0, 0, 0), (19, 18, 19), 0)
    lens = revolve(bm, [(0, 0), (6.4, 0), (6.4, 6.5), (5.6, 8.5), (4.3, 8.5), (4.3, 9.3), (0, 9.3)], 0,
                   closed=False)
    glass = revolve(bm, [(0, 9.3), (4.3, 9.3), (4.0, 9.9), (0, 10.2)], 1, closed=False)
    xform(bm, lens + glass, Matrix.Translation((0, -9, 0)) @ Matrix.Rotation(pi / 2, 4, 'X'))
    box(bm, (0, 9.3, -1), (8, .6, 6), 2)                     # 背面插座
    bmesh.ops.transform(bm, matrix=Matrix.Translation((0, py, pz)) @ Matrix.Rotation(radians(-CAM_TILT), 4, 'X'),
                        verts=bm.verts[:])
    pts = catmull([Vector(p) for p in ((0, -32.6, 16.8), (0, -30, 17.4), (0, -25, 19.5), (0, -18, 22.6),
                                       (0, -13.6, 22.0))], 6)
    sweep(bm, pts, .8, 3, sides=8)                             # 相机线 → 图传
    finish('P12_Camera', 'FPV 相机（上仰 %d°，含相机线）' % CAM_TILT, bm,
           [M['cam'], M['glass'], M['jst'], M['black']], ex=EX['camera'], bevel=.8, seg=2)


def build_battery(M):
    bm = bmesh.new()
    extrude(bm, [rrect(15, 28, 3, cy=1)], 31.2, 51.2, 0)
    box(bm, (0, -8, 41.2), (30.4, 12, 20.4), 1)      # 标签带
    text_into(bm, '4S 650', 7, Matrix.Translation((0, 15, 51.2)) @ Matrix.Rotation(pi / 2, 4, 'Z'), 2, .1)
    for j, x in enumerate((-1.4, 1.4)):
        pts = catmull([Vector((x, 28.5, 44)), Vector((x, 36, 44)), Vector((x, 41.5, 38)), Vector((x, 42, 32))], 6)
        sweep(bm, pts, 1.1, 3 if j else 4, sides=8)
    box(bm, (0, 42, 29.5), (8, 5, 5), 5)              # XT30 公头
    finish('P13_Battery', '4S 650mAh 锂电池', bm,
           [M['batt'], M['label'], M['white'], M['red'], M['black'], M['xt']], ex=EX['battery'], bevel=.9)
    # 绑带：在 XZ 平面绕过电池顶、机身罩两侧、机架底面一圈
    inner = [(-15.5, 49.6 + 1.6), (15.5, 49.6 + 1.6), (15.5, 31.2), (22.5, 31.2), (22.5, -.6), (-22.5, -.6),
             (-22.5, 31.2), (-15.5, 31.2)]
    outer = [(-16.5, 52.2), (16.5, 52.2), (16.5, 32.2), (23.5, 32.2), (23.5, -1.6), (-23.5, -1.6),
             (-23.5, 32.2), (-16.5, 32.2)]
    bm = bmesh.new()
    extrude(bm, [outer, inner[::-1]], -14, -2, 0, axis='Y')
    box(bm, (0, -8, 52.6), (9, 13, 1.6), 1)           # 搭扣
    finish('P14_Strap', '电池绑带', bm, [M['strap'], M['buckle']], ex=EX['strap'], bevel=.3)


def build_antennas(M):
    bm = bmesh.new()
    for s in (-1, 1):
        a = Vector((6 * s, 30.5, 24))
        b = Vector((16 * s, 46, 60))
        d = (b - a).normalized()
        L = (b - a).length
        sweep(bm, [a + d * t for t in (0, L * .5, L)], 1.1, 0, sides=10)
        sweep(bm, [a - d * 2, a + d * 4], 2.0, 1, sides=12)                # 镀金接头
        sweep(bm, [a + d * L * .58, a + d * L * .97], 1.9, 2, sides=12)    # 振子套
        coax = catmull([Vector((6 * s, y, z)) for (y, z) in ((12, 22.4), (14, 25.5), (22, 26.5), (28, 25),
                                                             (30.5, 24))], 6)
        sweep(bm, coax, .6, 0, sides=6)                                     # 同轴线 → 图传 MMCX
    finish('P15_Antennas', '图传天线 ×2（含同轴线）', bm, [M['ant'], M['gold'], M['ant_sleeve']],
           ex=EX['antenna'])


# ---------------------------------------------------------------- 场景（单位：米）
def scene_obj(name, bm, mats, coll='Field'):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection(coll).objects.link(ob)
    shade(me, 30)
    return ob


def build_field(M):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40)
    scene_obj('Ground', bm, [M['ground']])
    bm = bmesh.new()
    revolve(bm, [(0, 0), (.35, 0), (.35, .005), (0, .005)], 0, seg=64, closed=False)
    revolve(bm, [(.27, .0051), (.30, .0051), (.30, .0056), (.27, .0056)], 1, seg=64)
    text_into(bm, 'H', .3, Matrix.Translation((0, 0, .005)), 1, .0006)
    scene_obj('LandingPad', bm, [M['pad'], M['white']])
    for gx in (-GATE_X, GATE_X):         # 竞速门：开口 0.9 m，门面在 XZ 平面（飞机沿 ±Y 穿过）
        bm = bmesh.new()
        hw = .45
        sq = [Vector((gx + x, 0, H + z)) for (x, z) in ((-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw))]
        ring = []
        for i in range(4):
            a, b = sq[i], sq[(i + 1) % 4]
            ring += [a + (b - a) * t for t in (0, .5)]
        sweep(bm, ring, .028, 0, sides=10, closed=True, plane_n=Vector((0, 1, 0)))
        for x in (-hw, hw):
            sweep(bm, [Vector((gx + x, 0, 0)), Vector((gx + x, 0, H - hw))], .02, 1, sides=8)
            box(bm, (gx + x, 0, .01), (.2, .3, .02), 1)
        scene_obj('Gate_%s' % ('L' if gx < 0 else 'R'), bm, [M['gate'], M['gate_dark']])
    bm = bmesh.new()
    for k in range(10):                  # 场地四周的雪糕筒，给画面一点参照物
        a = 2 * pi * k / 10
        cx, cy = 4.2 * cos(a), 3.6 * sin(a)
        revolve(bm, [(0, 0), (.13, 0), (.13, .02), (.09, .02), (.025, .32), (0, .32)], 0, seg=24,
                closed=False, cy=cx, cz=cy)
    scene_obj('Cones', bm, [M['cone']])
    bm = bmesh.new()                     # 透明展示台：只在爆炸图段出现，托住机架底面
    revolve(bm, [(0, 0), (.06, 0), (.06, .006), (.008, .008), (.005, DISPLAY_Z - .0018),
                 (.012, DISPLAY_Z - .0018), (0, DISPLAY_Z - .0018)], 0, seg=48, closed=False)
    stand = scene_obj('DisplayStand', bm, [M['acrylic']])
    show_between(stand, F_CUT, F_END + 1)


# ---------------------------------------------------------------- 飞行轨迹与姿态
def S5(x):
    """五次平滑：起点终点的速度和加速度都是 0，分段拼接时姿态不会跳"""
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def S9(x):
    """九次平滑：连 3 阶、4 阶导数在两端都是 0。平移用它，倾角（∝ 加速度）的角加速度才不会在起步瞬间突变"""
    x = min(1.0, max(0.0, x))
    return x ** 5 * (126 + x * (-420 + x * (540 + x * (-315 + x * 70))))


def path(f):
    """飞行段第 f 帧 Drone 的位置（米）"""
    if f <= F_CLIMB[1]:
        z = Z0 + (H - Z0) * S5((f - F_CLIMB[0]) / (F_CLIMB[1] - F_CLIMB[0]))
        return Vector((0, 0, z))
    if f <= F_LOOP[1]:
        th = 2 * pi * S5((f - F_LOOP[0]) / (F_LOOP[1] - F_LOOP[0]))
        return Vector((LOOP_A * sin(th), LOOP_B * sin(th) * cos(th), H + .15 * sin(2 * th)))
    z = H + (Z0 - H) * S5((f - F_LAND[0]) / (F_LAND[1] - F_LAND[0]))
    return Vector((0, 0, z))


def demo_pos(f):
    """差速演示段：起飞 → 原地偏航 → 右移再回来（横滚）→ 前移再回来（俯仰）→ 降落"""
    z = Z0 + (DEMO_H - Z0) * (S5((f - D_UP[0]) / (D_UP[1] - D_UP[0]))
                              - S5((f - D_DOWN[0]) / (D_DOWN[1] - D_DOWN[0])))
    x = DEMO_MOVE * (S9((f - D_ROLL[0]) / D_SHIFT) - S9((f - D_ROLL[1]) / D_SHIFT))
    y = -DEMO_MOVE * (S9((f - D_PITCH[0]) / D_SHIFT) - S9((f - D_PITCH[1]) / D_SHIFT))
    return Vector((x, y, z))


def demo_yaw(f):
    return -pi / 2 + pi / 2 * (S5((f - D_YAW[0]) / 40) - S5((f - D_YAW[1]) / 40))


def kinematics(f, h=.5):
    fn = path if f < F_DEMO else demo_pos
    dt = h / FPS
    p0, p1, p2 = fn(f - h), fn(f), fn(f + h)
    return p1, (p2 - p0) / (2 * dt), (p2 - 2 * p1 + p0) / (dt * dt)


def attitude(thrust, yaw):
    """多旋翼只能沿机身 +Z 方向产生推力，所以机身 +Z 必须对准 (a + g)；机头方向由 yaw 决定"""
    z = thrust.normalized()
    h = Vector((cos(yaw), sin(yaw), 0))
    f = (h - h.dot(z) * z).normalized()
    y = -f                     # 机头是 -Y
    x = y.cross(z)
    return Matrix(((x.x, y.x, z.x), (x.y, y.y, z.y), (x.z, y.z, z.z))).to_quaternion()


def wrap(a):
    return (a + pi) % (2 * pi) - pi


def key_quat(ob, q, f, prev):
    if prev is not None and q.dot(prev) < 0:
        q = -q
    ob.rotation_quaternion = q
    ob.keyframe_insert('rotation_quaternion', frame=f)
    return q


# ---------------------------------------------------------------- 混控器：从姿态变化反推四个电机的推力
def mixer_inverse():
    """[总推力, 绕 x 力矩, 绕 y 力矩, 绕 z 力矩] = M @ [f1..f4]，求逆就得到每个电机该出多少力。
    第 i 个电机在机身坐标 (x, y) 处向上推 f：力矩 = r × F = (y·f, −x·f, 0)；
    桨转动时机身受到反扭矩 −spin·KQ·f（桨俯视逆时针转，机身就被往顺时针拧）"""
    R = [(mx * MM, my * MM, s) for _, (mx, my), s in MOTORS]
    rows = ([1.0] * 4, [y for _, y, _ in R], [-x for x, _, _ in R], [-s * KQ for _, _, s in R])
    return Matrix(rows).inverted()


def airborne(f):
    """0 = 在地上怠速（混控器不管），1 = 飞起来了（混控器接管）"""
    if f < F_DEMO:
        return S5((f - F_CLIMB[0]) / 8) * (1 - S5((f - (F_LAND[1] - 8)) / 8))
    return S5((f - D_UP[0]) / 8) * (1 - S5((f - (D_DOWN[1] - 6)) / 6))


def armed(f):
    """0 = 停桨，1 = 已解锁（至少在怠速）"""
    if f < F_DEMO:
        return S5((f - 1) / (F_CLIMB[0] - 1)) * (1 - S5((f - F_STOP[0]) / (F_STOP[1] - F_STOP[0])))
    return S5((f - F_DEMO) / (D_UP[0] - 5 - F_DEMO)) * (1 - S5((f - D_STOP[0]) / (D_STOP[1] - D_STOP[0])))


MOTION = {}     # f → dict(p, q, fi, k, e, w, dev, col)


def compute_motion():
    dt = 1.0 / FPS
    P, Q, TH = {}, {}, {}
    yaw, prev = -pi / 2, None              # 起飞前机头朝 -Y
    for f in range(1, F_CUT):
        p, v, a = kinematics(f)
        thrust = a + Vector((0, 0, G))
        if f < F_DEMO:
            sp = Vector((v.x, v.y, 0)).length
            if sp > .05:                   # 机头慢慢转向速度方向（速度越快转得越干脆）
                yaw += wrap(atan2(v.y, v.x) - yaw) * min(1.0, sp / 1.5) * .25
            y = yaw
        else:
            y = demo_yaw(f)
        q = attitude(thrust, y)
        if prev is not None and q.dot(prev) < 0:
            q = -q
        prev = q
        P[f], Q[f], TH[f] = p, q, thrust

    def seg(f):
        return 0 if f < F_DEMO else 1

    def nb(f):
        f0 = f - 1 if (f - 1) in Q and seg(f - 1) == seg(f) else f
        f1 = f + 1 if (f + 1) in Q and seg(f + 1) == seg(f) else f
        return f0, f1

    W = {}                                 # 机身坐标系下的角速度 (rad/s)
    for f in Q:
        f0, f1 = nb(f)
        if f0 == f1:
            W[f] = Vector((0, 0, 0))
            continue
        ax, ang = (Q[f0].conjugated() @ Q[f1]).to_axis_angle()
        if ang > pi:
            ang -= 2 * pi
        W[f] = Vector(ax) * ang / ((f1 - f0) * dt)
    I = Vector(INERTIA)
    TAU = {}                               # 需要的力矩 τ = I·α + ω × (I·ω)
    for f in Q:
        f0, f1 = nb(f)
        al = (W[f1] - W[f0]) / ((f1 - f0) * dt) if f1 != f0 else Vector((0, 0, 0))
        w = W[f]
        Iw = Vector((I.x * w.x, I.y * w.y, I.z * w.z))
        TAU[f] = Vector((I.x * al.x, I.y * al.y, I.z * al.z)) + w.cross(Iw)
    Minv = mixer_inverse()
    hover = MASS * G / 4
    stats = {}
    for f in Q:
        acc, n = Vector((0, 0, 0)), 0      # 5 帧平均，去掉数值微分的毛刺
        for k in range(-2, 3):
            g = f + k
            if g in TAU and seg(g) == seg(f):
                acc += TAU[g]
                n += 1
        tau = acc / n
        fi = Minv @ Vector((MASS * TH[f].length, tau.x, tau.y, tau.z))
        fi = [min(F_MAX, max(.03 * hover, x)) for x in fi]
        k, e = airborne(f), armed(f)
        mean = sum(fi) / 4
        w = [IDLE_DEG * e * (1 - k) + k * HOVER_DEG * sqrt(x / hover) for x in fi]   # 推力 ∝ 转速²
        dev = [k * (x - mean) / mean for x in fi]
        col = k * mean / F_MAX + (1 - k) * e * .08
        MOTION[f] = dict(p=P[f], q=Q[f], fi=fi, k=k, e=e, w=w, dev=dev, col=col)
        key = 'flight' if f < F_DEMO else ('yaw' if D_YAW[0] <= f < D_ROLL[0] else
                                           'roll' if D_ROLL[0] <= f < D_PITCH[0] else
                                           'pitch' if D_PITCH[0] <= f < D_DOWN[0] else 'other')
        stats[key] = max(stats.get(key, 0), max(abs(d) for d in dev))
    print('[OK] max motor difference vs mean: ' + ', '.join(f'{k} {v * 100:.0f}%' for k, v in stats.items()))


def animate_motion():
    compute_motion()
    ROOT.rotation_mode = 'QUATERNION'
    prev = None
    max_tilt = 0.0
    for f in range(1, F_CUT):
        m = MOTION[f]
        ROOT.location = m['p']
        ROOT.keyframe_insert('location', frame=f)
        prev = key_quat(ROOT, m['q'], f, prev)
        max_tilt = max(max_tilt, math.degrees((m['q'] @ Vector((0, 0, 1))).angle(Vector((0, 0, 1)))))
    # 展示台：机身水平，原地慢慢转一圈
    for f in range(F_CUT, F_END + 1):
        ROOT.location = (0, 0, DISPLAY_Z)
        ROOT.keyframe_insert('location', frame=f)
        yaw_d = -pi / 2 + 2 * pi * (f - F_CUT) / (F_END - F_CUT)
        prev = key_quat(ROOT, attitude(Vector((0, 0, 1)), yaw_d), f, prev)
    # 每个桨按自己的转速转（只转桨的局部 Z），桨盘虚影按转速淡入
    for i, (prop, disc, spin) in enumerate(PROPS):
        ang = 0.0
        for f in range(1, F_CUT):
            w = MOTION[f]['w'][i]
            ang += w
            prop.rotation_euler = (0, 0, spin * radians(ang))
            prop.keyframe_insert('rotation_euler', index=2, frame=f)
            s = min(1.0, max(0.0, (w - 18) / 18))
            disc.scale = (max(s, 1e-3),) * 3
            disc.keyframe_insert('scale', frame=f)
        disc.scale = (1e-3,) * 3
        disc.keyframe_insert('scale', frame=F_CUT)
    print(f'[OK] motion: max tilt {max_tilt:.1f} deg')


# ---------------------------------------------------------------- 画面上的电机转速条（HUD，挂在相机前面）
FONT = None
TEXT_K = 1.0


def load_font():
    """中文字幕要用系统里的中文字体；找不到就退回英文字幕"""
    global FONT
    for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyh.ttf', r'C:\Windows\Fonts\simhei.ttf',
              r'C:\Windows\Fonts\YuGothM.ttc', r'C:\Windows\Fonts\meiryo.ttc',
              '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
              '/System/Library/Fonts/PingFang.ttc'):
        if os.path.exists(p):
            try:
                FONT = bpy.data.fonts.load(p)
                print('[OK] font', p)
                break
            except Exception:
                continue
    if FONT is None:
        print('[INFO] no CJK font found, captions in English')
    # 不同字体的字号和实际字高差别很大：量一个参考字，之后按“字高”来排版
    global TEXT_K
    bm = bmesh.new()
    text_into(bm, '国' if FONT is not None else 'H', 1.0, Matrix.Identity(4), 0, 0.0, font=FONT)
    ys = [v.co.y for v in bm.verts]
    bm.free()
    TEXT_K = 1.0 / max(1e-6, max(ys) - min(ys))


def T(zh, en):
    return zh if FONT is not None else en


def emission_mat(name, hexc, strength=1.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*hexcol(hexc), 1)
    em.inputs['Strength'].default_value = strength
    if alpha < 1:
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mix = nt.nodes.new('ShaderNodeMixShader')
        mix.inputs['Fac'].default_value = alpha
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs[0])
        for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    else:
        nt.links.new(em.outputs[0], out.inputs[0])
    m.diffuse_color = (*hexcol(hexc), alpha)
    return m


def hud_obj(name, bm, mat, cam, loc):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    collection('HUD').objects.link(ob)
    ob.parent = cam
    ob.location = loc
    for attr in ('visible_shadow', 'visible_diffuse', 'visible_glossy'):
        try:
            setattr(ob, attr, False)
        except Exception:
            pass
    return ob


def hud_rect(name, w, h, mat, cam, loc, bottom=False):
    bm = bmesh.new()
    y0, y1 = (0.0, 1.0) if bottom else (-.5, .5)
    vs = [bm.verts.new((x * w, y * h, 0)) for (x, y) in ((-.5, y0), (.5, y0), (.5, y1), (-.5, y1))]
    bm.faces.new(vs)
    return hud_obj(name, bm, mat, cam, loc)


def hud_text(name, body, height, mat, cam, loc):
    """height = 一个汉字（英文时是大写字母）的实际高度 (m)"""
    bm = bmesh.new()
    text_into(bm, body, height * TEXT_K, Matrix.Identity(4), 0, 0.0, font=FONT)
    return hud_obj(name, bm, mat, cam, loc)


def show_between(ob, f0, f1):
    """只在 [f0, f1) 这段帧里显示"""
    keys = [(f0, False), (f1, True)]
    if f0 > 1:
        keys.insert(0, (1, True))
    for f, hide in keys:
        ob.hide_render = hide
        ob.hide_viewport = hide
        ob.keyframe_insert('hide_render', frame=f)
        ob.keyframe_insert('hide_viewport', frame=f)


def build_hud(cam, tag, f0, f1, captions):
    """相机前 0.5 m 处的平面：左下角是 4 个电机的推力差条 + 总推力条，上方是字幕。
    镜头 40 mm 时，这个距离上画面宽 0.45 m、高 0.253 m（720p 下 1 像素 ≈ 0.35 mm）"""
    Z = -.5
    mt = dict(bg=emission_mat(f'H_{tag}_bg', '#101418', 1, .6), white=emission_mat(f'H_{tag}_w', '#f2f4f6', 1.2),
              dim=emission_mat(f'H_{tag}_dim', '#8a949e', 1), col=emission_mat(f'H_{tag}_col', '#e8e8e8', 1.2),
              cw=emission_mat(f'H_{tag}_cw', '#ff8a2a', 1.5), ccw=emission_mat(f'H_{tag}_ccw', '#35c4be', 1.5))
    obs = [hud_rect(f'HUD_{tag}_panel', .121, .072, mt['bg'], cam, (-.1585, -.088, Z - .002)),
           hud_text(f'HUD_{tag}_title', T('推力差（满格 ±30%）', 'Thrust vs avg (full = 30%)'), .0048,
                    mt['white'], cam, (-.1585, -.0595, Z)),
           hud_text(f'HUD_{tag}_legend', T('橙 = 顺时针桨　青 = 逆时针桨', 'orange = CW   teal = CCW'), .0044,
                    mt['white'], cam, (-.1585, -.0675, Z)),
           hud_rect(f'HUD_{tag}_base', .088, .0007, mt['dim'], cam, (-.1515, -.093, Z)),
           hud_rect(f'HUD_{tag}_colbg', .009, .04, mt['dim'], cam, (-.2075, -.114, Z - .001), bottom=True),
           hud_text(f'HUD_{tag}_coll', T('总推力', 'Total'), .0040, mt['white'], cam, (-.2075, -.1195, Z))]
    col = hud_rect(f'HUD_{tag}_colbar', .007, 1.0, mt['col'], cam, (-.2075, -.114, Z), bottom=True)
    obs.append(col)
    names = (T('右前', 'FR'), T('左前', 'FL'), T('右后', 'RR'), T('左后', 'RL'))
    bars = {}
    for slot, i in enumerate((1, 0, 3, 2)):   # 画面上从左到右：左前 右前 左后 右后
        x = -.183 + slot * .021
        spin = MOTORS[i][2]
        bar = hud_rect(f'HUD_{tag}_bar_{MOTORS[i][0]}', .013, 1.0, mt['cw'] if spin < 0 else mt['ccw'], cam,
                       (x, -.093, Z + .001), bottom=True)
        bars[i] = bar
        obs.append(bar)
        obs.append(hud_text(f'HUD_{tag}_lbl_{MOTORS[i][0]}', names[i], .0044, mt['white'], cam, (x, -.1195, Z)))
    for j, (c0, c1, zh, en) in enumerate(captions):
        bg = hud_rect(f'HUD_{tag}_capbg{j}', .44, .017, mt['bg'], cam, (0, .107, Z - .002))
        tx = hud_text(f'HUD_{tag}_cap{j}', T(zh, en), .0075, mt['white'], cam, (0, .107, Z))
        show_between(bg, max(c0, f0), min(c1, f1))
        show_between(tx, max(c0, f0), min(c1, f1))
    for ob in obs:
        show_between(ob, f0, f1)
    gain = .02 / .30                      # 条形满格 = 比平均多/少 30%
    for f in range(f0, f1):
        m = MOTION[f]
        col.scale = (1, max(m['col'] * .04, 1e-4), 1)
        col.keyframe_insert('scale', index=1, frame=f)
        for i, bar in bars.items():
            h = max(-.02, min(.02, m['dev'][i] * gain))
            bar.scale = (1, h if abs(h) > 1e-4 else 1e-4, 1)
            bar.keyframe_insert('scale', index=1, frame=f)


def captions():
    """字幕：(起始帧, 结束帧, 中文, 英文)。Blender 画面和网页共用"""
    return dict(
        flight=[(F_CLIMB[0], F_LAND[1], '8 字航线：每次转弯、改方向的瞬间，四个电机的推力都不一样',
                 'Figure-8: whenever the drone turns, the four motors push differently')],
        demo=[(F_DEMO, D_YAW[0] - 8, '油门：四个电机一起加速 → 总推力大于重力 → 上升',
               'Throttle: all four speed up -> thrust > weight -> climb'),
              (D_YAW[0] - 8, D_ROLL[0] - 8, '偏航：顺时针桨和逆时针桨一快一慢 → 反扭矩不再抵消 → 机头转动',
               'Yaw: CW pair vs CCW pair -> reaction torques no longer cancel -> nose turns'),
              (D_ROLL[0] - 8, D_PITCH[0] - 8, '横滚：左右两侧一快一慢 → 机身侧倾 → 推力有了水平分量 → 横移',
               'Roll: left vs right -> body banks -> thrust tilts -> slides sideways'),
              (D_PITCH[0] - 8, D_DOWN[0], '俯仰：前后两组一快一慢 → 低头前进，抬头刹车',
               'Pitch: front vs rear -> nose down to go, nose up to brake'),
              (D_DOWN[0], F_CUT, '降落：四个电机一起减速', 'Land: all four slow down together')])


def build_huds(chase, cam_d):
    load_font()
    cap = captions()
    build_hud(chase, 'F', 1, F_DEMO, cap['flight'])
    build_hud(cam_d, 'D', F_DEMO, F_CUT, cap['demo'])


def ease(x):
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def prog(t, s):
    return ease(min(1.0, max(0.0, (t - s * .6) / .4)))


def animate_explode():
    for d in OBJS:
        ob, base, ex = d['ob'], d['base'], d['ex']
        ob.location = base * MM
        ob.keyframe_insert('location', frame=1)
        if not ex:
            continue
        for f in list(range(F_CUT - 1, F_END + 1, 2)) + [F_END]:
            if f < F_EXP[0]:
                k = lambda s: 0.0
            elif f <= F_EXP[1]:
                t = (f - F_EXP[0]) / (F_EXP[1] - F_EXP[0])
                k = lambda s, t=t: prog(t, s)
            elif f < F_ASM[0]:
                k = lambda s: 1.0
            else:
                u = min(1.0, (f - F_ASM[0]) / (F_ASM[1] - F_ASM[0]))
                k = lambda s, u=u: prog(1 - u, s)     # 装回时顺序反过来：最后拆的最先装
            v = Vector(base)
            for e in ex:
                v += Vector(e[:3]) * k(e[3])
            ob.location = v * MM
            ob.keyframe_insert('location', frame=f)


# ---------------------------------------------------------------- 相机 / 灯光 / 渲染
def look_at(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat('-Z', 'Y').to_euler()


def setup_world_and_cams():
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, F_END
    world = bpy.data.worlds.new('Sky')
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
    if bg is None:
        nt.nodes.clear()
        bg = nt.nodes.new('ShaderNodeBackground')
        out = nt.nodes.new('ShaderNodeOutputWorld')
        nt.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs['Color'].default_value = (*hexcol('#bcd4ec'), 1)
    bg.inputs['Strength'].default_value = 1.0

    sun_d = bpy.data.lights.new('Sun', 'SUN')
    sun_d.energy = 3.2
    sun_d.angle = radians(3)
    sun = bpy.data.objects.new('Sun', sun_d)
    collection('Studio').objects.link(sun)
    sun.rotation_euler = (radians(50), 0, radians(35))
    fill_d = bpy.data.lights.new('Fill', 'AREA')
    fill_d.energy = 25
    fill_d.size = 1.2
    fill = bpy.data.objects.new('Fill', fill_d)
    collection('Studio').objects.link(fill)
    fill.location = (-1.0, -1.2, DISPLAY_Z + 1.0)
    look_at(fill, (0, 0, DISPLAY_Z))

    # 跟拍相机：位置跟着 Drone 平移（不跟着转），镜头一直对准 Drone
    rig = bpy.data.objects.new('ChaseRig', None)
    collection('Studio').objects.link(rig)
    c = rig.constraints.new('COPY_LOCATION')
    c.target = ROOT
    cd = bpy.data.cameras.new('Cam_Chase')
    cd.lens = 40
    cd.clip_start = .01
    chase = bpy.data.objects.new('Cam_Chase', cd)
    collection('Studio').objects.link(chase)
    chase.parent = rig
    chase.location = (.55, -.72, .26)
    t = chase.constraints.new('TRACK_TO')       # TRACK_TO 保持地平线水平（DAMPED_TRACK 会让画面歪）
    t.target = ROOT
    t.track_axis = 'TRACK_NEGATIVE_Z'
    t.up_axis = 'UP_Y'

    # 差速演示相机：固定在起降垫右前方，镜头跟着 Drone 转
    cd = bpy.data.cameras.new('Cam_Demo')
    cd.lens = 40
    cd.clip_start = .01
    cam_d = bpy.data.objects.new('Cam_Demo', cd)
    collection('Studio').objects.link(cam_d)
    cam_d.location = (.62, -.78, DEMO_H + .28)
    t = cam_d.constraints.new('TRACK_TO')
    t.target = ROOT
    t.track_axis = 'TRACK_NEGATIVE_Z'
    t.up_axis = 'UP_Y'

    # 爆炸图相机：固定在右前上方
    cd = bpy.data.cameras.new('Cam_Explode')
    cd.lens = 50
    cd.clip_start = .01
    cam_e = bpy.data.objects.new('Cam_Explode', cd)
    collection('Studio').objects.link(cam_e)
    # 装配状态拉近看细节，拆开时跟着退远，装回时再推近
    a, e = radians(-35), radians(22)
    d = Vector((sin(-a) * cos(e), -cos(a) * cos(e), sin(e)))
    for f in range(F_CUT, F_END + 1, 2):
        k = ease(min(1.0, max(0.0, (f - F_EXP[0] + 10) / (F_EXP[1] - F_EXP[0]) * 1.4)))
        if f >= F_ASM[0]:
            k = 1 - ease(min(1.0, max(0.0, (f - F_ASM[0] - 30) / (F_ASM[1] - F_ASM[0]) * 1.3)))
        tgt = Vector((0, 0, DISPLAY_Z + .025 + .055 * k))
        cam_e.location = tgt + d * (.52 + .45 * k)
        look_at(cam_e, tgt)
        cam_e.keyframe_insert('location', frame=f)
        cam_e.keyframe_insert('rotation_euler', frame=f)

    for name, f, cam in (('飞行演示', 1, chase), ('差速原理', F_DEMO, cam_d), ('爆炸图', F_CUT, cam_e)):
        m = sc.timeline_markers.new(name, frame=f)
        m.camera = cam
    for name, f in (('起飞', F_CLIMB[0]), ('8字航线', F_LOOP[0]), ('降落', F_LAND[0]),
                    ('油门', D_UP[0]), ('偏航', D_YAW[0]), ('横滚', D_ROLL[0]), ('俯仰', D_PITCH[0]),
                    ('拆开', F_EXP[0]), ('装回', F_ASM[0])):
        sc.timeline_markers.new(name, frame=f)
    sc.camera = chase
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    try:
        vt = [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items]
        sc.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
    except Exception:
        pass
    set_engine('EEVEE')
    return chase, cam_d, cam_e


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


def viewport_defaults():
    """打开 .blend 时：材质预览、从相机看"""
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


def render_video():
    sc = bpy.context.scene
    eng = set_engine('EEVEE')
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    st = sc.render.image_settings
    try:
        st.media_type = 'VIDEO'          # Blender 5.x
    except Exception:
        pass
    st.file_format = 'FFMPEG'
    sc.render.ffmpeg.format = 'MPEG4'
    sc.render.ffmpeg.codec = 'H264'
    try:
        sc.render.ffmpeg.constant_rate_factor = 'HIGH'
    except Exception:
        pass
    sc.render.filepath = os.path.join(OUT, 'drone_demo_')
    print('[..] rendering video with', eng, '- this takes a while')
    bpy.ops.render.render(animation=True)
    for fn in os.listdir(OUT):
        if fn.startswith('drone_demo_') and fn.endswith('.mp4'):
            dst = os.path.join(OUT, 'drone_demo.mp4')
            if os.path.exists(dst):
                os.remove(dst)
            os.replace(os.path.join(OUT, fn), dst)
            print('[OK] video', dst)


# ---------------------------------------------------------------- 网页查看器（glb + 运动数据）
PART_INFO = {   # 对象名（去掉 _FR 这类后缀）→ (编号, 说明)
    'P01_Frame': (1, '3 mm 碳板：中央板 + 四条臂 + 电机座。其他零件都装在它上面。'),
    'P02_Standoffs': (2, '25.5 mm 孔距的尼龙立柱，把电调、飞控、图传三层板叠起来，中间留出走线和散热空间。'),
    'P03_Foot': (3, '落地缓冲，也让涵道底面不直接蹭地。'),
    'P04_Duct': (4, '保护桨。桨尖和内壁单边只留 1 mm，能减少桨尖涡流；外侧 8 条加强筋提高刚性。'),
    'P05_Motor': (5, '外转子无刷电机：钟罩带着桨一起转。三根相线沿机臂焊到电调焊盘。'),
    'P06_Prop': (6, '前橙后灰，一眼看出机头方向。正桨和反桨叶片是镜像的，装错位置会直接翻机。'),
    'P07_ESC': (7, '每个电机 6 颗 MOS 管组成三相桥，按飞控的指令决定电机转多快。电源线上的电容吸收电压尖峰。'),
    'P08_FC': (8, '读陀螺仪算姿态，再由混控器把“想要的力矩”分配给四个电机。左侧 USB-C 用来调参。'),
    'P09_VTX': (9, '把相机画面发给眼镜。屏蔽罩上的铝散热片负责散热，两个 MMCX 座接天线。'),
    'P10_Canopy': (10, 'TPU 机身罩：保护飞控塔，开有 USB 口、散热格栅和前后走线孔。'),
    'P11_CamMount': (11, 'TPU 软支架吸收振动；两侧转轴可以调相机仰角。'),
    'P12_Camera': (12, '上仰 15°：平飞时机身前倾，相机上仰才能拍到地平线。'),
    'P13_Battery': (13, '4S 锂电池，标称 14.8 V。XT30 插头接电调的电源线。'),
    'P14_Strap': (14, '从机架底面绕上来，把电池压在机身罩顶上。拆机第一步就是松开它。'),
    'P15_Antennas': (15, '两根天线做分集接收，同轴线接到图传的 MMCX 座。'),
}


def export_web(glb_path):
    """导出网页用的 glb（只含飞机零件）+ 运动数据，再填进网页模板"""
    sc = bpy.context.scene
    sc.frame_set(1)
    for ob in sc.objects:
        ob.select_set(False)
    for d in OBJS:
        ob = d['ob']
        key = ob.name[:-3] if ob.name[-3:] in ('_FR', '_FL', '_RR', '_RL') else ob.name
        no, desc = PART_INFO.get(key, (0, ''))
        ob['part'] = key
        ob['no'] = no
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

    p0 = MOTION[1]['p']
    rows = []
    for f in range(1, F_CUT):
        m = MOTION[f]
        p, q = m['p'] - p0, m['q']
        rows.append([round(p.x, 4), round(p.z, 4), round(-p.y, 4),
                     round(q.x, 5), round(q.z, 5), round(-q.y, 5), round(q.w, 5)]
                    + [round(w, 2) for w in m['w']] + [round(v, 4) for v in m['dev']] + [round(m['col'], 4)])
    cn = {'FR': '右前', 'FL': '左前', 'RR': '右后', 'RL': '左后'}
    cap = captions()
    data = dict(fps=FPS, p0=[p0.x, p0.z, -p0.y], frames=rows,
                seg=dict(flight=[1, F_DEMO - 1], demo=[F_DEMO, F_CUT - 1]),
                motors=[dict(tag=t, spin=s, cn=cn[t]) for t, _, s in MOTORS],
                captions={k: [[a, b, zh] for (a, b, zh, en) in v] for k, v in cap.items()},
                marks=dict(flight=[[F_CLIMB[0], '起飞'], [F_LOOP[0], '8 字'], [F_LAND[0], '降落']],
                           demo=[[D_UP[0], '油门'], [D_YAW[0], '偏航'], [D_ROLL[0], '横滚'], [D_PITCH[0], '俯仰'],
                                 [D_DOWN[0], '降落']]),
                gates=[[-GATE_X, H, 0], [GATE_X, H, 0]], H=H, display=DISPLAY_Z,
                params=dict(mass=MASS, kq=KQ, inertia=list(INERTIA), fmax=F_MAX))
    with open(os.path.join(OUT, 'motion.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    tpl = os.path.join(HERE, 'viewer_template.html')
    if not os.path.exists(tpl):
        print('[WARN] viewer_template.html not found, skip html')
        return
    with open(tpl, encoding='utf-8') as f:
        html = f.read()
    with open(glb_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    html = html.replace('"__GLB_BASE64__"', '"' + b64 + '"')
    html = html.replace('"__DRONE_JSON__"', json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    dst = os.path.join(OUT, '涵道无人机_离线版.html')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[OK] wrote', dst)


def main():
    global ROOT
    reset()
    M = make_materials()
    ROOT = bpy.data.objects.new('Drone', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .05
    collection('Drone').objects.link(ROOT)
    build_frame(M)
    build_standoffs(M)
    build_feet(M)
    build_ducts(M)
    build_motors(M)
    build_props(M)
    build_stack(M)
    build_canopy(M)
    build_camera(M)
    build_battery(M)
    build_antennas(M)
    build_field(M)
    chase, cam_d, _cam_e = setup_world_and_cams()
    animate_motion()
    animate_explode()
    build_huds(chase, cam_d)
    viewport_defaults()
    export_web(os.path.join(OUT, 'drone.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'drone.blend'))
    print('[OK] saved drone.blend')
    tris = 0
    for d in OBJS:
        d['ob'].data.calc_loop_triangles()
        tris += len(d['ob'].data.loop_triangles)
    print(f'[OK] {len(OBJS)} drone objects, {tris} triangles')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_flight.png', 240)
        render_still('render_demo.png', D_YAW[0] + 8)
        render_still('render_assembled.png', F_CUT + 5)
        render_still('render_exploded.png', F_EXP[1] + 15)
        set_engine('EEVEE')
    if DO_VIDEO:
        render_video()


main()
