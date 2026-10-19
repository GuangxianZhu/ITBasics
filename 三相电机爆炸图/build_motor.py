# -*- coding: utf-8 -*-
"""
三相鼠笼式异步电动机（YE4-132M-4，7.5 kW，4 极，36 槽 / 28 导条）—— Blender 建模脚本

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_motor.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    motor.blend           Blender 工程；按空格播放 = 爆炸动画（第 1 帧装配，第 121 帧全拆开）
    motor.glb             给网页 / 虚幻 5 用（零件独立、带中文名和爆炸数据 extras）
    三相电机_离线版.html   双击就能看的网页（需要同目录的 viewer_template.html）
    render_*.png          只有加 --render 时才渲染（Cycles，有显卡自动用显卡）

坐标约定:
    尺寸全部按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    电机轴线 = +X（轴伸端 / 驱动端 DE 朝 +X，风扇端 NDE 朝 -X），+Z 向上，底脚底面 z = -132（中心高 132）
    极坐标角 φ 的位置 = (y, z) = (r·cos φ, r·sin φ)；φ = 0 在 +Y（后方），90° 在正上方，180° 在 -Y（前方）
    所有零件原点都在世界原点，方便做爆炸动画；转子零件绕 X 轴转

兼容: 在 Blender 5.2 上测试；建模只用 bmesh，布尔 / 倒角用修改器并在内存里应用
"""
import base64
import json
import math
import os
import sys
from math import asin, atan2, cos, pi, radians, sin, sqrt

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
P = 2                 # 极对数（4 极）
NS, NR = 36, 28       # 定子槽数 / 转子导条数
ROT = -1              # 槽号增加的方向：-1 = 从轴伸端看顺时针（U1V1W1 接 L1L2L3 时顺时针转，符合 IEC 60034-8）
R_SO, R_SI = 105.0, 68.0      # 定子铁芯外径 Φ210 / 内径 Φ136
R_RO = 67.6                   # 转子外径（气隙 0.4 mm）
LC = 80.0                     # 铁芯半长（叠厚 160）
R_FB = 113.0                  # 机座本体外半径
FL = 112.0                    # 机座半长
H = 132.0                     # 中心高
SKEW = radians(10)            # 导条斜槽：一个定子齿距
LAM = 2.0                     # 图上一片叠片的厚度（真实 0.5 mm，画稀一点避免手机上出现摩尔纹）
BOX_X = -50.0                 # 接线盒中心 x
STUD_X = (-68.0, -46.0, -24.0)


def slot_ang(k):
    return radians(ROT * (5 + 10 * k))


# 单层同心式绕组：每组 3 个同心线圈；(相, 正向槽, 反向槽, 端部层)
GROUPS = [('U', (0, 1, 2), (11, 10, 9), 0), ('V', (6, 7, 8), (17, 16, 15), 1),
          ('W', (12, 13, 14), (23, 22, 21), 0), ('U', (18, 19, 20), (29, 28, 27), 1),
          ('V', (24, 25, 26), (35, 34, 33), 0), ('W', (30, 31, 32), (5, 4, 3), 1)]
SLOT_INFO = {}
for _ph, _pl, _mi, _t in GROUPS:
    for _k in _pl:
        SLOT_INFO[_k] = (_ph, 1)
    for _k in _mi:
        SLOT_INFO[_k] = (_ph, -1)


# ---------------------------------------------------------------- 场景
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


