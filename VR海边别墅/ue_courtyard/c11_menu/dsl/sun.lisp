(fn CourtSetSun (Pitch Yaw Lux R G B ExposureWeight)
  (bind sun (Actor|GetActorOfClass :ActorClass "/Script/Engine.DirectionalLight"))
  (Utilities|IsValid sun
    (:"Is Valid"
      (bind lc (类|Light|GetLightComponent :self sun))
      (Transformation|SetMobility :self lc :NewMobility "Movable")
      (Transformation|SetWorldRotation :self lc :NewRotation (Math|Rotator|MakeRotator :Roll 0.0 :Pitch Pitch :Yaw Yaw))
      (Rendering|Components|Light|SetIntensity :self lc :NewIntensity Lux)
      (Rendering|Components|Light|SetLightColor :self lc :NewLightColor (工具|结构体|MakeLinearColor :R R :G G :B B :A 1.0)))
    (:"Is Not Valid")))
