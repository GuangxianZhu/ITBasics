(fn CourtCycleTurn ()
  (bind cur (变量|Default|GetSnapTurnDegrees))
  (变量|Default|SetSnapTurnDegrees :SnapTurnDegrees (Math|Float|SelectFloat :A -30.0 :B -45.0 :bPickA (Math|Float|NearlyEqual(Float) :A cur :B -45.0 :ErrorTolerance 1.0))))
