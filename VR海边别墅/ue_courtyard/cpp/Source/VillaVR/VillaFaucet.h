#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VillaFaucet.generated.h"

class UStaticMeshComponent;
class UAudioComponent;
class URotaryHandleComponent;
class UMaterialInterface;
class UStaticMesh;
class USoundBase;

// Wall-mounted quarter-turn (ball valve) garden tap.
// Local frame: origin = wall face at pipe height, +X = out of the wall, +Z = up.
// Lever across the pipe (+Y) = closed, along the pipe (+X) = fully open.
// Stream diameter ~ sqrt(opening): flow ~ opening, flow ~ cross-section area.
UCLASS()
class VILLAVR_API AVillaFaucet : public AActor
{
	GENERATED_BODY()
public:
	AVillaFaucet();

	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Flange;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Pipe;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Spout;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Stem;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<URotaryHandleComponent> Handle;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Lever;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Grip;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UStaticMeshComponent> Water;
	UPROPERTY(VisibleAnywhere, Category = "Faucet") TObjectPtr<UAudioComponent> Sound;

	// Distance from the spout outlet down to whatever the water hits (sink top), cm
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Faucet") float WaterDropLength = 12.f;
	// Stream diameter at full opening, cm
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Faucet") float MaxStreamDiameter = 1.4f;
	// Below this opening the tap counts as closed
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Faucet") float ClosedThreshold = 0.03f;

	UFUNCTION(BlueprintPure, Category = "Faucet") float GetOpening() const;
	// Litres per second at the current opening (full = 0.2 L/s, a typical garden tap)
	UFUNCTION(BlueprintPure, Category = "Faucet") float GetFlowRate() const;
	UFUNCTION(BlueprintPure, Category = "Faucet") FVector GetOutletLocation() const;
	// Debug / scripted: turn the lever to an opening 0..1
	UFUNCTION(BlueprintCallable, Category = "Faucet") void SetOpening(float Opening01);

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void ApplyOpening(float V);
	UStaticMeshComponent* MakePart(FName Name, UStaticMesh* Mesh, UMaterialInterface* Mat, USceneComponent* Parent,
		const FVector& Loc, const FRotator& Rot, const FVector& SizeCm);

	float Applied = -1.f;
	UPROPERTY(Transient) TObjectPtr<UActorComponent> GrabComponent;
	static constexpr float OutletX = 13.f;
	static constexpr float OutletZ = -7.f;
};
