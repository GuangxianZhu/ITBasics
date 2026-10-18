# uepy rebuild_restart2.py : 保存 /Game 脏资产 -> 关 UE -> 等 DLL 解锁 (改名成功) -> 编 VillaVREditor -> 成功就重开 VillaVR
# 和 rebuild_restart.py 的区别 (README 坑 27): 不等进程号 (从项目浏览器开的编辑器退出后会回到项目浏览器, 进程不结束),
# 而是反复尝试把 UnrealEditor-VillaVR.dll 改名, 改名成功 = 编辑器已经放开 DLL。
# 日志: Unreal Projects/VillaVR/build_log.txt (最后一行 EXITCODE=n)
import os, subprocess, unreal
L = unreal.EditorLoadingAndSavingUtils
L.save_packages([p for p in L.get_dirty_content_packages() if p.get_name().startswith("/Game/")], True)
L.save_dirty_packages(True, False)        # 关卡也存
exe = r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
bat = r"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat"
root = os.path.join(os.path.expanduser("~"), "Documents", "Unreal Projects", "VillaVR")
proj = os.path.join(root, "VillaVR.uproject")
dll_dir = os.path.join(root, "Binaries", "Win64")
log = os.path.join(root, "build_log.txt")
script = os.path.join(root, "Saved", "rebuild_restart2.cmd")
with open(script, "w", encoding="ascii") as f:
    f.write('@echo off\r\n')
    f.write('> "%s" echo waiting for the editor to release the DLL\r\n' % log)
    f.write('set N=0\r\n:wait\r\nset /a N+=1\r\n')
    f.write('if %%N%% GTR 90 (>> "%s" echo EXITCODE=99 DLL still locked & exit /b 99)\r\n' % log)
    f.write('timeout /t 2 /nobreak >nul\r\n')
    f.write('if not exist "%s\\UnrealEditor-VillaVR.dll" goto build\r\n' % dll_dir)
    f.write('ren "%s\\UnrealEditor-VillaVR.dll" "UnrealEditor-VillaVR.dll.old%%RANDOM%%" 2>nul || goto wait\r\n' % dll_dir)
    f.write(':build\r\n')
    f.write('call "%s" VillaVREditor Win64 Development -Project="%s" -WaitMutex -NoHotReloadFromIDE >> "%s" 2>&1\r\n' % (bat, proj, log))
    f.write('set RC=%ERRORLEVEL%\r\n')
    f.write('>> "%s" echo EXITCODE=%%RC%%\r\n' % log)
    f.write('if "%%RC%%"=="0" start "" "%s" "%s"\r\n' % (exe, proj))
flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
try:
    subprocess.Popen('cmd /c "%s"' % script, creationflags=flags | 0x01000000)   # CREATE_BREAKAWAY_FROM_JOB
except OSError:
    subprocess.Popen('cmd /c "%s"' % script, creationflags=flags)
print("rebuild + restart scheduled:", script)
unreal.SystemLibrary.quit_editor()
