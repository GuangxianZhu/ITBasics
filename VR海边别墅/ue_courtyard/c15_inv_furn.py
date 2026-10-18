# c15_inv_furn.py <Content 下的文件夹…> : 列出素材包里所有静态网格的尺寸 / 三角形数 / LOD 数 / Nanite / 材质数
# 输出 court/furn_inv.json (给挑件用) + 打印汇总。例: py c15_inv_furn.py /Game/ApartmentTech /Game/ModernHouse
# 为什么要这一步: Fab 室内包常是 Nanite-only 或高面数; VR forward 下 Nanite 不可靠 (README 坑 17), 要看 LOD0 三角形数和有没有 LOD
import json, os, sys
import unreal

EAL = unreal.EditorAssetLibrary
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
roots = sys.argv[1:] or ["/Game"]
rows = []
for root in roots:
    for path in EAL.list_assets(root, recursive=True, include_folder=False):
        ad = unreal.EditorAssetLibrary.find_asset_data(path)
        if str(ad.asset_class_path.asset_name) != "StaticMesh":
            continue
        sm = unreal.load_asset(path)
        b = sm.get_bounding_box()
        size = [round((getattr(b.max, c) - getattr(b.min, c)), 1) for c in "xyz"]
        try:
            nanite = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
        except Exception:
            nanite = None
        lods = SMES.get_lod_count(sm)
        try:
            tris = SMES.get_number_verts(sm, 0)   # 顶点数 (三角形数接口不稳定, 顶点数足够比较)
        except Exception:
            tris = -1
        rows.append(dict(path=path.split(".")[0], name=sm.get_name(), size_cm=size, verts_lod0=tris, lods=lods,
                         nanite=nanite, mats=len(sm.static_materials)))
rows.sort(key=lambda r: r["path"])
json.dump(rows, open(os.path.join(D, "furn_inv.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for r in rows:
    print("%-70s %7s verts lod%d %s %s" % (r["path"][-70:], r["verts_lod0"], r["lods"], "NANITE" if r["nanite"] else "", r["size_cm"]))
print("meshes:", len(rows))
