#!/bin/bash
# usage: mcp <tool_name> '<json args>'   -> prints text result
Q="$HOME/mnt/UE-MCP-Tools/court/mcpq"; id=r$(date +%s%N)
python3 -c "import json,sys; json.dump({'method':'tools/call','params':{'name':'call_tool','arguments':{'toolset_name':sys.argv[1].rsplit('.',1)[0],'tool_name':sys.argv[1].rsplit('.',1)[1],'arguments':json.loads(sys.argv[2])}}}, open(sys.argv[3],'w'))" "$1" "${2:-{\}}" "$Q/$id.json"
for i in $(seq 1 600); do [ -f "$Q/$id.out" ] && grep -q "#DONE" "$Q/$id.out" && break; sleep 0.5; done
python3 - "$Q/$id.out" <<'PY'
import json,sys
s=open(sys.argv[1],encoding='utf-8-sig').read().replace('#DONE','')
try:
    d=json.loads(s); r=d.get('result',d)
    for c in r.get('content',[]): print(c.get('text',''))
    if r.get('isError'): print('[isError]')
except Exception: print(s)
PY
