(fn CourtTurnLabel ()
  (bind cur (变量|Default|GetSnapTurnDegrees))
  (return (Utilities|String|SelectString :A "转向：30°" :B "转向：45°" :bPickA (Math|Float|NearlyEqual(Float) :A cur :B -30.0 :ErrorTolerance 1.0))))
