# -*- coding: utf-8 -*-
"""检查导航路径: 入口长巷 -> 门厅 -> 楼梯 -> 地下室 是否连通 (不是"部分路径")。结果追加到 nav_check.txt"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
V = lambda x, y, z: unreal.Vector(x * 100, -y * 100, z * 100)
out = []
for name, a, b in (("门厅->地下室", V(18.2, 5.0, 0.3), V(23.85, 4.9, -2.7)),
                   ("入口->地下室", V(29.3, 8.6, 0.2), V(23.85, 4.9, -2.7))):
    p = unreal.NavigationSystemV1.find_path_to_location_synchronously(w, a, b)
    if p is None:
        out.append("%s: no path" % name)
        continue
    pts = p.get_editor_property("path_points")
    partial = p.is_partial()
    L = sum((pts[i + 1] - pts[i]).length() for i in range(len(pts) - 1)) / 100 if len(pts) > 1 else 0
    out.append("%s: %s, %d pts, %.1f m, via %s" % (name, "PARTIAL" if partial else "ok", len(pts), L,
                                                  " ".join("(%.1f,%.1f,%.1f)" % (q.x / 100, -q.y / 100, q.z / 100) for q in pts)))
open(os.path.join(D, "nav_check.txt"), "a", encoding="utf-8").write("\n" + "\n".join(out))
print(" | ".join(out))
