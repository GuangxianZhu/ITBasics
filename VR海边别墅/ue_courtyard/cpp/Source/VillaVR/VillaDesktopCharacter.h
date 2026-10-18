#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "VillaDesktopCharacter.generated.h"

class UCameraComponent;
class UPhysicsHandleComponent;
class UPrimitiveComponent;
class UInputAction;
class UInputMappingContext;
class AVillaFaucet;
class SWidget;

// Desktop (no headset) player for checking the villa on a monitor.
//   WASD move · mouse look · Space jump · Shift run · C crouch · F fly (no collision; Space/C = up/down)
//   E or left click: pick up / put down a grabbable, open/close the tap · wheel: tap opening / hold distance
//   right click: throw · T: time of day · 1-9, 0: viewpoints · Tab or M: menu · H: help
// Everything (input actions, HUD, menu) is created in C++ at runtime: no Blueprint or UMG asset needed.
UCLASS()
class VILLAVR_API AVillaDesktopCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	AVillaDesktopCharacter();

	UPROPERTY(VisibleAnywhere, Category = "Villa") TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(VisibleAnywhere, Category = "Villa") TObjectPtr<UPhysicsHandleComponent> PhysicsHandle;

	UPROPERTY(EditAnywhere, Category = "Villa") float WalkSpeed = 260.f;
	UPROPERTY(EditAnywhere, Category = "Villa") float RunSpeed = 600.f;
	UPROPERTY(EditAnywhere, Category = "Villa") float FlySpeed = 900.f;
	UPROPERTY(EditAnywhere, Category = "Villa") float ReachCm = 260.f;
	UPROPERTY(EditAnywhere, Category = "Villa") float MouseSensitivity = 1.0f;

	// ---- callable from Python / console for testing (PIE: pawn.call_method("...")) ----
	UFUNCTION(BlueprintCallable, Category = "Villa") void Interact();
	UFUNCTION(BlueprintCallable, Category = "Villa") void ToggleMenu();
	UFUNCTION(BlueprintCallable, Category = "Villa") void ToggleFly();
	UFUNCTION(BlueprintCallable, Category = "Villa") void CycleTime();
	UFUNCTION(BlueprintCallable, Category = "Villa") void ApplyTime(int32 Index);
	UFUNCTION(BlueprintCallable, Category = "Villa") void GoToViewpoint(int32 Index);
	UFUNCTION(BlueprintCallable, Category = "Villa") FString GetPromptText() const { return Prompt; }
	UFUNCTION(BlueprintPure, Category = "Villa") bool IsHolding() const;
	UFUNCTION(BlueprintPure, Category = "Villa") bool IsMenuOpen() const { return bMenuOpen; }

	struct FViewpoint { const TCHAR* Name; float X, Y, Z, Yaw; float Pitch = -5.f; };   // plan metres (x east, y north); Yaw/Pitch in UE degrees (yaw -90 = plan north = sea)
	static const TArray<FViewpoint>& Viewpoints();
	static const TCHAR* TimeName(int32 Index);

	int32 TimeIndex = 0;
	bool bFlying = false;
	bool bHelp = true;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;

private:
	void MakeInput();
	void OnMove(const FInputActionValue& V);
	void OnLook(const FInputActionValue& V);
	void OnJumpStart(const FInputActionValue& V);
	void OnJumpStop(const FInputActionValue& V);
	void OnRunStart(const FInputActionValue& V);
	void OnRunStop(const FInputActionValue& V);
	void OnCrouchStart(const FInputActionValue& V);
	void OnCrouchStop(const FInputActionValue& V);
	void OnWheel(const FInputActionValue& V);
	void OnThrow(const FInputActionValue& V);
	void OnHelp(const FInputActionValue& V);
	void OnViewpointKey(int32 Index);

	void UpdateTarget();
	void Drop(float ThrowSpeed);
	void BuildUI();
	void RemoveUI();
	void CheckHeadset();

	UPROPERTY(Transient) TObjectPtr<UInputMappingContext> Context;
	UPROPERTY(Transient) TArray<TObjectPtr<UInputAction>> Actions;   // keeps the runtime actions alive
	UInputAction* AMove = nullptr;
	UInputAction* ALook = nullptr;
	UInputAction* AJump = nullptr;
	UInputAction* ARun = nullptr;
	UInputAction* ACrouch = nullptr;
	UInputAction* AInteract = nullptr;
	UInputAction* AThrow = nullptr;
	UInputAction* AWheel = nullptr;
	UInputAction* AFly = nullptr;
	UInputAction* ATime = nullptr;
	UInputAction* AMenu = nullptr;
	UInputAction* AHelp = nullptr;
	TArray<UInputAction*> AViewpoints;

	// what the crosshair is on
	TWeakObjectPtr<UPrimitiveComponent> TargetComp;
	TWeakObjectPtr<AVillaFaucet> TargetFaucet;
	TWeakObjectPtr<UPrimitiveComponent> HeldComp;
	float HoldDistance = 110.f;
	bool bRunning = false;
	bool bMenuOpen = false;
	FString Prompt;
	FString Toast;
	double ToastUntil = 0.0;
	float HeadsetCheckIn = 0.5f;

	TSharedPtr<SWidget> RootWidget;
	void ShowToast(const FString& S, float Seconds = 2.f);
	FText HudPrompt() const;
	FText HudHelp() const;
	FText HudToast() const;
};
