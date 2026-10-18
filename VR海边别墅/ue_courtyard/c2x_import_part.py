# -*- coding: utf-8 -*-
"""UE 里运行: 局部替换合并网格 (README 坑 31 的流程做成脚本)。
  1. 云端: python c2x_export_geom.py <网格名…>  -> court_geom_part.glb, 传到 court/part/court_geom.glb
     (文件必须叫 court_geom.glb: Interchange 用文件名当目录, 才会落到 Geom/court_geom/StaticMeshes/ 覆盖原资产)
  2. UE:   c2x_import_part.py [消失的网格名…]  -> 导入覆盖 + 删凸包碰撞/复杂当简单 + 删掉消失网格的 Actor 和资产
  之后还要: c9_bake.py prep, RebuildNavigation, 重烘。"""
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
DST = "/Game/Courtyard/Geom"
SM_DIR = DST + "/court_geom/StaticMeshes/"
LOG = []
gone = sys.argv[1:]

f = os.path.join(D, "part", "court_geom.glb")
if os.path.exists(f):
    t = unreal.AssetImportTask()
    t.filename = f
    t.destination_path = DST
    t.automated = True
    t.save = True
    t.replace_existing = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    names = [p.split("/")[-1].split(".")[0] for p in t.imported_object_paths]
    LOG.append("imported: %s" % names)
    for p in t.imported_object_paths:
        m = EAL.load_asset(p)
        if isinstance(m, unreal.StaticMesh):
            SMES.remove_collisions(m)
            bs = m.get_editor_property("body_setup")
            if bs:
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(m)
else:
    LOG.append("no part/court_geom.glb, import skipped")

n = 0
for a in EAS.get_all_level_actors():
    lab = a.get_actor_label()
    if lab.startswith("G_") and lab[2:] in gone:
        EAS.destroy_actor(a)
        n += 1
LOG.append("deleted actors: %d / %d" % (n, len(gone)))
for g in gone:
    p = SM_DIR + g
    if EAL.does_asset_exist(p):
        EAL.delete_asset(p)
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
print(" | ".join(LOG))
