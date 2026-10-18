import unreal
L = unreal.BlueprintEditorLibrary
bp = unreal.load_asset("/Game/XRFramework/Blueprints/WBP_Menu")
ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, "EventGraph")
nodes = ge.list_all_nodes()
def title(n): return str(L.get_node_title(n))
def outpin(n, name):
    for p in L.list_all_pins(n):
        if str(p.get_pin_name()) == name and p.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_OUTPUT: return p
def inpin(n, name):
    for p in L.list_all_pins(n):
        if str(p.get_pin_name()) == name and p.get_pin_direction() == unreal.EdGraphPinDirection.EGPD_INPUT: return p
for n in nodes:
    print(title(n), L.get_node_pos(n), [ (str(p.get_pin_name()), len(p.list_connected_pins())) for p in L.list_all_pins(n) if p.get_pin_direction()==unreal.EdGraphPinDirection.EGPD_OUTPUT][:3])
byt = {title(n): n for n in nodes}
def call(fn, x, y):
    n = ge.create_node_from_name("CallFunction|" + fn, unreal.Vector2D(x, y), [])
    print("created", fn, n)
    return n
pairs = [("Event Construct", "CourtRefresh", 300, 144), ("On Clicked (TimeButton)", "CourtTimeClicked", 300, 2464), ("On Clicked (TurnButton)", "CourtTurnClicked", 300, 2720)]
for ev, fn, x, y in pairs:
    e = byt[ev]
    c = call(fn, x, y)
    print(ev, "->", fn, outpin(e, "then").try_create_connection(inpin(c, "execute")))
ol = byt["Open Level (by Name)"]
print("OpenLevel pins", [(str(p.get_pin_name()), p.get_pin_value()) for p in L.list_input_pins(ol)])
