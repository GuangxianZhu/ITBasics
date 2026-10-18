#include "VillaGameMode.h"

#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "GameFramework/Character.h"
#include "GameFramework/Controller.h"
#include "HAL/IConsoleManager.h"
#include "StereoRendering.h"
#include "UObject/ConstructorHelpers.h"
#include "VillaDesktopCharacter.h"

static TAutoConsoleVariable<int32> CVarVillaDesktop(
	TEXT("villa.Desktop"), 0,
	TEXT("0 = auto (desktop character when no headset is rendering), 1 = always desktop, 2 = always VR pawn"));

AVillaGameMode::AVillaGameMode()
{
	static ConstructorHelpers::FClassFinder<APawn> XRPawn(TEXT("/Game/XRFramework/Blueprints/BP_XRPawn"));
	if (XRPawn.Succeeded()) DefaultPawnClass = XRPawn.Class;
	DesktopPawnClass = AVillaDesktopCharacter::StaticClass();
}

bool AVillaGameMode::IsStereoActive()
{
	return GEngine && GEngine->StereoRenderingDevice.IsValid() && GEngine->StereoRenderingDevice->IsStereoEnabled();
}

bool AVillaGameMode::WantDesktop()
{
	const int32 Mode = CVarVillaDesktop.GetValueOnGameThread();
	if (Mode == 1) return true;
	if (Mode == 2) return false;
	return !IsStereoActive();
}

UClass* AVillaGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	if (WantDesktop() && DesktopPawnClass) return DesktopPawnClass;
	return Super::GetDefaultPawnClassForController_Implementation(InController);
}

static float FloorOffset(const APawn* P)
{
	// characters stand on their capsule bottom; the XR pawn's origin is already on the floor
	if (const ACharacter* Ch = Cast<ACharacter>(P)) return Ch->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	return 0.f;
}

APawn* AVillaGameMode::RespawnAs(AController* C, TSubclassOf<APawn> NewClass)
{
	if (!C || !NewClass) return nullptr;
	APawn* Old = C->GetPawn();
	FVector Loc = Old ? Old->GetActorLocation() : FVector::ZeroVector;
	const FRotator Rot(0.f, C->GetControlRotation().Yaw, 0.f);
	if (Old) Loc.Z -= FloorOffset(Old);
	const APawn* NewCDO = NewClass->GetDefaultObject<APawn>();
	Loc.Z += FloorOffset(NewCDO) + 2.f;
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	APawn* NewPawn = GetWorld()->SpawnActor<APawn>(NewClass, Loc, Rot, SP);
	if (!NewPawn) return nullptr;
	C->UnPossess();
	if (Old) Old->Destroy();
	C->Possess(NewPawn);
	return NewPawn;
}
