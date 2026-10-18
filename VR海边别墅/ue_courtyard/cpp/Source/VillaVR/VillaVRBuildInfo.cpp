#include "VillaVRBuildInfo.h"

FString UVillaVRBuildInfo::GetBuildInfo()
{
	return FString::Printf(TEXT("VillaVR C++ module OK (built %s %s, MSVC %d)"),
		TEXT(__DATE__), TEXT(__TIME__), _MSC_FULL_VER);
}
