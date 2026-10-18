# -*- coding: utf-8 -*-
"""调试: 在每个参观点竖直往下打射线, 列出命中的 Actor 和高度; 再用大范围投影找最近的 NavMesh。结果写 probe.txt。"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
pts = json.load(open(os.path.join(D, "court_points.json"), encoding="utf-8"))["points"]
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
out = []
for p in pts:
    x, y, z = p["x"] * 100, -p["y"] * 100, p["z"] * 100
    hs = []
    for top in (450, 160, 60):
        h = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, z + top), unreal.Vector(x, y, z - 120),
                                                   unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                   unreal.DrawDebugTrace.NONE, True)
        if h:
            t = h.to_tuple()
            loc, act = t[4], t[9]
            hs.append("from+%d: %s@%.0f" % (top, act.get_actor_label() if act else "?", loc.z))
        else:
            hs.append("from+%d: none" % top)
    r = unreal.NavigationSystemV1.project_point_to_navigation(world, unreal.Vector(x, y, z + 50), None, None,
                                                              unreal.Vector(400, 400, 400))
    nav = "nav(%.0f,%.0f,%.0f)" % (r.x / 100, -r.y / 100, r.z) if r else "nav none"
    out.append("%s: %s | %s" % (p["name"], nav, ", ".join(hs)))
open(os.path.join(D, "probe.txt"), "w", encoding="utf-8").write("\n".join(out))
print("probe done")
