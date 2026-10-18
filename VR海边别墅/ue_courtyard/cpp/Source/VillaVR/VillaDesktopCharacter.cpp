#include "VillaDesktopCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/LightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"
#include "Styling/CoreStyle.h"
#include "VillaFaucet.h"
#include "VillaGameMode.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

// ------------------------------------------------------------------ data
// Plan metres (x east, y north) like the build scripts; Yaw is the UE yaw (-90 = plan north = toward the sea).
const TArray<AVillaDesktopCharacter::FViewpoint>& AVillaDesktopCharacter::Viewpoints()
{
	static const TArray<FViewpoint> V = {
		{TEXT("1 入口长巷"), 29.3f, 8.6f, 0.05f, 180.f},
		{TEXT("2 客厅看海"), 25.5f, 13.0f, 0.15f, -90.f},
		{TEXT("3 泳池平台"), 18.5f, 20.6f, 0.15f, -90.f},
		{TEXT("4 凉棚餐台"), 31.0f, 19.6f, 0.15f, -90.f},
		{TEXT("5 橄榄树院"), 6.0f, 11.8f, 0.05f, -75.f},
		{TEXT("6 香草院 (水龙头)"), 13.6f, 12.3f, 0.05f, 133.f, -27.f},
		{TEXT("7 主卧私院"), 6.3f, 7.0f, 0.15f, -70.f},
		{TEXT("8 柠檬巷"), 31.6f, 11.2f, 0.10f, -90.f},
		{TEXT("9 电子工作室"), 34.3f, 14.2f, 0.15f, 10.f},
		{TEXT("0 车库工作间"), 30.2f, 3.0f, 0.05f, -40.f},
		{TEXT("地下室"), 23.85f, 4.9f, -2.85f, -90.f},
		{TEXT("主卧"), 16.2f, 7.2f, 0.15f, 160.f},
		{TEXT("厨房"), 23.5f, 13.7f, 0.15f, 90.f},
		{TEXT("次卧"), 9.8f, 5.9f, 0.15f, 45.f},
	};
	return V;
}

const TCHAR* AVillaDesktopCharacter::TimeName(int32 Index)
{
	static const TCHAR* N[] = {TEXT("黄昏"), TEXT("上午"), TEXT("正午"), TEXT("下午")};
	return N[((Index % 4) + 4) % 4];
}

static FString GrabName(const AActor* A)
{
	if (!A) return TEXT("东西");
#if WITH_EDITOR
	const FString L = A->GetActorLabel();
#else
	const FString L = A->GetName();
#endif
	struct FName2 { const TCHAR* Key; const TCHAR* Value; };
	static const FName2 Map[] = {
		{TEXT("Cup"), TEXT("杯子")}, {TEXT("WineBottle"), TEXT("酒瓶")}, {TEXT("Lemon"), TEXT("柠檬")},
		{TEXT("BeachBall"), TEXT("沙滩球")}, {TEXT("Basil"), TEXT("罗勒")}, {TEXT("Lavender"), TEXT("薰衣草")},
		{TEXT("Hammer"), TEXT("锤子")}, {TEXT("Wrench"), TEXT("扳手")}, {TEXT("Screwdriver"), TEXT("螺丝刀")},
		{TEXT("DevBoard"), TEXT("开发板")}, {TEXT("Servo"), TEXT("舵机")}, {TEXT("SolderSpool"), TEXT("焊锡卷")},
		{TEXT("Multimeter"), TEXT("万用表")}, {TEXT("SmallBox"), TEXT("小纸箱")}, {TEXT("SmallPot"), TEXT("小花盆")}};
	for (const auto& P : Map)
		if (L.Contains(P.Key)) return P.Value;
	return TEXT("东西");
}

