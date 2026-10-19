# -*- coding: utf-8 -*-
"""
E235 系（山手线）先头车 クハE235 —— Blender 脚本建模

用法（启动.bat 会自动调用）:
    blender --background --factory-startup --python build_train.py -- <输出目录> [--render]

坐标约定（单位：米）:
    X = 车长方向，+X 是车头（驾驶室）一侧
    Y = 车宽方向，面向车头时 +Y 是左侧、-Y 是右侧（站台在右侧 -Y）
    Z = 高度，0 = 轨面

可动部分全部由空物体 Train_Controls 上的自定义属性驱动（驱动器只用简单表达式，
不需要允许 Python 自动运行）:
    door_open   0~1   车门开度
    door_left   0/1   左侧（+Y）车门是否参与开关
    door_right  0/1   右侧（-Y）车门是否参与开关
    lights      0~1   车内灯 + 前照灯/尾灯总开关
    headlight   0/1   1=前照灯（本车在前），0=尾灯（本车在尾）
    night       0~1   0=白天 1=夜晚
"""
import bpy
import bmesh
import math
import os
import sys
import base64
import numpy as np
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
_argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
_pos = [a for a in _argv if not a.startswith('--')]
OUT = os.path.abspath(_pos[0]) if _pos else os.path.join(HERE, 'output')
RENDER = '--render' in _argv
RENDER_FAST = '--fast' in _argv          # 只用于自检：低分辨率低采样
NO_HTML = '--no-html' in _argv

# ───────────────────────── 尺寸（参照 E235 系，部分为推测，见 README） ─────────────────────────
FLOOR = 1.13                    # 地板面高度（轨面起）
X_REAR = -9.80                  # 后端（贯通路一侧）外表面
X_SHELL_FRONT = 10.00           # 侧墙结束、车头罩开始
DOORS = [-7.245, -2.425, 2.395, 7.215]   # 4 对客室门中心，门距 4.82 m
DOOR_W = 1.30                   # 门开口宽
DOOR_Z1 = 2.98                  # 门开口上沿
LEAF_W = DOOR_W / 2
TRAVEL = 0.64                   # 每扇门滑开距离
WIN_Z0, WIN_Z1 = 1.98, 2.88     # 客室侧窗上下沿
PART_X = 8.82                   # 驾驶室隔墙（客室侧表面）
PART_T = 0.05
CAB_FLOOR = FLOOR + 0.18        # 驾驶室地板抬高
CREW_DOOR = (8.92, 9.50)        # 乘务员门
CAB_WIN = (9.58, 9.95)          # 驾驶室侧窗
BOGIES = [-6.70, 7.10]          # 转向架中心
SEAT_W = 0.46                   # 座位宽（E235 比 E231 宽 1 cm）
STRAP_Z = 3.08                  # 吊环横杆高度
RACK_Z = FLOOR + 1.70           # 行李架高度

SEC_MID = [(DOORS[i] + LEAF_W, DOORS[i + 1] - LEAF_W) for i in range(3)]
SEC_REAR = (X_REAR + 0.06, DOORS[0] - LEAF_W)
SEC_FREE = (DOORS[3] + LEAF_W, PART_X)

# 车体外轮廓（右半，Y≥0，从车底往上再到车顶中心）。宽车体：下部内收，最宽 2.95 m
OUT_HALF = [(1.40, 1.00), (1.43, 1.10), (1.455, 1.22), (1.47, 1.36), (1.475, 1.50),
            (1.475, 2.95), (1.47, 3.06), (1.45, 3.15), (1.41, 3.24), (1.35, 3.32),
            (1.26, 3.40), (1.10, 3.48), (0.85, 3.55), (0.55, 3.60), (0.25, 3.62), (0.0, 3.625)]


def tval(z):
    """壁厚：侧墙 5 cm，车顶处加厚到 20 cm（车顶里面有风道和结构，客室天花板因此在 2.3 m 左右）"""
    return 0.05 if z <= 3.0 else 0.05 + 0.15 * min(1.0, (z - 3.0) / 0.45)


def _full(half):
    return list(half) + [(-y, z) for y, z in reversed(half[:-1])]


def _offset(pts, tfun):
    res = []
    n = len(pts)
    for i, (y, z) in enumerate(pts):
        p = Vector((y, z))
        nrm = Vector((0.0, 0.0))
        if i > 0:
            d = p - Vector(pts[i - 1])
            nrm += Vector((d.y, -d.x)).normalized()
        if i < n - 1:
            d = Vector(pts[i + 1]) - p
            nrm += Vector((d.y, -d.x)).normalized()
        nrm.normalize()
        q = p - nrm * tfun(z)
        res.append((q.x, q.y))
    return res


OUTER = _full(OUT_HALF)
INNER = _offset(OUTER, tval)
INNER_HALF = INNER[:len(OUT_HALF)]
_ZS = [z for _, z in OUT_HALF]
_YS = [y for y, _ in OUT_HALF]


def y_out(z):
    return float(np.interp(z, _ZS, _YS))


def y_in(z):
    return float(np.interp(z, [p[1] for p in INNER_HALF], [p[0] for p in INNER_HALF]))


def z_ceiling(y):
    """客室天花板（内轮廓车顶部分）在横向位置 y 处的高度"""
    pts = [p for p in INNER_HALF if p[1] > 3.0]
    ys = [p[0] for p in reversed(pts)]
    zs = [p[1] for p in reversed(pts)]
    return float(np.interp(abs(y), ys, zs))


def x_face(z):
    """车头黑色面板前表面（略微后倾）"""
    return 10.30 - (z - 1.10) * (0.04 / 2.28)


# ───────────────────────── 场景、集合、材质 ─────────────────────────
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    for name in ('Body', 'Doors', 'Interior', 'Cab', 'Underfloor', 'Lamps', 'Environment', 'Rig'):
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)


def C(name):
    return bpy.data.collections[name]


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


MATS = {}
UVSCALE = {}


