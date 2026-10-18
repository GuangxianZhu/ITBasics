# -*- coding: utf-8 -*-
"""云端预览: 用一个很小的软件光栅器 (正交投影, 贴图 + alpha 测试 + 兰伯特光照) 把 c8x_trees 生成的植物画出来,
不用进 UE 就能看形状和叶片卡效果。输出 shots/plants_preview.jpg"""
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import c8x_trees as T  # noqa: E402

TEX = os.path.join(HERE, "..", "tex")
LEAF_TEX = {"Olive": "T_olive_leaves", "Fig": "T_fig_leaves", "Lemon": "T_lemon_leaves", "OliveShrub": "T_olive_leaves",
            "PotShrub": "T_rosemary", "Lavender": "T_lavender", "Rosemary": "T_rosemary", "BougaWall": "T_bougainvillea"}


def load(name, size=256):
    im = Image.open(os.path.join(TEX, name + ".png")).convert("RGBA").resize((size, size))
    return np.asarray(im).astype(np.float32) / 255


def render(parts, W=520, H=520, yaw=30, extent=None):
    a = math.radians(yaw)
    R = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1]])
    allv = np.concatenate([np.asarray(p.V) for p, _ in parts if p.V])
    allv = allv @ R.T
    lo, hi = allv.min(0), allv.max(0)
    ext = extent or max(hi[0] - lo[0], hi[2] - lo[2]) * 1.05
    cx = (lo[0] + hi[0]) / 2
    img = np.zeros((H, W, 3), np.float32) + np.array([0.80, 0.86, 0.92])
    zb = np.full((H, W), -1e9, np.float32)
    L = T.norm([0.4, -0.6, 0.7]) @ R.T           # 光从镜头左前上方来
    L = np.array([0.5, -0.6, 0.65])
    L = L / np.linalg.norm(L)
    for part, tex in parts:
        if not part.F:
            continue
        V = np.asarray(part.V) @ R.T
        N = np.asarray(part.N) @ R.T
        UV = np.asarray(part.UV)
        sx = (V[:, 0] - cx) / ext * W + W / 2
        sy = H - 10 - (V[:, 2] - 0) / ext * H
        dep = -V[:, 1]
        for f in part.F:
            i, j, k = f
            xs, ys = sx[[i, j, k]], sy[[i, j, k]]
            x0, x1 = int(max(0, xs.min())), int(min(W - 1, xs.max() + 1))
            y0, y1 = int(max(0, ys.min())), int(min(H - 1, ys.max() + 1))
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(d) < 1e-9:
                continue
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
            w2 = 1 - w0 - w1
            m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not m.any():
                continue
            z = w0 * dep[i] + w1 * dep[j] + w2 * dep[k]
            u = w0 * UV[i, 0] + w1 * UV[j, 0] + w2 * UV[k, 0]
            v = w0 * UV[i, 1] + w1 * UV[j, 1] + w2 * UV[k, 1]
            th, tw = tex.shape[:2]
            tx = (np.mod(u, 1) * (tw - 1)).astype(int)
            ty = (np.mod(v, 1) * (th - 1)).astype(int)
            c = tex[ty, tx]
            m &= c[..., 3] > 0.4
            yy, xx = np.nonzero(m)
            Y, X = yy + y0, xx + x0
            zz = z[m]
            closer = zz > zb[Y, X]
            Y, X, zz = Y[closer], X[closer], zz[closer]
            n = (w0[m][closer, None] * N[i] + w1[m][closer, None] * N[j] + w2[m][closer, None] * N[k])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            lam = np.clip(n @ L, 0, 1) * 0.75 + 0.35
            zb[Y, X] = zz
            img[Y, X] = c[m][closer, :3] * lam[:, None]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), ext


def main():
    plants = T.main()
    bark = load("T_olive_bark")
    figbark = bark * np.array([1.25, 1.25, 1.3, 1])
    tiles = []
    for name in ("Olive", "Fig", "Lemon", "OliveShrub", "Lavender", "Rosemary", "BougaWall"):
        b, l, _ = plants[name]
        im, ext = render([(b, figbark if name == "Fig" else bark), (l, load(LEAF_TEX[name]))],
                         yaw=0 if name == "BougaWall" else 30)
        from PIL import ImageDraw
        ImageDraw.Draw(im).text((8, 8), "%s  %.1f m" % (name, ext), fill=(0, 0, 0))
        tiles.append(im)
    W = 520
    sheet = Image.new("RGB", (W * 4, W * 2), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 4) * W, (i // 4) * W))
    out = os.path.join(HERE, "..", "shots", "plants_preview.jpg")
    sheet.save(out, quality=88)
    print(out)


if __name__ == "__main__":
    main()
