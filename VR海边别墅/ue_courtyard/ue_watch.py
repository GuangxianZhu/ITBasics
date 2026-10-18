# -*- coding: utf-8 -*-
"""远程操作用的"投递箱": 每 0.5 秒看一次 court/pyq/ 里有没有 .py, 有就在编辑器里执行,
输出写到同名 .out, 然后删掉 .py。只需在 UE 控制台运行一次:
    py "C:/Users/12192/Documents/UE-MCP-Tools/court/ue_watch.py"
再运行一次 = 重新注册 (不会重复)。py ue_watch.py stop = 停止。"""
import builtins
import io
import os
import sys
import traceback

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
Q = os.path.join(D, "pyq")
os.makedirs(Q, exist_ok=True)

old = getattr(builtins, "_court_watch_handle", None)
if old is not None:
    unreal.unregister_slate_post_tick_callback(old)
    builtins._court_watch_handle = None

_acc = [0.0]


def _tick(dt):
    _acc[0] += dt
    if _acc[0] < 0.5:
        return
    _acc[0] = 0.0
    try:
        names = sorted(f for f in os.listdir(Q) if f.endswith(".py"))
    except Exception:
        return
    for f in names:
        p = os.path.join(Q, f)
        try:
            src = open(p, encoding="utf-8").read()
            os.remove(p)
        except Exception:
            continue
        buf = io.StringIO()
        so, se = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = buf
        try:
            exec(compile(src, p, "exec"), {"__name__": "__main__", "__file__": p})
        except Exception:
            traceback.print_exc(file=buf)
        finally:
            sys.stdout, sys.stderr = so, se
        open(p[:-3] + ".out", "w", encoding="utf-8").write(buf.getvalue() + "\n#DONE\n")


if not (len(sys.argv) > 1 and sys.argv[1] == "stop"):
    builtins._court_watch_handle = unreal.register_slate_post_tick_callback(_tick)
    print("court watch: listening on " + Q)
else:
    print("court watch stopped")
