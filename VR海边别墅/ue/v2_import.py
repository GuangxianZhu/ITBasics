# -*- coding: utf-8 -*-
"""
第 2 步: 用 Interchange "导入场景" 把 villa_ue.glb 导入到当前关卡 (保留物体名字和变换)。
资产放在 /Game/Villa/Import。导入是异步的: 脚本只负责发起, 等编辑器处理完再跑第 3 步。
"""
import os

import unreal

GLB = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "villa", "villa_ue.glb").replace("\\", "/")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world.get_path_name().startswith("/Game/Villa/Maps/L_Villa"):
    raise RuntimeError("open L_Villa first")
mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
sd = unreal.InterchangeManager.create_source_data(GLB)
p = unreal.ImportAssetParameters()
p.is_automated = True
p.replace_existing = True
print("import_scene started:", mgr.import_scene("/Game/Villa/Import", sd, p), GLB)
