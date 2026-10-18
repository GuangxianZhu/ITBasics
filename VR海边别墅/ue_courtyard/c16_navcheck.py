# -*- coding: utf-8 -*-
"""c16 家具摆完后: 家具旁边的空地还能不能瞬移过去 (VR 模板瞬移只要落点在 NavMesh 上, 不要求能走过去)。
落点用很小的搜索范围投影 (水平 15 cm): 投不上 = 那里被家具或腐蚀吃掉了。追加写 nav_check.txt
注: 路径连通性 (find_path) 在这个场景里本来就不全通 (门窄、台阶), 瞬移不受影响, 所以这里不查。"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
V = lambda x, y, z: unreal.Vector(x * 100, -y * 100, z * 100)
GOALS = [("厨房台面和岛台之间", 23.0, 11.85, 0.3), ("岛台北侧吧凳旁", 22.9, 13.8, 0.3),
         ("次卧床西侧", 9.75, 4.4, 0.3), ("次卧床东侧", 13.45, 4.0, 0.3), ("次卧床尾", 11.75, 6.0, 0.3),
         ("卫生间", 15.3, 4.2, 0.3), ("工作间中间", 30.0, 4.0, 0.2), ("工作台前", 29.5, 5.2, 0.2),
         ("工作室中间", 35.0, 14.0, 0.3), ("写代码椅子后", 34.0, 15.9, 0.3), ("长桌前", 35.9, 15.5, 0.3),
         ("地下室过道尽头看酒架", 25.9, 4.9, -2.7)]
out = []
ok = 0
for name, x, y, z in GOALS:
    g = unreal.NavigationSystemV1.project_point_to_navigation(w, V(x, y, z), None, None, unreal.Vector(15, 15, 60))
    hit = g is not None and (abs(g.x) + abs(g.y) + abs(g.z)) > 0.001
    ok += hit
    out.append("%s: %s" % (name, "ok" if hit else "NOT ON NAVMESH"))
out.insert(0, "furniture teleport spots ok: %d/%d" % (ok, len(GOALS)))
open(os.path.join(D, "nav_check.txt"), "a", encoding="utf-8").write("\n" + "\n".join(out))
print(" | ".join(out))
