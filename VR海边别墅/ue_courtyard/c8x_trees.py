# -*- coding: utf-8 -*-
"""云端运行 (不需要 UE): 程序化生成植物网格 -> court_plants.glb
  每种植物一个网格, 两个材质槽: 树皮 (锥形管, 沿枝条展 UV) + 叶片卡 (带透明贴图的面片)。
  叶片卡技巧:
    - 双面几何 (正反两层三角形, 法线相同), 材质用单面 -> 不会出现"背面法线翻转变黑"
    - 法线不用面片自己的, 而是"树冠球面法线" (从树冠中心指向外) 和面片法线混合:
      一堆面片在光照下就像一个有体积的、柔和的树冠, 而不是一片片硬纸板 (商业植被的标准做法)
  坐标: UE 米制 (X 东, Y 南, Z 上; 植物局部坐标, 原点在根部) -> glTF (gx=X, gy=Z, gz=Y), 换手性三角形反向。
用法: python c8x_trees.py  (只需要 numpy)"""
import json
import math
import os
import struct

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ 网格累加器
class Part:
    def __init__(self):
        self.V, self.N, self.UV, self.F = [], [], [], []

    def add(self, V, N, UV, F):
        b = len(self.V)
        self.V.extend(V)
        self.N.extend(N)
        self.UV.extend(UV)
        self.F.extend([(a + b, c + b, d + b) for a, c, d in F])


