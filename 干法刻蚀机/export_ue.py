# -*- coding: utf-8 -*-
"""
干法刻蚀机 → 虚幻工程 MyVRToyBox 用的 etcher_ue.glb（工艺腔 PM1 合成 19 个抓取单元 + 基座 + 爆炸路线）

用法
  blender -b --factory-startup --python export_ue.py -- <输出目录>        （MyVRToyBox 的 scripts/import_etcher.bat 会调）
  pip 版 bpy：python export_ue.py <输出目录>
  出预览图（装配 / 爆炸，从 VR 里玩家眼睛的位置看）：再加 --preview；查爆炸后零件有没有互相穿插：加 --check

和网页用的 etcher_detail.glb 的不同：
  1. 只要工艺腔 PM1。射频电源柜不要（1.6 m 高的大柜子，放进来整机变宽，别的零件全都跟着变小），两个机械手留给以后的 fab 模式。
  2. 多一片晶圆（K12），放在静电卡盘上，可以抓。真实厚度 0.775 mm，这里加厚到 3 mm，缩小以后才看得见。
  3. 去掉三根连到别处的线：源匹配器到电源柜的射频电缆、偏压匹配器到电源柜的射频电缆、气体盒到喷嘴的进气管
     （电源柜不在了；进气管从屏蔽罩里穿过去，拆开时会被屏蔽罩"穿过"）。
  4. 按开腔保养的顺序拆，每个单元一个节点、顶点在装配位置；extras.ex = 若干步 [gx, gy, gz, 出场时刻]（glTF 坐标，毫米）。

拆开后的摆法（Blender 坐标：闸阀朝 -Y = 朝玩家，+X 是玩家右手边，+Z 向上，原点是机架底面 = 桌面）：
  - 源组件（匹配器、屏蔽罩、线圈、喷嘴、介质窗）先往上提，再退到腔体后面排成一排。
  - 晶圆从腔里升起来，飘到腔体前面（闸阀上方），离玩家最近。
  - 腔里的件（内衬、约束环、边缘环、绝缘环、卡盘）从腔口提出来，摆到左边两排；升降针从腔底下抽出来，放在左前方。
  - 气体盒、真空计、摆阀、分子泵往右边拉开；观察窗往左；闸阀门往玩家这边；偏压匹配器往左后方。
"""
import json
import math
import os
import sys

import bpy  # noqa: I001  pip 版 bpy 要先 import bpy，bmesh 才找得到
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 先照 build_etcher.py 把零件建出来（不导出）
_src = open(os.path.join(HERE, 'build_etcher.py'), encoding='utf-8').read()
_src = _src[:_src.index('# ================= 导出 =================')]
B = {'__file__': os.path.join(HERE, 'build_etcher.py'), '__name__': 'build_etcher'}
exec(compile(_src, 'build_etcher.py', 'exec'), B)
H = B['H']

# 晶圆：Ø300 mm，放在卡盘陶瓷面上（卡盘顶面 H - 0.001），颜色和网页一样（多晶硅膜的金棕色）
_wafer = B['Part']('wafer')
_wafer.add(B['bm_cyl'](0.15, H - 0.001, H + 0.002, 96, 0.0008), B['mat']('晶圆（多晶硅膜）', 0xa08a5c, 0.5, 0.2))
_wafer.add(B['bm_box'](0.008, 0.006, 0.0032), B['M']['dark'], B['T'](0.147, 0, H + 0.0005))   # 缺口（notch）
_wafer.build()

# ---------------------------------------------------------------- 讲解文字：和网页共用（tools/export_core.mjs 生成）
with open(os.path.join(HERE, 'output', 'etcher_content.json'), encoding='utf-8') as f:
    CONTENT = json.load(f)
PART_TEXT = {p['id']: p for p in CONTENT['parts']}


def lift_route(up, dx, dy, dz, s):
    """先往上提 up，再水平挪 (dx, dy)，最后上下调 dz - up 到终点（米）。三段错开出场。"""
    legs = [(0, 0, up, s), (dx, dy, 0, s + 0.1)]
    if abs(dz - up) > 1e-6:
        legs.append((0, 0, dz - up, s + 0.2))
    return legs


