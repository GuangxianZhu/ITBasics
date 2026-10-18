# -*- coding: utf-8 -*-
"""c16 家具检查图: court/shots/ff_<名字>.png (SceneCapture, 一次全拍)。用法: c16_shots.py [名字…]"""
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
OUT = os.path.join(D, "shots")
os.makedirs(OUT, exist_ok=True)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
# 名字: 平面图 x, y, 眼高 z, 俯仰, 朝向 (0 = 东, 90 = 北)
VIEWS = {
    "kitchen": (23.6, 15.2, 1.65, -18, -90),
    "kitchen2": (17.8, 14.2, 1.65, -16, -25),
    "guest": (13.6, 6.2, 1.65, -22, -140),
    "bath": (15.6, 4.8, 1.65, -30, -95),
    "basement": (21.2, 4.9, -1.25, -8, 0),
    "workshop": (31.8, 3.4, 1.65, -18, 140),
    "workshop2": (28.6, 4.4, 1.65, -14, -25),
    "studio": (33.8, 13.0, 1.65, -14, 50),
    "studio2": (35.8, 15.8, 1.65, -16, -115),
    "desk": (34.9, 15.6, 1.35, -12, 90),          # 近看: 显示器屏幕朝哪
    "benchmon": (35.9, 15.2, 1.4, -10, 0),
}
pick = [a for a in sys.argv[1:] if a in VIEWS]
views = {a: VIEWS[a] for a in pick} if pick else VIEWS
rt = unreal.RenderingLibrary.create_render_target2d(world, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
cap = EAS.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
cc = cap.capture_component2d
cc.set_editor_property("texture_target", rt)
cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
cc.set_editor_property("fov_angle", 90.0)
cc.set_editor_property("capture_every_frame", False)
for name, (x, y, z, pitch, yaw) in views.items():
    cap.set_actor_location_and_rotation(unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(0, pitch, -yaw), False, False)
    cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, "ff_" + name)
EAS.destroy_actor(cap)
print("shots:", list(views), "->", OUT)
