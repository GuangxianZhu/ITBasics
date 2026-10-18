import unreal
imc = unreal.load_asset("/Game/XRFramework/Input/IMC_Default")
ia = unreal.load_asset("/Game/XRFramework/Input/Actions/IA_Turn")
have = [str(m.get_editor_property("key").get_editor_property("key_name")) for m in imc.get_editor_property("default_key_mappings").get_editor_property("mappings")]
for k in ["OculusTouch_Right_Thumbstick_X", "PICO_Right_Thumbstick_X", "ValveIndex_Right_Thumbstick_X"]:
    if k in have:
        print("exists", k); continue
    key = unreal.Key(); key.set_editor_property("key_name", k); m = imc.map_key(ia, key)
    print("mapped", k, m.get_editor_property("key").get_editor_property("key_name"))
for m in imc.get_editor_property("default_key_mappings").get_editor_property("mappings"):
    if m.get_editor_property("action") == ia:
        print("IA_Turn <-", m.get_editor_property("key").get_editor_property("key_name"))
