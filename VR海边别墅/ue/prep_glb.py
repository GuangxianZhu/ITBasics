# -*- coding: utf-8 -*-
"""
把 Godot 版导出的 villa.glb 处理成 UE 友好的 villa_ue.glb:
  - 物体/网格/材质名: 中文 -> 拼音 ASCII (UE 资产路径和部分工具对非 ASCII 不友好)
  - 名字对照表 names.json, 标记点 (灯位/可拿/烧烤火位/灯塔) 和 VR 点位 markers.json (glTF 坐标, 米)
只改名字, 不动几何和变换。
用法: python prep_glb.py villa.glb villa_meta.json  ->  villa_ue.glb names.json markers.json
"""
import json
import re
import sys

from pygltflib import GLTF2
from pypinyin import lazy_pinyin

src, meta_path = sys.argv[1], sys.argv[2]
g = GLTF2().load(src)
meta = json.load(open(meta_path, encoding="utf-8"))


def ascii_name(s, used):
    py = "_".join(lazy_pinyin(s)) if s else "noname"
    py = re.sub(r"[^A-Za-z0-9_]+", "_", py)
    py = re.sub(r"_+", "_", py).strip("_") or "x"
    out, k = py, 1
    while out in used:
        k += 1
        out = "{}_{}".format(py, k)
    used.add(out)
    return out


names = {"nodes": {}, "materials": {}}
used = set()
for n in g.nodes:
    a = ascii_name(n.name, used)
    names["nodes"][a] = n.name
    n.name = a
used_m = set()
for m in g.materials:
    a = "M_" + ascii_name(m.name, used_m)
    names["materials"][a] = m.name
    m.name = a
for i, me in enumerate(g.meshes):
    me.name = "SM_{:03d}".format(i)

markers = {"empties": {}, "vr_points": meta.get("vr_points", [])}
for n in g.nodes:
    if n.mesh is None:
        markers["empties"][n.name] = {"cn": names["nodes"][n.name], "pos": n.translation or [0, 0, 0]}
g.save("villa_ue.glb")
json.dump(names, open("names.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(markers, open("markers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("nodes", len(g.nodes), "materials", len(g.materials), "empties", len(markers["empties"]))
