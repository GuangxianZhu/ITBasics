# -*- coding: utf-8 -*-
"""修 NavMesh: 合并网格导入时自动生成了"简单碰撞"(凸包)。导航用的是简单碰撞, 一个区域的墙+天花板合成一个凸包
就成了一整块实心, 屋里没有 NavMesh(只在屋顶上有)。这里把简单碰撞全删掉, 只用"复杂碰撞当简单碰撞"(按三角面)。
c2_build.py 的 import_merged 也做同样的事; 这个脚本用来修已经导入的资产, 不用整栋重建。"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAL = unreal.EditorAssetLibrary
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
out, n = [], 0
for path in EAL.list_assets("/Game/Courtyard/Geom", recursive=True, include_folder=False):
    m = EAL.load_asset(path)
    if not isinstance(m, unreal.StaticMesh):
        continue
    before = SMES.get_convex_collision_count(m) + SMES.get_simple_collision_count(m)
    SMES.remove_collisions(m)
    bs = m.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    EAL.save_loaded_asset(m)
    n += 1
    if before:
        out.append("%s: removed %d simple shapes" % (m.get_name(), before))
out.insert(0, "meshes: %d, with simple collision: %d" % (n, len(out)))
open(os.path.join(D, "fixcol.txt"), "w", encoding="utf-8").write("\n".join(out))
print(out[0])
