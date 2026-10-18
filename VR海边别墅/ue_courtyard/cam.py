# helper: py cam.py x y z pitch yaw name  (平面图米制坐标) -> HighResShot court_<name>.png ; 同时把 CF_* 家具的旋转写到 cam.txt
import os, sys, unreal
D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
x, y, z, pitch, yaw = [float(v) for v in sys.argv[1:6]]
name = sys.argv[6]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(0, pitch, yaw))
unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), "HighResShot 1600x900 filename=court_" + name)
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = ["%s rot=%s" % (a.get_actor_label(), a.get_actor_rotation()) for a in sub.get_all_level_actors() if a.get_actor_label().startswith("CF_")]
open(os.path.join(D, "cam.txt"), "w", encoding="utf-8").write("\n".join(out))
