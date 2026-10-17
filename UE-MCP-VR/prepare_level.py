# -*- coding: utf-8 -*-
"""
第 1 步: 把 XR 模板关卡复制成 /Game/ClaudeVR/Maps/L_Study, 再清掉模板的演示几何体。

为什么复制而不是新建空关卡:
  VR 模板的传送移动依赖 NavMesh (NavMeshBoundsVolume + RecastNavMesh), 还有 VRSpectator、
  Passthrough、天空球等配置。用 Python 生成的 NavMeshBoundsVolume 没有 brush 几何,
  导航会失效, 所以保留模板里现成的, 只删演示用的墙/方块/手枪等。
  删除只发生在复制出来的新关卡里, 原模板关卡 L_XRTemplate 不动。
"""
import unreal

SRC = "/Game/XRFramework/Levels/L_XRTemplate"
DST = "/Game/ClaudeVR/Maps/L_Study"

EAL = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# 注意: 不能用 EditorAssetLibrary.duplicate_asset 复制关卡再 load_level ——
# 复制出来的 World 留在内存里, 加载时触发 "Old world not cleaned up by GC" 致命错误 (实测会崩)。
# 正确做法: 打开模板关卡, 用 "另存为" (save_map) 存成新包, 编辑器随即切换到新关卡。
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if EAL.does_asset_exist(DST):
    if not world.get_path_name().startswith(DST):
        les.load_level(DST)
else:
    if not world.get_path_name().startswith(SRC):
        les.load_level(SRC)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    ok = unreal.EditorLoadingAndSavingUtils.save_map(world, DST)
    print("save_map as", DST, "->", ok)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
print("current world:", world.get_path_name())
if not world.get_path_name().startswith(DST):
    raise RuntimeError("not in L_Study, abort to avoid touching the template level")

KEEP_CLASSES = {
    "WorldSettings", "PlayerStart", "NavMeshBoundsVolume", "RecastNavMesh", "VRSpectator_C",
    "BP_Passthrough_C", "DirectionalLight", "SkyLight", "BP_Sky_Sphere_C", "SphereReflectionCapture",
    "LightmassImportanceVolume", "InstancedFoliageActor", "BP_Grabbable_SmallCube_C", "Brush",
    "AbstractNavData", "GameplayDebuggerPlayerManager", "ChaosDebugDrawActor",
}
removed = []
for a in sub.get_all_level_actors():
    cls = a.get_class().get_name()
    if cls in KEEP_CLASSES or "ClaudeStudy" in [str(t) for t in a.tags]:
        continue
    removed.append("{} ({})".format(a.get_actor_label(), cls))
    sub.destroy_actor(a)
les.save_current_level()
print("L_Study ready; removed {} template actors:".format(len(removed)))
for r in removed:
    print("  -", r)
