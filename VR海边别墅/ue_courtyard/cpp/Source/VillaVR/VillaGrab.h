#pragma once

#include "CoreMinimal.h"

class UActorComponent;
class USceneComponent;
class AActor;

// Bridge to the VR template's Blueprint grab component (/Game/XRFramework/Blueprints/BP_GrabComponent).
// We read/write its Blueprint variables by reflection, so no Blueprint wiring is needed:
//   bIsHeld (bool), MotionControllerRef (MotionControllerComponent), GrabType (E_GrabType: Free/Snap/Custom)
// With GrabType = Custom, TryGrab only stores the hand + plays a haptic; it does NOT attach the object.
namespace VillaGrab
{
	// Spawn a BP_GrabComponent under Parent at RelLocation and set its GrabType to Custom. Call from BeginPlay.
	VILLAVR_API UActorComponent* AddCustomGrab(AActor* Owner, USceneComponent* Parent, const FVector& RelLocation);

	// Read held state. OutController is the MotionControllerComponent holding it (or null).
	VILLAVR_API bool ReadHeld(const UActorComponent* Grab, USceneComponent*& OutController);

	// Set an enum/byte Blueprint variable by the enumerator's display name ("Custom").
	VILLAVR_API bool SetEnumByDisplayName(UObject* Obj, FName Property, const FString& DisplayName);

	// Short haptic pulse on the hand that owns Controller (MotionSource "Left"/"Right").
	VILLAVR_API void Pulse(const UObject* WorldContext, const USceneComponent* Controller, float Amplitude, float Seconds = 0.03f);
}
