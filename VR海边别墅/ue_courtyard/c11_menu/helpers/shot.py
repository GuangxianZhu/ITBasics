import unreal, sys
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
unreal.SystemLibrary.execute_console_command(w, "HighResShot 1280x720 filename=" + sys.argv[1])
print("shot", sys.argv[1])
