# -*- coding: utf-8 -*-
"""视口摆到 Godot 版的 8 个参观点位 (眼高 1.65m) 截图 -> Saved/Screenshots/WindowsEditor/villa_<n>.png
用法: py "shot_villa.py" 1          (1~8)
      py "shot_villa.py" 1 lumen    -> villa_lumen_1.png (对比不同渲染模式)"""
import json
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
pts = json.load(open(os.path.join(D, "markers.json"), encoding="utf-8"))["vr_points"]
i = int(sys.argv[1]) if len(sys.argv) > 1 else 1
tag = (sys.argv[2] + "_") if len(sys.argv) > 2 else ""
p = pts[i - 1]
x, y, z = p["pos"]
loc = unreal.Vector(x * 100, z * 100, y * 100 + 165)
yaw = -90 - p.get("yaw_deg", 0)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(loc, unreal.Rotator(0, -5, yaw))
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "HighResShot 1600x900 filename=villa_{}{}".format(tag, i))
print("shot", i, p["name"])
