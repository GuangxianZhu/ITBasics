# uepy build_check.py <工程名> [目标]   编辑器开着时检查 C++ 能不能编过: 编 "游戏" 目标 (不碰编辑器正在用的 DLL)
# 默认目标 <工程名> (Win64 Development 游戏 exe)。日志 build_check_log.txt, 结尾 EXITCODE=n
# 编过了再按 README 坑 26 的方法重编编辑器 DLL
import subprocess, os, sys
name = sys.argv[1]
target = sys.argv[2] if len(sys.argv) > 2 else name
proj = os.path.expanduser(r"~\Documents\Unreal Projects\%s\%s.uproject" % (name, name))
bat = r"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat"
log = os.path.join(os.path.dirname(proj), "build_check_log.txt")
cmd = f'"{bat}" {target} Win64 Development -Project="{proj}" -WaitMutex -NoHotReloadFromIDE'
f = open(log, "w", encoding="utf-8")
p = subprocess.Popen(f'cmd /c "{cmd} & echo EXITCODE=%ERRORLEVEL%"', stdout=f, stderr=subprocess.STDOUT, creationflags=0x08000000)
print("started", p.pid, log)
