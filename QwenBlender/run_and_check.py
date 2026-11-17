# -*- coding: utf-8 -*-
"""
执行一个模型脚本 → 自动检查 → 渲染四视图 → 保存 .blend
用法（agent.py 会自动调用，一般不用手动跑）：
  blender -b --factory-startup --python run_and_check.py -- models/xxx.py 输出目录
输出：
  输出目录/report.txt    中文检查报告（给模型看）
  输出目录/report.json   同样内容的结构化版本
  输出目录/views.png     2x2 四视图（views_small.png 是缩小一半的版本，发给模型看）
                       （左上 斜视 | 右上 正视（从 -Y 看）| 左下 右视（从 +X 看）| 右下 俯视）
  输出目录/model.blend   可以直接用 Blender 打开
"""
import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')   # 日文 Windows 默认 cp932，打印中文会报错
    except Exception:
        pass

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
MODEL = os.path.abspath(ARGV[0])
OUT = os.path.abspath(ARGV[1]) if len(ARGV) > 1 else os.path.join(HERE, 'out')
NO_RENDER = '--no-render' in ARGV
os.makedirs(OUT, exist_ok=True)

TOL = 0.05        # mm，判定"在内部"的容差
FLOAT_GAP = 0.5   # mm，离所有零件和地面都超过这个距离 → 悬空
CROSS_TOL = 0.2   # mm，零件表面上的点嵌进另一个零件实体超过这个深度，才算穿插（过滤贴合面的数值误差）


def run_model():
    src = open(MODEL, encoding='utf-8').read()
    ns = {'__name__': '__main__', '__file__': MODEL}
    print('=====MODEL_OUT_BEGIN=====', flush=True)
    try:
        exec(compile(src, MODEL, 'exec'), ns)
        print('=====MODEL_OUT_END=====', flush=True)
        return None, ns
    except Exception:
        print('=====MODEL_OUT_END=====', flush=True)
        tb = traceback.format_exc()
        # 只保留和模型脚本、qbkit 相关的几行，方便模型定位
        lines = [ln for ln in tb.splitlines() if 'run_and_check.py' not in ln]
        return '\n'.join(lines[-12:]), ns


def mesh_objects():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('_')]


def world_data(o):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    mw = o.matrix_world
    vs = [mw @ v.co for v in me.vertices]
    polys = [p.vertices[:] for p in me.polygons]
    ev.to_mesh_clear()
    return vs, polys


def bbox(vs):
    return (Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs))),
            Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs))))


def bbox_overlap(a, b, pad=0.0):
    return all(a[0][i] - pad <= b[1][i] and b[0][i] - pad <= a[1][i] for i in range(3))


def sample(vs, n=1500):
    if len(vs) <= n:
        return vs
    step = len(vs) / n
    return [vs[int(i * step)] for i in range(n)]


def inside_count(vs, tree):
    c = 0
    for v in sample(vs):
        hit = tree.find_nearest(v)
        if hit[0] is None:
            continue
        loc, nor = hit[0], hit[1]
        if (v - loc).dot(nor) < -TOL and (v - loc).length > TOL:
            c += 1
    return c


def min_dist(vs, tree):
    d = 1e9
    for v in sample(vs, 600):
        hit = tree.find_nearest(v)
        if hit[0] is not None:
            d = min(d, hit[3])
    return d


def _plane(pts):
    n = Vector((0, 0, 0))
    k = len(pts)
    for i in range(k):
        a, b = pts[i], pts[(i + 1) % k]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    if n.length < 1e-12:
        return None, 0.0
    n.normalize()
    return n, n.dot(pts[0])


def _poly_samples(pts, step=1.0, n_max=40):
    """在多边形面上均匀撒点。面可能是凹多边形（比如带孔的板面），所以先正确三角化。"""
    from mathutils.geometry import tessellate_polygon
    out = []
    tris = tessellate_polygon([pts]) if len(pts) > 3 else [(0, 1, 2)]
    for a, b, c in tris:
        p0, p1, p2 = pts[a], pts[b], pts[c]
        longest = max((p1 - p0).length, (p2 - p1).length, (p0 - p2).length)
        n = max(3, min(n_max, int(longest / step) + 1))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                out.append(p0 + (p1 - p0) * u + (p2 - p0) * v)
    return out


