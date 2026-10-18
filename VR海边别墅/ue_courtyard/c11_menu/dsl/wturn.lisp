(fn CourtTurnClicked ()
  (bind p (工具|Casting|CastToBP_XRPawn :Object (Game|GetPlayerPawn :PlayerIndex 0))
    (:then
      (类|BPXRPawn|CourtCycleTurn :self p)
      (CallFunction|CourtRefresh))
    (:CastFailed)))
