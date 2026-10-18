# c14_ceiling_normal.py : 修天花板顶灯周围的黑圈 (M_CourtPBR 法线朝向修正)
# 诊断 (2026-10-18 实测): 视口"仅光照"下天花板正常, "细节光照"(带法线贴图) 下灯周围一圈黑
#   -> 烘焙没问题, 是材质法线: 引擎 WorldAlignedNormal 在朝下的面 (天花板 = 屋顶盒子底面) 给出朝上的法线,
#      方向光照贴图按 dot(法线, 光方向) 着色, 灯在正下方时 dot ~ -1 -> 全黑, 只有少数凸起的像素亮 (斑点)。
# 修正: 法线和几何法线 (VertexNormalWS) 不在同一侧时, 关于该面镜像回来: N' = N - 2*min(dot(N,Nv),0)*Nv, 再归一化。
#   保留凹凸细节, 只纠正朝向; 墙/地面本来就同侧, 不受影响。
import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
PATH = "/Game/Courtyard/PBR/M_CourtPBR"
BACKUP = "/Game/Courtyard/PBR/Backup/M_CourtPBR_before_normalfix"


def add_hemisphere_fix(m, src, src_pin, x=-500, y=500):
    def e(cls, dx, dy):
        return MEL.create_material_expression(m, cls, x + dx, y + dy)
    vn = e(unreal.MaterialExpressionVertexNormalWS, 0, 150)
    d = e(unreal.MaterialExpressionDotProduct, 150, 100)
    MEL.connect_material_expressions(src, src_pin, d, "A")
    MEL.connect_material_expressions(vn, "", d, "B")
    mn = e(unreal.MaterialExpressionMin, 300, 100)
    MEL.connect_material_expressions(d, "", mn, "A")
    mn.set_editor_property("const_b", 0.0)
    k = e(unreal.MaterialExpressionMultiply, 450, 100)
    MEL.connect_material_expressions(mn, "", k, "A")
    k.set_editor_property("const_b", 2.0)
    kv = e(unreal.MaterialExpressionMultiply, 600, 150)
    MEL.connect_material_expressions(k, "", kv, "A")
    MEL.connect_material_expressions(vn, "", kv, "B")
    sub = e(unreal.MaterialExpressionSubtract, 750, 50)
    MEL.connect_material_expressions(src, src_pin, sub, "A")
    MEL.connect_material_expressions(kv, "", sub, "B")
    nz = e(unreal.MaterialExpressionNormalize, 900, 50)
    MEL.connect_material_expressions(sub, "", nz, "")
    return nz


if __name__ == "__main__":
    m = unreal.load_asset(PATH)
    src = MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_NORMAL)
    if src.get_class().get_name() == "MaterialExpressionNormalize":
        print("already fixed")
    else:
        if not EAL.does_asset_exist(BACKUP):
            EAL.duplicate_asset(PATH, BACKUP)
        pin = MEL.get_material_property_input_node_output_name(m, unreal.MaterialProperty.MP_NORMAL)
        nz = add_hemisphere_fix(m, src, pin)
        MEL.connect_material_property(nz, "", unreal.MaterialProperty.MP_NORMAL)
        MEL.recompile_material(m)
        EAL.save_loaded_asset(m)
        print("normal hemisphere fix applied; backup at", BACKUP)
