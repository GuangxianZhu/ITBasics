#!/bin/bash
# 把 DSL 文件写进蓝图图表: dsl <图表 refPath> <file.lisp>
# 例: dsl /Game/XRFramework/Blueprints/BP_XRPawn.BP_XRPawn:CourtSetSun sun.lisp
# 自动: 切英文 -> 写入 -> 切回中文 (中文界面下 DSL 会把执行引脚接错)
T="$(dirname "$0")"
"$T/uepy.sh" "$T/lang.py" en >/dev/null
python3 -c "import json,sys; print(json.dumps({'graph':{'refPath':sys.argv[1]},'code':open(sys.argv[2]).read()}))" "$1" "$2" > /tmp/.dsl.json
"$T/mcp.sh" editor_toolset.toolsets.blueprint.BlueprintTools.write_graph_dsl "$(cat /tmp/.dsl.json)"
"$T/uepy.sh" "$T/lang.py" zh-Hans >/dev/null
