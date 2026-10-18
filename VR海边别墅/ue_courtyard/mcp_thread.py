# -*- coding: utf-8 -*-
"""远程操作用: 在编辑器里开一个后台线程, 把 court/mcpq/*.json (method + params) 转发给本机 MCP 服务器, 结果写 .out。
(MCP 工具本身在游戏线程执行, 后台线程只负责收发, 所以不会卡住编辑器。)"""
import builtins, json, os, threading, time, urllib.request
URL = "http://127.0.0.1:8000/mcp"
Q = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court", "mcpq")
os.makedirs(Q, exist_ok=True)
builtins._court_mcp_gen = getattr(builtins, "_court_mcp_gen", 0) + 1
GEN = builtins._court_mcp_gen
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
S = {"sid": None, "id": 100}

def post(obj, timeout=900):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if S["sid"]: h["Mcp-Session-Id"] = S["sid"]
    req = urllib.request.Request(URL, data=json.dumps(obj).encode("utf-8"), headers=h, method="POST")
    with op.open(req, timeout=timeout) as r:
        if r.headers.get("Mcp-Session-Id"): S["sid"] = r.headers.get("Mcp-Session-Id")
        raw = r.read().decode("utf-8", "replace")
    lines = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
    return "\n".join(lines) if lines else raw

def init():
    S["sid"] = None
    post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "court", "version": "1"}}}, 30)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, 30)

def loop():
    while builtins._court_mcp_gen == GEN:
        for f in sorted(os.listdir(Q)):
            if not f.endswith(".json"): continue
            p = os.path.join(Q, f)
            try:
                req = json.load(open(p, encoding="utf-8-sig")); os.remove(p)
            except Exception:
                continue
            S["id"] += 1
            body = {"jsonrpc": "2.0", "id": S["id"], "method": req["method"], "params": req.get("params", {})}
            try:
                if not S["sid"]: init()
                try: res = post(body)
                except Exception: init(); res = post(body)
            except Exception as e:
                res = "ERROR: %r" % e
            open(p[:-5] + ".out", "w", encoding="utf-8").write(res + "\n#DONE\n")
        time.sleep(0.3)

threading.Thread(target=loop, daemon=True).start()
print("mcp thread gen", GEN)
