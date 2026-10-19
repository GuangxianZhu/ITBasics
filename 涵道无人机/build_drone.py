# -*- coding: utf-8 -*-
"""
原创 3 寸涵道穿越机（cinewhoop）—— Blender 建模 + 飞行演示 + 爆炸图

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_drone.py -- [输出目录] [--render] [--video]

输出（默认在 output/ 下）:
    drone.blend        Blender 工程，按空格播放：
                         第 1~449 帧   飞行演示（起飞 → 8 字穿过两个竞速门 → 降落）
                         第 450~750 帧 爆炸图（转台展示：拆开 → 停留 → 装回）
                       时间线上的标记（Marker）会自动切换相机
    render_*.png       加 --render 时用 Cycles 渲染 3 张预览图
    drone_demo.mp4     加 --video 时用 EEVEE 把整段动画渲染成视频（1280×720）

坐标约定:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    机头朝 -Y（Blender 前视图 Numpad1 正对机头），+Z 向上，+X 是机身右侧
    所有零件都挂在空物体 Drone 下面：飞行动画只动 Drone，爆炸动画只动零件的相对位置

兼容: Blender 4.2 ~ 5.x
"""
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
F_CUT = 450              # 切到展示台
F_EXP = (460, 580)       # 拆开
F_ASM = (610, 730)       # 装回
F_END = 750

H = 1.30                 # 巡航高度 (m)
Z0 = 0.009               # 停在起降垫上时 Drone 原点高度（脚垫 4 mm + 垫子 5 mm）
LOOP_A, LOOP_B = 2.6, 2.4    # 8 字航线尺寸 (m)
DISPLAY_Z = 0.22         # 爆炸展示时悬停高度 (m)
GATE_X = LOOP_A          # 两个竞速门放在 x = ±A
IDLE_DEG = 22.0          # 怠速：桨每帧转多少度
HOVER_DEG = 42.0         # 悬停：桨每帧转多少度（30 fps 下故意取“看得出在转”的值，真实转速快得多）


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


def text_into(bm, body, size, mtx, mi, extrude=0.05):
    """Blender 内置字体 → 网格，并入 bm（mtx 把文字局部 XY 平面放到世界里）"""
    cu = bpy.data.curves.new('txt', 'FONT')
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
        d, _n = diag(mx, my)
        bm = bmesh.new()
        revolve(bm, prof, 0, seg=96, closed=True, b=.35)
        c = -d * 37.75     # 涵道底法兰压在机臂末端，用两颗螺丝固定
        for k in (-2.5, 2.5):
            p = c + _n * k
            cyl(bm, 1.3, 4.5, 5.4, 1, 12, p.x, p.y)
        ex = [(d.x * 45, d.y * 45, 0, .72)]
        finish(f'P04_Duct_{tag}', '涵道（桨保护圈）', bm, [M['duct'], M['steel']], base=(mx, my, 0), ex=ex,
               smooth=40)


def build_motors(M):
    for tag, (mx, my), _ in MOTORS:
        d, n = diag(mx, my)
        bm = bmesh.new()
        revolve(bm, [(0, 3.0), (9.0, 3.0), (9.0, 5.0), (8.2, 5.5), (0, 5.5)], 0, closed=False)   # 底座
        revolve(bm, [(0, 5.7), (9.0, 5.7), (9.0, 12.6), (8.0, 14.0), (2.2, 14.0), (2.2, 14.6), (0, 14.6)],
                0, closed=False)                                                                     # 外转子钟罩
        revolve(bm, [(9.0, 7.2), (9.15, 7.2), (9.15, 9.6), (9.0, 9.6)], 1, closed=True)              # 色环
        cyl(bm, .75, 14.6, 20.6, 2, 16)                                                               # 轴
        for k in range(6):                                                                            # 顶部散热窗
            a = k * pi / 3 + pi / 6
            box(bm, (5.2 * cos(a), 5.2 * sin(a), 14.02), (3.2, 1.6, .1), 3)
        # 三根相线沿机臂走到电调；越过涵道法兰时抬高一点
        for j, k in enumerate((-.9, 0, .9)):
            off = n * k
            ctrl = [-d * 9 + off, -d * 22 + off, -d * 33 + off, -d * 37.5 + off, -d * 42 + off,
                    -d * 50 + off, -d * 55 + off]
            zs = [3.8, 3.8, 3.8, 5.3, 3.8, 3.8, 6.8]
            pts = catmull([Vector((p.x, p.y, z)) for p, z in zip(ctrl, zs)], 6)
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


