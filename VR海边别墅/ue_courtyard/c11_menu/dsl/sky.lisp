(fn CourtSky (ExposureWeight)
  (bind cam (Actor|GetComponentbyClass :ComponentClass "/Script/Engine.CameraComponent"))
  (Camera|SetPostProcessBlendWeight :self cam :InPostProcessBlendWeight ExposureWeight)
  (bind sph (Actor|GetActorOfClass :ActorClass "/Engine/EngineSky/BP_Sky_Sphere.BP_Sky_Sphere_C"))
  (Utilities|IsValid sph
    (:"Is Valid"
      (类|BPSkySphere|UpdateSunDirection :self sph)
      (bind sky (Actor|GetActorOfClass :ActorClass "/Script/Engine.SkyLight"))
      (Utilities|IsValid sky
        (:"Is Valid"
          (Rendering|Components|SkyLight|RecaptureSky :self (类|SkyLight|GetLightComponent :self sky)))
        (:"Is Not Valid")))
    (:"Is Not Valid"
      (bind sky2 (Actor|GetActorOfClass :ActorClass "/Script/Engine.SkyLight"))
      (Utilities|IsValid sky2
        (:"Is Valid"
          (Rendering|Components|SkyLight|RecaptureSky :self (类|SkyLight|GetLightComponent :self sky2)))
        (:"Is Not Valid")))))