def norm(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def any_perp(d):
    a = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
    return norm(np.cross(d, a))


# ------------------------------------------------------------------ 树枝 (锥形管)
def tube(part, pts, radii, sides, u_rep, v_tile, v0=0.0):
    """沿折线 pts 生成锥形管; 平行移动标架避免扭曲。返回累计长度 (给子枝接 v 坐标)。"""
    pts = [np.asarray(p, float) for p in pts]
    n = len(pts)
    tang = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tang.append(norm(t))
    side = any_perp(tang[0])
    V, N, UV, F = [], [], [], []
    vacc = v0
    for i in range(n):
        if i > 0:
            vacc += np.linalg.norm(pts[i] - pts[i - 1]) / v_tile
            # 平行移动
            side = norm(side - np.dot(side, tang[i]) * tang[i])
        up = np.cross(tang[i], side)
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            d = math.cos(a) * side + math.sin(a) * up
            V.append(pts[i] + d * radii[i])
            N.append(d)
            UV.append((u_rep * k / sides, vacc))
    for i in range(n - 1):
        for k in range(sides):
            a = i * (sides + 1) + k
            b = a + sides + 1
            F.append((a, a + 1, b + 1))
            F.append((a, b + 1, b))
    part.add(V, N, UV, F)
    return vacc


# ------------------------------------------------------------------ 叶片卡
def card(part, rng, pos, up, face, w, h, crown_c, crown_bias=0.75, pivot=0.15, uv_rect=(0, 0, 1, 1)):
    """以 pos 为叶柄位置、沿 up 方向长出去的一张卡; face 是卡片朝向; 双面。uv_rect=(u0,v0,u1,v1) 只用贴图的一部分。"""
    up = norm(up)
    face = norm(face - np.dot(face, up) * up)
    if np.linalg.norm(face) < 1e-6:
        face = any_perp(up)
    right = norm(np.cross(up, face))
    base = np.asarray(pos, float) - up * h * pivot
    c = [base - right * w / 2, base + right * w / 2, base + right * w / 2 + up * h, base - right * w / 2 + up * h]
    u0, v0, u1, v1 = uv_rect
    uv = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
    nrm = []
    for p in c:
        sph = norm(p - crown_c)
        f = face if np.dot(face, sph) >= 0 else -face
        nrm.append(norm(sph * crown_bias + f * (1 - crown_bias)))
    # 正面 (逆时针 = 朝 face) 和背面
    tri_front = [(0, 1, 2), (0, 2, 3)]
    if np.dot(np.cross(c[1] - c[0], c[2] - c[0]), face) < 0:
        tri_front = [(0, 2, 1), (0, 3, 2)]
    tri_back = [(a, cc, b) for a, b, cc in tri_front]
    part.add(c, nrm, uv, tri_front)
    part.add(c, nrm, uv, tri_back)


# ------------------------------------------------------------------ 递归分枝
def grow(rng, bark, tips, start, d, length, radius, depth, sp, v0=0.0):
    """sp: 物种参数。tips 收集末梢 (位置, 方向, 长度)。"""
    segs = max(3, int(length / sp["seg"]))
    pts, radii = [np.asarray(start, float)], [radius]
    p, dd = np.asarray(start, float), norm(d)
    r_end = radius * sp["taper"]
    for i in range(1, segs + 1):
        # 扭曲 (橄榄要很"拧") + 向光 (往上) + 向外
        jitter = rng.normal(0, sp["gnarl"], 3)
        out = np.array([dd[0], dd[1], 0.0])
        dd = norm(dd + jitter + np.array([0, 0, sp["photo"]]) + out * sp["spread"])
        p = p + dd * length / segs
        pts.append(p.copy())
        radii.append(radius + (r_end - radius) * i / segs)
    if radius > sp["min_r"]:
        sides = 10 if radius > 0.12 else (7 if radius > 0.05 else 5)
        vend = tube(bark, pts, radii, sides, sp["u_rep"] if radius > 0.08 else 1, sp["v_tile"], v0)
    else:
        vend = v0
    if depth >= sp["depth"] or radius < sp["twig_r"]:
        tips.append((pts[-1], dd, length, pts))
        return
    k = rng.integers(sp["kids"][0], sp["kids"][1] + 1)
    az0 = rng.uniform(0, 2 * math.pi)
    for j in range(k):
        az = az0 + 2 * math.pi * j / k + rng.normal(0, 0.3)
        ang = math.radians(rng.uniform(*sp["angle"]))
        side = any_perp(dd)
        up2 = np.cross(dd, side)
        nd = norm(dd * math.cos(ang) + (math.cos(az) * side + math.sin(az) * up2) * math.sin(ang))
        grow(rng, bark, tips, pts[-1], nd, length * rng.uniform(*sp["len_k"]), r_end * sp["r_k"], depth + 1, sp, vend)
    # 沿枝条的侧枝 (小枝, 让树冠里面也有叶子)
    if depth >= 1:
        for i in range(1, len(pts) - 1):
            if rng.random() < sp["side_p"]:
                side = norm(np.cross(dd, rng.normal(0, 1, 3)))
                nd = norm(dd * 0.4 + side + np.array([0, 0, 0.2]))
                grow(rng, bark, tips, pts[i], nd, length * 0.45, radii[i] * 0.45, sp["depth"], sp, vend)


def leaves_on_tips(rng, leaf, tips, crown_c, n_per, w, h, spread, droop=0.0, bias=0.75):
    for pos, d, L, pts in tips:
        for i in range(n_per):
            t = rng.uniform(0.35, 1.0)
            idx = min(len(pts) - 1, int(t * (len(pts) - 1)))
            p = pts[idx] + rng.normal(0, spread, 3)
            up = norm(d + rng.normal(0, 0.6, 3) + np.array([0, 0, -droop]))
            face = rng.normal(0, 1, 3)
            s = rng.uniform(0.8, 1.2)
            card(leaf, rng, p, up, face, w * s, h * s, crown_c, bias)


# ------------------------------------------------------------------ 物种
OLIVE = dict(seg=0.22, taper=0.62, gnarl=0.22, photo=0.10, spread=0.15, min_r=0.012, twig_r=0.018,
             depth=4, kids=(2, 3), angle=(28, 48), len_k=(0.62, 0.8), r_k=0.78, side_p=0.35,
             u_rep=2, v_tile=0.9)
FIG = dict(seg=0.25, taper=0.65, gnarl=0.08, photo=0.18, spread=0.25, min_r=0.012, twig_r=0.02,
           depth=3, kids=(2, 3), angle=(25, 45), len_k=(0.65, 0.8), r_k=0.8, side_p=0.25,
           u_rep=2, v_tile=1.2)
LEMON = dict(seg=0.12, taper=0.6, gnarl=0.12, photo=0.25, spread=0.1, min_r=0.006, twig_r=0.008,
             depth=3, kids=(2, 3), angle=(30, 50), len_k=(0.6, 0.75), r_k=0.8, side_p=0.2,
             u_rep=1, v_tile=0.4)


def make_olive(seed=7):
    rng = np.random.default_rng(seed)
    bark, leaf = Part(), Part()
    tips = []
    # 粗短、拧着的主干, 1.1 m 处分成 3 根主枝 (老橄榄的典型样子)
    trunk_pts, rr = [np.zeros(3)], [0.30]
    p, d = np.zeros(3), norm([0.15, 0.05, 1])
    for i in range(6):
        d = norm(d + rng.normal(0, 0.12, 3) + np.array([0, 0, 0.05]))
        p = p + d * 0.2
        trunk_pts.append(p.copy())
        rr.append(0.30 - 0.1 * (i + 1) / 6)
    rr[0] = 0.38                                       # 根部放大一点 (根张)
    vend = tube(bark, trunk_pts, rr, 12, 3, 0.9)
    top = trunk_pts[-1]
    for j in range(3):
        az = 2 * math.pi * j / 3 + rng.normal(0, 0.25)
        nd = norm([math.cos(az) * 0.75, math.sin(az) * 0.75, 1.0])
        grow(rng, bark, tips, top, nd, 1.35, 0.15, 1, OLIVE, vend)
    pts = np.array([t[0] for t in tips])
    crown_c = np.array([pts[:, 0].mean(), pts[:, 1].mean(), pts[:, 2].mean() - 0.4])
    leaves_on_tips(rng, leaf, tips, crown_c, 13, 0.42, 0.42, 0.14, droop=0.3)
    return bark, leaf, crown_c


def make_fig(seed=11):
    rng = np.random.default_rng(seed)
    bark, leaf = Part(), Part()
    tips = []
    # 无花果: 根部分成 3 根光滑的斜干, 冠幅宽、略扁
    for j in range(3):
        az = 2 * math.pi * j / 3 + 0.4
        nd = norm([math.cos(az) * 0.35, math.sin(az) * 0.35, 1.0])
        grow(rng, bark, tips, np.array([math.cos(az) * 0.06, math.sin(az) * 0.06, 0]), nd, 1.3, 0.1, 0, FIG)
    pts = np.array([t[0] for t in tips])
    crown_c = np.array([0, 0, pts[:, 2].mean() - 0.3])
    leaves_on_tips(rng, leaf, tips, crown_c, 7, 0.6, 0.6, 0.15, droop=0.1)
    return bark, leaf, crown_c


def make_lemon(seed=5):
    """柠檬 (盆栽): 原点 = 盆土表面。细干 0.6 m, 球形冠半径 ~0.5 m。"""
    rng = np.random.default_rng(seed)
    bark, leaf = Part(), Part()
    tips = []
    trunk = [np.zeros(3), np.array([0.02, 0, 0.3]), np.array([0, 0.02, 0.6])]
    vend = tube(bark, trunk, [0.035, 0.03, 0.025], 6, 1, 0.4)
    for j in range(3):
        az = 2 * math.pi * j / 3
        grow(rng, bark, tips, trunk[-1], norm([math.cos(az), math.sin(az), 1.3]), 0.35, 0.02, 1, LEMON, vend)
    crown_c = np.array([0, 0, 0.95])
    # 叶子铺在球壳上 (修剪成球形的盆栽柑橘)
    # 贴图上半 (v 0.12~0.50) 只有叶子, 下半是两个柠檬: 大部分卡只用上半, 少数整张 (带果)
    for i in range(130):
        fruit = i < 12
        dirn = norm(rng.normal(0, 1, 3) + np.array([0, 0, 0.2 if not fruit else -0.3]))
        r = 0.45 * rng.uniform(0.6, 1.0)
        p = crown_c + dirn * r * np.array([1, 1, 0.9])
        up = norm(dirn + rng.normal(0, 0.5, 3))
        if fruit:
            card(leaf, rng, p, up, rng.normal(0, 1, 3), 0.3, 0.3, crown_c, 0.8, pivot=0.3)
        else:
            card(leaf, rng, p, up, rng.normal(0, 1, 3), 0.3, 0.3 * 0.38, crown_c, 0.8, pivot=0.2,
                 uv_rect=(0, 0.12, 1, 0.5))
    return bark, leaf, crown_c


def make_shrub(seed=3, d=0.6, n=34, size=0.28):
    """修剪成球的橄榄灌木 / 盆里的小灌木: 原点 = 底部中心, 直径 d。"""
    rng = np.random.default_rng(seed)
    leaf = Part()
    c = np.array([0, 0, d * 0.45])
    for i in range(n):
        dirn = norm(rng.normal(0, 1, 3) + np.array([0, 0, 0.3]))
        p = c + dirn * np.array([d / 2, d / 2, d * 0.45]) * rng.uniform(0.55, 0.9)
        up = norm(dirn * 0.6 + np.array([0, 0, 0.6]) + rng.normal(0, 0.3, 3))
        card(leaf, rng, p, up, dirn, size, size, c, 0.85, pivot=0.35)
    return Part(), leaf, c


def make_clump(seed=9, h=0.5, w=0.42, n=7):
    """薰衣草 / 迷迭香一丛: 竖着的卡片绕中心转一圈, 略向外倾。原点 = 底部中心。"""
    rng = np.random.default_rng(seed)
    leaf = Part()
    c = np.array([0, 0, h * 0.35])
    for i in range(n):
        az = math.pi * i / n + rng.normal(0, 0.15)
        off = np.array([rng.normal(0, 0.03), rng.normal(0, 0.03), 0])
        tilt = rng.normal(0, 0.18)
        face = np.array([math.cos(az), math.sin(az), 0.0])
        up = norm(np.array([0, 0, 1.0]) + np.cross(face, [0, 0, 1]) * tilt)
        card(leaf, rng, off, up, face, w * rng.uniform(0.85, 1.1), h * rng.uniform(0.85, 1.15), c, 0.55, pivot=0.0)
    return Part(), leaf, c


def make_bouga_wall(seed=21, L=4.55, z0=0.4, z1=3.5):
    """九重葛贴墙: 原点 = 墙面左下 (平面图 x=4.4, y=10.17), 沿 +X 4.55 m, 卡片朝 +Y (UE) = 平面图的南。
    几根贴墙的藤 + 一层叶片卡, 上沿起伏、下沿稀疏。"""
    rng = np.random.default_rng(seed)
    bark, leaf = Part(), Part()
    for k in range(5):                                  # 藤: 从下往上斜着爬
        x = 0.3 + k * 1.0 + rng.normal(0, 0.1)
        pts, rr = [], []
        for i in range(10):
            t = i / 9
            pts.append(np.array([x + math.sin(t * 5 + k) * 0.35 + t * 0.4, 0.06, 0.05 + t * (z1 - 0.3)]))
            rr.append(0.035 - 0.025 * t)
        tube(bark, pts, rr, 5, 1, 0.5)
    c_line = lambda x, z: np.array([x, -0.9, z])        # 法线往墙外偏 (假装是一个贴墙的厚冠)
    for i in range(140):
        x = rng.uniform(0.05, L - 0.05)
        top = z1 - 0.35 + 0.35 * math.sin(x * 1.9) + rng.normal(0, 0.1)
        z = z0 + 0.6 + (top - z0 - 0.6) * (rng.random() ** 0.5)     # 花多在上半部
        p = np.array([x, 0.08 + rng.uniform(0, 0.18), z])
        face = norm(np.array([rng.normal(0, 0.35), 1.0, rng.normal(0, 0.35)]))
        up = norm(np.array([rng.normal(0, 0.6), rng.normal(0, 0.2), 1.0]))
        s = rng.uniform(0.32, 0.5)
        card(leaf, rng, p, up, face, s, s, c_line(x, z), 0.6, pivot=0.5)
    green = Part()                                       # 九重葛的绿叶 (用无花果叶贴图缩小, 读起来就是一般的绿叶)
    for i in range(300):
        x = rng.uniform(0.05, L - 0.05)
        top = z1 - 0.2 + 0.35 * math.sin(x * 1.9 + 0.5) + rng.normal(0, 0.1)
        z = z0 - 0.2 + (top - z0) * rng.random()
        p = np.array([x, 0.05 + rng.uniform(0, 0.12), z])
        face = norm(np.array([rng.normal(0, 0.4), 1.0, rng.normal(0, 0.4)]))
        up = norm(np.array([rng.normal(0, 0.8), 0, 1.0]))
        s = rng.uniform(0.28, 0.4)
        card(green, rng, p, up, face, s, s, c_line(x, z), 0.6, pivot=0.5)
    BOUGA_GREEN[0] = green
    return bark, leaf, np.array([L / 2, -0.9, 1.8])


BOUGA_GREEN = [None]


# ------------------------------------------------------------------ glb 写出 (一个网格多个 primitive = UE 里一个静态网格两个材质槽)
def write_glb(path, meshes):
    """meshes: [(name, [(material_name, Part), ...]), ...]; Part 是 UE 米制坐标 (X, Y, Z)。"""
    bin_chunks, views, accs = [], [], []
    mats, mat_idx = [], {}

    def push(arr, target, comp, typ, minmax=False):
        data = arr.tobytes()
        off = sum(len(b) for b in bin_chunks)
        pad = (-len(data)) % 4
        bin_chunks.append(data + b"\0" * pad)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data), "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": typ}
        if minmax:
            acc["min"] = arr.min(0).tolist()
            acc["max"] = arr.max(0).tolist()
        accs.append(acc)
        return len(accs) - 1

    gl_meshes, nodes = [], []
    for name, prims in meshes:
        gp = []
        for mname, part in prims:
            if not part.F:
                continue
            V = np.asarray(part.V, np.float32)
            N = np.asarray(part.N, np.float32)
            gV = np.stack([V[:, 0], V[:, 2], V[:, 1]], 1).astype(np.float32)
            gN = np.stack([N[:, 0], N[:, 2], N[:, 1]], 1)
            gN = (gN / np.maximum(np.linalg.norm(gN, axis=1, keepdims=True), 1e-9)).astype(np.float32)
            UV = np.asarray(part.UV, np.float32)
            F = np.asarray(part.F, np.uint32)[:, ::-1].reshape(-1)       # 换手性
            if mname not in mat_idx:
                mat_idx[mname] = len(mats)
                mats.append({"name": mname, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                                     "metallicFactor": 0.0, "roughnessFactor": 0.8},
                             "doubleSided": False})
            a_p = push(gV, 34962, 5126, "VEC3", True)
            a_n = push(gN, 34962, 5126, "VEC3")
            a_t = push(UV, 34962, 5126, "VEC2")
            a_i = push(F, 34963, 5125, "SCALAR")
            gp.append({"attributes": {"POSITION": a_p, "NORMAL": a_n, "TEXCOORD_0": a_t},
                       "indices": a_i, "material": mat_idx[mname]})
        gl_meshes.append({"name": name, "primitives": gp})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1})
    blob = b"".join(bin_chunks)
    js = {"asset": {"version": "2.0", "generator": "c8x_trees.py"}, "scene": 0,
          "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gl_meshes,
          "materials": mats, "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * ((-len(jb)) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(jb) + 8 + len(blob)))
        f.write(struct.pack("<II", len(jb), 0x4E4F534A) + jb)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)


