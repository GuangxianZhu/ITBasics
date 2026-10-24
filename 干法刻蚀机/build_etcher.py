# 干法刻蚀机：工艺腔 PM1 + 两个机械手，Blender 脚本建模，导出 glb 给网页（以后也给 MyVRToyBox）。
#
#   blender -b -P build_etcher.py
#
# 坐标（Blender）：米，+Z 向上，地面 Z = 0；工艺腔轴线是 Z 轴；闸阀朝 -Y（导出成 glTF 后就是网页里的 +Z）。
# 晶圆传送面 Z = H = 0.95。尺寸和网页 web/app.js 里的一致（那边有同样的数字）。
# 每个物体名就是网页里的零件 id；"id__子名" 表示同一个零件里单独会动的部分（门、阀板、转子）。
# 机械手的连杆原点在关节，沿 +X 伸出；刀叉原点在晶圆中心。
import bpy, bmesh, math, os
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'output')
os.makedirs(OUT, exist_ok=True)
H = 0.95
PI = math.pi

bpy.ops.wm.read_factory_settings(use_empty=True)
COLL = bpy.context.scene.collection


# ---------------- 材质 ----------------
def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(h):
    return tuple(lin(((h >> s) & 255) / 255) for s in (16, 8, 0))


def mat(name, hexc, metal=0.0, rough=0.5, alpha=1.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*rgb(hexc), 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    return m


# 金属度都不超过 0.55（MyVRToyBox 的工作室没有反射探针，金属度高了发黑）
M = dict(
    anod=mat('阳极氧化铝', 0xa9b0b8, 0.35, 0.45),
    alu=mat('铝', 0xc8ced4, 0.5, 0.32),
    coat=mat('氧化钇涂层', 0xe9e4d6, 0.0, 0.7),
    steel=mat('不锈钢', 0xc4c7cb, 0.55, 0.22),
    white=mat('喷粉白', 0xeceeef, 0.0, 0.55),
    grey=mat('喷粉灰', 0x8d949c, 0.05, 0.5),
    frame=mat('机架灰', 0x6b737c, 0.15, 0.5),
    dark=mat('深灰塑料', 0x2a2e33, 0.0, 0.6),
    black=mat('黑色橡胶', 0x141618, 0.0, 0.75),
    ceramic=mat('氧化铝陶瓷', 0xf1ebdc, 0.0, 0.45),
    quartz=mat('石英', 0xeef4f8, 0.0, 0.08, 0.55),
    acrylic=mat('亚克力窗', 0xd8ecf5, 0.0, 0.05, 0.18),
    glasscap=mat('电容玻璃', 0xf3d9a0, 0.0, 0.1, 0.55),
    copper=mat('镀银铜', 0xd28a55, 0.55, 0.28),
    silicon=mat('硅', 0x3c424c, 0.45, 0.25),
    heater=mat('加热丝', 0xd9542b, 0.2, 0.5),
    coolant=mat('冷却液', 0x2f7fd6, 0.0, 0.4),
    hoseblue=mat('进水管', 0x2f6fc8, 0.0, 0.55),
    hosered=mat('出水管', 0xc8362f, 0.0, 0.55),
    hv=mat('高压线', 0xd23a2a, 0.0, 0.5),
    rfcable=mat('射频电缆', 0x1d2024, 0.0, 0.5),
    orange=mat('橙色光纤', 0xf08a2a, 0.0, 0.45),
    yellow=mat('警示黄', 0xf2c418, 0.0, 0.45),
    green=mat('光谱仪', 0x4a8f6a, 0.1, 0.45),
    screen=mat('屏幕', 0x0f2a24, 0.0, 0.25),
    led=mat('指示灯绿', 0x36e07a, 0.0, 0.3),
    cl2=mat('Cl2 色环', 0xb7d02a, 0.0, 0.45),
    hbr=mat('HBr 色环', 0x9b7bd6, 0.0, 0.45),
    o2=mat('O2 色环', 0x2f8fe0, 0.0, 0.45),
    ar=mat('Ar 色环', 0x2fb39a, 0.0, 0.45),
    valve=mat('气动阀蓝', 0x2f63b8, 0.1, 0.4),
    rotor=mat('转子', 0xb7bcc2, 0.55, 0.3),
)


# ---------------- 几何体 ----------------
def T(x, y, z):
    return Matrix.Translation((x, y, z))


def R(axis, a):
    return Matrix.Rotation(a, 4, axis)


def bm_box(sx, sy, sz, bev=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    if bev > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bev, sx / 3, sy / 3, sz / 3), offset_type='OFFSET',
                        segments=2, profile=0.5, affect='EDGES', clamp_overlap=True)
    return bm


def bm_rev(prof, seg=64):
    """截面 (r, z) 闭合折线绕 Z 轴转一圈。"""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in prof]
    es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * PI, steps=seg, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def bm_cyl(r, z0, z1, seg=48, c=0.0):
    if c > 0:
        return bm_rev([(0, z0), (r - c, z0), (r, z0 + c), (r, z1 - c), (r - c, z1), (0, z1)], seg)
    return bm_rev([(0, z0), (r, z0), (r, z1), (0, z1)], seg)