// ------------------------------------------------------------------ setup
AVillaDesktopCharacter::AVillaDesktopCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(32.f, 88.f);
	BaseEyeHeight = 77.f;                          // eyes 1.65 m above the floor (capsule centre is 0.88 m up)
	CrouchedEyeHeight = 30.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(GetCapsuleComponent());
	Camera->SetRelativeLocation(FVector(0.f, 0.f, BaseEyeHeight));
	Camera->bUsePawnControlRotation = true;
	Camera->SetFieldOfView(90.f);
	// Same as BP_XRPawn's camera: post process only overrides exposure bias = 0; its blend weight is the
	// per-time-of-day "ExposureWeight" (0 at dusk -> the level's PP_Global exposure is used as is).
	Camera->PostProcessSettings.bOverride_AutoExposureBias = true;
	Camera->PostProcessSettings.AutoExposureBias = 0.f;
	Camera->PostProcessBlendWeight = 0.f;

	PhysicsHandle = CreateDefaultSubobject<UPhysicsHandleComponent>(TEXT("PhysicsHandle"));
	PhysicsHandle->bInterpolateTarget = true;
	PhysicsHandle->InterpolationSpeed = 25.f;

	bUseControllerRotationYaw = true;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* M = GetCharacterMovement();
	M->MaxWalkSpeed = WalkSpeed;
	M->MaxWalkSpeedCrouched = 150.f;
	M->MaxFlySpeed = FlySpeed;
	M->BrakingDecelerationFlying = 3000.f;
	M->JumpZVelocity = 420.f;
	M->AirControl = 0.35f;
	M->MaxStepHeight = 40.f;                       // basement stair risers are 18.75 cm
	M->GetNavAgentPropertiesRef().bCanCrouch = true;
	M->bOrientRotationToMovement = false;
}

void AVillaDesktopCharacter::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	GetCharacterMovement()->MaxFlySpeed = FlySpeed;
}

void AVillaDesktopCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
	if (IsHolding()) Drop(0.f);
	RemoveUI();
	Super::EndPlay(Reason);
}

void AVillaDesktopCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	APlayerController* PC = Cast<APlayerController>(Controller);
	if (!PC) return;
	if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
	{
		MakeInput();
		Sub->AddMappingContext(Context, 10);
	}
	PC->SetInputMode(FInputModeGameOnly());
	PC->bShowMouseCursor = false;
	BuildUI();
}

void AVillaDesktopCharacter::MakeInput()
{
	if (Context) return;
	Context = NewObject<UInputMappingContext>(this, TEXT("IMC_VillaDesktop"));
	auto NewAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* A = NewObject<UInputAction>(this, Name);
		A->ValueType = Type;
		Actions.Add(A);
		return A;
	};
	auto Map = [this](UInputAction* A, FKey Key, bool bSwizzle = false, bool bNegate = false)
	{
		FEnhancedActionKeyMapping& M = Context->MapKey(A, Key);
		if (bSwizzle) M.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(this));   // X -> Y (forward)
		if (bNegate) M.Modifiers.Add(NewObject<UInputModifierNegate>(this));
	};
	AMove = NewAction(TEXT("IA_DMove"), EInputActionValueType::Axis2D);
	Map(AMove, EKeys::W, true);           Map(AMove, EKeys::S, true, true);
	Map(AMove, EKeys::D);                 Map(AMove, EKeys::A, false, true);
	Map(AMove, EKeys::Up, true);          Map(AMove, EKeys::Down, true, true);
	Map(AMove, EKeys::Right);             Map(AMove, EKeys::Left, false, true);
	ALook = NewAction(TEXT("IA_DLook"), EInputActionValueType::Axis2D);
	Map(ALook, EKeys::Mouse2D);
	AJump = NewAction(TEXT("IA_DJump"), EInputActionValueType::Boolean);
	Map(AJump, EKeys::SpaceBar);
	ARun = NewAction(TEXT("IA_DRun"), EInputActionValueType::Boolean);
	Map(ARun, EKeys::LeftShift);
	ACrouch = NewAction(TEXT("IA_DCrouch"), EInputActionValueType::Boolean);
	Map(ACrouch, EKeys::C);               Map(ACrouch, EKeys::LeftControl);
	AInteract = NewAction(TEXT("IA_DInteract"), EInputActionValueType::Boolean);
	Map(AInteract, EKeys::E);             Map(AInteract, EKeys::LeftMouseButton);
	AThrow = NewAction(TEXT("IA_DThrow"), EInputActionValueType::Boolean);
	Map(AThrow, EKeys::RightMouseButton);
	AWheel = NewAction(TEXT("IA_DWheel"), EInputActionValueType::Axis1D);
	Map(AWheel, EKeys::MouseWheelAxis);
	AFly = NewAction(TEXT("IA_DFly"), EInputActionValueType::Boolean);
	Map(AFly, EKeys::F);
	ATime = NewAction(TEXT("IA_DTime"), EInputActionValueType::Boolean);
	Map(ATime, EKeys::T);
	AMenu = NewAction(TEXT("IA_DMenu"), EInputActionValueType::Boolean);
	Map(AMenu, EKeys::Tab);               Map(AMenu, EKeys::M);
	AHelp = NewAction(TEXT("IA_DHelp"), EInputActionValueType::Boolean);
	Map(AHelp, EKeys::H);
	const FKey Num[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
	                    EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine, EKeys::Zero};
	for (int32 i = 0; i < 10; ++i)
	{
		UInputAction* A = NewAction(*FString::Printf(TEXT("IA_DView%d"), i), EInputActionValueType::Boolean);
		Map(A, Num[i]);
		AViewpoints.Add(A);
	}
}

void AVillaDesktopCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	UEnhancedInputComponent* EI = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!EI) return;
	MakeInput();
	EI->BindAction(AMove, ETriggerEvent::Triggered, this, &AVillaDesktopCharacter::OnMove);
	EI->BindAction(ALook, ETriggerEvent::Triggered, this, &AVillaDesktopCharacter::OnLook);
	EI->BindAction(AJump, ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnJumpStart);
	EI->BindAction(AJump, ETriggerEvent::Completed, this, &AVillaDesktopCharacter::OnJumpStop);
	EI->BindAction(ARun, ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnRunStart);
	EI->BindAction(ARun, ETriggerEvent::Completed, this, &AVillaDesktopCharacter::OnRunStop);
	EI->BindAction(ACrouch, ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnCrouchStart);
	EI->BindAction(ACrouch, ETriggerEvent::Completed, this, &AVillaDesktopCharacter::OnCrouchStop);
	EI->BindAction(AInteract, ETriggerEvent::Started, this, &AVillaDesktopCharacter::Interact);
	EI->BindAction(AThrow, ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnThrow);
	EI->BindAction(AWheel, ETriggerEvent::Triggered, this, &AVillaDesktopCharacter::OnWheel);
	EI->BindAction(AFly, ETriggerEvent::Started, this, &AVillaDesktopCharacter::ToggleFly);
	EI->BindAction(ATime, ETriggerEvent::Started, this, &AVillaDesktopCharacter::CycleTime);
	EI->BindAction(AMenu, ETriggerEvent::Started, this, &AVillaDesktopCharacter::ToggleMenu);
	EI->BindAction(AHelp, ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnHelp);
	for (int32 i = 0; i < AViewpoints.Num(); ++i)
		EI->BindAction(AViewpoints[i], ETriggerEvent::Started, this, &AVillaDesktopCharacter::OnViewpointKey, i);
}

// ------------------------------------------------------------------ movement
void AVillaDesktopCharacter::OnMove(const FInputActionValue& V)
{
	const FVector2D In = V.Get<FVector2D>();
	if (!Controller) return;
	const FRotator Ctrl = Controller->GetControlRotation();
	if (bFlying)
	{
		// fly where you look (pitch included), like an editor camera
		const FRotator R(Ctrl.Pitch, Ctrl.Yaw, 0.f);
		AddMovementInput(FRotationMatrix(R).GetUnitAxis(EAxis::X), In.Y);
		AddMovementInput(FRotationMatrix(R).GetUnitAxis(EAxis::Y), In.X);
		return;
	}
	const FRotator Yaw(0.f, Ctrl.Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), In.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), In.X);
}

