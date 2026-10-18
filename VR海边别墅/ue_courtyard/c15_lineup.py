# c15_lineup.py place <组名> <网格路径…> : 候选网格在海边草地排成一排 (间隔 4 m, 都 yaw 0)
# c15_lineup.py shoot <组名>              : 每件从 4 个方向近拍 -> court/shots/lu_<组名>_<序号>_<方向>.png
# c15_lineup.py clear                     : 删掉
# 两步分开: 放下后等几秒让材质着色器编译完 (同一帧里拍会全是灰色默认材质)
# 方向名 = 相机在物体的哪一侧 (UE 坐标): px=+X, nx=-X, py=+Y, ny=-Y。由此判断网格"正面"朝哪
import json
import os
import sys

import unreal

D = os.path.join(os.path.expanduser("~"), "Documents", "UE-MCP-Tools", "court")
OUT = os.path.join(D, "shots")
os.makedirs(OUT, exist_ok=True)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
TAG = "CourtLineup"
X0, Y0, GAP = -3000.0, -2600.0, 400.0
mode = sys.argv[1]
if mode in ("clear", "place"):
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
if mode == "place":
    name, paths = sys.argv[2], sys.argv[3:]
    rows = []
    for i, p in enumerate(paths):
        m = unreal.load_asset(p)
        b = m.get_bounding_box()
        c = (b.min + b.max) * 0.5
        a = EAS.spawn_actor_from_object(m, unreal.Vector(X0 + i * GAP - c.x, Y0 - c.y, 5 - b.min.z), unreal.Rotator(0, 0, 0))
        a.set_editor_property("tags", [unreal.Name(TAG)])
        a.set_folder_path("Lineup")
        rows.append(dict(i=i + 1, path=p, name=p.split("/")[-1].split(".")[0],
                         size=[round(b.max.x - b.min.x), round(b.max.y - b.min.y), round(b.max.z - b.min.z)]))
    json.dump(rows, open(os.path.join(D, "lineup_%s.json" % name), "w"), indent=1)
    print("placed", len(rows))
elif mode == "shoot":
    name = sys.argv[2]
    rows = json.load(open(os.path.join(D, "lineup_%s.json" % name)))
    rt = unreal.RenderingLibrary.create_render_target2d(world, 480, 360, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
    cap = EAS.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    cc = cap.capture_component2d
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
    cc.set_editor_property("fov_angle", 50.0)
    cc.set_editor_property("capture_every_frame", False)
    for r in rows:
        sx, sy, sz = r["size"]
        cx, cy, cz = X0 + (r["i"] - 1) * GAP, Y0, 5 + sz / 2
        dist = max(sx, sy, sz) * 1.6 + 60
        for vn, (dx, dy) in {"ny": (0, -1), "px": (1, 0), "py": (0, 1), "nx": (-1, 0)}.items():
            cam = unreal.Vector(cx + dx * dist, cy + dy * dist, cz + dist * 0.45)
            cap.set_actor_location_and_rotation(cam, unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(cx, cy, cz)), False, False)
            cc.capture_scene()
            unreal.RenderingLibrary.export_render_target(world, rt, OUT, "lu_%s_%02d_%s" % (name, r["i"], vn))
    EAS.destroy_actor(cap)
    print("shot", len(rows))