def bm_ring(ri, ro, z0, z1, seg=64, c=0.0):
    if c > 0:
        return bm_rev([(ri, z0), (ro - c, z0), (ro, z0 + c), (ro, z1 - c), (ro - c, z1), (ri, z1)], seg)
    return bm_rev([(ri, z0), (ro, z0), (ro, z1), (ri, z1)], seg)


def bm_torus(R0, r, z, seg=48, n=12):
    return bm_rev([(R0 + r * math.cos(2 * PI * k / n), z + r * math.sin(2 * PI * k / n)) for k in range(n)], seg)


def bm_hex(r, z0, z1):
    return bm_rev([(0, z0), (r, z0), (r, z1), (0, z1)], 6)


def curve_bm(points, r, extrude=0.0, res=2, cyclic=False):
    cu = bpy.data.curves.new('tmpc', 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (p[0], p[1], p[2], 1)
    sp.use_cyclic_u = cyclic
    cu.bevel_depth = r
    cu.bevel_resolution = res
    cu.extrude = extrude
    cu.use_fill_caps = True
    ob = bpy.data.objects.new('tmpc', cu)
    COLL.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return bm


def fillet(pts, rad, n=6):
    """折线拐角改成圆弧（管子、电缆用）。"""
    P = [Vector(p) for p in pts]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b = P[i - 1] - P[i], P[i + 1] - P[i]
        d = min(rad, a.length / 2, b.length / 2)
        A, B = P[i] + a.normalized() * d, P[i] + b.normalized() * d
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * A + 2 * (1 - t) * t * P[i] + t * t * B)
    out.append(P[-1])
    return [tuple(v) for v in out]


def pipe(pts, r, rad=0.05, res=2):
    return curve_bm(fillet(pts, rad), r, res=res)


class Part:
    def __init__(self, name, origin=(0, 0, 0)):
        self.name, self.origin = name, Vector(origin)
        self.bm = bmesh.new()
        self.mats = []

    def add(self, bm, m, M=None):
        if M is not None:
            bm.transform(M)
        if m not in self.mats:
            self.mats.append(m)
        idx = self.mats.index(m)
        for f in bm.faces:
            f.material_index = idx
            f.smooth = True
        me = bpy.data.meshes.new('t')
        bm.to_mesh(me)
        bm.free()
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        return self

    def build(self):
        me = bpy.data.meshes.new(self.name)
        self.bm.transform(T(*(-self.origin)))
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        try:
            me.set_sharp_from_angle(angle=math.radians(38))
        except Exception:
            pass
        ob = bpy.data.objects.new(self.name, me)
        ob.location = self.origin
        COLL.objects.link(ob)
        return ob


def around(n, phase=0.0):
    return [phase + 2 * PI * k / n for k in range(n)]


def bolts(part, n, r, z, hr=0.0075, hh=0.007, up=True, phase=0.0):
    for a in around(n, phase):
        z0, z1 = (z, z + hh) if up else (z - hh, z)
        part.add(bm_hex(hr, z0, z1), M['steel'], T(r * math.cos(a), r * math.sin(a), 0))


def slots(part, n, r, z, w, h, d, m, phase=0.0):
    """沿圆周的一圈深色格栅/槽（贴在表面上）。"""
    for a in around(n, phase):
        part.add(bm_box(d, w, h), m, T(r * math.cos(a), r * math.sin(a), z) @ R('Z', a))


# ================= 工艺腔 PM1 =================
# --- 机架 ---
p = Part('frame')
for x, y in ((-0.3, -0.3), (0.3, -0.3), (-0.3, 0.3), (0.3, 0.3)):
    p.add(bm_box(0.045, 0.045, 0.70, 0.004), M['frame'], T(x, y, 0.40))
    p.add(bm_box(0.012, 0.047, 0.66, 0), M['dark'], T(x, y, 0.40))            # 型材槽
    p.add(bm_cyl(0.028, 0.0, 0.018, 24, 0.003), M['black'], T(x, y, 0))        # 调平脚
    p.add(bm_cyl(0.008, 0.018, 0.05, 12), M['steel'], T(x, y, 0))
    p.add(bm_hex(0.016, 0.03, 0.042), M['steel'], T(x, y, 0))
for y in (-0.3, 0.3):
    p.add(bm_box(0.645, 0.045, 0.045, 0.004), M['frame'], T(0, y, 0.735))
    p.add(bm_box(0.645, 0.04, 0.04, 0.004), M['frame'], T(0, y, 0.22))
for x in (-0.3, 0.3):
    p.add(bm_box(0.045, 0.645, 0.045, 0.004), M['frame'], T(x, 0, 0.735))
# 升降针的气缸（固定在机架上）
p.add(bm_cyl(0.022, 0.40, 0.56, 24, 0.003), M['alu'], T(-0.12, 0.12, 0))
p.add(bm_cyl(0.008, 0.56, 0.60, 12), M['steel'], T(-0.12, 0.12, 0))
p.add(bm_box(0.24, 0.03, 0.012, 0.003), M['grey'], T(-0.12, 0.0, 0.42) @ R('Z', PI / 2))
p.build()

