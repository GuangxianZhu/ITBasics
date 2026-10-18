#!/bin/bash
# usage: uepy script.py [args...]  -> runs in UE editor via the drop box, prints output
Q="$HOME/mnt/UE-MCP-Tools/court/pyq"; id=u$(date +%s%N)
{ echo "import sys; sys.argv=['x'] + $(python3 -c 'import sys,json; print(json.dumps(sys.argv[1:]))' "${@:2}")"; cat "$1"; } > "$Q/$id.tmp"; mv "$Q/$id.tmp" "$Q/$id.py"
for i in $(seq 1 600); do [ -f "$Q/$id.out" ] && grep -q "#DONE" "$Q/$id.out" && break; sleep 0.5; done
cat "$Q/$id.out"
