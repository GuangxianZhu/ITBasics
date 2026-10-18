# uepy restart_ue.py : 保存 /Game 下的脏资产, 关掉编辑器, 15 秒后自动重新打开 VillaVR (不用点启动器)
import os, subprocess, unreal
L = unreal.EditorLoadingAndSavingUtils
L.save_packages([p for p in L.get_dirty_content_packages() if p.get_name().startswith("/Game/")], True)
exe = r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
proj = os.path.join(os.path.expanduser("~"), "Documents", "Unreal Projects", "VillaVR", "VillaVR.uproject")
subprocess.Popen('cmd /c "timeout /t 15 /nobreak >nul & start "" "%s" "%s""' % (exe, proj),
                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, shell=False)
print("restarting in 15 s")
unreal.SystemLibrary.quit_editor()
