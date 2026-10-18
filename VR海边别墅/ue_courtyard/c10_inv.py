# -*- coding: utf-8 -*-
"""第 10 步准备: 列出从 Fab 加进来的植物网格 (尺寸、LOD 数、LOD0 三角面、是否 Nanite、材质) -> plants_inv.json / plants_inv.txt"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
SKIP = ("/Game/Courtyard", "/Game/Villa", "/Game/XR", "/Game/LevelPrototyping", "/Game/VRSpectator", "/Game/Weapons",
        "/Game/VRTemplate", "/Game/StarterContent")
for _d in ("/Game/Fab",):
    if unreal.EditorAssetLibrary.does_directory_exist(_d):
        unreal.EditorAssetLibrary.save_directory(_d, True, True)
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
ar = unreal.AssetRegistryHelpers.get_asset_registry()
flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")], package_paths=["/Game"],
                      recursive_paths=True)
out, lines = [], []
for d in ar.get_assets(flt):
    p = str(d.package_name)
    if p.startswith(SKIP) or "/UE4_ThirdPerson/" in p:
        continue
    m = unreal.load_asset(p)
    if not isinstance(m, unreal.StaticMesh):
        continue
    b = m.get_bounding_box()
    size = [round((getattr(b.max, c) - getattr(b.min, c)) / 100.0, 2) for c in "xyz"]
    try:
        nan = bool(m.get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        nan = None
    lods = m.get_num_lods()
    try:
        tris = SMES.get_number_verts(m, 0)
    except Exception:
        tris = -1
    mats = [str(sm.get_editor_property("material_interface").get_path_name()) if sm.get_editor_property("material_interface") else "None"
            for sm in m.get_editor_property("static_materials")]
    rec = dict(path=p, size=size, zmin=round(b.min.z / 100.0, 2), lods=lods, verts0=tris, nanite=nan, mats=mats)
    out.append(rec)
    lines.append("%-90s size=%s lods=%d verts0=%s nanite=%s mats=%d" % (p, size, lods, tris, nan, len(mats)))
json.dump(out, open(os.path.join(D, "plants_inv.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
open(os.path.join(D, "plants_inv.txt"), "w", encoding="utf-8").write("\n".join(sorted(lines)))
print("inventory: %d meshes" % len(out))
