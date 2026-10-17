# -*- coding: utf-8 -*-
"""
程序化生成 Godot 版用的贴图和声音（只依赖 numpy；Blender 自带的 Python 里就有，所以 bat 用 Blender 来跑它）。

    blender --background --factory-startup --python make_assets.py
    或  python make_assets.py      （装了 numpy 的普通 Python 也行）

输出到 godot/model/tex/ 和 godot/model/snd/（已在 .gitignore 里，不进仓库）。

为什么自己"算"而不是下载素材:
    1) 一键 bat 不依赖任何素材网站，离线也能跑；
    2) 贴图: 用"频域合成噪声"——白噪声做 FFT、按 1/f^β 衰减、再逆变换。FFT 天生是周期的，所以生成的图
       左右上下自动无缝衔接，可以无限平铺；
    3) 声音: 海浪 = 低通噪声 × 周期性包络（涌起→拍岸→回落的嘶嘶声），脚步 = 短噪声冲击按地面材质换滤波……
       真实录音当然更像，但程序化声音体积小、能无缝循环、而且每个参数都能调。
想换成真实素材: 把同名文件（.png / .wav）放进 godot/hd/ 文件夹，Godot 会优先用它（见 README）。
"""
import math
import os
import struct
import sys
import wave
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "godot", "model", "tex")
SND = os.path.join(HERE, "godot", "model", "snd")
N = 1024                     # 贴图边长（像素）
SR = 22050                   # 声音采样率

rng = np.random.default_rng(20261017)


# ===================================================================== 小工具
def save_png(path, arr):
    """arr: HxW (灰度) 或 HxWx3 (RGB)，取值 0..1。纯 zlib 写 PNG，不依赖 PIL。"""
    a = np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if a.ndim == 2:
        ctype, ch = 0, 1
    else:
        ctype, ch = 2, 3
    h, w = a.shape[:2]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def noise(n=N, beta=2.0, sx=1.0, sy=1.0, seed=None, m=None):
    """周期（可无缝平铺）噪声。beta 越大越"糊"；sx/sy 拉伸频率 → 各向异性（木纹）。"""
    r = rng if seed is None else np.random.default_rng(seed)
    mm = n if m is None else m
    w = r.standard_normal((n, mm))
    fy = np.fft.fftfreq(n)[:, None] * n * sy
    fx = np.fft.fftfreq(mm)[None, :] * mm * sx
    k = np.sqrt(fx * fx + fy * fy)
    k[0, 0] = 1.0
    f = np.fft.fft2(w) / k ** (beta / 2.0)
    f[0, 0] = 0
    out = np.real(np.fft.ifft2(f))
    out -= out.min()
    return out / max(out.max(), 1e-9)


def normal_from_height(h, strength):
    """高度图 → 法线贴图（OpenGL 约定，Godot 用的就是这个）。np.roll 保证边缘也无缝。"""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l, ny / l, nz / l], -1) * 0.5 + 0.5


def lerp(a, b, t):
    t = t[..., None] if np.ndim(t) == 2 else t
    return np.asarray(a) * (1 - t) + np.asarray(b) * t


def hash01(i, salt=0):
    """整数 → 0..1 伪随机（给每块木板/瓷砖不同的颜色）。"""
    x = (np.asarray(i, dtype=np.int64) * 374761393 + salt * 668265263) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((x ^ (x >> 16)) & 0xFFFF) / 65535.0


def save_set(name, albedo, height, rough, nstrength):
    save_png(os.path.join(TEX, f"{name}_albedo.png"), albedo)
    save_png(os.path.join(TEX, f"{name}_normal.png"), normal_from_height(height, nstrength))
    save_png(os.path.join(TEX, f"{name}_rough.png"), rough)
    print("[assets] tex", name)


