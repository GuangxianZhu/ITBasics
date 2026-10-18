# -*- coding: utf-8 -*-
"""
第 7 步: PBR 材质升级 (换掉只有颜色+粗糙度的程序贴图)。
  1) 在你电脑上从 ambientCG 下载 CC0 贴图 (CC0 = 公共领域, 可商用、不用署名), 2K JPG:
     颜色 Color / 法线 NormalDX (UE 用 DirectX 法线) / 粗糙度 Roughness
  2) 新母材质 M_CourtPBR: 世界坐标三向投影 (和以前一样, 合并网格不用 UV 也能贴), 加上
     - 世界空间法线 (WorldAlignedNormal) -> 表面有凹凸, 灯光掠过时能看出石缝、木纹
     - 大尺度明暗变化: 同一张颜色图放大 6 倍再采一次当"污渍/色差"遮罩 -> 一面墙不再完全重复
  3) 每种表面一个材质实例 MI_P_<名字>, 直接替换场景里合并网格的材质; c2_build.py 重跑时也会优先用它们。
用法: py "c7_pbr.py"          (下载 + 建材质 + 替换)
      py "c7_pbr.py" nodl    (不下载, 只重建材质)
结果写 c7_report.txt
"""
import json
import os
import sys
import urllib.request
import zipfile

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
PBR = os.path.join(D, "pbr")
TEXDIR, MATDIR = "/Game/Courtyard/PBR/Textures", "/Game/Courtyard/PBR"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
log = []

# 表面 -> (ambientCG 搜索词, 指定 ID 或 None, 平铺米数, 颜色乘数, 粗糙度乘数, 变化强度)
SURF = {
    "white":    ("plaster", "Plaster001", 2.0, (1.08, 1.06, 1.03), 1.0, 0.25),
    "white_in": ("plaster", "Plaster001", 2.0, (1.02, 0.99, 0.95), 1.0, 0.15),
    "stone":    ("stone wall", "Rocks011", 2.5, (1.05, 1.0, 0.92), 1.0, 0.25),     # 干砌片石墙
    "terrace":  ("limestone", "Tiles142", 2.4, (1.05, 1.03, 1.0), 1.0, 0.2),       # 大块石灰华石板
    "coping":   ("limestone", "Tiles139", 1.2, (1.1, 1.08, 1.04), 0.9, 0.15),
    "wood":     ("wood floor", None, 2.4, (1.0, 1.0, 1.0), 0.9, 0.2),
    "teak":     ("planks", None, 2.0, (0.95, 0.85, 0.75), 1.0, 0.25),
    "gravel":   ("gravel", "Ground079S", 1.5, (1.05, 1.0, 0.95), 1.0, 0.3),
    "concrete": ("concrete", None, 2.5, (1.0, 1.0, 1.0), 1.0, 0.3),
    "rock":     ("rock", "Rock051", 5.0, (1.0, 1.0, 1.0), 1.0, 0.3),
    "marble":   ("marble", None, 1.5, (1.0, 1.0, 1.0), 0.8, 0.1),
    "pooltile": ("tiles", None, 0.8, (0.7, 0.9, 1.0), 0.8, 0.1),
}


def api(q, aid):
    base = "https://ambientcg.com/api/v2/full_json?type=Material&include=downloadData&limit=6&sort=Popular"
    url = base + ("&id=" + aid if aid else "&q=" + urllib.parse.quote(q))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UE court builder)"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))


def download(key, q, aid):
    dst = os.path.join(PBR, aid or key)
    if os.path.isdir(dst) and any(f.lower().endswith((".jpg", ".png")) for f in os.listdir(dst)):
        return dst
    os.makedirs(dst, exist_ok=True)
    data = api(q, aid)
    if aid and not data.get("foundAssets"):
        data = api(q, None)
    for asset in data.get("foundAssets", []):
        cats = asset.get("downloadFolders", {}).get("default", {}).get("downloadFiletypeCategories", {})
        for d in cats.get("zip", {}).get("downloads", []):
            if d.get("attribute") == "2K-JPG":
                zp = os.path.join(dst, "tex.zip")
                req = urllib.request.Request(d["downloadLink"], headers={"User-Agent": "Mozilla/5.0"})
                open(zp, "wb").write(urllib.request.urlopen(req, timeout=120).read())
                zipfile.ZipFile(zp).extractall(dst)
                os.remove(zp)
                log.append("%s <- ambientCG %s (CC0)" % (key, asset.get("assetId")))
                open(os.path.join(dst, "SOURCE.txt"), "w").write("ambientCG %s CC0 https://ambientcg.com/a/%s\n" % (asset.get("assetId"), asset.get("assetId")))
                return dst
    log.append("WARN no 2K-JPG for %s (%s)" % (key, q))
    return None