# --- 腔体（剖开时一起剖） ---
p = Part('chamber')
p.add(bm_rev([(0.32, 0.78), (0.372, 0.78), (0.372, 0.80), (0.345, 0.80), (0.345, 1.18), (0.372, 1.18), (0.372, 1.20), (0.32, 1.20)], 96), M['anod'])
p.add(bm_ring(0.316, 0.3205, 0.80, 1.18, 96), M['coat'])                      # 内壁涂层
p.add(bm_cyl(0.372, 0.76, 0.78, 96, 0.002), M['anod'])                        # 底板
for a in around(16, PI / 16):                                                 # 外壁加强筋
    p.add(bm_box(0.016, 0.006, 0.36, 0.0015), M['anod'], T(0.352 * math.cos(a), 0.352 * math.sin(a), 0.99) @ R('Z', a))
bolts(p, 32, 0.36, 1.20)                                                      # 上法兰螺栓
bolts(p, 24, 0.36, 0.78, up=False)                                            # 下法兰螺栓
for x in (-0.12, 0.12):                                                        # 开盖铰链（在后面 +Y）
    p.add(bm_box(0.05, 0.05, 0.06, 0.004), M['steel'], T(x, 0.395, 1.215))
p.add(bm_cyl(0.012, -0.16, 0.16, 16), M['steel'], T(0, 0.405, 1.235) @ R('Y', PI / 2))
p.add(bm_box(0.004, 0.07, 0.045, 0.001), M['yellow'], T(0.36 * math.cos(0.5), 0.36 * math.sin(0.5), 1.02) @ R('Z', 0.5))
p.build()

# --- 陶瓷介质窗 ---
p = Part('window')
p.add(bm_rev([(0, 1.20), (0.342, 1.20), (0.345, 1.203), (0.345, 1.232), (0.342, 1.235), (0, 1.235)], 96), M['ceramic'])
p.add(bm_torus(0.33, 0.003, 1.2005, 96, 8), M['black'])                       # O 形圈
p.build()

# --- 线圈：方截面铜带，内外两组，陶瓷支撑梳 ---
p = Part('coil')


def spiral(r0, r1, turns, z, a0=0.0):
    pts = []
    n = int(turns * 72)
    for i in range(n + 1):
        t = i / n
        a = a0 + t * turns * 2 * PI
        r = r0 + (r1 - r0) * t
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return pts


for (r0, r1, tn, a0) in ((0.065, 0.125, 2.0, 0.0), (0.185, 0.27, 2.25, PI)):
    pts = spiral(r0, r1, tn, 1.256, a0)
    p.add(curve_bm(pts, 0.0028, extrude=0.007, res=1), M['copper'])
    for q in (pts[0], pts[-1]):                                               # 引线往上到端子
        p.add(bm_box(0.012, 0.012, 0.19, 0.002), M['copper'], T(q[0], q[1], 1.35))
        p.add(bm_box(0.03, 0.03, 0.012, 0.003), M['copper'], T(q[0], q[1], 1.448))
for a in around(6, PI / 6):                                                   # 支撑梳
    c, s = math.cos(a), math.sin(a)
    p.add(bm_box(0.24, 0.016, 0.01, 0.002), M['ceramic'], T(0.165 * c, 0.165 * s, 1.243) @ R('Z', a))
    for r in (0.07, 0.095, 0.12, 0.19, 0.215, 0.24, 0.265):
        p.add(bm_box(0.006, 0.016, 0.014, 0.001), M['ceramic'], T(r * c, r * s, 1.255) @ R('Z', a))
p.build()

# --- 射频屏蔽罩（剖开时一起剖） ---
p = Part('rfcover')
p.add(bm_rev([(0.333, 1.235), (0.349, 1.235), (0.349, 1.45), (0.353, 1.452), (0.353, 1.465), (0.0, 1.465), (0.0, 1.455), (0.333, 1.455)], 96), M['white'])
slots(p, 40, 0.3495, 1.405, 0.012, 0.05, 0.003, M['dark'])                     # 散热格栅
p.add(bm_box(0.003, 0.06, 0.06, 0.001), M['yellow'], T(0.351, -0.12, 1.32) @ R('Z', -0.33))   # 射频警示牌
p.build()

# --- 源匹配器：前面是透明窗，能看到两个真空可变电容和电感 ---
p = Part('srcmatch')
cx, cy, z0, z1 = 0.0, 0.0, 1.47, 1.65
w, d = 0.36, 0.27
p.add(bm_box(w, 0.006, z1 - z0, 0.002), M['grey'], T(cx, cy + d / 2, (z0 + z1) / 2))       # 后板
for sx in (-1, 1):
    p.add(bm_box(0.006, d, z1 - z0, 0.002), M['grey'], T(cx + sx * w / 2, cy, (z0 + z1) / 2))
p.add(bm_box(w, d, 0.006, 0.002), M['grey'], T(cx, cy, z1))
p.add(bm_box(w, d, 0.006, 0.002), M['grey'], T(cx, cy, z0 + 0.003))
p.add(bm_box(w - 0.01, 0.004, z1 - z0 - 0.01, 0.001), M['acrylic'], T(cx, cy - d / 2, (z0 + z1) / 2))
for sx in (-1, 1):                                                            # 前框
    p.add(bm_box(0.012, 0.008, z1 - z0, 0.002), M['grey'], T(cx + sx * (w / 2 - 0.006), cy - d / 2, (z0 + z1) / 2))
