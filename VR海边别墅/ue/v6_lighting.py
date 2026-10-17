# -*- coding: utf-8 -*-
"""
第 6 步: 天空和灯光
  - L_Villa 是从 XR 模板另存来的, 模板的太阳/天光/天空球在共享子关卡 L_XRTemplate_Lighting 里。
    直接改它会连带改坏模板和 VRStudy, 所以把这个子关卡从 L_Villa 里移除 (只删引用, 资产不动), 自己建一套:
    DirectionalLight(太阳) + BP_Sky_Sphere(引擎自带天空球, 绑定太阳) + SkyLight + ExponentialHeightFog(远景空气透视)
    实测: SkyAtmosphere 在这个工程里渲染出全黑天空 (原因没查清, SKY_MODE="atmosphere" 可切回去试);
          体积云在固定曝光下发灰发脏, 默认关 (USE_CLOUDS)。
  - 室内灯: 在 Blender 标的 "灯位_*" 位置放点光源 (Godot 版同样的位置)
  - 曝光: 模板关了自动曝光; 放一个全局后期体积, 曝光固定, 两种 GI 模式下亮度可比。
全部可移动光源 (不烘焙), 两种 GI 模式通用。
"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
TAG = "VillaLight"
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
log = []

SUN = {"pitch": -38.0, "yaw": 55.0, "lux": 8.0}
INTERIOR_CD = 4.0
USE_CLOUDS = False
SKY_MODE = "sphere"   # "sphere" (模板天空球) / "atmosphere" (物理大气)
EXPOSURE_BIAS = 0.0


def spawn(cls, label, loc=(0, 0, 0), rot=(0, 0, 0)):
    a = sub.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(rot[2], rot[0], rot[1]))
    a.set_actor_label(label)
    a.set_folder_path("Villa/Lighting")
    a.tags = [TAG]
    return a


def main():
    world = ues.get_editor_world()
    if not world.get_path_name().startswith("/Game/Villa/Maps/L_Villa"):
        raise RuntimeError("open L_Villa first")
    # 1) 去掉模板灯光子关卡 (只从 L_Villa 移除引用)
    for lvl in unreal.EditorLevelUtils.get_levels(world):
        pkg = lvl.get_outermost().get_name()
        if "L_XRTemplate_Lighting" in pkg:
            ok = unreal.EditorLevelUtils.remove_level_from_world(lvl)
            log.append("removed sublevel {} from L_Villa: {}".format(pkg, ok))
    # 2) 删上次本脚本建的
    for a in sub.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            sub.destroy_actor(a)
        elif a.get_class().get_name() in ("BP_Sky_Sphere_C", "SkyLight", "DirectionalLight", "SphereReflectionCapture"):
            sub.destroy_actor(a)  # 持久关卡里残留的模板天空/灯 (子关卡已移除, 这里只会是 L_Villa 自己的)
    # 3) 天空与太阳
    sun = spawn(unreal.DirectionalLight, "Sun", (0, 0, 1500), (SUN["pitch"], SUN["yaw"], 0))
    c = sun.light_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_intensity(SUN["lux"])
    c.set_light_color(unreal.LinearColor(1.0, 0.95, 0.88, 1))
    c.set_editor_property("dynamic_shadow_distance_movable_light", 6000.0)
    if SKY_MODE == "atmosphere":
        # 物理大气: 实测在本模板配置下天空发黑 (原因未查清), 先不用
        c.set_editor_property("atmosphere_sun_light", True)
        spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
    else:
        # 模板自带的天空球 (VRStudy 里实测正常): 蓝天 + 云, 跟着太阳方向
        cls = unreal.load_class(None, "/Engine/EngineSky/BP_Sky_Sphere.BP_Sky_Sphere_C")
        sky = spawn(cls, "SkySphere")
        # 蓝图变量名带空格, Python 里要用原名; 关联太阳后重跑构造脚本, 天空颜色才按太阳高度算
        linked = False
        for prop in ("Directional light actor", "DirectionalLightActor", "directional_light_actor"):
            try:
                sky.set_editor_property(prop, sun)
                linked = True
                break
            except Exception:
                pass
        for prop, val in (("Colors determined by sun position", True),):
            try:
                sky.set_editor_property(prop, val)
            except Exception as e:
                log.append("sky prop {} failed: {}".format(prop, e))
        try:
            sky.rerun_construction_scripts()
        except Exception as e:
            log.append("rerun construction failed: {}".format(e))
        log.append("sky sphere linked to sun: {}".format(linked))
    sl = spawn(unreal.SkyLight, "SkyLight", (0, 0, 800))
    slc = sl.light_component
    slc.set_mobility(unreal.ComponentMobility.MOVABLE)
    slc.set_editor_property("real_time_capture", SKY_MODE == "atmosphere")
    slc.set_intensity(1.0)
    if USE_CLOUDS:  # 体积云: 固定曝光下发灰发脏, VR 里也贵 -> 默认关
        spawn(unreal.VolumetricCloud, "Clouds")
    fog = spawn(unreal.ExponentialHeightFog, "Fog", (0, 0, -300))
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_editor_property("fog_density", 0.004)
    # 4) 室内灯 (灯位_* 标记)
    n = 0
    for a in sub.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("deng_wei_"):
            loc = a.get_actor_location()
            l = spawn(unreal.PointLight, "L_" + lab, (loc.x, loc.y, loc.z - 15))
            lc = l.light_component
            lc.set_mobility(unreal.ComponentMobility.MOVABLE)
            lc.set_intensity(INTERIOR_CD)
            lc.set_light_color(unreal.LinearColor(1.0, 0.82, 0.62, 1))
            lc.set_attenuation_radius(750.0)
            lc.set_cast_shadows(False)  # 9 盏重叠可移动光源; 前向渲染下投影光源最多 4 个重叠
            n += 1
    log.append("interior lights: {}".format(n))
    # 5) 全局后期: 固定曝光
    ppv = spawn(unreal.PostProcessVolume, "PP_Global")
    ppv.set_editor_property("unbound", True)
    s = ppv.settings
    s.set_editor_property("override_auto_exposure_method", True)
    s.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    s.set_editor_property("override_auto_exposure_bias", True)
    s.set_editor_property("auto_exposure_bias", EXPOSURE_BIAS)
    s.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    s.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    ppv.settings = s
    try:
        slc.recapture_sky()
    except Exception:
        pass
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    open(os.path.join(D, "v6_report.txt"), "w", encoding="utf-8").write("\n".join(log))
    print("\n".join(log))


main()