def main():
    plants = {
        "Olive": make_olive(),
        "Fig": make_fig(),
        "Lemon": make_lemon(),
        "OliveShrub": make_shrub(3, 0.6, 64, 0.24),
        "PotShrub": make_shrub(4, 0.5, 48, 0.22),
        "Lavender": make_clump(9, 0.5, 0.42, 7),
        "Rosemary": make_clump(13, 0.42, 0.4, 6),
        "BougaWall": make_bouga_wall(),
    }
    leaf_mat = {"Olive": "leaf_olive", "Fig": "leaf_fig", "Lemon": "leaf_lemon", "OliveShrub": "leaf_olive",
                "PotShrub": "leaf_rosemary", "Lavender": "leaf_lavender", "Rosemary": "leaf_rosemary",
                "BougaWall": "leaf_bouga"}
    bark_mat = {"Fig": "bark_fig"}
    # 尺寸归一: s=1 时和 c2_build 里旧的球形树差不多大 (橄榄 ~3.6 m 高, 无花果 ~2.8 m, 盆栽柠檬冠宽 ~1.1 m)
    for name, k in (("Olive", 0.78), ("Fig", 0.75), ("Lemon", 0.82)):
        for part in plants[name][:2]:
            part.V = [np.asarray(v) * k for v in part.V]
    meshes, stats = [], {}
    for name, (bark, leaf, _) in plants.items():
        prims = [(bark_mat.get(name, "bark"), bark), (leaf_mat[name], leaf)]
        if name == "BougaWall":
            prims.append(("leaf_fig", BOUGA_GREEN[0]))
            leaf.F = leaf.F + []                       # (统计里只算花)
        meshes.append(("PL_" + name, prims))
        V = np.asarray(bark.V + leaf.V) if (bark.V or leaf.V) else np.zeros((1, 3))
        stats[name] = dict(tris=len(bark.F) + len(leaf.F), cards=len(leaf.F) // 4,
                           size=[round(float(x), 2) for x in (V.max(0) - V.min(0))],
                           zmax=round(float(V[:, 2].max()), 2))
    out = os.path.join(HERE, "court_plants.glb")
    write_glb(out, meshes)
    for k, v in stats.items():
        print(k, v)
    print("->", out, os.path.getsize(out) // 1024, "KB")
    export_placements()
    return plants


def export_placements():
    """用假的 unreal 模块跑一遍 c2_build 的各 build_*, 收集 olive()/fig()/lemon_pot()/bush()/九重葛 的位置 -> court_plants.json"""
    import importlib.util
    import sys
    from unittest import mock
    sys.modules.setdefault("unreal", mock.MagicMock())
    spec = importlib.util.spec_from_file_location("c2b_pl", os.path.join(HERE, "c2_build.py"))
    c2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c2)
    c2.RECORD = []
    for fn in ("build_site", "build_terrace", "build_courts", "build_living", "build_basement",
               "build_wing", "build_entry", "build_garage", "build_studio"):
        getattr(c2, fn)()
    out = os.path.join(HERE, "court_plants.json")
    json.dump({"plants": c2.PLANTS}, open(out, "w"), indent=0)
    from collections import Counter
    print("placements:", len(c2.PLANTS), dict(Counter(p[0] for p in c2.PLANTS)))


if __name__ == "__main__":
    main()
