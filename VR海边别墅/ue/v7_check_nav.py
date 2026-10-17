# -*- coding: utf-8 -*-
"""检查: 8 个参观点位能否投影到 NavMesh (VR 模板的瞬移只能落在 NavMesh 上)。结果写 nav_check.txt"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
pts = json.load(open(os.path.join(D, "markers.json"), encoding="utf-8"))["vr_points"]
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
out = []
ok_n = 0
for p in pts:
    x, y, z = p["pos"]
    q = unreal.Vector(x * 100, z * 100, y * 100 + 50)
    r = unreal.NavigationSystemV1.project_point_to_navigation(world, q, None, None, unreal.Vector(60, 60, 200))
    hit = r is not None and (abs(r.x) + abs(r.y) + abs(r.z)) > 0.001
    ok_n += 1 if hit else 0
    out.append("{} {} -> {}".format(p["name"], q, r if hit else "NOT ON NAVMESH"))
out.insert(0, "on navmesh: {}/{}".format(ok_n, len(pts)))
open(os.path.join(D, "nav_check.txt"), "w", encoding="utf-8").write("\n".join(out))
print(out[0])
