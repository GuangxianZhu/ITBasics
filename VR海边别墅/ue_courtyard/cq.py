# -*- coding: utf-8 -*-
"""命令队列: 依次执行 cq.txt 里的每一行, 然后清空 cq.txt。
  "c9_bake.py build"   -> 运行同目录脚本 (带参数)
  "!RebuildNavigation" -> 执行控制台命令
远程操作时只要反复运行同一条 py "…/cq.py" (控制台里按 ↑ 回车), 不用每次输入长路径。"""
import os
import runpy
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
q = os.path.join(D, "cq.txt")
lines = [l.strip() for l in open(q, encoding="utf-8").read().splitlines() if l.strip()] if os.path.exists(q) else []
open(q, "w").close()
for l in lines:
    print("cq> " + l)
    if l.startswith("!"):
        unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), l[1:])
        continue
    parts = l.split()
    old = sys.argv
    sys.argv = [os.path.join(D, parts[0])] + parts[1:]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        sys.argv = old
print("cq done: %d" % len(lines))