void AVillaDesktopCharacter::OnLook(const FInputActionValue& V)
{
	if (bMenuOpen) return;
	const FVector2D In = V.Get<FVector2D>();
	AddControllerYawInput(In.X * MouseSensitivity);
	AddControllerPitchInput(-In.Y * MouseSensitivity);
}

void AVillaDesktopCharacter::OnJumpStart(const FInputActionValue&)
{
	if (!bFlying) Jump();
}

void AVillaDesktopCharacter::OnJumpStop(const FInputActionValue&)
{
	StopJumping();
}

void AVillaDesktopCharacter::OnRunStart(const FInputActionValue&)
{
	bRunning = true;
	GetCharacterMovement()->MaxWalkSpeed = RunSpeed;
	GetCharacterMovement()->MaxFlySpeed = FlySpeed * 2.5f;
}

void AVillaDesktopCharacter::OnRunStop(const FInputActionValue&)
{
	bRunning = false;
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	GetCharacterMovement()->MaxFlySpeed = FlySpeed;
}

void AVillaDesktopCharacter::OnCrouchStart(const FInputActionValue&)
{
	if (!bFlying) Crouch();
}

void AVillaDesktopCharacter::OnCrouchStop(const FInputActionValue&)
{
	UnCrouch();
}

void AVillaDesktopCharacter::ToggleFly()
{
	bFlying = !bFlying;
	UnCrouch();
	SetActorEnableCollision(!bFlying);             // fly = pass through walls, handy for checking the roof / basement
	GetCharacterMovement()->SetMovementMode(bFlying ? MOVE_Flying : MOVE_Falling);
	ShowToast(bFlying ? TEXT("飞行模式：开（穿墙；Space 上升 / C 下降，再按 F 落地）") : TEXT("飞行模式：关"));
}

void AVillaDesktopCharacter::OnHelp(const FInputActionValue&)
{
	bHelp = !bHelp;
}

void AVillaDesktopCharacter::OnViewpointKey(int32 Index)
{
	if (!bMenuOpen) GoToViewpoint(Index);
}

