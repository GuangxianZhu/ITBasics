#!/bin/bash
# usage: dsl <graphRefPath> <file>
python3 -c "import json,sys; print(json.dumps({'graph':{'refPath':sys.argv[1]},'code':open(sys.argv[2]).read()}))" "$1" "$2" > $HOME/.dsl.json
$HOME/bin/mcp editor_toolset.toolsets.blueprint.BlueprintTools.write_graph_dsl "$(cat $HOME/.dsl.json)"
