using UnrealBuildTool;

public class VillaVREditorTarget : TargetRules
{
	public VillaVREditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("VillaVR");
	}
}
