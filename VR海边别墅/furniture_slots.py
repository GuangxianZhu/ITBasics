# -*- coding: utf-8 -*-
"""
家具"槽位": 每件家具有固定的位置/朝向/尺寸。
    有 AI 模型（ai_furniture/models/<名字>.glb）→ 导入、减面、平滑、按槽位尺寸等比缩放、上材质
    没有 → 用脚本拼的占位家具（形状接近，方便先看布局）

物体名约定（Godot 靠它识别）:
    AI_<名字>_<序号>            例 AI_sofa_0
    ... + _座<厘米>             能坐，座面离地多少厘米，例 AI_sofa_0_座45
材质名 AI_<名字>，颜色/质感来自 furniture.json 的 material（export_godot.py 把它写进 villa_meta.json 给 Godot）。

朝向约定: yaw = 0 表示家具正面朝 +Y（大海）。
AI 模型的"正面"朝哪不确定（取决于生成时的图），所以有两道保险:
    1) 宽/深明显不同的家具（沙发、台球桌…）自动转 90° 让长边对上槽位的长边
    2) furniture.json 里每件可以写 "yaw_fix": 180 之类手动修正
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

V = None
HERE = os.path.dirname(os.path.abspath(__file__))
FURN_JSON = os.path.join(HERE, "ai_furniture", "furniture.json")
MODELS = os.path.join(HERE, "ai_furniture", "models")
AI_FRONT_DEG = 180.0        # Hunyuan3D 出的模型正面朝 -Y（实测 14 件都是），转 180° 对上"正面朝 +Y"的约定
TARGET_FACES = 24000        # 每件 AI 家具减面到多少个面（VR 里几十件同时显示也不卡）


def places():
    F1, F2 = V.F1, V.F2
    return {
        "sofa": [(1.7, 0.95, F1, 0)],
        "armchair": [(5.7, 0.6, F1, 180), (2.6, 3.7, F2, 210)],
        "coffee_table": [(1.6, 2.4, F1, 0)],
        "dining_table": [(-3.9, 1.5, F1, 0)],
        "dining_chair": [(-4.8, 0.75, F1, 0), (-3.9, 0.75, F1, 0), (-3.0, 0.75, F1, 0),
                         (-4.8, 2.25, F1, 180), (-3.9, 2.25, F1, 180), (-3.0, 2.25, F1, 180)],
        "billiard_table": [(-2.3, 2.6, F2, 0)],
        "round_bed": [(4.25, 4.3, F2, 0)],
        "bar_stool": [(-5.0, -1.3, F1, 180), (-3.9, -1.3, F1, 180), (-2.8, -1.3, F1, 180)],
        "plant": [(6.2, 4.2, F1, 0), (-3.0, 4.25, F1, 40), (0.9, 4.2, F2, 0), (-6.2, 4.2, F2, 70)],
        "sun_lounger": [(-5.0, 7.5, F1, 0), (-3.6, 7.5, F1, 0), (3.3, 7.5, F1, 0), (4.6, 7.5, F1, 0),
                        (-4.6, 5.95, F2, 0), (-3.2, 5.95, F2, 0)],
        "egg_chair": [(-8.0, 6.0, F1, 30)],
        "bbq_grill": [(13.4, 9.9, F1, 180)],
        "flamingo_float": [(-2.0, 9.7, V.POOL_WATER - 0.25, 30)],
        "umbrella": [(-5.0, 11.85, F1, 0), (0.0, 11.85, F1, 0), (5.0, 11.85, F1, 0)],
    }


# ===================================================================== 占位家具（局部坐标: 中心在原点，正面 +Y，地面 z=0）
def _tag(vs, mi):
    for f in {f for v in vs for f in v.link_faces}:
        f.material_index = mi


def pbox(bm, mi, x0, y0, z0, x1, y1, z1):
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), verts=vs)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=vs)
    _tag(vs, mi)


def pcyl(bm, mi, x, y, z0, z1, r0, r1=None, seg=24):
    vs = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1,
                               depth=z1 - z0, matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))["verts"]
    _tag(vs, mi)


def ptube(bm, mi, p0, p1, r, seg=8):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    vs = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=d.length)["verts"]
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=vs)
    _tag(vs, mi)


def psphere(bm, mi, x, y, z, sx, sy, sz, sub=2):
    vs = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=vs)
    bmesh.ops.translate(bm, vec=(x, y, z), verts=vs)
    _tag(vs, mi)


def placeholder(name, size, bm):
    """返回额外材质键列表（索引 1 起）；索引 0 = 主材质 AI_<名字>。"""
    w, d, h = size
    hw, hd = w / 2, d / 2
    if name == "sofa":
        pbox(bm, 0, -hw + 0.15, -hd, 0.0, hw - 0.15, hd, 0.42)
        pbox(bm, 0, -hw + 0.15, -hd, 0.42, hw - 0.15, -hd + 0.25, h)
        for s in (-1, 1):
            pbox(bm, 0, s * hw - 0.15 if s > 0 else -hw, -hd, 0.0, s * hw if s > 0 else -hw + 0.15, hd, 0.62)
        for k in range(3):
            x = -hw + 0.35 + k * (w - 0.7) / 2.5
            pbox(bm, 0, x, -hd + 0.25, 0.42, x + 0.75, hd - 0.05, 0.55)
        return []
    if name == "armchair":
        pcyl(bm, 0, 0, 0.05, 0.0, 0.42, hw * 0.85, hw * 0.9)
        for k in range(5):                                       # 扇贝形靠背
            a = math.radians(200 + k * 35)
            pcyl(bm, 0, 0.32 * math.cos(a), 0.32 * math.sin(a) - 0.05, 0.3, h, 0.17, 0.2)
        return []
    if name == "coffee_table":
        pcyl(bm, 0, 0, 0, h - 0.03, h, hw, hw, 40)
        pcyl(bm, 1, 0, 0, 0, h - 0.03, 0.06, 0.06, 12)
        pcyl(bm, 1, 0, 0, 0, 0.02, hw * 0.6, hw * 0.6, 24)
        return ["frame"]
    if name == "dining_table":
        pbox(bm, 0, -hw, -hd, h - 0.05, hw, hd, h)
        for sx in (-1, 1):
            for sy in (-1, 1):
                pbox(bm, 0, sx * (hw - 0.1) - 0.04, sy * (hd - 0.1) - 0.04, 0, sx * (hw - 0.1) + 0.04, sy * (hd - 0.1) + 0.04, h - 0.05)
        return []
    if name == "dining_chair":
        pbox(bm, 0, -hw, -hd, 0.42, hw, hd, 0.5)
        pbox(bm, 0, -hw, -hd, 0.5, hw, -hd + 0.06, h)
        for sx in (-1, 1):
            for sy in (-1, 1):
                pbox(bm, 1, sx * (hw - 0.04) - 0.015, sy * (hd - 0.04) - 0.015, 0, sx * (hw - 0.04) + 0.015, sy * (hd - 0.04) + 0.015, 0.42)
        return ["frame"]
    if name == "billiard_table":
        pbox(bm, 1, -hw, -hd, h - 0.18, hw, hd, h - 0.02)                       # 白色台框
        pbox(bm, 0, -hw + 0.12, -hd + 0.12, h - 0.02, hw - 0.12, hd - 0.12, h)  # 蓝色台呢
        for sx in (-1, 1):
            for sy in (-1, 1):
                pbox(bm, 1, sx * (hw - 0.25) - 0.1, sy * (hd - 0.22) - 0.1, 0, sx * (hw - 0.25) + 0.1, sy * (hd - 0.22) + 0.1, h - 0.18)
        for x in (-hw + 0.1, 0, hw - 0.1):
            for y in (-hd + 0.1, hd - 0.1):
                pcyl(bm, 2, x, y, h - 0.01, h + 0.005, 0.06, 0.06, 12)
        return ["counter", "frame"]
    if name == "round_bed":
        r = hw
        pcyl(bm, 0, 0, 0, 0.0, 0.42, r, r, 48)
        pcyl(bm, 1, 0, 0, 0.42, 0.6, r - 0.08, r - 0.1, 48)
        for k, x in enumerate((-0.5, 0.0, 0.5)):
            pbox(bm, 1, x - 0.28, -r * 0.6, 0.6, x + 0.28, -r * 0.6 + 0.35, 0.78)
        return ["bed"]
    if name == "bar_stool":
        pcyl(bm, 0, 0, 0, h - 0.06, h, hw * 0.9, hw * 0.9)
        pcyl(bm, 1, 0, 0, 0, h - 0.06, 0.025, 0.025, 10)
        pcyl(bm, 1, 0, 0, 0, 0.02, hw * 0.85, hw * 0.85)
        return ["frame"]
    if name == "plant":
        pcyl(bm, 1, 0, 0, 0, 0.45, 0.22, 0.27)
        for k in range(12):
            a = k * 2.399
            L = h * (0.55 + 0.4 * ((k * 37) % 10) / 10)
            ptube(bm, 0, (0, 0, 0.4), (0.35 * math.cos(a), 0.35 * math.sin(a), 0.4 + L), 0.02, 5)
            psphere(bm, 0, 0.38 * math.cos(a), 0.38 * math.sin(a), 0.4 + L, 0.22, 0.09, 0.3, 1)
        return ["ceramic"]
    if name == "sun_lounger":
        pbox(bm, 1, -hw, -hd, 0.0, hw, hd, 0.3)
        pbox(bm, 0, -hw + 0.03, -hd + 0.6, 0.3, hw - 0.03, hd - 0.02, 0.38)
        bm2 = []
        vs = [bm.verts.new(p) for p in [(-hw, -hd, 0.3), (hw, -hd, 0.3), (hw, -hd + 0.62, 0.3), (-hw, -hd + 0.62, 0.3),
                                        (-hw, -hd, 0.85), (hw, -hd, 0.85)]]
        for f in ((0, 1, 2, 3), (0, 4, 5, 1), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2)):
            bm.faces.new([vs[i] for i in f]).material_index = 0
        return ["counter"]
    if name == "egg_chair":
        for s in (-1, 1):
            ptube(bm, 1, (s * 0.45, -0.3, 0.02), (s * 0.15, -0.35, h), 0.03)
        pcyl(bm, 1, 0, -0.3, 0, 0.04, 0.45, 0.45)
        ptube(bm, 1, (0, -0.35, h), (0, 0.0, h - 0.1), 0.025)
        psphere(bm, 0, 0, 0.05, 0.95, 0.45, 0.42, 0.62, 2)
        pcyl(bm, 2, 0, 0.12, 0.42, 0.55, 0.33, 0.33)
        return ["frame", "bed"]
    if name == "bbq_grill":
        psphere(bm, 0, 0, 0, 0.72, hw, hw, 0.3, 2)
        for k in range(3):
            a = math.radians(90 + k * 120)
            ptube(bm, 0, (0.25 * math.cos(a), 0.25 * math.sin(a), 0.6), (0.3 * math.cos(a), 0.3 * math.sin(a), 0.0), 0.02)
        return []
    if name == "flamingo_float":
        r = hw * 0.7
        for k in range(16):                                   # 甜甜圈形的圈
            a0, a1 = k * math.tau / 16, (k + 1) * math.tau / 16
            ptube(bm, 0, (r * math.cos(a0), r * math.sin(a0), 0.15), (r * math.cos(a1), r * math.sin(a1), 0.15), 0.17, 12)
        ptube(bm, 0, (0, r, 0.2), (0, r + 0.05, 0.75), 0.07, 10)
        ptube(bm, 0, (0, r + 0.05, 0.75), (0, r - 0.15, 1.0), 0.07, 10)
        psphere(bm, 0, 0, r - 0.2, 1.02, 0.1, 0.12, 0.09, 1)
        return []
    if name == "umbrella":
        pbox(bm, 1, -0.25, -0.25, 0, 0.25, 0.25, 0.12)
        pcyl(bm, 2, 0, 0, 0.12, h, 0.03, 0.03, 10)
        vs = bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=hw, radius2=0.03, depth=0.55,
                                   matrix=Matrix.Translation((0, 0, h - 0.28)))["verts"]
        _tag(vs, 0)
        return ["paving", "wood_furn"]
    pbox(bm, 0, -hw, -hd, 0, hw, hd, h)
    return []


# ===================================================================== AI 模型导入 + 清理
CACHE_VERSION = 6


def _components(faces, nv):
    """按共享顶点给面分组（连通块）。纯 numpy 的标签传播，2~3 万面只要零点几秒。"""
    import numpy as np
    lab = np.arange(nv)
    while True:
        fmin = lab[faces].min(axis=1)
        new = lab.copy()
        np.minimum.at(new, faces.ravel(), np.repeat(fmin, faces.shape[1]))
        new = new[new]                                   # 指针跳跃，加速收敛
        if np.array_equal(new, lab):
            break
        lab = new
    return lab[faces[:, 0]]


def clean_ai_mesh(V_, F_):
    """
    Hunyuan3D 从"白底产品图"生成时，常把照片里的地面阴影也重建成一块薄"底板"，还会有零星漂浮的碎块。
    1) 底板: 最底下一层里挤着大量顶点（>12%）→ 找到这层的上沿，把这层的面全部删掉
    2) 碎块: 只保留最大的连通块 + 和它包围盒挨着的块（桌腿、椅腿和主体是挨着的），其余丢掉
    """
    import numpy as np
    z = V_[:, 2]
    zmin, zmax = z.min(), z.max()
    H = zmax - zmin
    removed_plate = False
    if (z < zmin + 0.06 * H).mean() > 0.12:
        # 底板有上下两层皮（体素重建后），所以找"底部 15% 高度内、顶点特别密的最高一层"，从它上面切
        nb = 150
        binw = 0.15 * H / nb
        bins = np.histogram(z, bins=nb, range=(zmin, zmin + 0.15 * H))[0]
        big = np.where(bins >= 0.2 * bins.max())[0]
        cut = zmin + (big.max() + 2) * binw
        keep = V_[F_][:, :, 2].mean(axis=1) > cut
        F_ = F_[keep]
        removed_plate = True
    lab = _components(F_, len(V_))
    ids, counts = np.unique(lab, return_counts=True)
    def box(c):
        pts = V_[np.unique(F_[lab == c])]
        return pts.min(0), pts.max(0)
    # 残留的大薄片（又扁又大的连通块）也是底板的一部分，去掉
    ext_all = V_.max(0) - V_.min(0)
    flat = []
    for c in ids:
        bmin, bmax = box(c)
        e = bmax - bmin
        if e[2] < 0.04 * H and e[0] > 0.5 * ext_all[0] and e[1] > 0.5 * ext_all[1]:
            flat.append(c)
    if flat:
        F_ = F_[~np.isin(lab, flat)]
        lab = lab[~np.isin(lab, flat)]
        ids, counts = np.unique(lab, return_counts=True)
    order = ids[np.argsort(-counts)]
    kmin, kmax = box(order[0])
    keep_ids = [order[0]]
    eps = 0.02 * H
    changed = True
    rest = list(order[1:])
    while changed:
        changed = False
        for c in list(rest):
            bmin, bmax = box(c)
            if np.all(bmin <= kmax + eps) and np.all(bmax >= kmin - eps):
                keep_ids.append(c)
                rest.remove(c)
                kmin, kmax = np.minimum(kmin, bmin), np.maximum(kmax, bmax)
                changed = True
    F_ = F_[np.isin(lab, keep_ids)]
    used = np.unique(F_)
    remap = -np.ones(len(V_), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return V_[used], remap[F_], removed_plate, len(ids) - len(keep_ids)


def _load_or_process(name, path, voxel_div=220):
    """导入 glb → 合并 → 减面 → 清理，结果缓存成 .npz（下次启动直接读，几乎不花时间）。"""
    import numpy as np
    cache_dir = os.path.join(MODELS, "_cache")
    cache = os.path.join(cache_dir, name + ".npz")
    stamp = f"{os.path.getsize(path)}_{int(os.path.getmtime(path))}_{TARGET_FACES}_{CACHE_VERSION}_{voxel_div}"
    if os.path.exists(cache):
        d = np.load(cache)
        if str(d["stamp"]) == stamp:
            return d["v"], d["f"], "cache"
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    bm = bmesh.new()
    for o in new:
        if o.type == "MESH":
            me = o.data.copy()
            me.transform(o.matrix_world)
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    # ComfyUI 存的 glb 是"三角形汤"（相邻三角形不共用顶点）→ 先焊接重合顶点，否则减面和连通块分析都不灵
    size = max((max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts)) for i in range(3))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=size * 1e-5)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    me = bpy.data.meshes.new("_ai_tmp")
    bm.to_mesh(me)
    bm.free()
    n = len(me.polygons)

    def apply_mod(me, kind, **kw):
        tmp = bpy.data.objects.new("_mod_tmp", me)
        bpy.context.scene.collection.objects.link(tmp)
        mod = tmp.modifiers.new("m", kind)
        for k, v in kw.items():
            setattr(mod, k, v)
        dg = bpy.context.evaluated_depsgraph_get()
        out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.meshes.remove(me)
        return out
    # Hunyuan 的 surface-net 网格有大量"非流形边"（一条边被 3 个以上三角形共用），直接减面减不动 →
    # 先体素重建（约 1/220 尺寸的体素，≈1cm）得到干净的封闭表面，再按目标面数减面
    me = apply_mod(me, "REMESH", mode="VOXEL", voxel_size=size / voxel_div, adaptivity=0.0)   # 薄的东西（伞面）用更细的体素
    m = len(me.polygons)
    if m > TARGET_FACES:
        me = apply_mod(me, "DECIMATE", ratio=TARGET_FACES / m, use_collapse_triangulate=True)
    tri = bmesh.new()
    tri.from_mesh(me)
    bmesh.ops.triangulate(tri, faces=tri.faces)
    tri.to_mesh(me)
    tri.free()
    v = np.zeros(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    f = np.zeros(len(me.polygons) * 3, dtype=np.int64)
    me.polygons.foreach_get("vertices", f)
    f = f.reshape(-1, 3)
    bpy.data.meshes.remove(me)
    v, f, plate, junk = clean_ai_mesh(v, f)
    print(f"[furniture] {name}: {n} → {len(f)} 面" + ("，去掉了底板" if plate else "") + (f"，丢掉 {junk} 块碎片" if junk else ""))
    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(cache, v=v, f=f, stamp=stamp)
    return v, f, "new"


def import_ai(name, path, it):
    import numpy as np
    try:
        v, f, src = _load_or_process(name, path, it.get("voxel_div", 220))
    except Exception as e:
        print(f"[furniture] {name}: 导入失败 {e}")
        return None
    w, d, h = it["size"]
    a = math.radians(AI_FRONT_DEG + it.get("yaw_fix", 0))
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    v = v @ rz.T
    ext = v.max(0) - v.min(0)
    if (w > d * 1.25 and ext[0] < ext[1] * 0.85) or (d > w * 1.25 and ext[1] < ext[0] * 0.85):
        r90 = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        v = v @ r90.T
        ext = v.max(0) - v.min(0)
    s = min(w / max(ext[0], 1e-6), d / max(ext[1], 1e-6), h / max(ext[2], 1e-6))
    lo, hi = v.min(0), v.max(0)
    v = (v - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])) * s
    ok = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])     # 去掉退化三角形
    f = f[ok]
    me = bpy.data.meshes.new(f"AI_{name}")
    me.from_pydata(v.tolist(), [], f.tolist())
    me.validate(clean_customdata=False)
    me.update()
    # 按高度分两种材质（比如沙发腿、花盆、台球桌台呢），见 furniture.json 的 split
    sp = it.get("split")
    if sp:
        zc = v[f][:, :, 2].mean(axis=1) / max(v[:, 2].max(), 1e-6)
        sel = zc < sp["below"] if "below" in sp else zc > sp["above"]
        if sp.get("facing") == "up":                     # 只要朝上的面（台球桌的台呢）
            tri = v[f]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
            sel &= nz > 0.7
        me["_split_idx"] = np.where(sel, 1, 0).astype(np.int32).tolist()   # 材质加上之后再写（见 build）
    for p in me.polygons:
        p.use_smooth = True
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(40))
    print(f"[furniture] {name}: {'缓存' if src == 'cache' else '新处理'}，{len(f)} 面，缩放 {s:.3f}")
    return me


def material_for(it, M):
    m = it.get("material", {})
    mat, b = V.principled(f"AI_{it['name']}", tuple(m.get("color", (0.7, 0.7, 0.7))), m.get("rough", 0.6), m.get("metal", 0.0))
    return mat


def build(M, villa_module):
    global V
    V = villa_module
    C = V.coll("家具槽位")
    with open(FURN_JSON, encoding="utf-8") as f:
        cfg = json.load(f)
    P = places()
    n_ai = 0
    for it in cfg["items"]:
        name = it["name"]
        spots = P.get(name, [])
        if not spots:
            continue
        mat = material_for(it, M)
        glb = os.path.join(MODELS, name + ".glb")
        me = import_ai(name, glb, it) if os.path.exists(glb) else None
        if me is not None:
            me.materials.clear()
            me.materials.append(mat)
            if it.get("split"):
                m2 = it["split"].get("material", {})
                mat2, _ = V.principled(f"AI_{name}_2", tuple(m2.get("color", (0.5, 0.5, 0.5))), m2.get("rough", 0.6), m2.get("metal", 0.0))
                me.materials.append(mat2)
                # 注意: 必须在材质槽加好之后再写 material_index（materials.clear() 会把索引清零）
                me.polygons.foreach_set("material_index", list(me["_split_idx"]))
                del me["_split_idx"]
            n_ai += 1
        else:
            bm = bmesh.new()
            extra = placeholder(name, it["size"], bm)
            me = bpy.data.meshes.new(f"占位_{name}")
            bm.to_mesh(me)
            bm.free()
            me.materials.append(mat)
            for k in extra:
                me.materials.append(M[k])
        seat = it.get("seat_h")
        for k, (x, y, z, yaw) in enumerate(spots):
            nm = f"AI_{name}_{k}" + (f"_座{int(round(seat * 100))}" if seat else "")
            ob = bpy.data.objects.new(nm, me)
            ob.location = (x, y, z)
            ob.rotation_euler = (0, 0, math.radians(yaw))
            C.objects.link(ob)
        if name == "bbq_grill":
            x, y, z, _ = spots[0]
            e = bpy.data.objects.new("烧烤火位", None)
            e.location = (x, y, z + 0.85)
            C.objects.link(e)
    print(f"[furniture] {n_ai} 种家具用了 AI 模型，其余是占位")
    return cfg