# 单元：(节点名, 由哪些零件合成, 中文名, 材料, 讲解文字取哪个零件的, 爆炸路线 [(dx, dy, dz 米, 出场时刻 0~1)])
# 出场时刻 s：这一段在整个拆开过程的 s*0.6 开始，走 0.4（和其他模型同一个公式）
UNITS = [
    ('K00_Base', ['frame', 'chamber', 'slit', 'lines'], '腔体 + 机架',
     '阳极氧化铝腔体（内壁氧化钇涂层）· 闸阀口 · 铝型材机架 · 冷却水管 / 高压线 / 背氦管', 'chamber', []),
    ('K01_RFCover', ['rfcover'], None, '白色喷粉铝罩 · 散热格栅', 'rfcover', lift_route(0.40, 0.42, 0.72, 0.12, 0.08)),
    ('K02_SourceMatch', ['srcmatch'], None, '喷粉铝箱 + 透明前窗 · 2 个真空可变电容 + 步进电机 · 铜电感', 'srcmatch',
     lift_route(0.55, 1.10, 0.72, 0.15, 0.0)),
    ('K03_Coil', ['coil'], None, '镀银铜带（方截面）· 内外两组 · 陶瓷支撑梳', 'coil', lift_route(0.40, -0.30, 0.72, 0.10, 0.16)),
    ('K04_Nozzle', ['nozzle'], None, '氧化铝陶瓷喷嘴 + 不锈钢接头', 'nozzle', lift_route(0.55, -0.30, 0.72, 0.42, 0.22)),
    ('K05_Window', ['window'], None, '氧化铝陶瓷 Ø690 × 35 mm + O 形圈', 'window', lift_route(0.40, -1.00, 0.72, 0.10, 0.25)),
    ('K06_GasBox', ['gasbox'], None, '喷粉钣金箱 + 透明前窗 · 4 路质量流量计 + 气动阀 + 过滤器', 'gasbox', [(0.55, 0, 0, 0.02)]),
    ('K07_OES', ['oes'], None, '石英观察窗 + 光纤 + 光谱仪', 'oes', [(-0.45, 0, 0, 0.10)]),
    ('K08_Gauges', ['cmg'], None, '电容薄膜真空计 ×2', 'cmg', [(0, 0, 0.10, 0.10), (0.20, 0, 0, 0.16)]),
    ('K09_SlitDoor', ['slit__door'], '闸阀门', '铝门板 + 氟橡胶密封圈', 'slit', [(0, -0.20, 0, 0.12)]),
    ('K10_Liner', ['liner'], None, '阳极氧化铝 + 氧化钇涂层（消耗件，脏了整个换下来洗）', 'liner',
     lift_route(1.30 - 0.87, -1.62, 0.12, 0.55 - 0.87, 0.52)),
    ('K11_Baffle', ['baffle'], None, '阳极氧化铝 · 一圈导流槽（消耗件）', 'baffle', lift_route(1.30 - 0.86, -1.62, -0.50, 0.35 - 0.86, 0.56)),
    ('K12_Wafer', ['wafer'], None, '300 mm 硅片 · 4 nm 栅氧 + 100 nm 多晶硅 + 60 nm 宽光刻胶线条', 'wafer', lift_route(0.45, 0, -0.55, 0.40, 0.45)),
    ('K13_EdgeRing', ['edgering'], None, '单晶硅（消耗件，被等离子体慢慢吃掉，按射频小时更换）', 'edgering',
     lift_route(1.30 - 0.936, -1.05, -0.50, 0.40 - 0.936, 0.60)),
    ('K14_InsRing', ['insring'], None, '石英（消耗件）', 'insring', lift_route(1.30 - 0.83, -1.05, 0.12, 0.40 - 0.83, 0.64)),
    ('K15_ESC', ['esc'], None, '氧化铝陶瓷顶层（双极吸附电极 + 4 区加热层）+ 铝底座（冷却液螺旋水道、背氦沟槽）', 'esc',
     lift_route(1.30 - 0.60, -0.60, 0.12, 0.30 - 0.60, 0.68)),
    ('K16_LiftPins', ['pins'], None, '氧化铝陶瓷针 ×3 + 不锈钢波纹管 + 顶升轭', 'pins',
     [(0, 0, -0.25, 0.74), (-0.60, 0, 0, 0.82), (0, -0.50, 0, 0.90)]),
    ('K17_BiasMatch', ['biasmatch'], None, '喷粉铝箱 + 散热格栅 · 铜带接到卡盘', 'biasmatch', [(-0.45, 0, 0, 0.30), (0, 0.30, 0, 0.40)]),
    ('K18_PendulumValve', ['pendulum', 'pendulum__plate'], None, '铝阀体 + 不锈钢阀板 + 驱动电机', 'pendulum',
     [(0.60, 0, 0, 0.34), (0, 0, 0.05, 0.44)]),
    ('K19_Turbo', ['turbo', 'turbo__rotor'], None, '铝外壳 + 散热片 · 多级叶片转子 · 控制器 · 前级波纹管', 'turbo',
     [(0.55, 0, 0, 0.42), (0, -0.45, 0, 0.52)]),
]
DROP = ['rack', 'atm_base', 'atm_l1', 'atm_l2', 'atm_blade', 'vtm_base', 'vtm_l1', 'vtm_l2', 'vtm_blade']
# 去掉的连线：(零件, 管线的折线, 半径)。折线照抄 build_etcher.py；整段网格都贴着这条折线的（管身 + 两头的盖）就删掉
CUT_PATHS = [
    ('srcmatch', [(-0.12, 0.185, 1.6), (-0.12, 0.22, 1.74), (-0.62, 0.22, 1.74), (-0.78, 0.12, 1.62)], 0.011),
    ('biasmatch', [(-0.22, 0.28, 0.62), (-0.22, 0.34, 0.62), (-0.55, 0.34, 0.5), (-0.74, 0.20, 0.42)], 0.010),
    ('gasbox', [(0.66, 0.17, 1.49), (0.66, 0.17, 1.72), (0.25, 0.15, 1.72), (0.25, 0.15, 1.37), (0.0, 0.0, 1.37),
                (0.0, 0.0, 1.345)], 0.0055),
]


