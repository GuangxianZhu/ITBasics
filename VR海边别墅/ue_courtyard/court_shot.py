# -*- coding: utf-8 -*-
"""视口摆到院落别墅的参观点 (眼高 1.65 m) 截图 -> Saved/Screenshots/WindowsEditor/court_<n>.png
用法: py "court_shot.py" 3        第 3 个点
      py "court_shot.py" top      俯瞰全景"""
import json
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
pts = json.load(open(os.path.join(D, "court_points.json"), encoding="utf-8"))["points"]
arg = sys.argv[1] if len(sys.argv) > 1 else "1"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if arg == "top":
    loc, rot, name = unreal.Vector(1900, 2600, 3600), unreal.Rotator(0, -52, -90), "top"
elif arg == "top2":
    loc, rot, name = unreal.Vector(-900, -3200, 2400), unreal.Rotator(0, -38, 45), "top2"
else:
    p = pts[int(arg) - 1]
    loc = unreal.Vector(p["x"] * 100, -p["y"] * 100, (p["z"] + 1.65) * 100)
    rot, name = unreal.Rotator(0, -6, p["yaw"]), arg
ues.set_level_viewport_camera_info(loc, rot)
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "HighResShot 1600x900 filename=court_{}".format(name))
print("shot", name)