def _depth_inside(p, tree):
    hit = tree.find_nearest(p)
    if hit[0] is None:
        return 0.0
    d = (p - hit[0]).dot(hit[1])
    return -d if d < 0 else 0.0


def crossing_count(A, B, limit=60, max_pairs=600):
    """返回 (嵌进去的采样点数, 最深嵌进去多少 mm)"""
    """在两个零件互相重叠的面上撒点，统计"嵌进对方实体超过 CROSS_TOL"的点数。
    只是贴合或者碰到边的话，点都在对方表面或外面，数出来是 0。"""
    c = 0
    deep = 0.0
    pairs = A['tree'].overlap(B['tree'])[:max_pairs]
    done_a, done_b = set(), set()
    for i, j in pairs:
        if i not in done_a:
            done_a.add(i)
            for p in _poly_samples([A['vs'][k] for k in A['polys'][i]]):
                dp = _depth_inside(p, B['tree'])
                if dp > CROSS_TOL:
                    c += 1
                    deep = max(deep, dp)
        if j not in done_b:
            done_b.add(j)
            for p in _poly_samples([B['vs'][k] for k in B['polys'][j]]):
                dp = _depth_inside(p, A['tree'])
                if dp > CROSS_TOL:
                    c += 1
                    deep = max(deep, dp)
        if c >= limit:
            break
    return c, deep


