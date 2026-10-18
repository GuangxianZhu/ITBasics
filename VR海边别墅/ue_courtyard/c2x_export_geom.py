# -*- coding: utf-8 -*-
"""云端运行 (不需要 UE): 用假的 unreal 模块导入 c2_build.py, 把所有 box/cyl/sph 记录下来,
生成 "带倒角、按 (区域, 材质) 合并" 的网格, 导出 court_geom.glb。
  - 倒角: 每个盒子 12 条边都切 1.2 cm 斜面 (VR 里近看, 直角边像刀切; 倒角会接住一条高光, 物体才显得结实)
  - 合并: 1200 多个立方体 -> 一百个左右网格, 绘制调用大幅减少
  - 坐标: 平面图 (x 东, y 北, z 上) -> UE (X=x, Y=-y, Z=z) -> glTF (gx=X, gy=Z, gz=Y)
用法: python c2x_export_geom.py  (需要 pip install trimesh numpy)"""
import importlib.util
import math
import os
import sys
from collections import defaultdict
from unittest import mock

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.modules["unreal"] = mock.MagicMock()
spec = importlib.util.spec_from_file_location("c2b", os.path.join(HERE, "c2_build.py"))
c2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2)
c2.RECORD = []
for fn in ("build_site", "build_terrace", "build_courts", "build_living", "build_basement",
           "build_wing", "build_entry", "build_garage", "build_studio"):
    getattr(c2, fn)()
rec = [r for r in c2.RECORD if r[3] not in c2.SPAWN_ALWAYS]
print("records:", len(c2.RECORD), "merged:", len(rec))


def poly_mesh(polys):
    """polys: list of vertex lists (UE 米制). 每个面独立顶点 (平直着色), 按法线主轴做世界尺度 UV。"""
    V, F, UV = [], [], []
    for p in polys:
        p = np.asarray(p, float)
        c = p.mean(0)
        n = np.zeros(3)
        for i in range(len(p)):                      # Newell 法线
            a, b = p[i], p[(i + 1) % len(p)]
            n += np.cross(a, b)
        if np.dot(n, c - CEN[0]) < 0:
            p = p[::-1]
            n = -n
        ax = int(np.argmax(np.abs(n)))
        uv_axes = [(1, 2), (0, 2), (0, 1)][ax]
        base = len(V)
        for v in p:
            V.append(v)
            UV.append((v[uv_axes[0]], v[uv_axes[1]]))
        for i in range(1, len(p) - 1):
            F.append((base, base + i, base + i + 1))
    return V, F, UV


CEN = [np.zeros(3)]


def chamfer_box(cx, cy, cz, dx, dy, dz, b):
    hx, hy, hz = dx / 2, dy / 2, dz / 2
    CEN[0] = np.array([cx, cy, cz])
    o = np.array([cx, cy, cz])
    if b <= 0:
        polys = []
        for ax in range(3):
            for sgn in (-1, 1):
                q = []
                for u, w in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    v = [0, 0, 0]
                    v[ax] = sgn
                    oth = [k for k in range(3) if k != ax]
                    v[oth[0]], v[oth[1]] = u, w
                    q.append(o + np.array(v) * [hx, hy, hz])
                polys.append(q)
        return poly_mesh(polys)
    S = [-1, 1]
    VX = lambda sx, sy, sz: o + [sx * hx, sy * (hy - b), sz * (hz - b)]
    VY = lambda sx, sy, sz: o + [sx * (hx - b), sy * hy, sz * (hz - b)]
    VZ = lambda sx, sy, sz: o + [sx * (hx - b), sy * (hy - b), sz * hz]
    loop = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    polys = []
    for s in S:
        polys.append([VX(s, a, c) for a, c in loop])
        polys.append([VY(a, s, c) for a, c in loop])
        polys.append([VZ(a, c, s) for a, c in loop])
    for sx in S:
        for sy in S:
            polys.append([VX(sx, sy, -1), VX(sx, sy, 1), VY(sx, sy, 1), VY(sx, sy, -1)])
    for sx in S:
        for sz in S:
            polys.append([VX(sx, -1, sz), VX(sx, 1, sz), VZ(sx, 1, sz), VZ(sx, -1, sz)])
    for sy in S:
        for sz in S:
            polys.append([VY(-1, sy, sz), VY(1, sy, sz), VZ(1, sy, sz), VZ(-1, sy, sz)])
    for sx in S:
        for sy in S:
            for sz in S:
                polys.append([VX(sx, sy, sz), VY(sx, sy, sz), VZ(sx, sy, sz)])
    return poly_mesh(polys)


def prim_mesh(tm, center):
    """trimesh 原语 -> 平直着色 + UV"""
    CEN[0] = np.asarray(center, float)
    polys = [tm.vertices[f] for f in tm.faces]
    return poly_mesh(polys)


def rot(pitch, roll):
    p, r = math.radians(-pitch), math.radians(roll)
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Ry @ Rx


groups = defaultdict(lambda: ([], [], []))
CYL = trimesh.creation.cylinder(radius=0.5, height=1.0, sections=20)
SPH = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
for kind, prm, mat, group, collide in rec:
    if kind == "box":
        x0, x1, y0, y1, z0, z1, yaw = prm
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        mind = min(dx, dy, dz)
        b = 0.0 if (max(dx, dy) > 40 or mind < 0.03) else min(0.012, mind / 4)
        V, F, UV = chamfer_box((x0 + x1) / 2, -(y0 + y1) / 2, (z0 + z1) / 2, dx, dy, dz, b)
    elif kind == "cyl":
        x, y, z0, z1, d, dy_, pitch, roll = prm
        m = CYL.copy()
        m.apply_scale([d, dy_, z1 - z0])
        T = np.eye(4)
        T[:3, :3] = rot(pitch, roll)
        T[:3, 3] = [x, -y, (z0 + z1) / 2]
        m.apply_transform(T)
        V, F, UV = prim_mesh(m, T[:3, 3])
    else:
        x, y, z, sx, sy, sz = prm
        m = SPH.copy()
        m.apply_scale([sx, sy, sz])
        m.apply_translation([x, -y, z])
        V, F, UV = prim_mesh(m, [x, -y, z])
    key = (group.replace("/", "_"), mat, collide)
    gv, gf, guv = groups[key]
    base = len(gv)
    gv.extend(V)
    guv.extend(UV)
    gf.extend([(a + base, b + base, c + base) for a, b, c in F])

scene = trimesh.Scene()
tris = 0
for (group, mat, collide), (V, F, UV) in sorted(groups.items()):
    V = np.asarray(V)
    gl = np.stack([V[:, 0], V[:, 2], V[:, 1]], 1)          # UE -> glTF
    F = np.asarray(F)[:, ::-1]                               # 换手性后保持外法线朝外
    name = "%s__%s%s" % (group, mat, "" if collide else "__nc")
    mesh = trimesh.Trimesh(vertices=gl, faces=F, process=False,
                           visual=trimesh.visual.TextureVisuals(uv=np.asarray(UV), material=trimesh.visual.material.PBRMaterial(name=mat)))
    scene.add_geometry(mesh, node_name=name, geom_name=name)
    tris += len(F)
out = os.path.join(HERE, "court_geom.glb")
scene.export(out, file_type="glb", include_normals=True)
print("meshes:", len(groups), "triangles:", tris, "->", out, os.path.getsize(out) // 1024, "KB")
