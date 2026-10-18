import unreal, sys
L = unreal.BlueprintEditorLibrary
bp = unreal.load_asset(sys.argv[1])
for g in sys.argv[2:]:
    ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, g)
    for n in ge.list_all_nodes():
        vals = []
        for p in L.list_input_pins(n):
            v = p.get_pin_value()
            if v != "" : vals.append("%s=%s" % (p.get_pin_name(), v))
        print(g, "|", L.get_node_title(n), "|", vals)