def check(allow):
    objs = mesh_objects()
    data = {}
    for o in objs:
        vs, polys = world_data(o)
        if not vs:
            continue
        data[o.name] = dict(vs=vs, polys=polys, bb=bbox(vs), tree=BVHTree.FromPolygons(vs, polys),
                            mat=(o.data.materials[0].name if o.data.materials and o.data.materials[0] else '无'))
    names = sorted(data)
    allow_set = {tuple(sorted(p)) for p in allow}
    parts, clashes, contacts, below = [], [], [], []
    for n in names:
        mn, mx = data[n]['bb']
        s = mx - mn
        parts.append(dict(name=n, size=[round(s.x, 2), round(s.y, 2), round(s.z, 2)],
                          min=[round(mn.x, 2), round(mn.y, 2), round(mn.z, 2)],
                          max=[round(mx.x, 2), round(mx.y, 2), round(mx.z, 2)], material=data[n]['mat']))
        if mn.z < -TOL:
            below.append((n, round(mn.z, 2)))
    link = {n: set() for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = data[a], data[b]
            if not bbox_overlap(A['bb'], B['bb'], FLOAT_GAP + 0.01):
                continue
            pair = tuple(sorted((a, b)))
            allowed = pair in allow_set
            if bbox_overlap(A['bb'], B['bb']):
                tri = len(A['tree'].overlap(B['tree']))
                ins = inside_count(A['vs'], B['tree']) + inside_count(B['vs'], A['tree'])
                cross, deep = crossing_count(A, B) if tri else (0, 0.0)
                if ins > 0 or cross > 0:
                    clashes.append(dict(a=a, b=b, inside_points=ins, crossing=cross, depth=round(deep, 2), allowed=allowed))
                    link[a].add(b); link[b].add(a)
                    continue
                if tri > 0:
                    contacts.append(dict(a=a, b=b, tri=tri, allowed=allowed))
                    link[a].add(b); link[b].add(a)
                    continue
            d = min(min_dist(A['vs'], B['tree']), min_dist(B['vs'], A['tree']))
            if d <= FLOAT_GAP:
                link[a].add(b); link[b].add(a)
    # 从"碰到地面"的零件出发，沿接触关系走一遍；走不到的就是悬空的（整组悬空也能发现）
    grounded = {n for n in names if data[n]['bb'][0].z <= FLOAT_GAP}
    seen, stack = set(grounded), list(grounded)
    while stack:
        n = stack.pop()
        for m in link[n]:
            if m not in seen:
                seen.add(m)
                stack.append(m)
    floating = []
    for n in names:
        if n in seen:
            continue
        best = None
        for m in seen:
            if not bbox_overlap(data[n]['bb'], data[m]['bb'], 300):
                continue
            d = min(min_dist(data[n]['vs'], data[m]['tree']), min_dist(data[m]['vs'], data[n]['tree']))
            if best is None or d < best[0]:
                best = (d, m)
        floating.append((n, None if best is None else (round(best[0], 2), best[1])))
    return dict(parts=parts, clashes=clashes, contacts=contacts, floating=floating, below=below,
                grounded=sorted(grounded))


# ------------------------------------------------------------------ 渲染
def setup_scene_bounds():
    objs = mesh_objects()
    allv = []
    for o in objs:
        vs, _ = world_data(o)
        allv += vs
    if not allv:
        return Vector((0, 0, 0)), 100.0
    mn, mx = bbox(allv)
    return (mn + mx) / 2, max((mx - mn).length, 1.0)


def make_cam(name, ortho, loc, target, scale):
    cd = bpy.data.cameras.new(name)
    cd.clip_start = scale * 0.001
    cd.clip_end = scale * 50
    if ortho:
        cd.type = 'ORTHO'
        cd.ortho_scale = scale * 1.15
    else:
        cd.lens = 50
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob


def setup_look(engine):
    sc = bpy.context.scene
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    sc.world = w
    w.color = (0.92, 0.93, 0.95)
    sc.render.film_transparent = False
    if engine == 'WORKBENCH':
        sc.render.engine = 'BLENDER_WORKBENCH'
        sh = sc.display.shading
        sh.light = 'STUDIO'
        sh.color_type = 'MATERIAL'
        sh.show_cavity = True
        sh.cavity_type = 'BOTH'
        sh.show_object_outline = True
        sh.background_type = 'WORLD' if hasattr(sh, 'background_type') else sh.background_type
        sc.display.render_aa = '8'
    else:
        sc.render.engine = 'CYCLES'
        sc.cycles.samples = 16
        try:
            w.use_nodes = True
            bg = w.node_tree.nodes.get('Background')
            if bg:
                bg.inputs[0].default_value = (0.92, 0.93, 0.95, 1)
                bg.inputs[1].default_value = 1.2
        except Exception:
            pass
    sc.view_settings.view_transform = 'Standard'


def render_views():
    sc = bpy.context.scene
    c, size = setup_scene_bounds()
    W, H = 800, 600
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    d = size * 1.8
    views = [
        ('iso', False, c + Vector((0.62, -0.78, 0.55)).normalized() * d * 1.25),
        ('front', True, c + Vector((0, -d, 0))),
        ('right', True, c + Vector((d, 0, 0))),
        ('top', True, c + Vector((0, 0, d))),
    ]
    files = []
    # 检查用的渲染：把金属度压低，避免工作台渲染里金属件发黑看不清（渲染完恢复）
    saved = [(m, m.metallic) for m in bpy.data.materials]
    for m, v in saved:
        m.metallic = min(v, 0.15)
    for engine in ('WORKBENCH', 'CYCLES'):
        try:
            setup_look(engine)
            files = []
            for name, ortho, loc in views:
                cam = make_cam('_cam_' + name, ortho, loc, c, size)
                if name == 'top':
                    cam.rotation_euler = (0, 0, 0)
                sc.camera = cam
                fp = os.path.join(OUT, f'_view_{name}.png')
                sc.render.filepath = fp
                bpy.ops.render.render(write_still=True)
                files.append(fp)
                bpy.data.objects.remove(cam, do_unlink=True)
            break
        except Exception as e:
            print('[render] %s 失败，换下一个引擎：%s' % (engine, e))
    for m, v in saved:
        m.metallic = v
    if len(files) != 4:
        return None
    # 拼成 2x2
    import numpy as np
    tiles = []
    for fp in files:
        im = bpy.data.images.load(fp)
        px = np.array(im.pixels[:], dtype=np.float32).reshape(H, W, 4)
        tiles.append(px)
        bpy.data.images.remove(im)
    # Blender 图像行从下往上：左上=iso，右上=front，左下=right，右下=top
    top_row = np.concatenate([tiles[0], tiles[1]], axis=1)
    bot_row = np.concatenate([tiles[2], tiles[3]], axis=1)
    grid = np.concatenate([bot_row, top_row], axis=0)
    grid[H - 1:H + 1, :, :3] = 0.3
    grid[:, W - 1:W + 1, :3] = 0.3
    img = bpy.data.images.new('views', W * 2, H * 2, alpha=True)
    img.pixels[:] = grid.ravel()
    out = os.path.join(OUT, 'views.png')
    img.filepath_raw = out
    img.file_format = 'PNG'
    img.save()
    # 再存一张缩小一半的（800x600），发给模型看，省上下文
    small = grid.reshape(H, 2, W, 2, 4).mean(axis=(1, 3))
    img2 = bpy.data.images.new('views_small', W, H, alpha=True)
    img2.pixels[:] = small.ravel()
    img2.filepath_raw = os.path.join(OUT, 'views_small.png')
    img2.file_format = 'PNG'
    img2.save()
    for fp in files:
        try:
            os.remove(fp)
        except OSError:
            pass
    return out


def write_report(err, res, views, ns):
    L = []
    if err:
        L.append('【结果】脚本运行出错，模型没有建完。请根据下面的报错修改脚本：')
        L.append(err)
    if res is not None:
        parts = res['parts']
        L.append(f'【零件】共 {len(parts)} 个（尺寸 = 包围盒 长x宽x高，单位 mm）')
        for p in parts:
            L.append(f"  {p['name']}: {p['size'][0]} x {p['size'][1]} x {p['size'][2]}  "
                     f"x[{p['min'][0]}, {p['max'][0]}] y[{p['min'][1]}, {p['max'][1]}] z[{p['min'][2]}, {p['max'][2]}]  材质:{p['material']}")
        bad = [c for c in res['clashes'] if not c['allowed']]
        L.append(f'【穿插】{len(bad)} 处（两个零件的实体互相嵌进去了）')
        for c in bad:
            L.append(f"  {c['a']} × {c['b']}：互相嵌进去" + (f"，最深约 {c['depth']} mm" if c['depth'] else '') +
                     "（注意：采样有间隔，实际可能更深）")
        ok = [c for c in res['clashes'] if c['allowed']]
        if ok:
            L.append('  （以下穿插在 ALLOW_TOUCH 里声明过，是设计上允许的：' +
                     '，'.join(f"{c['a']}×{c['b']}" for c in ok) + '）')
        if res['contacts']:
            L.append('【接触】' + '，'.join(f"{c['a']}×{c['b']}" for c in res['contacts']) + '（表面贴合，一般正常）')
        L.append(f"【悬空】{len(res['floating'])} 个（顺着零件之间的接触关系，连不到地面 z=0 上的零件）")
        for n, d in res['floating']:
            L.append(f"  {n}" + (f"：离最近的有支撑零件 {d[1]} 还差 {d[0]} mm" if d else "：附近没有任何有支撑的零件"))
        if res['below']:
            L.append('【低于地面】' + '，'.join(f"{n}(最低 z={z})" for n, z in res['below']))
        problems = len(bad) + len(res['floating']) + len(res['below'])
        if not err:
            L.append('【结论】' + ('自动检查没有发现问题。请再看四视图，确认形状和比例符合要求。' if problems == 0
                                 else f'有 {problems} 个问题需要处理。'))
    if views:
        L.append('【四视图】views.png：左上=斜视，右上=正视（从 -Y 方向看），左下=右视（从 +X 方向看），右下=俯视。正视/右视/俯视是正交投影，可以直接比较尺寸比例。')
    txt = '\n'.join(L)
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write(txt + '\n')
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(error=err, result=res, views=views), f, ensure_ascii=False, indent=1)
    print(txt)


def main():
    err, ns = run_model()
    res = None
    views = None
    if mesh_objects():
        try:
            res = check(ns.get('ALLOW_TOUCH', []))
        except Exception:
            err = (err or '') + '\n[检查器出错]\n' + traceback.format_exc()[-1500:]
        try:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'model.blend'))
        except Exception as e:
            print('[save] 失败', e)
        if not NO_RENDER:
            try:
                views = render_views()
            except Exception:
                print('[render] 失败\n' + traceback.format_exc())
    elif not err:
        err = '脚本运行完了，但场景里一个零件都没有。是不是忘了调用建模函数？'
    write_report(err, res, views, ns)


main()
