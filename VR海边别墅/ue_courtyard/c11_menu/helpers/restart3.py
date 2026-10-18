import unreal
L = unreal.BlueprintEditorLibrary
bp = unreal.load_asset("/Game/XRFramework/Blueprints/WBP_Menu")
ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, "EventGraph")
N = {str(L.get_node_title(n)): n for n in ge.list_all_nodes()}
def pin(n, name, d):
    return [p for p in L.list_all_pins(n) if str(p.get_pin_name()) == name and p.get_pin_direction() == d][0]
O, I = unreal.EdGraphPinDirection.EGPD_OUTPUT, unreal.EdGraphPinDirection.EGPD_INPUT
dthen = pin(N["Delay"], "then", O)
print("delay then ->", [(str(L.get_node_title(x.get_owning_node()))) for x in dthen.list_connected_pins()])
olx = pin(N["Open Level (by Name)"], "execute", I)
dthen.break_single_pin_link(olx)
g = N["GetCurrentLevelName"]
print(dthen.try_create_connection(pin(g, "execute", I)), pin(g, "then", O).try_create_connection(olx))
L.compile_blueprint(bp)
print("wbp status", bp.get_editor_property("status"))