for sx in (-1, 1):                                                            # 两个真空可变电容（横放）
    X = sx * 0.085
    p.add(bm_cyl(0.032, -0.05, 0.05, 32, 0.004), M['glasscap'], T(X, -0.02, 1.575) @ R('X', PI / 2))
    for e in (-1, 1):
        p.add(bm_cyl(0.036, -0.008, 0.008, 32, 0.002), M['copper'], T(X, -0.02 + e * 0.055, 1.575) @ R('X', PI / 2))
    p.add(bm_box(0.05, 0.05, 0.05, 0.004), M['dark'], T(X, 0.07, 1.575))              # 步进电机
    p.add(bm_cyl(0.006, -0.02, 0.02, 12), M['steel'], T(X, 0.035, 1.575) @ R('X', PI / 2))
helix = [(-0.04 + 0.08 * t / 200, 0.02 + 0.022 * math.cos(t / 200 * 5 * 2 * PI), 1.515 + 0.022 * math.sin(t / 200 * 5 * 2 * PI)) for t in range(201)]
p.add(curve_bm(helix, 0.004, res=2), M['copper'])                            # 电感
p.add(bm_cyl(0.07, z1, z1 + 0.004, 32), M['dark'], T(0.08, 0.03, 0))         # 风扇格栅
p.add(bm_cyl(0.016, -0.03, 0.03, 20), M['steel'], T(-0.12, d / 2 + 0.02, 1.6) @ R('X', PI / 2))   # N 型接头
for x in (-0.07, 0.07):                                                       # 到线圈端子的铜接头
    p.add(bm_cyl(0.012, 1.454, z0 + 0.004, 16), M['copper'], T(x, 0.0, 0))
p.add(bm_box(0.08, 0.002, 0.03, 0.001), M['white'], T(0.11, -d / 2 - 0.003, z1 - 0.03))   # 铭牌
p.add(pipe([(-0.12, d / 2 + 0.05, 1.6), (-0.12, 0.22, 1.74), (-0.62, 0.22, 1.74), (-0.78, 0.12, 1.62)], 0.011, 0.08), M['rfcable'])
p.build()

# --- 中心进气喷嘴 + 进气管 ---
p = Part('nozzle')
p.add(bm_cyl(0.024, 1.20, 1.30, 32, 0.002), M['ceramic'])
p.add(bm_cyl(0.03, 1.236, 1.25, 32, 0.002), M['steel'])
p.add(bm_hex(0.016, 1.30, 1.32), M['steel'])
p.add(bm_hex(0.013, 1.325, 1.345), M['steel'])
p.build()

# --- 闸阀口（剖开时一起剖）+ 门 + 气缸 ---
p = Part('slit')
zc = H + 0.01
y0, y1 = -0.335, -0.445
for (dx, dz, sx, sz) in ((0, 0.06, 0.44, 0.05), (0, -0.06, 0.44, 0.05), (-0.195, 0, 0.05, 0.17), (0.195, 0, 0.05, 0.17)):
    p.add(bm_box(sx, y0 - y1, sz, 0.003), M['anod'], T(dx, (y0 + y1) / 2, zc + dz))
p.add(bm_box(0.50, 0.012, 0.22, 0.004), M['anod'], T(0, y1 + 0.006, zc))
for x in (-0.22, -0.11, 0.11, 0.22):
    for dz in (-0.095, 0.095):
        p.add(bm_hex(0.006, 0, 0.006), M['steel'], T(x, y1 - 0.0, zc + dz) @ R('X', PI / 2))
p.add(bm_cyl(0.022, 0.62, 0.86, 24, 0.003), M['alu'], T(0, -0.475, 0))      # 门的气缸
p.add(bm_box(0.04, 0.03, 0.03, 0.003), M['dark'], T(0, -0.475, 0.63))
p.add(pipe([(0.03, -0.475, 0.64), (0.12, -0.42, 0.62), (0.28, -0.30, 0.62)], 0.004, 0.04), M['valve'])
p.build()
p = Part('slit__door', origin=(0, -0.458, zc))
p.add(bm_box(0.42, 0.02, 0.125, 0.004), M['grey'], T(0, -0.458, zc))
p.add(bm_box(0.36, 0.004, 0.06, 0.001), M['black'], T(0, -0.447, zc))
p.add(bm_cyl(0.008, 0.86, zc - 0.06, 12), M['steel'], T(0, -0.475, 0))     # 活塞杆跟着门动
p.build()

# --- 内衬、约束环（剖开时一起剖） ---
p = Part('liner')
p.add(bm_rev([(0.298, 0.87), (0.314, 0.87), (0.314, 1.165), (0.298, 1.165)], 96), M['coat'])
p.add(bm_ring(0.28, 0.314, 0.87, 0.882, 96), M['coat'])
p.build()
p = Part('baffle')
p.add(bm_ring(0.19, 0.30, 0.86, 0.872, 96, 0.001), M['grey'])
slots(p, 48, 0.245, 0.8725, 0.004, 0.0016, 0.085, M['black'])
p.build()

# --- 静电卡盘（剖开能看到电极、加热层、冷却水道） ---
p = Part('esc')
p.add(bm_rev([(0, H - 0.013), (0.149, H - 0.013), (0.15, H - 0.012), (0.15, H - 0.002), (0.149, H - 0.001), (0, H - 0.001)], 96), M['ceramic'])
for r in (0.05, 0.095, 0.14):                                                 # 背氦沟槽
    p.add(bm_ring(r - 0.0012, r + 0.0012, H - 0.00105, H - 0.0009, 96), M['dark'])
