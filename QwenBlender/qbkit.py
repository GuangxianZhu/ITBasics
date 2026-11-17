# -*- coding: utf-8 -*-
"""
qbkit —— 给本地模型（Qwen）用的 Blender 建模工具箱
整理自朱工以前的建模脚本（无刷电机、五指灵巧手等）里的常用写法。

约定（必须遵守，详见 建模规范.md）：
  * 所有尺寸单位都是 毫米（mm）。场景单位已设成 1 Blender 单位 = 1 mm。
  * +Z 朝上，地面是 z = 0。物体默认"放在地面上"由你自己算好 at 的 z 值。
  * at=(x, y, z) 永远是物体的【中心点】（包围盒中心），不是底面。
  * axis='X' / 'Y' / 'Z' 表示圆柱、管、回转体的轴线方向。
  * 每个零件都要起一个有意义的英文名字，例如 'base_plate', 'shaft', 'bolt_1'。

最常用的几个函数：
  reset()                        清空场景（每个模型脚本第一行调用）
  mat(name, hexcolor, metal, rough)  新建材质
  box / cyl / tube / cone / sphere   基本体
  revolve(name, profile, ...)    回转体：profile = [(半径, 轴向位置), ...]
  extrude(name, outline, h, ...) 二维轮廓拉伸，可带孔
  pipe(name, points, r, ...)     圆截面沿折线/曲线扫掠（管子、导线、弹簧）
  cut(target, tool)              布尔差集（在 target 上挖掉 tool，tool 自动删除）
  join(target, other)            布尔并集
  hole(target, r, at, axis, depth)  打圆孔（通孔或盲孔）
  copy(obj, name, at, rot)       复制零件
  polar(obj, n, axis, center)    绕轴等分阵列复制 n-1 个
  rotate(obj, deg, axis)         绕物体自身中心旋转
  info(obj)                      打印尺寸和位置，自己核对用
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

MAT_CACHE = {}
_DEFAULT = None


# ------------------------------------------------------------------ 场景
def reset():
    """清空场景，设置单位为 mm。每个模型脚本开头必须调用。"""
    global _DEFAULT
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                 bpy.data.lights, bpy.data.images):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    MAT_CACHE.clear()
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    _DEFAULT = mat('default_gray', '#9aa3ad', 0.3, 0.5)


def collection(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


# ------------------------------------------------------------------ 材质
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hexcol(h):
    h = h.lstrip('#')
    return tuple(_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def mat(name, hexcolor='#9aa3ad', metal=0.0, rough=0.5):
    """新建（或取回同名的）材质。hexcolor 例如 '#c9cdd2'。metal 0~1，rough 0~1。"""
    if name in MAT_CACHE:
        return MAT_CACHE[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    col = _hexcol(hexcolor)
    nt = m.node_tree
    if nt is not None:
        b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if b is not None:
            b.inputs['Base Color'].default_value = (*col, 1.0)
            b.inputs['Metallic'].default_value = metal
            b.inputs['Roughness'].default_value = rough
    m.diffuse_color = (*col, 1.0)
    m.metallic = metal
    m.roughness = rough
    MAT_CACHE[name] = m
    return m


# ------------------------------------------------------------------ 内部工具
def _axis_matrix(axis):
    """把局部 +Z 转到指定轴方向的旋转矩阵"""
    axis = axis.upper()
    if axis == 'Z':
        return Matrix.Identity(4)
    if axis == 'X':
        return Matrix.Rotation(math.radians(90), 4, 'Y')
    if axis == 'Y':
        return Matrix.Rotation(math.radians(-90), 4, 'X')
    raise ValueError("axis 只能是 'X'、'Y'、'Z'")


def _new_object(name, bm, material, coll, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    collection(coll).objects.link(ob)
    me.materials.append(material or _DEFAULT)
    for p in me.polygons:
        p.use_smooth = False
    if bevel > 0:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = bevel
        md.segments = 2
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(40)
        _apply_modifiers(ob)
    _smooth_by_angle(ob.data, 35)
    return ob


def _smooth_by_angle(me, deg):
    try:
        me.shade_smooth()
        if hasattr(me, 'set_sharp_from_angle'):
            me.set_sharp_from_angle(angle=math.radians(deg))
    except Exception:
        pass


def _apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = new
    new.name = ob.name
    bpy.data.meshes.remove(old)


def _place(bm, at, axis):
    """bm 已经以原点为中心、沿 +Z 建好；转到 axis 方向再移到 at"""
    m = Matrix.Translation(Vector(at)) @ _axis_matrix(axis)
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)


def _check_num(**kw):
    for k, v in kw.items():
        if v is None or (isinstance(v, (int, float)) and (v <= 0 or v != v)):
            raise ValueError(f"参数 {k}={v} 必须是正数")


# ------------------------------------------------------------------ 基本体
def box(name, size, at=(0, 0, 0), mat=None, bevel=0.0, coll='Model'):
    """长方体。size=(长x, 宽y, 高z) mm；at=中心点。bevel>0 时倒圆边（mm）。"""
    sx, sy, sz = size
    _check_num(sx=sx, sy=sy, sz=sz)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
    return _new_object(name, bm, mat, coll, bevel)


def cyl(name, r, h, at=(0, 0, 0), axis='Z', mat=None, seg=64, bevel=0.0, coll='Model'):
    """实心圆柱。r=半径，h=长度（沿 axis），at=中心点。"""
    _check_num(r=r, h=h)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=h)
    _place(bm, at, axis)
    return _new_object(name, bm, mat, coll, bevel)


def cone(name, r1, r2, h, at=(0, 0, 0), axis='Z', mat=None, seg=64, coll='Model'):
    """圆台/圆锥。r1=轴向负端半径，r2=轴向正端半径（可以为 0），at=中心点。"""
    _check_num(h=h)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=h)
    _place(bm, at, axis)
    return _new_object(name, bm, mat, coll)


def tube(name, r_out, r_in, h, at=(0, 0, 0), axis='Z', mat=None, seg=64, coll='Model'):
    """空心管。r_out > r_in。at=中心点。"""
    _check_num(r_out=r_out, r_in=r_in, h=h)
    if r_in >= r_out:
        raise ValueError("tube 要求 r_out > r_in")
    prof = [(r_in, -h / 2), (r_out, -h / 2), (r_out, h / 2), (r_in, h / 2)]
    return revolve(name, prof, at=at, axis=axis, mat=mat, seg=seg, coll=coll)


def sphere(name, r, at=(0, 0, 0), mat=None, seg=48, coll='Model'):
    _check_num(r=r)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    bmesh.ops.translate(bm, vec=Vector(at), verts=bm.verts)
    ob = _new_object(name, bm, mat, coll)
    _smooth_by_angle(ob.data, 180)
    return ob


def revolve(name, profile, at=(0, 0, 0), axis='Z', mat=None, seg=64, coll='Model'):
    """回转体。profile=[(半径, 轴向位置), ...] 是一个闭合轮廓（首尾自动相连），
    绕 axis 旋转一周。轴向位置相对 at。半径为 0 的点会落在轴线上。
    例：带台阶的轴 profile=[(0,0),(5,0),(5,20),(4,20),(4,60),(0,60)]"""
    if len(profile) < 3:
        raise ValueError("profile 至少要 3 个点")
    bm = bmesh.new()
    rings = []
    for (r, z) in profile:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / seg),
                                        r * math.sin(2 * math.pi * k / seg), z)) for k in range(seg)])
    n = len(rings)
    for i in range(n):
        a, c = rings[i], rings[(i + 1) % n]
        if len(a) == 1 and len(c) == 1:
            continue
        if len(a) == 1:
            for k in range(seg):
                bm.faces.new((a[0], c[k], c[(k + 1) % seg]))
        elif len(c) == 1:
            for k in range(seg):
                bm.faces.new((a[k], a[(k + 1) % seg], c[0]))
        else:
            for k in range(seg):
                bm.faces.new((a[k], a[(k + 1) % seg], c[(k + 1) % seg], c[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _place(bm, at, axis)
    return _new_object(name, bm, mat, coll)


def extrude(name, outline, h, holes=(), at=(0, 0, 0), axis='Z', mat=None, coll='Model'):
    """把二维轮廓沿 axis 拉伸 h（以 at 为中心，两边各 h/2）。
    outline=[(u, v), ...] 外轮廓（逆时针），holes=[[(u, v), ...], ...] 内孔。
    axis='Z' 时 (u,v)=(x,y)；'X' 时 (u,v)=(y,z)；'Y' 时 (u,v)=(x,z)。"""
    from mathutils.geometry import tessellate_polygon
    _check_num(h=h)
    loops = [list(outline)] + [list(x) for x in holes]
    bm = bmesh.new()
    L0 = [[bm.verts.new((u, v, -h / 2)) for (u, v) in L] for L in loops]
    L1 = [[bm.verts.new((u, v, h / 2)) for (u, v) in L] for L in loops]
    tris = tessellate_polygon([[Vector((u, v, 0)) for (u, v) in L] for L in loops])
    f0 = [v for L in L0 for v in L]
    f1 = [v for L in L1 for v in L]
    for t in tris:
        bm.faces.new((f0[t[0]], f0[t[2]], f0[t[1]]))
        bm.faces.new((f1[t[0]], f1[t[1]], f1[t[2]]))
    for A, C in zip(L0, L1):
        k = len(A)
        for i in range(k):
            bm.faces.new((A[i], A[(i + 1) % k], C[(i + 1) % k], C[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    axis = axis.upper()
    if axis == 'X':
        m = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    elif axis == 'Y':
        m = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    else:
        m = Matrix.Identity(4)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(at)) @ m, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_object(name, bm, mat, coll)


def circle_pts(r, n=48, cx=0.0, cy=0.0):
    """二维圆的点列，给 extrude 的 outline / holes 用"""
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rrect_pts(w, d, r, n=8, cx=0.0, cy=0.0):
    """二维圆角矩形点列（宽 w、深 d、圆角半径 r），给 extrude 用"""
    r = min(r, w / 2 - 1e-3, d / 2 - 1e-3)
    pts = []
    for (ux, uy, a0) in ((w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90),
                         (-w / 2 + r, -d / 2 + r, 180), (w / 2 - r, -d / 2 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + ux + r * math.cos(a), cy + uy + r * math.sin(a)))
    return pts


def pipe(name, points, r, mat=None, sides=16, smooth=True, coll='Model'):
    """圆截面沿路径扫掠。points=[(x,y,z), ...]，r=截面半径。smooth=True 时把折线变成平滑曲线。"""
    _check_num(r=r)
    pts = [Vector(p) for p in points]
    if smooth and len(pts) >= 3:
        P = [pts[0]] + pts + [pts[-1]]
        out = []
        for i in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            for k in range(8):
                t = k / 8
                out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
        out.append(pts[-1])
        pts = out
    n = len(pts)
    T = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    ref = Vector((0, 0, 1)) if abs(T[0].z) < .9 else Vector((0, 1, 0))
    nr = T[0].cross(ref).normalized()
    N = [nr.copy()]
    for i in range(1, n):
        ax = T[i - 1].cross(T[i])
        if ax.length > 1e-9:
            nr = Matrix.Rotation(T[i - 1].angle(T[i]), 3, ax.normalized()) @ nr
        N.append(nr.copy())
    B = [T[i].cross(N[i]) for i in range(n)]
    bm = bmesh.new()
    rings = [[bm.verts.new(pts[i] + r * (math.cos(2 * math.pi * k / sides) * N[i] + math.sin(2 * math.pi * k / sides) * B[i]))
              for k in range(sides)] for i in range(n)]
    for i in range(n - 1):
        a, c = rings[i], rings[i + 1]
        for k in range(sides):
            bm.faces.new((a[k], a[(k + 1) % sides], c[(k + 1) % sides], c[k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _new_object(name, bm, mat, coll)
    _smooth_by_angle(ob.data, 60)
    return ob


def helix_pts(r, pitch, turns, at=(0, 0, 0), n_per_turn=24):
    """螺旋线点列（沿 +Z，从 at 开始往上），给 pipe 做弹簧用"""
    pts = []
    total = int(turns * n_per_turn)
    for k in range(total + 1):
        a = 2 * math.pi * k / n_per_turn
        pts.append((at[0] + r * math.cos(a), at[1] + r * math.sin(a), at[2] + pitch * k / n_per_turn))
    return pts


# ------------------------------------------------------------------ 布尔与编辑
def _bool(target, tool, op):
    md = target.modifiers.new('bool', 'BOOLEAN')
    md.object = tool
    md.operation = op
    md.solver = 'EXACT'
    _apply_modifiers(target)
    _smooth_by_angle(target.data, 35)
    d = tool.data
    bpy.data.objects.remove(tool, do_unlink=True)
    if d.users == 0:
        bpy.data.meshes.remove(d)
    return target


def cut(target, tool):
    """布尔差集：在 target 上挖掉 tool 的形状，tool 用完自动删除。返回 target。"""
    return _bool(target, tool, 'DIFFERENCE')


def join(target, other):
    """布尔并集：把 other 合并进 target，other 自动删除。返回 target。"""
    return _bool(target, other, 'UNION')


def hole(target, r, at, axis='Z', depth=None):
    """在 target 上打圆孔。at=孔的中心点；depth=None 表示打穿（自动取足够长）。"""
    if depth is None:
        dims = target.dimensions
        depth = (max(dims) + 2 * max(abs(c) for c in at) + 10) * 2
    tool = cyl('_hole_tool', r, depth, at=at, axis=axis, seg=48)
    return cut(target, tool)


def copy(obj, name, at=None, rot=None):
    """复制零件。at=新的中心点（None 表示原位）；rot=(rx,ry,rz) 角度（度），绕新零件中心旋转。"""
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = name
    for c in obj.users_collection:
        c.objects.link(new)
    if at is not None:
        c0 = center(obj)
        delta = Vector(at) - c0
        new.data.transform(Matrix.Translation(delta))
    if rot is not None:
        for ang, ax in zip(rot, 'XYZ'):
            if ang:
                rotate(new, ang, ax)
    return new


def polar(obj, n, axis='Z', center_pt=(0, 0, 0), prefix=None):
    """把 obj 绕 axis（穿过 center_pt）等分复制成 n 个（含原件），返回全部列表。"""
    prefix = prefix or obj.name
    out = [obj]
    for k in range(1, n):
        new = obj.copy()
        new.data = obj.data.copy()
        new.name = f"{prefix}_{k + 1}"
        for c in obj.users_collection:
            c.objects.link(new)
        m = (Matrix.Translation(Vector(center_pt)) @ Matrix.Rotation(2 * math.pi * k / n, 4, axis.upper())
             @ Matrix.Translation(-Vector(center_pt)))
        new.data.transform(m)
        out.append(new)
    return out


def rotate(obj, deg, axis='Z', pivot=None):
    """绕 pivot（默认物体自身中心）旋转 deg 度。"""
    p = Vector(pivot) if pivot is not None else center(obj)
    m = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis.upper()) @ Matrix.Translation(-p)
    obj.data.transform(m)
    return obj


def move(obj, dx=0, dy=0, dz=0):
    obj.data.transform(Matrix.Translation(Vector((dx, dy, dz))))
    return obj


# ------------------------------------------------------------------ 查询
def bounds(obj):
    """返回 (最小角, 最大角) 两个 Vector，世界坐标 mm"""
    ws = [obj.matrix_world @ v.co for v in obj.data.vertices]
    mn = Vector((min(v.x for v in ws), min(v.y for v in ws), min(v.z for v in ws)))
    mx = Vector((max(v.x for v in ws), max(v.y for v in ws), max(v.z for v in ws)))
    return mn, mx


def center(obj):
    mn, mx = bounds(obj)
    return (mn + mx) / 2


def info(obj):
    """打印零件的包围盒，建模时可以随时调用来核对尺寸"""
    mn, mx = bounds(obj)
    s = mx - mn
    print(f"[info] {obj.name}: 尺寸 {s.x:.1f} x {s.y:.1f} x {s.z:.1f} mm, "
          f"x {mn.x:.1f}~{mx.x:.1f}, y {mn.y:.1f}~{mx.y:.1f}, z {mn.z:.1f}~{mx.z:.1f}")