def build_stack(M):
    # 电调（四合一 ESC）
    bm = bmesh.new()
    board(bm, 16, 5.0, 6.6, 0)
    for (x, y) in ((-8, -4), (-8, 4), (8, -4), (8, 4), (-4, -8), (4, -8), (-4, 8), (4, 8)):
        box(bm, (x, y, 7.1), (4, 4, 1), 1)
    box(bm, (0, 0, 7.0), (4, 4, .8), 1)
    for k in range(4):                 # 电机线焊盘
        a = pi / 4 + k * pi / 2
        box(bm, (14 * cos(a) * .92, 14 * sin(a) * .92, 6.7), (2.4, 2.4, .2), 2)
    # 电源线 + XT30 母头
    for j, x in enumerate((-1.4, 1.4)):
        pts = catmull([Vector((x, 14, 6.8)), Vector((x, 26, 7)), Vector((x, 36, 10)), Vector((x, 42, 17)),
                       Vector((x, 42, 20))], 6)
        sweep(bm, pts, 1.1, 3 if j else 4, sides=8)
    box(bm, (0, 42, 24), (8, 5, 6), 5)
    finish('P07_ESC', '四合一电调（含电源线、XT30 母头）', bm,
           [M['pcb'], M['chip'], M['gold'], M['red'], M['black'], M['xt']], ex=EX['esc'], bevel=.15)
    # 飞控
    bm = bmesh.new()
    board(bm, 16, 12.0, 13.6, 0)
    box(bm, (0, 1, 14.2), (7, 7, 1.2), 1)       # MCU
    box(bm, (0, -8, 14.0), (3, 3, .8), 1)       # 陀螺仪
    box(bm, (7, 7, 14.0), (3, 2, .8), 1)        # BEC
    box(bm, (-10.5, 0, 15.1), (3, 7, 3), 2)     # JST 插座
    box(bm, (10.5, 0, 15.1), (3, 6, 3), 2)
    box(bm, (0, 13.5, 13.9), (1.4, 1.0, .6), 3)  # LED
    finish('P08_FC', '飞控', bm, [M['pcb'], M['chip'], M['jst'], M['accent']], ex=EX['fc'], bevel=.15)
    # 图传
    bm = bmesh.new()
    board(bm, 15, 19.0, 20.6, 0)
    box(bm, (0, -2, 22.1), (18, 16, 3), 1)      # 屏蔽罩
    for x in (-6, 6):                           # MMCX 天线座
        cyl(bm, 1.6, 20.6, 22.4, 2, 16, x, 12)
    box(bm, (-11, 9, 21.0), (3, 4, .8), 3)
    finish('P09_VTX', '数字图传', bm, [M['pcb'], M['shield'], M['gold'], M['chip']], ex=EX['vtx'], bevel=.15)


def build_canopy(M):
    bm = bmesh.new()
    extrude(bm, [rrect(22, 30, 8, 12)], 3.0, 31.0, 0)
    cut = bmesh.new()
    extrude(cut, [rrect(20.6, 28.6, 6.6, 12)], 1.0, 29.6, 0)
    for x in (-6, 6):                                          # 后壁天线孔
        extrude(cut, [circle(x, 24, 2.1, 20)], 26, 34, 0, axis='Y')
    for z in (11, 17):                                         # 侧面散热槽
        for (a0, a1) in ((18, 25), (-25, -18)):
            extrude(cut, [stadium(4, z, 7, 1.4)], a0, a1, 0, axis='X')
    bm = boolean(bm, cut, 'DIFFERENCE')
    finish('P10_Canopy', 'TPU 机身罩', bm, [M['canopy']], ex=EX['canopy'], bevel=.9, seg=3, angle=40)


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
    bmesh.ops.transform(bm, matrix=Matrix.Translation((0, py, pz)) @ Matrix.Rotation(radians(-CAM_TILT), 4, 'X'),
                        verts=bm.verts[:])
    finish('P12_Camera', 'FPV 相机（上仰 %d°）' % CAM_TILT, bm, [M['cam'], M['glass']], ex=EX['camera'],
           bevel=.8, seg=2)


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
    finish('P15_Antennas', '图传天线 ×2', bm, [M['ant'], M['gold'], M['ant_sleeve']], ex=EX['antenna'])


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