void AVillaDesktopCharacter::GoToViewpoint(int32 Index)
{
	const TArray<FViewpoint>& V = Viewpoints();
	if (!V.IsValidIndex(Index)) return;
	const FViewpoint& P = V[Index];
	if (IsHolding()) Drop(0.f);
	const float Half = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	SetActorLocation(FVector(P.X * 100.f, -P.Y * 100.f, P.Z * 100.f + Half + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
	GetCharacterMovement()->StopMovementImmediately();
	if (Controller) Controller->SetControlRotation(FRotator(P.Pitch, P.Yaw, 0.f));
	ShowToast(FString(TEXT("到：")) + P.Name);
}

// ------------------------------------------------------------------ time of day (same numbers as BP_XRPawn CourtApplyTime)
void AVillaDesktopCharacter::CycleTime()
{
	ApplyTime(TimeIndex + 1);
}

void AVillaDesktopCharacter::ApplyTime(int32 Index)
{
	struct FT { float Pitch, Yaw, Lux, R, G, B, W; };
	static const FT T[4] = {
		{-7.f, 55.f, 4.f, 1.f, 0.55f, 0.3f, 0.f},     // dusk
		{-30.f, 235.f, 7.f, 1.f, 0.93f, 0.82f, 1.f},  // morning
		{-62.f, 145.f, 9.f, 1.f, 0.98f, 0.94f, 1.f},  // noon
		{-22.f, 70.f, 6.f, 1.f, 0.84f, 0.62f, 0.6f}}; // afternoon
	TimeIndex = ((Index % 4) + 4) % 4;
	const FT& P = T[TimeIndex];
	UWorld* W = GetWorld();
	for (TActorIterator<ADirectionalLight> It(W); It; ++It)
	{
		ULightComponent* LC = It->GetLightComponent();
		LC->SetMobility(EComponentMobility::Movable);   // a Stationary sun cannot be turned at runtime
		LC->SetWorldRotation(FRotator(P.Pitch, P.Yaw, 0.f));
		LC->SetIntensity(P.Lux);
		LC->SetLightColor(FLinearColor(P.R, P.G, P.B));
		break;
	}
	Camera->PostProcessBlendWeight = P.W;
	for (TActorIterator<AActor> It(W); It; ++It)
	{
		if (!It->GetClass()->GetName().StartsWith(TEXT("BP_Sky_Sphere"))) continue;
		if (UFunction* F = It->FindFunction(TEXT("UpdateSunDirection")))
			if (F->NumParms == 0) It->ProcessEvent(F, nullptr);
		break;
	}
	for (TActorIterator<ASkyLight> It(W); It; ++It)
	{
		It->GetLightComponent()->RecaptureSky();
		break;
	}
	ShowToast(FString(TEXT("时间：")) + TimeName(TimeIndex) + TEXT("（室内烘焙的间接光不会跟着变）"), 3.f);
}

// ------------------------------------------------------------------ interaction
bool AVillaDesktopCharacter::IsHolding() const
{
	return PhysicsHandle && PhysicsHandle->GetGrabbedComponent() != nullptr;
}

void AVillaDesktopCharacter::UpdateTarget()
{
	TargetComp.Reset();
	TargetFaucet.Reset();
	UWorld* W = GetWorld();
	const FVector Start = Camera->GetComponentLocation();
	const FVector Dir = Camera->GetForwardVector();
	FCollisionQueryParams Q(SCENE_QUERY_STAT(VillaAim), false, this);
	if (UPrimitiveComponent* H = HeldComp.Get()) Q.AddIgnoredComponent(H);

	float MaxD = ReachCm;
	FHitResult Hit;
	if (W->LineTraceSingleByChannel(Hit, Start, Start + Dir * ReachCm, ECC_Visibility, Q))
		MaxD = Hit.Distance + 6.f;

	// physics bodies (grabbables, the tap's grip which only overlaps) in a thin sweep up to the first wall
	TArray<FHitResult> Hits;
	W->SweepMultiByObjectType(Hits, Start, Start + Dir * MaxD, FQuat::Identity,
		FCollisionObjectQueryParams(ECC_PhysicsBody), FCollisionShape::MakeSphere(7.f), Q);
	Hits.Sort([](const FHitResult& A, const FHitResult& B) { return A.Distance < B.Distance; });
	for (const FHitResult& H : Hits)
	{
		if (AVillaFaucet* F = Cast<AVillaFaucet>(H.GetActor())) { TargetFaucet = F; return; }
		UPrimitiveComponent* C = H.GetComponent();
		if (C && C->IsSimulatingPhysics()) { TargetComp = C; return; }
	}
	// the tap is small: also accept it when the crosshair is within ~10 degrees of it
	for (TActorIterator<AVillaFaucet> It(W); It; ++It)
	{
		const FVector To = It->GetActorLocation() - Start;
		const float D = To.Size();
		if (D < MaxD + 20.f && D < ReachCm && FVector::DotProduct(To / FMath::Max(D, 1.f), Dir) > 0.985f)
		{
			TargetFaucet = *It;
			return;
		}
	}
}

void AVillaDesktopCharacter::Interact()
{
	if (bMenuOpen) return;
	if (IsHolding()) { Drop(0.f); return; }
	if (AVillaFaucet* F = TargetFaucet.Get())
	{
		F->SetOpening(F->GetOpening() > F->ClosedThreshold ? 0.f : 1.f);
		return;
	}
	UPrimitiveComponent* C = TargetComp.Get();
	if (!C) return;
	const FVector Start = Camera->GetComponentLocation();
	HoldDistance = FMath::Clamp(FVector::Dist(Start, C->GetComponentLocation()), 60.f, 180.f);
	C->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);   // don't push yourself around with it
	PhysicsHandle->GrabComponentAtLocationWithRotation(C, NAME_None, C->GetComponentLocation(), C->GetComponentRotation());
	HeldComp = C;
}

void AVillaDesktopCharacter::Drop(float ThrowSpeed)
{
	UPrimitiveComponent* C = HeldComp.Get();
	PhysicsHandle->ReleaseComponent();
	HeldComp.Reset();
	if (!C) return;
	C->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
	C->WakeAllRigidBodies();
	if (ThrowSpeed > 0.f) C->AddImpulse(Camera->GetForwardVector() * ThrowSpeed, NAME_None, true);
}

void AVillaDesktopCharacter::OnThrow(const FInputActionValue&)
{
	if (!bMenuOpen && IsHolding()) Drop(700.f);
}

void AVillaDesktopCharacter::OnWheel(const FInputActionValue& V)
{
	if (bMenuOpen) return;
	const float D = V.Get<float>();
	if (FMath::IsNearlyZero(D)) return;
	if (IsHolding()) { HoldDistance = FMath::Clamp(HoldDistance + D * 10.f, 50.f, 220.f); return; }
	if (AVillaFaucet* F = TargetFaucet.Get()) F->SetOpening(F->GetOpening() + (D > 0.f ? 0.1f : -0.1f));
}

void AVillaDesktopCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// headset switched on after this pawn spawned (VR Preview): hand over to the VR pawn
	HeadsetCheckIn -= DeltaSeconds;
	if (HeadsetCheckIn <= 0.f)
	{
		HeadsetCheckIn = 1.f;
		if (!AVillaGameMode::WantDesktop())
		{
			if (AVillaGameMode* GM = GetWorld()->GetAuthGameMode<AVillaGameMode>())
			{
				GM->RespawnAs(Controller, GM->DefaultPawnClass);
				return;
			}
		}
	}

	if (bFlying && Controller)
	{
		const APlayerController* PC = Cast<APlayerController>(Controller);
		float Up = 0.f;
		if (PC && PC->IsInputKeyDown(EKeys::SpaceBar)) Up += 1.f;
		if (PC && (PC->IsInputKeyDown(EKeys::C) || PC->IsInputKeyDown(EKeys::LeftControl))) Up -= 1.f;
		if (Up != 0.f) AddMovementInput(FVector::UpVector, Up);
	}

	if (UPrimitiveComponent* H = HeldComp.Get())
	{
		const FVector Start = Camera->GetComponentLocation();
		const FRotator Yaw(0.f, GetControlRotation().Yaw, 0.f);
		PhysicsHandle->SetTargetLocationAndRotation(Start + Camera->GetForwardVector() * HoldDistance, Yaw);
		Prompt = FString::Printf(TEXT("拿着%s    [E/左键] 放下   [右键] 扔   [滚轮] 远近"), *GrabName(H->GetOwner()));
		return;
	}

	UpdateTarget();
	if (AVillaFaucet* F = TargetFaucet.Get())
	{
		const float O = F->GetOpening();
		Prompt = FString::Printf(TEXT("水龙头（%d%%）    [E/左键] %s   [滚轮] 调水量"), FMath::RoundToInt(O * 100.f),
			O > F->ClosedThreshold ? TEXT("关") : TEXT("开"));
	}
	else if (UPrimitiveComponent* C = TargetComp.Get())
		Prompt = FString::Printf(TEXT("[E/左键] 拿起%s"), *GrabName(C->GetOwner()));
	else
		Prompt.Reset();
}

