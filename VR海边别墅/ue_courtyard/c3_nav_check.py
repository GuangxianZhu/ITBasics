# -*- coding: utf-8 -*-
"""第 3 步: 检查各参观点能否落到 NavMesh (VR 模板的瞬移只能落在 NavMesh 上)。结果写 nav_check.txt。
NavMesh 不更新时: py "c1_new_level.py" load 重新加载关卡, 再在控制台输 RebuildNavigation (UE 版踩过的坑)。"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
pts = json.load(open(os.path.join(D, "court_points.json"), encoding="utf-8"))["points"]
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
out, ok = [], 0
for p in pts:
    q = unreal.Vector(p["x"] * 100, -p["y"] * 100, p["z"] * 100 + 50)
    r = unreal.NavigationSystemV1.project_point_to_navigation(world, q, None, None, unreal.Vector(60, 60, 150))
    hit = r is not None and (abs(r.x) + abs(r.y) + abs(r.z)) > 0.001
    ok += 1 if hit else 0
    out.append("{} -> {}".format(p["name"], "OK z=%.0f" % r.z if hit else "NOT ON NAVMESH"))
out.insert(0, "on navmesh: {}/{}".format(ok, len(pts)))
open(os.path.join(D, "nav_check.txt"), "w", encoding="utf-8").write("\n".join(out))
print(out[0])