p.add(bm_cyl(0.142, H - 0.0062, H - 0.0052, 96), M['copper'])                # 吸附电极
p.add(bm_cyl(0.142, H - 0.0105, H - 0.0095, 96), M['heater'])                # 加热层
p.add(bm_rev([(0.03, 0.83), (0.165, 0.83), (0.165, 0.92), (0.168, 0.922), (0.168, H - 0.013), (0.03, H - 0.013)], 96), M['alu'])
for r in (0.055, 0.085, 0.115, 0.145):                                        # 冷却水道
    p.add(bm_torus(r, 0.009, 0.895, 64, 10), M['coolant'])
p.add(bm_rev([(0.0, 0.60), (0.095, 0.60), (0.095, 0.62), (0.07, 0.62), (0.07, 0.83), (0.0, 0.83)], 64), M['alu'])   # 杆
p.build()
p = Part('edgering')
p.add(bm_rev([(0.151, H - 0.014), (0.185, H - 0.014), (0.185, H + 0.002), (0.159, H + 0.002), (0.158, H - 0.0035), (0.151, H - 0.0035)], 96), M['silicon'])
p.build()
p = Part('insring')
p.add(bm_rev([(0.168, 0.83), (0.19, 0.83), (0.19, H - 0.014), (0.168, H - 0.014)], 96), M['quartz'])
p.build()

# --- 升降针（整组上下动） ---
p = Part('pins')
for a in around(3, PI / 2):
    x, y = 0.1 * math.cos(a), 0.1 * math.sin(a)
    p.add(bm_rev([(0, 0.80), (0.0025, 0.80), (0.0025, H - 0.006), (0.0015, H - 0.004), (0, H - 0.0036)], 16), M['ceramic'], T(x, y, 0))
    acc = []
    for k in range(10):
        z = 0.63 + k * 0.012
        acc += [(0.014, z), (0.010, z + 0.006)]
    p.add(bm_rev([(0.004, 0.625)] + acc + [(0.004, 0.755)], 24), M['steel'], T(x, y, 0))   # 波纹管
    p.add(bm_cyl(0.004, 0.60, 0.80, 12), M['steel'], T(x, y, 0))
p.add(bm_ring(0.085, 0.115, 0.598, 0.61, 48, 0.002), M['alu'])                # 顶升轭
p.build()

# --- 摆阀：剖开能看到阀板，按开度摆动 ---
PX, PY = 0.22, 0.0
p = Part('pendulum')
p.add(bm_ring(0.15, 0.175, 0.70, 0.758, 64, 0.003), M['alu'], T(PX, PY, 0))
p.add(bm_box(0.35, 0.30, 0.058, 0.004), M['alu'], T(PX, PY + 0.15, 0.729))
p.add(bm_cyl(0.175, 0.70, 0.758, 64, 0.003), M['alu'], T(PX, PY + 0.30, 0))
p.add(bm_box(0.08, 0.08, 0.10, 0.006), M['dark'], T(PX, PY + 0.30, 0.82))      # 电机
p.add(bm_box(0.05, 0.02, 0.03, 0.002), M['led'], T(PX, PY + 0.259, 0.84))
p.build()
p = Part('pendulum__plate', origin=(PX, PY + 0.30, 0.729))
p.add(bm_cyl(0.148, 0.722, 0.736, 64, 0.002), M['steel'], T(PX, PY, 0))
p.add(bm_box(0.06, 0.30, 0.012, 0.002), M['steel'], T(PX, PY + 0.15, 0.729))
p.add(bm_cyl(0.02, 0.715, 0.745, 24), M['steel'], T(PX, PY + 0.30, 0))
p.build()

# --- 分子泵：外壳 + 散热片 + 转子（会转）+ 控制器 + 前级波纹管 ---
p = Part('turbo')
p.add(bm_rev([(0.115, 0.44), (0.128, 0.44), (0.131, 0.443), (0.131, 0.675), (0.152, 0.675), (0.152, 0.70), (0.115, 0.70)], 64), M['white'], T(PX, PY, 0))
p.add(bm_cyl(0.128, 0.44, 0.452, 64), M['white'], T(PX, PY, 0))
for z in (0.47, 0.50, 0.53, 0.56, 0.59, 0.62):
    p.add(bm_ring(0.131, 0.141, z, z + 0.006, 64), M['alu'], T(PX, PY, 0))
bolts(p, 12, 0.142, 0.70, hr=0.006, hh=0.006, up=True)
p.add(bm_box(0.085, 0.13, 0.11, 0.006), M['dark'], T(PX + 0.17, PY, 0.52))    # 控制器
p.add(bm_box(0.002, 0.05, 0.02, 0.001), M['led'], T(PX + 0.2135, PY - 0.03, 0.55))
p.add(bm_cyl(0.028, -0.06, 0.06, 24), M['steel'], T(PX, PY + 0.17, 0.47) @ R('X', PI / 2))
p.add(pipe([(PX, PY + 0.20, 0.47), (PX, PY + 0.30, 0.47), (PX, PY + 0.32, 0.25), (PX, PY + 0.32, 0.02)], 0.032, 0.09, 3), M['steel'])
for z in [0.06 + 0.035 * k for k in range(6)]:                                # 波纹管的楞
    p.add(bm_torus(0.034, 0.005, z, 32, 6), M['steel'], T(PX, PY + 0.32, 0))
