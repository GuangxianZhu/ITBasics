#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "RotaryHandleComponent.generated.h"

// A handle that turns around its parent's Z axis when grabbed in VR (faucet lever, valve, knob...).
// Children of this component turn with it. RelativeRotation.Yaw = -Angle.
// Hand tracking: each tick the hand position is projected onto the plane perpendicular to the axis,
// and the change of its angle around the axis is applied to the handle (incremental, so reversing
// direction responds immediately even after hitting a limit).
UCLASS(ClassGroup = (VillaVR), meta = (BlueprintSpawnableComponent))
class VILLAVR_API URotaryHandleComponent : public USceneComponent
{
	GENERATED_BODY()
public:
	URotaryHandleComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rotary") float MinAngle = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rotary") float MaxAngle = 90.f;
	// Haptic "click" every DetentStep degrees (0 = off)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rotary") float DetentStep = 15.f;
	// Ignore the hand when it is closer than this to the axis (angle is unstable there), cm
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Rotary") float MinHandRadius = 2.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Rotary") float Angle = 0.f;

	// The template grab component that drives this handle (set by the owner in BeginPlay)
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Rotary") TObjectPtr<UActorComponent> GrabComponent;

	UFUNCTION(BlueprintCallable, Category = "Rotary") void SetAngle(float NewAngle);
	UFUNCTION(BlueprintPure, Category = "Rotary") float GetValue01() const;
	UFUNCTION(BlueprintPure, Category = "Rotary") bool IsHeld() const { return bWasHeld; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	bool HandYaw(const FVector& WorldPos, float& OutYaw) const;

	bool bWasHeld = false;
	bool bHaveYaw = false;
	float LastHandYaw = 0.f;
	int32 LastDetent = 0;
};