# ===================================================================== 贴图
def planks(tile_m, plank_w, plank_l, gap_m, c_dark, c_light, grain_amt, seed, weathered=False):
    """木板: 每行一条，行内随机错缝。返回 albedo, height, rough。木板沿图像竖直方向（v）铺。"""
    px = N / tile_m
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)
    rows = int(round(tile_m / plank_w))
    pw = N / rows
    row = np.floor(xx / pw).astype(int)
    offs = hash01(np.arange(rows), seed) * plank_l * px
    ylen = plank_l * px
    yshift = (yy + offs[row]) % N
    col = np.floor(yshift / ylen).astype(int)
    pid = row * 97 + col
    # 每块板一条木纹: 同一张拉伸噪声，按木板编号错开取样位置
    grain = noise(beta=2.4, sx=6.0, sy=0.25, seed=seed)
    fine = noise(beta=1.2, seed=seed + 1)
    g = np.empty_like(grain)
    sh = (hash01(pid, seed + 2) * N).astype(int)
    for r in range(rows):
        m = row == r
        g[m] = np.roll(grain, int(hash01(r, seed + 3) * N), axis=0)[m]
    g = (g + np.roll(g, 0, 1)) * 0.5
    tone = hash01(pid, seed + 4)
    t = np.clip(0.25 + 0.5 * tone + grain_amt * (g - 0.5) + 0.12 * (fine - 0.5), 0, 1)
    alb = lerp(c_dark, c_light, t)
    # 缝: 到木板边缘的距离
    ex = np.minimum(xx % pw, pw - xx % pw)
    ey = np.minimum(yshift % ylen, ylen - yshift % ylen)
    gpx = max(1.0, gap_m * px)
    seam = np.clip(np.minimum(ex, ey) / gpx - 0.5, 0, 1)
    alb = alb * (0.35 + 0.65 * seam[..., None])
    height = 0.6 * seam + 0.06 * g + 0.02 * fine
    rough = np.clip(0.42 + 0.25 * (1 - seam) + 0.15 * (g - 0.5) + (0.2 if weathered else 0), 0, 1)
    if weathered:
        alb = lerp(alb, np.array([0.55, 0.52, 0.48]), 0.25 * noise(beta=2.0, seed=seed + 5))
    return alb, height, rough


def tiles(tile_m, size_m, grout_m, c_a, c_b, grout_c, seed):
    px = N / tile_m
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)
    s = size_m * px
    tid = (np.floor(xx / s) * 31 + np.floor(yy / s)).astype(int)
    ex = np.minimum(xx % s, s - xx % s)
    ey = np.minimum(yy % s, s - yy % s)
    gp = grout_m * px
    joint = np.clip((np.minimum(ex, ey) - gp * 0.5) / 2.0, 0, 1)
    n1 = noise(beta=1.6, seed=seed)
    n2 = noise(beta=2.8, seed=seed + 1)
    t = np.clip(0.3 + 0.4 * hash01(tid, seed) + 0.3 * (n2 - 0.5) + 0.15 * (n1 - 0.5), 0, 1)
    alb = lerp(lerp(c_a, c_b, t), grout_c, 1 - joint)
    height = 0.7 * joint + 0.05 * n1
    rough = np.clip(0.55 + 0.25 * (1 - joint) + 0.1 * (n1 - 0.5), 0, 1)
    return alb, height, rough


