# -*- coding: utf-8 -*-
"""第 8 步: 程序化植物 (c8x_trees.py 在云端生成的 court_plants.glb) 换掉球形树。
  1. 导入 tex/ 下的叶片卡 (本地 Z-Image 生成 + 抠图) 和树皮贴图
  2. 建材质:
     M_Foliage  遮罩 (Masked) + 双面植被着色 (TwoSidedFoliage: 逆光时叶子透光) + 轻微风动 (世界位置偏移, 越高摆得越多)
     M_Bark     按网格 UV 贴树皮
  3. 导入 court_plants.glb -> /Game/Courtyard/Plants, 给每个材质槽配材质
  4. 删掉旧的球形植物 (保留花盆和土), 按 court_plants.json 摆放
用法: py "c8_trees.py"            (c2_build.py 重建时也会自动调用 spawn())"""
import json
import math
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
ROOT = "/Game/Courtyard/Plants"
TEXDIR = ROOT + "/Tex"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
TAG = "Courtyard"
# 只摆这些种类。2026-10-18: 程序化的树/灌木/香草不好看, 先全部撤掉, 只留九重葛墙; 以后换成现成素材
ENABLED = {"BougaWall"}
LOG = []

LEAVES = {  # 槽名 -> (贴图, 颜色倍乘, 透光颜色倍乘)
    "leaf_olive": ("T_olive_leaves", (0.85, 0.98, 0.78), 0.45),
    "leaf_fig": ("T_fig_leaves", (0.95, 1.0, 0.9), 0.6),
    "leaf_lemon": ("T_lemon_leaves", (1.0, 1.0, 1.0), 0.6),
    "leaf_lavender": ("T_lavender", (1.0, 1.0, 1.0), 0.4),
    "leaf_rosemary": ("T_rosemary", (0.95, 1.0, 0.95), 0.4),
    "leaf_bouga": ("T_bouga_spray", (0.95, 0.9, 0.92), 0.6),        # 2x2 图集: 带几簇苞片的垂枝
    "leaf_bougaleaf": ("T_bouga_leaf", (0.8, 0.9, 0.75), 0.5),     # 2x2 图集: 绿叶小枝
}
BARKS = {"bark": (1.0, 1.0, 1.0), "bark_fig": (1.35, 1.35, 1.4)}


def imp_tex(name):
    dst = TEXDIR + "/" + name
    t = unreal.AssetImportTask()
    t.filename = os.path.join(D, "tex", name + ".png")
    t.destination_path = TEXDIR
    t.destination_name = name
    t.automated = True
    t.replace_existing = True
    t.save = True
    TOOLS.import_asset_tasks([t])
    return unreal.load_asset(dst)


