import unreal, sys, re
bp = unreal.load_asset(sys.argv[1])
ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, sys.argv[2])
names = ge.list_available_nodes([])
pat = re.compile(sys.argv[3])
print(len(names)); print("\n".join(n for n in names if pat.search(n))[:6000])
