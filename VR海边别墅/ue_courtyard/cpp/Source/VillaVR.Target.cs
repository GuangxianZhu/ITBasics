using UnrealBuildTool;

public class VillaVRTarget : TargetRules
{
	public VillaVRTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("VillaVR");
	}
}
