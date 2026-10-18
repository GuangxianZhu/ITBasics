# c13_railglass.py : 楼梯口玻璃栏杆 (G_D_Hall__glass) 换成看得见的玻璃 M_RailGlass
# 原 M_CourtGlass: 不透明度恒定 0.12 + 体积光照(无镜面高光) -> 几乎隐形, 只剩黑扶手像飘在空中
# 新材质: 淡绿 (浮法玻璃含铁) + 菲涅尔不透明度 (正视 0.15, 掠射 0.65, 边缘和斜看时看得见) + 表面逐像素光照 (有高光)
import unreal
AT = unreal.AssetToolsHelpers.get_asset_tools(); MEL = unreal.MaterialEditingLibrary; EAL = unreal.EditorAssetLibrary
path = "/Game/Courtyard/Materials/M_RailGlass"
if EAL.does_asset_exist(path):
    m = unreal.load_asset(path); MEL.delete_all_material_expressions(m)
else:
    m = AT.create_asset("M_RailGlass", "/Game/Courtyard/Materials", unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
m.set_editor_property("two_sided", True)


def C(v, x, y):
    n = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, x, y)
    n.set_editor_property("r", v)
    return n


col = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -400, -200)
col.set_editor_property("constant", unreal.LinearColor(0.70, 0.86, 0.82, 1))
MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
MEL.connect_material_property(C(0.03, -400, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
MEL.connect_material_property(C(1.0, -400, 60), "", unreal.MaterialProperty.MP_SPECULAR)
fr = MEL.create_material_expression(m, unreal.MaterialExpressionFresnel, -600, 200)
fr.set_editor_property("exponent", 3.0)
fr.set_editor_property("base_reflect_fraction", 0.04)
lp = MEL.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -300, 200)
MEL.connect_material_expressions(C(0.15, -600, 120), "", lp, "A")
MEL.connect_material_expressions(C(0.65, -600, 160), "", lp, "B")
MEL.connect_material_expressions(fr, "", lp, "Alpha")
MEL.connect_material_property(lp, "", unreal.MaterialProperty.MP_OPACITY)
MEL.recompile_material(m)
EAL.save_loaded_asset(m)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in EAS.get_all_level_actors():
    if a.get_actor_label() == "G_D_Hall__glass":
        smc = a.static_mesh_component
        for i in range(smc.get_num_materials()):
            smc.set_material(i, m)
        print("applied to", a.get_actor_label())
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