// ------------------------------------------------------------------ HUD + menu (plain Slate, built here)
void AVillaDesktopCharacter::ShowToast(const FString& S, float Seconds)
{
	Toast = S;
	ToastUntil = FPlatformTime::Seconds() + Seconds;
}

FText AVillaDesktopCharacter::HudPrompt() const { return FText::FromString(Prompt); }
FText AVillaDesktopCharacter::HudToast() const
{
	return FPlatformTime::Seconds() < ToastUntil ? FText::FromString(Toast) : FText::GetEmpty();
}
FText AVillaDesktopCharacter::HudHelp() const
{
	return FText::FromString(FString::Printf(
		TEXT("桌面模式（不戴头显）\n")
		TEXT("WASD 走  鼠标 看  Shift 跑  Space 跳  C 蹲\n")
		TEXT("E / 左键 拿起·放下·开关水龙头  右键 扔  滚轮 调\n")
		TEXT("F 飞行（穿墙）%s   T 时间：%s\n")
		TEXT("1-9, 0 参观点   Tab / M 菜单   H 隐藏说明\n")
		TEXT("Shift+F1 放开鼠标   Esc 结束运行"),
		bFlying ? TEXT("开") : TEXT("关"), TimeName(TimeIndex)));
}

void AVillaDesktopCharacter::ToggleMenu()
{
	bMenuOpen = !bMenuOpen;
	APlayerController* PC = Cast<APlayerController>(Controller);
	if (!PC) return;
	if (bMenuOpen)
	{
		if (IsHolding()) Drop(0.f);
		FInputModeGameAndUI M;
		M.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		M.SetHideCursorDuringCapture(false);
		PC->SetInputMode(M);
		PC->bShowMouseCursor = true;
		PC->SetIgnoreMoveInput(true);
	}
	else
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
		PC->ResetIgnoreMoveInput();
	}
}

