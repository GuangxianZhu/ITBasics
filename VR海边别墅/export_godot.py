# -*- coding: utf-8 -*-
"""
把 build_villa.py 生成的别墅导出给 Godot 用（godot/model/villa.glb + godot/model/villa_meta.json）。

用法（启动_Godot.bat 会自动跑）:
    blender --background --factory-startup --python export_godot.py

在 Blender 版场景的基础上，额外做了 Godot 交互需要的东西:
    - 一楼、二楼的海景落地窗里，拆出可以推拉的玻璃门扇（物体名 "滑门_*_L/R"，L 往 -X 推，R 往 +X 推）
    - 灯开关（物体名 "开关_一楼/二楼"）
    - 楼梯和平台台阶的隐形碰撞坡道（物体名 "碰撞_*"，Godot 里只做碰撞、不显示）
    - 室内灯位置（空物体 "灯位_一楼_*"），Godot 在这些位置放点光源
坐标换算: glTF 导出会把 Blender 的 (x, y, z) 变成 Godot 的 (x, z, -y)，所以大海在 Godot 里是 -Z 方向（正好是 Godot 的"前方"）。
"""
import json
import math
import os
import sys

import bpy
import bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_villa as bv  # noqa: E402

OUT_DIR = os.path.join(HERE, "godot", "model")


def remove(name):
    ob = bpy.data.objects.get(name)
    if ob:
        bpy.data.objects.remove(ob, do_unlink=True)
    else:
        print("[export] WARN not found:", name)


