# -*- coding: utf-8 -*-
"""
直列四缸汽油发动机（通用 2.0L 自然吸气 DOHC 16 气门）—— Blender 脚本建模 + 原理爆炸图

不对应某一款车：尺寸按这个排量级常见的数值取（缸径 86 × 行程 86、缸心距 93、连杆 139、甲板高 212），
零件树和接口参数表见 README.md。按 VR 里好抓来分：一个零件（或一组一起拆下的小件）= 一个节点 = 一个抓取单元，
共 48 个可抓单元 + 缸体（底座，不动）。

用法（一般不用手动跑，双击 启动.bat 即可）:
    blender --background --factory-startup --python build_engine.py -- [输出目录] [--render]

输出（默认在 output/ 下）:
    engine.blend   Blender 工程，按空格播放：第 1~120 帧按拆机顺序拆开，第 150~270 帧反顺序装回
    engine.glb     glTF 模型（单位米，每个单元一个节点，extras 里有零件号、中文名、材料、作用、爆炸路线），
                   虚幻工程 MyVRToyBox 的 Tools/import_model.py 直接导入（MODEL_NAME=Engine）
    parts.json     零件表
    render_*.png   加 --render 时用 Cycles 渲染装配 / 爆炸预览图

坐标约定（和接口参数表一致）:
    零件尺寸按 毫米 写，建完统一缩放成米（1 Blender 单位 = 1 m）
    原点在曲轴中心线上、2 / 3 缸中间；+X = 正时端（发动机前端），+Z 向上，-Y = 进气侧（放在桌上时朝向玩家）
    1 缸在正时端：四个缸中心 X = +139.5、+46.5、-46.5、-139.5
    分型面高度：油底壳底 Z = -220（贴桌面）、油底壳 / 主轴承梁 -70、主轴承梁 / 缸体 0（曲轴中心线）、
               缸体顶面 212、缸垫 212~215、缸盖 215~350（350 是凸轮轴中心线）、气门室盖顶 425
    曲轴摆在 1、4 缸上止点（1 缸压缩上止点），2、3 缸在下止点
    所有零件都直接按装配位置建模（物体原点都在世界原点），爆炸动画只动物体位置
    导出前整体左右镜像（X 取反，见 MIRROR_X）：桌上进气侧朝玩家时，正时端落在玩家左手边（右前方是触屏）。
    脚本里的尺寸和爆炸路线都照上面的坐标写，镜像只在 finish() 里做一次；气门室盖上的字提前反写了

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


# ---------------------------------------------------------------- 表面贴图（可平铺的噪声，numpy 现算）
# 真实零件的表面不是一个颜色、一个粗糙度：砂铸铝有颗粒，加工面有刀纹，抛光面有手印。全身一个值 = "刚出模的塑料玩具"。
# 做法：每一类表面（铸造、锻造、加工、光面、注塑、锈）生成一套灰度贴图，材质再乘上自己的颜色和粗糙度。
# glTF 也是"贴图 × 系数"（baseColorFactor、roughnessFactor、metallicFactor），所以同一套贴图能给很多材质共用，
# 导出时 Blender 认得 Mix(相乘) / Math(相乘) 这两种节点，自动换成系数。
TEX_N = 512            # 贴图边长（像素）
TEX_MM = 128.0         # 一张贴图铺多大（毫米），0.25 mm / 像素。UV 用盒式投影（box_uv），所有零件纹理大小一致
TEX = {}               # 类别 → (底色图, 粗糙度图, 法线图或 None, 底色均值, 粗糙度均值)


def _noise(n, beta, seed, stretch=1.0):
    """可平铺的 1/f^beta 噪声：白噪声在频域里按频率衰减再变回来。FFT 天生是周期的，所以贴图四边接得上。
    beta 大 = 大块斑驳，beta 小 = 细颗粒；stretch > 1 时沿 u 方向拉长（刀纹）。均值 0、标准差 1"""
    import numpy as np
    rng = np.random.default_rng(seed)
    F = np.fft.fft2(rng.standard_normal((n, n)))
    fu = np.fft.fftfreq(n)[None, :] * stretch
    fv = np.fft.fftfreq(n)[:, None]
    f = np.sqrt(fu * fu + fv * fv)
    f[0, 0] = 1.0
    F *= f ** -beta
    F[0, 0] = 0
    a = np.real(np.fft.ifft2(F))
    return (a - a.mean()) / a.std()


# 类别：底色乘数 = 1 - 斑驳 - 颗粒，粗糙度乘数 = 基准 + 斑驳 + 颗粒；blot / grain 是两层噪声的 beta（越小越细）。
# bump = 法线图强度：只给铸造、锻造、锈这三种"摸得出颗粒"的表面，而且压得很低（法面平均只偏 3° ~ 5°）——
# 砂铸的颗粒不到 0.5 mm，太强就成了水泥墙；VR 里细碎的法线还会在高光上闪（镜面走样），所以加工面、注塑件只靠粗糙度变化
SURFACES = dict(
    cast=dict(base=(.035, .03), rough=(.07, .08), bump=.12, blot=1.8, grain=.3),        # 砂铸铝：细颗粒 + 大块明暗
    forged=dict(base=(.06, .03), rough=(.09, .05), bump=.1, blot=1.6, grain=.5),        # 锻件、铸铁：氧化皮，斑驳更明显
    machined=dict(base=(.02, .015), rough=(.03, .09), bump=0, blot=1.6, grain=.8, stretch=14),   # 车 / 磨削面：一道道刀纹
    smooth=dict(base=(.015, .005), rough=(.12, .02), bump=0, blot=2.0, grain=.6),       # 抛光钢、喷漆面：只有淡淡的手印
    molded=dict(base=(.02, .01), rough=(.05, .05), bump=0, blot=1.8, grain=.3),         # 注塑件、橡胶：细皮纹（只在粗糙度上）
    rust=dict(base=(.14, .06), rough=(.1, .05), bump=.18, blot=1.5, grain=.6),          # 排气歧管：烧过的铸铁，颜色斑驳
)


def _image(name, rgb, srgb):
    import numpy as np
    n = rgb.shape[0]
    img = bpy.data.images.new(name, n, n, alpha=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'    # 先设色彩空间：之后再改会把生成的图重置成黑的
    px = np.ones((n, n, 4), dtype=np.float32)
    px[..., :3] = rgb
    img.pixels.foreach_set(px.ravel())
    img.update()
    img.file_format = 'PNG'
    img.pack()                      # 打进 .blend，glb 导出时也按 PNG 嵌进去
    return img


def surface_tex(kind):
    """生成（第一次用到时）一类表面的贴图"""
    if kind in TEX:
        return TEX[kind]
    import numpy as np
    s = SURFACES[kind]
    seed = sorted(SURFACES).index(kind) * 10
    blot = _noise(TEX_N, s['blot'], seed)
    grain = _noise(TEX_N, s['grain'], seed + 1, s.get('stretch', 1.0))
    base = np.clip(1 - .05 - s['base'][0] * blot - s['base'][1] * grain, 0, 1)
    rough = np.clip(.8 + s['rough'][0] * blot + s['rough'][1] * grain, 0, 1)
    srgb = np.where(base <= .0031308, base * 12.92, 1.055 * base ** (1 / 2.4) - .055)    # 存的是 sRGB，乘的时候按线性
    base_img = _image(f'T_{kind}_Base', np.repeat(srgb[..., None], 3, 2), True)
    orm = np.stack([np.ones_like(rough), rough, np.ones_like(rough)], -1)                 # R 不用、G 粗糙度、B 金属度（glTF 约定）
    orm_img = _image(f'T_{kind}_ORM', orm, False)
    nrm_img = None
    if s['bump'] > 0:
        h = grain + blot * .2
        dx = np.roll(h, -1, 1) - np.roll(h, 1, 1)                  # roll = 周期边界，法线图也能平铺
        dy = np.roll(h, -1, 0) - np.roll(h, 1, 0)
        k = .5 / np.sqrt((dx * dx + dy * dy).mean())               # 斜率归一化：图里法线平均偏 ~27°，材质里再乘 bump
        dx, dy = dx * k, dy * k
        nv = np.stack([-dx, -dy, np.ones_like(h)], -1)
        nv /= np.linalg.norm(nv, axis=-1, keepdims=True)
        nrm_img = _image(f'T_{kind}_Normal', nv * .5 + .5, False)
    TEX[kind] = (base_img, orm_img, nrm_img, float(base.mean()), float(rough.mean()))
    return TEX[kind]


def pbr(name, hexc, metal, rough, kind):
    """贴图材质：底色 = 贴图 × 颜色，粗糙度 = 贴图 G × 系数，金属度 = 贴图 B（全白）× 系数，法线图按类别给强度"""
    base_img, orm_img, nrm_img, base_mean, rough_mean = surface_tex(kind)
    m = principled(name, hexc, metal, rough)
    nt, b = _bsdf(m)
    N, L = nt.nodes, nt.links
    col = hexcol(hexc)
    tb = N.new('ShaderNodeTexImage')
    tb.image = base_img
    mix = N.new('ShaderNodeMix')
    mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    mix.inputs[7].default_value = (*[min(1.0, c / base_mean) for c in col], 1.0)      # B（颜色）
    L.new(tb.outputs['Color'], mix.inputs[6])                                         # A（贴图）
    L.new(mix.outputs[2], b.inputs['Base Color'])
    to = N.new('ShaderNodeTexImage')
    to.image = orm_img
    sep = N.new('ShaderNodeSeparateColor')
    L.new(to.outputs['Color'], sep.inputs[0])
    for ch, val, sock in ((1, min(1.0, rough / rough_mean), 'Roughness'), (2, metal, 'Metallic')):
        mul = N.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = val
        L.new(sep.outputs[ch], mul.inputs[0])
        L.new(mul.outputs[0], b.inputs[sock])
    if nrm_img is not None:
        tn = N.new('ShaderNodeTexImage')
        tn.image = nrm_img
        nm = N.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = SURFACES[kind]['bump']
        L.new(tn.outputs['Color'], nm.inputs['Color'])
        L.new(nm.outputs['Normal'], b.inputs['Normal'])
    return m


def box_uv(bm):
    """盒式投影 UV：每个面按法线最接近的那根轴，取另外两个坐标（毫米）÷ TEX_MM。
    所有零件同一个纹理密度；圆柱面上换轴的地方有接缝，纹理对比很淡，看不太出来"""
    uv = bm.loops.layers.uv.new('UVMap')
    bm.normal_update()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        a, c = ((1, 2), (0, 2), (0, 1))[ax]
        for lp in f.loops:
            lp[uv].uv = (lp.vert.co[a] / TEX_MM, lp.vert.co[c] / TEX_MM)


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



# ---------------------------------------------------------------- 零件信息（信息牌上显示的三行：中文名、材料、作用）
INFO = {
    1: ('缸体', '铝合金压铸 + 铸铁缸套',
        '发动机的骨架。4 个气缸孔、包着气缸的冷却水套、通向各轴承的油道都铸在里面；下半部分是曲轴箱，5 道隔板托住曲轴。'
        '拆发动机时它不动，其他零件都从它上面拆下来。'),
    2: ('主轴承梁（下曲轴箱）', '铝合金压铸 · 5 道主轴承盖连成一体',
        '曲轴夹在缸体和它之间：上下各一片轴瓦，10 颗 M10 螺栓拉紧。把 5 个轴承盖连成一整块梯子形，'
        '比单个轴承盖刚性好得多，高转速时曲轴不容易"甩"。'),
    3: ('油底壳', '冲压钢板 · 黑色烤漆',
        '发动机的"油箱"，装约 4 L 机油。后半部分做深（集油槽），刹车、转弯时机油晃过去，集滤器还泡在油里。'
        '最低点有放油螺塞，换机油就是拧开它。'),
    4: ('气缸垫', '多层钢片（MLS）· 表面橡胶涂层',
        '夹在缸体和缸盖之间。燃烧时缸内压力有六七十个大气压，它要同时封住燃烧室、冷却液水道和机油油道，'
        '互相不能串。"冲缸垫"就是这里漏了：冷却液进了燃烧室，排气冒白烟。'),
    5: ('曲轴', '锻钢 · 轴颈表面淬火、磨光',
        '把活塞的上下运动变成旋转。5 道主轴颈在一条直线上（转动中心），4 个连杆轴颈偏出去 43 mm（行程的一半）。'
        '1、4 缸的连杆轴颈朝同一边，2、3 缸朝反方向，所以每转半圈就有一个缸点火（点火顺序 1-3-4-2）。'
        '8 块平衡重抵消连杆轴颈甩出去的离心力。'),
    6: ('1 缸活塞', '铝硅合金铸造 · 3 道活塞环 + 活塞销',
        '直接承受燃烧压力：最大约 4 吨的力压在它顶上。上两道是气环，封住燃烧气体；第三道是油环，把缸壁上多余的机油刮回油底壳。'
        '活塞销把它和连杆连起来，活塞和缸壁之间只有约 0.03 mm 间隙。现在在压缩上止点：火花塞即将点火。'),
    7: ('2 缸活塞', '铝硅合金铸造 · 3 道活塞环 + 活塞销',
        '和 1 缸一样的活塞。现在在下止点：2、3 缸的连杆轴颈和 1、4 缸差 180°，1、4 缸在顶上时它们在最底下。'
        '2 缸半圈前刚点过火（点火顺序 1-3-4-2 的最后一个），做功行程到底，接下来往上推出废气。'),
    8: ('3 缸活塞', '铝硅合金铸造 · 3 道活塞环 + 活塞销',
        '和 1 缸一样的活塞。现在在下止点，正在进气行程结束、马上开始压缩：它是下一个点火的缸（1-3-4-2）。'),
    9: ('4 缸活塞', '铝硅合金铸造 · 3 道活塞环 + 活塞销',
        '和 1 缸一样，也在上止点，但它是排气行程结束、进气刚开始（进排气门同时微开，叫"气门重叠"）。'
        '所以 1、4 缸同时到顶，只有一个在点火。'),
    10: ('1 缸连杆', '锻钢 · 工字形截面 · 连杆盖 + 2 颗 M9 螺栓 + 轴瓦',
         '小头套活塞销，大头抱住曲轴的连杆轴颈。工字形截面是为了在轻的前提下不被压弯。'
         '大头是剖开的：连杆盖用两颗螺栓装上，才能把它装到曲轴上。'),
    11: ('2 缸连杆', '锻钢 · 工字形截面 · 连杆盖 + 2 颗 M9 螺栓 + 轴瓦', '和 1 缸一样的连杆，中心距 139 mm。'),
    12: ('3 缸连杆', '锻钢 · 工字形截面 · 连杆盖 + 2 颗 M9 螺栓 + 轴瓦', '和 1 缸一样的连杆，中心距 139 mm。'),
    13: ('4 缸连杆', '锻钢 · 工字形截面 · 连杆盖 + 2 颗 M9 螺栓 + 轴瓦', '和 1 缸一样的连杆，中心距 139 mm。'),
    14: ('飞轮（含齿圈）', '铸铁 · 外圈热套钢齿圈',
         '一个很重的圆盘，存住转动的惯量：四缸每半圈才点一次火，靠它把转速"抹平"。外圈的齿圈给起动机的小齿轮啮合；'
         '后面就是离合器（手动挡）或变矩器（自动挡）。'),
    15: ('曲轴减振皮带轮', '铸铁轮毂 + 橡胶环 + 外圈 6 槽带轮',
         '前端带动多楔带，驱动发电机和水泵。轮毂和外圈之间夹一圈橡胶：曲轴长、每次点火都被"拧"一下，会扭转振动，'
         '外圈的惯量和橡胶一起把这个振动吸收掉，不然曲轴会疲劳断裂。'),
    16: ('缸盖', '铝合金铸造 · 压装气门座圈和气门导管',
         '燃烧室的"屋顶"。每缸 2 个进气道（朝前，接进气歧管）和 2 个排气道（朝后，接排气歧管），中间是火花塞孔；'
         '气门挺柱孔和凸轮轴的下半个轴承座也在它上面。10 颗缸盖螺栓穿过它拧进缸体。'),
    17: ('进气凸轮轴（含链轮）', '冷硬铸铁 / 钢 · 凸轮表面淬火',
         '8 个凸轮按顺序顶开 8 个进气门。它由正时链条带动，转速是曲轴的一半：四冲程每个缸转两圈才进一次气。'
         '凸轮的形状（升程多高、开多久）就决定了发动机"性格"。'),
    18: ('排气凸轮轴（含链轮）', '冷硬铸铁 / 钢 · 凸轮表面淬火',
         '顶开 8 个排气门，同样是曲轴转速的一半。进、排两根各管一边，就是 DOHC（双顶置凸轮轴）。'),
    19: ('凸轮轴承盖架', '铝合金 · 10 个轴承盖连成梯子形',
         '把两根凸轮轴压在缸盖上：缸盖是轴承座的下半个，它是上半个，中间只留一层油膜。连成一整块比 10 个单独的盖好装、刚性好。'),
    20: ('1 缸气门组', '2 进气门 + 2 排气门 · 气门弹簧 · 弹簧座 · 液压挺柱',
         '凸轮压下挺柱，气门就往下打开；凸轮转过去，弹簧把气门拉回关闭。进气门（Φ34）比排气门（Φ29）大：'
         '吸进来比推出去难。液压挺柱自动补偿间隙，不用定期调气门。'),
    21: ('2 缸气门组', '2 进气门 + 2 排气门 · 气门弹簧 · 弹簧座 · 液压挺柱', '和 1 缸一样的 4 个气门。每缸 4 气门，一共 16 气门（16V）。'),
    22: ('3 缸气门组', '2 进气门 + 2 排气门 · 气门弹簧 · 弹簧座 · 液压挺柱', '和 1 缸一样的 4 个气门。'),
    23: ('4 缸气门组', '2 进气门 + 2 排气门 · 气门弹簧 · 弹簧座 · 液压挺柱', '和 1 缸一样的 4 个气门。'),
    24: ('正时链条', '套筒滚子链 · 节距 8 mm',
         '把曲轴和两根凸轮轴"锁"在一起：曲轴链轮 21 齿、凸轮轴链轮 42 齿，曲轴转两圈凸轮轴转一圈。'
         '它要是跳了齿，气门开关的时刻就错了，严重时活塞会撞上气门。链条终身免换，皮带要定期换。'),
    25: ('链条张紧器与导轨', '液压张紧器 + 尼龙导轨板',
         '链条用久了会拉长。张紧器用机油压力顶住导轨，一直把链条压紧，不让它甩、不让它跳齿；另一边的固定导轨让链条走直线、少拍打。'),
    26: ('正时罩盖', '铝合金压铸',
         '把正时链条盖起来，里面是飞溅的机油在润滑链条。中间的孔装曲轴前油封，曲轴从这里伸出来带皮带轮。'),
    27: ('气门室盖（含机油加注盖）', '玻纤增强尼龙 · 橡胶密封条',
         '盖住凸轮轴和气门机构，挡住里面飞溅的机油。顶上的黄盖子是加机油的口；4 个圆孔插点火线圈。'),
    28: ('进气歧管', '玻纤增强尼龙 · 稳压腔 + 4 根歧管',
         '空气从节气门进到稳压腔，再分成 4 根一样长的管子送到各缸。管子做得长，进气有惯性，'
         '能在气门关闭前多"塞"进一点空气，中低转速扭矩更大。'),
    29: ('节气门体', '铝合金 · 电子节气门（电机 + 位置传感器）',
         '踩油门其实是在开这片阀片：开得越大进气越多，ECU 按进气量配喷油量，发动机就越有劲。现在是电机驱动，油门踏板只是个传感器。'),
    30: ('油轨与喷油器', '不锈钢油轨 + 4 个电磁喷油器',
         '油轨里是约 3.5 个大气压的汽油。ECU 给喷油器通电几毫秒，针阀抬起，汽油雾化后喷进进气道，'
         '和空气混合后进入气缸。通电时间越长，喷得越多。'),
    31: ('排气歧管', '球墨铸铁',
         '把 4 个缸的废气收集到一起，送去三元催化器。排气温度可到 800 ℃以上，所以用耐热的铸铁，'
         '刚熄火时它会发红。4 根管子长度相近，各缸排气不互相"顶"。'),
    32: ('排气隔热罩', '冲压铝板 · 压出加强筋',
         '挡住排气歧管的热辐射，保护上面的线束、塑料件和旁边的零件。和歧管之间留一层空气隔热。'),
    33: ('1 缸点火线圈', '笔式点火线圈（每缸一个）',
         '其实是一个变压器：初级几百匝、次级上万匝。ECU 突然切断初级电流，磁场崩塌，次级感应出约 3 万伏高压，'
         '经下面的橡胶护套送到火花塞。一缸一个，不需要分电器和高压线。'),
    34: ('2 缸点火线圈', '笔式点火线圈', '和 1 缸一样的点火线圈。'),
    35: ('3 缸点火线圈', '笔式点火线圈', '和 1 缸一样的点火线圈。'),
    36: ('4 缸点火线圈', '笔式点火线圈', '和 1 缸一样的点火线圈。'),
    37: ('1 缸火花塞', 'M12 × 1.25 · 陶瓷绝缘体 + 镍合金电极',
         '拧在燃烧室顶部正中间。几万伏的电压击穿电极之间约 0.8 mm 的间隙，跳出火花点燃混合气。'
         '白色陶瓷把高压和外壳（接地）隔开。点火时刻在上止点前十几度：火焰烧开需要时间。'),
    38: ('2 缸火花塞', 'M12 × 1.25 · 陶瓷绝缘体 + 镍合金电极', '和 1 缸一样的火花塞。'),
    39: ('3 缸火花塞', 'M12 × 1.25 · 陶瓷绝缘体 + 镍合金电极', '和 1 缸一样的火花塞。'),
    40: ('4 缸火花塞', 'M12 × 1.25 · 陶瓷绝缘体 + 镍合金电极', '和 1 缸一样的火花塞。'),
    41: ('机油泵与集滤器', '铝合金泵体 + 钢转子 · 钢网集滤器',
         '曲轴用一根小链条带动它。集滤器的口泡在油底壳最低处，泵把机油吸上来，以三四个大气压压进缸体油道，'
         '送到曲轴、凸轮轴的每个轴承和液压挺柱。机油压力灯亮就是这里出了问题。'),
    42: ('机油滤清器', '钢壳 · 纸质滤芯 · 旁通阀',
         '机油从泵出来先过它，滤掉磨下来的金属屑和积碳，再进主油道。每次换机油一起换。'),
    43: ('机油尺', '弹簧钢片 + 黄色拉环',
         '拔出来擦干净、插回去、再拔出来看：油迹在尺头两个刻度之间就对。太少会烧瓦，太多会被曲轴搅起泡沫。'),
    44: ('水泵（含皮带轮）', '铝合金泵体 + 叶轮',
         '多楔带带着它转，里面的叶轮把冷却液推进缸体水套，绕着气缸和燃烧室吸热，再经节温器去散热器。'),
    45: ('节温器壳', '铝合金 · 内装蜡式节温器',
         '里面的蜡块受热膨胀推开阀门：冷车时关着，冷却液只在发动机里小循环，升温快；到约 90 ℃才打开，'
         '冷却液去散热器大循环。'),
    46: ('发电机', '铝壳 · 爪极转子 + 三相定子 + 整流器 + 调节器',
         '皮带带它转，转速是曲轴的 2.7 倍。发出的三相交流电经二极管整流成直流，稳成约 14 V，'
         '给蓄电池充电、给全车用电器供电。'),
    47: ('起动机', '直流串励电机 + 电磁开关 + 单向离合器',
         '拧钥匙时电磁开关把小齿轮推出去咬住飞轮齿圈，同时接通电机大电流（一两百安），带着曲轴转起来。'
         '着车后单向离合器打滑，小齿轮退回，不会被发动机反拖。'),
    48: ('多楔带', '三元乙丙橡胶 · 6 楔',
         '一根带子绕过曲轴皮带轮、发电机、水泵和张紧轮，一次带动全部附件。楔形槽增大接触面积，比一根三角带传的力大得多。'),
    49: ('皮带张紧轮', '钢摆臂 + 扭簧 + 塑料带轮',
         '扭簧推着摆臂，带轮一直压在多楔带上，保持合适的张紧力：太松会打滑尖叫，太紧会伤轴承。'),
}


# ---------------------------------------------------------------- 时间线（帧）
F_EXP = (1, 120)       # 拆开
F_ASM = (150, 270)     # 装回
F_END = 300


# ---------------------------------------------------------------- 主要尺寸 (mm)，和接口参数表一一对应
BORE, STROKE = 86.0, 86.0
R_CRANK = STROKE / 2           # 曲柄半径
PITCH = 93.0                   # 缸心距
CYL_X = (139.5, 46.5, -46.5, -139.5)          # 1~4 缸中心（1 缸在正时端 +X）
CRANK_UP = (True, False, False, True)         # 1、4 缸连杆轴颈朝上（上止点），2、3 缸朝下
MAIN_X = (186.0, 93.0, 0.0, -93.0, -186.0)    # 5 道主轴承
ROD_L = 139.0                  # 连杆中心距
COMP_H = 30.0                  # 活塞压缩高度（销中心到活塞顶）
DECK = 212.0                   # 缸体顶面 = 43 + 139 + 30
GASKET = (212.0, 215.0)        # 缸垫（实物 1.2，画成 3）
CAM_Z = 350.0                  # 凸轮轴中心线 = 缸盖 / 承盖架分型面
CAM_Y = 58.0                   # 进气凸轮轴 Y = -58，排气 +58
COVER_TOP = 425.0
PAN_BOT, PAN_TOP = -220.0, -70.0
BLK_X = (-215.0, 215.0)        # 缸体前后端面
SKIRT_W = 125.0                # 曲轴箱（裙部）半宽
CYL_W = 104.0                  # 气缸部分半宽（缸体顶面、缸垫）
HEAD_W = 115.0                 # 缸盖半宽
BOLT_Y = 96.0                  # 缸盖螺栓 Y = ±96，X = 5 道主轴承的位置
SKIRT_TOP = 90.0               # 裙部 / 气缸部分交界
MAIN_R = 27.5                  # 主轴颈半径（Φ55）
PIN_R = 24.0                   # 连杆轴颈半径（Φ48）
VALVE_ANG = radians(17.5)      # 气门与竖直线夹角（夹角 35°）
CHAIN_X = (232.0, 242.0)       # 正时链条所在平面
BELT_X = (268.0, 289.0)        # 多楔带所在平面
FLY_X = (-253.0, -228.0)       # 飞轮


def crank_pin(i):
    """第 i 缸连杆轴颈中心 (y, z)"""
    return (0.0, R_CRANK if CRANK_UP[i] else -R_CRANK)


def piston_pin_z(i):
    """活塞销中心高度（曲柄在上 / 下止点，连杆竖直）"""
    return crank_pin(i)[1] + ROD_L


def make_materials():
    # 金属的金属度给 1。金属没有漫反射，颜色全靠反射周围的环境；0.3 ~ 0.5 这种"半金属"一半按漆面算，看起来像喷了灰漆的塑料。
    # 以前压在 0.55 以下，是因为虚幻工作室里没有东西可反射（金属发黑，车床实测）；现在 MyVRToyBox 的工作室加了天光
    # （开局抓一次房间当环境），金属有东西可照了。金属的底色就是它的反射率：铝最亮，钢铁暗一些，铸造 / 锻造表面再暗一点。
    # 漆、塑料、橡胶、陶瓷、涂层（缸垫、弹簧漆）是非金属，金属度 0
    return dict(
        alu=pbr('M_Alu_Cast', '#c3c7cb', 1, .55, 'cast'),
        alu_lt=pbr('M_Alu_Head', '#ccd0d4', 1, .5, 'cast'),
        alu_mach=pbr('M_Alu_Machined', '#e0e3e6', 1, .28, 'machined'),
        iron=pbr('M_Iron_Dark', '#8b8f94', 1, .55, 'forged'),
        forged=pbr('M_Steel_Forged', '#9a9ea3', 1, .45, 'forged'),
        steel=pbr('M_Steel_Polished', '#c8cbce', 1, .22, 'smooth'),
        bearing=pbr('M_Bearing_Shell', '#c2a678', 1, .35, 'machined'),
        hole=principled('M_Hole', '#0b0b0c', 0, .85),
        pan=pbr('M_Pan_Black', '#2a2c30', 0, .42, 'smooth'),
        plastic=pbr('M_Plastic_Black', '#1f2023', 0, .55, 'molded'),
        rubber=pbr('M_Rubber', '#141516', 0, .85, 'molded'),
        rust=pbr('M_Iron_Exhaust', '#6a4b3c', .2, .75, 'rust'),
        shield=pbr('M_Heat_Shield', '#cfd2d5', 1, .35, 'smooth'),
        piston=pbr('M_Piston_Alu', '#d3d6d9', 1, .38, 'machined'),
        piston_dk=pbr('M_Piston_Relief', '#b4b8bc', 1, .5, 'cast'),
        ring=pbr('M_Ring_Dark', '#5a5d62', 1, .35, 'smooth'),
        gasket=pbr('M_Gasket_MLS', '#3c4a43', 0, .5, 'smooth'),
        orange=pbr('M_Guide_Orange', '#e07a1a', 0, .5, 'molded'),
        spring=pbr('M_Spring_Green', '#3a8a78', 0, .4, 'smooth'),
        ceramic=pbr('M_Ceramic', '#ece8df', 0, .45, 'smooth'),
        yellow=pbr('M_Yellow', '#f2c316', 0, .45, 'molded'),
        blue=pbr('M_Filter_Blue', '#1f4fa6', 0, .35, 'smooth'),
        copper=pbr('M_Copper', '#c98a62', 1, .35, 'smooth'),
        red=pbr('M_Red', '#c8231e', 0, .45, 'molded'),
        chain=pbr('M_Chain', '#a9adb2', 1, .38, 'smooth'),
        white=principled('M_Print_White', '#eeeeee', 0, .5),
    )


# ---------------------------------------------------------------- 几何工具（发动机用的补充）
ROT['-Z'] = Matrix.Rotation(pi, 4, 'X')    # 局部 +Z → 世界 -Z


def hexagon(r, cx=0.0, cy=0.0, rot=0.0):
    return [(cx + r * cos(rot + pi / 3 * k), cy + r * sin(rot + pi / 3 * k)) for k in range(6)]


def place(bm, fs, origin, direction):
    """把沿局部 +Z 建好的几何转到 direction、原点挪到 origin"""
    q = Vector(direction).normalized().to_track_quat('Z', 'Y')
    xform(bm, fs, Matrix.Translation(Vector(origin)) @ q.to_matrix().to_4x4())


def rod_dir(bm, r, a0, a1, mi, origin, direction, seg=32):
    fs = revolve(bm, [(0, a0), (r, a0), (r, a1), (0, a1)], mi, seg=seg, closed=False)
    place(bm, fs, origin, direction)
    return fs


def rev_dir(bm, prof, mi, origin, direction, seg=48, closed=False):
    fs = revolve(bm, prof, mi, seg=seg, closed=closed)
    place(bm, fs, origin, direction)
    return fs


def tube(bm, r0, r1, a0, a1, mi, axis='X', c=(0, 0, 0), seg=48):
    """空心管 / 圆环（内半径 r0、外半径 r1）"""
    return rev(bm, [(r0, a0), (r1, a0), (r1, a1), (r0, a1)], mi, axis, c, seg, closed=True)


def hex_bolt(bm, c, axis, mi, s=13.0, h=7.0, washer=True):
    """六角螺栓头（对边 s，高 h），从 c 沿 axis 方向凸出"""
    r = s / 2 / cos(pi / 6)
    fs = []
    if washer:
        fs += revolve(bm, [(0, 0), (r * 1.15, 0), (r * 1.15, 1.2), (0, 1.2)], mi, seg=20, closed=False)
        fs += extrude(bm, [hexagon(r)], 1.2, h, mi)
    else:
        fs += extrude(bm, [hexagon(r)], 0, h, mi)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def arc_pts(cx, cy, r, a0, a1, n=16):
    return [(cx + r * cos(a0 + (a1 - a0) * k / n), cy + r * sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def circle_hull(circles, n=40):
    """若干圆 (cx, cy, r) 的凸包，逆时针点列（链条、皮带、罩盖外形用）"""
    pts = []
    for (cx, cy, r) in circles:
        pts += circle(cx, cy, r, n)
    return hull(pts)


def offset_loop(pts, d):
    """凸多边形向外平移 d（按顶点法线，近似即可）"""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = (p1[0] - p0[0], p1[1] - p0[1])
        e2 = (p2[0] - p1[0], p2[1] - p1[1])
        n1 = (e1[1], -e1[0])
        n2 = (e2[1], -e2[0])
        l1, l2 = math.hypot(*n1) or 1, math.hypot(*n2) or 1
        nx, ny = n1[0] / l1 + n2[0] / l2, n1[1] / l1 + n2[1] / l2
        ln = math.hypot(nx, ny) or 1
        out.append((p1[0] + nx / ln * d, p1[1] + ny / ln * d))
    return out


def resample(pts, step):
    """闭合折线按弧长重采样（链节、皮带楔用）"""
    n = len(pts)
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
    k = max(8, int(total / step))
    out, acc, si = [], 0.0, 0
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
    for j in range(k):
        t = total * j / k
        while si < n - 1 and acc + lens[si] < t:
            acc += lens[si]
            si += 1
        a, b = segs[si]
        u = (t - acc) / (lens[si] or 1)
        out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
    return out


# ---------------------------------------------------------------- 零件登记
ROOT = None         # 空物体 Engine
OBJS = []           # dict(ob, ex, no)


# 桌上的摆法要求进气侧朝玩家、正时端在玩家左手边（右前方是触屏），所以导出时整体左右镜像（X 取反）。
# 脚本里所有尺寸、路线照接口参数表写（+X = 正时端），镜像只在这里做一次。
MIRROR_X = True

# 倒角：现实里没有绝对锐利的边，最小也有零点几毫米的圆角，这条小圆角接住高光、在边上亮出一条细线，
# 眼睛靠它判断"这是硬的实物"；没有它，边上只有两块明暗不同的面硬碰硬，一看就是 CG。
# 宽度按零件大小取（最长边 × 0.35%，0.4 ~ 1.8 mm）。只倒夹角超过 50° 的边：方块、六角螺栓头、齿形都在里面，
# 8 ~ 12 边的细管（弹簧、链销、导线）相邻面只差 30° ~ 45°，本来就该是圆的，倒了只会白白多出面。薄片类零件单独给小值，免得整条边被倒成圆的
BEVEL_MM = {4: .3, 24: .3, 32: .5, 48: .6}      # 缸垫、正时链条、隔热罩、多楔带


def add_bevel(ob, no, size_mm):
    bv = ob.modifiers.new('Bevel', 'BEVEL')
    bv.width = BEVEL_MM.get(no, min(1.8, max(.4, size_mm * .0035))) * MM
    bv.segments = 1                    # 一段斜面 + 下面的加权法线，看起来就是圆角（游戏美术的常用做法），面数只有两段的一半
    bv.limit_method = 'ANGLE'
    bv.angle_limit = radians(50)
    bv.use_clamp_overlap = True
    # 加权法线：顶点法线按相邻面的面积加权，大平面说了算、保持平的，只有窄窄的倒角面弯过去。
    # 不加的话，拉伸出来的端面（带孔的轮廓三角化后全是细长三角形）会把倒角边上斜着的法线拖出一道道黑楔子
    wn = ob.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')
    wn.mode = 'FACE_AREA'
    wn.keep_sharp = True


def finish(name, no, bm, mats, ex=(), smooth=34):
    if MIRROR_X:
        bmesh.ops.transform(bm, matrix=Matrix.Scale(-1, 4, (1, 0, 0)), verts=bm.verts)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        ex = [(-e[0], e[1], e[2], e[3]) for e in ex]
    size = max(max(v.co[k] for v in bm.verts) - min(v.co[k] for v in bm.verts) for k in range(3))
    box_uv(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    collection('Engine').objects.link(ob)
    shade(me, smooth)
    ob.data.transform(Matrix.Scale(MM, 4))
    add_bevel(ob, no, size)
    ob.parent = ROOT
    ob['name_cn'] = INFO[no][0]
    OBJS.append(dict(ob=ob, ex=list(ex), no=no))
    return ob


def mats_of(M, *keys):
    """材质列表 + 名字到序号的表"""
    return [M[k] for k in keys], {k: i for i, k in enumerate(keys)}


# ---------------------------------------------------------------- E01 缸体
def build_block(M):
    mats, I = mats_of(M, 'alu', 'hole', 'steel', 'bearing', 'alu_mach')
    bm = bmesh.new()
    x0, x1 = BLK_X
    # 气缸部分：4 个缸孔从上到下打通（下面通进曲轴箱）
    bores = [circle(cx, 0, BORE / 2, 64) for cx in CYL_X]
    extrude(bm, [rrect(x1, CYL_W, 12)] + bores, SKIRT_TOP, DECK, I['alu'])
    # 缸套下段伸进曲轴箱
    for cx in CYL_X:
        tube(bm, BORE / 2, BORE / 2 + 5, 72, SKIRT_TOP, I['alu'], 'Z', (cx, 0, 0))
    # 曲轴箱裙部：空心框，上面一圈肩把气缸部分和裙部接起来
    extrude(bm, [rrect(x1, SKIRT_W, 12), rrect(x1 - 10, SKIRT_W - 10, 8)[::-1]], 0, SKIRT_TOP - 8, I['alu'])
    extrude(bm, [rrect(x1, SKIRT_W, 12), rrect(x1 - 1, CYL_W - 1, 11)[::-1]], SKIRT_TOP - 8, SKIRT_TOP + 2, I['alu'])
    # 5 道隔板：下沿是主轴承座（半圆）
    for mx in MAIN_X:
        prof = [(-(SKIRT_W - 9), 0), (-30, 0)] + arc_pts(0, 0, 30, pi, 0, 20)[1:-1] + [(30, 0), (SKIRT_W - 9, 0),
                                                                                         (SKIRT_W - 9, SKIRT_TOP - 7), (-(SKIRT_W - 9), SKIRT_TOP - 7)]
        extrude(bm, [prof], mx - 10, mx + 10, I['alu'], axis='X')
        shell = arc_pts(0, 0, 30.2, 0, pi, 20) + arc_pts(0, 0, MAIN_R + .3, pi, 0, 20)
        extrude(bm, [shell], mx - 9.5, mx + 9.5, I['bearing'], axis='X')
    # 裙部外侧的加强筋（对着每道隔板）
    for mx in MAIN_X:
        for s in (-1, 1):
            boxf(bm, (mx - 5, s * SKIRT_W - (0 if s > 0 else 6), 4), (mx + 5, s * SKIRT_W + (6 if s > 0 else 0), SKIRT_TOP - 4), I['alu'])
    # 顶面：10 个缸盖螺栓孔、冷却液孔、2 个定位销
    for mx in MAIN_X:
        for s in (-1, 1):
            disk(bm, 6, (mx, s * BOLT_Y, DECK), 'Z', I['hole'], h=.3)
    for cx in CYL_X:
        for s in (-1, 1):
            flat(bm, [stadium(cx, s * 72, 9, 4.5)], DECK, I['hole'], h=.3)
    for (dx, dy) in ((x1 - 14, -84), (x0 + 14, 84)):
        tube(bm, 4.5, 7, DECK, DECK + 6, I['steel'], 'Z', (dx, dy, 0), seg=20)
    # 后端面法兰（接变速箱），左下角伸出起动机安装耳
    flange = hull([(-150, -70), (150, -70), (150, 225), (-150, 225)] + circle(-176, -58, 38, 24))
    extrude(bm, [flange, circle(0, 0, 62, 48)], x0 - 10, x0, I['alu'], axis='X')
    for (fy, fz) in ((-140, -55), (140, -55), (-140, 205), (140, 205), (0, 215), (-145, 80), (145, 80)):
        disk(bm, 6.5, (x0 - 10, fy, fz), '-X', I['hole'], h=.3)
    # 前端面：曲轴孔周围的加工面（被正时罩盖盖住）
    tube(bm, 30, 70, x1, x1 + 1, I['alu_mach'], 'X', (0, 0, 0))
    # 进气侧：机油滤清器座（斜向下 30°）、发电机支架
    fdir = Vector((0, -cos(radians(30)), -sin(radians(30))))
    rod_dir(bm, 34, 0, 16, I['alu'], (20, -SKIRT_W + 6, 50), fdir)
    rod_dir(bm, 12, 15, 17, I['alu_mach'], (20, -SKIRT_W + 6, 50), fdir)
    boxf(bm, (175, -150, 8), (213, -SKIRT_W, 72), I['alu'])
    # 机油尺导管（从裙部侧面一路弯上来，管口在缸盖高度）
    path = [Vector(p) for p in catmull([Vector((93, -SKIRT_W + 2, 40)), Vector((93, -150, 110)),
                                        Vector((93, -165, 230)), Vector((93, -172, 372))], 8)]
    sweep(bm, path, 6, I['steel'], sides=12)
    # 排气侧：发动机悬置支座
    boxf(bm, (60, SKIRT_W, 120), (140, SKIRT_W + 22, 180), I['alu'])
    for (bx, bz) in ((75, 135), (125, 135), (75, 165), (125, 165)):
        disk(bm, 5, (bx, SKIRT_W + 22, bz), 'Y', I['hole'], h=.3)
    finish('E01_Block', 1, bm, mats)


# ---------------------------------------------------------------- E02 主轴承梁
def build_bedplate(M, ex):
    mats, I = mats_of(M, 'alu', 'bearing', 'steel', 'hole')
    bm = bmesh.new()
    x0, x1 = BLK_X
    extrude(bm, [rrect(x1, SKIRT_W - 5, 10), rrect(x1 - 10, SKIRT_W - 15, 6)[::-1]], PAN_TOP, 0, I['alu'])
    for mx in MAIN_X:
        prof = [(-(SKIRT_W - 14), 0), (-30, 0)] + arc_pts(0, 0, 30, pi, 2 * pi, 20)[1:-1] + [(30, 0), (SKIRT_W - 14, 0),
                                                                                                  (SKIRT_W - 14, PAN_TOP), (-(SKIRT_W - 14), PAN_TOP)]
        extrude(bm, [prof], mx - 10, mx + 10, I['alu'], axis='X')
        shell = arc_pts(0, 0, 30.2, pi, 2 * pi, 20) + arc_pts(0, 0, MAIN_R + .3, 2 * pi, pi, 20)
        extrude(bm, [shell], mx - 9.5, mx + 9.5, I['bearing'], axis='X')
        # 底面的主轴承螺栓（每道 2 颗 M10）
        for s in (-1, 1):
            fs = extrude(bm, [hexagon(8.5)], 0, 7, I['steel'])
            xform(bm, fs, Matrix.Translation(Vector((mx, s * 52, PAN_TOP - 7))))
    # 下面一根纵梁把 5 道隔板连起来
    boxf(bm, (x0 + 10, -14, PAN_TOP), (x1 - 10, 14, PAN_TOP + 18), I['alu'])
    # 周边 12 颗 M8
    for bx in (-200, -139.5, -46.5, 46.5, 139.5, 200):
        for s in (-1, 1):
            fs = extrude(bm, [hexagon(6.5)], 0, 6, I['steel'])
            xform(bm, fs, Matrix.Translation(Vector((bx, s * (SKIRT_W - 10), PAN_TOP - 6))))
    finish('E02_Bedplate', 2, bm, mats, ex)


# ---------------------------------------------------------------- 曲柄连杆机构
def gear(bm, n, r_root, r_tip, a0, a1, mi, axis='X', c=(0, 0, 0), phase=0.0):
    """直齿轮 / 链轮：梯形齿截面沿 axis 拉伸"""
    pts = []
    for k in range(n):
        a = phase + 2 * pi * k / n
        w = pi / n
        for (da, r) in ((-w * .55, r_root), (-w * .25, r_tip), (w * .25, r_tip), (w * .55, r_root)):
            pts.append((r * cos(a + da), r * sin(a + da)))
    fs = extrude(bm, [pts], a0, a1, mi)
    xform(bm, fs, Matrix.Translation(Vector(c)) @ ROT[axis])
    return fs


def yz_extrude(bm, loops, x0, x1, mi):
    """(y, z) 平面里的轮廓沿 X 拉伸（extrude 的 axis='X' 正好是 (u, v) → (y, z)）"""
    return extrude(bm, loops, x0, x1, mi, axis='X')


def build_crank(M, ex):
    mats, I = mats_of(M, 'forged', 'steel', 'hole')
    bm = bmesh.new()
    for mx in MAIN_X:
        rod(bm, MAIN_R, mx - 11, mx + 11, I['steel'], 'X')
        disk(bm, 2.5, (mx, 0, MAIN_R), 'Z', I['hole'], h=.25, seg=10)
    for i, cx in enumerate(CYL_X):
        py, pz = crank_pin(i)
        d = 1 if pz > 0 else -1
        rod(bm, PIN_R, cx - 13.5, cx + 13.5, I['steel'], 'X', (0, py, pz))
        disk(bm, 2.5, (cx, 0, pz + d * PIN_R), 'Z' if d > 0 else '-Z', I['hole'], h=.25, seg=10)
        # 曲柄臂：连杆轴颈一侧窄、平衡重一侧是扇形
        web = hull(circle(0, pz, 31, 32) + circle(0, 0, 36, 32) +
                   arc_pts(0, 0, 68, -d * pi / 2 - radians(62), -d * pi / 2 + radians(62), 24))
        for s in (-1, 1):
            a, b = sorted((cx + s * 13.5, cx + s * 35.5))
            yz_extrude(bm, [web], a, b, I['forged'])
    # 前端：机油泵链轮、正时链轮（21 齿）、油封轴颈、皮带轮座
    rod(bm, 22, 197, 264, I['forged'], 'X')
    gear(bm, 16, 18, 22.5, 214, 222, I['forged'])
    gear(bm, 21, 23.5, 30.5, CHAIN_X[0], CHAIN_X[1], I['steel'])
    rod(bm, 20, 242, 262, I['steel'], 'X')
    # 后端：油封轴颈 + 飞轮法兰
    rod(bm, 40, -222, -197, I['steel'], 'X')
    rod(bm, 46, FLY_X[1], -222, I['forged'], 'X')
    for k in range(8):
        a = 2 * pi * k / 8 + pi / 8
        disk(bm, 4.5, (FLY_X[1], 35 * cos(a), 35 * sin(a)), '-X', I['hole'], h=.25, seg=12)
    finish('E05_Crankshaft', 5, bm, mats, ex)


def build_piston(M, i, ex):
    mats, I = mats_of(M, 'piston', 'ring', 'steel', 'hole', 'piston_dk')
    bm = bmesh.new()
    cx = CYL_X[i]
    zp = piston_pin_z(i)
    zc = zp + COMP_H
    R = BORE / 2 - .3
    prof = [(0, zc - 26), (34, zc - 26), (R - 2.5, zc - 55), (R, zc - 55), (R, zc - 2), (R - 1.5, zc), (12, zc + 1.2), (0, zc + 1.2)]
    rev(bm, prof, I['piston'], 'Z', (cx, 0, 0), seg=64, closed=False)
    for (z0, z1) in ((zc - 8, zc - 6.5), (zc - 12.5, zc - 11), (zc - 18.5, zc - 15.5)):
        tube(bm, R - .6, R + .15, z0, z1, I['ring'], 'Z', (cx, 0, 0), seg=64)
    # 气门避让坑（4 个浅坑对着 4 个气门）
    for (vx, vy, r) in ((-17, -20, 14), (17, -20, 14), (-15, 20, 12), (15, 20, 12)):
        disk(bm, r, (cx + vx, vy, zc + .3), 'Z', I['piston_dk'], h=.95, seg=24)
    # 活塞销（两端露在裙部销孔里）
    rod(bm, 10.5, cx - 31, cx + 31, I['steel'], 'X', (0, 0, zp))
    for s in (-1, 1):
        tube(bm, 10.5, 13.5, cx + s * 41.5 - .8, cx + s * 41.5 + .8, I['hole'], 'X', (0, 0, zp), seg=24)
    finish(f'E{6 + i:02d}_Piston{i + 1}', 6 + i, bm, mats, ex)


def build_conrod(M, i, ex):
    mats, I = mats_of(M, 'forged', 'steel', 'hole', 'bearing')
    bm = bmesh.new()
    cx = CYL_X[i]
    py, zb = crank_pin(i)
    zs = zb + ROD_L
    # 大头（含连杆盖）、小头
    tube(bm, PIN_R + 1.5, 37, cx - 11, cx + 11, I['forged'], 'X', (0, 0, zb), seg=48)
    tube(bm, PIN_R + .2, PIN_R + 1.5, cx - 10.5, cx + 10.5, I['bearing'], 'X', (0, 0, zb), seg=48)
    tube(bm, 10.6, 16, cx - 10, cx + 10, I['forged'], 'X', (0, 0, zs), seg=32)
    # 连杆盖的螺栓凸台 + 螺栓（从盖下面拧上来）
    for s in (-1, 1):
        boxf(bm, (cx - 11, s * 30 - 8, zb - 18), (cx + 11, s * 30 + 8, zb + 14), I['forged'])
        rod(bm, 6.5, zb - 26, zb - 18, I['steel'], 'Z', (cx, s * 30, 0), seg=6)
    # 连杆盖分开的那条缝
    boxf(bm, (cx - 11.3, -38.5, zb - .6), (cx + 11.3, 38.5, zb + .6), I['hole'])
    # 杆身：工字形（中间薄腹板 + 两侧翼缘）
    z0, z1 = zb + 30, zs - 13
    yz_extrude(bm, [[(-17, z0), (17, z0), (10, z1), (-10, z1)]], cx - 4, cx + 4, I['forged'])
    for s in (-1, 1):
        edge = [(s * 17, z0), (s * 12, z0), (s * 6, z1), (s * 10, z1)]
        yz_extrude(bm, [edge if s < 0 else edge[::-1]], cx - 9, cx + 9, I['forged'])
    disk(bm, 2, (cx, 0, zs + 16), 'Z', I['hole'], h=.25, seg=10)
    finish(f'E{10 + i:02d}_ConRod{i + 1}', 10 + i, bm, mats, ex)


def build_flywheel(M, ex):
    mats, I = mats_of(M, 'iron', 'steel', 'hole', 'forged')
    bm = bmesh.new()
    a, b = FLY_X
    prof = [(24, b), (52, b), (58, b - 6), (122, b - 6), (128, b), (134, b), (134, a), (128, a), (126, a + 4),
            (72, a + 4), (66, a), (24, a)]
    rev(bm, prof, I['iron'], 'X', seg=96, closed=True)
    tube(bm, 72, 124, a - .3, a, I['steel'], 'X', seg=96)               # 离合器摩擦面（磨光）
    gear(bm, 60, 133.5, 142, b - 10, b, I['forged'])                   # 起动齿圈
    for k in range(8):
        t = 2 * pi * k / 8 + pi / 8
        hex_bolt(bm, (a, 35 * cos(t), 35 * sin(t)), '-X', I['steel'], s=12, h=6)
    for k in range(6):
        t = 2 * pi * k / 6
        disk(bm, 5, (a + 4, 98 * cos(t), 98 * sin(t)), '-X', I['hole'], h=.3, seg=14)
    finish('E14_Flywheel', 14, bm, mats, ex)


def build_crank_pulley(M, ex):
    mats, I = mats_of(M, 'iron', 'rubber', 'steel', 'hole')
    bm = bmesh.new()
    rev(bm, [(20.5, 262), (30, 262), (30, 300), (20.5, 300)], I['iron'], 'X', seg=48, closed=True)
    tube(bm, 29, 56, 278, 285, I['iron'], 'X', seg=64)
    tube(bm, 55, 60, 266, 293, I['rubber'], 'X', seg=64)
    # 外圈：6 道楔槽
    prof = [(60, 266), (75, 266)]
    n = 6
    w = (BELT_X[1] - BELT_X[0]) / n
    for k in range(n):
        x = BELT_X[0] + k * w
        prof += [(75, x), (71.5, x + w / 2)]
    prof += [(75, BELT_X[1]), (75, 293), (60, 293)]
    rev(bm, prof, I['iron'], 'X', seg=96, closed=True)
    for k in range(4):
        t = 2 * pi * k / 4 + pi / 4
        disk(bm, 7, (285, 42 * cos(t), 42 * sin(t)), 'X', I['hole'], h=.3, seg=16)
    rod(bm, 15, 300, 302, I['steel'], 'X')
    fs = extrude(bm, [hexagon(11)], 302, 312, I['steel'])
    xform(bm, fs, ROT['X'])
    finish('E15_CrankPulley', 15, bm, mats, ex)


# ---------------------------------------------------------------- 配气机构
# 每个气门沿自己的轴线建：原点 = 气门盘底面中心，轴线方向 d（往上、往各自的凸轮轴那边斜 17.5°）。
# 轴线延长到 VALVE_S_CAM 处正好是凸轮轴中心，所以凸轮的基圆刚好压在挺柱顶上。
VALVE_S_CAM = 125.0
VALVE_LEN = 95.0
BUCKET = (86.0, 108.0)         # 液压挺柱（沿轴线）
CAM_BASE, CAM_LIFT = 17.0, 9.0
JOURNAL_X = MAIN_X             # 凸轮轴颈和主轴颈对齐（在两缸之间）
CAM_X = (-200.0, 250.0)        # 凸轮轴两端（前端伸出缸盖装链轮）
LADDER_Z = (CAM_Z, CAM_Z + 22)


def valve_axes(i):
    """第 i 缸 4 个气门：(x, 原点, 方向, 盘半径, 进气?)"""
    cx = CYL_X[i]
    out = []
    for kind, sy, xs, r in (('in', -1, 17.0, 17.0), ('ex', 1, 15.0, 14.5)):
        d = Vector((0, sy * sin(VALVE_ANG), cos(VALVE_ANG)))
        o = Vector((0, sy * CAM_Y, CAM_Z)) - d * VALVE_S_CAM
        for s in (-1, 1):
            out.append((cx + s * xs, Vector((cx + s * xs, o.y, o.z)), d, r, kind == 'in'))
    return out


def build_gasket(M, ex):
    mats, I = mats_of(M, 'gasket', 'steel')
    bm = bmesh.new()
    z0, z1 = GASKET
    holes = [circle(cx, 0, BORE / 2 + 1.5, 64) for cx in CYL_X]
    holes += [circle(mx, s * BOLT_Y, 6.5, 16) for mx in MAIN_X for s in (-1, 1)]
    holes += [stadium(cx, s * 72, 9, 4.5) for cx in CYL_X for s in (-1, 1)]
    holes += [circle(x, y, 4, 12) for x in (-200, 200) for y in (-60, 60)]
    extrude(bm, [rrect(BLK_X[1], CYL_W, 12)] + holes, z0, z1, I['gasket'])
    for cx in CYL_X:        # 缸口的钢质火圈
        tube(bm, BORE / 2 + 1.5, BORE / 2 + 4, z1, z1 + .5, I['steel'], 'Z', (cx, 0, 0), seg=64)
    finish('E04_HeadGasket', 4, bm, mats, ex)


def build_head(M, ex):
    mats, I = mats_of(M, 'alu_lt', 'hole', 'steel', 'alu_mach', 'alu')
    bm = bmesh.new()
    x0, x1 = BLK_X
    floor = CAM_Z - 12
    extrude(bm, [rrect(x1, HEAD_W, 10)], GASKET[1], floor, I['alu_lt'])
    extrude(bm, [rrect(x1, HEAD_W, 10), rrect(x1 - 10, HEAD_W - 10, 6)[::-1]], floor, CAM_Z, I['alu_lt'])
    flat(bm, [rrect(x1, HEAD_W, 10), rrect(x1 - 10, HEAD_W - 10, 6)[::-1]], CAM_Z, I['alu_mach'], h=.3)
    # 凸轮轴承座（下半个，半圆槽）
    for jx in JOURNAL_X:
        for sy in (-1, 1):
            cy = sy * CAM_Y
            prof = [(cy - 26, floor), (cy + 26, floor), (cy + 26, CAM_Z), (cy + 13.5, CAM_Z)] + \
                arc_pts(cy, CAM_Z, 13.5, 0, -pi, 16)[1:-1] + [(cy - 13.5, CAM_Z), (cy - 26, CAM_Z)]
            yz_extrude(bm, [prof], jx - 9, jx + 9, I['alu_lt'])
    # 挺柱孔、火花塞孔（凸台）
    for i, cx in enumerate(CYL_X):
        for (x, o, d, r, _) in valve_axes(i):
            p = o + d * ((floor - o.z) / d.z)
            disk(bm, 16.5, (x, p.y, floor), 'Z', I['hole'], h=.3, seg=24)
        tube(bm, 11, 17, floor - 1, floor + 14, I['alu_lt'], 'Z', (cx, 0, 0), seg=32)
        disk(bm, 11, (cx, 0, floor + 2), 'Z', I['hole'], h=.3, seg=24)
    # 10 颗缸盖螺栓（法兰面十二角头，画成六角 + 垫圈）
    for mx in MAIN_X:
        for s in (-1, 1):
            hex_bolt(bm, (mx, s * BOLT_Y, floor), 'Z', I['steel'], s=15, h=9)
    # 进气道（-Y）、排气道（+Y）
    for cx in CYL_X:
        for sy, zz, hl, r in ((-1, 290, 15, 16), (1, 284, 10, 17)):
            fs = extrude(bm, [stadium(0, 0, hl, r)], 0, .3, I['hole'])
            m = Matrix.Translation(Vector((cx, sy * HEAD_W, zz))) @ (ROT['-Y'] if sy < 0 else ROT['Y'])
            xform(bm, fs, m)
        for sy in (-1, 1):
            for dx in (-34, 34):
                disk(bm, 4, (cx + dx, sy * HEAD_W, 290 + (16 if dx > 0 else -16)), '-Y' if sy < 0 else 'Y',
                     I['hole'], h=.3, seg=12)
    # 吊环（前端排气侧、后端进气侧）
    for (lx, ly) in ((x1 - 26, HEAD_W - 6), (x0 + 26, -(HEAD_W - 6))):
        yz_extrude(bm, [rrect(16, 22, 6, cx=ly, cy=CAM_Z + 18), circle(ly, CAM_Z + 26, 7, 16)], lx - 4, lx + 4, I['alu'])
    # 后端：节温器座
    rod(bm, 30, x0 - 4, x0, I['alu_mach'], 'X', (0, 40, 285))
    finish('E16_CylinderHead', 16, bm, mats, ex)


def build_valves(M, i, ex):
    mats, I = mats_of(M, 'steel', 'spring', 'forged', 'alu_mach')
    bm = bmesh.new()
    for (x, o, d, r, is_in) in valve_axes(i):
        prof = [(0, 0), (r, 0), (r, 1.8), (r - 3.5, 4.5), (4.5, 16), (2.75, 26), (2.75, VALVE_LEN), (0, VALVE_LEN)]
        rev_dir(bm, prof, I['steel'], o, d, seg=32)
        # 气门弹簧（螺旋），弹簧座
        n, turns, rr, wire = 70, 6.5, 12.5, 1.9
        s0, s1 = 50.0, BUCKET[0] + 4
        path = [Vector((rr * cos(2 * pi * turns * k / n), rr * sin(2 * pi * turns * k / n), s0 + (s1 - s0) * k / n))
                for k in range(n + 1)]
        fs = sweep(bm, path, wire, I['spring'], sides=8)
        place(bm, fs, o, d)
        rev_dir(bm, [(4, s0 - 2), (15, s0 - 2), (15, s0), (4, s0)], I['forged'], o, d, seg=24, closed=True)
        # 液压挺柱（倒扣的杯子，顶面被凸轮压）
        a, b = BUCKET
        rev_dir(bm, [(13.5, a), (15.5, a), (15.5, b), (0, b), (0, b - 3), (13.5, b - 3)], I['alu_mach'], o, d,
                seg=32, closed=True)
    finish(f'E{20 + i:02d}_Valves{i + 1}', 20 + i, bm, mats, ex)


CYL_PHASE = (0, 540, 180, 360)     # 各缸压缩上止点相对 1 缸的曲轴转角（点火顺序 1-3-4-2）


def lobe_angle(i, is_in):
    """凸轮桃尖的方向（YZ 平面里的角度）。曲轴停在 1 缸压缩上止点"""
    c = (-CYL_PHASE[i]) % 720                  # 这个缸现在在自己循环里的曲轴转角
    c_max = 470 if is_in else 250              # 进 / 排气门最大升程时刻
    sy = -1 if is_in else 1
    to_valve = math.atan2(-cos(VALVE_ANG), -sy * sin(VALVE_ANG))   # 凸轮中心指向挺柱
    return to_valve + radians((c - c_max) / 2)


def build_camshaft(M, is_in, ex):
    mats, I = mats_of(M, 'iron', 'steel', 'forged', 'hole')
    bm = bmesh.new()
    sy = -1 if is_in else 1
    cy = sy * CAM_Y
    yz_extrude(bm, [circle(cy, CAM_Z, 11.5, 24)], CAM_X[0], CAM_X[1], I['iron'])
    for jx in JOURNAL_X:
        rod(bm, 13.3, jx - 9, jx + 9, I['steel'], 'X', (0, cy, CAM_Z))
    # 每缸 2 个凸轮
    for i, cx in enumerate(CYL_X):
        a = lobe_angle(i, is_in)
        nose = (cy + (CAM_BASE + CAM_LIFT - 8) * cos(a), CAM_Z + (CAM_BASE + CAM_LIFT - 8) * sin(a))
        lobe = hull(circle(cy, CAM_Z, CAM_BASE, 40) + circle(nose[0], nose[1], 8, 24))
        xs = 17.0 if is_in else 15.0
        for s in (-1, 1):
            yz_extrude(bm, [lobe], cx + s * xs - 7, cx + s * xs + 7, I['steel'])
    # 扳手六方（拆装时卡住凸轮轴用）
    yz_extrude(bm, [hexagon(14, cy, CAM_Z)], 160, 172, I['iron'])
    # 链轮：42 齿，节圆 Φ107；轮辐开减重孔
    yz_extrude(bm, [circle(cy, CAM_Z, 22, 32)], 215, CHAIN_X[0], I['forged'])
    gear(bm, 42, 50.5, 56, CHAIN_X[0], CHAIN_X[1], I['forged'], c=(0, cy, CAM_Z))
    for k in range(5):
        t = 2 * pi * k / 5 + (.3 if is_in else 0)
        disk(bm, 9, (CHAIN_X[1], cy + 34 * cos(t), CAM_Z + 34 * sin(t)), 'X', I['hole'], h=.3, seg=16)
    hex_bolt(bm, (CHAIN_X[1], cy, CAM_Z), 'X', I['steel'], s=17, h=8)
    disk(bm, 2.5, (CHAIN_X[1], cy, CAM_Z + 46), 'X', I['steel'], h=.4, seg=10)     # 正时记号
    name = 'E17_CamIntake' if is_in else 'E18_CamExhaust'
    finish(name, 17 if is_in else 18, bm, mats, ex)


def build_cam_ladder(M, ex):
    mats, I = mats_of(M, 'alu', 'steel', 'alu_mach')
    bm = bmesh.new()
    z0, z1 = LADDER_Z
    x0, x1 = JOURNAL_X[-1] - 14, JOURNAL_X[0] + 14
    for sy in (-1, 1):
        cy = sy * CAM_Y
        # 纵梁：外侧、内侧各一根
        for k in (-1, 1):
            ya, yb = sorted((cy + k * 22, cy + k * 30))
            boxf(bm, (x0, ya, z0), (x1, yb, z0 + 10), I['alu'])
        for jx in JOURNAL_X:
            prof = [(cy - 26, z0), (cy - 13.5, z0)] + arc_pts(cy, z0, 13.5, pi, 0, 16)[1:-1] + \
                [(cy + 13.5, z0), (cy + 26, z0), (cy + 26, z0 + 8)] + arc_pts(cy, z0, 26, 0, pi, 20)[4:-4] + [(cy - 26, z0 + 8)]
            yz_extrude(bm, [prof], jx - 9, jx + 9, I['alu'])
            for s in (-1, 1):
                fs = extrude(bm, [hexagon(5.5)], 0, 6, I['steel'])
                xform(bm, fs, Matrix.Translation(Vector((jx, cy + s * 21, z0 + 13))))
    # 横向拉筋：把进、排气两边连成一块
    for jx in (JOURNAL_X[0], JOURNAL_X[2], JOURNAL_X[-1]):
        boxf(bm, (jx - 5, -CAM_Y + 22, z0), (jx + 5, CAM_Y - 22, z0 + 8), I['alu'])
    finish('E19_CamLadder', 19, bm, mats, ex)


# ---------------------------------------------------------------- 正时、气门室盖、点火
CHAIN_CIRCLES = ((0.0, 0.0, 27.0), (-CAM_Y, CAM_Z, 53.5), (CAM_Y, CAM_Z, 53.5))   # (y, z, 节圆半径)
TCOVER_X = (BLK_X[1], 256.0)


def chain_loop():
    return resample(circle_hull(CHAIN_CIRCLES, 72), 3.0)


def chain_spans():
    """链条左右两段直线：(起点, 终点, 向外法线)，起点在曲轴那头"""
    pts = circle_hull(CHAIN_CIRCLES, 72)
    n = len(pts)
    segs = []
    for k in range(n):
        p0, p1 = pts[k], pts[(k + 1) % n]
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if L > 80:
            nrm = ((p1[1] - p0[1]) / L, -(p1[0] - p0[0]) / L)      # 逆时针多边形的外法线
            if p0[1] > p1[1]:
                p0, p1 = p1, p0
            segs.append((p0, p1, nrm))
    segs.sort(key=lambda s: s[0][0] + s[1][0])
    return [s for s in segs if abs(s[2][0]) > .5]      # 只要左右两段（不要两个凸轮链轮之间那段）


def build_chain(M, ex):
    mats, I = mats_of(M, 'chain', 'steel')
    bm = bmesh.new()
    loop = chain_loop()
    yz_extrude(bm, [offset_loop(loop, 4.5), offset_loop(loop, -4.5)[::-1]], CHAIN_X[0] + 1, CHAIN_X[1] - 1, I['chain'])
    pins = resample(circle_hull(CHAIN_CIRCLES, 72), 8.0)
    for (py, pz) in pins:
        rod(bm, 2.2, CHAIN_X[0] - .5, CHAIN_X[1] + .5, I['steel'], 'X', (0, py, pz), seg=8)
    finish('E24_TimingChain', 24, bm, mats, ex)


def build_chain_guides(M, ex):
    mats, I = mats_of(M, 'orange', 'plastic', 'alu', 'steel', 'hole')
    bm = bmesh.new()
    for k, (p0, p1, nrm) in enumerate(chain_spans()):
        a = [p0[0] + (p1[0] - p0[0]) * .08, p0[1] + (p1[1] - p0[1]) * .08]
        b = [p0[0] + (p1[0] - p0[0]) * .9, p0[1] + (p1[1] - p0[1]) * .9]
        bow = 3.0 if k == 0 else 0.0           # 张紧边的导轨稍微压弯一点
        pts_in, pts_out = [], []
        for j in range(13):
            t = j / 12
            off = bow * sin(pi * t)
            py, pz = a[0] + (b[0] - a[0]) * t - nrm[0] * off, a[1] + (b[1] - a[1]) * t - nrm[1] * off
            pts_in.append((py + nrm[0] * 5, pz + nrm[1] * 5))
            pts_out.append((py + nrm[0] * 12, pz + nrm[1] * 12))
        yz_extrude(bm, [pts_in + pts_out[::-1]], CHAIN_X[0] - 4, CHAIN_X[1] + 4, I['orange'])
        back = [(p[0] + nrm[0] * 6, p[1] + nrm[1] * 6) for p in pts_out]
        yz_extrude(bm, [pts_out + back[::-1]], CHAIN_X[0] - 2, CHAIN_X[1] + 2, I['plastic'])
        for t in ((.1, ) if k == 0 else (.12, .88)):
            q = pts_out[int(t * 12)]
            rod(bm, 5, TCOVER_X[0] + 1, CHAIN_X[1] + 6, I['steel'], 'X', (0, q[0] + nrm[0] * 3, q[1] + nrm[1] * 3), seg=12)
        if k == 0:
            # 液压张紧器：缸体前端面上的油缸，柱塞顶住导轨背面
            q = pts_out[8]
            c = Vector((CHAIN_X[0] + 5, q[0] + nrm[0] * 28, q[1] + nrm[1] * 28))
            d = Vector((0, -nrm[0], -nrm[1]))
            rod_dir(bm, 11, 0, 30, I['alu'], c, d, seg=20)
            rod_dir(bm, 6, 30, 38, I['steel'], c, d, seg=16)
            boxf(bm, (TCOVER_X[0] + 1, c.y - 16, c.z - 7), (TCOVER_X[0] + 8, c.y + 16, c.z + 7), I['alu'])
    finish('E25_ChainGuides', 25, bm, mats, ex)


def tcover_outline():
    pts = circle_hull(((0.0, 0.0, 66.0), (-CAM_Y, CAM_Z, 68.0), (CAM_Y, CAM_Z, 68.0)), 48)
    return hull(pts + [(-118.0, PAN_TOP), (118.0, PAN_TOP)])


def build_timing_cover(M, ex):
    mats, I = mats_of(M, 'alu', 'steel', 'hole', 'alu_mach')
    bm = bmesh.new()
    out = resample(tcover_outline(), 6.0)
    x0, x1 = TCOVER_X
    yz_extrude(bm, [out, offset_loop(out, -6)[::-1]], x0, x1 - 6, I['alu'])
    yz_extrude(bm, [out, circle(0, 0, 22, 32)], x1 - 6, x1, I['alu'])
    tube(bm, 20.5, 30, x1, x1 + 6, I['alu_mach'], 'X', seg=32)           # 曲轴前油封座
    # 加强筋、水泵座、张紧轮座
    for (y0, z0, y1, z1) in ((-40, 60, -95, 260), (40, 60, 95, 260), (-30, 300, 30, 300)):
        L = math.hypot(y1 - y0, z1 - z0)
        ny, nz = -(z1 - z0) / L * 3, (y1 - y0) / L * 3
        yz_extrude(bm, [[(y0 - ny, z0 - nz), (y1 - ny, z1 - nz), (y1 + ny, z1 + nz), (y0 + ny, z0 + nz)]], x1, x1 + 5, I['alu'])
    tube(bm, 0, 46, x1, x1 + 4, I['alu'], 'X', (0, 60, 150), seg=40)
    tube(bm, 0, 28, x1, x1 + 4, I['alu'], 'X', (0, -55, 92), seg=32)
    # 周边一圈 M6 螺栓
    for (py, pz) in resample(offset_loop(tcover_outline(), -10), 60.0):
        hex_bolt(bm, (x1, py, pz), 'X', I['steel'], s=10, h=5)
    finish('E26_TimingCover', 26, bm, mats, ex)


VCOVER_Z = (CAM_Z, 392.0, 412.0, COVER_TOP)
FILLER = (-93.0, -55.0)


def build_valve_cover(M, ex):
    mats, I = mats_of(M, 'plastic', 'rubber', 'steel', 'hole', 'yellow', 'white')
    bm = bmesh.new()
    z0, z1, z2, z3 = VCOVER_Z
    extrude(bm, [rrect(212, HEAD_W - 2, 14), rrect(204, HEAD_W - 10, 10)[::-1]], z0 + 2, z1, I['plastic'])
    extrude(bm, [rrect(212, HEAD_W - 2, 14), rrect(204, HEAD_W - 10, 10)[::-1]], z0, z0 + 2, I['rubber'])
    extrude(bm, [rrect(208, HEAD_W - 6, 16)], z1, z2, I['plastic'])
    coil_holes = [circle(cx, 0, 13, 32) for cx in CYL_X]
    extrude(bm, [rrect(192, 86, 22)] + coil_holes, z2, z3, I['plastic'])
    for cx in CYL_X:
        tube(bm, 13, 15.5, z1, z3 + 1.5, I['plastic'], 'Z', (cx, 0, 0), seg=32)
        disk(bm, 13, (cx, 0, z1 + 2), 'Z', I['hole'], h=.3, seg=24)
    # 顶上的加强筋
    for y in (-72, 72):
        boxf(bm, (-170, y - 2.5, z3), (170, y + 2.5, z3 + 4), I['plastic'])
    # 12 颗带橡胶垫圈的螺栓
    for x in (-180.0, -93.0, 0.0, 93.0, 180.0):
        for s in (-1, 1):
            tube(bm, 0, 9, z2, z2 + 1.5, I['rubber'], 'Z', (x, s * 97, 0), seg=16)
            hex_bolt(bm, (x, s * 97, z2 + 1.5), 'Z', I['steel'], s=10, h=5, washer=False)
    for x in (-199.0, 199.0):
        tube(bm, 0, 9, z2, z2 + 1.5, I['rubber'], 'Z', (x, 0, 0), seg=16)
        hex_bolt(bm, (x, 0, z2 + 1.5), 'Z', I['steel'], s=10, h=5, washer=False)
    # 机油加注盖（黄）
    knurl(bm, 21, z3, z3 + 16, I['yellow'], 'Z', (FILLER[0], FILLER[1], 0), n=24, depth=1.2)
    flat(bm, [rrect(9, 3, 1.5, cx=FILLER[0], cy=FILLER[1])], z3 + 16, I['hole'], h=.3)
    # PCV 阀管嘴
    rod_dir(bm, 7, 0, 22, I['plastic'], (150, 70, z3 - 6), (0, .6, .8), seg=16)

    def label(b2):
        # 文字先在 X 方向反着建，导出时整体镜像后才是正的
        n0 = len(b2.verts)
        text(b2, 'DOHC 16V', 24, 0, 0, 0, I['white'], h=1.0)
        b2.verts.ensure_lookup_table()
        vs = [b2.verts[k] for k in range(n0, len(b2.verts))]
        sx = -1 if MIRROR_X else 1
        bmesh.ops.transform(b2, matrix=Matrix.Translation((93, 34, z3)) @ Matrix.Scale(sx, 4, (1, 0, 0)), verts=vs)
        if MIRROR_X:
            bmesh.ops.reverse_faces(b2, faces=list({f for v in vs for f in v.link_faces}))
    label(bm)
    finish('E27_ValveCover', 27, bm, mats, ex)


def build_coil(M, i, ex):
    mats, I = mats_of(M, 'plastic', 'rubber', 'steel', 'hole', 'red')
    bm = bmesh.new()
    cx = CYL_X[i]
    z3 = COVER_TOP
    rod(bm, 12.5, 296, 330, I['rubber'], 'Z', (cx, 0, 0), seg=24)            # 橡胶护套（套在火花塞上）
    rod(bm, 10.5, 330, z3 + 2, I['plastic'], 'Z', (cx, 0, 0), seg=24)
    extrude(bm, [rrect(23, 15, 6, cx=cx)], z3 + 2, z3 + 26, I['plastic'])
    # 插头（朝进气侧）+ 固定耳
    boxf(bm, (cx - 9, -29, z3 + 8), (cx + 9, -15, z3 + 22), I['plastic'])
    boxf(bm, (cx - 6.5, -29.3, z3 + 11), (cx + 6.5, -29, z3 + 19), I['red'])
    yz_extrude(bm, [rrect(8, 3, 1.5, cx=0, cy=z3 + 4)], cx + 20, cx + 40, I['plastic'])
    hex_bolt(bm, (cx + 32, 0, z3 + 7), 'Z', I['steel'], s=10, h=5)
    finish(f'E{33 + i}_Coil{i + 1}', 33 + i, bm, mats, ex)


def build_spark_plug(M, i, ex):
    mats, I = mats_of(M, 'steel', 'ceramic', 'forged', 'copper')
    bm = bmesh.new()
    cx = CYL_X[i]
    zt = CAM_Z - VALVE_S_CAM * cos(VALVE_ANG)      # 燃烧室顶（气门盘那个高度）
    rod(bm, 1.2, zt - 4, zt, I['steel'], 'Z', (cx, 0, 0), seg=8)               # 中心电极
    boxf(bm, (cx - 1.2, -1.2, zt - 5.5), (cx + 1.2, 4.5, zt - 4), I['steel'])   # 侧电极
    boxf(bm, (cx - 1.2, 3.3, zt - 5.5), (cx + 1.2, 4.5, zt), I['steel'])
    rev(bm, [(0, zt), (6, zt), (6, zt + 19), (5.2, zt + 19)], I['steel'], 'Z', (cx, 0, 0), seg=24)
    for k in range(9):                                                          # 螺纹
        tube(bm, 5.4, 6.25, zt + 1.5 + k * 1.9, zt + 2.3 + k * 1.9, I['steel'], 'Z', (cx, 0, 0), seg=24)
    tube(bm, 5, 8, zt + 19, zt + 21, I['copper'], 'Z', (cx, 0, 0), seg=24)      # 密封垫圈
    fs = extrude(bm, [hexagon(8.1)], zt + 21, zt + 33, I['forged'])
    xform(bm, fs, Matrix.Translation(Vector((cx, 0, 0))))
    prof = [(0, zt + 33), (6.5, zt + 33)]
    for k in range(5):
        z = zt + 36 + k * 6
        prof += [(6.5, z), (5.4, z + 3)]
    prof += [(5.4, zt + 70), (4.5, zt + 72), (0, zt + 72)]
    rev(bm, prof, I['ceramic'], 'Z', (cx, 0, 0), seg=32)
    rod(bm, 2.6, zt + 72, zt + 78, I['steel'], 'Z', (cx, 0, 0), seg=12)
    finish(f'E{37 + i}_SparkPlug{i + 1}', 37 + i, bm, mats, ex)


# ---------------------------------------------------------------- 进气、燃油
PLENUM = (-230.0, 175.0, 46.0)          # 稳压腔中心 (y, z) 和半径，沿 X
PLENUM_X = (-185.0, 185.0)
RAIL = (-145.0, 258.0)                  # 油轨 (y, z)


def runner_path(cx):
    ctrl = [Vector((cx, -HEAD_W - 4, 292)), Vector((cx, -160, 318)), Vector((cx, -212, 318)),
            Vector((cx, -250, 285)), Vector((cx, -262, 232)), Vector((cx, PLENUM[0] - 8, PLENUM[1] + 10))]
    return catmull(ctrl, 8)


def build_intake(M, ex):
    mats, I = mats_of(M, 'plastic', 'hole', 'steel', 'alu')
    bm = bmesh.new()
    py, pz, pr = PLENUM
    rev(bm, [(0, PLENUM_X[0]), (pr - 8, PLENUM_X[0]), (pr, PLENUM_X[0] + 8), (pr, PLENUM_X[1] - 4), (pr + 4, PLENUM_X[1] - 4),
             (pr + 4, PLENUM_X[1]), (0, PLENUM_X[1])], I['plastic'], 'X', (0, py, pz), seg=48)
    for cx in CYL_X:
        sweep(bm, [Vector(p) for p in runner_path(cx)], 21, I['plastic'], sides=20)
    # 缸盖法兰（一整块，4 个口 + 8 颗螺栓）
    fl = rrect(205, 24, 8, cx=0, cy=292)
    holes = [stadium(cx, 292, 6, 15) for cx in CYL_X]
    fs = extrude(bm, [fl] + holes, 0, 10, I['plastic'])
    xform(bm, fs, Matrix.Translation(Vector((0, -HEAD_W, 0))) @ ROT['-Y'])
    for cx in CYL_X:
        for dx in (-34, 34):
            hex_bolt(bm, (cx + dx, -HEAD_W - 10, 292 + (16 if dx > 0 else -16)), '-Y', I['steel'], s=12, h=6)
    # 真空管嘴（接刹车助力泵）
    rod_dir(bm, 5, 0, 24, I['plastic'], (-60, py - pr + 6, pz + 20), (0, -.7, .7), seg=12)
    finish('E28_IntakeManifold', 28, bm, mats, ex)


def build_throttle(M, ex):
    mats, I = mats_of(M, 'alu', 'hole', 'plastic', 'steel', 'alu_mach')
    bm = bmesh.new()
    py, pz, pr = PLENUM
    x0 = PLENUM_X[1]
    rev(bm, [(30, x0), (40, x0), (40, x0 + 8), (33, x0 + 8), (33, x0 + 44), (36, x0 + 44), (36, x0 + 50), (30, x0 + 50)],
        I['alu'], 'X', (0, py, pz), seg=40, closed=True)
    yz_extrude(bm, [circle(py, pz, 30, 40)], x0 + 2, x0 + 3, I['hole'])
    # 节气门阀片（半开）
    fs = extrude(bm, [circle(0, 0, 29.5, 32)], -.8, .8, I['alu_mach'])
    xform(bm, fs, Matrix.Translation(Vector((x0 + 25, py, pz))) @ Matrix.Rotation(radians(60), 4, 'Z') @ ROT['X'])
    rod(bm, 3, x0 + 25 - 2, x0 + 25 + 2, I['steel'], 'X', (0, py, pz))
    # 电机壳 + 位置传感器插头
    boxf(bm, (x0 + 10, py + 22, pz + 26), (x0 + 42, py + 52, pz + 56), I['alu'])
    rod(bm, 15, x0 + 8, x0 + 46, I['alu'], 'X', (0, py + 36, pz + 38), seg=24)
    boxf(bm, (x0 + 18, py - 40, pz - 12), (x0 + 36, py - 30, pz + 12), I['plastic'])
    for (dy, dz) in ((-32, -28), (32, -28), (-32, 28), (32, 28)):
        hex_bolt(bm, (x0 + 8, py + dy * .9, pz + dz * .9), 'X', I['steel'], s=10, h=5)
    finish('E29_ThrottleBody', 29, bm, mats, ex)


def build_fuel_rail(M, ex):
    mats, I = mats_of(M, 'steel', 'plastic', 'rubber', 'hole', 'alu')
    bm = bmesh.new()
    ry, rz = RAIL
    rod(bm, 9, -178, 178, I['steel'], 'X', (0, ry, rz), seg=20)
    rod(bm, 5, -200, -178, I['steel'], 'X', (0, ry, rz), seg=12)          # 进油接头
    rod(bm, 7, -206, -198, I['plastic'], 'X', (0, ry, rz), seg=12)
    for bx in (-93.0, 93.0):                                                # 固定支架（螺栓拧到缸盖上）
        yz_extrude(bm, [[(ry - 4, rz + 6), (ry + 4, rz + 6), (-HEAD_W, 275), (-HEAD_W, 283)]], bx - 6, bx + 6, I['steel'])
        hex_bolt(bm, (bx, -HEAD_W - 1, 279), '-Y', I['steel'], s=12, h=6)
    for cx in CYL_X:
        a = Vector((cx, ry, rz))
        d = Vector((0, 12, 27)).normalized()
        rod_dir(bm, 8, 4, 22, I['alu'], a, d, seg=16)          # 喷油器座
        rod_dir(bm, 7.5, 22, 40, I['plastic'], a, d, seg=16)
        rod_dir(bm, 6.5, 40, 44, I['rubber'], a, d, seg=16)
        rod_dir(bm, 5, 44, 50, I['steel'], a, d, seg=12)
        boxf(bm, (cx - 5, ry - 20, rz + 14), (cx + 5, ry - 8, rz + 26), I['plastic'])     # 插头
    finish('E30_FuelRail', 30, bm, mats, ex)


# ---------------------------------------------------------------- 排气
COLLECT = (0.0, 222.0, 128.0)


def primary_path(cx):
    ctrl = [Vector((cx, HEAD_W + 8, 284)), Vector((cx, 160, 280)), Vector((cx * .75, 196, 236)),
            Vector((cx * .35, 216, 178)), Vector((0, COLLECT[1], COLLECT[2] + 6))]
    return catmull(ctrl, 8)


def build_exhaust(M, ex):
    mats, I = mats_of(M, 'rust', 'copper', 'steel')
    bm = bmesh.new()
    for cx in CYL_X:
        sweep(bm, [Vector(p) for p in primary_path(cx)], 17, I['rust'], sides=18)
        fs = extrude(bm, [rrect(30, 24, 6)], 0, 12, I['rust'])
        xform(bm, fs, Matrix.Translation(Vector((cx, HEAD_W, 284))) @ ROT['Y'])
        for dz in (-14, 14):
            rod(bm, 3.8, HEAD_W + 12, HEAD_W + 24, I['steel'], 'Y', (cx - 16 if dz < 0 else cx + 16, 0, 284 + dz), seg=10)
            fs = extrude(bm, [hexagon(7)], 0, 7, I['copper'])
            xform(bm, fs, Matrix.Translation(Vector((cx - 16 if dz < 0 else cx + 16, HEAD_W + 12, 284 + dz))) @ ROT['Y'])
    cy, cz = COLLECT[1], COLLECT[2]
    rev(bm, [(0, cz + 14), (30, cz + 14), (30, cz - 10), (24, cz - 38), (44, cz - 38), (44, cz - 48), (0, cz - 48)],
        I['rust'], 'Z', (0, cy, 0), seg=40)
    for k in range(3):
        t = 2 * pi * k / 3 + pi / 2
        rod(bm, 4, cz - 62, cz - 48, I['steel'], 'Z', (36 * cos(t), cy + 36 * sin(t), 0), seg=10)
    finish('E31_ExhaustManifold', 31, bm, mats, ex)


def build_heat_shield(M, ex):
    mats, I = mats_of(M, 'shield', 'steel')
    bm = bmesh.new()
    ctrl = [Vector((0, 128, 322)), Vector((0, 192, 314)), Vector((0, 240, 282)), Vector((0, 258, 232)), Vector((0, 258, 160))]
    line = [(p.y, p.z) for p in catmull(ctrl, 6)]
    n = len(line)
    for k in range(5):                      # 压出来的波纹：分 5 段，每段中间往外鼓一点
        xa, xb = -190 + k * 76, -190 + (k + 1) * 76 - 2
        bump = 2.5
        nrm = []
        for j in range(n):
            p0, p1 = line[max(j - 1, 0)], line[min(j + 1, n - 1)]
            L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            nrm.append(((p1[1] - p0[1]) / L, -(p1[0] - p0[0]) / L))
        outer = [(p[0] + nr[0] * (1.5 + bump), p[1] + nr[1] * (1.5 + bump)) for p, nr in zip(line, nrm)]
        inner = [(p[0] - nr[0] * 1.5, p[1] - nr[1] * 1.5) for p, nr in zip(line, nrm)]
        yz_extrude(bm, [outer + inner[::-1]], xa + 6, xb - 6, I['shield'])
        outer2 = [(p[0] + nr[0] * 1.5, p[1] + nr[1] * 1.5) for p, nr in zip(line, nrm)]
        yz_extrude(bm, [outer2 + inner[::-1]], xa, xb, I['shield'])
    for x in (-150.0, 0.0, 150.0):
        hex_bolt(bm, (x, 136, 322), 'Z', I['steel'], s=10, h=5)
    finish('E32_HeatShield', 32, bm, mats, ex)


# ---------------------------------------------------------------- 润滑
def build_oil_pan(M, ex):
    mats, I = mats_of(M, 'pan', 'steel', 'hole')
    bm = bmesh.new()
    z0 = PAN_TOP
    extrude(bm, [rrect(214, 124, 10), rrect(202, 112, 6)[::-1]], z0 - 6, z0, I['pan'])
    # 前面浅、后面深（集油槽在 2~4 缸下面）
    for (xa, xb, zb) in ((40.0, 205.0, -150.0), (-205.0, 44.0, PAN_BOT)):
        hw, c = (xb - xa) / 2, (xa + xb) / 2
        extrude(bm, [rrect(hw, 118, 12, cx=c), rrect(hw - 3, 115, 9, cx=c)[::-1]], zb + 3, z0 - 6, I['pan'])
        extrude(bm, [rrect(hw, 118, 12, cx=c)], zb, zb + 3, I['pan'])
    # 冲压加强筋
    for x in (-150.0, -80.0, -10.0):
        boxf(bm, (x - 4, -119, PAN_BOT + 20), (x + 4, -117, z0 - 16), I['pan'])
        boxf(bm, (x - 4, 117, PAN_BOT + 20), (x + 4, 119, z0 - 16), I['pan'])
    # 放油螺塞（后壁最低处）、16 颗 M6
    hex_bolt(bm, (-205, 0, PAN_BOT + 18), '-X', I['steel'], s=17, h=8)
    for (bx, by) in [(x, s * 119) for x in (-195, -130, -65, 0, 65, 130, 195) for s in (-1, 1)] + [(209, -60), (209, 60)]:
        hex_bolt(bm, (bx, by, z0 - 6), '-Z', I['steel'], s=10, h=5)
    finish('E03_OilPan', 3, bm, mats, ex)


def build_oil_pump(M, ex):
    mats, I = mats_of(M, 'alu', 'steel', 'hole', 'forged')
    bm = bmesh.new()
    z0 = PAN_TOP
    extrude(bm, [rrect(38, 36, 8, cx=158)], z0 - 40, z0 - 8, I['alu'])
    for (bx, by) in ((128, -28), (188, -28), (128, 28), (188, 28)):
        hex_bolt(bm, (bx, by, z0 - 40), '-Z', I['steel'], s=10, h=5)
    gear(bm, 16, 18, 22, 196, 203, I['forged'], c=(0, 0, z0 - 24))
    yz_extrude(bm, [circle(0, z0 - 24, 9, 16)], 190, 196, I['steel'])
    path = catmull([Vector((140, 0, z0 - 40)), Vector((70, 0, z0 - 52)), Vector((20, 0, z0 - 92)), Vector((-20, 0, PAN_BOT + 30))], 8)
    sweep(bm, [Vector(p) for p in path], 9, I['steel'], sides=14)
    # 集滤器（钢网）
    rev(bm, [(0, PAN_BOT + 12), (36, PAN_BOT + 12), (38, PAN_BOT + 16), (38, PAN_BOT + 22), (12, PAN_BOT + 32), (0, PAN_BOT + 32)],
        I['alu'], 'Z', (-20, 0, 0), seg=40)
    for k in range(4):
        tube(bm, 8 + k * 8, 10 + k * 8, PAN_BOT + 11.6, PAN_BOT + 12, I['hole'], 'Z', (-20, 0, 0), seg=40)
    finish('E41_OilPump', 41, bm, mats, ex)


FILTER_DIR = Vector((0, -cos(radians(30)), -sin(radians(30))))
FILTER_O = Vector((20, -SKIRT_W + 6, 50))


def build_oil_filter(M, ex):
    mats, I = mats_of(M, 'blue', 'steel', 'white')
    bm = bmesh.new()
    prof = [(12, 17), (36, 17), (38, 21), (38, 108), (34, 117), (0, 117), (0, 110), (12, 110)]
    rev_dir(bm, prof, I['blue'], FILTER_O, FILTER_DIR, seg=48, closed=True)
    rev_dir(bm, [(14, 16), (37, 16), (37, 21), (14, 21)], I['steel'], FILTER_O, FILTER_DIR, seg=48, closed=True)
    # 底部扳手位（多棱）
    fs = extrude(bm, [[(30 * cos(2 * pi * k / 30 + (pi / 30 if k % 2 else 0)) * (1 if k % 2 else .93),
                        30 * sin(2 * pi * k / 30) * (1 if k % 2 else .93)) for k in range(30)]], 108, 117.5, I['blue'])
    place(bm, fs, FILTER_O, FILTER_DIR)
    rev_dir(bm, [(38, 55), (38.4, 55), (38.4, 75), (38, 75)], I['white'], FILTER_O, FILTER_DIR, seg=48, closed=True)
    finish('E42_OilFilter', 42, bm, mats, ex)


def dipstick_path():
    return [Vector(p) for p in catmull([Vector((93, -SKIRT_W + 2, 40)), Vector((93, -150, 110)),
                                        Vector((93, -165, 230)), Vector((93, -172, 372))], 8)]


def build_dipstick(M, ex):
    mats, I = mats_of(M, 'steel', 'yellow')
    bm = bmesh.new()
    path = dipstick_path()
    sweep(bm, path + [path[-1] + (path[-1] - path[-2]).normalized() * 6], 2.4, I['steel'], sides=8)
    top = path[-1] + (path[-1] - path[-2]).normalized() * 6
    rod_dir(bm, 7, 0, 14, I['yellow'], top, (path[-1] - path[-2]), seg=16)
    ring = [Vector((93 + 16 * sin(2 * pi * k / 32), top.y, top.z + 14 + 16 + 16 * -cos(2 * pi * k / 32))) for k in range(32)]
    sweep(bm, ring, 4, I['yellow'], sides=10, closed=True)
    finish('E43_Dipstick', 43, bm, mats, ex)


# ---------------------------------------------------------------- 冷却、附件
WP = (60.0, 150.0, 50.0)          # 水泵皮带轮 (y, z, 半径)
ALT = (-195.0, 40.0, 27.5)        # 发电机皮带轮
TENS = (-90.0, 140.0, 35.0)       # 张紧轮
TENS_PIVOT = (-55.0, 92.0)
CRANK_PULLEY = (0.0, 0.0, 75.0)


def grooved_pulley(bm, r, y, z, mi, n=6, flange=True):
    prof = [(r - 12, BELT_X[0] - 2)]
    if flange:
        prof += [(r + 2, BELT_X[0] - 2), (r + 2, BELT_X[0])]
    w = (BELT_X[1] - BELT_X[0]) / n
    for k in range(n):
        x = BELT_X[0] + k * w
        prof += [(r, x), (r - 3.5, x + w / 2)]
    prof += [(r, BELT_X[1])]
    if flange:
        prof += [(r + 2, BELT_X[1]), (r + 2, BELT_X[1] + 2)]
    prof += [(r - 12, BELT_X[1] + 2)]
    rev(bm, prof, mi, 'X', (0, y, z), seg=64, closed=True)


def build_water_pump(M, ex):
    mats, I = mats_of(M, 'alu', 'steel', 'hole', 'iron')
    bm = bmesh.new()
    y, z, r = WP
    x1 = TCOVER_X[1]
    rev(bm, [(0, x1 + 4), (40, x1 + 4), (40, x1 + 9), (22, x1 + 14), (0, x1 + 14)], I['alu'], 'X', (0, y, z), seg=40)
    rod(bm, 9, x1 + 14, BELT_X[0], I['steel'], 'X', (0, y, z), seg=16)
    grooved_pulley(bm, r, y, z, I['iron'], flange=False)
    yz_extrude(bm, [circle(y, z, r - 12, 40)], BELT_X[1] - 4, BELT_X[1] + 2, I['iron'])
    for k in range(4):
        t = 2 * pi * k / 4
        hex_bolt(bm, (BELT_X[1] + 2, y + 18 * cos(t), z + 18 * sin(t)), 'X', I['steel'], s=10, h=5)
        hex_bolt(bm, (x1 + 9, y + 33 * cos(t + pi / 4), z + 33 * sin(t + pi / 4)), 'X', I['steel'], s=10, h=4)
    finish('E44_WaterPump', 44, bm, mats, ex)


def build_thermostat(M, ex):
    mats, I = mats_of(M, 'alu', 'steel', 'rubber')
    bm = bmesh.new()
    x0 = BLK_X[0] - 4
    rev(bm, [(0, 0), (30, 0), (30, 6), (24, 10), (24, 34), (0, 34)], I['alu'], '-X', (x0, 40, 285), seg=40)
    rod_dir(bm, 16, 0, 46, I['alu'], (x0 - 22, 40, 285), (0, .55, .83), seg=24)
    rod_dir(bm, 17.5, 38, 42, I['alu'], (x0 - 22, 40, 285), (0, .55, .83), seg=24)
    for (dy, dz) in ((-22, 0), (22, 0)):
        hex_bolt(bm, (x0 - 6, 40 + dy, 285 + dz), '-X', I['steel'], s=10, h=5)
    finish('E45_Thermostat', 45, bm, mats, ex)


def build_alternator(M, ex):
    mats, I = mats_of(M, 'alu', 'hole', 'iron', 'steel', 'plastic', 'red')
    bm = bmesh.new()
    y, z, r = ALT
    R = 62.0
    rev(bm, [(0, 112), (R - 6, 112), (R, 118), (R, 175), (R - 3, 178), (R - 3, 182), (R, 185), (R, 240), (R - 10, 250), (0, 250)],
        I['alu'], 'X', (0, y, z), seg=64)
    for k in range(16):                      # 散热窗
        t = 2 * pi * k / 16
        if k % 2:
            continue
        for (xa, xb) in ((122, 168), (192, 236)):
            boxf(bm, (xa, y + (R - 1.5) * cos(t) - 3, z + (R - 1.5) * sin(t) - 3),
                 (xb, y + (R - 1.5) * cos(t) + 3, z + (R - 1.5) * sin(t) + 3), I['hole'])
    rod(bm, 10, 250, BELT_X[0], I['steel'], 'X', (0, y, z), seg=16)
    grooved_pulley(bm, r, y, z, I['iron'])
    fs = extrude(bm, [hexagon(10)], BELT_X[1] + 2, BELT_X[1] + 10, I['steel'])
    xform(bm, fs, Matrix.Translation(Vector((0, y, z))) @ ROT['X'])
    # 安装耳（夹在缸体前端的支架上）
    for (xa, xb) in ((182, 206), (118, 134)):
        yz_extrude(bm, [[(y + R - 12, z - 18), (-150, z - 14), (-150, z + 14), (y + R - 12, z + 18)]], xa, xb, I['alu'])
        rod(bm, 7, xa - 3, xb + 3, I['steel'], 'X', (0, -155, z), seg=12)
    # B+ 输出端子、插头
    rod(bm, 5, 105, 112, I['steel'], 'X', (0, y - 25, z + 20), seg=12)
    boxf(bm, (98, y + 10, z - 12), (112, y + 30, z + 6), I['plastic'])
    fs = extrude(bm, [hexagon(6)], 98, 104, I['red'])
    xform(bm, fs, Matrix.Translation(Vector((0, y - 25, z + 20))) @ ROT['X'])
    finish('E46_Alternator', 46, bm, mats, ex)


STARTER = (-175.0, -60.0, 38.0)
PINION = (150 * cos(radians(215)), 150 * sin(radians(215)))


def build_starter(M, ex):
    mats, I = mats_of(M, 'plastic', 'alu', 'steel', 'forged', 'copper')
    bm = bmesh.new()
    y, z, R = STARTER
    rev(bm, [(0, -200), (R - 8, -200), (R, -192), (R, -82), (R - 6, -76), (0, -76)], I['plastic'], 'X', (0, y, z), seg=48)
    rev(bm, [(0, -215), (R + 2, -215), (R + 2, -200), (0, -200)], I['alu'], 'X', (0, y, z), seg=48)
    # 电磁开关（上面那个小筒）+ 接线柱
    sy, sz = y - 4, z + 50
    rev(bm, [(0, -205), (22, -205), (22, -110), (18, -104), (0, -104)], I['alu'], 'X', (0, sy, sz), seg=40)
    rod(bm, 4, -104, -94, I['copper'], 'X', (0, sy + 8, sz + 8), seg=12)
    rod(bm, 4, -104, -94, I['copper'], 'X', (0, sy - 8, sz - 6), seg=12)
    # 鼻端壳 + 小齿轮（伸到飞轮齿圈旁边）
    yz_extrude(bm, [hull(circle(y, z, R + 2, 32) + circle(sy, sz, 22, 24) + circle(PINION[0], PINION[1], 20, 24))], -226, -215, I['alu'])
    yz_extrude(bm, [circle(PINION[0], PINION[1], 8, 16)], -232, -226, I['steel'])
    gear(bm, 9, 9.5, 13, -240, -232, I['forged'], c=(0, PINION[0], PINION[1]))
    for (dy, dz) in ((-34, 12), (24, -30)):
        hex_bolt(bm, (-215, y + dy, z + dz), 'X', I['steel'], s=15, h=8)
    finish('E47_Starter', 47, bm, mats, ex)


BELT_PULLEYS = (CRANK_PULLEY, ALT, TENS, WP)


def build_belt(M, ex):
    mats, I = mats_of(M, 'rubber',)
    bm = bmesh.new()
    inner = resample(circle_hull([(p[0], p[1], p[2] - 2) for p in BELT_PULLEYS], 64), 3.0)
    yz_extrude(bm, [offset_loop(inner, 5), inner[::-1]], BELT_X[0] + .5, BELT_X[1] - .5, I['rubber'])
    finish('E48_Belt', 48, bm, mats, ex)


def build_tensioner(M, ex):
    mats, I = mats_of(M, 'alu', 'plastic', 'steel', 'forged')
    bm = bmesh.new()
    y, z, r = TENS
    py, pz = TENS_PIVOT
    x1 = TCOVER_X[1]
    rev(bm, [(8, BELT_X[0] - 1), (r, BELT_X[0] - 1), (r, BELT_X[1] + 1), (8, BELT_X[1] + 1)], I['plastic'], 'X', (0, y, z), seg=48, closed=True)
    rod(bm, 10, BELT_X[0] - 4, BELT_X[1] + 4, I['steel'], 'X', (0, y, z), seg=20)
    hex_bolt(bm, (BELT_X[1] + 4, y, z), 'X', I['steel'], s=13, h=6)
    L = math.hypot(y - py, z - pz)
    ny, nz = -(z - pz) / L * 11, (y - py) / L * 11
    yz_extrude(bm, [[(py - ny, pz - nz), (y - ny, z - nz), (y + ny, z + nz), (py + ny, pz + nz)]], BELT_X[0] - 8, BELT_X[0] - 2, I['forged'])
    rev(bm, [(0, x1), (26, x1), (26, BELT_X[0] - 2), (0, BELT_X[0] - 2)], I['alu'], 'X', (0, py, pz), seg=40)
    hex_bolt(bm, (BELT_X[0] - 2, py, pz), 'X', I['steel'], s=13, h=6)
    finish('E49_Tensioner', 49, bm, mats, ex)


# ---------------------------------------------------------------- 组装（建模顺序 = 接口依赖顺序）
# 爆炸路线（毫米，接口参数表的坐标：+X = 正时端、-Y = 进气侧 / 玩家那边；最后一个数 = 出场时刻 0~1）。
# 每段位移在总进度 T 的 [0.6s, 0.6s + 0.4] 里缓动走完，几段叠加。按真实拆机顺序：
#   附件（皮带 → 张紧轮 → 发电机、水泵、皮带轮）→ 起动机、机滤、机油尺 → 点火线圈、火花塞 → 进气（节气门 → 歧管 → 油轨）
#   → 排气（隔热罩 → 歧管）→ 正时（罩盖 → 导轨 → 链条）→ 气门室盖 → 承盖架 → 凸轮轴 → 飞轮 → 缸盖（连气门）→ 缸垫
#   → 油底壳 → 活塞、连杆从缸孔往上推出 → 机油泵 → 主轴承梁 → 曲轴
# 摆法（桌面 160 × 70cm，模型缩放约 0.9；导出时 X 镜像，+X 在玩家左手边）：
#   左边（+X）：正时端的一串（皮带最远，皮带轮、水泵、张紧轮、发电机，正时罩盖、导轨、链条依次靠近缸体），机油泵在最下面；
#              点火线圈、火花塞排在它们上方
#   右边（-X）：飞轮、起动机、节温器、排气歧管，隔热罩在歧管上方，气门室盖在最上面
#   后面（+Y）：缸盖退后 30cm，气门浮在缸盖上方，再上面是两根凸轮轴、承盖架
#   缸体正上方：连杆（下）、活塞（上），一缸一列；缸垫浮在最上面，透过 4 个缸口看得到活塞
#   前面（-Y）：下半截像抽屉一样往玩家这边拉出 29cm，从下到上按装配顺序叠着：油底壳（贴桌面）、主轴承梁、曲轴；
#              再上面是油轨、进气歧管和节气门
HEAD_MOVE = (0, 300, 40)


def _ex():
    e = dict(
        belt=[(380, 0, 0, .00)],
        dipstick=[(0, -8, 200, .02)],
        tens=[(270, 0, 0, .04)],
        alt=[(270, -60, 0, .05)],
        wpump=[(270, 0, 0, .06)],
        pulley=[(270, 0, 0, .07)],
        filter=[tuple(FILTER_DIR * 60) + (.08,), (-330, 0, 80, .15)],
        starter=[(-200, -60, 0, .10)],
        shield=[(0, 70, 40, .11), (-440, 0, 180, .16)],
        thermo=[(-130, 0, 40, .12)],
        exhaust=[(0, 70, 0, .13), (-440, 0, 0, .18)],
        throttle=[(60, 0, 0, .14), (0, -120, 260, .20)],
        tcover=[(160, 0, 0, .18)],
        intake=[(0, -120, 0, .22), (0, 0, 260, .27)],
        guides=[(110, 0, 0, .24)],
        chain=[(60, 0, 0, .28)],
        vcover=[(0, 0, 120, .30), (-440, 200, 90, .36)],
        rail=[(0, -120, 0, .32), (0, 0, 60, .36)],
        ladder=[(0, 0, 315, .40), (0, 300, 0, .45)],
        cam_in=[(0, 0, 246, .44), (0, 300, 0, .50)],
        cam_ex=[(0, 0, 246, .46), (0, 300, 0, .50)],
        flywheel=[(-170, 0, 0, .50)],
        head=[HEAD_MOVE + (.52,)],
        gasket=[(0, 0, 328, .62)],
        pan=[(0, -290, 0, .66)],
        pump=[(260, 0, 0, .84)],
        bedplate=[(0, 0, -40, .84), (0, -290, 70, .88)],
        crank=[(0, 0, -80, .90), (0, -290, 0, .94), (0, 0, 250, .99)],
    )
    for i, cx in enumerate(CYL_X):
        e[f'coil{i}'] = [(0, 0, 200, .10 + .01 * i), (500, -80, 0, .14 + .01 * i)]
        e[f'plug{i}'] = [(0, 0, 200, .20 + .01 * i), (500, 40, 0, .26 + .01 * i)]
        e[f'valves{i}'] = [HEAD_MOVE + (.52,), (0, 0, 150, .58 + .01 * i)]
        # 活塞、连杆往上推出缸孔：活塞都停在 450~506，连杆停在 230~422（一缸一列，对得上自己的缸）
        zc = piston_pin_z(i) + COMP_H
        e[f'piston{i}'] = [(0, 0, 506 - zc, .74 + .01 * i)]
        zs = crank_pin(i)[1] + ROD_L
        e[f'rod{i}'] = [(0, 0, 406 - zs, .80 + .01 * i)]
    return e


EX = _ex()
HIDE = [a.split('=', 1)[1] for a in ARGV if a.startswith('--hide=')]
HIDE = HIDE[0].split(',') if HIDE else []


def build_all(M):
    build_block(M)
    build_bedplate(M, EX.get('bedplate', ()))
    build_crank(M, EX.get('crank', ()))
    for i in range(4):
        build_conrod(M, i, EX.get(f'rod{i}', ()))
        build_piston(M, i, EX.get(f'piston{i}', ()))
    build_flywheel(M, EX.get('flywheel', ()))
    build_crank_pulley(M, EX.get('pulley', ()))
    build_gasket(M, EX.get('gasket', ()))
    build_head(M, EX.get('head', ()))
    for i in range(4):
        build_valves(M, i, EX.get(f'valves{i}', ()))
    build_camshaft(M, True, EX.get('cam_in', ()))
    build_camshaft(M, False, EX.get('cam_ex', ()))
    build_cam_ladder(M, EX.get('ladder', ()))
    build_chain(M, EX.get('chain', ()))
    build_chain_guides(M, EX.get('guides', ()))
    build_timing_cover(M, EX.get('tcover', ()))
    build_valve_cover(M, EX.get('vcover', ()))
    for i in range(4):
        build_coil(M, i, EX.get(f'coil{i}', ()))
        build_spark_plug(M, i, EX.get(f'plug{i}', ()))
    build_intake(M, EX.get('intake', ()))
    build_throttle(M, EX.get('throttle', ()))
    build_fuel_rail(M, EX.get('rail', ()))
    build_exhaust(M, EX.get('exhaust', ()))
    build_heat_shield(M, EX.get('shield', ()))
    build_oil_pan(M, EX.get('pan', ()))
    build_oil_pump(M, EX.get('pump', ()))
    build_oil_filter(M, EX.get('filter', ()))
    build_dipstick(M, EX.get('dipstick', ()))
    build_water_pump(M, EX.get('wpump', ()))
    build_thermostat(M, EX.get('thermo', ()))
    build_alternator(M, EX.get('alt', ()))
    build_starter(M, EX.get('starter', ()))
    build_belt(M, EX.get('belt', ()))
    build_tensioner(M, EX.get('tens', ()))


def preview(kind):
    """开发时看单个阶段的预览图（--preview=名字）"""
    set_engine('CYCLES')
    sc = bpy.context.scene
    sc.cycles.samples = 16
    views = dict(
        front=((.75, -1.35, .95), (0, 0, .1)),
        top=((.35, -.55, 1.25), (0, 0, .1)),
        under=((.9, -1.1, -.05), (0, 0, -.05)),
        rear=((1.1, 1.0, .7), (0, 0, .05)),
        side=((0, -1.4, .2), (0, 0, .05)),
        end=((-1.4, -.35, .25), (0, 0, .1)),
    )
    views.update(
        xfront=((1.0, -2.3, 1.55), (0, .05, .2)),
        xtop=((.3, -.9, 2.6), (0, .08, 0)),
        xleft=((-2.2, -1.2, 1.2), (0, .05, .15)),
        xright=((2.2, -1.3, 1.2), (0, .05, .15)),
        xback=((.8, 2.4, 1.4), (0, .05, .15)),
    )
    for v in kind.split(','):
        cam, tgt = views[v]
        render_still(f'pv_{v}.png', F_EXP[1] + 10 if v.startswith('x') else 1, 960, 600, cam, tgt, hide=HIDE)


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


def studio_world(nt, plain):
    """镜头直接看到的背景还是原来那片浅灰；反射里看到的换成"摄影棚"：头顶亮、往下渐暗，地平线上一圈亮带。
    金属表面就是一面模糊的镜子，环境有明暗过渡，曲面上才有高光和暗部，才读得出"这是金属、这里是圆角"；
    环境是一片均匀的灰，金属就只剩一片均匀的灰。脚本自己拼，不用下载 HDRI"""
    N, L = nt.nodes, nt.links
    out = next(n for n in N if n.type == 'OUTPUT_WORLD')
    tc = N.new('ShaderNodeTexCoord')
    sep = N.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Generated'], sep.inputs[0])           # 世界着色器里 Generated = 视线方向
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value, mr.inputs['From Max'].default_value = -1.0, 1.0
    L.new(sep.outputs['Z'], mr.inputs['Value'])
    ramp = N.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = .0, (.02, .02, .02, 1)
    el[1].position, el[1].color = 1.0, (1.1, 1.1, 1.12, 1)
    for pos, v in ((.47, .06), (.52, .75), (.56, .3), (.75, .55)):
        e = el.new(pos)
        e.color = (v, v, v * 1.02, 1)
    L.new(mr.outputs['Result'], ramp.inputs['Fac'])
    studio = N.new('ShaderNodeBackground')
    studio.inputs['Strength'].default_value = .6
    L.new(ramp.outputs['Color'], studio.inputs['Color'])
    lp = N.new('ShaderNodeLightPath')
    mix = N.new('ShaderNodeMixShader')
    L.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    L.new(studio.outputs[0], mix.inputs[1])
    L.new(plain.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs['Surface'])


def setup_world_and_cam():
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
        studio_world(w.node_tree, bg)
    bm = bmesh.new()
    box(bm, (0, 0, PAN_BOT - 5), (3000, 3000, 10), 0)
    me = bpy.data.meshes.new('Table')
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Scale(MM, 4))
    me.materials.append(principled('M_Table', '#7a6650', 0, .6))
    table = bpy.data.objects.new('Table', me)
    collection('Scene').objects.link(table)
    for name, loc, power, size in (('Key', (-.9, -1.3, 1.6), 140, 2.0), ('Fill', (1.5, -.9, .9), 50, 2.4),
                                   ('Rim', (.4, 1.6, 1.3), 90, 1.6)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, (0, 0, .1))
        collection('Scene').objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 50
    cam = bpy.data.objects.new('Cam', cd)
    cam.location = (.75, -1.35, .95)
    look_at(cam, (0.0, 0.0, .1))
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


def render_still(name, frame, w=1280, h=720, cam=None, target=None, samples=None, hide=()):
    sc = bpy.context.scene
    if cam:
        sc.camera.location = cam
        look_at(sc.camera, target)
    if samples:
        sc.cycles.samples = samples
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.frame_set(frame)
    hidden = [d['ob'] for d in OBJS if any(d['ob'].name.startswith(p) for p in hide)]
    for ob in hidden:
        ob.hide_render = True
    sc.render.filepath = os.path.join(OUT, name)
    try:
        sc.render.image_settings.file_format = 'PNG'
    except Exception:
        pass
    bpy.ops.render.render(write_still=True)
    for ob in hidden:
        ob.hide_render = False
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
    ROOT = bpy.data.objects.new('Engine', None)
    ROOT.empty_display_type = 'ARROWS'
    ROOT.empty_display_size = .05
    collection('Engine').objects.link(ROOT)
    build_all(M)
    setup_world_and_cam()
    animate_explode()
    viewport_defaults()
    export_glb(os.path.join(OUT, 'engine.glb'))
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'engine.blend'))
    print('[OK] saved engine.blend')
    tris = 0
    lo, hi = [1e9] * 3, [-1e9] * 3
    dg = bpy.context.evaluated_depsgraph_get()
    for d in OBJS:
        ev = d['ob'].evaluated_get(dg)
        me = ev.to_mesh()                    # 带倒角之后的网格（导出的就是它）
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        for v in me.vertices:
            lo = [min(a, b) for a, b in zip(lo, v.co)]
            hi = [max(a, b) for a, b in zip(hi, v.co)]
        ev.to_mesh_clear()
    size = [round((b - a) * 1000, 1) for a, b in zip(lo, hi)]
    print(f'[OK] {len(OBJS)} engine objects, {tris} triangles, size {size} mm, '
          f'x {lo[0] * 1000:.0f}..{hi[0] * 1000:.0f}  y {lo[1] * 1000:.0f}..{hi[1] * 1000:.0f}  z {lo[2] * 1000:.0f}..{hi[2] * 1000:.0f}')
    if DO_RENDER:
        set_engine('CYCLES')
        render_still('render_assembled.png', 1, cam=(.75, -1.35, .95), target=(0, 0, .1))
        render_still('render_exploded.png', F_EXP[1] + 10, cam=(1.4, -2.45, 1.8), target=(0, .05, .22))
        set_engine('EEVEE')
    for a in ARGV:
        if a.startswith('--preview='):
            preview(a.split('=', 1)[1])


main()
