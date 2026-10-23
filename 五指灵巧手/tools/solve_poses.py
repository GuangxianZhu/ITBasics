# -*- coding: utf-8 -*-
"""重新求解各个手势的关节角（避开穿模），写回 params.json 的 "poses"。
改了零件尺寸或关节布局以后跑一次：
    blender -b --factory-startup --python tools/solve_poses.py
    （或 pip 版 bpy：python tools/solve_poses.py）
"""
import json, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.argv.append("--solve")
import build_hand as B

B.build()
fn = os.path.join(HERE, "params.json")
with open(fn, encoding="utf-8") as f:
    p = json.load(f)
p["poses"] = {"_说明": "由 tools/solve_poses.py 求解：拇指朝向、握拳不穿模、拇指与食指指尖套接触。单位 度，顺序 J1 J2 J3 J4"}
for name, pose in B.POSES.items():
    p["poses"][name] = {f: [round(B.clamp(f, k, v), 1) for k, v in enumerate(pose[f])] for f in B.FINGERS}
txt = json.dumps(p, ensure_ascii=False, indent=2)
# 让数字列表各占一行，方便看
import re
txt = re.sub(r'\[\s*(-?[\d.]+(?:,\s*-?[\d.]+)*)\s*\]', lambda m: '[' + ', '.join(x.strip() for x in m.group(1).split(',')) + ']', txt)
txt = re.sub(r'\[\s*(\[[^\[\]]*\](?:,\s*\[[^\[\]]*\])*)\s*\]', lambda m: '[\n      ' + re.sub(r'\],\s*\[', '], [', m.group(1)) + '\n    ]', txt)
txt = re.sub(r'\{[^{}]*\}', lambda m: (re.sub(r'\s*\n\s*', ' ', m.group(0)) if len(re.sub(r'\s*\n\s*', ' ', m.group(0))) < 150 else m.group(0)), txt)
with open(fn, "w", encoding="utf-8") as f:
    f.write(txt + "\n")
print("[ok] poses 写回 params.json")
