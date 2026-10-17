# VR Scale Sanity Check — L_Study (re-run after the build_study.py rebuild)

Level: `/Game/ClaudeVR/Maps/L_Study` · Date: 2026-10-18 · Read-only check (nothing changed in the level)
Method: world-space actor AABBs from the editor (units cm, floor z = 0). Room interior is x −250…250 and y −200…200 (5.0 × 4.0 m). The level has 227 actors, 178 of them in ClaudeStudy/Furniture.

| # | Check | Result | Key numbers |
|---|-------|--------|-------------|
| 1 | PlayerStart clearance (45 cm, < 200 cm) | **PASS** | Nearest solid object is Armchair_Seat, 67.8 cm away |
| 2 | Desk top height 70–78 cm | **PASS** | Desk_Top surface at 75 cm |
| 3 | Chair seat height 42–50 cm | **PASS** | Chair_Seat surface at 49 cm |
| 4 | Top bookshelf board ≤ 200 cm | **PASS** | Shelf_Board_5 at 192–195 cm; tallest book reaches 190.7 cm |
| 5 | Unintended Furniture overlaps (> 2 cm) | **PASS** | 16 overlapping pairs, all normal joints within one piece of furniture; none look unintended |
| 6 | Walkable clear floor area | **PASS** | 15.2 m² free of 20.0 m² (76%); 7.1 m² with 30 cm body clearance |

## Changes since previous run
- **Bookshelf (item 4, WARN → PASS):**
  - The cabinet is now 195 cm tall (it was 210).
  - Shelf spacing went from 42 cm to 38 cm. The board tops are now at 9.5, 47.5, 85.5, 123.5, 161.5 and 195 cm.
  - The tallest book reaches 190.7 cm (it was 211.4), so no book pokes into the top board any more.
- **Floor lamp / armchair (item 5, WARN → PASS):**
  - The floor lamp moved to the corner at about (−230, −182). It was at (−200, −150).
  - The armchair moved 10 cm toward +x. It now spans x −212…−108 (it was −222…−118).
  - The lamp base and the armchair seat are now 4.8 cm apart. The lamp pole no longer goes through the seat or backrest.
- **Desk drawer:** the drawer bottom went from 53 cm to 59 cm. Knee room above the chair seat on the drawer side is now **10 cm** (it was 4 cm).
- **Overlap count:** 16 pairs (it was 29). The 13 that went away were the floor lamp passing through the armchair and the books pushing into the top board.
- **Walkable area:** 15.2 m² free and 7.1 m² with clearance (it was 15.3 and 7.2). It went down slightly because the armchair now sits a bit further into the room.
- Unchanged: PlayerStart at (−40, −130, 92) facing yaw 25°, desk height, chair height, room shell, Brush1, and the missing east baseboard.

## 1. PlayerStart — PASS
- These objects come within 45 cm horizontally and start below 200 cm. None of them block movement:
  - Rug: 45.0 cm away, but only 1.2 cm tall.
  - Floor: the player stands on it.
  - Lights L_DeskLamp and L_Ceiling (2 cm): only their light-radius bounds reach the spot.
  - Engine volumes (NavMesh, Lightmass, SkySphere, reflection capture, DirectionalLight, BP_VRSpectator, Brush0): these are invisible helpers and don't block movement.
- Nearest solid geometry: Armchair_Seat at 67.8 cm (it was 77.8), Base_S at 68 cm and Wall_S at 70 cm.

## 2. Desk — PASS
- Desk_Top covers z 71–75, so the work surface is at **75 cm**.
- Desk_Drawer covers z 59–71, which leaves 10 cm of knee room above the 49 cm seat on that side.

## 3. Chair — PASS
- Chair_Seat covers z 43–49, so the seat is at **49 cm**. It is 26 cm below the desk top.

## 4. Bookshelf top board — PASS
| Board | Bottom → top (cm) |
|-------|------------------|
| Shelf_Board_0 | 6.5 → 9.5 |
| Shelf_Board_1 | 44.5 → 47.5 |
| Shelf_Board_2 | 82.5 → 85.5 |
| Shelf_Board_3 | 120.5 → 123.5 |
| Shelf_Board_4 | 158.5 → 161.5 |
| **Shelf_Board_5** | **192 → 195** (≤ 200) |

- The side and back panels now end at 195 cm.
- There are 136 books. The tallest ones are Book_117 (190.7), Book_134 (190.3) and Book_120 (190.2). All of them end below the top board, which starts at 192 cm.

## 5. Furniture overlaps — PASS
All 16 remaining overlaps are normal joints within one piece of furniture:
- Desk_Leg_0 and Desk_Leg_2 ↔ Desk_Drawer (3.5 / 4.5 / 12). The drawer is set into the legs.
- Chair_Post ↔ Chair_Foot_0…4, plus 7 pairs of chair feet with each other. This is the star base hub.
- Armchair_Seat ↔ Armchair_Back (54.9 / 69.7 / 7).
- FloorLamp_Pole ↔ FloorLamp_Shade (3 / 3 / 13).

Minor issue outside the Furniture-only check: FloorLamp_Shade (x −250…−210, y −202…−162, z 145–175) goes **2 cm into Wall_S** and touches Wall_W. You can't see this from the room interior, but moving the lamp 2–3 cm toward +y would clear it.

## 6. Walkable floor area — PASS
- Room interior: **20.0 m²**.
- Obstacles counted: 133 actors under ClaudeStudy/ whose bounds start below 120 cm and are taller than 2 cm. The rug, lights, floor and ceiling are left out.
- The floor was mapped on a 5 cm grid:
  - **Floor not covered by any obstacle: 15.2 m² (76%)**
  - **Floor at least 30 cm from any obstacle: 7.1 m²**

## Other notes (not part of the checks)
- **Brush1** (a BSP brush, bounds x 220…420, y −40…160, z 0…200) still reaches 30 cm into the room near the east window. Check whether it's additive.
- The east wall still has no baseboard (there is no Base_E). This is cosmetic only.
