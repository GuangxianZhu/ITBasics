# -*- coding: utf-8 -*-
"""第 5 步: 时段氛围。py "c5_mood.py" dusk  (黄昏: 太阳压低变暖, 曝光提高, 室内灯更亮)
                   py "c5_mood.py" day   (还原成白天: 和 L_Villa 的 v6 一样)"""
import sys

import unreal

mode = sys.argv[1] if len(sys.argv) > 1 else "dusk"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
P = {"day": dict(pitch=-38.0, yaw=55.0, lux=8.0, color=(1.0, 0.96, 0.9), bias=0.0, lamp=6.0),
     "dusk": dict(pitch=-7.0, yaw=55.0, lux=4.0, color=(1.0, 0.55, 0.3), bias=1.3, lamp=10.0)}[mode]
log = []
for a in EAS.get_all_level_actors():
    cls = a.get_class().get_name()
    if cls == "DirectionalLight":
        a.set_actor_rotation(unreal.Rotator(0, P["pitch"], P["yaw"]), False)
        a.root_component.set_editor_property("relative_rotation", unreal.Rotator(0, P["pitch"], P["yaw"]))
        c = a.light_component
        c.set_intensity(P["lux"])
        c.set_light_color(unreal.LinearColor(P["color"][0], P["color"][1], P["color"][2], 1))
        log.append("sun")
    elif cls == "PostProcessVolume":
        s = a.get_editor_property("settings")
        s.set_editor_property("override_auto_exposure_bias", True)
        s.set_editor_property("auto_exposure_bias", P["bias"])
        a.set_editor_property("settings", s)
        log.append("exposure")
    elif cls == "PointLight" and "Courtyard" in [str(t) for t in a.tags]:
        c = a.point_light_component
        if c.intensity >= 4.5:
            c.set_intensity(P["lamp"] if c.intensity >= 5.5 else c.intensity)
    elif "Sky_Sphere" in cls:
        for fn in ("RefreshMaterial", "UpdateSunDirection"):
            try:
                a.call_method(fn)
                log.append("sky." + fn)
            except Exception:
                pass
for a in EAS.get_all_level_actors():
    if a.get_class().get_name() == "SkyLight":
        try:
            a.light_component.recapture_sky()
            log.append("skylight recaptured")
        except Exception:
            pass
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
print("mood", mode, log)