p.add(pipe([(PX + 0.17, PY + 0.065, 0.52), (PX + 0.17, PY + 0.25, 0.4), (PX + 0.25, PY + 0.3, 0.02)], 0.007, 0.06), M['rfcable'])
p.build()
p = Part('turbo__rotor', origin=(PX, PY, 0))
p.add(bm_cyl(0.034, 0.47, 0.665, 32), M['rotor'], T(PX, PY, 0))
for s, z in enumerate([0.485 + 0.026 * k for k in range(7)]):
    p.add(bm_cyl(0.045, z - 0.004, z + 0.004, 32), M['rotor'], T(PX, PY, 0))
    for a in around(14, s * 0.2):
        p.add(bm_box(0.075, 0.016, 0.003, 0), M['rotor'], T(PX, PY, 0) @ R('Z', a) @ T(0.08, 0, z) @ R('X', 0.45 if s % 2 else -0.45))
p.build()

# --- 观察窗 + 光纤 + 光谱仪 ---
p = Part('oes')
oy, oz = 0.10, H + 0.085
p.add(bm_cyl(0.045, 0.0, 0.07, 32, 0.003), M['anod'], T(-0.338, oy, oz) @ R('Y', -PI / 2))
p.add(bm_cyl(0.06, 0.0, 0.012, 32, 0.002), M['steel'], T(-0.405, oy, oz) @ R('Y', -PI / 2))
p.add(bm_cyl(0.035, 0.0, 0.004, 32), M['quartz'], T(-0.418, oy, oz) @ R('Y', -PI / 2))
bolts_pts = around(6)
for a in bolts_pts:
    p.add(bm_hex(0.005, 0, 0.005), M['steel'], T(-0.417, oy + 0.05 * math.cos(a), oz + 0.05 * math.sin(a)) @ R('Y', -PI / 2))
p.add(bm_cyl(0.012, 0.0, 0.04, 16), M['steel'], T(-0.42, oy, oz) @ R('Y', -PI / 2))
p.add(pipe([(-0.46, oy, oz), (-0.52, oy, oz), (-0.56, oy + 0.06, 0.92), (-0.56, oy + 0.09, 0.80)], 0.0045, 0.06), M['orange'])
p.add(bm_box(0.11, 0.16, 0.07, 0.006), M['green'], T(-0.56, oy + 0.15, 0.765))
p.add(bm_box(0.002, 0.06, 0.02, 0.001), M['screen'], T(-0.6155, oy + 0.13, 0.775))
p.build()

# --- 真空计 ×2 ---
p = Part('cmg')
for gy in (0.14, 0.25):
    p.add(bm_cyl(0.014, 0.0, 0.09, 16), M['steel'], T(0.335, gy, 1.12) @ R('Y', PI / 2))
    p.add(bm_cyl(0.022, 0.0, 0.012, 24, 0.002), M['steel'], T(0.40, gy, 1.12) @ R('Y', PI / 2))
    p.add(bm_cyl(0.034, 1.04, 1.20, 32, 0.004), M['white'], T(0.45, gy, 0))
    p.add(bm_cyl(0.036, 1.20, 1.23, 32, 0.004), M['grey'], T(0.45, gy, 0))
    p.add(bm_box(0.02, 0.024, 0.02, 0.002), M['dark'], T(0.45, gy, 1.24))
p.build()

# --- 偏压匹配器 + 铜带 ---
p = Part('biasmatch')
p.add(bm_box(0.22, 0.22, 0.18, 0.006), M['grey'], T(-0.22, 0.17, 0.60))
for k in range(6):
    p.add(bm_box(0.003, 0.14, 0.012, 0.001), M['dark'], T(-0.3315, 0.17, 0.54 + 0.022 * k))
p.add(bm_box(0.002, 0.07, 0.03, 0.001), M['yellow'], T(-0.331, 0.12, 0.66))
p.add(bm_box(0.08, 0.012, 0.03, 0.002), M['copper'], T(-0.07, 0.07, 0.61) @ R('Z', 0.75))
p.add(pipe([(-0.22, 0.28, 0.62), (-0.22, 0.34, 0.62), (-0.55, 0.34, 0.5), (-0.74, 0.20, 0.42)], 0.010, 0.08), M['rfcable'])
p.build()

# --- 冷却水管（进蓝出红）、卡盘高压线、背氦管 ---
p = Part('lines')
p.add(pipe([(0.035, 0.0, 0.60), (0.035, 0.0, 0.52), (0.035, -0.22, 0.40), (0.035, -0.26, 0.02)], 0.011, 0.07), M['hoseblue'])
p.add(pipe([(-0.035, 0.0, 0.60), (-0.035, 0.0, 0.52), (-0.035, -0.22, 0.40), (-0.035, -0.26, 0.02)], 0.011, 0.07), M['hosered'])
p.add(pipe([(0.0, 0.04, 0.60), (0.0, 0.04, 0.50), (-0.10, 0.25, 0.30), (-0.12, 0.27, 0.02)], 0.006, 0.07), M['hv'])
p.add(pipe([(0.0, -0.04, 0.60), (0.0, -0.06, 0.50), (0.12, -0.25, 0.32), (0.15, -0.27, 0.02)], 0.0035, 0.05), M['steel'])
p.build()

