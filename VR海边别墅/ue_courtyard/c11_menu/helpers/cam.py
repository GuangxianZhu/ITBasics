import unreal
cam = unreal.load_object(None, "/Game/XRFramework/Blueprints/BP_XRPawn.BP_XRPawn_C:Camera_GEN_VARIABLE")
print(cam, cam.get_editor_property("post_process_blend_weight"))
s = cam.get_editor_property("post_process_settings")
print("before", s.get_editor_property("override_auto_exposure_bias"), s.get_editor_property("auto_exposure_bias"))
s.set_editor_property("override_auto_exposure_bias", True)
s.set_editor_property("auto_exposure_bias", 0.0)
cam.set_editor_property("post_process_settings", s)
cam.set_editor_property("post_process_blend_weight", 0.0)
s2 = cam.get_editor_property("post_process_settings")
print("after", s2.get_editor_property("override_auto_exposure_bias"), s2.get_editor_property("auto_exposure_bias"), cam.get_editor_property("post_process_blend_weight"))
pp = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if a.get_class().get_name()=="PostProcessVolume"][0]
ps = pp.get_editor_property("settings")
print("PP_Global method", ps.get_editor_property("auto_exposure_method"), "bias", ps.get_editor_property("auto_exposure_bias"), "min/max", ps.get_editor_property("auto_exposure_min_brightness"), ps.get_editor_property("auto_exposure_max_brightness"), "ovr", ps.get_editor_property("override_auto_exposure_method"))
