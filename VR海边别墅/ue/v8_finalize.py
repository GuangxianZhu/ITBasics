# -*- coding: utf-8 -*-
"""收尾: 保存 L_Villa (含已生成的 NavMesh), 并把编辑器启动关卡 + 游戏默认关卡设为 L_Villa。
原值: /Game/XRFramework/Levels/L_XRTemplate.L_XRTemplate (模板关卡本身没动)"""
import unreal

MAP = "/Game/Villa/Maps/L_Villa.L_Villa"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
print("save level:", les.save_current_level())

# GameMapsSettings 在 5.8 Python 里没有 save_config(), 直接改 Config/DefaultEngine.ini (第一次改前备份)
import os, re, shutil
ini = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_config_dir()), "DefaultEngine.ini")
bak = ini + ".before_claude"
if not os.path.exists(bak):
    shutil.copy2(ini, bak)
txt = open(ini, encoding="utf-8", newline="").read()  # 保留 CRLF
for k in ("EditorStartupMap", "GameDefaultMap"):
    txt = re.sub(r"(?m)^%s=[^\r\n]*" % k, "%s=%s" % (k, MAP), txt)
open(ini, "w", encoding="utf-8", newline="").write(txt)
print("default maps ->", MAP, "(", ini, ")")
