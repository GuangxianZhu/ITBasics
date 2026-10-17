# -*- coding: utf-8 -*-
"""把工程默认关卡 (编辑器启动 + 游戏默认) 设为 L_Study。原值: /Game/XRFramework/Levels/L_XRTemplate"""
import unreal

MAP = "/Game/ClaudeVR/Maps/L_Study.L_Study"
s = unreal.get_default_object(unreal.GameMapsSettings)
path = unreal.SoftObjectPath(MAP)
s.set_editor_property("editor_startup_map", path)
s.set_editor_property("game_default_map", path)
try:
    s.save_config()  # 写入 Config/DefaultEngine.ini
except Exception as e:
    print("save_config failed:", e)
print("default maps ->", MAP)
