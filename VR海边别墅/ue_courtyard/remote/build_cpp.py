# uepy build_cpp.py <工程名>   在后台编译 <工程名>Editor（Win64 Development），日志写到工程目录 build_log.txt，结尾一行 EXITCODE=n
# 用法: ./uepy.sh build_cpp.py VillaVR ; 然后轮询 "Unreal Projects/VillaVR/build_log.txt" 等 EXITCODE
# 注意: 编辑器开着 VillaVR 时编 VillaVR，新 DLL 要重启 UE（./uepy.sh restart_ue.py）才会加载
import subprocess, os, sys
name = sys.argv[1]
proj = os.path.expanduser(r"~\Documents\Unreal Projects\%s\%s.uproject" % (name, name))
bat = r"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat"
log = os.path.join(os.path.dirname(proj), "build_log.txt")
cmd = f'"{bat}" {name}Editor Win64 Development -Project="{proj}" -WaitMutex -NoHotReloadFromIDE'
f = open(log, "w", encoding="utf-8")
p = subprocess.Popen(f'cmd /c "{cmd} & echo EXITCODE=%ERRORLEVEL%"', stdout=f, stderr=subprocess.STDOUT, creationflags=0x08000000)
print("started", p.pid, log)
