import unreal
L = unreal.BlueprintEditorLibrary
bp = unreal.load_asset("/Game/XRFramework/Blueprints/WBP_Menu")
ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, "EventGraph")
ol = [n for n in ge.list_all_nodes() if str(L.get_node_title(n)) == "Open Level (by Name)"][0]
g = ge.create_node_from_name("Game|GetCurrentLevelName", unreal.Vector2D(900, 1100), [])
rv = [p for p in L.list_all_pins(g) if str(p.get_pin_name()) == "ReturnValue"][0]
ln = [p for p in L.list_input_pins(ol) if str(p.get_pin_name()) == "LevelName"][0]
print("connect", rv.try_create_connection(ln))
print("linked", [(str(L.get_node_title(x.get_owning_node())), str(x.get_pin_name())) for x in ln.list_connected_pins()])
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
print("wbp status", bp.get_editor_property("status"))
for gname in ["EventGraph", "CourtRefresh", "CourtTimeClicked", "CourtTurnClicked"]:
    e = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, gname)
    print(gname, "err", [str(L.get_node_title(n)) for n in e.list_nodes_with_errors()], "warn", [str(L.get_node_title(n)) for n in e.list_nodes_with_warnings()])
pb = unreal.load_asset("/Game/XRFramework/Blueprints/BP_XRPawn")
unreal.BlueprintEditorLibrary.compile_blueprint(pb)
print("pawn status", pb.get_editor_property("status"))
