(fn CourtApplyTime (Index)
  (switch 工具|流程控制|Switch|SwitchonInt Index
    (:0
      (CallFunction|CourtSetSun :Pitch -7.0 :Yaw 55.0 :Lux 4.0 :R 1.0 :G 0.55 :B 0.3)
      (CallFunction|CourtSky :ExposureWeight 0.0))
    (:1
      (CallFunction|CourtSetSun :Pitch -30.0 :Yaw 235.0 :Lux 7.0 :R 1.0 :G 0.93 :B 0.82)
      (CallFunction|CourtSky :ExposureWeight 1.0))
    (:2
      (CallFunction|CourtSetSun :Pitch -62.0 :Yaw 145.0 :Lux 9.0 :R 1.0 :G 0.98 :B 0.94)
      (CallFunction|CourtSky :ExposureWeight 1.0))
    (:3
      (CallFunction|CourtSetSun :Pitch -22.0 :Yaw 70.0 :Lux 6.0 :R 1.0 :G 0.84 :B 0.62)
      (CallFunction|CourtSky :ExposureWeight 0.6))
    (:Default)))
