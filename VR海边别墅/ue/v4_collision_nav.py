# -*- coding: utf-8 -*-
"""
第 4 步: 碰撞 + 导航 + 出生点
  - 所有导入的静态网格: "复杂碰撞当简单碰撞用" (直接拿渲染三角形做碰撞)。
    别墅是静态建筑, 不需要物理模拟, 这样最省事且楼梯/台阶贴合; 代价是碰撞计算比凸包贵 (静态场景影响很小)。
  - 碰撞坡道 (Blender 里叫 "碰撞_*", 拼音 peng_zhuang_*): 不显示, 只挡人 —— 楼梯靠它变成能走/能传送的斜坡。
  - NavMeshBoundsVolume 扩到整个别墅 + 平台 + 步道 (VR 模板的瞬移要在 NavMesh 上落点)。
  - PlayerStart 放在 Godot 版第 1 个参观点位 "01_客厅看海"。
注意: 脚本改完边界后 NavMesh 不会马上生成 (0 tile)。接着跑 v7b_reload_level.py (存盘+重载关卡),
      再在控制台输 RebuildNavigation, 用 v7_check_nav.py 验证。
坐标换算 (导入后实测): UE(厘米) = (100*gx, 100*gz, 100*gy), glTF/Godot 的 -Z (大海) = UE 的 -Y。
"""
import json
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
log = []


def g2ue(p):
    return unreal.Vector(p[0] * 100.0, p[2] * 100.0, p[1] * 100.0)


meshes, n_hidden = {}, 0
for a in sub.get_all_level_actors():
    if not isinstance(a, unreal.StaticMeshActor):
        continue
    smc = a.static_mesh_component
    sm = smc.static_mesh
    if not sm or not sm.get_path_name().startswith("/Game/Villa/Import"):
        continue
    meshes[sm.get_path_name()] = sm
    a.tags = ["Villa"]
    lab = a.get_actor_label()
    if lab.startswith("peng_zhuang"):
        smc.set_visibility(False)
        a.set_actor_hidden_in_game(True)
        n_hidden += 1
for path, sm in meshes.items():
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    EAL.save_loaded_asset(sm)
log.append("complex-as-simple collision on {} meshes; hidden collision ramps: {}".format(len(meshes), n_hidden))

markers = json.load(open(os.path.join(D, "markers.json"), encoding="utf-8"))
p0 = markers["vr_points"][0]
for a in sub.get_all_level_actors():
    if isinstance(a, unreal.PlayerStart):
        loc = g2ue(p0["pos"])
        a.set_actor_location(unreal.Vector(loc.x, loc.y, loc.z + 100), False, True)
        # Godot 里 yaw=0 朝 -Z (大海) = UE 的 -Y, 即 UE yaw -90
        a.set_actor_rotation(unreal.Rotator(0, 0, -90 - p0.get("yaw_deg", 0)), True)
        log.append("PlayerStart -> {} at {}".format(p0["name"], loc))
    if isinstance(a, unreal.NavMeshBoundsVolume):
        center, half = unreal.Vector(300, -300, 250), unreal.Vector(1700, 1500, 550)
        o, e = a.get_actor_bounds(False)
        s = a.get_actor_scale3d()
        # 用 set_editor_property 改根组件的变换: 它会触发 PostEditChange (和在细节面板里手动改一样),
        # 导航系统才会登记新的边界; 直接 set_actor_location 不会 -> 第一版重建导航后一块网格都没有
        rc = a.root_component
        rc.set_editor_property("relative_location", center)
        rc.set_editor_property("relative_scale3d", unreal.Vector(s.x * half.x / max(e.x, 1), s.y * half.y / max(e.y, 1),
                                                                 s.z * half.z / max(e.z, 1)))
        # 脚本改变换不会触发编辑器的"移动完成"事件, 导航系统不知道边界变了 -> 手动通知, 再全量重建
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        ns = unreal.NavigationSystemV1.get_navigation_system(world)
        if ns:
            ns.on_navigation_bounds_updated(a)
        unreal.SystemLibrary.execute_console_command(world, "RebuildNavigation")
        log.append("NavMeshBoundsVolume -> center {} half {} (nav rebuild requested)".format(center, half))
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
open(os.path.join(D, "v4_report.txt"), "w", encoding="utf-8").write("\n".join(log))
print("\n".join(log))