def panel(name, a0, a1, y0, y1, z0, z1, along_x, M, c):
    """一扇推拉门: 黑色框 (5cm) + 玻璃，合成一个物体（两个材质槽），方便整体移动。"""
    fw = 0.05
    bm = bmesh.new()

    def add_box(xa, ya, za, xb, yb, zb, mat_index):
        if not along_x:   # 沿 Y 的墙: 交换坐标
            xa, ya, xb, yb = ya, xa, yb, xb
        r = bmesh.ops.create_cube(bm, size=1.0)
        vs = r["verts"]
        bmesh.ops.scale(bm, vec=(abs(xb - xa), abs(yb - ya), abs(zb - za)), verts=vs)
        bmesh.ops.translate(bm, vec=((xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2), verts=vs)
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = mat_index

    add_box(a0, y0, z0, a1, y1, z0 + fw, 0)
    add_box(a0, y0, z1 - fw, a1, y1, z1, 0)
    add_box(a0, y0, z0, a0 + fw, y1, z1, 0)
    add_box(a1 - fw, y0, z0, a1, y1, z1, 0)
    mid0, mid1 = (y0 + y1) / 2 - 0.006, (y0 + y1) / 2 + 0.006
    add_box(a0 + fw, mid0, z0 + fw, a1 - fw, mid1, z1 - fw, 1)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(M["frame"])
    me.materials.append(M["glass"])
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    return ob


def ramp(name, p0, p1, width_axis, w0, w1, c, mat):
    """隐形坡道: 从 p0=(a, z) 到 p1=(a, z) 的斜板（a 是沿坡方向的坐标），宽度方向 [w0, w1]。"""
    (a0, z0), (a1, z1) = p0, p1
    t = 0.05
    if width_axis == "y":      # 坡沿 X 方向
        v = [(a0, w0, z0), (a1, w0, z1), (a1, w1, z1), (a0, w1, z0)]
    else:                      # 坡沿 Y 方向
        v = [(w0, a0, z0), (w0, a1, z1), (w1, a1, z1), (w1, a0, z0)]
    vb = [(x, y, z - t) for x, y, z in v]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return bv.mesh_obj(name, v + vb, faces, mat, c)


def main():
    # 1) 先生成和 Blender VR 版一模一样的场景（不保存 .blend）
    sys.argv = [sys.argv[0]]
    bv.main()
    M = {m.name: m for m in bpy.data.materials}
    Mk = {"frame": M["黑色窗框"], "glass": M["玻璃"]}
    C = bv.coll("Godot交互")
    F1, F2 = bv.F1, bv.F2

    # 2) 一楼海景窗: 去掉整片玻璃和正中竖梃，改成 2 片固定玻璃 + 中间 2 扇推拉门
    remove("一楼南墙_海景_玻璃0")
    remove("一楼南墙_海景_竖梃0_3")
    zs, zh = F1 + 0.05, F1 + 2.9 - 0.05
    bv.box("一楼海景_固定玻璃L", -6.55, 4.89, zs, -2.225, 4.91, zh, M["玻璃"], C)
    bv.box("一楼海景_固定玻璃R", 2.225, 4.89, zs, 6.55, 4.91, zh, M["玻璃"], C)
    panel("滑门_一楼_L", -2.2, 0.0, 4.93, 4.98, F1 + 0.05, F1 + 2.85, True, Mk, C)
    panel("滑门_一楼_R", 0.0, 2.2, 4.93, 4.98, F1 + 0.05, F1 + 2.85, True, Mk, C)

    # 3) 二楼海景窗（娱乐室 → 弧形阳台）: 最右一段 (-0.9~1.25) 改成往左推的门
    remove("二楼南墙_海景_玻璃0")
    remove("二楼南墙_海景_竖梃0_3")
    zs, zh = F2 + 0.05, F2 + 2.6 - 0.05
    bv.box("二楼海景_固定玻璃", -6.55, 4.89, zs, -0.925, 4.91, zh, M["玻璃"], C)
    panel("滑门_二楼_L", -0.9, 1.25, 4.93, 4.98, F2 + 0.05, F2 + 2.55, True, Mk, C)

    # 4) 灯开关（白色小面板，激光指着按扳机就能开关）
    sw = M["台面"]
    bv.box("开关_一楼", -6.80, -3.62, F1 + 1.15, -6.75, -3.48, F1 + 1.32, sw, C)
    bv.box("开关_二楼", 0.62, -4.80, F2 + 1.15, 0.76, -4.75, F2 + 1.32, sw, C)

    # 5) 隐形碰撞坡道: 楼梯（沿踏步前缘连线）、平台下沙滩的台阶
    inv = M["白墙"]
    # 踏步前缘连线: 过 (X0 + i*0.28, F1 + (i+1)*踢面高)，往前延一级正好落在一楼地面
    ramp("碰撞_楼梯坡", (bv.STAIR_X0 - bv.STAIR_RUN, F1), (bv.STAIR_X1, F2), "y",
         bv.STAIR_Y[0], bv.STAIR_Y[1], C, inv)

    # 6) 灯位（空物体），Godot 里换成点光源
    for k, (x, y, z) in enumerate([(1.5, 1.5, F2 - 0.4), (-4.0, -0.5, F2 - 0.4), (5.6, -3.6, F2 - 0.4),
                                   (-4.5, 3.0, F2 - 0.4), (4.5, 3.0, F2 - 0.4)]):
        e = bpy.data.objects.new(f"灯位_一楼_{k}", None)
        e.location = (x, y, z)
        C.objects.link(e)
    for k, (x, y, z) in enumerate([(-3.0, -1.0, bv.ROOF - 0.4), (-2.3, 2.6, bv.ROOF - 0.4),
                                   (4.25, -1.5, bv.ROOF - 0.4), (4.25, 3.0, bv.ROOF - 0.4)]):
        e = bpy.data.objects.new(f"灯位_二楼_{k}", None)
        e.location = (x, y, z)
        C.objects.link(e)

    # 7) 导出前去掉 Blender 专用的灯和相机（Godot 自己布光）
    points = []
    for name, x, y, floor, yaw in bv.VR_POINTS:
        points.append({"name": name, "pos": [x, floor, -y], "yaw_deg": yaw})   # 换成 Godot 坐标
    for ob in list(bpy.data.objects):
        if ob.type in ("LIGHT", "CAMERA"):
            bpy.data.objects.remove(ob, do_unlink=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    glb = os.path.join(OUT_DIR, "villa.glb")
    kw = dict(filepath=glb, export_format="GLB", export_yup=True, export_apply=True,
              export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:            # 极老版本没有部分参数
        bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB")
    # AI 家具的材质（颜色/质感）给 Godot
    with open(os.path.join(HERE, "ai_furniture", "furniture.json"), encoding="utf-8") as f:
        furn = json.load(f)
    ai_mats = {f"AI_{it['name']}": it.get("material", {}) for it in furn["items"]}
    ai_mats.update({f"AI_{it['name']}_2": it["split"].get("material", {}) for it in furn["items"] if it.get("split")})
    meta = {"vr_points": points, "floor1": F1, "floor2": F2, "ai_materials": ai_mats}
    with open(os.path.join(OUT_DIR, "villa_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("[export] wrote", glb)


if __name__ == "__main__":
    main()