def find(folder, *tags):
    for f in sorted(os.listdir(folder)):
        fl = f.lower()
        if fl.endswith((".jpg", ".png")) and all(t.lower() in fl for t in tags):
            return os.path.join(folder, f)
    return None


def imp(path, name, kind):
    dst = TEXDIR + "/" + name
    if not EAL.does_asset_exist(dst):
        t = unreal.AssetImportTask()
        t.filename = path
        t.destination_path = TEXDIR
        t.destination_name = name
        t.automated = True
        t.replace_existing = True
        t.save = False
        TOOLS.import_asset_tasks([t])
    a = unreal.load_asset(dst)
    if a and kind == "normal":
        a.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        a.set_editor_property("srgb", False)
    if a:
        EAL.save_loaded_asset(a)
    return a


def expr(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def scalar(m, name, val, x, y):
    e = expr(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", val)
    return e


def build_master():
    path = MATDIR + "/M_CourtPBR"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    m = TOOLS.create_asset("M_CourtPBR", MATDIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("tangent_space_normal", False)       # WorldAlignedNormal 输出的是世界空间法线
    wat = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions01/Texturing/WorldAlignedTexture")
    wan = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions01/Texturing/WorldAlignedNormal")
    tile = scalar(m, "TileCM", 200.0, -1200, 0)

    def tobj(name, default, x, y, normal=False):
        to = expr(m, unreal.MaterialExpressionTextureObjectParameter, x, y)
        to.set_editor_property("parameter_name", name)
        to.set_editor_property("texture", unreal.load_asset(default))
        if normal:
            to.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        return to

    def call(fn, to, size, x, y):
        fc = expr(m, unreal.MaterialExpressionMaterialFunctionCall, x, y)
        fc.set_editor_property("material_function", fn)
        MEL.connect_material_expressions(to, "", fc, "TextureObject")
        MEL.connect_material_expressions(size, "", fc, "TextureSize")
        return fc

    alb = tobj("Albedo", "/Engine/EngineResources/DefaultTexture", -1200, -400)
    rgh = tobj("Rough", "/Engine/EngineResources/DefaultTexture", -1200, 200)
    nrm = tobj("Normal", "/Engine/EngineMaterials/DefaultNormal", -1200, 500, normal=True)
    c_alb = call(wat, alb, tile, -800, -400)
    c_rgh = call(wat, rgh, tile, -800, 200)
    c_nrm = call(wan, nrm, tile, -800, 500)
    # 大尺度变化: 颜色图放大 6 倍再采一次, 取 R 通道当遮罩
    big = expr(m, unreal.MaterialExpressionMultiply, -1000, -150)
    MEL.connect_material_expressions(tile, "", big, "A")
    big.set_editor_property("const_b", 6.0)
    c_var = call(wat, alb, big, -800, -150)
    vmask = expr(m, unreal.MaterialExpressionComponentMask, -500, -150)
    vmask.set_editor_property("r", True)
    for c in ("g", "b", "a"):
        vmask.set_editor_property(c, False)
    MEL.connect_material_expressions(c_var, "XYZ Texture", vmask, "")
    vs = scalar(m, "VarStrength", 0.25, -500, 0)
    lerp = expr(m, unreal.MaterialExpressionLinearInterpolate, -300, -150)
    MEL.connect_material_expressions(vmask, "", lerp, "Alpha")
    one_minus = expr(m, unreal.MaterialExpressionOneMinus, -450, 60)
    MEL.connect_material_expressions(vs, "", one_minus, "")
    MEL.connect_material_expressions(one_minus, "", lerp, "A")
    plus = expr(m, unreal.MaterialExpressionAdd, -450, 120)
    MEL.connect_material_expressions(vs, "", plus, "A")
    plus.set_editor_property("const_b", 1.0)
    MEL.connect_material_expressions(plus, "", lerp, "B")
    tint = expr(m, unreal.MaterialExpressionVectorParameter, -500, -500)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    m1 = expr(m, unreal.MaterialExpressionMultiply, -300, -400)
    MEL.connect_material_expressions(c_alb, "XYZ Texture", m1, "A")
    MEL.connect_material_expressions(tint, "", m1, "B")
    m2 = expr(m, unreal.MaterialExpressionMultiply, -100, -300)
    MEL.connect_material_expressions(m1, "", m2, "A")
    MEL.connect_material_expressions(lerp, "", m2, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rmask = expr(m, unreal.MaterialExpressionComponentMask, -500, 200)
    rmask.set_editor_property("r", True)
    for c in ("g", "b", "a"):
        rmask.set_editor_property(c, False)
    MEL.connect_material_expressions(c_rgh, "XYZ Texture", rmask, "")
    # 粗糙度贴图按 sRGB 导入了, 采样值≈原值^2.2 (偏小→偏亮滑), 这里开 1/2.2 次方还原
    rpow = expr(m, unreal.MaterialExpressionPower, -400, 200)
    rpow.set_editor_property("const_exponent", 0.4545)
    MEL.connect_material_expressions(rmask, "", rpow, "Base")
    rmul = expr(m, unreal.MaterialExpressionMultiply, -300, 250)
    MEL.connect_material_expressions(rpow, "", rmul, "A")
    MEL.connect_material_expressions(scalar(m, "RoughMul", 1.0, -500, 320), "", rmul, "B")
    MEL.connect_material_property(rmul, "", unreal.MaterialProperty.MP_ROUGHNESS)
    # 2026-10-18: WorldAlignedNormal 在朝下的面 (天花板) 给出朝上的法线 -> 顶灯周围黑圈; 镜像回几何法线同侧 (见 c14_ceiling_normal.py)
    from c14_ceiling_normal import add_hemisphere_fix
    MEL.connect_material_property(add_hemisphere_fix(m, c_nrm, "XYZ Texture"), "", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(scalar(m, "Metallic", 0.0, -300, 400), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def main():
    nodl = len(sys.argv) > 1 and sys.argv[1] == "nodl"
    master = build_master()
    made = {}
    for key, (q, aid, tile_m, tint, rmul, var) in SURF.items():
        folder = os.path.join(PBR, aid or key)
        if not nodl:
            try:
                folder = download(key, q, aid) or folder
            except Exception as e:
                log.append("WARN download %s: %s" % (key, e))
        if not os.path.isdir(folder):
            continue
        col, nor, rou = find(folder, "_color"), find(folder, "_normaldx"), find(folder, "_roughness")
        if not col:
            log.append("WARN %s: no color map" % key)
            continue
        tid = aid or key
        ta = imp(col, "T_%s_C" % tid, "color")
        tn = imp(nor, "T_%s_N" % tid, "normal") if nor else None
        tr = imp(rou, "T_%s_R" % tid, "rough") if rou else None
        path = MATDIR + "/MI_P_" + key
        mi = unreal.load_asset(path) if EAL.does_asset_exist(path) else TOOLS.create_asset(
            "MI_P_" + key, MATDIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, master)
        MEL.set_material_instance_scalar_parameter_value(mi, "TileCM", tile_m * 100)
        MEL.set_material_instance_scalar_parameter_value(mi, "RoughMul", rmul)
        MEL.set_material_instance_scalar_parameter_value(mi, "VarStrength", var)
        MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1))
        MEL.set_material_instance_texture_parameter_value(mi, "Albedo", ta)
        if tn:
            MEL.set_material_instance_texture_parameter_value(mi, "Normal", tn)
        if tr:
            MEL.set_material_instance_texture_parameter_value(mi, "Rough", tr)
        EAL.save_loaded_asset(mi)
        made[key] = mi
    # 替换场景里合并网格 (G_<区域>__<材质>) 的材质
    n = 0
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if not lab.startswith("G_"):
            continue
        parts = lab[2:].split("__")
        if len(parts) >= 2 and parts[1] in made:
            c = a.static_mesh_component
            for i in range(c.get_num_materials()):
                c.set_material(i, made[parts[1]])
            n += 1
    log.append("PBR materials: %s; actors updated: %d" % (sorted(made), n))
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    open(os.path.join(D, "c7_report.txt"), "w", encoding="utf-8").write("\n".join(log))
    print(" | ".join(log))


main()