def _sock(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def mk(name, col='#ffffff', metal=0.0, rough=0.5, emit=None, estr=0.0, alpha=1.0,
       img=None, img_emit=False, coat=0.0, uvscale=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*srgb(col), 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if coat:
        s = _sock(b, 'Coat Weight', 'Clearcoat')
        if s:
            s.default_value = coat
    es = _sock(b, 'Emission Color', 'Emission')
    if emit:
        es.default_value = (*srgb(emit), 1)
        _sock(b, 'Emission Strength').default_value = estr
    if img is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img
        t.interpolation = 'Closest'
        t.location = (-400, 200)
        if img_emit:
            nt.links.new(t.outputs['Color'], es)
            b.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
            _sock(b, 'Emission Strength').default_value = estr
        else:
            nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    if alpha < 1.0:
        b.inputs['Alpha'].default_value = alpha
        if hasattr(m, 'surface_render_method'):
            m.surface_render_method = 'BLENDED'
        elif hasattr(m, 'blend_method'):
            m.blend_method = 'BLEND'
    m.use_backface_culling = False
    m.diffuse_color = (*srgb(col if not img else '#808080'), alpha)
    MATS[name] = m
    UVSCALE[name] = uvscale
    return m


def emission_socket(mat):
    b = mat.node_tree.nodes.get('Principled BSDF')
    return _sock(b, 'Emission Strength')


# ───────────────────────── 程序贴图（numpy 画） ─────────────────────────
def _hex(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def canvas(w, h, col):
    a = np.ones((h, w, 4), np.float32)
    a[..., :3] = _hex(col)
    return a


def rect(a, x0, y0, x1, y1, col):
    a[int(y0):int(y1), int(x0):int(x1), :3] = _hex(col)


def circle(a, cx, cy, r, col, r_in=0):
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    a[(d <= r) & (d >= r_in), :3] = _hex(col)


def to_image(name, a):
    h, w = a.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(a[::-1]).ravel())
    img.pack()
    return img


def make_images():
    I = {}
    # 座椅花纹：E235 的座椅靠背是山手线绿的格子花纹
    for key, c1, c2 in (('seat_back', '#5aa02c', '#76b83a'), ('seat_cush', '#3f4a44', '#4b5852'),
                        ('prio_back', '#3c5f9e', '#5378b8'), ('prio_cush', '#33405a', '#3d4b68')):
        a = canvas(64, 64, c1)
        for i in range(8):
            for j in range(8):
                if (i + j) % 2:
                    rect(a, i * 8, j * 8, i * 8 + 8, j * 8 + 8, c2)
        I[key] = to_image('tex_' + key, a)

    # 门上方的信息屏（只画图形，网页版会换成带日文站名的画面）
    a = canvas(512, 288, '#ffffff')
    rect(a, 0, 0, 512, 64, '#1d2b4f')
    rect(a, 10, 10, 54, 54, '#80c241')
    rect(a, 70, 18, 250, 30, '#ffffff'); rect(a, 70, 38, 200, 48, '#9fb0d0')
    rect(a, 280, 12, 500, 52, '#2e4a86')
    rect(a, 0, 64, 512, 74, '#80c241')
    rect(a, 30, 165, 482, 177, '#80c241')
    for k in range(6):
        cx = 60 + k * 78
        circle(a, cx, 171, 15, '#80c241')
        circle(a, cx, 171, 9, '#ffffff')
        rect(a, cx - 22, 196, cx + 22, 206, '#333333')
    circle(a, 216, 171, 15, '#f39800'); circle(a, 216, 171, 8, '#ffffff')
    rect(a, 0, 248, 512, 288, '#e9edf2'); rect(a, 20, 260, 300, 276, '#6b7a8f')
    I['lcd_info'] = to_image('tex_lcd_info', a)

    # 广告屏（三种）
    pal = [('#1b5fb5', '#59b7e8', '#ffffff'), ('#c4321f', '#f2a43a', '#ffffff'), ('#2a8a5a', '#a8db6e', '#1a1a1a')]
    for k, (c1, c2, c3) in enumerate(pal):
        a = canvas(512, 288, c1)
        t = np.linspace(0, 1, 512, dtype=np.float32)[None, :, None]
        a[..., :3] = _hex(c1) * (1 - t) + _hex(c2) * t
        circle(a, 380, 144, 92, c3)
        circle(a, 380, 144, 70, c2)
        rect(a, 40, 70, 260, 100, c3); rect(a, 40, 120, 220, 136, c3); rect(a, 40, 150, 190, 166, c3)
        rect(a, 40, 210, 140, 240, '#ffffff')
        I['lcd_ad%d' % k] = to_image('tex_lcd_ad%d' % k, a)

    # 驾驶台显示屏
    a = canvas(256, 160, '#06090d')
    circle(a, 70, 85, 55, '#1f9d55', 48)
    circle(a, 70, 85, 6, '#f2f2f2')
    for k in range(6):
        rect(a, 150 + k * 16, 140 - 18 * (k + 1), 160 + k * 16, 140, '#f39800' if k < 4 else '#3b82f6')
    rect(a, 8, 8, 248, 22, '#163049')
    I['lcd_cab'] = to_image('tex_lcd_cab', a)

    # 行先显示器底图（LED 点阵感的暗底）
    a = canvas(256, 64, '#050505')
    I['dest'] = to_image('tex_dest', a)
    return I


def make_materials(I):
    mk('Stainless', '#c7cacd', metal=0.92, rough=0.30)
    mk('RoofGray', '#6e7173', rough=0.7)
    mk('YamanoteGreen', '#7cc243', rough=0.32, coat=0.4)
    mk('FrontBlack', '#0a0c0e', metal=0.2, rough=0.10, coat=0.8)
    mk('Frame', '#a9adb0', metal=0.7, rough=0.40)
    mk('GlassSide', '#2a3548', rough=0.04, alpha=0.42)
    mk('GlassFront', '#121a24', rough=0.03, alpha=0.38)
    mk('GlassClear', '#dce6ea', rough=0.03, alpha=0.18)
    mk('GlassFrost', '#eef1f2', rough=0.6, alpha=0.55)
    mk('InteriorWall', '#ebe9e4', rough=0.55)
    mk('Ceiling', '#f4f4f2', rough=0.6)
    mk('Floor', '#8b8f93', rough=0.85)
    mk('FloorDoor', '#a9abab', rough=0.85)
    mk('YellowLine', '#efc219', rough=0.6)
    mk('SillSteel', '#9da2a6', metal=0.85, rough=0.45)
    mk('DoorInner', '#d3d6d8', metal=0.35, rough=0.40)
    mk('Rubber', '#141414', rough=0.85)
    mk('SeatBack', '#7cc243', rough=0.9, img=I['seat_back'], uvscale=1 / 0.32)
    mk('SeatCushion', '#4b5852', rough=0.9, img=I['seat_cush'], uvscale=1 / 0.32)
    mk('PrioBack', '#3c5f9e', rough=0.9, img=I['prio_back'], uvscale=1 / 0.32)
    mk('PrioCushion', '#33405a', rough=0.9, img=I['prio_cush'], uvscale=1 / 0.32)
    mk('SeatFrame', '#b6babd', metal=0.6, rough=0.45)
    mk('PoleSteel', '#d8dbde', metal=1.0, rough=0.16)
    mk('StrapBelt', '#2b2e2c', rough=0.7)
    mk('StrapGreen', '#7cc243', rough=0.45)
    mk('StrapYellow', '#f2c200', rough=0.45)
    mk('RackMetal', '#a7abad', metal=0.75, rough=0.45)
    mk('Bezel', '#17191b', rough=0.35)
    mk('VentDark', '#3a3d40', rough=0.7)
    mk('LED_Interior', '#ffffff', emit='#f4f7ff', estr=6.0, rough=0.3)
    mk('LCD_Info', img=I['lcd_info'], img_emit=True, estr=2.2, rough=0.2)
    for k in range(3):
        mk('LCD_Ad%d' % k, img=I['lcd_ad%d' % k], img_emit=True, estr=2.2, rough=0.2)
    mk('LCD_Cab', img=I['lcd_cab'], img_emit=True, estr=2.0, rough=0.2)
    mk('DestPanel', img=I['dest'], img_emit=True, estr=1.0, rough=0.2)
    mk('DestText', '#111111', emit='#ff9a1f', estr=14.0)
    mk('DestTextGreen', '#111111', emit='#7cdc3c', estr=14.0)
    mk('Headlight', '#f0f0f0', emit='#fff4dd', estr=40.0, rough=0.1)
    mk('Taillight', '#3a0808', emit='#ff1a10', estr=25.0, rough=0.1)
    mk('MarkerLamp', '#e8e8e8', emit='#ffffff', estr=10.0, rough=0.1)
    mk('LampHousing', '#1a1c1e', metal=0.5, rough=0.3)
    for s in ('L', 'R'):
        mk('DoorLamp_' + s, '#5a0d08', emit='#ff2a1a', estr=0.0, rough=0.2)
        mk('SideLamp_' + s, '#5a3008', emit='#ff8a1a', estr=0.0, rough=0.2)
    mk('SOS', '#d7261e', rough=0.4)
    mk('LeanPad', '#5b6f8a', rough=0.8)
    mk('CabGray', '#5b6168', rough=0.6)
    mk('CabConsole', '#3a3f45', rough=0.5)
    mk('CabSeat', '#26385f', rough=0.85)
    mk('CabFloor', '#45484c', rough=0.9)
    mk('BogieGray', '#3b3e41', rough=0.75)
    mk('UnderGray', '#2c2f32', rough=0.8)
    mk('WheelSteel', '#5a5f63', metal=0.85, rough=0.38)
    mk('AirSpring', '#151515', rough=0.6)
    mk('Rail', '#6e6a64', metal=0.75, rough=0.45)
    mk('Sleeper', '#a7a39a', rough=0.95)
    mk('Ballast', '#77736d', rough=1.0)
    mk('Ground', '#55534c', rough=1.0)
    mk('Platform', '#b8b5ad', rough=0.9)
    mk('PlatformYellow', '#e6b800', rough=0.8)
    mk('PlatformWhite', '#f2f2f2', rough=0.8)


# ───────────────────────── 网格构建工具 ─────────────────────────
def Mx(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    return Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(scale))


MAP_YZ_X = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # 平面(y,z) 沿 x 拉伸
MAP_XZ_Y = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # 平面(x,z) 沿 y 拉伸
MIRROR_Y = Matrix.Scale(-1, 4, (0, 1, 0))
MIRROR_X = Matrix.Scale(-1, 4, (1, 0, 0))


def rrect(x0, x1, y0, y1, r, n=4):
    r = min(r, (x1 - x0) / 2 - 1e-4, (y1 - y0) / 2 - 1e-4)
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rounded_path(pts, rad, n=4, closed=False):
    P = [Vector(p) for p in pts]
    out = []
    m = len(P)
    for i in range(m):
        if not closed and (i == 0 or i == m - 1):
            out.append(P[i])
            continue
        a, b, c = P[i - 1], P[i], P[(i + 1) % m]
        d1, d2 = (a - b), (c - b)
        r = min(rad, d1.length * 0.45, d2.length * 0.45)
        p1 = b + d1.normalized() * r
        p2 = b + d2.normalized() * r
        for k in range(n + 1):
            t = k / n
            out.append(p1 * (1 - t) ** 2 + b * 2 * t * (1 - t) + p2 * t * t)
    return out


class MB:
    """把很多零件拼进一个网格；每个零件可以先在局部坐标里建好，再用矩阵摆位"""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.flag = self.bm.faces.layers.int.new('uvset')

    def mi(self, m):
        if isinstance(m, str):
            m = MATS[m]
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def mark(self):
        return len(self.bm.verts)

    def xform(self, n0, M):
        self.bm.verts.ensure_lookup_table()
        for v in self.bm.verts[n0:]:
            v.co = M @ v.co

    def v(self, co):
        return self.bm.verts.new(co)

    def face(self, vs, m, uv=None):
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(m)
        if uv:
            for l, u in zip(f.loops, uv):
                l[self.uv].uv = u
            f[self.flag] = 1
        return f

    def quad(self, corners, m, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        return self.face([self.v(c) for c in corners], m, uv)

    def _bevel_copy(self, tmp, edges, offset, seg):
        """在独立的临时 bmesh 里倒角，再拷进主网格。
        直接在主网格里倒角会释放顶点槽位，之后新建的顶点可能复用这些槽位，
        mark()/xform() 按顺序找“新顶点”的办法就会失效。"""
        bmesh.ops.bevel(tmp, geom=edges, offset=offset, segments=seg, profile=0.5,
                        affect='EDGES', clamp_overlap=True)
        vm = {v: self.v(v.co) for v in tmp.verts}
        for f in tmp.faces:
            nf = self.bm.faces.new([vm[v] for v in f.verts])
            nf.material_index = f.material_index
        tmp.free()

    def box(self, x0, x1, y0, y1, z0, z1, m, bevel=0.0, seg=2, M=None):
        n0 = self.mark()
        P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        Q = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
        if bevel > 0:
            tmp = bmesh.new()
            vs = [tmp.verts.new(p) for p in P]
            mi = self.mi(m)
            for q in Q:
                tmp.faces.new([vs[i] for i in q]).material_index = mi
            bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
            self._bevel_copy(tmp, tmp.edges[:], bevel, seg)
        else:
            vs = [self.v(p) for p in P]
            for q in Q:
                self.face([vs[i] for i in q], m)
        if M is not None:
            self.xform(n0, M)

    def cbox(self, c, size, m, M=None, bevel=0.0, seg=2):
        """以 c 为中心、size 为尺寸的盒子，再乘 M（M 作用在以 c 为原点的局部坐标上）"""
        sx, sy, sz = [s / 2 for s in size]
        n0 = self.mark()
        self.box(-sx, sx, -sy, sy, -sz, sz, m, bevel, seg)
        T = Matrix.Translation(Vector(c)) @ (M if M is not None else Matrix())
        self.xform(n0, T)

    def screen_box(self, w, h, M):
        """屏幕外框：局部 xy 为屏幕平面、+z 为屏幕朝向，再乘 M"""
        n0 = self.mark()
        self.box(-w / 2, w / 2, -h / 2, h / 2, -0.015, 0.015, 'Bezel', bevel=0.006, seg=1)
        self.xform(n0, M)

    def prism(self, poly, h, m, M=None, bevel_top=0.0, bseg=3):
        """平面多边形 poly(局部 xy) 沿局部 z 拉伸 h，再乘 M"""
        n0 = self.mark()
        if bevel_top > 0:
            tmp = bmesh.new()
            mi = self.mi(m)
            b = [tmp.verts.new((x, y, 0)) for x, y in poly]
            t = [tmp.verts.new((x, y, h)) for x, y in poly]
            tmp.faces.new(b[::-1]).material_index = mi
            top = tmp.faces.new(t)
            top.material_index = mi
            n = len(poly)
            for i in range(n):
                j = (i + 1) % n
                tmp.faces.new([b[i], b[j], t[j], t[i]]).material_index = mi
            self._bevel_copy(tmp, list(top.edges), bevel_top, bseg)
        else:
            b = [self.v((x, y, 0)) for x, y in poly]
            t = [self.v((x, y, h)) for x, y in poly]
            self.face(b[::-1], m)
            self.face(t, m)
            n = len(poly)
            for i in range(n):
                j = (i + 1) % n
                self.face([b[i], b[j], t[j], t[i]], m)
        if M is not None:
            self.xform(n0, M)

    def cyl(self, r, h, m, seg=16, M=None, r2=None, caps=True):
        n0 = self.mark()
        r2 = r if r2 is None else r2
        b = [self.v((r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), 0)) for k in range(seg)]
        t = [self.v((r2 * math.cos(2 * math.pi * k / seg), r2 * math.sin(2 * math.pi * k / seg), h)) for k in range(seg)]
        for k in range(seg):
            j = (k + 1) % seg
            self.face([b[k], b[j], t[j], t[k]], m)
        if caps:
            self.face(b[::-1], m)
            self.face(t, m)
        if M is not None:
            self.xform(n0, M)

    def tube(self, pts, r, m, seg=10, closed=False, caps=True):
        P = [Vector(p) for p in pts]
        n = len(P)
        T = []
        for i in range(n):
            if closed:
                t = P[(i + 1) % n] - P[i - 1]
            else:
                t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
            T.append(t.normalized())
        a = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
        N = T[0].cross(a).normalized()
        rings = []
        for i in range(n):
            if i > 0:
                N = (N - T[i] * N.dot(T[i])).normalized()
            B = T[i].cross(N)
            rings.append([self.v(P[i] + (N * math.cos(2 * math.pi * k / seg) + B * math.sin(2 * math.pi * k / seg)) * r)
                          for k in range(seg)])
        for i in (range(n) if closed else range(n - 1)):
            A, Bv = rings[i], rings[(i + 1) % n]
            for k in range(seg):
                j = (k + 1) % seg
                self.face([A[k], A[j], Bv[j], Bv[k]], m)
        if caps and not closed:
            self.face(rings[0][::-1], m)
            self.face(rings[-1], m)

    def build(self, name, coll, recalc=True, smooth=35, loc=None):
        bm = self.bm
        if recalc:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        names = [m.name for m in self.mats]
        for f in bm.faces:
            if f[self.flag]:
                continue
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            sc = UVSCALE.get(names[f.material_index], 1.0) if names else 1.0
            for l in f.loops:
                co = l.vert.co
                u, v = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
                l[self.uv].uv = (u * sc, v * sc)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(m)
        finish_mesh(me, smooth)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        if loc is not None:
            ob.location = loc
        return ob


def finish_mesh(me, smooth=35):
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
        try:
            me.set_sharp_from_angle(angle=math.radians(smooth))
        except AttributeError:  # Blender < 4.1
            me.use_auto_smooth = True
            me.auto_smooth_angle = math.radians(smooth)


def boolean_apply(ob, cutter_mb, op='DIFFERENCE'):
    cut = cutter_mb.build(ob.name + '_cut', C('Rig'), smooth=None)
    mod = ob.modifiers.new('bool', 'BOOLEAN')
    mod.operation = op
    mod.object = cut
    try:
        mod.solver = 'EXACT'
    except TypeError:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    cm = cut.data
    bpy.data.objects.remove(cut)
    bpy.data.meshes.remove(cm)
    return ob


def assign_by(ob, mat_names, fn):
    """按面中心重新分配材质：fn(center, normal) → mat_names 中的下标"""
    me = ob.data
    me.materials.clear()
    for n in mat_names:
        me.materials.append(MATS[n])
    for p in me.polygons:
        p.material_index = fn(p.center, p.normal)
    finish_mesh(me)


def _seg_dist(P, poly):
    A = np.array(poly[:-1], np.float64)
    B = np.array(poly[1:], np.float64)
    AB = B - A
    AP = P[:, None, :] - A[None]
    t = np.clip((AP * AB).sum(-1) / (AB * AB).sum(-1), 0, 1)
    Cc = A[None] + t[..., None] * AB[None]
    return np.linalg.norm(P[:, None, :] - Cc, axis=-1).min(1)


def link_dup(ob, name, loc, coll):
    o = bpy.data.objects.new(name, ob.data)
    o.location = loc
    coll.objects.link(o)
    return o


# ───────────────────────── 字体 ─────────────────────────
_FONT = None


def font():
    global _FONT
    if _FONT is not None:
        return _FONT or None
    cands = [r'C:\Windows\Fonts\YuGothB.ttc', r'C:\Windows\Fonts\meiryob.ttc', r'C:\Windows\Fonts\meiryo.ttc',
             r'C:\Windows\Fonts\BIZ-UDGothicB.ttc', r'C:\Windows\Fonts\msgothic.ttc',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
             '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc']
    for p in cands:
        if os.path.exists(p):
            try:
                _FONT = bpy.data.fonts.load(p)
                print('[INFO] font:', p)
                return _FONT
            except Exception:
                pass
    _FONT = False
    print('[INFO] no CJK font, displays use English')
    return None


def text_mesh(name, body, size, mat, M, coll, align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    f = font()
    if f:
        cu.font = f
    tmp = bpy.data.objects.new(name + '_tmp', cu)
    C('Rig').objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.transform(M)
    me.materials.clear()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def jp(ja, en):
    return ja if font() else en


# ───────────────────────── 车体 ─────────────────────────
def build_shell():
    mb = MB()
    stations = [X_REAR, PART_X + PART_T / 2, X_SHELL_FRONT]
    n = len(OUTER)
    O = [[mb.v((x, y, z)) for y, z in OUTER] for x in stations]
    I = [[mb.v((x, y, z)) for y, z in INNER] for x in stations]
    for s in range(len(stations) - 1):
        for i in range(n - 1):
            mb.face([O[s][i], O[s][i + 1], O[s + 1][i + 1], O[s + 1][i]], 'Stainless')
            mb.face([I[s][i], I[s + 1][i], I[s + 1][i + 1], I[s][i + 1]], 'Stainless')
        for i in (0, n - 1):  # 底边
            mb.face([O[s][i], O[s + 1][i], I[s + 1][i], I[s][i]], 'Stainless')
    for s in (0, len(stations) - 1):  # 两端端面
        for i in range(n - 1):
            mb.face([O[s][i], I[s][i], I[s][i + 1], O[s][i + 1]], 'Stainless')
    shell = mb.build('Body_Shell', C('Body'), smooth=None)

    # 开口：客室门、侧窗、乘务员门、驾驶室侧窗（左右两侧）
    cut = MB()
    for sy in (1, -1):
        def ybox(x0, x1, z0, z1):
            y0, y1 = (1.10, 1.75) if sy > 0 else (-1.75, -1.10)
            cut.box(x0, x1, y0, y1, z0, z1, 'Stainless')

        def ywin(x0, x1, z0, z1, r=0.07):
            M = Matrix.Translation((0, 1.10 if sy > 0 else -1.75, 0)) @ MAP_XZ_Y
            cut.prism(rrect(x0, x1, z0, z1, r), 0.65, 'Stainless', M=M)

        for c in DOORS:
            ybox(c - LEAF_W, c + LEAF_W, FLOOR, DOOR_Z1)
        for a, b in SEC_MID:
            m = (a + b) / 2
            ywin(m - 1.0, m + 1.0, WIN_Z0, WIN_Z1)
        ywin(-9.55, -8.65, WIN_Z0, WIN_Z1)
        ybox(CREW_DOOR[0], CREW_DOOR[1], CAB_FLOOR + 0.02, 3.00)
        ywin(CAB_WIN[0], CAB_WIN[1], 2.10, 2.85, 0.06)
    boolean_apply(shell, cut)

    P = np.array([(abs(c.y), c.z) for c in (p.center for p in shell.data.polygons)])
    dO = _seg_dist(P, OUT_HALF)
    dI = _seg_dist(P, INNER_HALF)
    xs = [p.center.x for p in shell.data.polygons]
    res = {}
    for i in range(len(xs)):
        if dO[i] < 0.008:
            res[i] = 2 if P[i][1] > 3.30 else 0
        elif dI[i] < 0.008:
            res[i] = 3 if xs[i] > PART_X + PART_T / 2 else 1
        else:
            res[i] = 4
    idx = iter(range(len(xs)))
    assign_by(shell, ['Stainless', 'InteriorWall', 'RoofGray', 'CabGray', 'Frame'], lambda c, n: res[next(idx)])
    return shell


def build_end_wall():
    mb = MB()
    mb.prism(OUTER, 0.06, 'Stainless', M=Matrix.Translation((X_REAR, 0, 0)) @ MAP_YZ_X)
    ob = mb.build('Body_EndWall', C('Body'), smooth=None)
    cut = MB()
    cut.box(X_REAR - 0.1, X_REAR + 0.2, -0.42, 0.42, FLOOR, 3.05, 'Stainless')
    boolean_apply(ob, cut)
    assign_by(ob, ['Stainless', 'InteriorWall', 'Frame'],
              lambda c, n: 0 if c.x < X_REAR + 0.005 else (1 if c.x > X_REAR + 0.055 else 2))

    # 贯通路外侧的风挡（橡胶折棚只做了根部）
    g = MB()
    for k, (x0, x1, w, h) in enumerate(((-9.86, -9.80, 0.60, 2.20), (-9.95, -9.86, 0.56, 2.14), (-10.02, -9.95, 0.58, 2.18))):
        z0 = FLOOR - 0.06
        g.box(x0, x1, -w, -w + 0.10, z0, z0 + h, 'Rubber')
        g.box(x0, x1, w - 0.10, w, z0, z0 + h, 'Rubber')
        g.box(x0, x1, -w, w, z0 + h - 0.10, z0 + h, 'Rubber')
        g.box(x0, x1, -w, w, z0, z0 + 0.05, 'Rubber')
    g.build('Body_Gangway', C('Body'))

    # 贯通门（客室内侧，关闭状态）
    d = MB()
    x0, x1 = X_REAR + 0.065, X_REAR + 0.095
    d.box(x0, x1, -0.46, -0.27, FLOOR, 3.06, 'DoorInner')
    d.box(x0, x1, 0.27, 0.46, FLOOR, 3.06, 'DoorInner')
    d.box(x0, x1, -0.27, 0.27, FLOOR, 1.95, 'DoorInner')
    d.box(x0, x1, -0.27, 0.27, 2.90, 3.06, 'DoorInner')
    d.quad([(x0 + 0.015, -0.27, 1.95), (x0 + 0.015, 0.27, 1.95), (x0 + 0.015, 0.27, 2.90), (x0 + 0.015, -0.27, 2.90)], 'GlassClear')
    d.box(x1, x1 + 0.03, 0.30, 0.34, 1.80, 2.05, 'PoleSteel', bevel=0.008)
    d.build('Interior_GangwayDoor', C('Interior'))


def build_front():
    # 车头外罩（绿色包边）
    mb = MB()
    mb.prism(OUTER, 0.20, 'YamanoteGreen', M=Matrix.Translation((X_SHELL_FRONT, 0, 0)) @ MAP_YZ_X,
             bevel_top=0.09, bseg=5)
    cap = mb.build('Body_FrontCap', C('Body'), smooth=None)
    ws = MB()
    ws.prism(rrect(-1.10, 1.10, 2.10, 3.02, 0.12), 0.6, 'Rubber', M=Matrix.Translation((9.9, 0, 0)) @ MAP_YZ_X)
    boolean_apply(cap, ws)

    def cap_mat(c, n):
        if c.x < X_SHELL_FRONT + 0.01:
            return 2
        if abs(c.y) < 1.105 and 2.095 < c.z < 3.025:
            return 1
        return 0
    assign_by(cap, ['YamanoteGreen', 'FrontBlack', 'CabGray'], cap_mat)

    # 黑色前面板（略后倾）
    mb = MB()
    mb.prism(rrect(-1.25, 1.25, 1.10, 3.38, 0.22, 6), 0.18, 'FrontBlack',
             M=Matrix.Translation((10.12, 0, 0)) @ MAP_YZ_X, bevel_top=0.025, bseg=2)
    for v in mb.bm.verts:
        if v.co.x > 10.2:
            v.co.x = x_face(v.co.z) - (10.30 - v.co.x)
    face = mb.build('Body_FrontFace', C('Body'), smooth=None)
    ws = MB()
    ws.prism(rrect(-1.10, 1.10, 2.10, 3.02, 0.12), 0.6, 'Rubber', M=Matrix.Translation((9.9, 0, 0)) @ MAP_YZ_X)
    boolean_apply(face, ws)
    finish_mesh(face.data)

    # 前窗玻璃（跟着面板倾斜）
    g = MB()
    poly = rrect(-1.12, 1.12, 2.08, 3.04, 0.13)
    vs = [g.v((x_face(z) - 0.012, y, z)) for y, z in poly]
    g.face(vs, 'GlassFront')
    # 雨刷
    for y0 in (0.55, -0.45):
        z0 = 2.13
        a = Vector((x_face(z0) + 0.005, y0, z0))
        b = Vector((x_face(z0 + 0.62) + 0.005, y0 - 0.32, z0 + 0.62))
        g.tube([a, b], 0.010, 'Rubber', seg=6)
    g.build('Body_Windshield', C('Body'))

    # 灯具：前照灯（每侧 3 颗 LED）+ 尾灯条 + 上角标识灯
    L = MB()
    for sy in (1, -1):
        zc = 1.42
        xf = x_face(zc)
        L.box(xf - 0.02, xf + 0.018, sy * 0.60, sy * 1.14, 1.32, 1.52, 'LampHousing', bevel=0.02)
        for yy in (0.82, 0.94, 1.06):
            L.cyl(0.042, 0.012, 'Headlight', seg=20, M=Mx((xf + 0.016, sy * yy, zc + 0.02), (0, math.pi / 2, 0)))
        L.box(xf + 0.014, xf + 0.024, sy * 0.64, sy * 0.76, 1.35, 1.49, 'Taillight')
        L.box(x_face(3.30) - 0.01, x_face(3.30) + 0.012, sy * 1.10, sy * 1.17, 3.27, 3.34, 'MarkerLamp')
    L.build('Lamp_Front', C('Lamps'))

    # 行先显示器
    d = MB()
    z0, z1 = 3.10, 3.30
    # 从车头正面看，-Y 在左边，所以 UV 的 u=0 放在 -Y（贴图才不会左右反）
    d.quad([(x_face(z0) + 0.003, -0.85, z0), (x_face(z0) + 0.003, 0.85, z0),
            (x_face(z1) + 0.003, 0.85, z1), (x_face(z1) + 0.003, -0.85, z1)], 'DestPanel')
    d.build('Dest_Front', C('Lamps'))
    tilt = math.atan(0.04 / 2.28)
    base = Mx((x_face(3.20) + 0.006, 0, 3.20), (math.pi / 2, -tilt, math.pi / 2))
    text_mesh('DestText_Front1', jp('山手線', 'YAMANOTE'), 0.12, 'DestTextGreen',
              base @ Mx((-0.50, 0, 0)), C('Lamps'))
    text_mesh('DestText_Front2', jp('渋谷・新宿方面', 'Shibuya-Shinjuku'), 0.075, 'DestText',
              base @ Mx((0.28, 0, 0)), C('Lamps'))

    # 排障器（裙板）：沿 V 形平面曲线的一块厚板 + 背后的加强筋
    s = MB()
    plan = [(9.90, -1.30), (10.16, -1.22), (10.33, -0.62), (10.37, 0.0), (10.33, 0.62), (10.16, 1.22), (9.90, 1.30)]
    P = [Vector((x, y)) for x, y in plan]
    Q = []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        nrm = Vector((t.y, -t.x))
        if nrm.x < 0:
            nrm = -nrm
        Q.append(p - nrm * 0.05)
    z0, z1 = 0.30, 0.98
    rows = []
    for pts, dz in ((P, 0.0), (Q, 0.0)):
        rows.append([s.v((p.x - 0.04, p.y, z0)) for p in pts])
        rows.append([s.v((p.x, p.y, z1)) for p in pts])
    ob_, ot_, ib_, it_ = rows
    n = len(P)
    for i in range(n - 1):
        s.face([ob_[i], ob_[i + 1], ot_[i + 1], ot_[i]], 'BogieGray')
        s.face([ib_[i], it_[i], it_[i + 1], ib_[i + 1]], 'BogieGray')
        s.face([ot_[i], ot_[i + 1], it_[i + 1], it_[i]], 'BogieGray')
        s.face([ob_[i], ib_[i], ib_[i + 1], ob_[i + 1]], 'BogieGray')
    for i in (0, n - 1):
        s.face([ob_[i], ot_[i], it_[i], ib_[i]], 'BogieGray')
    for i in range(n - 1):   # 下沿的橡胶排障条
        a_, b_ = P[i], P[i + 1]
        s.tube([(a_.x - 0.045, a_.y, z0 - 0.01), (b_.x - 0.045, b_.y, z0 - 0.01)], 0.03, 'Rubber', seg=8)
    for yy in (-0.9, -0.3, 0.3, 0.9):
        xf = float(np.interp(abs(yy), [0, 0.62, 1.22], [10.32, 10.28, 10.11]))
        s.box(9.88, xf, yy - 0.025, yy + 0.025, z0 + 0.05, z1, 'UnderGray')
    s.box(9.90, 10.20, -0.07, 0.07, 0.82, 0.94, 'BogieGray')        # 前端车钩（收在裙板后面）
    s.box(10.08, 10.24, -0.15, 0.15, 0.76, 1.00, 'BogieGray', bevel=0.02)
    s.build('Under_Skirt', C('Underfloor'))


def build_side_details():
    d = MB()
    for sy in (1, -1):
        yo = sy * 1.4765
        for c in DOORS:   # 门上方的绿色饰条
            d.box(c - 0.70, c + 0.70, yo, yo + sy * 0.003, 2.985, 3.05, 'YamanoteGreen')
        d.tube([(X_REAR + 0.05, sy * 1.468, 3.10), (X_SHELL_FRONT, sy * 1.468, 3.10)], 0.012, 'Stainless', seg=6)  # 雨水槽
        # 乘务员门外侧扶手与踏板
        for x in (CREW_DOOR[0] - 0.06, CREW_DOOR[1] + 0.06):
            d.tube(rounded_path([(x, sy * 1.476, 1.55), (x, sy * 1.53, 1.60), (x, sy * 1.53, 2.55), (x, sy * 1.476, 2.60)], 0.04),
                   0.014, 'PoleSteel', seg=8)
        for z in (0.62, 0.86):
            d.box(9.00, 9.42, sy * 1.30, sy * 1.46, z, z + 0.035, 'BogieGray')
    d.build('Body_SideDetails', C('Body'))

    lamp = MB()
    for sy in (1, -1):
        for x in (-9.45, 8.65):
            lamp.cyl(0.035, 0.025, 'SideLamp_' + ('L' if sy > 0 else 'R'), seg=16,
                     M=Mx((x, sy * 1.47, 3.02), (-sy * math.pi / 2, 0, 0)))
    lamp.build('Lamp_Side', C('Lamps'))

    # 侧面行先显示器 + JR 标
    dsp = MB()
    for sy in (1, -1):
        y = sy * 1.4785
        x0, x1 = -0.55, 0.45
        if sy > 0:
            dsp.quad([(x1, y, 2.905), (x0, y, 2.905), (x0, y, 3.035), (x1, y, 3.035)], 'DestPanel')
        else:
            dsp.quad([(x0, y, 2.905), (x1, y, 2.905), (x1, y, 3.035), (x0, y, 3.035)], 'DestPanel')
        rot = (math.pi / 2, 0, math.pi if sy > 0 else 0)
        text_mesh('DestText_Side' + ('L' if sy > 0 else 'R'), jp('山手線 渋谷・新宿方面', 'Yamanote Line'), 0.075,
                  'DestText', Mx((-0.05, sy * 1.481, 2.97), rot), C('Lamps'))
        text_mesh('Logo_JR' + ('L' if sy > 0 else 'R'), 'JR', 0.15, 'YamanoteGreen',
                  Mx((9.75, sy * 1.478, 2.97), rot), C('Body'))
    dsp.build('Dest_Side', C('Lamps'))


def build_roof():
    r = MB()
    r.box(-1.30, 1.30, -0.95, 0.95, 3.50, 3.88, 'Stainless', bevel=0.07, seg=3)   # 空调机组
    for x in (-0.62, 0.62):
        r.cyl(0.34, 0.02, 'VentDark', seg=32, M=Mx((x, 0, 3.875)))
        for k in range(-3, 4):
            r.box(x - 0.34, x + 0.34, k * 0.09 - 0.012, k * 0.09 + 0.012, 3.885, 3.90, 'Stainless')
    for sy in (1, -1):
        for k in range(10):
            x = -1.15 + k * 0.255
            r.box(x - 0.08, x + 0.08, sy * 0.95 - 0.004, sy * 0.95 + 0.004, 3.60, 3.80, 'VentDark')
    for x in (9.15, 9.45):   # 天线
        r.cyl(0.04, 0.03, 'RoofGray', M=Mx((x, 0.35, z_out_roof(0.35) - 0.01)))
        r.cyl(0.012, 0.24, 'Bezel', M=Mx((x, 0.35, z_out_roof(0.35))))
    r.build('Body_Roof', C('Body'))


def z_out_roof(y):
    pts = [p for p in OUT_HALF if p[1] > 3.0]
    return float(np.interp(abs(y), [p[0] for p in reversed(pts)], [p[1] for p in reversed(pts)]))


# ───────────────────────── 车门 ─────────────────────────
def leaf_mesh(name, w, z0, z1, wz0, wz1, stile, out_mat, in_mat, edge=+1, side=+1, rubber=True):
    """沿车体外轮廓弯曲的门扇（局部坐标：x 以门扇中心为 0）。edge=碰头一侧 (+1 → +x)"""
    mb = MB()
    t_o, t_i = 0.012, 0.042
    hw = w / 2

    def sheet(x0, x1, zs):
        O0 = [mb.v((x0, y_out(z) - t_o, z)) for z in zs]
        O1 = [mb.v((x1, y_out(z) - t_o, z)) for z in zs]
        I0 = [mb.v((x0, y_out(z) - t_i, z)) for z in zs]
        I1 = [mb.v((x1, y_out(z) - t_i, z)) for z in zs]
        for k in range(len(zs) - 1):
            mb.face([O0[k], O1[k], O1[k + 1], O0[k + 1]], out_mat)
            mb.face([I0[k], I0[k + 1], I1[k + 1], I1[k]], in_mat)
            mb.face([O0[k], O0[k + 1], I0[k + 1], I0[k]], out_mat)
            mb.face([O1[k], I1[k], I1[k + 1], O1[k + 1]], out_mat)
        mb.face([O0[0], I0[0], I1[0], O1[0]], out_mat)
        mb.face([O0[-1], O1[-1], I1[-1], I0[-1]], out_mat)

    zs_bottom = [z for z in (z0, 1.22, 1.36, 1.50) if z < wz0] + [wz0]
    sheet(-hw, hw, zs_bottom)
    sheet(-hw, hw, [wz1, z1])
    rub = 0.022 if rubber else 0
    sheet(-hw, -hw + stile, [wz0, wz1])
    sheet(hw - stile, hw - rub, [wz0, wz1])
    if rubber:
        yo = y_out(2.4)
        mb.box(hw - rub, hw, yo - 0.044, yo - 0.008, z0, z1, 'Rubber')
    yg = y_out(2.4) - 0.027
    mb.quad([(-hw + stile, yg, wz0), (hw - stile, yg, wz0), (hw - stile, yg, wz1), (-hw + stile, yg, wz1)], 'GlassSide')
    M = Matrix()
    if side < 0:
        M = MIRROR_Y @ M
    if edge < 0:
        M = MIRROR_X @ M
    if side < 0 or edge < 0:
        mb.xform(0, M)
    ob = mb.build(name, C('Rig'))
    me = ob.data
    bpy.data.objects.remove(ob)
    return me


def build_doors(ctrl):
    meshes = {}
    for side in (1, -1):
        for edge in (1, -1):
            meshes[(side, edge)] = leaf_mesh('DoorLeaf_%s%s' % ('L' if side > 0 else 'R', 'a' if edge > 0 else 'b'),
                                             LEAF_W, FLOOR + 0.004, DOOR_Z1 - 0.004, 2.03, 2.83, 0.11,
                                             'YamanoteGreen', 'DoorInner', edge=edge, side=side)
    leaves = []
    for side in (1, -1):
        sname = 'L' if side > 0 else 'R'
        for k, c in enumerate(DOORS):
            for edge, sgn in ((1, -1), (-1, 1)):   # edge=+1 的门扇在门中心 -x 侧，开门时往 -x 走
                base = c + sgn * LEAF_W / 2
                ob = bpy.data.objects.new('Door_%s%d_%s' % (sname, k + 1, 'a' if edge > 0 else 'b'), meshes[(side, edge)])
                C('Doors').objects.link(ob)
                ob.location = (base, 0, 0)
                ob['side'] = side
                ob['open_dir'] = sgn
                ob['travel'] = TRAVEL
                ob['base_x'] = base
                prop = 'door_left' if side > 0 else 'door_right'
                add_driver(ob, 'location', 0, '%.4f%+.4f*o*s' % (base, sgn * TRAVEL), {'o': 'door_open', 's': prop}, ctrl)
                leaves.append(ob)

    # 乘务员门（固定关闭）
    for side in (1, -1):
        w = CREW_DOOR[1] - CREW_DOOR[0]
        me = leaf_mesh('CrewDoor_' + ('L' if side > 0 else 'R'), w - 0.01, CAB_FLOOR + 0.025, 2.995, 2.15, 2.80, 0.09,
                       'Stainless', 'CabGray', side=side, rubber=False)
        ob = bpy.data.objects.new('CrewDoor_' + ('L' if side > 0 else 'R'), me)
        C('Doors').objects.link(ob)
        ob.location = ((CREW_DOOR[0] + CREW_DOOR[1]) / 2, 0, 0)

    # 窗玻璃（固定窗）
    g = MB()
    for sy in (1, -1):
        y = sy * (y_out(2.4) - 0.022)

        def pane(x0, x1, z0, z1, r=0.07):
            poly = rrect(x0, x1, z0, z1, r)
            g.face([g.v((x, y, z)) for x, z in poly], 'GlassSide')
        for a, b in SEC_MID:
            m = (a + b) / 2
            pane(m - 1.0, m + 1.0, WIN_Z0, WIN_Z1)
        pane(-9.55, -8.65, WIN_Z0, WIN_Z1)
        pane(CAB_WIN[0], CAB_WIN[1], 2.10, 2.85, 0.06)
        # 窗中间的横框（上部可倾倒的小窗）
        for a, b in SEC_MID:
            m = (a + b) / 2
            g.box(m - 1.0, m + 1.0, y - 0.012, y + 0.012, 2.58, 2.61, 'Frame')
            g.box(m - 0.012, m + 0.012, y - 0.012, y + 0.012, 2.61, WIN_Z1, 'Frame')
    g.build('Body_WindowGlass', C('Body'))
    return leaves


# ───────────────────────── 客室内装 ─────────────────────────
def seat_bench(mb, x0, n, w, sy, back, cush, frame=True):
    """长条座椅：x0 起往 +x 排 n 个座位，sy=±1 靠哪侧墙"""
    for k in range(n):
        xc = x0 + w * (k + 0.5)
        mb.cbox((xc, sy * 1.115, FLOOR + 0.375), (w - 0.012, 0.50, 0.11), cush, bevel=0.025, seg=3)
        mb.cbox((xc, sy * 1.345, FLOOR + 0.68), (w - 0.012, 0.075, 0.47), back,
                M=Mx(rot=(-sy * math.radians(9), 0, 0)), bevel=0.025, seg=3)
    if frame:
        L = n * w
        mb.box(x0 + 0.02, x0 + L - 0.02, *sorted((sy * 0.93, sy * 1.37)), FLOOR + 0.17, FLOOR + 0.315, 'SeatFrame')
        mb.box(x0, x0 + L, *sorted((sy * 1.36, sy * 1.40)), FLOOR + 0.93, FLOOR + 0.97, 'SeatFrame', bevel=0.01)


def sode(mb, x, sy, toward):
    """袖仕切り（座椅端部的大隔板）：下部不透明、上部磨砂玻璃；toward=+1 表示座椅在 +x 一侧"""
    t = 0.035
    poly = rrect(0.86, 1.42, FLOOR + 0.06, FLOOR + 0.98, 0.10)
    M = Matrix.Translation((x - t / 2, 0, 0)) @ MAP_YZ_X
    if sy < 0:
        M = MIRROR_Y @ M
    mb.prism(poly, t, 'InteriorWall', M=M)
    gp = rrect(0.92, 1.40, FLOOR + 0.98, FLOOR + 1.80, 0.12)
    n0 = mb.mark()
    mb.face([mb.v((x, sy * y, z)) for y, z in gp], 'GlassFrost')
    mb.tube(rounded_path([(x, sy * 1.40, FLOOR + 1.80), (x, sy * 0.90, FLOOR + 1.80), (x, sy * 0.90, FLOOR + 0.98)], 0.10),
            0.016, 'SeatFrame', seg=8)
    pole(mb, x + toward * 0.0, sy * 0.84)


def pole(mb, x, y):
    sy = 1 if y > 0 else -1
    pts = rounded_path([(x, y, FLOOR), (x, y, STRAP_Z - 0.20), (x, sy * 0.72, STRAP_Z)], 0.14, 6)
    mb.tube(pts, 0.016, 'PoleSteel', seg=10)
    mb.cyl(0.035, 0.01, 'PoleSteel', M=Mx((x, y, FLOOR)))


def build_interior():
    seats = MB()
    fix = MB()

    # 地板
    fix.box(X_REAR + 0.06, PART_X, -1.37, 1.37, FLOOR - 0.06, FLOOR, 'Floor')
    for c in DOORS:
        fix.box(c - 0.78, c + 0.78, -1.10, 1.10, FLOOR, FLOOR + 0.001, 'FloorDoor')
        for sy in (1, -1):
            fix.box(c - LEAF_W, c + LEAF_W, *sorted((sy * 1.37, sy * 1.43)), FLOOR - 0.02, FLOOR + 0.002, 'SillSteel')
            fix.box(c - LEAF_W, c + LEAF_W, *sorted((sy * 1.31, sy * 1.37)), FLOOR, FLOOR + 0.002, 'YellowLine')

    # 客室中间三段：7 人座（2+3+2，中间两根立柱）
    for a, b in SEC_MID:
        x0 = a + (b - a - 7 * SEAT_W) / 2
        for sy in (1, -1):
            seat_bench(seats, x0, 7, SEAT_W, sy, 'SeatBack', 'SeatCushion')
            sode(fix, x0 - 0.05, sy, +1)
            sode(fix, x0 + 7 * SEAT_W + 0.05, sy, -1)
            pole(fix, x0 + 2 * SEAT_W, sy * 0.88)
            pole(fix, x0 + 5 * SEAT_W, sy * 0.88)
    # 后端：优先座 3 人
    a, b = SEC_REAR
    for sy in (1, -1):
        seat_bench(seats, a + 0.03, 3, 0.44, sy, 'PrioBack', 'PrioCushion')
        sode(fix, a + 0.03 + 1.32 + 0.06, sy, -1)

    # 前端：自由空间（轮椅/婴儿车），靠背垫 + 扶手
    a, b = SEC_FREE
    for sy in (1, -1):
        fix.box(a + 0.12, b - 0.10, *sorted((sy * 1.30, sy * 1.41)), FLOOR + 0.68, FLOOR + 0.98, 'LeanPad', bevel=0.03)
        fix.tube(rounded_path([(a + 0.12, sy * 1.42, FLOOR + 1.05), (a + 0.12, sy * 1.33, FLOOR + 1.05),
                               (b - 0.10, sy * 1.33, FLOOR + 1.05), (b - 0.10, sy * 1.42, FLOOR + 1.05)], 0.05),
                 0.016, 'PoleSteel', seg=8)

    # 门两侧墙上的竖扶手、门上开闭灯、紧急通报器
    lamps = MB()
    for c in DOORS:
        for sy in (1, -1):
            for x in (c - LEAF_W - 0.07, c + LEAF_W + 0.07):
                fix.tube(rounded_path([(x, sy * 1.42, FLOOR + 0.85), (x, sy * 1.33, FLOOR + 0.90),
                                       (x, sy * 1.33, FLOOR + 1.70), (x, sy * 1.42, FLOOR + 1.75)], 0.05),
                         0.016, 'PoleSteel', seg=8)
            lamps.box(c - 0.05, c + 0.05, *sorted((sy * 1.37, sy * 1.40)), 2.99, 3.02,
                      'DoorLamp_' + ('L' if sy > 0 else 'R'))
    fix.box(DOORS[1] + 0.80, DOORS[1] + 0.95, 1.40, 1.425, FLOOR + 1.05, FLOOR + 1.25, 'SOS', bevel=0.01)
    fix.box(DOORS[2] - 0.95, DOORS[2] - 0.80, -1.425, -1.40, FLOOR + 1.05, FLOOR + 1.25, 'SOS', bevel=0.01)
    lamps.build('Lamp_DoorIndicator', C('Lamps'))

    # 行李架（只在座位上方）
    def rack(x0, x1, sy):
        for k in range(6):
            yy = 1.12 + k * 0.055
            fix.tube([(x0, sy * yy, RACK_Z), (x1, sy * yy, RACK_Z)], 0.006, 'RackMetal', seg=6)
        fix.tube([(x0, sy * 1.09, RACK_Z + 0.01), (x1, sy * 1.09, RACK_Z + 0.01)], 0.015, 'RackMetal', seg=8)
        nb = max(2, int((x1 - x0) / 1.1) + 1)
        for k in range(nb):
            x = x0 + (x1 - x0) * k / (nb - 1)
            fix.tube(rounded_path([(x, sy * 1.09, RACK_Z + 0.01), (x, sy * 1.42, RACK_Z + 0.01),
                                   (x, sy * 1.42, RACK_Z + 0.16)], 0.04), 0.008, 'RackMetal', seg=6)
    for a, b in SEC_MID:
        for sy in (1, -1):
            rack(a + 0.10, b - 0.10, sy)
    for sy in (1, -1):
        rack(SEC_REAR[0] + 0.05, SEC_REAR[1] - 0.25, sy)

    # 天花板：中央风道面板 + 出风口 + 两条 LED 灯带
    ceil = MB()
    ceil.box(X_REAR + 0.06, PART_X, -0.40, 0.40, 3.385, 3.395, 'Ceiling')
    for sy in (1, -1):
        ceil.box(X_REAR + 0.10, PART_X - 0.04, *sorted((sy * 0.31, sy * 0.35)), 3.380, 3.386, 'VentDark')
    ceil.build('Interior_Ceiling', C('Interior'))
    led = MB()
    for sy in (1, -1):
        led.box(X_REAR + 0.12, PART_X - 0.06, *sorted((sy * 0.55, sy * 0.69)), 3.355, 3.375, 'LED_Interior', bevel=0.006, seg=1)
    led.build('Lamp_InteriorLED', C('Lamps'))

    # 吊环横杆 + 吊杆
    for sy in (1, -1):
        fix.tube([(X_REAR + 0.10, sy * 0.72, STRAP_Z), (PART_X - 0.05, sy * 0.72, STRAP_Z)], 0.015, 'PoleSteel', seg=10)
        nh = 13
        for k in range(nh):
            x = X_REAR + 0.30 + (PART_X - X_REAR - 0.60) * k / (nh - 1)
            fix.tube([(x, sy * 0.72, STRAP_Z), (x, sy * 0.72, z_ceiling(0.72) - 0.01)], 0.010, 'PoleSteel', seg=6)
    fix.build('Interior_Fixtures', C('Interior'))
    seats.build('Interior_Seats', C('Interior'))

    # 吊环（三角形，山手线绿；优先座附近为黄色）
    st = MB()
    ring = rounded_path([(0, 0, -0.215), (0.065, 0, -0.335), (-0.065, 0, -0.335)], 0.035, 5, closed=True)
    xs = []
    x = X_REAR + 0.32
    while x < PART_X - 0.25:
        xs.append(x)
        x += 0.26
    for sy in (1, -1):
        for x in xs:
            col = 'StrapYellow' if x < SEC_REAR[1] + 0.05 else 'StrapGreen'
            st.box(x - 0.014, x + 0.014, sy * 0.72 - 0.004, sy * 0.72 + 0.004, STRAP_Z - 0.21, STRAP_Z + 0.017, 'StrapBelt')
            st.tube([Vector((x, sy * 0.72, STRAP_Z)) + p for p in ring], 0.011, col, seg=8, closed=True)
    st.build('Interior_Straps', C('Interior'))

    # 液晶屏：行李架上方每段 3 块（21.5 英寸），门上方 2 块，两端墙上方 2 块
    scr = MB()

    def screen(c, w, h, mat, normal_yz=None, facing_x=None):
        """c=中心。normal_yz=(ny,nz) 朝向（在 yz 平面内）；facing_x=±1 朝 ±x"""
        cx, cy, cz = c
        if facing_x is not None:
            n = Vector((facing_x, 0, 0))
            right = Vector((0, -facing_x, 0))
            up = Vector((0, 0, 1))
        else:
            n = Vector((0, normal_yz[0], normal_yz[1])).normalized()
            up = Vector((0, -n.z, n.y)) if n.y < 0 else Vector((0, n.z, -n.y))
            if up.z < 0:
                up = -up
            right = up.cross(n)
        ctr = Vector(c)
        M = Matrix((right.to_4d(), up.to_4d(), n.to_4d(), (0, 0, 0, 1))).transposed()
        M[0][3], M[1][3], M[2][3] = ctr
        M[3][0] = M[3][1] = M[3][2] = 0
        scr.screen_box(w + 0.03, h + 0.03, M)
        p =[M @ Vector((sx * w / 2, sy_ * h / 2, 0.0155)) for sx, sy_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        scr.quad(p, mat)

    ads = ['LCD_Ad0', 'LCD_Ad1', 'LCD_Ad2']
    for i, (a, b) in enumerate(SEC_MID):
        m = (a + b) / 2
        for sy in (1, -1):
            for k in (-1, 0, 1):
                screen((m + k * 0.50, sy * 1.25, 3.10), 0.476, 0.268, ads[(i + k + 1) % 3],
                       normal_yz=(-sy * 0.72, -0.70))
    for c in DOORS:
        for sy in (1, -1):
            screen((c - 0.205, sy * 1.25, 3.10), 0.376, 0.235, 'LCD_Info', normal_yz=(-sy * 0.72, -0.70))
            screen((c + 0.205, sy * 1.25, 3.10), 0.376, 0.235, 'LCD_Ad%d' % (DOORS.index(c) % 3),
                   normal_yz=(-sy * 0.72, -0.70))
    for yy in (-0.255, 0.255):
        screen((X_REAR + 0.085, yy, 3.24), 0.476, 0.268, 'LCD_Info' if yy < 0 else 'LCD_Ad1', facing_x=1)
        screen((PART_X - 0.02, yy, 3.24), 0.476, 0.268, 'LCD_Info' if yy > 0 else 'LCD_Ad2', facing_x=-1)
    scr.build('Interior_Screens', C('Interior'))




# ───────────────────────── 驾驶室隔墙与驾驶室 ─────────────────────────
def build_cab():
    # 隔墙轮廓 = 内轮廓（地板以上）
    poly = [(y, z) for y, z in INNER if z > FLOOR + 0.01]
    poly = [(y_in(FLOOR + 0.01) - 0.004, FLOOR)] + [(y * 0.997, z - 0.003) for y, z in poly] + [(-(y_in(FLOOR + 0.01) - 0.004), FLOOR)]
    mb = MB()
    mb.prism(poly, PART_T, 'InteriorWall', M=Matrix.Translation((PART_X, 0, 0)) @ MAP_YZ_X)
    wall = mb.build('Cab_Partition', C('Cab'), smooth=None)
    cut = MB()
    cut.box(PART_X - 0.1, PART_X + 0.2, -0.32, 0.32, FLOOR, 3.02, 'Rubber')
    M = Matrix.Translation((PART_X - 0.1, 0, 0)) @ MAP_YZ_X
    cut.prism(rrect(-1.25, -0.48, 2.00, 2.80, 0.05), 0.3, 'Rubber', M=M)
    cut.prism(rrect(0.50, 1.20, 2.15, 2.70, 0.05), 0.3, 'Rubber', M=M)
    boolean_apply(wall, cut)
    assign_by(wall, ['InteriorWall', 'CabGray', 'Frame'],
              lambda c, n: 0 if c.x < PART_X + 0.005 else (1 if c.x > PART_X + PART_T - 0.005 else 2))

    g = MB()
    xg = PART_X + PART_T / 2
    for y0, y1, z0, z1 in ((-1.25, -0.48, 2.00, 2.80), (0.50, 1.20, 2.15, 2.70)):
        g.face([g.v((xg, y, z)) for y, z in rrect(y0, y1, z0, z1, 0.05)], 'GlassClear')
    # 隔墙门（关闭）
    x0, x1 = PART_X + 0.012, PART_X + 0.038
    g.box(x0, x1, -0.32, -0.20, FLOOR, 3.02, 'DoorInner')
    g.box(x0, x1, 0.20, 0.32, FLOOR, 3.02, 'DoorInner')
    g.box(x0, x1, -0.20, 0.20, FLOOR, 2.00, 'DoorInner')
    g.box(x0, x1, -0.20, 0.20, 2.80, 3.02, 'DoorInner')
    g.quad([(xg, -0.20, 2.00), (xg, 0.20, 2.00), (xg, 0.20, 2.80), (xg, -0.20, 2.80)], 'GlassClear')
    g.box(x0 - 0.03, x0, 0.24, 0.28, 1.95, 2.15, 'PoleSteel', bevel=0.006)
    g.build('Cab_PartitionGlass', C('Cab'))

    c = MB()
    c.box(PART_X + PART_T, X_SHELL_FRONT + 0.02, -1.36, 1.36, FLOOR - 0.01, CAB_FLOOR, 'CabFloor')
    # 驾驶台（侧面轮廓沿宽度拉伸）
    prof = [(9.58, CAB_FLOOR), (10.02, CAB_FLOOR), (10.02, 2.10), (9.66, 2.03), (9.58, 1.96)]
    c.prism(prof, 2.62, 'CabConsole', M=Matrix.Translation((0, -1.31, 0)) @ MAP_XZ_Y)
    # 仪表罩（司机侧 +Y）
    c.box(9.70, 9.98, 0.20, 1.26, 2.03, 2.22, 'CabConsole', bevel=0.02)
    # 主控制器（单手柄）
    c.box(9.36, 9.56, 1.02, 1.26, CAB_FLOOR, 1.98, 'CabConsole', bevel=0.02)
    c.tube([(9.46, 1.14, 1.98), (9.42, 1.14, 2.12)], 0.012, 'PoleSteel', seg=8)
    c.tube([(9.42, 1.08, 2.12), (9.42, 1.20, 2.12)], 0.018, 'Rubber', seg=10)
    # 司机座椅
    c.cyl(0.05, 0.36, 'SeatFrame', M=Mx((9.18, 0.70, CAB_FLOOR)))
    c.cbox((9.18, 0.70, CAB_FLOOR + 0.42), (0.48, 0.48, 0.10), 'CabSeat', bevel=0.03, seg=3)
    c.cbox((8.99, 0.70, CAB_FLOOR + 0.78), (0.09, 0.46, 0.62), 'CabSeat', M=Mx(rot=(0, math.radians(-10), 0)), bevel=0.03, seg=3)
    c.cbox((8.94, 0.70, CAB_FLOOR + 1.17), (0.08, 0.30, 0.16), 'CabSeat', M=Mx(rot=(0, math.radians(-10), 0)), bevel=0.03, seg=2)
    # 车掌侧小台
    c.box(9.30, 9.58, -1.30, -0.75, CAB_FLOOR, 1.95, 'CabConsole', bevel=0.02)
    c.build('Cab_Interior', C('Cab'))

    # 驾驶台显示屏（3 块，朝向司机）
    s = MB()
    ang = math.radians(50)
    for yy in (0.40, 0.73, 1.06):
        cx, cz = 9.82, 2.17
        right = Vector((0, -1, 0))
        up = Vector((math.sin(ang), 0, math.cos(ang)))
        n = right.cross(up)   # 指向司机（-x 并略向上）
        if n.x > 0:
            n = -n
        M = Matrix((right.to_4d(), up.to_4d(), n.to_4d(), (0, 0, 0, 1))).transposed()
        M[0][3], M[1][3], M[2][3] = cx, yy, cz
        M[3][0] = M[3][1] = M[3][2] = 0
        p = [M @ Vector((sx * 0.15, sy_ * 0.095, 0.02)) for sx, sy_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        s.quad(p, 'LCD_Cab')
    s.build('Cab_Screens', C('Cab'))


# ───────────────────────── 车底：转向架、设备箱、车钩 ─────────────────────────
def build_bogie(bx, name):
    b = MB()
    for ax in (-1.05, 1.05):
        x = bx + ax
        for sy in (1, -1):
            yc = sy * 0.5575
            Mw = Mx((x, yc - 0.065, 0.43), (-math.pi / 2, 0, 0))
            b.cyl(0.43, 0.13, 'WheelSteel', seg=40, M=Mw)
            Mf = Mx((x, yc - sy * 0.065 - (0.02 if sy > 0 else 0), 0.43), (-math.pi / 2, 0, 0))
            b.cyl(0.455, 0.02, 'WheelSteel', seg=40, M=Mf)
            b.cyl(0.33, 0.004, 'BogieGray', seg=32, M=Mx((x, yc + sy * 0.067 - (0.004 if sy > 0 else 0), 0.43), (-math.pi / 2, 0, 0)))
            b.cyl(0.31, 0.10, 'WheelSteel', seg=32, M=Mx((x, sy * 0.30 - 0.05, 0.43), (-math.pi / 2, 0, 0)))  # 车轴盘式制动盘
            b.box(x - 0.15, x + 0.15, *sorted((sy * 0.88, sy * 1.10)), 0.32, 0.56, 'BogieGray', bevel=0.03)  # 轴箱
            # 轴簧（螺旋弹簧）
            hel = []
            for k in range(5 * 16 + 1):
                a = 2 * math.pi * k / 16
                hel.append((x + 0.075 * math.cos(a), sy * 0.99 + 0.075 * math.sin(a), 0.56 + 0.13 * k / 80))
            b.tube(hel, 0.016, 'UnderGray', seg=6)
        b.cyl(0.085, 2.06, 'WheelSteel', seg=20, M=Mx((x, -1.03, 0.43), (-math.pi / 2, 0, 0)))
    # 侧梁（中间下沉的“鱼腹”形）
    prof = [(-1.45, 0.70), (-0.75, 0.70), (-0.45, 0.55), (0.45, 0.55), (0.75, 0.70), (1.45, 0.70),
            (1.45, 0.84), (0.75, 0.84), (0.45, 0.76), (-0.45, 0.76), (-0.75, 0.84), (-1.45, 0.84)]
    for sy in (1, -1):
        b.prism([(bx + x, z) for x, z in prof], 0.17, 'BogieGray', M=Matrix.Translation((0, sy * 0.99 - 0.085, 0)) @ MAP_XZ_Y)
        b.cyl(0.19, 0.20, 'AirSpring', seg=24, M=Mx((bx, sy * 0.99, 0.76)))   # 空气弹簧
        b.cyl(0.16, 0.03, 'BogieGray', seg=24, M=Mx((bx, sy * 0.99, 0.96)))
        b.box(bx - 0.55, bx - 0.30, *sorted((sy * 0.66, sy * 0.84)), 0.52, 0.66, 'UnderGray', bevel=0.02)  # 制动缸
        b.box(bx + 0.30, bx + 0.55, *sorted((sy * 0.66, sy * 0.84)), 0.52, 0.66, 'UnderGray', bevel=0.02)
    b.box(bx - 0.22, bx + 0.22, -0.99, 0.99, 0.52, 0.72, 'BogieGray', bevel=0.03)   # 横梁
    b.box(bx - 0.10, bx + 0.10, -0.15, 0.15, 0.72, 0.95, 'BogieGray')               # 中心销
    return b.build(name, C('Underfloor'))


def build_underfloor():
    u = MB()
    u.box(X_REAR + 0.05, X_SHELL_FRONT, -1.30, 1.30, 0.93, 1.06, 'UnderGray')   # 底架
    boxes = [(-4.6, -2.4, -1.25, -0.20, 0.50, 0.93), (-2.0, -0.6, -1.20, -0.50, 0.58, 0.93),
             (0.9, 2.4, 0.30, 1.20, 0.55, 0.93), (2.8, 4.7, -1.20, -0.40, 0.52, 0.93),
             (-4.2, -3.0, 0.50, 1.20, 0.62, 0.93), (3.0, 4.2, 0.55, 1.20, 0.60, 0.93),
             (-0.4, 0.6, -0.30, 0.35, 0.66, 0.93)]
    for x0, x1, y0, y1, z0, z1 in boxes:
        u.box(x0, x1, y0, y1, z0, z1, 'UnderGray', bevel=0.02)
        u.box(x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 - 0.05, z0 - 0.015, z0, 'BogieGray')
    for y, r in ((0.80, 0.22), (-0.10, 0.16)):   # 储气缸
        u.cyl(r, 2.6, 'BogieGray', seg=24, M=Mx((-2.0, y, 0.72), (0, math.pi / 2, 0)))
    # 后端车钩（密着式）
    u.box(-10.05, -9.80, -0.08, 0.08, 0.82, 0.95, 'BogieGray')
    u.box(-10.22, -10.05, -0.16, 0.16, 0.76, 1.00, 'BogieGray', bevel=0.02)
    u.build('Under_Equipment', C('Underfloor'))
    for i, bx in enumerate(BOGIES):
        build_bogie(bx, 'Under_Bogie%d' % (i + 1))


# ───────────────────────── 环境：轨道、站台 ─────────────────────────
def build_environment():
    e = MB()
    rail = [(-0.0635, -0.153), (0.0635, -0.153), (0.0635, -0.140), (0.010, -0.120), (0.008, -0.050),
            (0.032, -0.040), (0.0325, 0.0), (-0.0325, 0.0), (-0.032, -0.040), (-0.008, -0.050),
            (-0.010, -0.120), (-0.0635, -0.140)]
    for sy in (1, -1):
        e.prism([(sy * 0.566 + y, z) for y, z in rail], 40.0, 'Rail', M=Matrix.Translation((-20, 0, 0)) @ MAP_YZ_X)
    x = -19.8
    while x < 20:
        e.box(x - 0.10, x + 0.10, -1.0, 1.0, -0.33, -0.153, 'Sleeper')
        x += 0.6
    e.prism([(-2.2, -0.75), (2.2, -0.75), (1.55, -0.30), (-1.55, -0.30)], 40.0, 'Ballast',
            M=Matrix.Translation((-20, 0, 0)) @ MAP_YZ_X)
    e.box(-40, 40, -30, 30, -0.80, -0.75, 'Ground')
    # 站台（右侧 -Y）
    e.box(-16, 16, -7.5, -1.55, -0.75, 1.10, 'Platform')
    e.box(-16, 16, -1.75, -1.55, 1.10, 1.103, 'PlatformWhite')
    e.box(-16, 16, -2.65, -2.35, 1.10, 1.106, 'PlatformYellow')
    e.build('Env_TrackPlatform', C('Environment'))


# ───────────────────────── 控制器、驱动器、灯光、相机 ─────────────────────────
def make_controls():
    ctrl = bpy.data.objects.new('Train_Controls', None)
    C('Rig').objects.link(ctrl)
    ctrl.location = (0, 0, 4.5)
    ctrl.empty_display_size = 0.3
    defaults = dict(door_open=0.0, door_left=0, door_right=1, lights=1.0, headlight=1, night=0.0)
    for k, v in defaults.items():
        ctrl[k] = v
        ui = ctrl.id_properties_ui(k)
        if isinstance(v, float):
            ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0)
        else:
            ui.update(min=0, max=1)
    return ctrl


def add_driver(owner, path, index, expr, vars, ctrl):
    fc = owner.driver_add(path, index) if index is not None and index >= 0 else owner.driver_add(path)
    d = fc.driver
    d.type = 'SCRIPTED'
    d.expression = expr
    for name, prop in vars.items():
        v = d.variables.new()
        v.name = name
        v.type = 'SINGLE_PROP'
        t = v.targets[0]
        t.id_type = 'OBJECT'
        t.id = ctrl
        t.data_path = '["%s"]' % prop
    return fc


def drive_materials(ctrl):
    def em(name, expr, vars):
        add_driver(emission_socket(MATS[name]), 'default_value', -1, expr, vars, ctrl)
    em('LED_Interior', '6*l', {'l': 'lights'})
    em('Headlight', '40*l*h', {'l': 'lights', 'h': 'headlight'})
    em('MarkerLamp', '10*l*h', {'l': 'lights', 'h': 'headlight'})
    em('Taillight', '25*l*(1-h)', {'l': 'lights', 'h': 'headlight'})
    em('DoorLamp_L', 'min(1,o*40)*s*8', {'o': 'door_open', 's': 'door_left'})
    em('DoorLamp_R', 'min(1,o*40)*s*8', {'o': 'door_open', 's': 'door_right'})
    em('SideLamp_L', 'min(1,o*40)*s*15', {'o': 'door_open', 's': 'door_left'})
    em('SideLamp_R', 'min(1,o*40)*s*15', {'o': 'door_open', 's': 'door_right'})


def make_lights(ctrl):
    lc = C('Lamps')
    for sy in (1, -1):
        ld = bpy.data.lights.new('InteriorArea_%s' % ('L' if sy > 0 else 'R'), 'AREA')
        ld.shape = 'RECTANGLE'
        ld.size = PART_X - X_REAR - 0.3
        ld.size_y = 0.14
        ld.energy = 320
        ld.color = (0.97, 0.98, 1.0)
        ob = bpy.data.objects.new(ld.name, ld)
        lc.objects.link(ob)
        ob.location = ((X_REAR + PART_X) / 2, sy * 0.62, 3.35)
        add_driver(ld, 'energy', -1, '320*l', {'l': 'lights'}, ctrl)
        ob['web_skip'] = 1
    for sy in (1, -1):
        sp = bpy.data.lights.new('Headlight_%s' % ('L' if sy > 0 else 'R'), 'SPOT')
        sp.energy = 5000
        sp.spot_size = math.radians(42)
        sp.spot_blend = 0.35
        sp.color = (1.0, 0.96, 0.88)
        sp.shadow_soft_size = 0.05
        ob = bpy.data.objects.new(sp.name, sp)
        lc.objects.link(ob)
        ob.location = (10.36, sy * 0.92, 1.44)
        ob.rotation_euler = (0, math.radians(-87), 0)
        add_driver(sp, 'energy', -1, '5000*l*h', {'l': 'lights', 'h': 'headlight'}, ctrl)
        pt = bpy.data.lights.new('Taillight_%s' % ('L' if sy > 0 else 'R'), 'POINT')
        pt.energy = 20
        pt.color = (1, 0.1, 0.05)
        pt.shadow_soft_size = 0.05
        ob = bpy.data.objects.new(pt.name, pt)
        lc.objects.link(ob)
        ob.location = (10.36, sy * 0.70, 1.42)
        add_driver(pt, 'energy', -1, '20*l*(1-h)', {'l': 'lights', 'h': 'headlight'}, ctrl)
    sun = bpy.data.lights.new('Sun', 'SUN')
    sun.energy = 3.5
    sun.angle = math.radians(1.5)
    ob = bpy.data.objects.new('Sun', sun)
    C('Environment').objects.link(ob)
    ob.rotation_euler = (math.radians(50), math.radians(10), math.radians(-30))
    add_driver(sun, 'energy', -1, '3.5*(1-n)', {'n': 'night'}, ctrl)

    w = bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (0.42, 0.55, 0.75, 1)
    add_driver(bg.inputs['Strength'], 'default_value', -1, '0.9*(1-n)+0.012', {'n': 'night'}, ctrl)


def look_cam(name, loc, target, lens=28):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.05
    ob = bpy.data.objects.new(name, cd)
    C('Rig').objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob


def make_cameras():
    ext = look_cam('Cam_Exterior', (17.5, -8.5, 3.6), (3.5, 0.0, 2.0), 30)
    look_cam('Cam_Side', (0.0, 13.0, 2.4), (0.0, 0.0, 2.0), 22)
    look_cam('Cam_Front', (15.5, 3.2, 2.0), (10.0, 0.0, 1.9), 35)
    look_cam('Cam_Under', (2.0, 6.0, 0.5), (6.5, 0.0, 0.7), 24)
    look_cam('Cam_Interior', (-8.9, 0.30, 2.70), (6.0, -0.15, 2.45), 18)
    look_cam('Cam_Cab', (9.20, 0.70, 2.58), (16.0, 0.40, 2.10), 22)
    bpy.context.scene.camera = ext


def scene_settings():
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    try:
        sc.eevee.use_raytracing = True
        sc.eevee.use_shadows = True
    except AttributeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.frame_start, sc.frame_end = 1, 240
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'
    C('Rig').hide_render = True


# ───────────────────────── 导出 ─────────────────────────
def export_glb(path):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    kw = dict(filepath=path, export_format='GLB', use_selection=False, export_apply=True,
              export_extras=True, export_yup=True, export_cameras=False, export_lights=False,
              export_animations=False)
    hide = []
    lc = bpy.context.view_layer.layer_collection.children['Rig']
    lc.exclude = True
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ('export_animations', 'export_cameras', 'export_lights'):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    lc.exclude = False
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
    dst = os.path.join(OUT, 'E235电车_离线版.html')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[OK] wrote', dst)


def render_previews(ctrl):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dev in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.type == dev for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    sc.cycles.device = 'GPU'
                    print('[INFO] Cycles device:', dev)
                    break
            except TypeError:
                continue
    except Exception:
        pass
    sc.cycles.samples = 48 if RENDER_FAST else 256
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = (960, 540) if RENDER_FAST else (1920, 1080)
    shots = [('exterior_day', 'Cam_Exterior', dict(night=0.0, door_open=0.0)),
             ('exterior_night_open', 'Cam_Exterior', dict(night=1.0, door_open=1.0)),
             ('side', 'Cam_Side', dict(night=0.0, door_open=0.0)),
             ('front', 'Cam_Front', dict(night=0.0, door_open=0.0)),
             ('bogie', 'Cam_Under', dict(night=0.0, door_open=0.0)),
             ('interior', 'Cam_Interior', dict(night=1.0, door_open=0.0)),
             ('cab', 'Cam_Cab', dict(night=0.0, door_open=0.0))]
    only = os.environ.get('E235_SHOTS')
    for name, cam, props in shots:
        if only and name not in only.split(','):
            continue
        for k, v in props.items():
            ctrl[k] = v
        ctrl.update_tag()
        bpy.context.view_layer.update()
        sc.camera = bpy.data.objects[cam]
        sc.render.filepath = os.path.join(OUT, 'render_%s.png' % name)
        bpy.ops.render.render(write_still=True)
        print('[OK] rendered', name)
    ctrl['night'] = 0.0
    ctrl['door_open'] = 0.0
    sc.camera = bpy.data.objects['Cam_Exterior']
    scene_settings()


def main():
    os.makedirs(OUT, exist_ok=True)
    reset()
    I = make_images()
    make_materials(I)
    ctrl = make_controls()
    build_shell()
    build_end_wall()
    build_front()
    build_side_details()
    build_roof()
    build_doors(ctrl)
    build_interior()
    build_cab()
    build_underfloor()
    build_environment()
    drive_materials(ctrl)
    make_lights(ctrl)
    make_cameras()
    scene_settings()

    glb = os.path.join(OUT, 'train.glb')
    export_glb(glb)
    if not NO_HTML:
        write_html(glb)
    if RENDER:
        render_previews(ctrl)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'train.blend'), compress=True)
    print('[OK] saved', os.path.join(OUT, 'train.blend'))
    print('[DONE]')


if __name__ == '__main__':
    main()