# ---------------------------------------------------------------- 材质 / 贴图
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexcol(h):
    h = h.lstrip('#')
    return tuple(_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def srgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def make_tex(name, w, h, fn):
    """生成一张小贴图（fn(u, v) -> sRGB 三元组），打包进 .blend / .glb"""
    img = bpy.data.images.new(name, w, h, alpha=False)
    px = []
    for j in range(h):
        for i in range(w):
            r, g, b = fn((i + .5) / w, (j + .5) / h)
            px += [r, g, b, 1.0]
    img.pixels[:] = px
    try:
        img.pack()
    except Exception as e:
        print('[WARN] pack image failed', name, e)
    return img


def principled(name, hexc, metal=0.0, rough=0.5, coat=0.0, coat_rough=0.15, tex=None):
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
    if tex is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = tex
        t.extension = 'REPEAT'
        t.interpolation = 'Linear'
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    m.diffuse_color = (*col, 1.0)
    m.metallic = metal
    m.roughness = rough
    return m


def make_materials():
    lam_hi, lam_lo = srgb('#b9c0ca'), srgb('#5b636e')
    tex_lam = make_tex('T_Lamination', 32, 2, lambda u, v: lam_lo if u > .82 else lam_hi)
    cu_hi, cu_lo = srgb('#d9874f'), srgb('#8a4219')
    tex_cu = make_tex('T_CopperWire', 2, 32,
                      lambda u, v: tuple(c * (.78 + .22 * sin(pi * ((v * 8) % 1)) ** .5) for c in cu_hi)
                      if (v * 8) % 1 > .12 else cu_lo)
    pe_y, pe_g = srgb('#f2c230'), srgb('#2ea44f')
    tex_pe = make_tex('T_PE_Stripe', 32, 2, lambda u, v: pe_y if (u * 2) % 1 < .5 else pe_g)
    return dict(
        paint=principled('M_Paint_Blue', '#2a5db5', .05, .4, coat=.6, coat_rough=.22),
        paint_dark=principled('M_Paint_Blue_Dark', '#24589f', .05, .45, coat=.4),
        lam=principled('M_Silicon_Steel', '#b9c0ca', .7, .38, tex=tex_lam),
        copper=principled('M_Copper_Wire', '#c8743a', .9, .32, coat=.5, tex=tex_cu),
        cage=principled('M_Cast_Copper', '#c97a45', 1, .34),
        shaft=principled('M_Shaft_Steel', '#c9cdd2', 1, .22),
        bearing=principled('M_Bearing_Steel', '#d7dadf', 1, .14),
        shield=principled('M_Bearing_Shield', '#aab0b8', 1, .3),
        wedge=principled('M_Slot_Wedge', '#d9c9a0', 0, .6),
        fan=principled('M_PP_Fan', '#2c3036', 0, .5),
        rubber=principled('M_Rubber', '#141414', 0, .72),
        zinc=principled('M_Steel_Zinc', '#b4b8be', 1, .3),
        black=principled('M_Steel_BlackOxide', '#2a2d32', .6, .4),
        board=principled('M_DMC_Board', '#7a4b2a', 0, .5),
        brass=principled('M_Brass', '#c9a250', 1, .3),
        link=principled('M_Copper_Link', '#d17a43', 1, .25),
        silk=principled('M_Label_White', '#f2f2f2', 0, .6),
        label=principled('M_Nameplate', '#d9dde2', .85, .3),
        ink=principled('M_Ink', '#16191d', 0, .5),
        gland=principled('M_PA_Gland', '#1d1f22', 0, .45),
        yel=principled('M_Wire_L1_Yellow', '#f2c230', 0, .42),
        grn=principled('M_Wire_L2_Green', '#2ea44f', 0, .42),
        red=principled('M_Wire_L3_Red', '#d8402b', 0, .42),
        pe=principled('M_Wire_PE', '#f2c230', 0, .42, tex=tex_pe),
        sleeve=principled('M_Sleeve_White', '#e9e9e6', 0, .5),
    )


# ---------------------------------------------------------------- 几何工具（bmesh，单位 mm）
def pol(r, a):
    return (r * cos(a), r * sin(a))


def loc(rho, tau, a):
    """槽 / 导条局部坐标（径向 ρ、切向 τ）→ (y, z)，τ 正方向 = φ 增加方向"""
    return (rho * cos(a) - tau * sin(a), rho * sin(a) + tau * cos(a))


def chamfer(pts, b, closed):
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
    """绕轴回转。prof = [(r, 轴向坐标), ...]"""
    pts = chamfer(prof, b, closed) if b > 0 else [(p[0], p[1]) for p in prof]

    def V(r, h, k):
        a = 2 * pi * k / seg
        if axis == 'X':
            return (h, cy + r * cos(a), cz + r * sin(a))
        if axis == 'Y':
            return (cy + r * cos(a), h, cz + r * sin(a))
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


def prism(bm, loops, w0, w1, mi, mapf):
    """通用棱柱：2D 轮廓（第 1 个外轮廓，其余为孔）在 w0..w1 之间拉伸，mapf(u, v, w) -> (x, y, z)"""
    L0 = [[bm.verts.new(mapf(u, v, w0)) for (u, v) in L] for L in loops]
    L1 = [[bm.verts.new(mapf(u, v, w1)) for (u, v) in L] for L in loops]
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


def extrude(bm, loops, a0, a1, mi, axis='X'):
    """axis='X': (u,v)→(y,z)；'Z': (u,v)→(x,y)；'Y': (u,v)→(x,z)"""
    if axis == 'X':
        return prism(bm, loops, a0, a1, mi, lambda u, v, w: (w, u, v))
    if axis == 'Z':
        return prism(bm, loops, a0, a1, mi, lambda u, v, w: (u, v, w))
    return prism(bm, loops, a0, a1, mi, lambda u, v, w: (u, w, v))


def radial_plate(bm, poly_rx, phi, t, mi):
    """(r, x) 平面里的多边形，在角度 phi 处沿切向加厚 t（风叶、加强筋）"""
    def mp(u, v, w):
        return (v, u * cos(phi) - w * sin(phi), u * sin(phi) + w * cos(phi))
    return prism(bm, [poly_rx], -t / 2, t / 2, mi, mp)


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


def rrect(cx, cy, hw, hh, r, ns=8):
    pts = []
    for (ux, uy, a0) in ((hw - r, hh - r, 0), (-(hw - r), hh - r, pi / 2),
                         (-(hw - r), -(hh - r), pi), (hw - r, -(hh - r), 1.5 * pi)):
        for k in range(ns + 1):
            a = a0 + pi / 2 * k / ns
            pts.append((cx + ux + r * cos(a), cy + uy + r * sin(a)))
    return pts


def hexagon(cx, cy, af, rot=0.0):
    R = af / sqrt(3)
    return [(cx + R * cos(rot + k * pi / 3), cy + R * sin(rot + k * pi / 3)) for k in range(6)]


def lug_poly(cx, cy, ang, r_out=5.6, L=9.0, hw=2.3):
    """接线鼻子轮廓：圆环 + 朝 ang 方向的舌片"""
    d = (cos(ang), sin(ang))
    n = (-sin(ang), cos(ang))
    b = asin(hw / r_out)
    pts = [(cx + r_out * cos(ang + b + (2 * pi - 2 * b) * i / 28), cy + r_out * sin(ang + b + (2 * pi - 2 * b) * i / 28))
           for i in range(29)]
    pts += [(cx + d[0] * L - n[0] * hw, cy + d[1] * L - n[1] * hw), (cx + d[0] * L + n[0] * hw, cy + d[1] * L + n[1] * hw)]
    return pts


def box(bm, x0, x1, y0, y1, z0, z1, mi):
    return extrude(bm, [[(y0, z0), (y1, z0), (y1, z1), (y0, z1)]], x0, x1, mi, 'X')


def frames_along(path, closed, plane_n=None):
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
        return T, N, [plane_n] * n
    ref = Vector((0, 0, 1)) if abs(T[0].z) < .9 else Vector((0, 1, 0))
    nr = T[0].cross(ref).normalized()
    N = [nr.copy()]
    for i in range(1, n):
        ax = T[i - 1].cross(T[i])
        if ax.length > 1e-9:
            nr = Matrix.Rotation(T[i - 1].angle(T[i]), 3, ax.normalized()) @ nr
        N.append(nr.copy())
    if closed:   # 把闭合回路的扭转误差平均分摊，避免接缝处扭曲
        ax = T[-1].cross(T[0])
        nl = N[-1].copy()
        if ax.length > 1e-9:
            nl = Matrix.Rotation(T[-1].angle(T[0]), 3, ax.normalized()) @ nl
        ang = atan2(nl.cross(N[0]).dot(T[0]), nl.dot(N[0]))
        for i in range(n):
            N[i] = Matrix.Rotation(ang * i / n, 3, T[i]) @ N[i]
    Bv = [T[i].cross(N[i]) for i in range(n)]
    return T, N, Bv


def sweep(bm, path, radius, mi, sides=8, closed=False, plane_n=None, uv=None, uv_len=10.0):
    """圆截面沿路径扫掠（线圈、导线、电缆）。uv=层 时写 UV：u 沿长度，v 绕圆周"""
    n = len(path)
    T, N, Bv = frames_along(path, closed, plane_n)
    rings = [[bm.verts.new(path[i] + radius * (cos(2 * pi * k / sides) * N[i] + sin(2 * pi * k / sides) * Bv[i]))
              for k in range(sides)] for i in range(n)]
    s = [0.0]
    for i in range(1, n):
        s.append(s[-1] + (path[i] - path[i - 1]).length)
    total = s[-1] + ((path[0] - path[-1]).length if closed else 0)
    fs, meta = [], []
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        a, c = rings[i], rings[j]
        sj = total if (closed and j == 0) else s[j]
        for k in range(sides):
            f = bm.faces.new((a[k], a[(k + 1) % sides], c[(k + 1) % sides], c[k]))
            fs.append(f)
            meta.append((f, {a[k]: (s[i], k), a[(k + 1) % sides]: (s[i], k + 1),
                             c[(k + 1) % sides]: (sj, k + 1), c[k]: (sj, k)}))
    if not closed:
        fs.append(bm.faces.new(rings[0][::-1]))
        fs.append(bm.faces.new(rings[-1]))
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    if uv is not None:
        for f, d in meta:
            for l in f.loops:
                ss, kk = d[l.vert]
                l[uv].uv = (ss / uv_len, kk / sides)
    return fs


def catmull(ctrl, per=8):
    Pp = [ctrl[0]] + ctrl + [ctrl[-1]]
    out = []
    for i in range(1, len(Pp) - 2):
        p0, p1, p2, p3 = Pp[i - 1], Pp[i], Pp[i + 1], Pp[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(ctrl[-1])
    return out


def loft(bm, sections, mi):
    """截面环（点数相同）依次相连，两端封口"""
    rings = [[bm.verts.new(p) for p in S] for S in sections]
    fs = []
    for i in range(len(rings) - 1):
        fs += _bridge(bm, rings[i], rings[i + 1])
    fs.append(bm.faces.new(rings[0][::-1]))
    fs.append(bm.faces.new(rings[-1]))
    for f in fs:
        f.material_index = mi
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def uv_x(bm, faces, period):
    """叠片贴图：u = x / 一片厚度"""
    uv = bm.loops.layers.uv.verify()
    for f in faces:
        for l in f.loops:
            l[uv].uv = (l.vert.co.x / period, .5)


def text_into(bm, body, size, mtx, mi, extrude_mm=0.05, align='CENTER'):
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


def _tmp_obj(bm, coll=None):
    me = bpy.data.meshes.new('tmp')
    bm.to_mesh(me)
    ob = bpy.data.objects.new('tmp', me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def _free_obj(ob):
    d = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(d)


def boolean(bm_a, cutters, op='DIFFERENCE'):
    """精确布尔（EXACT）。cutters = bmesh 或 bmesh 列表；返回新的 bmesh，输入全部释放"""
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    a = _tmp_obj(bm_a)
    bm_a.free()
    tmpc = bpy.data.collections.new('cutters')
    bpy.context.scene.collection.children.link(tmpc)
    objs = []
    for c in cutters:
        objs.append(_tmp_obj(c, tmpc))
        c.free()
    md = a.modifiers.new('bool', 'BOOLEAN')
    md.operand_type = 'COLLECTION'
    md.collection = tmpc
    md.operation = op
    md.solver = 'EXACT'
    try:
        md.use_self = True
        md.use_hole_tolerant = True
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(a.evaluated_get(dg))
    out = bmesh.new()
    out.from_mesh(me)
    for ob in objs + [a]:
        _free_obj(ob)
    bpy.data.collections.remove(tmpc)
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


# ---------------------------------------------------------------- 剖切盖面（让剖开的地方是实心的）
SLAB = dict(
    q1=lambda bm, m: box(bm, -700, 700, 0, .4, 0, 700, m),        # 四分之一剖：y=0 平面（上半）
    q2=lambda bm, m: box(bm, -700, 700, -700, 0, -.4, 0, m),      # 四分之一剖：z=0 平面（前半）
    s=lambda bm, m: box(bm, -.4, 0, -700, 700, -700, 700, m),      # 横剖面：x=0 平面
    sb=lambda bm, m: box(bm, -.4, .25, -700, 700, -700, 700, m),   # 导条 / 槽内导体的盖面略微凸出
)


def section_of(bm_src, kinds):
    parts = []
    for k in kinds:
        a = bm_src.copy()
        s = bmesh.new()
        SLAB[k](s, 0)
        r = boolean(a, s, 'INTERSECT')
        if len(r.faces):
            parts.append(r)
        else:
            r.free()
    if not parts:
        return None
    out = parts[0]
    for r in parts[1:]:
        me = bpy.data.meshes.new('t')
        r.to_mesh(me)
        out.from_mesh(me)
        bpy.data.meshes.remove(me)
        r.free()
    return out


# ---------------------------------------------------------------- 零件登记
PARTS = []
OBJS = []


def part(no, cn, jp, en, mat_txt, qty, desc, group):
    p = dict(no=no, cn=cn, jp=jp, en=en, m=mat_txt, qty=qty, desc=desc, group=group)
    PARTS.append(p)
    return p


def _mk_obj(name, bm, mats, coll, smooth):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    textured = any(m.node_tree is not None and any(n.type == 'TEX_IMAGE' for n in m.node_tree.nodes) for m in mats)
    if textured and not me.uv_layers:   # 有贴图的材质要求网格有 UV（没有就补一层全 0 的）
        me.uv_layers.new(name='UVMap')
    elif not textured:                  # 没贴图就不要 UV，文件小一半
        while me.uv_layers:
            me.uv_layers.remove(me.uv_layers[0])
    try:
        me.validate(clean_customdata=False)
    except Exception:
        pass
    ob = bpy.data.objects.new(name, me)
    collection(coll).objects.link(ob)
    shade(me, smooth)
    return ob


def finish(p, name, bm, mats, ex, bevel=0.0, seg=2, angle=50, smooth=34, extra=None, coll='Motor',
           caps=None, cutq=False, sec='clip', spin=False):
    """建好的 bmesh → 物体（倒角、缩放成米、写 extras、按需要生成剖切盖面）"""
    ob = _mk_obj(name, bm, mats, coll, smooth)
    if bevel > 0:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = bevel
        md.segments = seg
        md.limit_method = 'ANGLE'
        md.angle_limit = radians(angle)
        try:
            md.harden_normals = True
            md.clamp_overlap = True
        except Exception:
            pass
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        old = ob.data
        ob.modifiers.clear()
        ob.data = new
        new.name = name
        bpy.data.meshes.remove(old)
    exj = json.dumps([[e[0], e[2], -e[1], e[3]] for e in ex])   # glTF 坐标 (x, z, -y)，单位 mm
    meta = dict(ex=exj, cutq=int(cutq), sec=sec, spin=int(spin))
    if caps:
        src = bmesh.new()
        src.from_mesh(ob.data)
        for kind, kinds in caps:
            cb = section_of(src, kinds)
            if cb is None:
                continue
            cap = _mk_obj(f'CAP{kind}_{name}', cb, mats, 'Caps', 30)
            cap.data.transform(Matrix.Scale(MM, 4))
            cap['cap'] = kind
            cap['part_no'] = p['no']
            for k, v in meta.items():
                cap[k] = v
            for k, v in (extra or {}).items():
                cap[k] = v
            OBJS.append((cap, ex))
        src.free()
    ob.data.transform(Matrix.Scale(MM, 4))
    ob['part_no'] = p['no']
    ob['name_cn'] = p['cn']
    ob['name_jp'] = p['jp']
    ob['name_en'] = p['en']
    ob['material_spec'] = p['m']
    ob['qty'] = p['qty']
    ob['desc'] = p['desc']
    ob['group'] = p['group']
    for k, v in meta.items():
        ob[k] = v
    for k, v in (extra or {}).items():
        ob[k] = v
    OBJS.append((ob, ex))
    return ob


def bare_cap(p, name, bm, mats, ex, kind, extra=None, spin=False):
    """直接建好的盖面（槽内导体、导条在剖面上的截面）"""
    ob = _mk_obj(name, bm, mats, 'Caps', 30)
    ob.data.transform(Matrix.Scale(MM, 4))
    ob['cap'] = kind
    ob['part_no'] = p['no']
    ob['ex'] = json.dumps([[e[0], e[2], -e[1], e[3]] for e in ex])
    ob['cutq'] = 0
    ob['sec'] = 'show'
    ob['spin'] = int(spin)
    for k, v in (extra or {}).items():
        ob[k] = v
    OBJS.append((ob, ex))
    return ob


# 爆炸路线（Blender 坐标 mm，最后一个数 = 出场时刻 0~1）
EX = dict(
    lid_screw=[(0, 0, 200, .00)], lid=[(0, 0, 160, .05)], eye=[(0, 0, 110, .08)],
    fan_cover=[(-260, 0, 0, .12)], circlip=[(-150, 0, 0, .18)], fan=[(-115, 0, 0, .22)],
    nde_shield=[(-75, 0, 0, .30)], nde_bolt=[(-75, 0, 0, .30), (-55, 0, 0, .36)], washer=[(-40, 0, 0, .36)],
    vring=[(500, 0, 0, .26)], de_shield=[(460, 0, 0, .30)], de_bolt=[(460, 0, 0, .30), (60, 0, 0, .36)],
    rotor=[(300, 0, 0, .45)], key=[(300, 0, 0, .45), (0, 0, 30, .62)], box=[(0, 0, 70, .55)], static=[],
)


# ---------------------------------------------------------------- 机座
def frame_outline():
    """机座横截面外轮廓：本体圆 + 轴向散热筋 + 顶部接线盒平台 + 两侧底脚"""
    pts = []

    def body(a_deg):
        return pol(R_FB, radians(a_deg))

    def arc(a0, a1, step=2.0):
        n = max(1, int(abs(a1 - a0) / step))
        return [body(a0 + (a1 - a0) * i / n) for i in range(n)]

    def rtip(a):
        c, s = abs(cos(a)), abs(sin(a))
        return min(128 / max(c, s), 138)

    def fins(a_from, a_to):
        out, cur = [], a_from
        fa = [3.75 + 7.5 * j for j in range(-8, 50)]
        fa = [f for f in fa if a_from + 2 < f < a_to - 2]
        for f in fa:
            a = radians(f)
            wr, wt, rt = 2.6, 1.6, rtip(a)
            out += arc(cur, f - math.degrees(wr / R_FB), 2.0)
            out += [pol(R_FB, a - wr / R_FB), pol(rt - 1.2, a - wt / rt), pol(rt, a - .6 * wt / rt),
                    pol(rt, a + .6 * wt / rt), pol(rt - 1.2, a + wt / rt), pol(R_FB, a + wr / R_FB)]
            cur = f + math.degrees(wr / R_FB)
        out += arc(cur, a_to, 2.0)
        return out

    pts += fins(-28, 62)
    pts += arc(62, 62.6)
    pts += [body(62.6), (52, 118), (-52, 118), body(117.4)]
    pts += fins(117.4, 212)
    pts += [body(212), (-128, -100), (-128, -132), (-70, -132), (-62, -sqrt(R_FB ** 2 - 62 ** 2))]
    e0 = math.degrees(atan2(-sqrt(R_FB ** 2 - 62 ** 2), -62)) % 360
    e1 = 360 - (e0 - 180)
    pts += arc(e0, e1)[1:]
    pts += [(62, -sqrt(R_FB ** 2 - 62 ** 2)), (70, -132), (128, -132), (128, -100), body(328)]
    pts += arc(328, 332)[1:]
    return pts


def build_frame(M):
    p = part(1, '机座', 'フレーム', 'Frame', 'HT250 灰铸铁', 1,
             '电机的外壳兼散热器：内孔压装定子铁芯，外面一圈轴向散热筋，风扇吹出的风沿着筋吹走热量。底脚上的 4 个孔用来固定在底座上；中心高 132 mm 就是型号里的“132”。', 'housing')
    bm = bmesh.new()
    extrude(bm, [frame_outline(), circle(0, 0, R_SI + 37, 180)], -FL, FL, 0, 'X')
    lugs = []
    for a_deg in (45, 135):
        a = radians(a_deg)
        poly = [pol(110, a - radians(6)), pol(136, a - radians(3.6)), pol(139, a),
                pol(136, a + radians(3.6)), pol(110, a + radians(6))]
        for x0, x1 in ((FL - 12, FL), (-FL, -FL + 12)):
            lb = bmesh.new()
            extrude(lb, [poly], x0, x1, 0, 'X')
            lugs.append(lb)
    bm = boolean(bm, lugs, 'UNION')
    cut = []
    for s in (1, -1):
        c = bmesh.new()
        revolve(c, [(0, s * 104), (108, s * 104), (108, s * 114), (0, s * 114)], 0, seg=128)
        cut.append(c)
        for a_deg in (45, 135, 225, 315):
            c = bmesh.new()
            y, z = pol(128, radians(a_deg))
            revolve(c, [(0, s * 92), (3.4, s * 92), (3.4, s * 114), (0, s * 114)], 0, seg=20, cy=y, cz=z)
            cut.append(c)
    c = bmesh.new()
    box(c, -100, -86, -22, 22, 95, 125, 0)              # 引出线孔（通到接线盒）
    cut.append(c)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = bmesh.new()
            revolve(c, [(0, -140), (6, -140), (6, -95), (0, -95)], 0, seg=24, cy=sx * 89, cz=sy * 108, axis='Z')
            cut.append(c)
    c = bmesh.new()
    revolve(c, [(0, 100), (5.2, 100), (5.2, 125), (0, 125)], 0, seg=24, cy=60, cz=0, axis='Z')
    cut.append(c)
    bm = boolean(bm, cut, 'DIFFERENCE')
    finish(p, 'P01_Frame', bm, [M['paint']], EX['static'], bevel=1.0, angle=40,
           caps=[('q', ('q1', 'q2')), ('s', ('s',))], cutq=True)

    p = part(2, '铭牌', '銘板', 'Nameplate', '不锈钢蚀刻', 1,
             '型号 YE4-132M-4：YE4 = 超超高效率（IE4）系列，132 = 中心高，M = 中机座，4 = 4 极。额定 7.5 kW、380 V 三角形接法、14.5 A、1460 r/min。', 'housing')
    bm = bmesh.new()
    box(bm, -42, 42, -129.6, -128.4, -60, -6, 0)
    front = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # 文字朝 -Y
    lines = [('THREE-PHASE ASYNCHRONOUS MOTOR', 3.1, -12.5), ('TYPE  YE4-132M-4          IE4', 3.0, -19.5),
             ('7.5 kW    380 V    Δ    50 Hz', 3.0, -26.5), ('14.5 A    1460 r/min    cosφ 0.85', 3.0, -33.5),
             ('IP55    INS. CL. F    S1    GB/T 755', 2.6, -40.5), ('No. 2610-0732        2026.10', 2.6, -47.5)]
    for body, size, z in lines:
        text_into(bm, body, size, Matrix.Translation((0, -129.62, z)) @ front, 1, extrude_mm=.05)
    for sx in (-1, 1):
        for sz in (-1, 1):
            revolve(bm, [(0, -130.4), (1.6, -130.4), (1.9, -129.6), (0, -129.6)], 2, seg=16,
                    cy=sx * 38, cz=-33 + sz * 23.5, axis='Y')
    finish(p, 'P02_Nameplate', bm, [M['label'], M['ink'], M['zinc']], EX['static'], cutq=True)

    p = part(3, '吊环螺钉', 'アイボルト', 'EyeBolt', 'M10 碳钢 镀锌', 1,
             '起吊整台电机用。只能竖直向上吊，斜拉容易把螺纹拉坏。', 'housing')
    bm = bmesh.new()
    revolve(bm, [(0, 100), (4.6, 100), (4.6, 118), (11, 118), (11, 122.5), (0, 122.5)], 0, seg=32,
            b=.6, cy=60, cz=0, axis='Z')
    ring = [Vector((60 + 15 * cos(2 * pi * k / 48), 0, 142 + 15 * sin(2 * pi * k / 48))) for k in range(48)]
    sweep(bm, ring, 5.2, 0, sides=16, closed=True)
    finish(p, 'P03_EyeBolt', bm, [M['zinc']], EX['eye'], cutq=True, sec='hide')


# ---------------------------------------------------------------- 定子
def slot_poly(a):
    pts = [(68, -1.5), (69, -1.5), (70.6, -3.2), (82, -4.2)]
    pts += [(82 + 4.2 * cos(t), 4.2 * sin(t)) for t in [radians(-90 + 15 * i) for i in range(1, 12)]]
    pts += [(82, 4.2), (70.6, 3.2), (69, 1.5), (68, 1.5)]
    return [loc(r, t, a) for (r, t) in pts]


def bundle_poly(a):
    pts = [(71.4, -2.85), (82, -3.7)]
    pts += [(82 + 3.7 * cos(t), 3.7 * sin(t)) for t in [radians(-90 + 15 * i) for i in range(1, 12)]]
    pts += [(82, 3.7), (71.4, 2.85)]
    return [loc(r, t, a) for (r, t) in pts]


def wedge_poly(a):
    return [loc(r, t, a) for (r, t) in ((69.35, -1.75), (70.85, -3.15), (70.85, 3.15), (69.35, 1.75))]


def stator_loops():
    outer = []
    for k in range(240):
        a = 2 * pi * k / 240
        r = R_SO
        if min(abs(math.atan2(sin(a - q), cos(a - q))) for q in (radians(15 + 90 * j) for j in range(4))) < radians(.8):
            r = R_SO - 1.2
        outer.append(pol(r, a))
    angs = sorted(((slot_ang(k) % (2 * pi)), k) for k in range(NS))
    inner = []
    half = asin(1.5 / R_SI)
    for i, (a, k) in enumerate(angs):
        inner += slot_poly(a)
        a_next = angs[(i + 1) % NS][0] + (2 * pi if i == NS - 1 else 0)
        a0, a1 = a + half, a_next - half
        for j in range(1, 4):
            inner.append(pol(R_SI, a0 + (a1 - a0) * j / 4))
    return [outer, inner]


def coil_path(a, b, tier, level):
    """一个同心线圈的中心线（闭合）：a 槽 → 驱动端端部 → b 槽 → 风扇端端部 → 回到 a 槽"""
    r0 = 78.5
    ra = 79.0 if tier == 0 else 92.0
    xe = (97.0, 104.0, 111.0)[level]
    rc = 5.0
    d = math.atan2(sin(b - a), cos(b - a))
    sg = 1 if d > 0 else -1

    def P3(x, r, ang):
        return Vector((x, r * cos(ang), r * sin(ang)))

    def end(s, ang_from, ang_to):
        pts = []
        legs = [86, 89, 92] if tier == 1 else [86]
        for x in legs:
            rr = r0 + (ra - r0) * min(1, (x - 86) / 6) if tier == 1 else r0 + (ra - r0) * (x - 86) / max(1, xe - 86)
            pts.append(P3(s * x, rr, ang_from))
        dd = math.atan2(sin(ang_to - ang_from), cos(ang_to - ang_from))
        sgn = 1 if dd > 0 else -1
        da = rc / ra
        for i in range(6):
            t = pi / 2 * i / 5
            x = xe - rc + rc * sin(t)
            ang = ang_from + sgn * (da - da * cos(t))
            pts.append(P3(s * x, ra, ang))
        n = max(3, int(abs(dd - 2 * sgn * da) / radians(3)))
        for i in range(1, n):
            ang = ang_from + sgn * da + (dd - 2 * sgn * da) * i / n
            pts.append(P3(s * xe, ra, ang))
        for i in range(5, -1, -1):
            t = pi / 2 * i / 5
            x = xe - rc + rc * sin(t)
            ang = ang_to - sgn * (da - da * cos(t))
            pts.append(P3(s * x, ra, ang))
        for x in reversed(legs):
            rr = r0 + (ra - r0) * min(1, (x - 86) / 6) if tier == 1 else r0 + (ra - r0) * (x - 86) / max(1, xe - 86)
            pts.append(P3(s * x, rr, ang_to))
        return pts

    path = [P3(-86, r0, a), P3(0, r0, a)]
    path += end(1, a, b)
    path += [P3(0, r0, b)]
    path += end(-1, b, a)
    out = []
    for q in path:
        if not out or (q - out[-1]).length > 1e-6:
            out.append(q)
    if (out[0] - out[-1]).length < 1e-6:
        out.pop()
    return out


def build_stator(M):
    p = part(4, '定子铁芯', 'ステータコア', 'StatorCore', '50W470 硅钢片叠压', 1,
             '0.5 mm 厚的硅钢片叠成 160 mm 长，内圆冲有 36 个半闭口槽放绕组。用叠片而不用整块铁，是为了截断涡流、降低铁损；外圆几道焊缝把叠片固定成一体。', 'stator')
    bm = bmesh.new()
    fs = extrude(bm, stator_loops(), -LC, LC, 0, 'X')
    uv_x(bm, fs, LAM)
    finish(p, 'P04_StatorCore', bm, [M['lam']], EX['static'], smooth=30,
           caps=[('q', ('q1', 'q2')), ('s', ('s',))], cutq=True)

    p = part(5, '定子绕组', 'ステータ巻線', 'StatorWinding', 'QZY-2 漆包圆铜线，单层同心式', 18,
             '36 槽 4 极：每极每相 3 个槽，3 个同心线圈组成一组，每相 2 组，共 18 个线圈。三相在空间上依次错开 120° 电角度（4 极电机 = 60° 机械角），通入三相交流电就合成旋转磁场。', 'stator')
    uvl = None
    for gi, (ph, plus, minus, tier) in enumerate(GROUPS):
        for lev, (ka, kb) in enumerate(zip(reversed(plus), reversed(minus))):
            a, b = slot_ang(ka), slot_ang(kb)
            bm = bmesh.new()
            uvl = bm.loops.layers.uv.verify()
            sweep(bm, coil_path(a, b, tier, lev), 3.3, 0, sides=10, closed=True, uv=uvl, uv_len=12)
            for k in (ka, kb):
                fs = extrude(bm, [bundle_poly(slot_ang(k))], -86, 86, 0, 'X')
                for f in fs:
                    for l in f.loops:
                        l[uvl].uv = (l.vert.co.x / 12, (Vector(l.vert.co).yz.length - 70) / 14)
            finish(p, f'P05_Coil_{ph}{gi // 3 + 1}_{lev + 1}', bm, [M['copper']], EX['static'], smooth=60,
                   cutq=True, extra=dict(phase=ph, slots=json.dumps([[ka, 1], [kb, -1]]), tier=tier))
    for k in range(NS):
        ph, sgn = SLOT_INFO[k]
        bm = bmesh.new()
        extrude(bm, [bundle_poly(slot_ang(k))], -.4, .25, 0, 'X')
        y, z = pol(78.5, slot_ang(k))
        bare_cap(p, f'CAPs_Slot_{k:02d}', bm, [M['copper']], EX['static'], 's',
                 extra=dict(slot=k, phase=ph, sign=sgn, angle=slot_ang(k), gy=z, gz=-y))

    p = part(6, '槽楔', 'くさび', 'SlotWedge', '3240 环氧玻璃布板', 36,
             '插在槽口，把导线压在槽里，防止运行中受电磁力振动、磨破绝缘。', 'stator')
    bm = bmesh.new()
    for k in range(NS):
        extrude(bm, [wedge_poly(slot_ang(k))], -83, 83, 0, 'X')
    finish(p, 'P06_SlotWedges', bm, [M['wedge']], EX['static'], cutq=True, caps=[('s', ('s',))])

    p = part(7, '引出线', '口出線', 'Leads', 'JBQ 电机引接线 ×6', 6,
             '每相绕组的头和尾各引出一根：U1/U2、V1/V2、W1/W2，共 6 根，穿过机座上的孔接到接线板，在盒里就能改接成星形或三角形。', 'stator')
    leads = [('U', -1, 11, 2.5, 29.0), ('V', 0, 11, 7.5, 33.5), ('W', 1, 11, 12.5, 38.0),
             ('W', -1, -11, -2.5, -29.0), ('U', 0, -11, -7.5, -33.5), ('V', 1, -11, -12.5, -38.0)]
    mat_i = dict(U=0, V=1, W=2)
    bm = bmesh.new()
    for ph, col, ys, y0, yc in leads:
        xs = STUD_X[col + 1]
        t = 1 if ys > 0 else -1
        ctrl = [Vector((-96, y0, 95.5)), Vector((-93, y0, 110)), Vector((-92, y0, 122)), Vector((-88, yc * .8, 128.5)),
                Vector((-80, yc, 131.5)), Vector((xs, yc, 133.5)), Vector((xs, ys + t * 13, 134.7)), Vector((xs, ys + t * 8.6, 134.7))]
        path = catmull(ctrl, per=8)
        sweep(bm, path, 2.0, mat_i[ph], sides=10)
        tdir = (path[-1] - path[-10]).normalized()
        sweep(bm, [path[-10] - tdir * .5, path[-3]], 2.35, 3, sides=10)
        extrude(bm, [lug_poly(xs, ys, pi / 2 * t), circle(xs, ys, 3.3, 20)], 134.0, 135.4, 4, 'Z')
    finish(p, 'P07_Leads', bm, [M['yel'], M['grn'], M['red'], M['sleeve'], M['link']], EX['static'], smooth=60)


# ---------------------------------------------------------------- 转子
def bar_poly(a):
    pts = [(64.2 + 3.0 * cos(t), 3.0 * sin(t)) for t in [radians(-105 + 210 * i / 14) for i in range(15)]]
    pts += [(54.5 + 1.6 * cos(t), 1.6 * sin(t)) for t in [radians(75 + 210 * i / 8) for i in range(9)]]
    return [loc(r, t, a) for (r, t) in pts]


def build_rotor(M):
    p = part(8, '转轴', 'シャフト', 'Shaft', '45 钢 调质', 1,
             '支撑转子并输出转矩。轴伸 Φ38×80 带 10 mm 键槽（IEC 132 机座标准）；两端 Φ40 轴颈装轴承；风扇端 Φ32 装风扇。', 'rotor')
    prof = [(0, -200), (16, -200), (16, -168), (17.5, -168), (17.5, -164), (20, -164), (20, -134),
            (22.5, -134), (22.5, -82), (24, -82), (24, 82), (22.5, 82), (22.5, 133), (20, 133),
            (20, 162), (19, 162), (19, 245), (0, 245)]
    bm = bmesh.new()
    revolve(bm, prof, 0, seg=64, closed=False, b=.6)
    cut = bmesh.new()
    extrude(cut, [stadium(204, 0, 27, 5)], 14, 25, 0, 'Z')
    bm = boolean(bm, cut)
    finish(p, 'P08_Shaft', bm, [M['shaft']], EX['rotor'], caps=[('s', ('s',))], spin=True)

    p = part(9, '平键', 'キー', 'Key', '45 钢 10×8×54', 1,
             '嵌在轴伸键槽里，和联轴器或皮带轮的键槽配合传递扭矩。', 'rotor')
    bm = bmesh.new()
    extrude(bm, [stadium(204, 0, 26.5, 4.95)], 14.05, 22, 0, 'Z')
    finish(p, 'P09_Key', bm, [M['shaft']], EX['key'], bevel=.4, spin=True, sec='hide')

    p = part(10, '转子铁芯', 'ロータコア', 'RotorCore', '50W470 硅钢片叠压', 1,
             '和定子用同一种硅钢片冲出来，外圆冲有 28 个闭口槽灌注导条；8 个轴向通风孔减轻重量、帮助散热。转子外圆和定子之间只有 0.4 mm 气隙。', 'rotor')
    loops = [circle(0, 0, R_RO, 168)] + [circle(*pol(37, radians(22.5 + 45 * k)), 6, 28) for k in range(8)] + \
            [circle(0, 0, 24, 64)]
    bm = bmesh.new()
    fs = extrude(bm, loops, -LC, LC, 0, 'X')
    uv_x(bm, fs, LAM)
    finish(p, 'P10_RotorCore', bm, [M['lam']], EX['rotor'], smooth=30, caps=[('s', ('s',))], spin=True)

    p = part(11, '鼠笼（导条 + 端环）', 'かご形導体', 'SquirrelCage', '铸铜（高效电机）/ 普通电机多为铸铝', 1,
             '28 根导条两端被端环短接，形状像松鼠笼子，所以叫鼠笼。导条斜了一个齿距（斜槽），能削弱齿谐波、减小噪音和启动时的“爬行”。端环上的小风叶顺带搅动内部空气散热。', 'rotor')
    for j in range(NR):
        a0 = 2 * pi * j / NR
        secs = []
        for x in (-82, -60, -40, -20, 0, 20, 40, 60, 82):
            a = a0 + ROT * SKEW * (x / (2 * LC))
            secs.append([Vector((x, y, z)) for (y, z) in bar_poly(a)])
        bm = bmesh.new()
        loft(bm, secs, 0)
        finish(p, f'P11_Bar_{j + 1:02d}', bm, [M['cage']], EX['rotor'], smooth=45, spin=True,
               extra=dict(bar=j, angle=a0))
        cb = bmesh.new()
        extrude(cb, [bar_poly(a0)], -.4, .25, 0, 'X')
        bare_cap(p, f'CAPs_Bar_{j + 1:02d}', cb, [M['cage']], EX['rotor'], 's', spin=True,
                 extra=dict(bar=j, angle=a0))
    bm = bmesh.new()
    for s in (1, -1):
        revolve(bm, [(50, s * 80), (66.8, s * 80), (66.8, s * 92), (50, s * 92)], 0, seg=112, b=.8)
        for k in range(14):
            radial_plate(bm, [(51, s * 91), (66, s * 91), (66, s * 101), (63, s * 104), (51, s * 104)],
                         2 * pi * k / 14 + pi / 28, 4, 0)
    finish(p, 'P11_EndRings', bm, [M['cage']], EX['rotor'], bevel=.5, spin=True)


def bearing_bm(xc, d, D, B, nb, rb):
    ri, ro = d / 2, D / 2
    t = (ro - ri) * .28
    pr = (ri + ro) / 2
    bm = bmesh.new()
    revolve(bm, [(ri, xc - B / 2), (ri + t, xc - B / 2), (ri + t, xc + B / 2), (ri, xc + B / 2)], 0, seg=72, b=.8)
    revolve(bm, [(ro - t, xc - B / 2), (ro, xc - B / 2), (ro, xc + B / 2), (ro - t, xc + B / 2)], 0, seg=72, b=.8)
    for s in (-1, 1):
        x0 = xc + s * (B / 2 - .9)
        revolve(bm, [(ri + t + .2, x0 - .25), (ro - t - .1, x0 - .25), (ro - t - .1, x0 + .25), (ri + t + .2, x0 + .25)],
                1, seg=72)
        revolve(bm, [(pr - 3, x0 + s * .25), (pr + 3, x0 + s * .25), (pr + 3, x0 + s * .55), (pr - 3, x0 + s * .55)],
                1, seg=72)
    for k in range(nb):
        a = 2 * pi * k / nb
        r = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=rb)
        bmesh.ops.translate(bm, verts=r['verts'], vec=(xc, pr * cos(a), pr * sin(a)))
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = 0
    return bm


def build_bearings(M):
    p = part(12, '驱动端轴承', '負荷側軸受', 'BearingDE', '6308-2Z（40×90×23）', 1,
             '轴伸这头受皮带、联轴器的径向力大，所以选大一号的 6308。2Z = 两面钢制防尘盖，内封润滑脂。', 'bearing')
    finish(p, 'P12_BearingDE', bearing_bm(144.5, 40, 90, 23, 8, 7.0), [M['bearing'], M['shield']], EX['rotor'],
           sec='hide')
    p = part(13, '风扇端轴承', '反負荷側軸受', 'BearingNDE', '6208-2Z（40×80×18）', 1,
             '风扇端只承受转子自重和少量轴向力，用小一号的 6208；外圈在端盖里可以轴向滑动，给转轴热胀冷缩留余量。', 'bearing')
    finish(p, 'P13_BearingNDE', bearing_bm(-143, 40, 80, 18, 9, 6.0), [M['bearing'], M['shield']], EX['rotor'])

    p = part(14, '波形垫圈', 'ウェーブワッシャ', 'WaveWasher', '65Mn 弹簧钢', 1,
             '压在风扇端轴承外圈上，给一个轴向预压，消除游隙、降低噪音。', 'bearing')
    bm = bmesh.new()
    n, rings = 120, []
    for k in range(n):
        a = 2 * pi * k / n
        x0 = -153.8 + .35 * sin(3 * a)
        rings.append([bm.verts.new((x0 - .2, 35 * cos(a), 35 * sin(a))), bm.verts.new((x0 - .2, 39.6 * cos(a), 39.6 * sin(a))),
                      bm.verts.new((x0 + .2, 39.6 * cos(a), 39.6 * sin(a))), bm.verts.new((x0 + .2, 35 * cos(a), 35 * sin(a)))])
    fs = []
    for k in range(n):
        a, c = rings[k], rings[(k + 1) % n]
        for j in range(4):
            fs.append(bm.faces.new((a[j], a[(j + 1) % 4], c[(j + 1) % 4], c[j])))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    finish(p, 'P14_WaveWasher', bm, [M['shield']], EX['washer'], smooth=40)

    p = part(15, 'V 形密封圈', 'Vリング', 'VRing', 'NBR 丁腈橡胶', 1,
             '套在轴上随轴转动，唇口贴着端盖端面，挡住灰尘和水进入轴承（IP55 防护的一部分）。', 'bearing')
    bm = bmesh.new()
    revolve(bm, [(19.6, 162.2), (24, 162.2), (24, 165), (30, 168.5), (29.2, 169.6), (22.6, 167.5), (19.6, 167.5)],
            0, seg=64, b=.3)
    finish(p, 'P15_VRing', bm, [M['rubber']], EX['vring'], spin=True, sec='hide')


# ---------------------------------------------------------------- 端盖 / 风扇 / 风罩
def shield_bm(s, rb, rh):
    prof = [(22, 156), (22, 162), (rh, 162), (rh, 142), (72, 138), (102, 131), (117, 125), (121, 120), (121, 112),
            (107.8, 112), (107.8, 104), (101, 104), (101, 116), (90, 121), (66, 126), (rb + 3, 128), (rb, 129), (rb, 156)]
    bm = bmesh.new()
    revolve(bm, [(r, s * x) for (r, x) in prof], 0, seg=128, b=.8)
    for a_deg in (45, 135, 225, 315):
        a = radians(a_deg)
        poly = [pol(112, a - radians(7)), pol(132, a - radians(5)), pol(137, a - radians(2.6)), pol(138, a),
                pol(137, a + radians(2.6)), pol(132, a + radians(5)), pol(112, a + radians(7))]
        x0, x1 = (112, 120) if s > 0 else (-120, -112)
        extrude(bm, [poly], x0, x1, 0, 'X')
    for k in range(6):
        radial_plate(bm, [(rh - 1, s * 141), (72, s * 137), (102, s * 130), (117, s * 124), (117, s * 126.5),
                          (102, s * 136), (72, s * 145), (rh - 1, s * 149)], radians(30 + 60 * k), 6, 0)
    holes = []
    for a_deg in (45, 135, 225, 315):
        y, z = pol(128, radians(a_deg))
        c = bmesh.new()
        revolve(c, [(0, s * 108), (4.5, s * 108), (4.5, s * 124), (0, s * 124)], 0, seg=20, cy=y, cz=z)
        holes.append(c)
    return boolean(bm, holes)


def bolt_bm(s, a_deg):
    y, z = pol(128, radians(a_deg))
    bm = bmesh.new()
    hx = hexagon(y, z, 13, radians(a_deg))
    extrude(bm, [hx], s * 120, s * 125.5, 0, 'X')
    revolve(bm, [(0, s * 125.5), (5.8, s * 125.5), (5.8, s * 126.2), (0, s * 126.2)], 0, seg=24, cy=y, cz=z)
    revolve(bm, [(0, s * 94), (3.4, s * 94), (3.9, s * 95), (3.9, s * 120), (0, s * 120)], 0, seg=20, cy=y, cz=z)
    return bm


def build_shields(M):
    p = part(16, '驱动端端盖', '負荷側ブラケット', 'EndShieldDE', 'HT200 灰铸铁', 1,
             '轴伸那头的端盖：中间的轴承室装 6308 轴承，靠止口（凸出的那一圈）和机座对中，保证转子和定子同心、气隙均匀。', 'housing')
    finish(p, 'P16_EndShieldDE', shield_bm(1, 45, 58), [M['paint']], EX['de_shield'], bevel=.8, angle=40,
           caps=[('q', ('q1', 'q2'))], cutq=True, sec='hide')
    p = part(17, '风扇端端盖', '反負荷側ブラケット', 'EndShieldNDE', 'HT200 灰铸铁', 1,
             '结构和驱动端端盖一样，轴承室小一号（6208）。外圈装风扇和风罩。', 'housing')
    finish(p, 'P17_EndShieldNDE', shield_bm(-1, 40, 54), [M['paint']], EX['nde_shield'], bevel=.8, angle=40,
           caps=[('q', ('q1', 'q2'))], cutq=True)

    p = part(18, '端盖螺栓', 'ブラケットボルト', 'ShieldBolts', 'M8×32 8.8 级 镀锌', 8,
             '每个端盖 4 颗，对角交替拧紧，否则端盖歪斜会让气隙不均匀。', 'housing')
    for s, key in ((1, 'de_bolt'), (-1, 'nde_bolt')):
        for a_deg in (45, 135, 225, 315):
            finish(p, f'P18_ShieldBolt_{"DE" if s > 0 else "NDE"}_{a_deg}', bolt_bm(s, a_deg), [M['zinc']], EX[key],
                   bevel=.3, cutq=True, sec='hide' if s > 0 else 'clip')

    p = part(19, '风扇', '冷却ファン', 'Fan', 'PP 塑料', 1,
             '装在风扇端轴头上随轴转动，把空气从风罩网孔吸进来，沿机座散热筋吹过去。直叶片，正反转都能用。', 'cooling')
    bm = bmesh.new()
    revolve(bm, [(16.1, -197), (26, -197), (26, -168), (16.1, -168)], 0, seg=64, b=.8)
    revolve(bm, [(25, -177), (102, -177), (102, -173), (25, -173)], 0, seg=128, b=.8)
    for k in range(10):
        radial_plate(bm, [(25, -197), (96, -197), (100, -193), (100, -176), (25, -176)], 2 * pi * k / 10, 3.5, 0)
    finish(p, 'P19_Fan', bm, [M['fan']], EX['fan'], bevel=.5, spin=True)

    p = part(20, '卡簧', '止め輪', 'Circlip', '65Mn 轴用弹性挡圈 Φ32', 1,
             '卡在轴头的环槽里，挡住风扇不让它轴向滑出。', 'cooling')
    bm = bmesh.new()
    sh = []
    for t in [radians(25 + 310 * i / 40) for i in range(41)]:
        sh.append(pol(20.5, t))
    for t in [radians(335 - 310 * i / 40) for i in range(41)]:
        sh.append(pol(15.4, t))
    extrude(bm, [sh], -199.2, -198, 0, 'X')
    finish(p, 'P20_Circlip', bm, [M['black']], EX['circlip'], bevel=.2, spin=True)

    p = part(21, '风罩', 'ファンカバー', 'FanCover', '1.5 mm 钢板冲压', 1,
             '罩住风扇，防止手或异物碰到叶片；端面的格栅是进风口。', 'cooling')
    bm = bmesh.new()
    revolve(bm, [(122, -118), (123.5, -118), (123.5, -220), (121, -227.2), (116, -230), (108, -230), (108, -228.5),
                 (115.4, -228.5), (119.6, -226), (122, -220)], 0, seg=144, b=.3)
    for r0, r1 in ((90, 98), (70, 78), (50, 58), (30, 38)):
        extrude(bm, [circle(0, 0, r1, 96), circle(0, 0, r0, 96)], -230, -228.5, 0, 'X')
    extrude(bm, [circle(0, 0, 16, 48)], -230, -228.5, 0, 'X')
    for k in range(12):
        a = 2 * pi * k / 12
        sp = [loc(r, t, a) for (r, t) in ((14, -2.6), (110, -2.6), (110, 2.6), (14, 2.6))]
        extrude(bm, [sp], -229.9, -228.6, 0, 'X')
    finish(p, 'P21_FanCover', bm, [M['paint']], EX['fan_cover'], smooth=40, cutq=True)

    p = part(22, '风罩螺钉', 'カバーねじ', 'CoverScrews', 'M5 十字盘头 镀锌', 3,
             '从侧面把风罩固定在风扇端端盖的外圆上。', 'cooling')
    for k in range(3):
        a = radians(90 + 120 * k)
        bm = bmesh.new()
        revolve(bm, [(0, 117.5), (2.4, 117.5), (2.4, 123.5), (4.6, 123.5), (4.6, 125.0), (3.2, 126.4), (0, 126.4)], 0,
                seg=24, b=.2, axis='Z')
        bm.transform(Matrix.Translation((-116, 0, 0)) @ Matrix.Rotation(a - pi / 2, 4, 'X'))
        out = Vector((0, cos(a), sin(a))) * 28
        finish(p, f'P22_CoverScrew_{k + 1}', bm, [M['zinc']], EX['fan_cover'] + [(out.x, out.y, out.z, .2)], cutq=True)


# ---------------------------------------------------------------- 接线盒
def build_terminal_box(M):
    p = part(23, '接线盒座', '端子箱', 'TerminalBox', 'HT200 灰铸铁', 1,
             '装在机座顶部，底下有孔通到绕组端部，6 根引出线从这里上来。侧面装电缆格兰头。', 'tbox')
    bm = bmesh.new()
    extrude(bm, [rrect(BOX_X, 0, 55, 52, 8)], 118, 170, 0, 'Z')
    cut = []
    c = bmesh.new()
    extrude(c, [rrect(BOX_X, 0, 50, 47, 4)], 124, 171, 0, 'Z')
    cut.append(c)
    c = bmesh.new()
    box(c, -100, -86, -22, 22, 110, 130, 0)
    cut.append(c)
    c = bmesh.new()
    revolve(c, [(0, 40), (10.2, 40), (10.2, 62), (0, 62)], 0, seg=32, cy=BOX_X, cz=146, axis='Y')
    cut.append(c)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = bmesh.new()
            revolve(c, [(0, 150), (2.2, 150), (2.2, 172), (0, 172)], 0, seg=16, cy=BOX_X + sx * 47.5, cz=sy * 44.5, axis='Z')
            cut.append(c)
    bm = boolean(bm, cut)
    finish(p, 'P23_TerminalBox', bm, [M['paint']], EX['box'], bevel=.8, angle=40, caps=[('q', ('q1',))], cutq=True)

    p = part(24, '接线板', '端子台', 'TerminalBlock', 'DMC 绝缘板 + M6 黄铜接线柱', 1,
             '上排 W2 U2 V2、下排 U1 V1 W1。这台 7.5 kW 电机铭牌写 380 V Δ：3 片连接片竖着把 U1-W2、V1-U2、W1-V2 连起来，就是三角形接法；横着把 W2 U2 V2 短接，就是星形接法。', 'tbox')
    bm = bmesh.new()
    extrude(bm, [rrect(-46, 0, 38, 25, 3)], 124, 131, 0, 'Z')
    for xs in STUD_X:
        for ys in (11, -11):
            extrude(bm, [circle(xs, ys, 7, 32)], 131, 134, 0, 'Z')
            revolve(bm, [(0, 128), (3, 128), (3, 152), (2.6, 152.6), (0, 152.6)], 1, seg=24, cy=xs, cz=ys, axis='Z')
            extrude(bm, [hexagon(xs, ys, 10)], 135.4, 140.4, 2, 'Z')
            extrude(bm, [hexagon(xs, ys, 10)], 144.6, 149.6, 2, 'Z')
        extrude(bm, [rrect(xs, 0, 5.5, 17, 2.2)], 140.4, 142.4, 3, 'Z')
    for xw in (-57, -35):
        extrude(bm, [rrect(xw, 0, 1.5, 20, .8)], 131, 139, 0, 'Z')
    top = Matrix.Translation((0, 0, 131.02))
    for lab, y in (('U1     V1     W1', 20.3), ('W2     U2     V2', -20.3)):
        text_into(bm, lab, 3.4, top @ Matrix.Translation((-46, y, 0)), 4, extrude_mm=.03)
    extrude(bm, [circle(-12, 38, 4.5, 24)], 124, 127, 2, 'Z')
    revolve(bm, [(0, 124), (2.5, 124), (2.5, 136), (0, 136)], 1, seg=20, cy=-12, cz=38, axis='Z')
    extrude(bm, [hexagon(-12, 38, 8)], 128.6, 132.6, 2, 'Z')
    finish(p, 'P24_TerminalBlock', bm, [M['board'], M['brass'], M['zinc'], M['link'], M['silk']], EX['box'],
           bevel=.25, angle=40)

    p = part(25, '电源线 + 格兰头', '電源ケーブル・グランド', 'SupplyCables', 'L1 黄 / L2 绿 / L3 红 / PE 黄绿', 1,
             '三相电源 L1、L2、L3 分别接 U1、V1、W1（颜色按国标：黄、绿、红），黄绿双色线是保护接地 PE，接盒内接地螺钉。格兰头夹紧电缆并密封。任意对调两根相线，电机就反转。', 'tbox')
    bm = bmesh.new()
    revolve(bm, [(9.6, 47), (13.6, 47), (13.6, 52), (12.8, 52), (12.8, 59), (13.4, 59), (13.4, 66), (11.2, 74), (8.9, 75),
                 (8.9, 47)], 0, seg=32, b=.3, cy=BOX_X, cz=146, axis='Y')
    extrude(bm, [hexagon(BOX_X, 146, 27, pi / 6)], 52, 58, 0, 'Y')
    ends = [(STUD_X[0], 11, 1), (STUD_X[1], 11, 2), (STUD_X[2], 11, 3), (-12, 38, 4)]
    offs = [(-3.2, 3.2), (3.2, 3.2), (3.2, -3.2), (-3.2, -3.2)]
    uvl = bm.loops.layers.uv.verify()
    for (xs, ys, mi), (ox, oz) in zip(ends, offs):
        gx, gz = BOX_X + ox, 146 + oz
        if mi < 4:
            inside = [Vector((xs, ys + 8.4, 143.2)), Vector((xs, ys + 13, 143.6)), Vector((xs, ys + 17, 145)),
                      Vector((xs * .55 + gx * .45, 33, 147)), Vector((gx, 43, gz)), Vector((gx, 56, gz))]
            extrude(bm, [lug_poly(xs, ys, pi / 2), circle(xs, ys, 3.3, 20)], 142.4, 143.9, 5, 'Z')
        else:
            inside = [Vector((xs - 8.2, ys, 127.7)), Vector((xs - 13, ys, 128.6)), Vector((xs - 20, ys + 2, 133)),
                      Vector((gx * .6 + xs * .4, 41, 141)), Vector((gx, 45, gz)), Vector((gx, 56, gz))]
            extrude(bm, [lug_poly(xs, ys, pi, r_out=5.0), circle(xs, ys, 2.8, 20)], 127, 128.4, 5, 'Z')
        outside = [Vector((gx, 70, gz)), Vector((gx, 92, gz - 2)), Vector((gx, 112, gz - 20)), Vector((gx * 1.02, 130, gz - 70)),
                   Vector((gx * 1.04, 145, gz - 160)), Vector((gx * 1.06, 160, gz - 250)), Vector((gx * 1.08, 182, -129 + oz * .2)),
                   Vector((gx * 1.1, 230, -129 + oz * .2)), Vector((gx * 1.12, 300, -129 + oz * .2))]
        path = catmull(inside + outside, per=7)
        sweep(bm, path, 2.8, mi, sides=12, uv=uvl, uv_len=24)
    finish(p, 'P25_SupplyCables', bm, [M['gland'], M['yel'], M['grn'], M['red'], M['pe'], M['link']], EX['box'],
           smooth=60)

    p = part(26, '接线盒盖', '端子箱ふた', 'BoxLid', 'HT200 + 丁腈密封垫', 1,
             '盖子下面压着一圈橡胶密封垫，和格兰头一起保证接线盒防尘防水。', 'tbox')
    bm = bmesh.new()
    extrude(bm, [rrect(BOX_X, 0, 55, 52, 8)] + [circle(BOX_X + sx * 47.5, sy * 44.5, 2.6, 16) for sx in (-1, 1) for sy in (-1, 1)],
            171, 180, 0, 'Z')
    extrude(bm, [rrect(BOX_X, 0, 40, 37, 6)], 180, 181.5, 0, 'Z')
    extrude(bm, [rrect(BOX_X, 0, 54.5, 51.5, 7.5), rrect(BOX_X, 0, 50.5, 47.5, 4)], 170, 171, 1, 'Z')
    finish(p, 'P26_BoxLid', bm, [M['paint'], M['rubber']], EX['lid'], bevel=.8, angle=40,
           caps=[('q', ('q1',))], cutq=True)

    p = part(27, '盒盖螺钉', 'ふたねじ', 'LidScrews', 'M5×20 十字盘头 镀锌', 4,
             '4 个角各一颗，把盒盖压紧在密封垫上。', 'tbox')
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = BOX_X + sx * 47.5, sy * 44.5
            bm = bmesh.new()
            revolve(bm, [(0, 155), (2.4, 155), (2.4, 180), (4.6, 180), (4.6, 181.6), (3.4, 183.2), (0, 183.2)], 0,
                    seg=24, b=.2, cy=cx, cz=cy, axis='Z')
            cr = bmesh.new()
            box(cr, cx - .45, cx + .45, cy - 2.6, cy + 2.6, 182.4, 184, 0)
            box(cr, cx - 2.6, cx + 2.6, cy - .45, cy + .45, 182.4, 184, 0)
            bm = boolean(bm, cr)
            finish(p, f'P27_LidScrew_{len([1 for o, _ in OBJS if o.name.startswith("P27")]) + 1}', bm, [M['zinc']],
                   EX['lid_screw'], cutq=True)


# ---------------------------------------------------------------- 爆炸动画（.blend 里按空格播放）
def ease(x):
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def prog(t, s):
    return ease(min(1.0, max(0.0, (t - s * .6) / .4)))


def animate():
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, FRAMES + 1
    for ob, ex in OBJS:
        if ob.get('cap'):
            ob.hide_render = True
            ob.hide_viewport = True
            continue
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
    bg_cam.inputs['Color'].default_value = (*hexcol('#0d1b33'), 1)
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
        bg_env.inputs['Strength'].default_value = 0.55
    else:
        bg_env.inputs['Color'].default_value = (*hexcol('#9fb3cc'), 1)
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg_env.outputs[0], mix.inputs[1])
    nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    def light(name, kind, loc_, energy, size):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == 'AREA':
            ld.size = size
        ob = bpy.data.objects.new(name, ld)
        collection('Studio').objects.link(ob)
        ob.location = loc_
        d = Vector((0, 0, 0)) - Vector(loc_)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        return ob

    light('Key', 'AREA', (0.5, -0.9, 1.1), 32, .8)
    light('Rim', 'AREA', (-0.9, 0.8, 0.5), 24, .8)
    cam_d = bpy.data.cameras.new('Camera')
    cam_d.lens = 60
    cam_d.clip_start = .01
    cam = bpy.data.objects.new('Camera', cam_d)
    collection('Studio').objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    items = [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items]
    sc.view_settings.view_transform = 'AgX' if 'AgX' in items else 'Filmic'
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


def frame_camera(cam, frame, dist, target, elev=22, azim=-35):
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
        ob.hide_viewport = False
        ob.hide_set(False)
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
    dst = os.path.join(OUT, '三相电机_离线版.html')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[OK] wrote', dst)


def main():
    reset()
    M = make_materials()
    build_frame(M)
    build_stator(M)
    build_rotor(M)
    build_bearings(M)
    build_shields(M)
    build_terminal_box(M)
    with open(os.path.join(OUT, 'parts.json'), 'w', encoding='utf-8') as f:
        json.dump(PARTS, f, ensure_ascii=False, indent=1)
    cam = setup_render()
    animate()
    glb = os.path.join(OUT, 'motor.glb')
    export_glb(glb)
    write_html(glb)
    for ob, _ in OBJS:
        if ob.get('cap'):
            ob.hide_set(True)
            ob.hide_viewport = True
    frame_camera(cam, 1, 1.5, (0, 0, 20))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'motor.blend'))
    print('[OK] saved motor.blend')
    if DO_RENDER:
        render(cam, 'render_assembled.png', 1, 1.45, (10, 0, 15))
        render(cam, 'render_exploded.png', FRAMES + 1, 2.6, (60, 0, 60), elev=20, azim=-28)
    tris = 0
    for o, _ in OBJS:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    print(f'[OK] {len(OBJS)} objects, {tris} triangles')


main()