void AVillaDesktopCharacter::BuildUI()
{
	UGameViewportClient* VC = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!VC || RootWidget.IsValid()) return;
	TWeakObjectPtr<AVillaDesktopCharacter> Self(this);
	auto Font = [](int32 Size) { return FCoreStyle::GetDefaultFontStyle("Regular", Size); };
	auto Shadowed = [&](TAttribute<FText> Text, int32 Size, FLinearColor Color = FLinearColor::White)
	{
		return SNew(STextBlock).Text(Text).Font(Font(Size)).ColorAndOpacity(Color)
			.ShadowOffset(FVector2D(1.5f, 1.5f)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, 0.85f));
	};
	auto Button = [&](TAttribute<FText> Label, TFunction<void()> Do)
	{
		return SNew(SButton).HAlign(HAlign_Center).VAlign(VAlign_Center).ContentPadding(FMargin(14.f, 6.f))
			.OnClicked_Lambda([Do]() { Do(); return FReply::Handled(); })
			[SNew(STextBlock).Text(Label).Font(Font(16))];
	};
	auto MenuVis = [Self]() { return Self.IsValid() && Self->bMenuOpen ? EVisibility::Visible : EVisibility::Collapsed; };
	auto Unhit = EVisibility::HitTestInvisible;

	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(4.f));
	const TArray<FViewpoint>& V = Viewpoints();
	for (int32 i = 0; i < V.Num(); ++i)
	{
		Grid->AddSlot(i % 3, i / 3)[Button(FText::FromString(V[i].Name), [Self, i]() {
			if (!Self.IsValid()) return;
			Self->ToggleMenu();
			Self->GoToViewpoint(i);
		})];
	}

	RootWidget = SNew(SOverlay)
		// crosshair
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[SNew(SBox).Visibility(Unhit)[Shadowed(FText::FromString(TEXT("+")), 18, FLinearColor(1.f, 1.f, 1.f, 0.8f))]]
		// what you are looking at
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(0.f, 0.f, 0.f, 110.f)
		[SNew(SBox).Visibility(Unhit)[Shadowed(TAttribute<FText>::CreateLambda([Self]() {
			return Self.IsValid() && !Self->bMenuOpen ? Self->HudPrompt() : FText::GetEmpty(); }), 20)]]
		// toast
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top).Padding(0.f, 40.f, 0.f, 0.f)
		[SNew(SBox).Visibility(Unhit)[Shadowed(TAttribute<FText>::CreateLambda([Self]() {
			return Self.IsValid() ? Self->HudToast() : FText::GetEmpty(); }), 18, FLinearColor(1.f, 0.92f, 0.6f))]]
		// help
		+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(24.f, 24.f)
		[SNew(SBox).Visibility_Lambda([Self]() {
			return Self.IsValid() && Self->bHelp && !Self->bMenuOpen ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
			[Shadowed(TAttribute<FText>::CreateLambda([Self]() { return Self.IsValid() ? Self->HudHelp() : FText::GetEmpty(); }), 13)]]
		// menu
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[SNew(SBorder).Visibility_Lambda(MenuVis)
			.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
			.BorderBackgroundColor(FLinearColor(0.02f, 0.02f, 0.03f, 0.82f))
			.Padding(FMargin(28.f, 22.f))
			[SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 0.f, 0.f, 14.f)
				[SNew(STextBlock).Text(FText::FromString(TEXT("院落别墅 · 桌面模式"))).Font(Font(22))]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)
				[Button(FText::FromString(TEXT("继续  (Tab)")), [Self]() { if (Self.IsValid()) Self->ToggleMenu(); })]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)
				[Button(TAttribute<FText>::CreateLambda([Self]() {
					return FText::FromString(FString(TEXT("时间：")) + (Self.IsValid() ? TimeName(Self->TimeIndex) : TEXT("")) + TEXT("  (T)")); }),
					[Self]() { if (Self.IsValid()) Self->CycleTime(); })]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)
				[Button(TAttribute<FText>::CreateLambda([Self]() {
					return FText::FromString(Self.IsValid() && Self->bFlying ? TEXT("飞行（穿墙）：开  (F)") : TEXT("飞行（穿墙）：关  (F)")); }),
					[Self]() { if (Self.IsValid()) Self->ToggleFly(); })]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f)
				[SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1.f).Padding(0.f, 0.f, 4.f, 0.f)
					[Button(FText::FromString(TEXT("鼠标慢一点")), [Self]() {
						if (Self.IsValid()) { Self->MouseSensitivity = FMath::Max(0.2f, Self->MouseSensitivity - 0.2f);
							Self->ShowToast(FString::Printf(TEXT("鼠标灵敏度 %.1f"), Self->MouseSensitivity)); } })]
					+ SHorizontalBox::Slot().FillWidth(1.f).Padding(4.f, 0.f, 0.f, 0.f)
					[Button(FText::FromString(TEXT("鼠标快一点")), [Self]() {
						if (Self.IsValid()) { Self->MouseSensitivity = FMath::Min(3.f, Self->MouseSensitivity + 0.2f);
							Self->ShowToast(FString::Printf(TEXT("鼠标灵敏度 %.1f"), Self->MouseSensitivity)); } })]]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 14.f, 0.f, 4.f)
				[SNew(STextBlock).Text(FText::FromString(TEXT("去参观点"))).Font(Font(16))]
				+ SVerticalBox::Slot().AutoHeight()[Grid]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 14.f, 0.f, 4.f)
				[SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1.f).Padding(0.f, 0.f, 4.f, 0.f)
					[Button(FText::FromString(TEXT("重新开始")), [Self]() {
						if (Self.IsValid()) UGameplayStatics::OpenLevel(Self.Get(), FName(*UGameplayStatics::GetCurrentLevelName(Self.Get()))); })]
					+ SHorizontalBox::Slot().FillWidth(1.f).Padding(4.f, 0.f, 0.f, 0.f)
					[Button(FText::FromString(TEXT("退出")), [Self]() {
						if (Self.IsValid()) UKismetSystemLibrary::QuitGame(Self.Get(), Cast<APlayerController>(Self->Controller), EQuitPreference::Quit, false); })]]]];

	VC->AddViewportWidgetContent(RootWidget.ToSharedRef(), 50);
}

void AVillaDesktopCharacter::RemoveUI()
{
	if (!RootWidget.IsValid()) return;
	if (UWorld* W = GetWorld())
		if (UGameViewportClient* VC = W->GetGameViewport())
			VC->RemoveViewportWidgetContent(RootWidget.ToSharedRef());
	RootWidget.Reset();
}
