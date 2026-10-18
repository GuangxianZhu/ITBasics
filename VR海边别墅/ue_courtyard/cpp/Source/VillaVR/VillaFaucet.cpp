#include "VillaFaucet.h"

#include "Components/AudioComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "RotaryHandleComponent.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"
#include "VillaGrab.h"

AVillaFaucet::AVillaFaucet()
{
	PrimaryActorTick.bCanEverTick = true;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Metal(TEXT("/Game/Courtyard/Materials/MI_C_metal.MI_C_metal"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Red(TEXT("/Game/Courtyard/Materials/MI_C_red.MI_C_red"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Glass(TEXT("/Game/Courtyard/Materials/M_CourtGlass.M_CourtGlass"));
	static ConstructorHelpers::FObjectFinder<USoundBase> Trickle(TEXT("/Game/Courtyard/Audio/trickle_loop.trickle_loop"));

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	const FRotator AlongX(90.f, 0.f, 0.f);   // cylinder axis Z -> X
	Flange = MakePart(TEXT("Flange"), Cyl.Object, Metal.Object, Root, FVector(0.6f, 0, 0), AlongX, FVector(6.f, 6.f, 1.2f));
	Pipe   = MakePart(TEXT("Pipe"),   Cyl.Object, Metal.Object, Root, FVector(7.f, 0, 0), AlongX, FVector(3.f, 3.f, 14.f));
	Spout  = MakePart(TEXT("Spout"),  Cyl.Object, Metal.Object, Root, FVector(OutletX, 0, OutletZ / 2.f + 1.f), FRotator::ZeroRotator, FVector(2.4f, 2.4f, -OutletZ + 2.f));
	Stem   = MakePart(TEXT("Stem"),   Cyl.Object, Metal.Object, Root, FVector(5.f, 0, 3.5f), FRotator::ZeroRotator, FVector(1.8f, 1.8f, 4.f));

	Handle = CreateDefaultSubobject<URotaryHandleComponent>(TEXT("Handle"));
	Handle->SetupAttachment(Root);
	Handle->SetRelativeLocation(FVector(5.f, 0, 5.5f));

	// lever points +Y (across the pipe) at Angle 0 = closed
	Lever = MakePart(TEXT("Lever"), Cube.Object, Metal.Object, Handle, FVector(0, 5.f, 0.4f), FRotator::ZeroRotator, FVector(1.4f, 10.f, 0.8f));
	Grip  = MakePart(TEXT("Grip"),  Cube.Object, Red.Object,   Handle, FVector(0, 8.5f, 0.4f), FRotator::ZeroRotator, FVector(2.2f, 5.f, 1.8f));
	// the template's grab trace looks for PhysicsBody objects; query only, never blocks anything
	Grip->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Grip->SetCollisionObjectType(ECC_PhysicsBody);
	Grip->SetCollisionResponseToAllChannels(ECR_Overlap);

	Water = MakePart(TEXT("Water"), Cyl.Object, Glass.Object, Root, FVector(OutletX, 0, OutletZ - 6.f), FRotator::ZeroRotator, FVector(1.f, 1.f, 12.f));
	Water->SetCastShadow(false);
	Water->SetHiddenInGame(true);
	Water->SetVisibility(false);

	Sound = CreateDefaultSubobject<UAudioComponent>(TEXT("Sound"));
	Sound->SetupAttachment(Root);
	Sound->SetRelativeLocation(FVector(OutletX, 0, OutletZ - 10.f));
	Sound->bAutoActivate = false;
	Sound->SetSound(Trickle.Object);
}

UStaticMeshComponent* AVillaFaucet::MakePart(FName Name, UStaticMesh* Mesh, UMaterialInterface* Mat, USceneComponent* Parent,
	const FVector& Loc, const FRotator& Rot, const FVector& SizeCm)
{
	UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	C->SetupAttachment(Parent);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	if (Mat) C->SetMaterial(0, Mat);
	C->SetRelativeLocationAndRotation(Loc, Rot);
	C->SetRelativeScale3D(SizeCm / 100.f);   // BasicShapes are 100 cm
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetGenerateOverlapEvents(false);
	return C;
}

void AVillaFaucet::BeginPlay()
{
	Super::BeginPlay();
	GrabComponent = VillaGrab::AddCustomGrab(this, Handle, FVector(0, 8.5f, 0.4f));
	Handle->GrabComponent = GrabComponent;
	ApplyOpening(GetOpening());
}

float AVillaFaucet::GetOpening() const
{
	return Handle ? Handle->GetValue01() : 0.f;
}

float AVillaFaucet::GetFlowRate() const
{
	const float V = GetOpening();
	return V < ClosedThreshold ? 0.f : 0.2f * V;
}

FVector AVillaFaucet::GetOutletLocation() const
{
	return GetActorTransform().TransformPosition(FVector(OutletX, 0, OutletZ));
}

void AVillaFaucet::SetOpening(float Opening01)
{
	if (!Handle) return;
	Handle->SetAngle(FMath::Lerp(Handle->MinAngle, Handle->MaxAngle, FMath::Clamp(Opening01, 0.f, 1.f)));
	ApplyOpening(GetOpening());
}

void AVillaFaucet::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ApplyOpening(GetOpening());
}

void AVillaFaucet::ApplyOpening(float V)
{
	if (FMath::IsNearlyEqual(V, Applied, 0.002f)) return;
	Applied = V;
	const bool bOn = V >= ClosedThreshold;
	Water->SetVisibility(bOn);
	Water->SetHiddenInGame(!bOn);
	if (bOn)
	{
		const float D = MaxStreamDiameter * FMath::Sqrt(V);
		Water->SetRelativeLocation(FVector(OutletX, 0, OutletZ - WaterDropLength / 2.f));
		Water->SetRelativeScale3D(FVector(D, D, WaterDropLength) / 100.f);
		if (!Sound->IsPlaying()) Sound->Play();
		Sound->SetVolumeMultiplier(0.25f + 0.75f * V);
		Sound->SetPitchMultiplier(0.9f + 0.2f * V);
	}
	else if (Sound->IsPlaying())
	{
		Sound->FadeOut(0.15f, 0.f);
	}
}