def expr(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def scalar(m, name, val, x, y):
    e = expr(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", val)
    return e


def vec(m, name, val, x, y):
    e = expr(m, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(*val))
    return e


def mask(m, src, out, chans, x, y):
    e = expr(m, unreal.MaterialExpressionComponentMask, x, y)
    for c in "rgba":
        e.set_editor_property(c, c in chans)
    MEL.connect_material_expressions(src, out, e, "")
    return e


def binop(m, cls, a, b, x, y, a_out="", b_out=""):
    e = expr(m, cls, x, y)
    MEL.connect_material_expressions(a, a_out, e, "A")
    if isinstance(b, (int, float)):
        e.set_editor_property("const_b", float(b))
    else:
        MEL.connect_material_expressions(b, b_out, e, "B")
    return e


def new_material(name):
    path = ROOT + "/" + name
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    return TOOLS.create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())


def build_foliage(default_tex):
    m = new_material("M_Foliage")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("opacity_mask_clip_value", 0.4)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    m.set_editor_property("two_sided", False)        # 几何本身已经是正反两层 (法线同向), 材质单面即可
    tex = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1100, -200)
    tex.set_editor_property("parameter_name", "Tex")
    tex.set_editor_property("texture", default_tex)
    tint = vec(m, "Tint", (1, 1, 1, 1), -1100, 50)
    col = binop(m, unreal.MaterialExpressionMultiply, tex, tint, -800, -200, "RGB")
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(tex, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    MEL.connect_material_property(scalar(m, "Roughness", 0.7, -800, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(scalar(m, "Specular", 0.3, -800, 80), "", unreal.MaterialProperty.MP_SPECULAR)
    sss = binop(m, unreal.MaterialExpressionMultiply, col, scalar(m, "Transmission", 0.5, -1100, 150), -600, 120)
    MEL.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    # ---- 风: 偏移 = (sin(时间*速度 + 位置相位) + 0.3*sin(快)) * 幅度 * 高度权重 * 方向
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -1500, 500)
    op = expr(m, unreal.MaterialExpressionObjectPositionWS, -1500, 650)
    h = binop(m, unreal.MaterialExpressionSubtract, mask(m, wp, "", "b", -1300, 500), mask(m, op, "", "b", -1300, 650),
              -1100, 560)
    hd = binop(m, unreal.MaterialExpressionDivide, h, scalar(m, "WindHeight", 400.0, -1100, 680), -900, 560)
    w = expr(m, unreal.MaterialExpressionSaturate, -750, 560)
    MEL.connect_material_expressions(hd, "", w, "")
    xy = binop(m, unreal.MaterialExpressionAdd, mask(m, wp, "", "r", -1300, 800), mask(m, wp, "", "g", -1300, 880),
               -1100, 840)
    phase = binop(m, unreal.MaterialExpressionMultiply, xy, 0.004, -950, 840)
    t = expr(m, unreal.MaterialExpressionTime, -1300, 980)
    ts = binop(m, unreal.MaterialExpressionMultiply, t, scalar(m, "WindSpeed", 0.35, -1300, 1060), -1100, 1000)
    s1 = expr(m, unreal.MaterialExpressionSine, -750, 900)
    MEL.connect_material_expressions(binop(m, unreal.MaterialExpressionAdd, ts, phase, -900, 920), "", s1, "")
    tf = binop(m, unreal.MaterialExpressionMultiply, t, 1.7, -1100, 1120)
    ph2 = binop(m, unreal.MaterialExpressionMultiply, xy, 0.03, -950, 1120)
    s2 = expr(m, unreal.MaterialExpressionSine, -750, 1060)
    MEL.connect_material_expressions(binop(m, unreal.MaterialExpressionAdd, tf, ph2, -900, 1080), "", s2, "")
    s = binop(m, unreal.MaterialExpressionAdd, s1, binop(m, unreal.MaterialExpressionMultiply, s2, 0.3, -600, 1060),
              -450, 950)
    amp = binop(m, unreal.MaterialExpressionMultiply, s, scalar(m, "WindAmp", 3.0, -600, 1160), -300, 950)
    aw = binop(m, unreal.MaterialExpressionMultiply, amp, w, -150, 800)
    dirv = expr(m, unreal.MaterialExpressionConstant3Vector, -300, 1100)
    dirv.set_editor_property("constant", unreal.LinearColor(1.0, 0.6, 0.15, 0))
    wpo = binop(m, unreal.MaterialExpressionMultiply, aw, dirv, 0, 850)
    MEL.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def build_bark(default_tex):
    m = new_material("M_Bark")
    tc = expr(m, unreal.MaterialExpressionTextureCoordinate, -1100, -200)
    uvs = binop(m, unreal.MaterialExpressionMultiply, tc, scalar(m, "UVScale", 1.0, -1100, -80), -900, -200)
    tex = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, -200)
    tex.set_editor_property("parameter_name", "Tex")
    tex.set_editor_property("texture", default_tex)
    MEL.connect_material_expressions(uvs, "", tex, "UVs")
    col = binop(m, unreal.MaterialExpressionMultiply, tex, vec(m, "Tint", (1, 1, 1, 1), -700, 50), -400, -200, "RGB")
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(scalar(m, "Roughness", 0.85, -400, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def mi(name, parent, tex, tint, extra=None):
    path = ROOT + "/" + name
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    i = TOOLS.create_asset(name, ROOT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(i, parent)
    MEL.set_material_instance_texture_parameter_value(i, "Tex", tex)
    MEL.set_material_instance_vector_parameter_value(i, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1))
    for k, v in (extra or {}).items():
        MEL.set_material_instance_scalar_parameter_value(i, k, v)
    EAL.save_loaded_asset(i)
    return i


def build_materials():
    mats = {}
    texs = {n: imp_tex(n) for n in set(v[0] for v in LEAVES.values()) | {"T_olive_bark"}}
    fol = build_foliage(texs["T_olive_leaves"])
    bark = build_bark(texs["T_olive_bark"])
    for slot, (tn, tint, tr) in LEAVES.items():
        mats[slot] = mi("MI_" + slot, fol, texs[tn], tint, {"Transmission": tr})
    for slot, tint in BARKS.items():
        mats[slot] = mi("MI_" + slot, bark, texs["T_olive_bark"], tint)
    return mats


def import_meshes(force=False):
    """Interchange 导入是异步的: 重新导入时网格会短暂消失。所以只在没有网格 (或明确要求 reimport) 时导入。"""
    have = [p for p in EAL.list_assets(ROOT, recursive=True, include_folder=False) if "/PL_" in p]
    if force:
        # 覆盖导入不会刷新已有网格 -> 先删 Actor 和旧资产, 再导入; 导入是异步的, 这次不摆放
        remove_old()
        EAL.delete_directory(ROOT + "/court_plants")
        _import_glb()
        return {}
    if not have:
        _import_glb()
    return _find_meshes()


def _import_glb():
    t = unreal.AssetImportTask()
    t.filename = os.path.join(D, "court_plants.glb")
    t.destination_path = ROOT
    t.automated = True
    t.replace_existing = True
    t.save = True
    TOOLS.import_asset_tasks([t])


def _find_meshes():
    meshes = {}
    for path in EAL.list_assets(ROOT, recursive=True, include_folder=False):   # Interchange 会放进 court_plants/StaticMeshes 子目录
        a = EAL.load_asset(path)
        if isinstance(a, unreal.StaticMesh) and "PL_" in a.get_name():
            kind = a.get_name().split("PL_", 1)[1]
            SMES.remove_collisions(a)                  # 植物不挡人、不影响导航
            EAL.save_loaded_asset(a)
            meshes[kind] = a
    return meshes


def slot_material(slot, mats):
    s = str(slot).lower()
    for k in sorted(mats, key=len, reverse=True):
        if s.startswith(k) or k in s:
            return mats[k]
    return None


def remove_old():
    """删掉 c2_build 生成的球形树和灌木 (Plants 组), 保留花盆 (terracotta) 和盆土 (soil); 以及上次的 PL_*。"""
    n = 0
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("PL_"):
            EAS.destroy_actor(a)
            n += 1
            continue
        if not str(a.get_folder_path()).endswith("Courtyard/Plants") or not isinstance(a, unreal.StaticMeshActor):
            continue
        mat = a.static_mesh_component.get_material(0)
        mname = mat.get_name().lower() if mat else ""
        if "terracotta" in mname or "soil" in mname:
            continue
        EAS.destroy_actor(a)
        n += 1
    LOG.append("removed old plant actors: %d" % n)


def spawn(placements, meshes, mats):
    n = 0
    placements = [p for p in placements if p[0] in ENABLED]
    for i, (kind, x, y, z, s) in enumerate(placements):
        mesh = meshes.get(kind)
        if not mesh:
            LOG.append("no mesh for " + kind)
            continue
        yaw = 0.0 if kind == "BougaWall" else float((x * 37.0 + y * 91.0) * 7.3 % 360)
        a = EAS.spawn_actor_from_object(mesh, unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(0, 0, yaw))
        a.set_actor_scale3d(unreal.Vector(s, s, s))
        a.set_actor_label("PL_%s_%d" % (kind, i))
        a.set_folder_path("Courtyard/Plants")
        a.set_editor_property("tags", [unreal.Name(TAG), unreal.Name("CourtyardPlant")])
        smc = a.static_mesh_component
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        smc.set_editor_property("can_ever_affect_navigation", False)
        for j, sm in enumerate(mesh.get_editor_property("static_materials")):
            mm = slot_material(sm.get_editor_property("material_slot_name"), mats)
            if mm:
                smc.set_material(j, mm)
        n += 1
    LOG.append("plants spawned: %d" % n)


def main(placements=None):
    import sys
    meshes = import_meshes("reimport" in sys.argv)
    if not meshes:
        LOG.append("植物网格还在导入 (异步), 过几秒再运行一次 c8_trees.py")
        print(" | ".join(LOG))
        return
    remove_old()                       # 先删旧 Actor, 再重建材质 (被引用的材质删不干净)
    mats = build_materials()
    LOG.append("meshes: %s" % sorted(meshes))
    for k, mesh in meshes.items():
        LOG.append("  %s slots: %s" % (k, [str(sm.get_editor_property("material_slot_name"))
                                           for sm in mesh.get_editor_property("static_materials")]))
    if placements is None:
        placements = json.load(open(os.path.join(D, "court_plants.json"), encoding="utf-8"))["plants"]
    spawn(placements, meshes, mats)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    open(os.path.join(D, "c8_report.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    print(" | ".join(LOG))


if __name__ == "__main__":
    main()
