# -*- coding: utf-8 -*-
"""修 NavMesh: v4 用脚本挪/缩放 NavMeshBoundsVolume 后, RebuildNavigation 一直 0 个 tile (0.00s)。
实测: 保存并重新加载关卡后, 导航系统才认新边界。之后在控制台再输 RebuildNavigation, 然后跑 v7_check_nav.py。"""
import unreal

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ok = les.save_current_level()
unreal.log("saved: %s" % ok)
les.load_level("/Game/Villa/Maps/L_Villa")
unreal.log("reloaded L_Villa")
