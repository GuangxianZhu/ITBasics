# -*- coding: utf-8 -*-
"""第 6 步: 能抓起来的东西。复用 VR 模板的 BP_Grabbable_SmallCube (带抓取组件 + 物理),
只把它的网格换成我们要的形状 (引擎自带的立方体/圆柱/球, 自带简单碰撞, 物理才能算)。可重复运行。"""
import unreal

TAG = "CourtyardGrab"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
CLS = unreal.EditorAssetLibrary.load_blueprint_class("/Game/XRFramework/Blueprints/BP_Grabbable_SmallCube")
MESH = {"box": unreal.load_asset("/Engine/BasicShapes/Cube.Cube"),
        "cyl": unreal.load_asset("/Engine/BasicShapes/Cylinder.Cylinder"),
        "sph": unreal.load_asset("/Engine/BasicShapes/Sphere.Sphere")}


def mat(k):
    p = {"white": "/Game/Courtyard/Materials/MI_C_white", "black": "/Game/Courtyard/Materials/MI_C_black",
         "yellow": "/Game/Courtyard/Materials/MI_C_yellow", "red": "/Game/Courtyard/Materials/MI_C_red",
         "metal": "/Game/Courtyard/Materials/MI_C_metal", "pcb": "/Game/Courtyard/Materials/MI_C_pcb",
         "leaf": "/Game/Courtyard/Materials/MI_C_leaf", "cardboard": "/Game/Courtyard/Materials/MI_C_cardboard",
         "lavender": "/Game/Courtyard/Materials/MI_C_lavender", "terracotta": "/Game/Courtyard/Materials/MI_C_terracotta"}[k]
    return unreal.load_asset(p)


FL = 0.15
ITEMS = [  # 形状, x, y, 底面 z, 尺寸 (米), 材质, 名字
    ("cyl", 19.6, 12.75, FL + 0.96, (0.08, 0.08, 0.1), "white", "Cup1"),
    ("cyl", 19.85, 12.6, FL + 0.96, (0.08, 0.08, 0.1), "white", "Cup2"),
    ("cyl", 20.1, 12.8, FL + 0.96, (0.08, 0.08, 0.1), "white", "Cup3"),
    ("cyl", 21.8, 12.7, FL + 0.96, (0.08, 0.08, 0.3), "black", "WineBottle"),
    ("sph", 30.6, 22.2, FL + 0.75, (0.08, 0.08, 0.08), "yellow", "Lemon1"),
    ("sph", 30.75, 22.35, FL + 0.75, (0.08, 0.08, 0.08), "yellow", "Lemon2"),
    ("sph", 30.9, 22.2, FL + 0.75, (0.08, 0.08, 0.08), "yellow", "Lemon3"),
    ("sph", 19.5, 21.0, FL + 0.01, (0.3, 0.3, 0.3), "red", "BeachBall"),
    ("sph", 12.4, 10.9, 0.91, (0.14, 0.14, 0.1), "leaf", "Basil"),
    ("sph", 12.75, 10.9, 0.91, (0.12, 0.12, 0.09), "lavender", "Lavender"),
    ("box", 29.2, 6.2, 0.99, (0.3, 0.04, 0.04), "red", "Hammer"),
    ("box", 29.7, 6.2, 0.99, (0.24, 0.05, 0.015), "metal", "Wrench"),
    ("box", 30.1, 6.2, 0.99, (0.2, 0.025, 0.025), "yellow", "Screwdriver"),
    ("box", 34.3, 17.3, FL + 0.73, (0.07, 0.05, 0.015), "pcb", "DevBoard1"),
    ("box", 34.5, 17.3, FL + 0.73, (0.07, 0.05, 0.015), "pcb", "DevBoard2"),
    ("box", 34.75, 17.3, FL + 0.73, (0.05, 0.04, 0.035), "black", "Servo"),
    ("cyl", 35.3, 17.3, FL + 0.73, (0.09, 0.09, 0.05), "metal", "SolderSpool"),
    ("box", 35.6, 17.3, FL + 0.73, (0.08, 0.15, 0.04), "yellow", "Multimeter"),
    ("box", 22.0, 3.3, -2.85, (0.32, 0.25, 0.22), "cardboard", "SmallBox"),
    ("cyl", 23.2, 10.1, 0.06, (0.2, 0.2, 0.2), "terracotta", "SmallPot"),
]

for a in EAS.get_all_level_actors():
    if TAG in [str(t) for t in a.tags]:
        EAS.destroy_actor(a)
n = 0
for shape, x, y, z0, (sx, sy, sz), m, name in ITEMS:
    a = EAS.spawn_actor_from_class(CLS, unreal.Vector(x * 100, -y * 100, (z0 + sz / 2 + 0.01) * 100))
    comps = a.get_components_by_class(unreal.StaticMeshComponent)
    if not comps:
        continue
    c = comps[0]
    c.set_static_mesh(MESH[shape])
    c.set_material(0, mat(m))
    a.set_actor_scale3d(unreal.Vector(sx, sy, sz))
    a.set_editor_property("tags", [unreal.Name(TAG)])
    a.set_folder_path("Courtyard/Grabbable")
    a.set_actor_label("GRAB_" + name)
    n += 1
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
print("grabbables:", n, "class:", CLS)
