# -*- coding: utf-8 -*-
"""第 10 步: 用 Fab 上的免费植物素材布置院子 (方案见 植物布置方案.md)。
原则: 3/5/7 株成团、大小错开、随机朝向; 高(树) / 中(灌木) / 低(地被) 三层; 贴墙贴角种, 路线和参观点留空。
可以重复运行 (先删掉上次放的); 换随机种子: c10_plants.py seed=7      只删除: c10_plants.py clear
常春藤的叶面朝向如果反了 (贴墙那面朝外): c10_plants.py ivyflip"""
import math
import os
import random
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
TAG = "CourtFab"
LOG = []
ARGS = sys.argv[1:]
SEED = int(next((a.split("=")[1] for a in ARGS if a.startswith("seed=")), "3"))
IVY_FLIP = 180.0 if "ivyflip" in ARGS else 0.0
rng = random.Random(SEED)

FL, GR = 0.15, 0.05

PN1 = "/Game/PN_mediterraneanPlants_I/Meshes/"
PN2 = "/Game/PN_mediterraneanPlants_II/Meshes/"
MS = "/Game/Fab/Megascans/Plants/"
HB = "/Game/EuropeanHornbeam/Geometry/SimpleWind/SM_EuropeanHornbeam_"
PALM = "/Game/Palms_Pack_02/Meshes/SM_Palm_02_"


def ms(folder, mid, vars_):
    return [MS + "%s/Medium/%s_tier_2/StaticMeshes/SM_%s_Var%s" % (folder, mid, mid, v) for v in vars_]


# 键 -> 候选网格 (每次随机挑一个); 后面的 (阴影, 最远绘制距离 m) 决定性能开销
K = {
    "agave_s": ([PN1 + "agave_01", PN1 + "agave_02"], True, 35),
    "agave_m": ([PN1 + "agave_03", PN1 + "agave_04"], True, 50),
    "agave_t": ([PN1 + "agave_05", PN1 + "agave_06"], True, 60),      # 带 2 m 多高的花葶, 一组最多一棵
    "pnbush": ([PN1 + "bush_0%d" % i for i in (1, 2, 3, 4)], True, 40),
    "lowbush": ([PN2 + n for n in ("bush_01_02", "bush_01_03", "bush_01_04", "bush_02_02", "bush_02_03")], True, 35),
    "cactus_l": ([PN2 + "cactus_04", PN2 + "cactus_05"], True, 40),
    "cactus_m": ([PN2 + "cactus_02", PN2 + "cactus_03"], True, 35),
    "flower": ([PN1 + "flower_03", PN1 + "flower_04", PN1 + "flower_05", PN2 + "flower_02", PN2 + "flower_03"], False, 30),
    "grass": ([PN1 + "grass_01_0%d" % i for i in (1, 2, 3)] + [PN2 + "grass_02_0%d" % i for i in (1, 2, 3)]
              + ms("Dry_Grass_tbbqejqr", "tbbqejqr", "ABC"), False, 25),
    "sage": (ms("Sage_ve3gbfoja", "ve3gbfoja", "ACDEF"), True, 40),
    "sage_s": (ms("Sage_ve3gbfoja", "ve3gbfoja", "GH"), True, 30),
    "yucca_t": (ms("Spineless_Yucca_vljhegvha", "vljhegvha", "AD"), True, 60),
    "yucca_m": (ms("Spineless_Yucca_vljhegvha", "vljhegvha", "EFG"), True, 50),
    "ribbon": (ms("Ribbon_Grass_tbdpec3r", "tbdpec3r", "DEF"), False, 30),
    "hydrangea": (ms("Bigleaf_Hydrangea_vgztealha", "vgztealha", "EF"), True, 40),   # E/F 只有 1.5–2 万顶点, A/C/D 6–9 万太重
    "ivy_big": (ms("English_Ivy_xfcnebhqx", "xfcnebhqx", "A"), False, 40),           # 1.75 x 1.5 m 平铺片
    "ivy_mid": (ms("English_Ivy_xfcnebhqx", "xfcnebhqx", "E"), False, 40),
    "ivy_strand": (ms("English_Ivy_xfcnebhqx", "xfcnebhqx", "BCD"), False, 30),
    "hornbeam": ([HB + "Field_04"], True, 0),            # 孤植的大冠形 (原 12 m, 缩到 ~4.5 m)
    "hornbeam_s": ([HB + "Forest_09"], True, 0),
    "sapling": ([HB + "Sapling_08", HB + "Sapling_05"], True, 0),
    "palm5": ([PALM + "5"], True, 0), "palm6": ([PALM + "6"], True, 0), "palm7": ([PALM + "7"], True, 0),
    "palm9": ([PALM + "9"], True, 0),
}
NO_NANITE = [HB + "Field_04", HB + "Forest_09", HB + "Sapling_08", HB + "Sapling_05"]
CACHE = {}
PLACED = []          # (x, y, 半径) 已放的植物, 成团采样时互相避让
COUNT = {}


