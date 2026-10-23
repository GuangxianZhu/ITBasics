# -*- coding: utf-8 -*-
"""
五指灵巧手 → 虚幻工程 MyVRToyBox 用的 hand_ue.glb（按零件树合并成 50 个部件 + 爆炸路线）

用法
  blender -b --factory-startup --python export_ue.py -- <输出目录>      （MyVRToyBox 的 scripts/import_hand.bat 会调）
  pip 版 bpy：python export_ue.py <输出目录>
  只出关节表：python export_ue.py <输出目录> --rig-only               （不重新导出 glb）

另外写一份 hand_ue_rig.json（关节表）：MyVRToyBox 把这只手当玩家的手用时，靠它让手指动起来（见 export_rig）。

和网页用的 hand.glb 有三点不同：
  1. 手指摆成"放松"手势（params.json 的 poses.rest），不是 0 位。拇指在 0 位是横着伸出去的，放松姿势更像一只手。
  2. 按零件树的叶子合并：每个电机模组（定子壳 + 输出环 + 端盖）、每节指骨（骨架 + 硅胶垫 + 盖板 + 螺钉）、指尖（传感器 + 指尖套）
     各是一个部件，一共 50 个（掌骨架是不动的底座，49 个能抓）。VR 里一次捏一个部件，太碎的小件（螺钉、端盖）单独抓没意义。
  3. 爆炸改成虚幻工程的约定：每个部件一个节点、顶点在装配位置；extras.ex = 若干步 [gx, gy, gz, 出场时刻]（glTF 坐标，毫米）。
     爆炸量比网页版大（VR 里要伸手进去捏），法兰和腕部改成往手背方向退出去，不往下走（往下会钻进桌面）。
     时间顺序：法兰 → 腕部 → 背盖 → 掌心硅胶 → 五根手指从掌上拔出 → 每根手指按关节拉开 → 电机往手心方向弹出 → 指尖。

坐标：沿用 build_hand.py（法兰中心为原点，+Z 指尖，手心朝 -Y，右手拇指在 +X）。导进虚幻后 +Z 朝上、手心朝模型 +Y。
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_hand as H  # noqa: E402

FINGER_EN = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "little": "Little"}

# 零件树叶子 → (英文名, 材料)。顺序就是编号顺序
LEAF = {
    "J1 根部屈伸电机": ("M1", "直驱无刷电机 Ø18 · 铝合金定子壳 + 橙色输出环 + 黑色端盖"),
    "指根轭架": ("Yoke", "铝合金 CNC"),
    "J2 侧摆电机": ("M2", "直驱无刷电机 Ø12 · 铝合金定子壳 + 橙色输出环"),
    "近节指骨": ("Proximal", "铝合金指骨 + 硅胶指节垫 + 指背盖板 + M1.6 螺钉 ×4"),
    "J3 中节屈伸电机": ("M3", "直驱无刷电机 Ø13 · 铝合金定子壳 + 橙色输出环"),
    "中节指骨": ("Middle", "铝合金指骨 + 硅胶指节垫 + 指背盖板 + M1.6 螺钉 ×4"),
    "J4 远节屈伸电机": ("M4", "直驱无刷电机 Ø11 · 铝合金定子壳 + 橙色输出环"),
    "远节指骨": ("Distal", "铝合金指骨，末端圆头"),
    "指尖力传感器": ("Tip", "多轴力传感器 + 硅胶指尖套"),
}
BODY = [  # (零件树路径, 英文名, 材料)
    ("手/掌骨架", "PalmFrame", "铝合金骨架"),
    ("手/掌骨架/背盖", "BackCover", "铝合金背盖 · 3 条散热槽 + 状态灯条"),
    ("手/掌骨架/掌心硅胶", "PalmSkin", "硅胶软皮 + 大鱼际垫 + 小鱼际垫"),
    ("手/腕部模块", "Wrist", "铝合金壳体 · 驱动板 / 主控 / IMU · 以太网 + 电源接口"),
    ("手/法兰", "Flange", "铝合金法兰 Ø52 + 定位止口 + M4 螺钉 ×4"),
]

# 爆炸：build_hand.py 里登记过偏移的对象 → (虚幻用的偏移 mm（同一个局部坐标系）, 出场时刻 0~1)。
# 名字按后缀匹配，手指的偏移方向沿用原来的（手指根部朝外 / 关节方向 / 电机往手心），只是加大
EX = H.P["explode"]


def ue_step(name, vec):
    v = Vector(vec)
    if name == "flange_grp":
        return Vector((0, 110, 0)), 0.0          # 往手背方向退出去（原来是往下 46mm）
    if name == "wrist_grp":
        return Vector((0, 55, 0)), 0.08
    if name == "backcover_grp":
        return v.normalized() * 45, 0.16
    if name == "palmskin_grp":
        return v.normalized() * 40, 0.24
    for i, f in enumerate(H.FINGERS):
        if name == f + "_base":                  # 整根手指从掌上拔出来
            return v.normalized() * 50, 0.32 + 0.03 * i
    tail = name.split("_", 1)[1]
    if tail == "F2":
        return v.normalized() * 20, 0.5
    if tail == "F3":
        return v.normalized() * 24, 0.58
    if tail == "F4":
        return v.normalized() * 24, 0.66
    if tail in ("M1", "M2", "M3", "M4"):
        return v.normalized() * 24, 0.76         # 电机往手心方向弹出
    if tail == "tipsensor":
        return v.normalized() * 22, 0.86
    return None                                  # 指节垫、盖板、指尖套的单独偏移不要：它们跟着所在部件一起走


def gltf_mm(v_m):
    """Blender 世界坐标（米）→ glTF 坐标（毫米）：(x, z, -y)"""
    return [round(v_m.x * 1000, 2), round(v_m.z * 1000, 2), round(-v_m.y * 1000, 2)]


def route(ob, explode_of):
    """部件的爆炸路线：沿父链收集所有登记过偏移的对象，按出场时刻排好。偏移换到世界坐标。"""
    steps = []
    o = ob
    while o is not None:
        if o.name in explode_of:
            s = ue_step(o.name, explode_of[o.name])
            if s is not None:
                vec, start = s
                w = o.parent.matrix_world.to_3x3() @ vec if o.parent else vec * 0.001
                steps.append(gltf_mm(w) + [start])
        o = o.parent
    return sorted(steps, key=lambda s: s[3])


def info_text(path):
    leaf = path.split("/")[-1]
    fing = next((f for f in H.FINGERS if "/" + H.CN[f] + "/" in path + "/"), None)
    return (H.THUMB_INFO.get(leaf) if fing == "thumb" else None) or H.PART_INFO.get(leaf, "")


def bake_unit(name, sources, coll):
    """把几个零件（带倒角修改器、在各自父坐标系里）烘成一个网格对象，顶点在世界坐标、单位米，对象本身不带变换。"""
    dg = bpy.context.evaluated_depsgraph_get()
    objs = []
    for src in sources:
        me = bpy.data.meshes.new_from_object(src.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(src.matrix_world)
        ob = bpy.data.objects.new(src.name + "_baked", me)
        coll.objects.link(ob)
        objs.append(ob)
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs,
                                       selected_objects=objs):
            bpy.ops.object.join()
    ob = objs[0]
    ob.name = name
    ob.data.name = name
    return ob


def ue_cm(v_m):
    """Blender 世界坐标（米）→ 虚幻导入后的模型坐标（厘米）：glTF (x, z, -y) 再被虚幻换成 (x, z, y)，合起来是 (x, -y, z)"""
    return Vector((v_m.x * 100, -v_m.y * 100, v_m.z * 100))


def ue_axis(k_world):
    """Blender 里绕 k 转 +a ⇔ 虚幻模型坐标里绕 (-kx, ky, -kz) 转 +a。
    (x, -y, z) 是镜像（行列式 -1），镜像把转动方向反过来：M·R(k, a)·M⁻¹ = R(M·k, -a) = R(-M·k, a)。
    FQuat(Axis, Angle) 的数值公式和这里一样，所以虚幻那边直接 FQuat(Axis, 弧度) 就行"""
    k = k_world.normalized()
    return Vector((-k.x, k.y, -k.z))


def rot_about(p, axis, deg, v):
    """绕过 p 点、方向 axis 的轴把 v 转 deg 度（右手公式，和 FQuat 数值一致）"""
    return p + Matrix.Rotation(math.radians(deg), 3, axis) @ (v - p)


def export_rig(hand, out, units):
    """关节表 hand_ue_rig.json：放松姿势（rest，就是 glb 里网格的样子）下每个关节的转轴，加上几个命名手势的关节角。

    虚幻里每根手指 J1→J4 串成一条链：关节 k 相对放松姿势多转 Δ = 目标角 - 放松角，
    部件跟着它所在的最深一级关节走（M1 电机固定在掌上；轭架、M2 跟 J1；近节、M3 跟 J2；中节、M4 跟 J3；远节、指尖跟 J4）。
    坐标都是虚幻模型坐标、厘米、没缩放（和 parts.json 一样）。"""
    H.apply_pose(hand, H.POSES["rest"])
    bpy.context.view_layer.update()

    def clamped(pose):
        return {f: [round(H.clamp(f, k, a), 3) for k, a in enumerate(pose[f])] for f in H.FINGERS}

    poses = {n: clamped(H.POSES[n]) for n in ("rest", "open", "fist", "pinch")}
    joints = {}
    tips = {}
    for f in H.FINGERS:
        row = []
        for k, j in enumerate(hand[f]["J"]):
            m = j.matrix_world
            k_world = m.col[1].to_3d() if k == 1 else m.col[0].to_3d()   # apply_pose：J2 绕本地 Y，其余绕本地 X
            p = ue_cm(m.translation)
            row.append(dict(pivot=[round(c, 4) for c in p], axis=[round(c, 6) for c in ue_axis(k_world)]))
        joints[f] = row
        # 指尖两个点（都跟 J4 走）：pad = 指腹表面中心（捏的接触点），end = 指尖最前端（戳触屏）
        fp = H.P["fingers"][f]
        tp = H.P["finger_common"]["tip_pad"]
        td = fp["t"] * 0.9
        L3 = fp["L"][2]
        j4 = hand[f]["J"][3].matrix_world
        end = ue_cm(j4 @ Vector((0, -td * tp[3], L3 * (0.70 + tp[2] / 2))))
        tips[f] = dict(pad=[round(c, 4) for c in ue_cm(hand[f]["tip"].matrix_world.translation)],
                       end=[round(c, 4) for c in end])

    # 部件 → (手指, 关节级别 1~4)；0 级（掌上不动）的不写
    level_of = {}
    for name, sources in units:
        o = sources[0]
        while o is not None:
            hit = next(((f, k + 1) for f in H.FINGERS for k, j in enumerate(hand[f]["J"]) if j == o), None)
            if hit:
                level_of[name] = list(hit)
                break
            o = o.parent

    wo = H.P["wrist_origin"]
    mid = hand["middle"]["J"][0].matrix_world.translation
    wrist = ue_cm(Vector(wo) * 0.001)
    rig = dict(
        _说明="五指灵巧手关节表（export_ue.py 生成）。虚幻模型坐标、厘米、未缩放；关节 k 相对 rest 多转 Δ 度 = FQuat(axis, Δ) 绕 pivot，"
             "J1→J4 逐级累乘。正角度 = 往手心弯（J2 是侧摆）。",
        side="right",
        palm_dir=[0, 1, 0],
        wrist=[round(c, 4) for c in wrist],
        knuckle=[round(c, 4) for c in ue_cm(mid)],
        palm_center_y=round(-H.P["palm"]["y_center"] / 10, 4),
        palm_thick=H.P["palm"]["thick"] / 10,
        joints=joints, poses=poses, tips=tips, units=level_of)

    # 自检：用上面的表在"虚幻坐标"里重算握拳、捏合两个手势的指尖位置，和 Blender 直接摆出来的比
    worst = 0.0
    for pose_name in ("fist", "pinch", "open"):
        H.apply_pose(hand, H.POSES[pose_name])
        bpy.context.view_layer.update()
        for f in H.FINGERS:
            v = Vector(tips[f]["pad"])
            for k in range(3, -1, -1):   # 从远端往近端套：先绕 J4 转，再绕 J3……
                d = poses[pose_name][f][k] - poses["rest"][f][k]
                jt = joints[f][k]
                v = rot_about(Vector(jt["pivot"]), Vector(jt["axis"]), d, v)
            truth = ue_cm(hand[f]["tip"].matrix_world.translation)
            worst = max(worst, (v - truth).length)
    H.apply_pose(hand, H.POSES["rest"])
    bpy.context.view_layer.update()
    if worst > 0.01:
        raise RuntimeError("关节表自检没过：指尖最大误差 %.4f cm" % worst)
    path = os.path.join(out, "hand_ue_rig.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=1)
    print("[OK] 关节表 %s（%d 个活动部件，自检指尖最大误差 %.5f cm）" % (path, len(level_of), worst))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    rig_only = "--rig-only" in argv
    argv = [a for a in argv if a != "--rig-only"]
    out = os.path.abspath(argv[0]) if argv else os.path.join(HERE, "output")
    os.makedirs(out, exist_ok=True)

    # build_hand 的 build() 会读 sys.argv 里的 --solve，这里不需要
    hand = H.build()
    for ob in bpy.data.objects:                  # 去掉动画，免得换帧时把手势覆盖回去
        if ob.animation_data:
            ob.animation_data_clear()
    H.set_explode(0)
    H.apply_pose(hand, H.POSES["rest"])
    bpy.context.view_layer.update()

    explode_of = {ob.name: vec for ob, base, vec in H.EXPLODE}
    by_path = {}
    for path, name, desc, mat in H.TREE:
        by_path.setdefault(path, []).append(bpy.data.objects[name])

    units = []   # (节点名, 零件树路径, 材料)
    for path, en, mat in BODY:
        units.append((en, path, mat))
    for f in H.FINGERS:
        for leaf, (en, mat) in LEAF.items():
            units.append((FINGER_EN[f] + "_" + en, "手/%s/%s" % (H.CN[f], leaf), mat))

    if rig_only:
        export_rig(hand, out, [("H%02d_%s" % (i, en), by_path[path]) for i, (en, path, mat) in enumerate(units, 1)])
        return

    coll = bpy.data.collections.new("UE_Export")
    bpy.context.scene.collection.children.link(coll)
    rows = []
    for i, (en, path, mat) in enumerate(units, 1):
        sources = by_path[path]
        name = "H%02d_%s" % (i, en)
        ex = [] if en == "PalmFrame" else route(sources[0], explode_of)
        ob = bake_unit(name, sources, coll)
        parts = path.split("/")
        cn = parts[-1] if len(parts) == 2 or parts[1] == "掌骨架" else "%s · %s" % (parts[1], parts[-1])
        ob["part_no"] = name
        ob["name_cn"] = cn
        ob["material_spec"] = mat
        ob["desc"] = info_text(path)
        ob["ex"] = json.dumps(ex)
        rows.append(dict(name=name, name_cn=cn, material=mat, parts=len(sources), ex=ex))

    keys = [json.dumps(r["ex"]) for r in rows]
    dup = [r["name"] for r, k in zip(rows, keys) if k != "[]" and keys.count(k) > 1]
    if dup:   # 虚幻那边按爆炸路线分组，路线一样的部件会被合成一个
        raise RuntimeError("这些部件的爆炸路线完全一样：%s" % dup)

    for ob in bpy.context.scene.objects:
        ob.select_set(ob.users_collection[0] == coll)
    glb = os.path.join(out, "hand_ue.glb")
    kw = dict(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_extras=True,
              export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ("export_animations", "export_cameras", "export_lights"):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    with open(os.path.join(out, "hand_ue_parts.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    export_rig(hand, out, [(r["name"], by_path[path]) for r, (en, path, mat) in zip(rows, units)])
    print("[OK] %d 个部件（%d 个网格零件）→ %s" % (len(rows), sum(r["parts"] for r in rows), glb))


if __name__ == "__main__":
    main()
