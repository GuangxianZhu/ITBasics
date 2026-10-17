# -*- coding: utf-8 -*-
"""
第 1 步: XR 模板关卡"另存为" /Game/Villa/Maps/L_Villa, 删模板演示几何体 (保留 NavMesh/出生点/VR观察者/天空/灯光子关卡)。
注意: 另存为 (save_map) 之后不能在同一次运行里 load_level 刚存的新关卡 (会触发 GC 致命错误),
所以要运行两次: 第一次另存为, 第二次加载并清理。
"""
import unreal

SRC = "/Game/XRFramework/Levels/L_XRTemplate"
DST = "/Game/Villa/Maps/L_Villa"
EAL = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

world = ues.get_editor_world()
if not EAL.does_asset_exist(DST):
    if not world.get_path_name().startswith(SRC):
        les.load_level(SRC)
        world = ues.get_editor_world()
    print("save_map ->", unreal.EditorLoadingAndSavingUtils.save_map(world, DST))
    print("RUN AGAIN to load and clean L_Villa")
else:
    if not world.get_path_name().startswith(DST):
        les.load_level(DST)
    world = ues.get_editor_world()
    if not world.get_path_name().startswith(DST):
        raise RuntimeError("not in L_Villa")
    KEEP = {"WorldSettings", "PlayerStart", "NavMeshBoundsVolume", "RecastNavMesh", "VRSpectator_C",
            "BP_Passthrough_C", "DirectionalLight", "SkyLight", "BP_Sky_Sphere_C", "SphereReflectionCapture",
            "LightmassImportanceVolume", "InstancedFoliageActor", "Brush", "AbstractNavData",
            "GameplayDebuggerPlayerManager", "ChaosDebugDrawActor"}
    removed = 0
    for a in sub.get_all_level_actors():
        cls = a.get_class().get_name()
        if cls in KEEP or "Villa" in [str(t) for t in a.tags]:
            continue
        sub.destroy_actor(a)
        removed += 1
    les.save_current_level()
    print("L_Villa ready, removed", removed, "template actors")
