# -*- coding: utf-8 -*-
"""第 9 步: 给自建材质打上 "用于 Nanite" 标记。
原因: Interchange 导入的静态网格默认开了 Nanite。前向渲染 (VR 模板默认) 不支持 Nanite, 走的是回退网格,
所以 forward 模式下看不出问题; 切到延迟渲染 + Lumen 后 Nanite 生效, 材质没这个标记就会被换成默认灰材质
(编辑器 "地图检测" 会警告 "缺失使用标记 Nanite")。结果写 v9_report.txt。"""
import os

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa")
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
out = []
for path in EAL.list_assets("/Game/Villa/Materials", recursive=True, include_folder=False):
    a = EAL.load_asset(path)
    if isinstance(a, unreal.Material):
        try:
            need = MEL.set_material_usage(a, unreal.MaterialUsage.MATUSAGE_NANITE)
        except Exception as e:
            need = "ERR %s" % e
        try:
            MEL.recompile_material(a)
        except Exception as e:
            out.append("recompile %s: %s" % (a.get_name(), e))
        EAL.save_loaded_asset(a)
        out.append("%s nanite_usage set (needs_recompile=%s)" % (a.get_name(), need))

nan_on = nan_off = 0
for path in EAL.list_assets("/Game/Villa/Import", recursive=True, include_folder=False):
    if "/StaticMeshes/" not in path:
        continue
    m = EAL.load_asset(path)
    if isinstance(m, unreal.StaticMesh):
        try:
            on = m.get_editor_property("nanite_settings").get_editor_property("enabled")
        except Exception:
            on = None
        if on:
            nan_on += 1
        else:
            nan_off += 1
out.insert(0, "static meshes nanite on=%d off=%d" % (nan_on, nan_off))
open(os.path.join(D, "v9_report.txt"), "w", encoding="utf-8").write("\n".join(out))
print(out[0], "| materials fixed:", len(out) - 1)
