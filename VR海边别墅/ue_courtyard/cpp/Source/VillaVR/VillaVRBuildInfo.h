#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VillaVRBuildInfo.generated.h"

// Smoke test: proves the VillaVR C++ module is compiled and loaded.
// Python: unreal.VillaVRBuildInfo.get_build_info()
UCLASS()
class VILLAVR_API UVillaVRBuildInfo : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintPure, Category = "VillaVR")
	static FString GetBuildInfo();
};