# --- 气体盒：前面透明窗，4 路气（MFC + 气动阀 + 过滤器），色环区分气体 ---
p = Part('gasbox')
gx, gy, gz = 0.66, 0.15, 1.25
gw, gd, gh = 0.34, 0.28, 0.52
p.add(bm_box(gw, 0.006, gh, 0.003), M['white'], T(gx, gy + gd / 2, gz))
for sx in (-1, 1):
    p.add(bm_box(0.006, gd, gh, 0.003), M['white'], T(gx + sx * gw / 2, gy, gz))
p.add(bm_box(gw, gd, 0.006, 0.003), M['white'], T(gx, gy, gz + gh / 2))
p.add(bm_box(gw, gd, 0.006, 0.003), M['white'], T(gx, gy, gz - gh / 2))
p.add(bm_box(gw - 0.02, 0.004, gh - 0.02, 0.001), M['acrylic'], T(gx, gy - gd / 2, gz))
p.add(bm_box(gw, 0.01, 0.03, 0.002), M['white'], T(gx, gy - gd / 2, gz + gh / 2 - 0.015))
p.add(bm_box(gw, 0.01, 0.03, 0.002), M['white'], T(gx, gy - gd / 2, gz - gh / 2 + 0.015))
for i, gm in enumerate((M['cl2'], M['hbr'], M['o2'], M['ar'])):
    x = gx - 0.12 + i * 0.08
    y = gy + 0.02
    p.add(bm_cyl(0.005, gz - 0.24, gz + 0.24, 12), M['steel'], T(x, y, 0))
    p.add(bm_box(0.045, 0.05, 0.10, 0.004), M['grey'], T(x, y, gz - 0.02))         # MFC
    p.add(bm_box(0.03, 0.002, 0.014, 0.001), M['screen'], T(x, y - 0.026, gz + 0.012))
    p.add(bm_box(0.008, 0.002, 0.004, 0.0005), M['led'], T(x + 0.012, y - 0.026, gz - 0.01))
    for vz in (gz + 0.12, gz - 0.15):                                              # 气动阀
        p.add(bm_cyl(0.013, vz - 0.01, vz + 0.01, 20, 0.002), M['steel'], T(x, y, 0))
        p.add(bm_cyl(0.011, 0.0, 0.035, 20, 0.002), M['valve'], T(x, y, vz) @ R('X', PI / 2))
    p.add(bm_cyl(0.012, gz + 0.16, gz + 0.21, 20, 0.002), M['steel'], T(x, y, 0))  # 过滤器
    p.add(bm_ring(0.0055, 0.008, gz - 0.21, gz - 0.19, 16), gm, T(x, y, 0))         # 色环
    p.add(bm_box(0.05, 0.002, 0.025, 0.001), gm, T(x, y - 0.028, gz + 0.075))
    p.add(pipe([(x, y, gz - 0.24), (x, y, gz - 0.30), (x, y + 0.20, gz - 0.40), (x, y + 0.22, 0.02)], 0.005, 0.05), M['steel'])
p.add(bm_cyl(0.006, -0.13, 0.13, 12), M['steel'], T(gx, gy + 0.02, gz + 0.24) @ R('Y', PI / 2))
p.add(pipe([(gx, gy + 0.02, gz + 0.24), (gx, gy + 0.02, 1.72), (0.25, 0.15, 1.72), (0.25, 0.15, 1.37), (0.0, 0.0, 1.37), (0.0, 0.0, 1.345)], 0.0055, 0.05), M['steel'])
p.build()

# --- 射频电源和控制柜 ---
p = Part('rack')
rx, ry, rz = -0.78, 0.12, 0.0
rw, rd, rh = 0.44, 0.62, 1.62
for sx in (-1, 1):
    p.add(bm_box(0.012, rd, rh, 0.003), M['grey'], T(rx + sx * (rw / 2 - 0.006), ry, rh / 2))
p.add(bm_box(rw, rd, 0.012, 0.003), M['grey'], T(rx, ry, rh - 0.006))
p.add(bm_box(rw, rd, 0.05, 0.003), M['dark'], T(rx, ry, 0.025))
p.add(bm_box(rw, 0.012, rh, 0.003), M['grey'], T(rx, ry + rd / 2, rh / 2))
fy = ry - rd / 2
units = [(1.42, 0.16, 'gen'), (1.22, 0.16, 'gen'), (1.04, 0.12, 'ctl'), (0.86, 0.16, 'blank'), (0.40, 0.56, 'blank'), (0.12, 0.14, 'pdu')]
for zc_, hh, kind in units:
    p.add(bm_box(rw - 0.03, 0.02, hh - 0.006, 0.003), M['white'] if kind != 'pdu' else M['dark'], T(rx, fy, zc_))
    for sx in (-1, 1):                                                         # 把手
        p.add(bm_box(0.012, 0.025, hh * 0.6, 0.003), M['steel'], T(rx + sx * (rw / 2 - 0.035), fy - 0.02, zc_))
    if kind == 'gen':
        p.add(bm_box(0.12, 0.004, 0.06, 0.001), M['screen'], T(rx - 0.06, fy - 0.011, zc_ + 0.02))
        p.add(bm_box(0.06, 0.002, 0.012, 0.0005), M['led'], T(rx - 0.06, fy - 0.0135, zc_ + 0.03))
        p.add(bm_cyl(0.018, 0, 0.02, 24, 0.002), M['dark'], T(rx + 0.08, fy - 0.01, zc_) @ R('X', PI / 2))
        for k in range(3):
            p.add(bm_box(0.016, 0.006, 0.01, 0.001), M['dark'], T(rx + 0.03 + k * 0.025, fy - 0.012, zc_ - 0.04))
    if kind == 'ctl':
        for k in range(8):
            p.add(bm_box(0.008, 0.003, 0.008, 0.0005), M['led'] if k % 3 else M['heater'], T(rx - 0.14 + k * 0.025, fy - 0.0115, zc_ + 0.02))
    if kind == 'pdu':
        p.add(bm_box(0.04, 0.006, 0.05, 0.002), M['hv'], T(rx + 0.12, fy - 0.012, zc_))
