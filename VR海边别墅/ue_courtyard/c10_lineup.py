# -*- coding: utf-8 -*-
"""调试: 把某个文件夹下的植物网格在海边草地上排成一排看效果, 截图后可用 'clear' 删除。
用法: c10_lineup.py <路径前缀, 如 /Game/PN_> [列数]     |     c10_lineup.py clear"""
import json
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
TAG = "CourtLineup"
for a in EAS.get_all_level_actors():
    if TAG in [str(t) for t in a.tags]:
        EAS.destroy_actor(a)
if len(sys.argv) > 1 and sys.argv[1] != "clear":
    pre = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 11
    inv = [r for r in json.load(open(os.path.join(D, "plants_inv.json"), encoding="utf-8")) if r["path"].startswith(pre)]
    inv.sort(key=lambda r: r["path"])
    x0, y0 = -20.0, 25.0            # 平面图: 房子西边的海边草地
    gap = 1.6
    for i, r in enumerate(inv):
        cx, cy = x0 + (i % cols) * gap, y0 + (i // cols) * gap
        m = unreal.load_asset(r["path"])
        a = EAS.spawn_actor_from_object(m, unreal.Vector(cx * 100, -cy * 100, 2), unreal.Rotator(0, 0, 0))
        a.set_actor_label("LU_" + r["path"].split("/")[-1])
        a.set_editor_property("tags", [unreal.Name(TAG)])
        a.set_folder_path("Lineup")
    # 相机: 站在南边略高处往北看
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    rows = (len(inv) + cols - 1) // cols
    cxm = x0 + (cols - 1) * gap / 2
    ues.set_level_viewport_camera_info(unreal.Vector(cxm * 100, -(y0 - 4.5) * 100, 260), unreal.Rotator(0, -22, -90))
    print("lineup %d meshes, %d rows" % (len(inv), rows))
