# -*- coding: utf-8 -*-
"""第 1 步: 新关卡 L_Courtyard (院落别墅)。从 L_Villa 另存 (沿用它的太阳/天空/雾/曝光/VR 出生点/导航体积)。
用法 (分两次, 避免"另存后立刻加载"导致编辑器崩溃):
  py "c1_new_level.py" save     (当前打开 L_Villa 时运行)
  py "c1_new_level.py" load"""
import sys
import unreal

NEW = "/Game/Courtyard/Maps/L_Courtyard"
mode = sys.argv[1] if len(sys.argv) > 1 else "save"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if mode == "save":
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    print("save_map:", unreal.EditorLoadingAndSavingUtils.save_map(world, NEW))
else:
    print("load:", les.load_level(NEW))
