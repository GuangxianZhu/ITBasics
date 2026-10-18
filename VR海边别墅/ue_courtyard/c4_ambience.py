# -*- coding: utf-8 -*-
"""第 4 步: 环境声音 (不需要写逻辑: 导入 wav -> 设循环 -> 摆 AmbientSound, 带距离衰减和空间化)。
  海浪 3 处 (海边) / 海鸥 (海上) / 风 (全场, 不定位) / 水渠和入口长巷的流水 / 门院石水钵 /
  客厅收音机 (小声) / 电子工作室设备嗡嗡声 / 地下室除湿机。可重复运行。"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
SRC = "C:/work/ITBasics/VR海边别墅/godot/model/snd"
DST = "/Game/Courtyard/Audio"
TAG = "CourtyardSound"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
log = []


def V(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def imp(path):
    name = os.path.splitext(os.path.basename(path))[0]
    dst = DST + "/" + name
    if not EAL.does_asset_exist(dst):
        t = unreal.AssetImportTask()
        t.filename = path
        t.destination_path = DST
        t.automated = True
        t.save = True
        t.replace_existing = True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    w = unreal.load_asset(dst)
    w.set_editor_property("looping", True)
    EAL.save_loaded_asset(w)
    return w


def emitter(wave, x, y, z, inner, falloff, vol, label, spatial=True):
    a = EAS.spawn_actor_from_class(unreal.AmbientSound, V(x, y, z))
    c = a.get_editor_property("audio_component")
    c.set_sound(wave)
    c.set_editor_property("volume_multiplier", vol)
    c.set_editor_property("auto_activate", True)
    if spatial:
        c.set_editor_property("override_attenuation", True)
        s = c.get_editor_property("attenuation_overrides")
        s.set_editor_property("attenuate", True)
        s.set_editor_property("spatialize", True)
        s.set_editor_property("attenuation_shape", unreal.AttenuationShape.SPHERE)
        s.set_editor_property("attenuation_shape_extents", unreal.Vector(inner * 100, 0, 0))
        s.set_editor_property("falloff_distance", falloff * 100)
        c.set_editor_property("attenuation_overrides", s)
    a.set_editor_property("tags", [unreal.Name(TAG)])
    a.set_folder_path("Courtyard/Sound")
    a.set_actor_label("SND_" + label)
    log.append(label)


for a in EAS.get_all_level_actors():
    if TAG in [str(t) for t in a.tags]:
        EAS.destroy_actor(a)

ocean = imp(SRC + "/ocean.wav")
wind = imp(SRC + "/wind.wav")
radio = imp(SRC + "/radio.wav")
gulls = imp(D + "/gulls_loop.wav")
trickle = imp(D + "/trickle_loop.wav")
hum = imp(D + "/studio_hum_loop.wav")

for x in (2.0, 19.0, 36.0):
    emitter(ocean, x, 31.0, -1.5, 8, 45, 1.0, "Ocean_%d" % x)
emitter(gulls, 15.0, 60.0, 12.0, 20, 80, 0.8, "Gulls")
emitter(wind, 19.0, 14.0, 3.0, 0, 0, 0.18, "Wind", spatial=False)
emitter(trickle, 10.5, 10.9, 1.3, 0.5, 7, 0.9, "RillSpout")
emitter(trickle, 25.5, 9.9, 0.3, 2.0, 7, 0.5, "LaneRill")
emitter(trickle, 32.4, 7.6, 0.7, 0.3, 4, 0.4, "StoneBasin")
emitter(radio, 18.6, 11.1, 1.2, 0.5, 7, 0.25, "KitchenRadio")
emitter(hum, 36.8, 14.0, 1.3, 1.0, 5, 0.6, "StudioHum")
emitter(hum, 17.7, 3.3, -2.4, 0.5, 5, 0.5, "BasementDehumidifier")
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
print("ambience:", ", ".join(log))
