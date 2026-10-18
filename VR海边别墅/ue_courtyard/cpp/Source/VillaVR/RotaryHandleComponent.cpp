#include "RotaryHandleComponent.h"
#include "VillaGrab.h"

URotaryHandleComponent::URotaryHandleComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	SetMobility(EComponentMobility::Movable);
}

void URotaryHandleComponent::SetAngle(float NewAngle)
{
	Angle = FMath::Clamp(NewAngle, MinAngle, MaxAngle);
	SetRelativeRotation(FRotator(0.f, -Angle, 0.f));
}

float URotaryHandleComponent::GetValue01() const
{
	return MaxAngle > MinAngle ? (Angle - MinAngle) / (MaxAngle - MinAngle) : 0.f;
}

bool URotaryHandleComponent::HandYaw(const FVector& WorldPos, float& OutYaw) const
{
	const USceneComponent* Parent = GetAttachParent();
	const FQuat AxisFrame = Parent ? Parent->GetComponentQuat() : FQuat::Identity;
	const FVector Local = AxisFrame.UnrotateVector(WorldPos - GetComponentLocation());
	if (FVector2D(Local.X, Local.Y).Size() < MinHandRadius) return false;
	OutYaw = FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X));
	return true;
}

void URotaryHandleComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	USceneComponent* Controller = nullptr;
	const bool bHeld = VillaGrab::ReadHeld(GrabComponent, Controller);
	if (bHeld)
	{
		float Yaw;
		if (HandYaw(Controller->GetComponentLocation(), Yaw))
		{
			if (bWasHeld && bHaveYaw)
			{
				// lever direction (parent frame) = 90 - Angle, so a hand moving +d degrees means Angle -= d
				const float D = FMath::FindDeltaAngleDegrees(LastHandYaw, Yaw);
				SetAngle(Angle - D);
			}
			LastHandYaw = Yaw;
			bHaveYaw = true;
		}
		if (DetentStep > 0.f)
		{
			const int32 Detent = FMath::FloorToInt((Angle - MinAngle) / DetentStep + 0.5f);
			if (bWasHeld && Detent != LastDetent)
			{
				const bool bEnd = FMath::IsNearlyEqual(Angle, MinAngle) || FMath::IsNearlyEqual(Angle, MaxAngle);
				VillaGrab::Pulse(this, Controller, bEnd ? 0.8f : 0.35f);
			}
			LastDetent = Detent;
		}
	}
	else
	{
		bHaveYaw = false;
	}
	bWasHeld = bHeld;
}