def mesh(path):
    if path not in CACHE:
        CACHE[path] = unreal.load_asset(path)
        if CACHE[path] is None:
            LOG.append("missing " + path)
    return CACHE[path]


def footprint(path, s):
    m = mesh(path)
    if not m:
        return 0.3
    b = m.get_bounding_box()
    return max(b.max.x - b.min.x, b.max.y - b.min.y) / 100.0 * s / 2


def put(key, x, y, z, s=1.0, yaw=None, roll=0.0, pitch=0.0, mode="b", path=None, sink=0.02):
    """mode b: 按包围盒对齐 (水平中心落在 x,y, 底面落在 z); mode p: 用网格自己的轴心 (树干底) 放在 x,y,z。"""
    cands, shadow, cull = K[key]
    path = path or rng.choice(cands)
    m = mesh(path)
    if not m:
        return None
    yaw = rng.uniform(0, 360) if yaw is None else yaw
    a = EAS.spawn_actor_from_object(m, unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(roll, pitch, -yaw))
    a.set_actor_scale3d(unreal.Vector(s, s, s))
    o, e = a.get_actor_bounds(False)
    loc = a.get_actor_location()
    if mode == "b":
        loc = unreal.Vector(loc.x + (x * 100 - o.x), loc.y + (-y * 100 - o.y), loc.z + (z * 100 - (o.z - e.z)) - sink * 100)
        a.set_actor_location(loc, False, False)
    else:
        LOG.append("%s pivot->bounds centre offset %.2f m, base %.2f m" % (
            key, math.hypot(o.x - loc.x, o.y - loc.y) / 100.0, (o.z - e.z - loc.z) / 100.0))
    smc = a.static_mesh_component
    smc.set_mobility(unreal.ComponentMobility.MOVABLE)          # 烘焙光照下植物用动态阴影 (会随风动)
    smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    smc.set_editor_property("can_ever_affect_navigation", False)
    smc.set_cast_shadow(shadow)
    if cull:
        smc.set_editor_property("ld_max_draw_distance", cull * 100.0)
    a.set_editor_property("tags", [unreal.Name(TAG), unreal.Name("CourtyardPlant")])
    a.set_folder_path("Courtyard/PlantsFab")
    COUNT[key] = COUNT.get(key, 0) + 1
    a.set_actor_label("FP_%s_%d" % (key, COUNT[key]))
    PLACED.append((x, y, footprint(path, s) * 0.6))
    return a


def clump(region, z, items, smin=0.8, smax=1.2, avoid=()):
    """region: ("c", cx, cy, r[, rmin]) 圆 / 环;  ("r", x0, x1, y0, y1) 矩形。items: 键列表, 每个放一株。
    大的先放; 每株找一个跟已放植物不太挤的点 (试 60 次, 最后退而求其次)。"""
    keys = sorted(items, key=lambda k: -footprint(K[k][0][0], 1.0))
    for k in keys:
        path = rng.choice(K[k][0])
        s = rng.uniform(smin, smax)
        r = footprint(path, s)
        best, bestd = None, -1e9
        for _ in range(60):
            if region[0] == "c":
                rmin = region[4] if len(region) > 4 else 0.0
                ang, rad = rng.uniform(0, 2 * math.pi), math.sqrt(rng.uniform((rmin / region[3]) ** 2, 1)) * region[3]
                px, py = region[1] + rad * math.cos(ang), region[2] + rad * math.sin(ang)
            else:
                px, py = rng.uniform(region[1], region[2]), rng.uniform(region[3], region[4])
            if any(ax0 <= px <= ax1 and ay0 <= py <= ay1 for ax0, ax1, ay0, ay1 in avoid):
                continue
            d = min([math.hypot(px - qx, py - qy) - (r * 0.6 + qr) for qx, qy, qr in PLACED] or [9])
            if d > bestd:
                best, bestd = (px, py), d
            if d > 0:
                break
        if best:
            put(k, best[0], best[1], z, s, path=path)


