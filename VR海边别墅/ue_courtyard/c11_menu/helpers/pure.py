import unreal
bp = unreal.load_asset("/Game/XRFramework/Blueprints/BP_XRPawn")
for g in ["CourtTimeLabel", "CourtTurnLabel"]:
    ge = unreal.BlueprintGraphEditor.get_graph_editor_by_name(bp, g)
    ge.set_is_pure_function(True)
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
print("ok", bp.get_editor_property("status"))