def make_textures():
    os.makedirs(TEX, exist_ok=True)
    # 室内木地板（橡木），贴图覆盖 2.4m
    a, h, r = planks(2.4, 0.2, 1.2, 0.003, (0.30, 0.18, 0.09), (0.66, 0.46, 0.27), 0.55, 11)
    save_set("wood_floor", a, h, r, 6.0)
    # 户外柚木平台: 板宽 14cm、缝 1cm、风化
    a, h, r = planks(1.2, 0.15, 1.2, 0.01, (0.24, 0.15, 0.08), (0.55, 0.38, 0.22), 0.7, 21, weathered=True)
    save_set("deck", a, h, r, 10.0)
    # 阳台石材 60cm 方砖
    a, h, r = tiles(1.2, 0.6, 0.006, (0.70, 0.68, 0.63), (0.84, 0.82, 0.77), (0.55, 0.53, 0.50), 31)
    save_set("stone_tile", a, h, r, 5.0)
    # 泳池马赛克 5cm
    a, h, r = tiles(0.6, 0.05, 0.003, (0.30, 0.62, 0.72), (0.52, 0.80, 0.86), (0.85, 0.88, 0.88), 41)
    save_set("pool_tile", a, h, r * 0.5, 4.0)
    # 沙滩: 大尺度起伏 + 风吹的沙纹 + 颗粒
    yy, xx = np.mgrid[0:N, 0:N] / N
    warp = noise(beta=3.0, seed=51)
    ripple = 0.5 + 0.5 * np.sin((yy * 22 + warp * 3.0) * 2 * math.pi)
    grain = noise(beta=0.6, seed=52)
    big = noise(beta=3.2, seed=53)
    h = 0.5 * big + 0.25 * ripple + 0.25 * grain
    alb = lerp((0.66, 0.53, 0.35), (0.86, 0.74, 0.54), np.clip(0.3 + 0.5 * big + 0.35 * (grain - 0.5), 0, 1))
    save_set("sand", alb, h, np.clip(0.85 + 0.1 * grain, 0, 1), 7.0)
    # 白墙（细微抹灰起伏）
    n1, n2 = noise(beta=2.6, seed=61), noise(beta=1.0, seed=62)
    alb = lerp((0.80, 0.79, 0.75), (0.90, 0.89, 0.86), np.clip(0.5 + 0.4 * (n1 - 0.5) + 0.2 * (n2 - 0.5), 0, 1))
    save_set("plaster", alb, 0.7 * n1 + 0.3 * n2, 0.85 + 0.08 * n2, 1.5)
    # 清水混凝土（模板印 + 气孔）
    n1, n2 = noise(beta=2.2, seed=71), noise(beta=0.8, seed=72)
    pores = (n2 > 0.86).astype(float)
    alb = lerp((0.42, 0.41, 0.39), (0.62, 0.61, 0.58), np.clip(0.5 + 0.6 * (n1 - 0.5) - 0.3 * pores, 0, 1))
    save_set("concrete", alb, n1 - 0.4 * pores, 0.85 + 0.1 * n2, 3.0)
    # 布料（经纬编织）
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)
    weave = (np.sin(xx * 2 * math.pi / 8) * np.sign(np.sin(yy * 2 * math.pi / 16)) + 1) * 0.5
    n1 = noise(beta=2.0, seed=81)
    alb = np.ones((N, N, 3)) * (0.75 + 0.15 * weave[..., None] + 0.1 * (n1[..., None] - 0.5))
    save_set("fabric", np.clip(alb, 0, 1), weave * 0.6 + 0.4 * n1, 0.95 + 0 * n1, 3.0)
    # 岩石
    n1, n2, n3 = noise(beta=2.6, seed=91), noise(beta=1.4, seed=92), noise(beta=3.4, seed=93)
    h = 0.6 * n1 + 0.25 * n2 + 0.15 * n3
    alb = lerp((0.22, 0.21, 0.20), (0.55, 0.52, 0.48), np.clip(h * 1.2 - 0.1, 0, 1))
    alb = lerp(alb, np.array([0.30, 0.36, 0.22]), np.clip((n3 - 0.6) * 3, 0, 1) * 0.6)   # 青苔
    save_set("rock", alb, h, 0.8 + 0.15 * n2, 9.0)
    # 椰树干（环纹）
    yy, xx = np.mgrid[0:N, 0:N] / N
    n1 = noise(beta=2.0, sx=0.3, sy=4.0, seed=101)
    ring = (np.sin(yy * 2 * math.pi * 24 + n1 * 2) * 0.5 + 0.5) ** 3
    alb = lerp((0.26, 0.19, 0.12), (0.50, 0.40, 0.29), np.clip(0.35 + 0.5 * n1 - 0.35 * ring, 0, 1))
    save_set("bark", alb, 1 - ring + 0.3 * n1, 0.9 + 0 * n1, 6.0)
    make_paintings()


def make_paintings():
    """墙上的画: 程序化"海景抽象画"。想换成自己的图（比如 ComfyUI 生成的）就把 PNG 放进 godot/art/。"""
    palettes = [
        ((0.95, 0.62, 0.35), (0.98, 0.85, 0.62), (0.10, 0.25, 0.42), (0.98, 0.95, 0.85)),   # 夕阳
        ((0.55, 0.75, 0.92), (0.90, 0.94, 0.96), (0.05, 0.35, 0.45), (1.0, 1.0, 0.95)),      # 晴天
        ((0.12, 0.14, 0.30), (0.35, 0.30, 0.50), (0.04, 0.08, 0.18), (0.92, 0.92, 0.80)),   # 夜
    ]
    for k, (sky0, sky1, sea, sun) in enumerate(palettes):
        h, w = (384, 512) if k != 1 else (512, 384)
        yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
        brush = noise(n=h, m=w, beta=1.8, sx=0.3, sy=3.0, seed=200 + k)
        horizon = 0.58 + 0.03 * (brush - 0.5)
        sky = lerp(sky1, sky0, np.clip(1 - yy / horizon, 0, 1) ** 0.8)
        sea_c = lerp(sea, np.array(sky1) * 0.6, np.clip((1 - (yy - horizon) / (1 - horizon)) * 0.5, 0, 1))
        img = np.where((yy < horizon)[..., None], sky, sea_c)
        cx, cy = 0.62, horizon - 0.12
        d = np.sqrt(((xx - cx) * w / h) ** 2 + (yy - cy) ** 2)
        img = lerp(img, sun, np.clip((0.07 - d) * 60, 0, 1))
        refl = (yy > horizon) & (np.abs(xx - cx) < 0.05 * (1 + (yy - horizon) * 3)) & (brush > 0.45)
        img = lerp(img, sun, refl * 0.6)
        img = img * (0.88 + 0.24 * brush[..., None])
        save_png(os.path.join(TEX, f"painting_{k}.png"), np.clip(img, 0, 1))
    print("[assets] paintings")


