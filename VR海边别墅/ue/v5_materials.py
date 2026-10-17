# -*- coding: utf-8 -*-
"""
第 5 步: 材质
原理:
  Blender 导出的模型几乎没有 UV (539 个面组里只有 5 个有 UV), Godot 版用的是"世界坐标三向投影":
  按物体表面在世界里的位置和朝向, 从 X/Y/Z 三个方向把贴图"投"上去, 再按法线混合。
  UE 里用引擎自带的材质函数 WorldAlignedTexture 做同样的事, 贴图按"厘米"平铺, 任何尺寸的墙密度一致。
  - 母材质 M_VillaTriplanar: 参数 Albedo/Rough 贴图, TileCM (多少厘米铺一张), Tint, RoughMul
  - 每种表面一个材质实例 (对照 Godot main.gd 的 _build_materials)
  - 玻璃: 半透明 + 双面; 海水/泳池水: 简化的光滑水面 (没有起伏, 看房版够用)
  - 灯带/灯罩: 自发光
  - 画: 用贴图 UV
  没做 (v1): 法线贴图 (WorldAlignedNormal 要切到世界空间法线, 先不冒险), 海浪动画。
"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
TEX_SRC = "C:/work/ITBasics/VR海边别墅/godot/model/tex"
MAT_DIR, TEX_DIR = "/Game/Villa/Materials", "/Game/Villa/Textures"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
log = []

# ---------------------------------------------------------------- 对照表 (Godot main.gd)
# 中文材质名: (贴图组, 平铺米数, 颜色乘数, 粗糙度乘数)
TRIPLANAR = {
    "白墙": ("plaster", 2.0, (1, 1, 1), 1.0),
    "清水混凝土": ("concrete", 2.0, (1, 1, 1), 1.0),
    "室内木地板": ("wood_floor", 2.4, (1, 1, 1), 1.0),
    "阳台石材": ("stone_tile", 1.2, (1, 1, 1), 1.0),
    "泳池条石": ("pool_stone", 1.2, (1, 1, 1), 1.0),
    "抛光地砖": ("porcelain", 1.6, (1, 1, 1), 1.0),
    "大理石": ("marble", 1.2, (1, 1, 1), 1.0),
    "露台石材": ("stone_tile", 1.2, (0.82, 0.82, 0.80), 1.0),
    "海堤毛石": ("seawall", 3.0, (1, 1, 1), 1.0),
    "草坪": ("grass", 3.0, (1, 1, 1), 1.0),
    "海岬草地": ("grass", 3.0, (0.9, 0.9, 0.85), 1.0),
    "山林": ("forest", 40.0, (1, 1, 1), 1.0),
    "树冠": ("forest", 9.0, (1.15, 1.15, 1.1), 1.0),
    "岩石": ("rock", 3.0, (1, 1, 1), 1.0),
    "沙滩": ("sand", 3.0, (1, 1, 1), 1.0),
    "椰树干": ("bark", 1.5, (1, 1, 1), 1.0),
    "沙发布": ("fabric", 0.4, (1.0, 0.97, 0.9), 1.0),
    "地毯": ("fabric", 0.25, (0.9, 0.82, 0.7), 1.0),
}
AI_TILE = {"fabric": 0.4, "marble": 1.0, "wood_floor": 1.2}


def tex(name):
    path = TEX_DIR + "/" + name
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    t = unreal.AssetImportTask()
    t.filename = TEX_SRC + "/" + name + ".png"
    t.destination_path = TEX_DIR
    t.automated = True
    t.replace_existing = True
    t.save = False
    tools.import_asset_tasks([t])
    a = unreal.load_asset(path)
    if a is None:
        log.append("WARN texture import failed: " + name)
        return None
    if name.endswith("_normal"):
        a.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        a.set_editor_property("srgb", False)
    # 粗糙度贴图保持 sRGB (和母材质参数默认贴图的采样类型一致, 否则材质编译报"采样器类型不匹配");
    # 代价是粗糙度曲线略有偏差, 用 RoughMul 补
    EAL.save_loaded_asset(a)
    return a


def new_material(name):
    path = MAT_DIR + "/" + name
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    return tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())


def expr(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def scalar(m, name, val, x, y):
    e = expr(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", val)
    return e


def vec(m, name, rgb, x, y):
    e = expr(m, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    return e


def build_triplanar():
    m = new_material("M_VillaTriplanar")
    wat = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions01/Texturing/WorldAlignedTexture")
    tile = scalar(m, "TileCM", 200.0, -900, 0)
    outs = {}
    for i, (pname, default) in enumerate((("Albedo", "/Engine/EngineResources/DefaultTexture"),
                                          ("Rough", "/Engine/EngineResources/DefaultTexture"))):
        to = expr(m, unreal.MaterialExpressionTextureObjectParameter, -900, -300 + i * 300)
        to.set_editor_property("parameter_name", pname)
        to.set_editor_property("texture", unreal.load_asset(default))
        fc = expr(m, unreal.MaterialExpressionMaterialFunctionCall, -500, -300 + i * 300)
        fc.set_editor_property("material_function", wat)
        ok1 = MEL.connect_material_expressions(to, "", fc, "TextureObject")
        ok2 = MEL.connect_material_expressions(tile, "", fc, "TextureSize")
        log.append("triplanar {} connect tex={} size={}".format(pname, ok1, ok2))
        outs[pname] = fc
    tint = vec(m, "Tint", (1, 1, 1), -500, 300)
    mul = expr(m, unreal.MaterialExpressionMultiply, -200, -300)
    MEL.connect_material_expressions(outs["Albedo"], "XYZ Texture", mul, "A")
    MEL.connect_material_expressions(tint, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mask = expr(m, unreal.MaterialExpressionComponentMask, -200, 0)
    for c in ("r",):
        mask.set_editor_property(c, True)
    for c in ("g", "b", "a"):
        mask.set_editor_property(c, False)
    MEL.connect_material_expressions(outs["Rough"], "XYZ Texture", mask, "")
    rmul = expr(m, unreal.MaterialExpressionMultiply, 0, 0)
    rm = scalar(m, "RoughMul", 1.0, -200, 150)
    MEL.connect_material_expressions(mask, "", rmul, "A")
    MEL.connect_material_expressions(rm, "", rmul, "B")
    MEL.connect_material_property(rmul, "", unreal.MaterialProperty.MP_ROUGHNESS)
    met = scalar(m, "Metallic", 0.0, -200, 300)
    MEL.connect_material_property(met, "", unreal.MaterialProperty.MP_METALLIC)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def build_simple(name, color, rough=0.5, metal=0.0, spec=0.5, opacity=None, emissive=0.0, two_sided=False):
    m = new_material(name)
    c = vec(m, "Color", color, -400, 0)
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(scalar(m, "Roughness", rough, -400, 150), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(scalar(m, "Metallic", metal, -400, 250), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(scalar(m, "Specular", spec, -400, 350), "", unreal.MaterialProperty.MP_SPECULAR)
    if opacity is not None:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        for mode in ("TLM_SURFACE_PER_PIXEL_LIGHTING", "TLM_SURFACE_FORWARD_SHADING"):
            if hasattr(unreal.TranslucencyLightingMode, mode):  # 表面逐像素光照: 玻璃上有高光反射
                m.set_editor_property("translucency_lighting_mode", getattr(unreal.TranslucencyLightingMode, mode))
                break
        MEL.connect_material_property(scalar(m, "Opacity", opacity, -400, 450), "", unreal.MaterialProperty.MP_OPACITY)
    if emissive > 0:
        em = expr(m, unreal.MaterialExpressionMultiply, -150, 550)
        MEL.connect_material_expressions(c, "", em, "A")
        MEL.connect_material_expressions(scalar(m, "Emissive", emissive, -400, 550), "", em, "B")
        MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property("two_sided", two_sided)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def build_painting():
    m = new_material("M_VillaPainting")
    ts = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -400, 0)
    ts.set_editor_property("parameter_name", "Tex")
    ts.set_editor_property("texture", unreal.load_asset("/Engine/EngineResources/DefaultTexture"))
    MEL.connect_material_property(ts, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(scalar(m, "Roughness", 0.8, -400, 250), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def instance(parent, name, scalars=None, vectors=None, textures=None):
    path = MAT_DIR + "/" + name
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(v[0], v[1], v[2], 1))
    for k, v in (textures or {}).items():
        if v:
            MEL.set_material_instance_texture_parameter_value(mi, k, v)
    EAL.save_loaded_asset(mi)
    return mi


def main():
    names = json.load(open(os.path.join(D, "names.json"), encoding="utf-8"))["materials"]   # ascii -> 中文
    cn2ascii = {v: k for k, v in names.items()}
    meta = json.load(open("C:/work/ITBasics/VR海边别墅/godot/model/villa_meta.json", encoding="utf-8"))
    tri = build_triplanar()
    override = {}  # ascii 材质名 -> 新材质

    def tri_inst(key, texset, tile_m, tint, rough_mul=1.0, metal=0.0):
        return instance(tri, "MI_" + key, {"TileCM": tile_m * 100.0, "RoughMul": rough_mul, "Metallic": metal},
                        {"Tint": tint}, {"Albedo": tex(texset + "_albedo"), "Rough": tex(texset + "_rough")})

    for cn, (ts, tile, tint, rm) in TRIPLANAR.items():
        if cn in cn2ascii:
            a = cn2ascii[cn]
            override[a] = tri_inst(a, ts, tile, tint, rm)
    for k, am in meta.get("ai_materials", {}).items():
        a = "M_" + k
        if a in names and am.get("tex"):
            col = [c * 1.25 for c in am.get("color", [0.7, 0.7, 0.7])]
            # 贴图本身的粗糙度 * 系数 ≈ Godot 里的 roughness 值
            override[a] = tri_inst(a, am["tex"], AI_TILE.get(am["tex"], 1.0), col, am.get("rough", 0.6) * 1.4,
                                   am.get("metal", 0.0))
    glass = build_simple("M_VillaGlass", (0.78, 0.9, 0.92), rough=0.03, spec=0.9, opacity=0.15, two_sided=True)
    dark_glass = build_simple("M_VillaDarkGlass", (0.05, 0.07, 0.08), rough=0.05, spec=0.9, opacity=0.6, two_sided=True)
    sea = build_simple("M_VillaSea", (0.015, 0.09, 0.12), rough=0.06, spec=0.8)
    pool = build_simple("M_VillaPoolWater", (0.12, 0.58, 0.66), rough=0.02, spec=0.8, opacity=0.55)
    lamp = build_simple("M_VillaLamp", (1.0, 0.82, 0.6), rough=0.9, emissive=4.0)
    lh = build_simple("M_VillaLighthouseGlass", (0.95, 0.92, 0.7), rough=0.3, emissive=2.0)
    for cn, mat in (("玻璃", glass), ("深色玻璃", dark_glass), ("海水", sea), ("泳池水", pool),
                    ("LED灯带", lamp), ("灯罩", lamp), ("灯室玻璃", lh)):
        if cn in cn2ascii:
            override[cn2ascii[cn]] = mat
    paint = build_painting()
    for k in range(3):
        a = cn2ascii.get("画布_%d" % k)
        if a:
            override[a] = instance(paint, "MI_Painting_%d" % k, textures={"Tex": tex("painting_%d" % k)})

    n_slots = 0
    for actor in sub.get_all_level_actors():
        if not isinstance(actor, unreal.StaticMeshActor) or "Villa" not in [str(t) for t in actor.tags]:
            continue
        smc = actor.static_mesh_component
        for i, mat in enumerate(smc.get_materials()):
            if mat is None:
                continue
            base = mat.get_name()
            if base in override:
                smc.set_material(i, override[base])
                n_slots += 1
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    log.append("materials: {} overrides, {} slots replaced".format(len(override), n_slots))
    open(os.path.join(D, "v5_report.txt"), "w", encoding="utf-8").write("\n".join(log))
    print("\n".join(log))


main()