# ---------------------------------------------------------------- 飞行轨迹与姿态
def S5(x):
    """五次平滑：起点终点的速度和加速度都是 0，分段拼接时姿态不会跳"""
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def path(f):
    """第 f 帧 Drone 的位置（米）"""
    if f <= F_CLIMB[1]:
        z = Z0 + (H - Z0) * S5((f - F_CLIMB[0]) / (F_CLIMB[1] - F_CLIMB[0]))
        return Vector((0, 0, z))
    if f <= F_LOOP[1]:
        th = 2 * pi * S5((f - F_LOOP[0]) / (F_LOOP[1] - F_LOOP[0]))
        return Vector((LOOP_A * sin(th), LOOP_B * sin(th) * cos(th), H + .15 * sin(2 * th)))
    z = H + (Z0 - H) * S5((f - F_LAND[0]) / (F_LAND[1] - F_LAND[0]))
    return Vector((0, 0, z))


def kinematics(f, h=.5):
    dt = h / FPS
    p0, p1, p2 = path(f - h), path(f), path(f + h)
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


def animate_flight():
    ROOT.rotation_mode = 'QUATERNION'
    yaw = -pi / 2              # 起飞前机头朝 -Y
    prev_q = None
    max_tilt, max_v = 0.0, 0.0
    omega = []                 # 每帧桨的角速度（度/帧）
    for f in range(1, F_CUT):
        p, v, a = kinematics(f)
        thrust = a + Vector((0, 0, G))
        sp = Vector((v.x, v.y, 0)).length
        if sp > .05:           # 机头慢慢转向速度方向（速度越快转得越干脆）
            yaw += wrap(atan2(v.y, v.x) - yaw) * min(1.0, sp / 1.5) * .25
        ROOT.location = p
        ROOT.keyframe_insert('location', frame=f)
        prev_q = key_quat(ROOT, attitude(thrust, yaw), f, prev_q)
        if F_CLIMB[0] <= f <= F_LAND[1]:
            max_tilt = max(max_tilt, math.degrees(thrust.angle(Vector((0, 0, 1)))))
            max_v = max(max_v, v.length)
        # 推力 ∝ 转速²，所以转速 ∝ √(需要的推力)
        w_fly = HOVER_DEG * sqrt(thrust.length / G)
        if f < F_CLIMB[0]:
            w = IDLE_DEG * S5((f - 1) / (F_CLIMB[0] - 1))
        elif f <= F_LAND[1]:
            k = S5((f - F_CLIMB[0]) / 8) * (1 - S5((f - (F_LAND[1] - 8)) / 8))
            w = IDLE_DEG + (w_fly - IDLE_DEG) * k
        else:
            w = IDLE_DEG * (1 - S5((f - F_STOP[0]) / (F_STOP[1] - F_STOP[0])))
        omega.append(w)
    # 展示台：机身水平，原地慢慢转一圈
    for f in range(F_CUT, F_END + 1):
        ROOT.location = (0, 0, DISPLAY_Z)
        ROOT.keyframe_insert('location', frame=f)
        yaw_d = -pi / 2 + 2 * pi * (f - F_CUT) / (F_END - F_CUT)
        prev_q = key_quat(ROOT, attitude(Vector((0, 0, 1)), yaw_d), f, prev_q)
    # 桨的转动（只转桨的局部 Z）和桨盘虚影
    for prop, disc, spin in PROPS:
        ang = 0.0
        for f in range(1, F_CUT):
            ang += omega[f - 1]
            prop.rotation_euler = (0, 0, spin * radians(ang))
            prop.keyframe_insert('rotation_euler', index=2, frame=f)
            s = min(1.0, max(0.0, (omega[f - 1] - 18) / 18))
            disc.scale = (max(s, 1e-3),) * 3
            disc.keyframe_insert('scale', frame=f)
        disc.scale = (1e-3,) * 3
        disc.keyframe_insert('scale', frame=F_CUT)
    print(f'[OK] flight: max tilt {max_tilt:.1f} deg, max speed {max_v:.1f} m/s')


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

    for name, f, cam in (('飞行演示', 1, chase), ('爆炸图', F_CUT, cam_e)):
        m = sc.timeline_markers.new(name, frame=f)
        m.camera = cam
    for name, f in (('起飞', F_CLIMB[0]), ('8字航线', F_LOOP[0]), ('降落', F_LAND[0]),
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
    return chase, cam_e


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
    setup_world_and_cams()
    animate_flight()
    animate_explode()
    viewport_defaults()
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
        render_still('render_flight.png', 178)
        render_still('render_takeoff.png', 45)
        render_still('render_assembled.png', F_CUT + 5)
        render_still('render_exploded.png', 595)
        set_engine('EEVEE')
    if DO_VIDEO:
        render_video()


main()