def along(x0, y0, x1, y1, z, items, jit=0.12, smin=0.8, smax=1.2):
    """沿墙脚一条线随机撒 (不是等距)。"""
    ts = sorted(rng.uniform(0.05, 0.95) for _ in items)
    for k, t in zip(items, ts):
        put(k, x0 + (x1 - x0) * t + rng.uniform(-jit, jit), y0 + (y1 - y0) * t + rng.uniform(-jit, jit), z, rng.uniform(smin, smax))


FACE_YAW = {"+y": 0.0, "-y": 180.0, "+x": -90.0, "-x": 90.0}     # 平面图里墙面朝向 (指向院子) -> 绕竖轴转多少


def ivy(key, x, y, z, face, s=1.0):
    """常春藤: 平铺片立起来贴墙 (x, y 是墙面上的点)。条状的 (ivy_strand) 本来就是竖的。"""
    nx, ny = {"+y": (0, 1), "-y": (0, -1), "+x": (1, 0), "-x": (-1, 0)}[face]
    off = 0.08 * s
    if key == "ivy_strand":
        return put(key, x + nx * 0.04, y + ny * 0.04, z, s, yaw=FACE_YAW[face], sink=0.0)
    return put(key, x + nx * off, y + ny * off, z, s, yaw=FACE_YAW[face] + IVY_FLIP, roll=90.0, sink=0.0)


def pot(x, y, z, d=0.6, h=0.5):
    """陶盆 (引擎自带圆柱 + 院子的陶土材质), 返回盆土高度。"""
    cyl = unreal.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")
    for dd, hh, mat in ((d, h, "terracotta"), (d * 0.86, h + 0.01, "soil")):
        a = EAS.spawn_actor_from_object(cyl, unreal.Vector(x * 100, -y * 100, (z + hh / 2) * 100), unreal.Rotator(0, 0, 0))
        a.set_actor_scale3d(unreal.Vector(dd, dd, hh))
        a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)   # 不进烘焙, 加盆不用重新烘焙光照
        mi = unreal.load_asset("/Game/Courtyard/Materials/MI_C_" + mat)
        if mi:
            a.static_mesh_component.set_material(0, mi)
        a.set_editor_property("tags", [unreal.Name(TAG)])
        a.set_folder_path("Courtyard/PlantsFab")
        a.set_actor_label("FP_pot")
    return z + h


def no_nanite():
    """Hornbeam 默认开 Nanite; VR 用 forward 渲染, 关掉改用它自带的 LOD (更稳)。"""
    smes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for p in NO_NANITE:
        m = mesh(p)
        if not m:
            continue
        ns = m.get_editor_property("nanite_settings")
        if not ns.get_editor_property("enabled"):
            continue
        ns.set_editor_property("enabled", False)
        try:
            smes.set_nanite_settings(m, ns, True)
        except Exception:
            m.set_editor_property("nanite_settings", ns)
        EAL.save_loaded_asset(m)
        LOG.append("nanite off: " + p.split("/")[-1])


def clear():
    n = 0
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if TAG in tags or "CourtLineup" in tags:
            EAS.destroy_actor(a)
            n += 1
    LOG.append("removed %d old actors" % n)


