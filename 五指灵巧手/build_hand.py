# -*- coding: utf-8 -*-
"""
五指灵巧手（20 自由度，直驱关节）—— 零件树 + 共享参数表 + 逐件建模

用法
  在 Blender 里：   blender --python build_hand.py            （打开界面并生成模型）
  无界面生成：     blender -b --python build_hand.py -- --out output
  pip 版 bpy：     python build_hand.py --out output
输出（都在 output\\ 里）：hand.blend、hand.glb、五指灵巧手_离线版.html、part_tree.md、bom.csv

坐标系：法兰中心为原点，+Z 指向指尖，手心朝 -Y，右手拇指在 +X，单位 mm（根节点缩放 0.001 → 米）。
所有尺寸只从 params.json 读取；零件树在建模过程中自动登记。
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "params.json"), encoding="utf-8") as f:
    P = json.load(f)

FINGERS = ["thumb", "index", "middle", "ring", "little"]
CN = {"thumb": "拇指", "index": "食指", "middle": "中指", "ring": "无名指", "little": "小指"}
rad = math.radians

# ---------------------------------------------------------------- 零件树登记
TREE = []          # [(层级路径, 名称, 中文说明, 材质)]
EXPLODE = []       # [(object, 基准位置, 偏移向量)]  e∈[0,1] 时 loc = base + vec*e


def reg(obj, path, desc, mat=""):
    TREE.append((path, obj.name, desc, mat))
    obj["part_path"] = path
    obj["part_desc"] = desc


def add_explode(obj, vec):
    EXPLODE.append((obj, obj.location.copy(), Vector(vec)))


# ---------------------------------------------------------------- 场景 / 材质
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name in ("cycles",):
        try:
            import addon_utils
            addon_utils.enable(name, default_set=True)
        except Exception:
            pass


MAT = {}


def make_materials():
    for key, m in P["materials"].items():
        mat = bpy.data.materials.new(key)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        rgb = m["rgb"]
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Metallic"].default_value = m.get("metal", 0)
        bsdf.inputs["Roughness"].default_value = m.get("rough", 0.5)
        if "emit" in m:
            bsdf.inputs["Emission Color"].default_value = (*rgb, 1)
            bsdf.inputs["Emission Strength"].default_value = m["emit"]
        if key == "silicone":
            try:
                bsdf.inputs["Subsurface Weight"].default_value = 0.08
            except KeyError:
                pass
        mat.diffuse_color = (*rgb, 1)   # 视口实体模式颜色
        MAT[key] = mat


COLL = None


def new_empty(name, parent=None, loc=(0, 0, 0), size=3.0):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "PLAIN_AXES"
    e.empty_display_size = size
    COLL.objects.link(e)
    e.parent = parent
    e.location = loc
    return e


def finish_mesh(name, bm, parent, mat, bevel=0.0, smooth=True, seg=3):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    COLL.objects.link(ob)
    ob.parent = parent
    ob.data.materials.append(MAT[mat])
    if bevel > 0:
        md = ob.modifiers.new("Bevel", "BEVEL")
        md.width = bevel
        md.segments = seg
        md.limit_method = "ANGLE"
        md.angle_limit = rad(35)
        md.harden_normals = True
    return ob


# ---------------------------------------------------------------- 几何基本体（bmesh）
def bm_box(size, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm


def bm_cyl(r, depth, axis="X", center=(0, 0, 0), seg=48, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r, radius2=r if r2 is None else r2, depth=depth)
    if axis == "X":
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rad(90), 3, "Y"))
    elif axis == "Y":
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rad(90), 3, "X"))
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm


def bm_cyls(specs, seg=20):
    """多个小圆柱合成一个网格：specs = [(r, depth, axis, center), ...]"""
    bm = bmesh.new()
    rot = {"X": Matrix.Rotation(rad(90), 4, "Y"), "Y": Matrix.Rotation(rad(90), 4, "X"), "Z": Matrix.Identity(4)}
    for r, depth, axis, c in specs:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=depth,
                              matrix=Matrix.Translation(c) @ rot[axis])
    return bm


def bm_ellipsoid(size, center=(0, 0, 0), rot_y=0.0, u=40, v=20):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=0.5)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if rot_y:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rad(rot_y), 3, "Y"))
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm


def bm_prism(pts2d, plane, d0, d1):
    """pts2d 为闭合多边形；plane='YZ' 时沿 X 拉伸（侧视轮廓），plane='XZ' 时沿 Y 拉伸（正视轮廓）"""
    bm = bmesh.new()

    def v3(a, b, d):
        return (d, a, b) if plane == "YZ" else (a, d, b)

    lo = [bm.verts.new(v3(a, b, d0)) for a, b in pts2d]
    hi = [bm.verts.new(v3(a, b, d1)) for a, b in pts2d]
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    return bm


def inset_polygon(pts, d):
    """逆时针多边形向内偏移 d（斜接）"""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e1 = (p1 - p0).normalized()
        e2 = (p2 - p1).normalized()
        n1 = Vector((-e1.y, e1.x))
        n2 = Vector((-e2.y, e2.x))
        m = (n1 + n2)
        if m.length < 1e-6:
            m = n1
        m.normalize()
        c = max(m.dot(n1), 0.35)
        q = p1 + m * (d / c)
        out.append((q.x, q.y))
    return out


# ---------------------------------------------------------------- 指骨侧视轮廓
def phalanx_profile(L, t, r0, r1, start="flex", tip=False):
    """返回 (y,z) 多边形。关节中心在 z=0 和 z=L；r0/r1 为两端关节电机半径。
    手心侧（-y）在关节附近做斜切，保证屈曲 90° 不互相穿模。"""
    h = t / 2
    if start == "flex":
        s_back, s_palm = r0 * 0.45, r0 + 1.5
        start_pts = [(-h, s_palm), (-0.3 * h, 0.45 * r0), (0.45 * h, 0.0)]
    else:  # 侧摆关节：轴沿 Y，两侧对称留出间隙
        s_back = s_palm = r0 + 0.8
        start_pts = [(-h, s_palm)]
    if tip:
        zc = L - h * 0.95
        arc = [(h * math.cos(a), zc + h * 0.95 * math.sin(a))
               for a in [rad(x) for x in range(0, 181, 12)]]
        pts = [(h, s_back)] + arc + start_pts
    else:
        e_back, e_palm = L - r1 * 0.45, L - r1 - 1.5
        pts = [(h, s_back), (h, e_back), (0.45 * h, L), (-0.3 * h, L - 0.45 * r1), (-h, e_palm)] + start_pts
    # 去掉重复点并保证逆时针（在 y-z 平面）
    clean = []
    for p in pts:
        if not clean or (Vector(p) - Vector(clean[-1])).length > 1e-4:
            clean.append(p)
    area = sum(clean[i][0] * clean[(i + 1) % len(clean)][1] - clean[(i + 1) % len(clean)][0] * clean[i][1]
               for i in range(len(clean)))
    if area < 0:
        clean.reverse()
    return clean


# ---------------------------------------------------------------- 关节电机模组
def build_motor(name, parent, act, axis, total, center, path, pop_vec):
    """直驱关节模组 = 定子壳（银）+ 两侧输出环（橙）+ 端盖轮毂（黑）。total 是整个模组的轴向宽度（不超出指骨宽）。"""
    grp = new_empty(name, parent, center, size=2)
    r = act["dia"] / 2
    ring = act["ring"]
    length = total - 2 * ring - 1.0
    stator = finish_mesh(name + "_stator", bm_cyl(r, length, axis), grp, "motor", bevel=0.6, seg=2)
    reg(stator, path, "定子壳 Ø%.0f×%.1f" % (act["dia"], length), "motor")
    ax = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
    for s in (1, -1):
        c = ax * s * (length / 2 + ring / 2)
        rg = finish_mesh("%s_ring%s" % (name, "R" if s > 0 else "L"), bm_cyl(r * 0.88, ring, axis, c), grp,
                         "ring", bevel=0.35, seg=2)
        reg(rg, path, "输出环", "ring")
        hub = finish_mesh("%s_hub%s" % (name, "R" if s > 0 else "L"),
                          bm_cyl(r * 0.36, 0.6, axis, ax * s * (length / 2 + ring + 0.25)), grp, "sensor",
                          bevel=0.15, seg=1)
        reg(hub, path, "端盖轮毂", "sensor")
    add_explode(grp, pop_vec)
    return grp


# ---------------------------------------------------------------- 手指（五指共用模板）
URDF_C = Matrix.Rotation(math.pi, 4, "X")   # URDF 坐标 (x, y, z) → 本模型 (x, -y, -z)


def urdf_rot(rpy):
    """URDF 的 rpy（固定轴 X→Y→Z，弧度）换算成本模型坐标系下的旋转"""
    r, p, y = rpy
    m = Matrix.Rotation(y, 4, "Z") @ Matrix.Rotation(p, 4, "Y") @ Matrix.Rotation(r, 4, "X")
    return URDF_C @ m @ URDF_C.transposed()


def base_matrix(fp):
    return urdf_rot(fp["urdf_rpy"])


def base_pos(fp):
    x, y, z = fp["urdf_xyz"]
    wo = P["wrist_origin"]
    return Vector((x + wo[0], -y + wo[1], -z + wo[2]))


def fix_frame(name, parent, loc, rpy):
    """关节前的固定坐标系（拇指的 J2/J3 轴相对上一节有固定偏转）。电机定子挂在这里，不随本关节转。"""
    e = new_empty(name, parent, loc, size=2)
    e.matrix_basis = Matrix.Translation(loc) @ urdf_rot(rpy)
    return e


def build_finger(fname, root):
    fp = P["fingers"][fname]
    A = P["actuators"]
    C = P["finger_common"]
    EX = P["explode"]
    pre = fp.get("pre_rpy", {})
    w, t = fp["w"], fp["t"]
    L1, L2, L3 = fp["L"]
    tag = CN[fname]
    path0 = "手/%s" % tag

    bp = base_pos(fp)
    base = new_empty(fname + "_base", root, bp, size=5)
    base.matrix_basis = Matrix.Translation(bp) @ base_matrix(fp)
    dir_world = (base_matrix(fp) @ Vector((0, 0, 1, 0))).to_3d()
    add_explode(base, dir_world * EX["finger_out"])

    # J1 根部屈伸电机（定子固定在掌内）
    build_motor(fname + "_M1", base, A["mcp_flex"], "X", w, (0, 0, 0), path0 + "/J1 根部屈伸电机",
                (0, -EX["motor_pop"], 0))

    if fname == "thumb":   # 拇指根座：把 J1 电机包在掌前侧，像人手的大鱼际
        hz = P["actuators"]["mcp_flex"]["dia"]
        house = finish_mesh("thumb_root", bm_box((w + 3.0, t + 5.0, hz + 4.0), (0, 1.5, -hz * 0.35)), base,
                            "skeleton", bevel=4.0, seg=3)
        reg(house, path0 + "/J1 根部屈伸电机", "拇指根座", "skeleton")

    # J1 转子 → 指根轭架；轭架末端是 J2 的固定坐标系（挂 J2 侧摆电机）
    j1 = new_empty(fname + "_J1", base, (0, 0, 0))
    r1 = A["mcp_flex"]["dia"] / 2
    ra = A["abd"]["dia"] / 2
    off = fp.get("abd_offset", C["abd_offset"])
    yoke_prof = [(t / 2, r1 * 0.45), (t / 2 * 0.92, off), (-t / 2 * 0.92, off), (-t / 2, r1 + 1.0),
                 (-0.3 * t / 2, 0.45 * r1), (0.45 * t / 2, 0.0)]
    yoke = finish_mesh(fname + "_yoke", bm_prism(yoke_prof, "YZ", -w / 2 * 0.9, w / 2 * 0.9), j1, "skeleton",
                       bevel=2.0)
    reg(yoke, path0 + "/指根轭架", "指根轭架（J1 转子 → J2 定子）", "skeleton")
    f2 = fix_frame(fname + "_F2", j1, (0, 0, off), pre.get("J2", (0, 0, 0)))
    add_explode(f2, (0, 0, EX["joint_gap"] * 0.7))
    build_motor(fname + "_M2", f2, A["abd"], "Y", t * 0.95, (0, 0, 0), path0 + "/J2 侧摆电机",
                (0, -EX["motor_pop"], 0))

    # J2 转子 → 近节
    j2 = new_empty(fname + "_J2", f2, (0, 0, 0))
    rp = A["pip"]["dia"] / 2
    prox = finish_mesh(fname + "_proximal",
                       bm_prism(phalanx_profile(L1, t, ra, rp, start="abd"), "YZ", -w / 2, w / 2),
                       j2, "skeleton", bevel=C["link_bevel"])
    reg(prox, path0 + "/近节指骨", "近节指骨 L=%.1f" % L1, "skeleton")
    add_pad(fname + "_pad1", j2, w, t, L1, ra + 2, path0 + "/近节指骨", 0.55)
    add_shell(fname + "_s1", j2, w, t, L1, ra + 1, L1 - rp - 1, path0 + "/近节指骨")
    f3 = fix_frame(fname + "_F3", j2, (0, 0, L1), pre.get("J3", (0, 0, 0)))
    add_explode(f3, (0, 0, EX["joint_gap"]))
    build_motor(fname + "_M3", f3, A["pip"], "X", w, (0, 0, 0), path0 + "/J3 中节屈伸电机",
                (0, -EX["motor_pop"], 0))

    # J3 → 中节
    j3 = new_empty(fname + "_J3", f3, (0, 0, 0))
    rd = A["dip"]["dia"] / 2
    mid = finish_mesh(fname + "_middle",
                      bm_prism(phalanx_profile(L2, t * 0.96, rp, rd), "YZ", -w / 2 * 0.97, w / 2 * 0.97),
                      j3, "skeleton", bevel=C["link_bevel"])
    reg(mid, path0 + "/中节指骨", "中节指骨 L=%.1f" % L2, "skeleton")
    add_pad(fname + "_pad2", j3, w * 0.97, t * 0.96, L2, rp + 1.5, path0 + "/中节指骨", 0.5)
    add_shell(fname + "_s2", j3, w * 0.97, t * 0.96, L2, rp * 0.6, L2 - rd - 1, path0 + "/中节指骨")
    f4 = fix_frame(fname + "_F4", j3, (0, 0, L2), pre.get("J4", (0, 0, 0)))
    add_explode(f4, (0, 0, EX["joint_gap"]))
    build_motor(fname + "_M4", f4, A["dip"], "X", w * 0.94, (0, 0, 0), path0 + "/J4 远节屈伸电机",
                (0, -EX["motor_pop"], 0))

    # J4 → 远节 + 指尖传感器 + 指腹
    j4 = new_empty(fname + "_J4", f4, (0, 0, 0))
    td = t * 0.9
    dist = finish_mesh(fname + "_distal",
                       bm_prism(phalanx_profile(L3, td, rd, 0, tip=True), "YZ", -w / 2 * 0.92, w / 2 * 0.92),
                       j4, "skeleton", bevel=C["link_bevel"] * 0.9)
    reg(dist, path0 + "/远节指骨", "远节指骨 L=%.1f" % L3, "skeleton")
    # 硅胶指尖套：像顶针一样把远节末端整个包住，捏取时总是软的先接触
    tp = C["tip_pad"]
    zp = L3 * 0.70
    cap_z0 = zp - L3 * tp[2] / 2
    zc = max(rd + C["tip_sensor_len"] / 2 + 0.5, cap_z0 - 0.5)
    sens = finish_mesh(fname + "_tipsensor",
                       bm_box((w * 0.92 + 1.2, td + 1.2, C["tip_sensor_len"]), (0, 0, zc)),
                       j4, "sensor", bevel=1.2)
    reg(sens, path0 + "/指尖力传感器", "多轴指尖力传感器", "sensor")
    add_explode(sens, (0, 0, 7))
    tippad = finish_mesh(fname + "_tippad",
                         bm_ellipsoid((w * tp[0], td * tp[1], L3 * tp[2]), (0, -td * tp[3], zp)),
                         j4, "silicone")
    reg(tippad, path0 + "/指尖力传感器", "硅胶指尖套", "silicone")
    add_explode(tippad, (0, -EX["pad_out"] * 0.4, 12))
    surf = td * (tp[3] + tp[1] / 2)    # 指腹表面到指骨中线的距离
    tip = new_empty(fname + "_tip", j4, (0, -surf, zp), size=2)
    return {"base": base, "J": [j1, j2, j3, j4], "tip": tip}


def add_shell(name, parent, w, t, L, z0, z1, path):
    """指背盖板 + 两侧固定螺钉（外观件，盖住指骨背面的走线槽）"""
    zc = (z0 + z1) / 2
    plate = finish_mesh(name + "_cover", bm_box((w * 0.66, 1.4, (z1 - z0) * 0.62), (0, t / 2 + 0.25, zc)), parent,
                        "cover", bevel=0.6, seg=2)
    reg(plate, path, "指背盖板", "cover")
    add_explode(plate, (0, 9, 0))
    specs = []
    for sx in (1, -1):
        for fz in (0.3, 0.7):
            specs.append((1.05, 0.7, "X", (sx * (w / 2 + 0.15), t * 0.12, z0 + (z1 - z0) * fz)))
    sc = finish_mesh(name + "_screws", bm_cyls(specs), parent, "motor", bevel=0.2, seg=1)
    reg(sc, path, "M1.6 螺钉 ×4", "motor")


def add_pad(name, parent, w, t, L, z0, path, frac):
    C = P["finger_common"]
    zc = z0 + (L - z0) * 0.45
    pad = finish_mesh(name, bm_box((w * 0.74, C["pad_thick"] + 1.0, (L - z0) * frac),
                                   (0, -t / 2 - C["pad_thick"] * 0.25, zc)), parent, "silicone",
                      bevel=1.4)
    reg(pad, path, "硅胶指节垫", "silicone")
    add_explode(pad, (0, -P["explode"]["pad_out"] * 0.5, 0))


# ---------------------------------------------------------------- 法兰 / 腕部 / 掌
def build_body(root):
    EX = P["explode"]
    fl = P["flange"]
    g = new_empty("flange_grp", root)
    flange = finish_mesh("flange", bm_cyl(fl["dia"] / 2, fl["thick"], "Z", (0, 0, fl["thick"] / 2), seg=64),
                         g, "motor", bevel=1.0)
    reg(flange, "手/法兰", "法兰盘 Ø%d（接机械臂）" % fl["dia"], "motor")
    pilot = finish_mesh("flange_pilot", bm_cyl(fl["pilot_dia"] / 2, fl["pilot_h"], "Z", (0, 0, -fl["pilot_h"] / 2)),
                        g, "motor", bevel=0.4)
    reg(pilot, "手/法兰", "定位止口", "motor")
    for i in range(fl["bolt_n"]):
        a = rad(45 + 360 / fl["bolt_n"] * i)
        c = (fl["bolt_circle"] / 2 * math.cos(a), fl["bolt_circle"] / 2 * math.sin(a), -0.3)
        b = finish_mesh("flange_bolt%d" % i, bm_cyl(fl["bolt_dia"] / 2 + 1, 0.8, "Z", c, seg=24), g, "sensor",
                        bevel=0.2)
        reg(b, "手/法兰", "M4 螺钉头", "sensor")
    add_explode(g, (0, 0, -EX["flange_down"]))

    wr = P["wrist"]
    gw = new_empty("wrist_grp", root)
    hz = wr["z1"] - wr["z0"]
    wrist = finish_mesh("wrist", bm_box((wr["w"], wr["d"], hz), (0, 0, wr["z0"] + hz / 2)), gw, "cover",
                        bevel=wr["r"], seg=4)
    reg(wrist, "手/腕部模块", "腕部壳体（驱动板、IMU）", "cover")
    port = finish_mesh("wrist_port", bm_cyl(wr["port_dia"] / 2, 5, "Y", (-14, wr["d"] / 2 + 1.2, wr["z0"] + 9)),
                       gw, "motor", bevel=0.5)
    reg(port, "手/腕部模块", "以太网/电源接口", "motor")
    plug = finish_mesh("wrist_port_in", bm_box((5.5, 1.0, 4.0), (-14, wr["d"] / 2 + 3.4, wr["z0"] + 9)), gw,
                       "sensor", bevel=0.3)
    reg(plug, "手/腕部模块", "接口插芯", "sensor")
    led = finish_mesh("wrist_led", bm_cyl(1.6, 1.2, "Y", (12, wr["d"] / 2 + 0.2, wr["z0"] + 10), seg=24), gw,
                      "led")
    reg(led, "手/腕部模块", "状态灯", "led")
    add_explode(gw, (0, 0, -EX["wrist_down"]))

    pm = P["palm"]
    h = pm["thick"] / 2
    gp = new_empty("palm_grp", root, (0, pm["y_center"], 0))   # 掌的子零件都相对掌厚中线
    palm = finish_mesh("palm_frame", bm_prism(pm["outline_xz"], "XZ", -h, h), gp, "skeleton", bevel=pm["bevel"],
                       seg=4)
    reg(palm, "手/掌骨架", "掌骨架（铝合金）", "skeleton")

    bc = pm["back_cover"]
    inner = inset_polygon(pm["outline_xz"], bc["inset"])
    gc = new_empty("backcover_grp", gp)
    cover = finish_mesh("back_cover", bm_prism(inner, "XZ", h - 0.6, h + bc["thick"]), gc, "cover", bevel=1.6)
    reg(cover, "手/掌骨架/背盖", "背盖", "cover")
    zs = 58
    for i in range(bc["slot_n"]):
        x = -10 + (i - (bc["slot_n"] - 1) / 2) * 9
        s = finish_mesh("back_slot%d" % i, bm_box((bc["slot_w"], 0.8, bc["slot_l"]), (x, h + bc["thick"] + 0.1, zs)),
                        gc, "sensor", bevel=0.6)
        reg(s, "手/掌骨架/背盖", "散热槽", "sensor")
    bar = finish_mesh("back_ledbar", bm_box((22, 0.8, 2.4), (12, h + bc["thick"] + 0.15, 74)), gc, "led",
                      bevel=0.5)
    reg(bar, "手/掌骨架/背盖", "状态灯条", "led")
    add_explode(gc, (0, EX["back_cover_out"], 0))

    fc = pm["front_cover"]
    gf = new_empty("palmskin_grp", gp)
    skin_outline = inset_polygon(pm["outline_xz"], fc["inset"])
    skin = finish_mesh("palm_skin", bm_prism(skin_outline, "XZ", -h - fc["thick"], -h + 0.8), gf, "silicone",
                       bevel=2.2, seg=4)
    reg(skin, "手/掌骨架/掌心硅胶", "掌心硅胶皮", "silicone")
    for key, pd in pm["pads"].items():
        if key.startswith("_"):
            continue
        cn = {"thenar": "大鱼际垫", "hypothenar": "小鱼际垫"}[key]
        pad = finish_mesh("palm_pad_" + key, bm_ellipsoid(pd["size"], pd["center"], pd["rot_y"]), gf, "silicone")
        reg(pad, "手/掌骨架/掌心硅胶", cn, "silicone")
    add_explode(gf, (0, -EX["pad_out"], 0))
    return gp


# ---------------------------------------------------------------- 姿态 / 动画
POSES = {
    "rest":   {"finger": [6, 0, 12, 6], "thumb": [10, -10, 8, 6]},
    "open":   {"finger": [0, 0, 0, 0], "thumb": [0, 0, 0, 0]},
    "fist":   {"finger": [88, 0, 105, 75], "thumb": [55, -35, 30, 40]},
    "spread": {"index": [0, 16, 0, 0], "middle": [0, 3, 0, 0], "ring": [0, -12, 0, 0], "little": [0, -24, 0, 0],
               "thumb": [-20, -30, 0, 0]},
    "pinch":  {"index": [40, 0, 40, 25], "middle": [10, -2, 18, 10], "ring": [14, -6, 22, 12],
               "little": [18, -10, 26, 14], "thumb": [30, -40, 20, 20]},
}


def clamp(fname, k, v):
    lim = P["limits_deg"]["thumb" if fname == "thumb" else "finger"]["J%d" % (k + 1)]
    return max(lim[0], min(lim[1], v))


def apply_pose(hand, pose, frame=None):
    for fname, d in hand.items():
        ang = pose.get(fname, pose.get("thumb" if fname == "thumb" else "finger", [0, 0, 0, 0]))
        for k, j in enumerate(d["J"]):
            a = rad(clamp(fname, k, ang[k]))
            if k == 1:
                j.rotation_euler = (0, a, 0)
            else:
                j.rotation_euler = (a, 0, 0)
            if frame is not None:
                j.keyframe_insert("rotation_euler", frame=frame)


def set_explode(e, frame=None):
    for ob, base, vec in EXPLODE:
        ob.location = base + vec * e
        if frame is not None:
            ob.keyframe_insert("location", frame=frame)


# ---------------------------------------------------------------- 干涉检测（求解姿态 & 自查共用）
LEVEL = {"base": 0, "J1": 1, "J2": 2, "J3": 3, "J4": 4}


def rigid_key(ob):
    """零件所属刚体：(手指名, 层级)；掌/腕/法兰为 ('body', -1)"""
    p = ob.parent
    while p is not None:
        for f in FINGERS:
            if p.name.startswith(f + "_") and p.name[len(f) + 1:] in LEVEL:
                return f, LEVEL[p.name[len(f) + 1:]]
        p = p.parent
    return "body", -1


def adjacent(a, b):
    """相邻刚体按设计就贴合，不算穿模"""
    if a[0] == b[0]:
        return abs(a[1] - b[1]) <= 1
    if "body" in (a[0], b[0]):
        other = b if a[0] == "body" else a
        return other[1] <= (2 if other[0] == "thumb" else 1)
    return False


class Interference:
    """把每个网格（含倒角修改器）的局部顶点缓存下来，按当前 matrix_world 变换成 mm 后建 BVH 求相交三角形数。"""

    def __init__(self):
        import numpy as np
        self.np = np
        dg = bpy.context.evaluated_depsgraph_get()
        self.items = []
        for o in bpy.data.objects:
            if o.type != "MESH":
                continue
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            vs = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
            polys = [p.vertices[:] for p in me.polygons]
            ev.to_mesh_clear()
            self.items.append((o, rigid_key(o), vs, polys))

    def trees(self, names=None):
        from mathutils.bvhtree import BVHTree
        np = self.np
        out = {}
        for o, k, vs, polys in self.items:
            if names is not None and k[0] not in names:
                continue
            m = np.array(o.matrix_world) * 1000.0
            w = vs @ m[:3, :3].T + m[:3, 3]
            out[o.name] = (k, BVHTree.FromPolygons(w.tolist(), polys))
        return out

    @staticmethod
    def overlaps(ta, tb, allow=()):
        hits = []
        for na, (ka, A) in ta.items():
            for nb, (kb, Bt) in tb.items():
                if na >= nb and tb is ta:
                    continue
                if ka[0] == kb[0] and tb is not ta:
                    continue
                if adjacent(ka, kb):
                    continue
                if any(x in na and y in nb or x in nb and y in na for x, y in allow):
                    continue
                n = len(A.overlap(Bt))
                if n:
                    hits.append((n, na, nb))
        return hits


def solve_pose(hand, pose, var_keys, target_fn, allow=(), penalty=2.0, grid=None, topk=1, starts0=None):
    """坐标下降求解关节角：cost = target_fn() + penalty × 相交三角形数。
    var_keys: [(手指, 关节序号)]；只有这些关节会动，其余手指作为静态障碍。"""
    vl = bpy.context.view_layer
    movable = sorted({f for f, k in var_keys})
    apply_pose(hand, pose)
    vl.update()
    itf = Interference()
    static = itf.trees([f for f in FINGERS + ["body"] if f not in movable])
    x = [pose[f][k] for f, k in var_keys]

    def setx(v):
        for (f, k), val in zip(var_keys, v):
            pose[f] = list(pose[f])
            pose[f][k] = clamp(f, k, val)
        apply_pose(hand, pose)
        vl.update()

    def cost(v):
        setx(v)
        mov = itf.trees(movable)
        hits = itf.overlaps(mov, static, allow) + itf.overlaps(mov, mov, allow)
        n = sum(h[0] for h in hits)
        t = target_fn()
        return t + penalty * n, t, n

    starts = [(cost(x)[0], x)]
    if starts0:
        starts = sorted(((cost(list(v))[0], list(v)) for v in starts0), key=lambda s: s[0])[:topk]
    if grid:   # 第一阶段：粗网格搜索，取最好的几个当起点（避免从穿模的初值卡死）
        import itertools
        idx = sorted(grid)
        for combo in itertools.product(*[grid[i] for i in idx]):
            v = list(x)
            for i, val in zip(idx, combo):
                v[i] = val
            starts.append((cost(v)[0], v))
        starts.sort(key=lambda s: s[0])
        starts = starts[:topk]

    def descend(x, step):
        best, tval, nhit = cost(x)
        while step > 0.5:
            improved = False
            for i in range(len(x)):
                for s in (step, -step):
                    v = list(x)
                    v[i] += s
                    c, t, n = cost(v)
                    if c < best - 1e-6:
                        best, tval, nhit, x, improved = c, t, n, v, True
            if not improved:
                step *= 0.5
        return best, tval, nhit, x

    # 第二阶段：从每个起点做坐标下降，取总代价最小的
    best, tval, nhit, x = min((descend(list(v), 8.0 if grid else 16.0) for _, v in starts), key=lambda r: r[0])
    setx(x)
    for f in movable:
        pose[f] = [round(a, 1) for a in pose[f]]
    apply_pose(hand, pose)
    return tval, nhit


def wpos(ob, local=(0, 0, 0)):
    return ob.matrix_world @ Vector(local)


THUMB_GRID = {0: [-20, 0, 15, 30, 45, 60, 74], 1: [-80, -60, -40, -20, 0, 20, 40],
              2: [0, 25, 50, 75], 3: [0, 25, 50, 75]}


THUMB_DIR = {   # 张开/放松/张指时拇指（根部→指尖）想要的朝向
    "open": (0.70, -0.22, 0.68), "rest": (0.50, -0.50, 0.71), "spread": (0.93, -0.12, 0.35),
}


def solve_named_poses(hand):
    """拇指各姿态的关节角都由求解器算出（避免手工试错导致穿模）"""
    fp_i, fp_m = P["fingers"]["index"], P["fingers"]["middle"]
    thumb4 = [("thumb", 0), ("thumb", 1), ("thumb", 2), ("thumb", 3)]

    for name, d in THUMB_DIR.items():
        pose = POSES[name]
        for f in FINGERS:
            pose.setdefault(f, list(pose.get("thumb" if f == "thumb" else "finger", [0, 0, 0, 0])))
        tgt = Vector(d).normalized()

        def dir_target(pose=pose, tgt=tgt):
            a = hand["thumb"]["base"].matrix_world.translation
            b = hand["thumb"]["tip"].matrix_world.translation
            ang = math.degrees((b - a).normalized().angle(tgt))
            curl = abs(pose["thumb"][2]) + abs(pose["thumb"][3])
            return ang + 0.15 * curl + (0.1 * (20 - curl) if name == "rest" and curl < 20 else 0)

        solve_pose(hand, pose, thumb4, dir_target, grid=THUMB_GRID)
        print("[pose] %s thumb=%s" % (name, pose["thumb"]))

    # 对指：拇指指腹贴食指指腹，且两指腹法向相对
    pin = POSES["pinch"]
    for f in FINGERS:
        pin.setdefault(f, list(POSES["rest"].get(f, POSES["rest"]["finger"])))

    # 捏取目标：两个硅胶指尖套之间的最小间隙（接触即为 0），再加一点“指腹相对”的偏好
    from mathutils.bvhtree import BVHTree
    import numpy as np
    itf0 = Interference()
    caps = {o.name: (o, vs, polys) for o, k, vs, polys in itf0.items if o.name in ("thumb_tippad", "index_tippad")}

    def cap_world(name, step=1):
        o, vs, polys = caps[name]
        m = np.array(o.matrix_world) * 1000.0
        return (vs[::step] @ m[:3, :3].T + m[:3, 3]).tolist(), polys

    def pinch_target():
        iv, ip = cap_world("index_tippad")
        it = BVHTree.FromPolygons(iv, ip)
        tv, tpoly = cap_world("thumb_tippad")
        if it.overlap(BVHTree.FromPolygons(tv, tpoly)):
            gap = 0.0
        else:
            gap = min(it.find_nearest(Vector(p))[3] for p in tv[::3])
        ta, ia = hand["thumb"]["tip"].matrix_world, hand["index"]["tip"].matrix_world
        nt = (ta.to_3x3() @ Vector((0, -1, 0))).normalized()
        ni = (ia.to_3x3() @ Vector((0, -1, 0))).normalized()
        return gap + 2.0 * (1 + nt.dot(ni)) / 2

    keys7 = [("thumb", 0), ("thumb", 1), ("thumb", 2), ("thumb", 3), ("index", 0), ("index", 2), ("index", 3)]
    # 第一步：随机撒点只算运动学（很快），留下最好的一批当起点
    import random
    rnd = random.Random(7)
    vl = bpy.context.view_layer
    samples = []
    for _ in range(int(os.environ.get("PINCH_SAMPLES", "1200"))):
        v = []
        for f, k in keys7:
            lo, hi = P["limits_deg"]["thumb" if f == "thumb" else "finger"]["J%d" % (k + 1)]
            lo = max(lo, 0 if k >= 2 else lo)
            v.append(rnd.uniform(lo, hi if f == "thumb" else min(hi, 80)))
        for (f, k), val in zip(keys7, v):
            pin[f] = list(pin[f]); pin[f][k] = val
        apply_pose(hand, pin)
        vl.update()
        samples.append((pinch_target(), v))
    samples.sort(key=lambda s: s[0])
    # 第二步：从最好的几个起点带穿模惩罚做坐标下降
    d1, n1 = solve_pose(hand, pin, keys7, pinch_target, allow=(("thumb_tippad", "index_tippad"),),
                        penalty=0.5, topk=8, starts0=[v for _, v in samples[:40]])

    # 握拳：四指先弯好，拇指压在食指/中指中节外侧
    fist = POSES["fist"]
    for f in FINGERS:
        fist.setdefault(f, list(fist["thumb"] if f == "thumb" else fist["finger"]))

    def fist_target():
        pi = wpos(hand["index"]["J"][2], (0, fp_i["t"] / 2 + 7.5, fp_i["L"][1] * 0.45))
        pm = wpos(hand["middle"]["J"][2], (0, fp_m["t"] / 2 + 7.5, fp_m["L"][1] * 0.45))
        tgt = pi * 0.6 + pm * 0.4
        return (hand["thumb"]["tip"].matrix_world.translation - tgt).length * 1000

    d2, n2 = solve_pose(hand, fist, [("thumb", 0), ("thumb", 1), ("thumb", 2), ("thumb", 3)], fist_target,
                        grid=THUMB_GRID)
    # 四指在握拳时会向掌心汇聚：用 J2 侧摆把相邻手指错开，代价是侧摆角越小越好
    four = [("index", 1), ("middle", 1), ("ring", 1), ("little", 1)]
    sp, sn = solve_pose(hand, fist, four, lambda: 0.3 * sum(abs(fist[f][1]) for f, _ in four))
    print("[pose] 握拳四指侧摆 %s，相交 %d" % ([fist[f][1] for f, _ in four], sn))
    print("[pose] 对指 指尖套间隙+朝向代价 %.1f, 相交 %d | 握拳 拇指离目标 %.1f mm, 相交 %d" % (d1, n1, d2, n2))
    print("[pose] pinch thumb=%s index=%s | fist thumb=%s" % (pin["thumb"], pin["index"], fist["thumb"]))


FRAMES = {"rest": 1, "fist": 36, "open": 68, "pinch": 100, "spread": 155, "explode": 230}


def build_animation(hand):
    sc = bpy.context.scene
    sc.render.fps = 24
    seq = [(1, "rest", 0), (28, "fist", 0), (44, "fist", 0), (68, "open", 0), (92, "pinch", 0), (108, "pinch", 0),
           (128, "open", 0), (148, "spread", 0), (162, "spread", 0), (180, "rest", 0), (182, "rest", 0),
           (212, "spread", 1), (246, "spread", 1), (276, "rest", 0)]
    for fr, pose, e in seq:
        apply_pose(hand, POSES[pose], fr)
        set_explode(e, fr)
    sc.frame_start, sc.frame_end = 1, 276
    for ob in bpy.data.objects:
        ad = ob.animation_data
        if ad and ad.action:
            for fc in iter_fcurves(ad):
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.easing = "EASE_IN_OUT"
    set_explode(0)
    apply_pose(hand, POSES["rest"])


def iter_fcurves(ad):
    act = ad.action
    if hasattr(act, "fcurves") and act.fcurves:
        return list(act.fcurves)
    out = []   # Blender 5.x 分层动作
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


# ---------------------------------------------------------------- 输出零件树 / BOM
def write_tree(out):
    from collections import OrderedDict
    os.makedirs(out, exist_ok=True)
    groups = OrderedDict()
    for path, name, desc, mat in TREE:
        groups.setdefault(path, []).append((name, desc, mat))
    lines = ["# 零件树（由 build_hand.py 自动生成）", "",
             "网格零件 **%d** 个；关节电机 **20** 个（5 指 × 4）" % len(TREE), "", "```"]
    last = []
    for path in groups:
        parts = path.split("/")
        for i, p in enumerate(parts):
            if i < len(last) and last[i] == p:
                continue
            lines.append("    " * i + ("└─ " if i else "") + p)
        last = parts
        cnt = OrderedDict()
        for n, d, m in groups[path]:
            cnt[d] = cnt.get(d, 0) + 1
        for d, c in cnt.items():
            lines.append("    " * len(parts) + "· %s%s" % (d, " ×%d" % c if c > 1 else ""))
    lines.append("```")
    with open(os.path.join(out, "part_tree.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out, "bom.csv"), "w", encoding="utf-8-sig") as f:
        f.write("层级路径,对象名,说明,材质\n")
        for path, name, desc, mat in TREE:
            f.write("%s,%s,%s,%s\n" % (path, name, desc, mat))


# ---------------------------------------------------------------- 网页查看器（glb + 姿态数据）
PART_INFO = {
    "法兰": "把手装到机械臂末端。中间的止口负责定心，4 颗 M4 螺钉固定。",
    "腕部模块": "放驱动板、主控和 IMU。20 个关节电机的线都汇到这里，背面是以太网/电源接口和状态灯。",
    "掌骨架": "铝合金骨架。四指的 J1 电机、拇指根部、背盖和掌心硅胶都固定在它上面。",
    "背盖": "盖住掌内走线。三条散热槽给驱动电路散热，灯条显示工作状态。",
    "掌心硅胶": "一层软皮加大鱼际、小鱼际两块凸起。抓东西时变形贴合，增加接触面积和摩擦。",
    "J1 根部屈伸电机": "最大的关节电机（Ø18）。整根手指往手心弯靠它，要扛整根手指的力矩，所以最粗。定子固定在掌里，转子带动指根轭架。",
    "指根轭架": "J1 的输出件：J1 转动时带着它一起转，上面横着装 J2 侧摆电机。",
    "J2 侧摆电机": "轴线垂直于手掌，让手指左右张开、并拢（±40°）。它装在 J1 后面，所以手指弯下去以后，侧摆方向也跟着转。",
    "近节指骨": "第一节指骨。手心一侧在两端做了斜切，弯到 90° 也不会和前一节相撞；中间贴一块硅胶指节垫。",
    "J3 中节屈伸电机": "直驱关节：电机转子直接带动下一节，没有减速齿轮和连杆。好处是能反向驱动：外力推手指，电机跟着转，从电流就能估出受力。",
    "中节指骨": "第二节指骨，结构和近节一样，只是更短更窄。",
    "J4 远节屈伸电机": "最小的关节电机（Ø11）。人手的远端关节通常和中间关节联动，这里单独一个电机，所以能独立控制。",
    "远节指骨": "最后一节，末端做成圆头，外面包着指腹。",
    "指尖力传感器": "黑色的一圈是多轴力传感器，夹在指骨和硅胶指尖套之间，测接触力的大小和方向。指尖套像顶针一样包住指尖，负责防滑和缓冲，捏东西时总是软的先接触。",
}
THUMB_INFO = {
    "J1 根部屈伸电机": "拇指根部第一个关节。拇指的 J1、J2 两个轴互相垂直，像一个万向节，决定拇指能不能转到四指对面去（对掌）。",
    "J2 侧摆电机": "拇指根部第二个关节，让拇指在手掌平面内外摆动。和 J1 配合，拇指指腹才能正对食指指腹。",
    "近节指骨": "相当于人手的第一掌骨，所以比其他手指的近节短，也更粗。",
}


def _gl(v):
    """Blender (x, y, z) → glTF (x, z, -y)"""
    return [round(v[0], 3), round(v[2], 3), round(-v[1], 3)]


def export_web(hand, out):
    import base64
    sc = bpy.context.scene
    sc.frame_set(FRAMES["open"])
    zero = {f: [0, 0, 0, 0] for f in FINGERS}
    apply_pose(hand, zero)          # 网页里的关节角都相对 0 位，导出时必须全部归零
    set_explode(0)
    bpy.context.view_layer.update()
    for ob in bpy.data.objects:
        ob.select_set(False)
    root = bpy.data.objects["DexHand_root"]
    sel = [root] + list(root.children_recursive)
    for ob, base, vec in EXPLODE:
        ob["ex"] = json.dumps(_gl(vec))
    for f, d in hand.items():
        for k, j in enumerate(d["J"]):
            j["joint"] = json.dumps({"f": f, "k": k, "axis": [0, 0, -1] if k == 1 else [1, 0, 0]})
    for ob in sel:
        ob.select_set(True)
    glb = os.path.join(out, "hand.glb")
    saved = {}   # 导出器会按时间轴重新求动画，先把动作摘掉，导完再挂回去
    for ob in bpy.data.objects:
        if ob.animation_data and ob.animation_data.action:
            saved[ob.name] = ob.animation_data.action
            ob.animation_data.action = None
    apply_pose(hand, zero)
    set_explode(0)
    kw = dict(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_extras=True,
              export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ("export_animations", "export_cameras", "export_lights"):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    for name, act in saved.items():
        bpy.data.objects[name].animation_data.action = act

    # 零件分组（层级路径 → 说明）
    groups = []
    seen = {}
    for path, name, desc, mat in TREE:
        if path not in seen:
            leaf = path.split("/")[-1]
            fing = next((x for x in FINGERS if "/" + CN[x] + "/" in path + "/"), None)
            info = (THUMB_INFO.get(leaf) if fing == "thumb" else None) or PART_INFO.get(leaf, "")
            seen[path] = dict(key=path, name=leaf, parent="/".join(path.split("/")[:-1]), n=0, info=info, items=[])
            groups.append(seen[path])
        g = seen[path]
        g["n"] += 1
        if desc not in g["items"]:
            g["items"].append(desc)
    lo = Vector((1e9, 1e9, 1e9)); hi = -lo
    for ob in sel:
        if ob.type != "MESH":
            continue
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c) * 1000
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    poses = {}
    for name, pose in POSES.items():
        poses[name] = {f: [clamp(f, k, v) for k, v in
                           enumerate(pose.get(f, pose.get("thumb" if f == "thumb" else "finger", [0] * 4)))]
                       for f in FINGERS}
    data = dict(
        fingers=[[f, CN[f]] for f in FINGERS],
        poses=poses,
        poseNames=[["open", "张开"], ["rest", "放松"], ["fist", "握拳"], ["pinch", "对指捏取"], ["spread", "张指"]],
        seq=[["rest", 1.0], ["fist", 1.2], ["open", 0.9], ["pinch", 1.4], ["open", 0.9], ["spread", 1.2]],
        limits=P["limits_deg"], groups=groups,
        stats=dict(parts=len(TREE), dof=20, motors=20,
                   size=[round(hi.z - lo.z), round(hi.x - lo.x), round(hi.y - lo.y)]))
    with open(os.path.join(out, "hand_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("[web] hand.glb %.0f KB, 尺寸 长×宽×厚 = %s mm" % (os.path.getsize(glb) / 1024, data["stats"]["size"]))
    tpl = os.path.join(HERE, "viewer_template.html")
    if not os.path.exists(tpl):
        print("[WARN] 没找到 viewer_template.html，跳过网页")
        return
    with open(tpl, encoding="utf-8") as f:
        html = f.read()
    with open(glb, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    html = html.replace('"__GLB_BASE64__"', '"' + b64 + '"')
    html = html.replace('"__HAND_JSON__"', json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    dst = os.path.join(out, "五指灵巧手_离线版.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    print("[web] wrote", dst)


# ---------------------------------------------------------------- 灯光 / 相机
def setup_stage():
    sc = bpy.context.scene
    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.045, 0.05, 0.058, 1)
    bg.inputs["Strength"].default_value = 1.0

    def area(name, loc, target, power, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = power
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        COLL.objects.link(ob)
        ob.location = loc
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    tgt = (0, 0, 0.1)
    area("Key", (-0.35, -0.45, 0.42), tgt, 16, 0.35, (1.0, 0.97, 0.92))
    area("Fill", (0.45, -0.3, 0.15), tgt, 6, 0.5, (0.85, 0.92, 1.0))
    area("Rim", (0.1, 0.5, 0.35), tgt, 13, 0.3, (0.8, 0.9, 1.0))
    area("Top", (0.0, 0.0, 0.6), tgt, 5, 0.4)

    cd = bpy.data.cameras.new("Camera")
    cd.lens = 70
    cam = bpy.data.objects.new("Camera", cd)
    COLL.objects.link(cam)
    sc.camera = cam
    cd.clip_start = 0.01
    return cam


def aim_camera(cam, loc, target=(0, 0, 0.105), lens=70):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens


# ---------------------------------------------------------------- 主流程
def out_dir():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.path.join(HERE, "output")


def viewport_defaults():
    """在 Blender 界面里打开时：材质预览、单位毫米"""
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.type = "MATERIAL"
                        sp.clip_start = 0.001


def build():
    global COLL
    TREE.clear()
    EXPLODE.clear()
    reset_scene()
    make_materials()
    COLL = bpy.data.collections.new("DexHand")
    bpy.context.scene.collection.children.link(COLL)
    root = new_empty("DexHand_root", None, size=20)
    root.scale = (0.001, 0.001, 0.001)
    build_body(root)
    hand = {f: build_finger(f, root) for f in FINGERS}
    bpy.context.view_layer.update()
    if "--solve" in sys.argv or "poses" not in P:
        solve_named_poses(hand)          # 重新求解（约 1 分钟），结果用 tools/solve_poses.py 写回 params.json
    else:
        for name, pose in P["poses"].items():
            if not name.startswith("_"):
                POSES[name] = {f: list(v) for f, v in pose.items()}
    build_animation(hand)
    cam = setup_stage()
    aim_camera(cam, (0.22, -0.40, 0.24))
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "MILLIMETERS"
    sc.render.engine = "CYCLES"
    try:
        viewport_defaults()
    except Exception:
        pass
    return hand


def main():
    out = out_dir()
    os.makedirs(out, exist_ok=True)
    hand = build()
    write_tree(out)
    export_web(hand, out)
    bpy.context.scene.frame_set(1)
    path = os.path.join(out, "hand.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("[ok] %d 个零件 → %s" % (len(TREE), path))
    return hand


if __name__ == "__main__":
    main()
