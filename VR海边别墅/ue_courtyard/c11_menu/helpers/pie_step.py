import unreal, sys
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
pawn = unreal.GameplayStatics.get_player_pawn(w, 0)
cam = pawn.get_component_by_class(unreal.CameraComponent)
act = sys.argv[1]
if act == "time":
    pawn.call_method("CourtCycleTime")
elif act == "turn":
    pawn.call_method("CourtCycleTurn")
elif act == "look":
    pc = unreal.GameplayStatics.get_player_controller(w, 0)
    pc.set_control_rotation(unreal.Rotator(0, float(sys.argv[2]), float(sys.argv[3])))
sun = unreal.GameplayStatics.get_all_actors_of_class(w, unreal.DirectionalLight)[0]
print("idx", pawn.get_editor_property("CourtTimeIndex"), "label", pawn.call_method("CourtTimeLabel"), "turn", pawn.get_editor_property("SnapTurnDegrees"), pawn.call_method("CourtTurnLabel"))
print("sun", sun.get_actor_rotation(), sun.light_component.intensity, sun.light_component.mobility, "ppw", cam.get_editor_property("post_process_blend_weight"), cam.get_editor_property("post_process_settings").get_editor_property("override_auto_exposure_bias"))