# ===================================================================== 声音
def save_wav(name, x, peak=0.8):
    x = np.asarray(x, dtype=np.float64)
    x = x / max(np.abs(x).max(), 1e-9) * peak
    pcm = (x * 32767).astype("<i2").tobytes()
    with wave.open(os.path.join(SND, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def colored(n, beta, lo=0.0, hi=None, seed=None):
    """一维周期噪声（beta=0 白、1 粉、2 棕），可选带通 [lo, hi] Hz。周期 = 整段长度 → 循环无缝。"""
    r = rng if seed is None else np.random.default_rng(seed)
    f = np.fft.rfft(r.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    amp = 1.0 / np.maximum(fr, 1.0) ** (beta / 2.0)
    amp[fr < lo] = 0
    if hi:
        amp *= 1.0 / (1.0 + (fr / hi) ** 4)
    return np.fft.irfft(f * amp, n)


def env_ad(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-np.maximum(t - attack, 0) / decay)


def make_sounds():
    os.makedirs(SND, exist_ok=True)
    # --- 海浪 16 秒循环: 两个浪。每个浪 = 低频涌动 + 拍岸冲击 + 退去的嘶嘶声
    L = 16 * SR
    t = np.arange(L) / SR
    body = colored(L, 2.0, 30, 900, seed=1)
    hiss = colored(L, 0.6, 1500, 7000, seed=2)
    e_body = np.zeros(L)
    e_hiss = np.zeros(L)
    for start, size in ((0.0, 1.0), (7.3, 0.8)):
        for rep in (-16, 0, 16):                          # 包络也做成周期的
            p = t - start - rep
            e_body += size * np.exp(-((p - 1.6) / 1.1) ** 2) + size * 0.6 * np.exp(-np.maximum(p - 1.6, 0) / 2.0) * (p > 1.6)
            e_hiss += size * 0.7 * np.exp(-np.maximum(p - 2.0, 0) / 2.8) * (p > 1.4) * np.clip((p - 1.4) * 3, 0, 1)
    ocean = body * (0.25 + e_body) + hiss * 0.5 * e_hiss
    save_wav("ocean", ocean, 0.7)
    # --- 风 12 秒循环
    L = 12 * SR
    t = np.arange(L) / SR
    gust = 0.55 + 0.3 * np.sin(2 * math.pi * t / 12) + 0.15 * np.sin(2 * math.pi * 3 * t / 12 + 1)
    save_wav("wind", colored(L, 1.0, 200, 1600, seed=3) * gust, 0.5)
    # --- 脚步: 木地板（闷响 + 一点吱）、沙（沙沙）、石材（硬脆）
    for k in range(3):
        n = int(0.22 * SR)
        thump = colored(n, 2.0, 60, 400, seed=10 + k) * env_ad(n, 0.004, 0.035)
        click = colored(n, 0.0, 1500, 4000, seed=20 + k) * env_ad(n, 0.001, 0.008) * 0.4
        save_wav(f"step_wood_{k}", thump + click, 0.6)
        sand = colored(n, 0.3, 2000, 9000, seed=30 + k) * env_ad(n, 0.02, 0.06) * (0.7 + 0.3 * colored(n, 2.0, 5, 60, seed=40 + k))
        save_wav(f"step_sand_{k}", sand, 0.35)
        hard = colored(n, 0.5, 800, 6000, seed=50 + k) * env_ad(n, 0.001, 0.02) + thump * 0.3
        save_wav(f"step_stone_{k}", hard, 0.5)
    # --- 推拉门（滑轨隆隆声 + 结尾轻碰）
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    rumble = colored(n, 1.5, 80, 1200, seed=60) * np.clip(np.sin(math.pi * t / 1.3), 0, 1) ** 0.5
    knock = colored(n, 1.0, 100, 2000, seed=61) * env_ad(n, 0.002, 0.04)
    knock = np.roll(knock, int(1.3 * SR))
    save_wav("door_slide", rumble * 0.6 + knock, 0.5)
    # --- 开关咔哒
    n = int(0.08 * SR)
    save_wav("click", colored(n, 0.0, 2000, 8000, seed=62) * env_ad(n, 0.0005, 0.006), 0.5)
    # --- 海鸥: 频率先升后降的 "kee-ow"，带谐波和颤动
    for k in range(2):
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        f = 1500 + 700 * np.sin(math.pi * np.clip(t / 0.25, 0, 1)) - 900 * np.clip((t - 0.25) / 0.6, 0, 1)
        f *= 1.0 + 0.04 * np.sin(2 * math.pi * 28 * t) + 0.05 * k
        ph = 2 * math.pi * np.cumsum(f) / SR
        s = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)
        save_wav(f"gull_{k}", s * env_ad(n, 0.03, 0.35) * (t < 0.85), 0.45)
    # --- 篝火 10 秒循环: 低沉的火焰声 + 随机噼啪
    L = 10 * SR
    roar = colored(L, 2.0, 40, 500, seed=70) * (0.6 + 0.4 * colored(L, 2.0, 0.2, 3, seed=71) / 3)
    crack = np.zeros(L)
    r = np.random.default_rng(72)
    for pos in r.integers(0, L - 3000, 70):
        m = int(r.integers(200, 1500))
        crack[pos:pos + m] += colored(m, 0.0, 1500, 8000, seed=int(pos)) * env_ad(m, 0.0003, 0.004 + r.random() * 0.01) * r.random()
    save_wav("fire", roar * 0.5 + crack * 2.0, 0.6)
    # --- 入水 / 水下
    n = int(0.9 * SR)
    save_wav("splash", colored(n, 0.5, 300, 6000, seed=80) * env_ad(n, 0.01, 0.25), 0.7)
    L = 8 * SR
    save_wav("underwater", colored(L, 2.0, 20, 300, seed=81), 0.5)
    # --- 球弹地
    n = int(0.15 * SR)
    t = np.arange(n) / SR
    save_wav("ball", np.sin(2 * math.pi * 180 * t * (1 - t)) * env_ad(n, 0.001, 0.03) + 0.2 * colored(n, 1.0, 200, 3000, seed=82) * env_ad(n, 0.001, 0.01), 0.6)
    # --- 收音机: 慢速五声音阶琶音 + 柔和和弦铺底（24 秒循环）
    L = 24 * SR
    t = np.arange(L) / SR
    out = np.zeros(L)
    chords = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)]
    scale = [440.0, 493.88, 554.37, 659.25, 739.99, 880.0]
    r = np.random.default_rng(90)
    for ci, ch in enumerate(chords):
        s0, s1 = ci * 6 * SR, (ci + 1) * 6 * SR
        tt = t[s0:s1] - ci * 6
        pad = sum(np.sin(2 * math.pi * f * tt) + 0.3 * np.sin(4 * math.pi * f * tt) for f in ch)
        out[s0:s1] += pad * 0.12 * np.clip(tt / 0.8, 0, 1) * np.clip((6 - tt) / 0.8, 0, 1)
        for b in range(12):                                     # 每拍一个音符
            f = scale[int(r.integers(0, len(scale)))]
            st = s0 + int(b * 0.5 * SR)
            m = int(1.2 * SR)
            if st + m > L:
                m = L - st
            tn = np.arange(m) / SR
            out[st:st + m] += (np.sin(2 * math.pi * f * tn) + 0.2 * np.sin(6 * math.pi * f * tn)) * np.exp(-tn / 0.35) * 0.3
    save_wav("radio", out, 0.5)
    print("[assets] sounds")


def up_to_date():
    """生成器源码没变、输出也都在 → 跳过（bat 每次启动都会调用本脚本，避免每次多等 10 秒）。"""
    import hashlib
    with open(os.path.abspath(__file__), "rb") as f:
        h = hashlib.sha1(f.read()).hexdigest()
    stamp = os.path.join(HERE, "godot", "model", "assets.stamp")
    ok = os.path.exists(stamp) and open(stamp).read().strip() == h \
        and os.path.exists(os.path.join(TEX, "sand_albedo.png")) and os.path.exists(os.path.join(SND, "ocean.wav"))
    return ok, stamp, h


if __name__ == "__main__":
    ok, stamp, h = up_to_date()
    if ok and "--force" not in sys.argv:
        print("[assets] up to date, skip")
    else:
        make_textures()
        make_sounds()
        with open(stamp, "w") as f:
            f.write(h)
        print("[assets] done ->", TEX, SND)
