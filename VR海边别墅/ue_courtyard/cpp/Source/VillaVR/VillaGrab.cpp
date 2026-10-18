#include "VillaGrab.h"

#include "Components/SceneComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "MotionControllerComponent.h"
#include "TimerManager.h"
#include "UObject/UnrealType.h"

namespace VillaGrab
{
	static const TCHAR* GrabClassPath = TEXT("/Game/XRFramework/Blueprints/BP_GrabComponent.BP_GrabComponent_C");

	UActorComponent* AddCustomGrab(AActor* Owner, USceneComponent* Parent, const FVector& RelLocation)
	{
		if (!Owner || !Parent) return nullptr;
		UClass* GrabClass = LoadClass<UActorComponent>(nullptr, GrabClassPath);
		if (!GrabClass)
		{
			UE_LOG(LogTemp, Warning, TEXT("VillaGrab: %s not found"), GrabClassPath);
			return nullptr;
		}
		USceneComponent* Grab = NewObject<USceneComponent>(Owner, GrabClass, NAME_None, RF_Transient);
		Grab->SetupAttachment(Parent);
		Grab->SetRelativeLocation(RelLocation);
		SetEnumByDisplayName(Grab, TEXT("GrabType"), TEXT("Custom"));
		Grab->RegisterComponent();   // owner is in BeginPlay -> component BeginPlay runs too
		Owner->AddInstanceComponent(Grab);
		return Grab;
	}

	bool ReadHeld(const UActorComponent* Grab, USceneComponent*& OutController)
	{
		OutController = nullptr;
		if (!Grab) return false;
		const UClass* C = Grab->GetClass();
		const FBoolProperty* HeldProp = FindFProperty<FBoolProperty>(C, TEXT("bIsHeld"));
		const FObjectPropertyBase* CtrlProp = FindFProperty<FObjectPropertyBase>(C, TEXT("MotionControllerRef"));
		if (!HeldProp) return false;
		const bool bHeld = HeldProp->GetPropertyValue_InContainer(Grab);
		if (bHeld && CtrlProp)
		{
			OutController = Cast<USceneComponent>(CtrlProp->GetObjectPropertyValue_InContainer(Grab));
		}
		return bHeld && OutController != nullptr;
	}

	bool SetEnumByDisplayName(UObject* Obj, FName Property, const FString& DisplayName)
	{
		if (!Obj) return false;
		FProperty* P = FindFProperty<FProperty>(Obj->GetClass(), Property);
		UEnum* Enum = nullptr;
		FNumericProperty* Underlying = nullptr;
		if (FEnumProperty* EP = CastField<FEnumProperty>(P)) { Enum = EP->GetEnum(); Underlying = EP->GetUnderlyingProperty(); }
		else if (FByteProperty* BP = CastField<FByteProperty>(P)) { Enum = BP->Enum; Underlying = BP; }
		if (!Enum || !Underlying) return false;
		for (int32 i = 0; i < Enum->NumEnums(); ++i)
		{
			if (Enum->GetDisplayNameTextByIndex(i).ToString().Equals(DisplayName, ESearchCase::IgnoreCase))
			{
				Underlying->SetIntPropertyValue(P->ContainerPtrToValuePtr<void>(Obj), Enum->GetValueByIndex(i));
				return true;
			}
		}
		UE_LOG(LogTemp, Warning, TEXT("VillaGrab: enum value '%s' not found on %s"), *DisplayName, *Property.ToString());
		return false;
	}

	void Pulse(const UObject* WorldContext, const USceneComponent* Controller, float Amplitude, float Seconds)
	{
		const UMotionControllerComponent* MC = Cast<UMotionControllerComponent>(Controller);
		APlayerController* PC = UGameplayStatics::GetPlayerController(WorldContext, 0);
		if (!MC || !PC) return;
		const EControllerHand Hand = MC->MotionSource.ToString().Contains(TEXT("Left")) ? EControllerHand::Left : EControllerHand::Right;
		PC->SetHapticsByValue(0.6f, Amplitude, Hand);
		FTimerHandle H;
		TWeakObjectPtr<APlayerController> WeakPC(PC);
		PC->GetWorldTimerManager().SetTimer(H, FTimerDelegate::CreateLambda([WeakPC, Hand]()
		{
			if (WeakPC.IsValid()) WeakPC->SetHapticsByValue(0.f, 0.f, Hand);
		}), Seconds, false);
	}
}