def dist_to_path(p, pts):
    best = 1e9
    for a, b in zip(pts, pts[1:]):
        a, b = Vector(a), Vector(b)
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        best = min(best, (p - (a + ab * t)).length)
    return best


def drop_path(ob, pts, r):
    """删掉物体里整段都贴着折线 pts 的连通网格（拐角做了圆角，所以容差放宽到半径 + 2 cm）。返回删掉的顶点数。"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    m = ob.matrix_world
    seen, doomed = set(), []
    for v0 in bm.verts:
        if v0 in seen:
            continue
        island, todo = [v0], [v0]
        seen.add(v0)
        while todo:
            v = todo.pop()
            for e in v.link_edges:
                o = e.other_vert(v)
                if o not in seen:
                    seen.add(o)
                    island.append(o)
                    todo.append(o)
        if all(dist_to_path(m @ v.co, pts) < r + 0.02 for v in island):
            doomed += island
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()
    return len(doomed)


def bake_unit(name, sources):
    """几个零件合成一个网格对象：顶点在世界坐标（装配位置），对象本身不带变换。"""
    objs = []
    for src in sources:
        ob = bpy.data.objects[src]
        ob.data.transform(ob.matrix_world)
        ob.matrix_world.identity()
        objs.append(ob)
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
            bpy.ops.object.join()
    ob = objs[0]
    ob.name = name
    ob.data.name = name
    return ob


def gltf_mm(dx, dy, dz):
    """Blender 坐标（米）→ glTF 坐标（毫米）：(x, z, -y)"""
    return [round(dx * 1000, 2), round(dz * 1000, 2), round(-dy * 1000, 2)]


# ---------------------------------------------------------------- 爆炸（和虚幻 / 其他模型同一个公式）
def ease(x):
    return 4 * x * x * x if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def prog(t, s):
    return ease(min(1.0, max(0.0, (t - s * .6) / .4)))


def place(objs, t):
    for ob, legs in objs:
        v = Vector((0, 0, 0))
        for dx, dy, dz, s in legs:
            v += Vector((dx, dy, dz)) * prog(t, s)
        ob.location = v


def world_bvh(ob):
    m = ob.matrix_world
    return BVHTree.FromPolygons([m @ v.co for v in ob.data.vertices], [p.vertices[:] for p in ob.data.polygons])


def check_overlaps(objs, times=(1.0,)):
    """几个时刻下哪些单元互相穿插（三角面相交）。"""
    for t in times:
        place(objs, t)
        bpy.context.view_layer.update()
        trees = [(ob.name, world_bvh(ob)) for ob, _ in objs]
        hits = []
        for i in range(len(trees)):
            for j in range(i + 1, len(trees)):
                n = len(trees[i][1].overlap(trees[j][1]))
                if n:
                    hits.append('%s × %s（%d）' % (trees[i][0], trees[j][0], n))
        print('[检查] 拆开 %.0f%%：%s' % (t * 100, '；'.join(hits) if hits else '没有穿插'))
    place(objs, 0.0)


# ---------------------------------------------------------------- 预览图（从 VR 里玩家眼睛的位置看）
# 桌上展示 60 cm（最长边是高度 1.725 m → 缩放约 0.348），模型原点在桌面 (70, -10, 75) cm，Yaw 90 让闸阀朝玩家。
# 玩家眼睛在 (0, 0, 160) cm → 换回 Blender 坐标约 (0.29, -2.01, 2.44) m
EYE = (0.29, -2.01, 2.44)


def render_previews(out, objs):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 16
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = 1280, 800
    w = bpy.data.worlds.new('World')
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes.get('Background')
    bg.inputs[0].default_value = (0.75, 0.78, 0.82, 1)
    bg.inputs[1].default_value = 0.6
    # 桌面（160 × 70 cm 换回模型尺寸）
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(4.6, 2.0, 0.02), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.29, 0.14, -0.012), verts=bm.verts)
    me = bpy.data.meshes.new('Desk')
    bm.to_mesh(me)
    bm.free()
    me.materials.append(B['mat']('桌面', 0x7a6650, 0.0, 0.6))
    desk = bpy.data.objects.new('Desk', me)
    sc.collection.objects.link(desk)
    for name, loc, power in (('Key', (-1.5, -2.5, 4.0), 900), ('Fill', (2.5, -1.5, 3.0), 400), ('Top', (0.0, 0.5, 5.0), 600)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.size = power, 3.0
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0.8)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(lo)
    cd = bpy.data.cameras.new('Cam')
    cam = bpy.data.objects.new('Cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    shots = [('preview_assembled.png', 0.0, EYE, (0.0, 0.0, 0.9), 24),
             ('preview_exploded.png', 1.0, EYE, (-0.3, 0.1, 0.8), 18),
             ('preview_exploded_mid.png', 0.55, EYE, (-0.3, 0.1, 0.8), 18),
             ('preview_exploded_top.png', 1.0, (0.0, -0.3, 5.5), (0.0, 0.1, 0.8), 18)]
    for fname, t, eye, target, lens in shots:
        place(objs, t)
        cd.lens = lens
        cam.location = eye
        cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out, fname)
        bpy.ops.render.render(write_still=True)
        print('[OK] 预览图', fname)
    place(objs, 0.0)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    flags = {a for a in argv if a.startswith('--')}
    args = [a for a in argv if not a.startswith('--')]
    out = os.path.abspath(args[0]) if args else os.path.join(HERE, 'output')
    os.makedirs(out, exist_ok=True)

    for name in DROP:
        ob = bpy.data.objects.get(name)
        if ob:
            bpy.data.objects.remove(ob)
    for part, pts, r in CUT_PATHS:
        n = drop_path(bpy.data.objects[part], pts, r)
        if n == 0:
            raise RuntimeError('%s 上没找到要去掉的连线，build_etcher.py 里的管线改过了？' % part)
        print('[OK] %s 去掉连线（%d 个顶点）' % (part, n))

    objs, rows = [], []
    for name, sources, cn, mat, text_id, legs in UNITS:
        ob = bake_unit(name, sources)
        text = PART_TEXT[text_id]
        ex = [gltf_mm(dx, dy, dz) + [s] for dx, dy, dz, s in legs]
        ob['part_no'] = name.split('_')[0]
        ob['name_cn'] = cn or text['name']
        ob['material_spec'] = mat
        ob['desc'] = text['desc']
        ob['ex'] = json.dumps(ex)
        objs.append((ob, legs))
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        rows.append(dict(name=name, name_cn=ob['name_cn'], material=mat, sources=sources, tris=tris, ex=ex))
    left = [ob.name for ob in bpy.data.objects if ob.type == 'MESH' and ob not in [o for o, _ in objs]]
    if left:
        raise RuntimeError('这些零件没有归到任何单元：%s' % left)
    keys = [json.dumps(r['ex']) for r in rows]
    dup = [r['name'] for r, k in zip(rows, keys) if k != '[]' and keys.count(k) > 1]
    if dup:   # 虚幻那边按爆炸路线分组，路线一样的单元会被合成一个
        raise RuntimeError('这些单元的爆炸路线完全一样：%s' % dup)

    for ob in bpy.context.scene.objects:
        ob.select_set(ob.type == 'MESH')
    glb = os.path.join(out, 'etcher_ue.glb')
    kw = dict(filepath=glb, export_format='GLB', use_selection=True, export_apply=True, export_extras=True,
              export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        for k in ('export_animations', 'export_cameras', 'export_lights'):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    with open(os.path.join(out, 'etcher_ue_parts.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('[OK] %d 个单元（%d 个能抓），%d 个三角面，%d KB → %s' % (
        len(rows), len(rows) - 1, sum(r['tris'] for r in rows), os.path.getsize(glb) // 1024, glb))

    if '--check' in flags:
        check_overlaps(objs, (0.25, 0.5, 0.75, 1.0))
    if '--preview' in flags:
        render_previews(out, objs)


if __name__ == '__main__':
    main()
