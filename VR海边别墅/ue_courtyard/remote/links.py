import unreal, sys
L = unreal.BlueprintEditorLibrary
bp = unreal.load_asset(sys.argv[1])
for g in sys.argv[2:]:
    ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, g)
    for n in ge.list_all_nodes():
        t = L.get_node_title(n)
        for p in L.list_all_pins(n) if hasattr(L, "list_all_pins") else []:
            c = p.list_connected_pins()
            if c and p.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_OUTPUT:
                print(g, "|", t, ".", p.get_pin_name(), "->", [(L.get_node_title(x.get_owning_node()), str(x.get_pin_name())) for x in c])
