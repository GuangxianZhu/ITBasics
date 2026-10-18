# c12_faucet.py : 在香草厨园石水槽上方装可交互的球阀龙头 (C++ 类 AVillaFaucet)
# 位置来自 c2_build.py: 石水槽 box(12.0-13.2, 10.75-11.05, z 0.05-0.85), 墙上金属板 Tap box(12.4-12.8, 10.78-10.85, z 0.85-1.15)
# 龙头本地坐标: +X 垂直墙面向外, 原点 = 金属板前表面、水管高度 1.05 m
import unreal

EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
LABEL = "INT_HerbTap"

for a in EAS.get_all_level_actors():
    if a.get_actor_label() == LABEL:
        EAS.destroy_actor(a)

def V(x, y, z):  # 平面图米制 -> UE 厘米 (和 c2_build.py 一致)
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)

loc = V(12.6, 10.85, 1.05)
rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=-90.0)   # 本地 +X -> 世界 -Y (= 平面图 +y, 朝院子)
a = EAS.spawn_actor_from_class(unreal.VillaFaucet, loc, rot)
a.set_actor_label(LABEL)
a.set_folder_path("Courtyard/Interactive")
a.set_editor_property("water_drop_length", (1.05 - 0.07 - 0.85) * 100.0)   # 出水口到水槽面
LES.save_current_level()
o = a.get_outlet_location()
print("placed", LABEL, "outlet", round(o.x), round(o.y), round(o.z))
