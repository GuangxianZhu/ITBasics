# -*- coding: utf-8 -*-
"""第 9 步: 烘焙光照 (Lightmass)。
  prep   : 准备 (可重复运行)
           - 灯: 太阳/天光 -> Stationary (直射仍是实时阴影, 间接光烘进光照贴图); 室内外点光源 -> Static + 投影 (阴影烘进去, 运行时 0 开销, 还不漏光)
           - 合并网格 G_*、花盆等固定物: Static, 按面积给光照贴图分辨率 (没有第二套 UV 的自动生成)
           - 植物 PL_*、能抓的东西、AI 家具: Movable (靠体积光照贴图取间接光, 实时投影)
           - World Settings: 允许预计算光照, 间接光反弹 3 次; 在房子周围放一个 Lightmass Importance Volume
  build  : 开始烘焙 (异步, 进度在编辑器右下角; 结束后 py "c9_bake.py" save 保存)
  save   : 保存关卡和光照数据
  revert : 回到全动态 (灯 Movable, 关闭预计算光照), 不用重新烘焙
结果写 c9_report.txt"""
import math
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EAL = unreal.EditorAssetLibrary
LOG = []
LOW_RES_GROUPS = ("Site", "Far")          # 场地/远景: 面积大但不重要
M = unreal.ComponentMobility


def pow2(v):
    return int(2 ** math.ceil(math.log2(max(v, 1))))


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def mesh_lightmap(mesh, group):
    """保证有光照贴图 UV (第 1 套), 按包围盒面积给分辨率。返回分辨率。"""
    nuv = SMES.get_num_uv_channels(mesh, 0)
    if nuv < 2:
        bs = SMES.get_lod_build_settings(mesh, 0)
        bs.set_editor_property("generate_lightmap_u_vs", True)
        bs.set_editor_property("src_lightmap_index", 0)
        bs.set_editor_property("dst_lightmap_index", 1)
        SMES.set_lod_build_settings(mesh, 0, bs)
        LOG.append("  generated lightmap UVs: " + mesh.get_name())
    b = mesh.get_bounding_box()
    dx, dy, dz = [(getattr(b.max, c) - getattr(b.min, c)) / 100.0 for c in "xyz"]
    area = 2 * (dx * dy + dy * dz + dx * dz)
    if group in LOW_RES_GROUPS:
        res = 128
    else:
        res = min(1024, max(64, pow2(math.sqrt(area) * 16)))
    bs = SMES.get_lod_build_settings(mesh, 0)
    bs.set_editor_property("min_lightmap_resolution", res)
    SMES.set_lod_build_settings(mesh, 0, bs)
    mesh.set_editor_property("light_map_coordinate_index", 1)
    mesh.set_editor_property("light_map_resolution", res)
    EAL.save_loaded_asset(mesh)
    return res


def set_mob(a, mob):
    rc = a.root_component
    if rc:
        rc.set_mobility(mob)


def importance_volume():
    for a in EAS.get_all_level_actors():
        if isinstance(a, unreal.LightmassImportanceVolume):
            EAS.destroy_actor(a)
    center = unreal.Vector(19.0 * 100, -14.0 * 100, 0.0)
    half = unreal.Vector(2600, 2000, 700)          # 平面图 x -7~45, y -6~34, z -7~7 m
    a = EAS.spawn_actor_from_class(unreal.LightmassImportanceVolume, center)
    a.set_actor_label("Court_LightmassImportance")
    a.set_folder_path("Courtyard/Lighting")
    o, e = a.get_actor_bounds(False)
    if e.x < 1:
        LOG.append("WARNING: importance volume has no brush")
        return
    s = a.get_actor_scale3d()
    a.set_actor_scale3d(unreal.Vector(s.x * half.x / e.x, s.y * half.y / e.y, s.z * half.z / e.z))
    LOG.append("importance volume ok, extent %s" % str(a.get_actor_bounds(False)[1]))


def prep():
    ws = world().get_world_settings()
    ws.set_editor_property("force_no_precomputed_lighting", False)
    ls = ws.get_editor_property("lightmass_settings")
    ls.set_editor_property("num_indirect_lighting_bounces", 3)
    ls.set_editor_property("num_sky_lighting_bounces", 2)
    ls.set_editor_property("use_ambient_occlusion", True)
    ls.set_editor_property("direct_illumination_occlusion_fraction", 0.5)
    ls.set_editor_property("indirect_illumination_occlusion_fraction", 1.0)
    ls.set_editor_property("compress_lightmaps", True)
    ws.set_editor_property("lightmass_settings", ls)
    importance_volume()
    n = {"static": 0, "movable": 0, "lights_static": 0, "lights_stationary": 0}
    done_meshes = {}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        tags = [str(t) for t in a.tags]
        folder = str(a.get_folder_path())
        if isinstance(a, unreal.DirectionalLight) or isinstance(a, unreal.SkyLight):
            comp = a.light_component if isinstance(a, unreal.DirectionalLight) else a.light_component
            if isinstance(a, unreal.SkyLight):
                comp.set_editor_property("real_time_capture", False)
            set_mob(a, M.STATIONARY)
            n["lights_stationary"] += 1
            continue
        if isinstance(a, (unreal.PointLight, unreal.SpotLight, unreal.RectLight)):
            set_mob(a, M.STATIC)
            a.light_component.set_cast_shadows(True)
            n["lights_static"] += 1
            continue
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        smc = a.static_mesh_component
        mesh = smc.static_mesh
        movable = (lab.startswith("PL_") or lab.startswith("CF_") or lab.startswith("AI_")
                   or "CourtyardGrab" in tags or "CourtyardPlant" in tags)
        if movable:
            set_mob(a, M.MOVABLE)
            n["movable"] += 1
            continue
        if "Courtyard" not in tags or mesh is None:
            continue
        set_mob(a, M.STATIC)
        group = folder.split("/")[-1] if "/" in folder else folder
        if mesh.get_path_name() not in done_meshes:
            done_meshes[mesh.get_path_name()] = mesh_lightmap(mesh, group)
        n["static"] += 1
    res = sorted(done_meshes.values())
    texels = sum(r * r for r in res)
    LOG.append("mobility: %s" % n)
    LOG.append("lightmapped meshes: %d, resolutions min/median/max %d/%d/%d, total %.1f Mtexel"
               % (len(res), res[0], res[len(res) // 2], res[-1], texels / 1e6))
    LES.save_current_level()


def build():
    q = unreal.LightingBuildQuality.QUALITY_MEDIUM if "high" not in sys.argv else unreal.LightingBuildQuality.QUALITY_HIGH
    LOG.append("build_light_maps(%s) -> %s" % (q, LES.build_light_maps(q, True)))


def revert():
    ws = world().get_world_settings()
    ws.set_editor_property("force_no_precomputed_lighting", True)
    for a in EAS.get_all_level_actors():
        if isinstance(a, (unreal.DirectionalLight, unreal.SkyLight, unreal.PointLight, unreal.SpotLight, unreal.RectLight)):
            set_mob(a, M.MOVABLE)
            if isinstance(a, unreal.PointLight):
                a.light_component.set_cast_shadows(False)
    LES.save_current_level()
    LOG.append("reverted to fully dynamic lighting")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prep"
    {"prep": prep, "build": build, "revert": revert, "save": lambda: LOG.append("saved %s" % LES.save_current_level())}[mode]()
    open(os.path.join(D, "c9_report.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    print(" | ".join(LOG))
