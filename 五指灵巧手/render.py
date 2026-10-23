# -*- coding: utf-8 -*-
"""渲染多视角 / 姿态 / 爆炸图，以及动画 GIF 帧。
用法：python render.py [--quick] [--views front,back,...] [--anim N] [--out renders]
"""
import os, sys, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import build_hand as B

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT = os.path.abspath(opt("--out", os.path.join(B.HERE, "output", "renders")))
os.makedirs(OUT, exist_ok=True)
QUICK = "--quick" in argv
hand = B.build()
sc = bpy.context.scene
cam = sc.camera
sc.render.resolution_x = int(opt("--res", 900))
sc.render.resolution_y = int(opt("--resy", opt("--res", 900)))
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = int(opt("--samples", 12 if QUICK else 48))
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"

T = (0, 0, 0.105)
# 静帧直接取时间轴上的关键帧（.blend 里的动画就是唯一真值）
VIEWS = {
    "hero":    dict(loc=(0.22, -0.40, 0.24), frame="rest"),
    "front":   dict(loc=(0.0, -0.50, 0.105), frame="open", lens=62),
    "back":    dict(loc=(0.0, 0.50, 0.105), frame="open", lens=62),
    "side":    dict(loc=(0.50, 0.0, 0.105), frame="open", lens=62),
    "fist":    dict(loc=(0.20, -0.36, 0.20), frame="fist", target=(0, 0, 0.09)),
    "pinch":   dict(loc=(0.30, -0.30, 0.22), frame="pinch", target=(0.01, -0.01, 0.10)),
    "spread":  dict(loc=(0.08, -0.48, 0.18), frame="spread"),
    "explode": dict(loc=(0.30, -0.50, 0.30), frame="explode", lens=50, target=(0.005, 0, 0.125)),
}

views = opt("--views", "hero,front,side,fist,pinch,spread,explode,back").split(",")
for v in views:
    cfg = VIEWS[v]
    sc.frame_set(B.FRAMES[cfg["frame"]])
    B.aim_camera(cam, cfg["loc"], cfg.get("target", T), cfg.get("lens", 70))
    sc.render.filepath = os.path.join(OUT, v + ".png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("[render] %s %.1fs" % (v, time.time() - t), flush=True)

n = int(opt("--anim", 0))
if n:
    d = os.path.join(OUT, "anim")
    os.makedirs(d, exist_ok=True)
    sc.render.resolution_x = sc.render.resolution_y = int(opt("--animres", 540))
    sc.cycles.samples = int(opt("--animsamples", 16))
    frames = [round(1 + i * (sc.frame_end - 1) / (n - 1)) for i in range(n)]
    for i, fr in enumerate(frames):
        sc.frame_set(fr)
        ang = math.radians(-35 + 70 * i / (n - 1))   # 缓慢环绕
        r = 0.62
        B.aim_camera(cam, (r * math.sin(ang), -r * math.cos(ang), 0.27), (0, 0, 0.115), 62)
        sc.render.filepath = os.path.join(d, "f%04d.png" % i)
        bpy.ops.render.render(write_still=True)
        print("[anim] %d/%d" % (i + 1, n), flush=True)
