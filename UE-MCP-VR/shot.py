# -*- coding: utf-8 -*-
"""
把编辑器视口摆到预设机位并截图 (HighResShot -> Saved/Screenshots/WindowsEditor/)。
用法:  py "shot.py" <机位名>     机位: eye / desk / shelf / top / door
同时把场景里所有灯光的强度/单位/可移动性写进 Documents/UE-MCP-Tools/lights.txt, 方便排查曝光。
"""
import os
import sys

import unreal

CAMS = {
    # 站立视角 1.65m, 从房间西南角看向书桌和窗
    "eye": ((-60, -170, 165), (-10, 35, 0)),
    "desk": ((40, -60, 140), (-22, 15, 0)),
    "shelf": ((60, 30, 150), (-8, 150, 0)),
    "top": ((0, 0, 760), (-89, 0, 0)),
    "door": ((200, 150, 170), (-12, -140, 0)),
    "corner": ((220, -170, 200), (-18, 150, 0)),
    "reading": ((110, 60, 165), (-15, -146, 0)),
    "west": ((180, -10, 160), (-5, 180, 0)),
    "north": ((60, -150, 160), (-5, 90, 0)),
}
name = sys.argv[1] if len(sys.argv) > 1 else "eye"
loc, rot = CAMS[name]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(rot[2], rot[0], rot[1]))
world = ues.get_editor_world()
unreal.SystemLibrary.execute_console_command(world, "HighResShot 1600x900 filename=study_{}".format(name))

sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
lines = []
for a in sub.get_all_level_actors():
    for c in a.get_components_by_class(unreal.LightComponentBase):
        d = [a.get_actor_label(), c.get_class().get_name(), "I=%.3f" % c.get_editor_property("intensity")]
        for p in ("intensity_units", "mobility", "cast_shadows"):
            try:
                d.append("%s=%s" % (p, c.get_editor_property(p)))
            except Exception:
                pass
        lines.append("  ".join(d))
    if isinstance(a, unreal.PostProcessVolume):
        s = a.settings
        lines.append("PPV %s unbound=%s method=%s bias=%s" % (a.get_actor_label(), a.unbound,
                     s.auto_exposure_method, s.auto_exposure_bias))
out = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "lights.txt")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print("shot", name, "lights ->", out)
