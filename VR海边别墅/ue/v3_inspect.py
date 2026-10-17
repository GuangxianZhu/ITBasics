# -*- coding: utf-8 -*-
"""导入后检查: 列出 Actor/网格/材质, 并用空物体 (标记点) 解出 glTF(米, Y上) -> UE(厘米, Z上) 的坐标换算。"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
markers = json.load(open(os.path.join(D, "markers.json"), encoding="utf-8"))
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
lines, by_label = [], {}
for a in sub.get_all_level_actors():
    lab = a.get_actor_label()
    by_label[lab] = a
    smc = a.get_component_by_class(unreal.StaticMeshComponent)
    info = ""
    if smc and smc.static_mesh:
        mats = [m.get_name() if m else "None" for m in smc.get_materials()]
        info = "{} mats={}".format(smc.static_mesh.get_path_name(), mats)
    loc = a.get_actor_location()
    lines.append("{}\t{}\t({:.0f},{:.0f},{:.0f})\tparent={}\t{}".format(
        lab, a.get_class().get_name(), loc.x, loc.y, loc.z,
        a.get_attach_parent_actor().get_actor_label() if a.get_attach_parent_actor() else "-", info))
pairs = []
for name, m in markers["empties"].items():
    a = by_label.get(name)
    if a:
        l = a.get_actor_location()
        pairs.append((m["pos"], [l.x, l.y, l.z]))
lines.insert(0, "MARKER PAIRS (gltf -> ue): " + json.dumps(pairs[:6]))
open(os.path.join(D, "inspect.txt"), "w", encoding="utf-8").write("\n".join(lines))
print("inspect: actors", len(lines), "marker pairs", len(pairs))
