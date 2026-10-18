# uepy rebuild_restart.py : 保存 /Game 脏资产 -> 关 UE -> 编译 VillaVREditor -> 成功才重开 VillaVR
# 日志: Unreal Projects/VillaVR/build_log.txt (最后一行 EXITCODE=n); 失败时 UE 不会重开, 修好代码后再跑 build_cpp.py + 手动/启动器打开
import os, subprocess, unreal
L = unreal.EditorLoadingAndSavingUtils
L.save_packages([p for p in L.get_dirty_content_packages() if p.get_name().startswith("/Game/")], True)
exe = r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
bat = r"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat"
proj = os.path.join(os.path.expanduser("~"), "Documents", "Unreal Projects", "VillaVR", "VillaVR.uproject")
log = os.path.join(os.path.dirname(proj), "build_log.txt")
script = os.path.join(os.path.dirname(proj), "Saved", "rebuild_restart.cmd")
with open(script, "w", encoding="ascii") as f:
    f.write('@echo off\r\n')
    # wait only for THIS editor process (a leftover project-browser UnrealEditor.exe must not block us)
    f.write(':wait\r\ntasklist /FI "PID eq %d" | find "%d" >nul\r\nif not errorlevel 1 (timeout /t 2 /nobreak >nul & goto wait)\r\n' % (os.getpid(), os.getpid()))
    f.write('call "%s" VillaVREditor Win64 Development -Project="%s" -WaitMutex -NoHotReloadFromIDE > "%s" 2>&1\r\n' % (bat, proj, log))
    f.write('set RC=%%ERRORLEVEL%%\r\n>> "%s" echo EXITCODE=%%RC%%\r\n' % log)
    f.write('if "%%RC%%"=="0" start "" "%s" "%s"\r\n' % (exe, proj))
subprocess.Popen('cmd /c "%s"' % script, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000)
print("rebuild + restart scheduled")
unreal.SystemLibrary.quit_editor()