# ------------------------------------------------------------------ 布置
def layout():
    # ① 主树院 (x 4.0–9.35, y 10.5–17.5): 鹅耳枥 1 棵靠西, 树冠盖住一半院子; 东墙两团鼠尾草; 西墙常春藤
    #    路线: 平台开口 (x 6–7.5) -> 踏步石 (x ~6.7) -> 南边石凳, 所以 x 5.9–7.6 中间留空
    put("hornbeam", 5.5, 14.4, GR, 0.38, yaw=0, mode="p")
    clump(("c", 5.0, 14.4, 0.75, 0.25), GR, ["grass"] * 4 + ["lowbush"] * 2 + ["flower"])
    clump(("c", 8.6, 12.4, 0.6), GR, ["sage"] * 3 + ["pnbush"] * 2)
    clump(("c", 8.6, 16.6, 0.55), GR, ["sage", "sage", "agave_m", "grass", "grass"])
    clump(("c", 4.45, 11.65, 0.25), GR, ["grass", "grass"])
    along(4.3, 17.25, 5.7, 17.25, GR, ["grass", "grass", "flower"])
    ivy("ivy_big", 4.0, 16.4, GR, "+x", 1.0)
    ivy("ivy_strand", 4.0, 12.7, GR, "+x", 1.8)
    ivy("ivy_strand", 4.0, 13.05, GR, "+x", 1.5)
    ivy("ivy_mid", 9.35, 15.1, GR, "-x", 1.2)

    # ② 水渠窄院 (x 9.65–11.35): 尽头一对丝兰 (从平台往南看是一条对称的透视线), 渠边零星 Ribbon Grass
    for x in (9.98, 11.02):
        put("yucca_t", x, 17.15, GR + 0.03, 0.6, path=K["yucca_t"][0][0])
    for x, y in ((9.86, 12.4), (9.86, 12.8), (9.86, 15.1), (11.14, 13.7), (11.14, 15.7), (11.14, 16.05)):
        put("ribbon", x, y, GR + 0.03, rng.uniform(0.65, 0.85))

    # ③ 香草厨园: 4 个种植池 (池土顶 0.52 m), 每池一团, 不排方阵
    Z = 0.52
    # 香草池要"满": 每池 7–9 株, 叶子盖住土; 池土内沿 x0+0.1..x1-0.1
    clump(("r", 12.25, 13.45, 11.7, 13.05), Z, ["sage"] * 6 + ["sage_s"] * 2, 0.95, 1.25)
    clump(("r", 15.15, 16.35, 11.7, 13.05), Z, ["flower"] * 6 + ["pnbush"] * 2 + ["lowbush"], 1.0, 1.25)
    clump(("r", 12.25, 13.45, 14.75, 16.3), Z, ["pnbush"] * 4 + ["lowbush"] * 3 + ["sage_s"] * 2, 1.0, 1.3)
    clump(("r", 15.15, 16.35, 14.75, 16.3), Z, ["sage"] * 5 + ["sage_s"] * 2 + ["flower"], 0.95, 1.25)
    for x, y in ((11.9, 17.25), (16.75, 17.25), (16.75, 10.8), (13.6, 10.8)):
        clump(("c", x, y, 0.15), GR, ["grass", "grass"])

    # ④ 主卧私院: 九重葛墙保留 (c8_trees.py); 两个陶盆种绣球, 放在不挡门的两个角
    for x, y in ((4.8, 7.15), (8.4, 9.65)):
        put("hydrangea", x, y, pot(x, y, FL) - 0.02, rng.uniform(0.65, 0.75))

    # ⑤ 次卧私院 (碎石 0.12 m): 西北角一组干景 (丝兰 + 龙舌兰 + 干草), 另两个角零星
    Z = GR + 0.07
    clump(("c", 5.25, 5.55, 0.85), Z, ["yucca_t", "yucca_m", "agave_m", "agave_s", "lowbush", "grass", "grass", "grass"])
    clump(("c", 8.4, 6.05, 0.3), Z, ["agave_s", "grass"])
    clump(("c", 4.6, 3.05, 0.25), Z, ["grass", "grass"])

    # ⑥ 入口长巷 (x 21–30, y 7.1–10.1): 北边 3 个陶罐里种鼠尾草; 南墙脚两团干草野花; 南墙常春藤
    for x in (23.0, 25.5, 28.0):
        put("sage", x, 9.95, GR + 0.7 - 0.02, rng.uniform(0.7, 0.8))
    clump(("r", 21.6, 23.4, 7.25, 7.45), GR, ["grass", "grass", "grass", "flower"])
    clump(("r", 26.2, 27.6, 7.25, 7.45), GR, ["grass", "grass", "lowbush"])
    ivy("ivy_big", 24.7, 7.1, GR, "+y", 1.0)
    ivy("ivy_mid", 28.9, 7.1, GR, "+y", 1.1)
    ivy("ivy_strand", 22.5, 7.1, GR, "+y", 1.7)

    # ⑦ 门院 (x 30–33, y 7–10.5): 石水钵西边一组仙人掌 + 龙舌兰; 西北角一棵开花龙舌兰; 中间和门洞留空
    clump(("c", 31.25, 7.35, 0.33), GR, ["cactus_l", "cactus_m", "agave_s", "grass"])
    clump(("c", 32.85, 7.2, 0.12), GR, ["cactus_m", "grass"])
    clump(("c", 30.35, 10.15, 0.28), GR, ["agave_t", "grass", "cactus_m"])

    # ⑧ 柠檬巷: 3 个现成的陶盆 (盆土 0.63 m) 种小树苗, 代替柠檬树
    for y in (11.5, 13.0, 14.5):
        put("sapling", 30.5, y, FL - 0.05 + 0.53, rng.uniform(1.0, 1.15))

    # A 泳池平台的两个种植池 (土顶 0.17 m): 西边一棵小鹅耳枥 + 干草, 东边龙舌兰干景
    put("hornbeam_s", 9.1, 19.35, FL + 0.02, 0.55, mode="p")
    clump(("r", 7.75, 10.45, 18.7, 20.0), FL + 0.02, ["grass"] * 4 + ["lowbush"] * 2, avoid=[(8.7, 9.5, 19.0, 19.7)])
    clump(("r", 14.35, 17.05, 18.75, 19.95), FL + 0.02, ["agave_t", "agave_m", "agave_m", "agave_s", "agave_s", "grass", "grass", "grass"])

    # 海边草地: 3 棵加那利海枣, 从客厅 (25.5, 13) 往海看时分在视野两边, 中间 x 14–34 不种高的
    for key, x, y in (("palm5", 10.6, 26.3), ("palm7", 8.0, 27.6), ("palm6", 37.6, 25.3)):
        put(key, x, y, 0.0, 1.0, mode="p")
    clump(("c", 10.6, 26.3, 1.0, 0.45), 0.02, ["agave_m", "pnbush", "grass", "grass", "grass"])
    clump(("c", 8.0, 27.6, 0.8, 0.4), 0.02, ["lowbush", "lowbush", "grass", "grass"])
    clump(("c", 37.6, 25.3, 0.9, 0.45), 0.02, ["agave_m", "agave_s", "grass", "grass", "grass"])
    for x, y in ((2.5, 28.0), (31.5, 28.1), (42.0, 27.8)):
        clump(("c", x, y, 0.5), 0.02, ["grass", "grass", "grass"])

    # G 访客停车: 门洞外两侧一对丝兰 (进门前的"门框"); 北头一棵矮海枣 + 龙舌兰
    for y in (7.45, 9.55):
        put("yucca_t", 33.8, y, GR, 0.7, path=K["yucca_t"][0][0])
    put("palm9", 36.7, 8.4, GR, 1.0, mode="p")
    clump(("c", 36.7, 8.4, 0.9, 0.4), GR, ["agave_m", "agave_s", "agave_s", "grass", "grass", "grass"])


def main():
    clear()
    if "clear" not in ARGS:
        no_nanite()
        layout()
        LOG.append("placed: " + ", ".join("%s %d" % kv for kv in sorted(COUNT.items())))
        LOG.append("total %d plants (seed %d)" % (sum(COUNT.values()), SEED))
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    open(os.path.join(D, "c10_report.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    print(" | ".join(LOG))


if __name__ == "__main__":
    main()