for k in range(12):                                                            # 侧面散热孔
    p.add(bm_box(0.003, 0.3, 0.008, 0.001), M['dark'], T(rx - rw / 2 - 0.0005, ry, 0.3 + k * 0.05))
p.build()

# ================= 机械手 =================
def stadium(L, wd, th, m, z=0.0):
    """沿 +X、两头圆的连杆。"""
    b = bm_box(L, wd, th, 0.004)
    b.transform(T(L / 2, 0, z))
    return b


def robot(prefix, L, base_kind):
    # 底座
    p = Part(prefix + '_base')
    if base_kind == 'atm':
        p.add(bm_cyl(0.15, 0.0, 0.04, 48, 0.004), M['dark'])
        p.add(bm_rev([(0, 0.04), (0.10, 0.04), (0.10, 0.83), (0.095, 0.84), (0, 0.84)], 64), M['white'])
        p.add(bm_ring(0.099, 0.104, 0.80, 0.806, 64), M['dark'])
        p.add(bm_ring(0.099, 0.104, 0.12, 0.126, 64), M['dark'])
        p.add(bm_box(0.002, 0.04, 0.012, 0.0005), M['led'], T(0.101, 0, 0.75))
        p.add(bm_cyl(0.07, 0.84, 0.875, 48, 0.004), M['grey'])
    else:
        p.add(bm_cyl(0.16, 0.78, 0.80, 64, 0.003), M['alu'])
        bolts(p, 12, 0.145, 0.80, hr=0.006, hh=0.005)
        p.add(bm_cyl(0.10, 0.80, 0.875, 64, 0.004), M['alu'])
        p.add(bm_ring(0.099, 0.103, 0.84, 0.845, 64), M['dark'])
    p.build()
    col = M['white'] if base_kind == 'atm' else M['alu']
    # 大臂：原点在肩关节
    p = Part(prefix + '_l1')
    p.add(stadium(L, 0.10, 0.022, col), col)
    p.add(bm_cyl(0.06, -0.011, 0.011, 40, 0.004), col)
    p.add(bm_cyl(0.05, -0.011, 0.011, 40, 0.004), col, T(L, 0, 0))
    p.add(bm_box(L - 0.12, 0.06, 0.003, 0.001), M['grey'], T(L / 2, 0, 0.012))
    p.add(bm_cyl(0.035, 0.011, 0.02, 32, 0.002), M['dark'], T(L, 0, 0))       # 肘关节盖
    p.add(bm_cyl(0.045, 0.011, 0.016, 32, 0.002), M['dark'])
    p.build()
    # 小臂：原点在肘关节
    p = Part(prefix + '_l2')
    p.add(stadium(L, 0.075, 0.014, col), col)
    p.add(bm_cyl(0.042, -0.007, 0.007, 36, 0.003), col)
    p.add(bm_cyl(0.034, -0.007, 0.007, 36, 0.003), col, T(L, 0, 0))
    p.add(bm_box(L - 0.1, 0.045, 0.002, 0.0008), M['grey'], T(L / 2, 0, 0.0075))
    p.add(bm_cyl(0.025, 0.007, 0.013, 32, 0.002), M['dark'], T(L, 0, 0))       # 腕关节盖
    p.build()
    # 刀叉：原点在晶圆中心，U 形开口朝 +X
    p = Part(prefix + '_blade')
    fk = M['ceramic']
    p.add(bm_box(0.07, 0.11, 0.004, 0.0015), fk, T(-0.02, 0, 0))
    for sy in (-1, 1):
        p.add(bm_box(0.16, 0.026, 0.004, 0.0015), fk, T(0.09, sy * 0.042, 0))
        p.add(bm_cyl(0.008, 0.002, 0.0028, 16), M['black'], T(0.14, sy * 0.042, 0))   # 真空吸盘
    p.add(bm_cyl(0.008, 0.002, 0.0028, 16), M['black'], T(-0.03, 0, 0))
    p.add(bm_box(0.012, 0.012, 0.01, 0.002), M['dark'], T(-0.045, 0.045, 0.006))       # 晶圆检测传感器
    p.build()


robot('atm', 0.46, 'atm')
robot('vtm', 0.55, 'vtm')

# ================= 导出 =================
tris = 0
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        tris += sum(len(pl.vertices) - 2 for pl in ob.data.polygons)
print('objects', len(bpy.data.objects), 'triangles', tris)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'etcher.blend'))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'etcher_detail.glb'), export_format='GLB', use_selection=False,
                          export_apply=True, export_yup=True, export_extras=False, export_cameras=False, export_lights=False)
print('GLB', os.path.getsize(os.path.join(OUT, 'etcher_detail.glb')) // 1024, 'KB')
