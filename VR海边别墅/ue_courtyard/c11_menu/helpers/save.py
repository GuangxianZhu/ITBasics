import unreal
E = unreal.EditorAssetLibrary
for a in ["/Game/XRFramework/Blueprints/BP_XRPawn", "/Game/XRFramework/Blueprints/WBP_Menu", "/Game/XRFramework/Input/IMC_Default"]:
    print(a, E.save_asset(a, only_if_is_dirty=False))
print("dirty", [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()])
