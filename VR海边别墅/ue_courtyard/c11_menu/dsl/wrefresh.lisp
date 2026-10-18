(fn CourtRefresh ()
  (bind p (工具|Casting|CastToBP_XRPawn :Object (Game|GetPlayerPawn :PlayerIndex 0))
    (:then
      (Widget|SetText(Text) :self (变量|WBP_Menu|GetText_TimeButton) :InText (Utilities|Text|ToText(String) :InString (类|BPXRPawn|CourtTimeLabel :self p)))
      (Widget|SetText(Text) :self (变量|WBP_Menu|GetText_TurnButton) :InText (Utilities|Text|ToText(String) :InString (类|BPXRPawn|CourtTurnLabel :self p))))
    (:CastFailed)))
