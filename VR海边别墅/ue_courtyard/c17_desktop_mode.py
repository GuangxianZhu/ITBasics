# -*- coding: utf-8 -*-
"""第 17 步: 关卡的 GameMode 换成 C++ 的 VillaGameMode -> 不戴头显点"运行"就是桌面模式 (WASD/跳/交互/菜单),
"VR 预览"仍然是原来的 BP_XRPawn。代码在 cpp/Source/VillaVR/VillaGameMode.* 和 VillaDesktopCharacter.*。
用法: c17_desktop_mode.py          换成 VillaGameMode
      c17_desktop_mode.py revert   换回模板的 BP_XRGameMode"""
import sys

import unreal

w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
ws = w.get_world_settings()
if "revert" in sys.argv[1:]:
    gm = unreal.EditorAssetLibrary.load_blueprint_class("/Game/XRFramework/Blueprints/BP_XRGameMode")
else:
    gm = unreal.VillaGameMode.static_class()
ws.set_editor_property("default_game_mode", gm)
print("GameMode override:", ws.get_editor_property("default_game_mode"),
      "saved:", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
