#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "VillaGameMode.generated.h"

// L_Courtyard's game mode. Same as the VR template's BP_XRGameMode (default pawn BP_XRPawn), except:
// when no headset is rendering (normal Play-in-viewport, -game without VR), it spawns AVillaDesktopCharacter
// (WASD + mouse, jump, interact, menu) so the scene can be checked without putting the headset on.
//   console:  villa.Desktop 0 = auto (default), 1 = always desktop, 2 = always VR pawn
UCLASS()
class VILLAVR_API AVillaGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	AVillaGameMode();

	virtual UClass* GetDefaultPawnClassForController_Implementation(AController* InController) override;

	// true when a stereo (HMD) view is active right now
	static bool IsStereoActive();
	static bool WantDesktop();

	// Replace the controller's pawn with one of NewClass at the same place (floor-aligned). Used when the
	// headset turns stereo on only after the first pawn was spawned.
	APawn* RespawnAs(AController* C, TSubclassOf<APawn> NewClass);

	UPROPERTY(EditAnywhere, Category = "Villa") TSubclassOf<APawn> DesktopPawnClass;
};
