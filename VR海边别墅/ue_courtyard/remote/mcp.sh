#!/bin/bash
# 在"连接电脑"的 Linux 外壳 (device_bash) 里用: mcp <toolset>.<tool> '<json 参数>'
# 例: mcp editor_toolset.toolsets.blueprint.BlueprintTools.list_graphs '{"blueprint":{"refPath":"/Game/X/BP.BP"}}'
#     mcp describe UMGToolSet.UMGToolSet        (列出某个工具集的工具和参数)
Q="$HOME/mnt/UE-MCP-Tools/court/mcpq"; id=r$(date +%s%N)
if [ "$1" = describe ]; then
  python3 -c "import json,sys; json.dump({'method':'tools/call','params':{'name':'describe_toolset','arguments':{'toolset_name':sys.argv[1]}}}, open(sys.argv[2],'w'))" "$2" "$Q/$id.tmp"
else
  python3 -c "import json,sys; t=sys.argv[1].rsplit('.',1); json.dump({'method':'tools/call','params':{'name':'call_tool','arguments':{'toolset_name':t[0],'tool_name':t[1],'arguments':json.loads(sys.argv[2])}}}, open(sys.argv[3],'w'))" "$1" "${2:-{\}}" "$Q/$id.tmp"
fi
mv "$Q/$id.tmp" "$Q/$id.json"
for i in $(seq 1 1200); do [ -f "$Q/$id.out" ] && grep -q "#DONE" "$Q/$id.out" && break; sleep 0.5; done
python3 - "$Q/$id.out" <<'PY'
import json,sys
s=open(sys.argv[1],encoding='utf-8-sig').read().replace('#DONE','')
try:
    d=json.loads(s); r=d.get('result',d)
    for c in r.get('content',[]): print(c.get('text',''))
    if r.get('isError'): print('[isError]')
except Exception: print(s)
PY
