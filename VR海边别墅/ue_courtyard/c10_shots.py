# -*- coding: utf-8 -*-
"""一次拍多张检查图 (SceneCapture2D -> PNG, 不用一张张 HighResShot): court/shots/plants_<名字>.png
用法: c10_shots.py            默认那组视角
      c10_shots.py ivy        只拍常春藤的近景"""
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
OUT = os.path.join(D, "shots")
os.makedirs(OUT, exist_ok=True)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

# 名字: 平面图 x, y, 眼高 z, 俯仰, 朝向 (平面图角度: 0 = 东, 90 = 北)
VIEWS = {
    "c1": (6.9, 11.6, 1.65, -8, 100),       # 橄榄院(主树院): 从石凳往北
    "c1b": (7.0, 17.9, 1.8, -14, -110),     # 从平台开口往下看主树院
    "c3": (14.3, 10.9, 1.65, -18, 90),      # 香草院
    "c2": (10.5, 20.5, 1.7, -10, -90),      # 从平台看水渠窄院 (隔着矮墙)
    "c4": (8.2, 7.0, 1.65, -10, 150),       # 主卧私院
    "c5": (8.5, 4.6, 1.65, -12, 165),       # 次卧私院
    "c6": (29.3, 8.6, 1.65, -8, 180),       # 入口长巷 (出生点)
    "c7": (32.6, 9.9, 1.65, -22, -135),     # 门院
    "c8": (31.8, 16.5, 1.65, -10, -95),     # 柠檬巷 (往南看)
    "terr": (18.5, 21.5, 1.65, -6, 165),    # 平台往西: 种植池 + 橄榄
    "sea": (25.5, 14.0, 1.65, -4, 90),      # 客厅看海: 棕榈在两边
    "gate": (36.0, 4.0, 1.65, -6, 110),     # 停车位看大门: 柏树门框
    "top": (19.0, -6.0, 26.0, -48, 90),     # 俯瞰
}
IVY = {
    "ivy1": (6.2, 15.6, 1.4, -10, 180),
    "ivy6": (25.0, 9.2, 1.4, -10, -90),
}
views = IVY if "ivy" in sys.argv[1:] else VIEWS
pick = [a for a in sys.argv[1:] if a in VIEWS]
if pick:
    views = {a: VIEWS[a] for a in pick}

rt = unreal.RenderingLibrary.create_render_target2d(world, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
cap = EAS.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
cc = cap.capture_component2d
cc.set_editor_property("texture_target", rt)
cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
cc.set_editor_property("fov_angle", 90.0)
cc.set_editor_property("capture_every_frame", False)
done = []
for name, (x, y, z, pitch, yaw) in views.items():
    cap.set_actor_location_and_rotation(unreal.Vector(x * 100, -y * 100, z * 100), unreal.Rotator(0, pitch, -yaw), False, False)
    cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, "plants_" + name)
    done.append(name)
EAS.destroy_actor(cap)
print("shots:", done, "->", OUT)
