# -*- coding: utf-8 -*-
"""云端: 把本地 Z-Image 生成的白底植物照片抠成带透明通道的叶片卡贴图, 可拼成 2x2 图集。
  alpha: 和背景色 (取四周边框中位数) 的色差 + 饱和度; 去小噪点; 边缘颜色用最近的不透明像素向外填 (防白边/黑边)
用法: python tex_cutout.py out.png a.png b.png c.png d.png   (4 张 -> 2x2 图集, 每格 1024)
      python tex_cutout.py out.png a.png                     (1 张)"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def cutout(path, cell=1024, margin=0.04):
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    border = np.concatenate([im[:8].reshape(-1, 3), im[-8:].reshape(-1, 3), im[:, :8].reshape(-1, 3), im[:, -8:].reshape(-1, 3)])
    bg = np.median(border, 0)
    dist = np.linalg.norm(im - bg, axis=2)
    mx, mn = im.max(2), im.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    lum_drop = np.maximum(0, bg.mean() - im.mean(2))          # 只算明显变暗的 (影子只暗一点, 而且没有饱和度)
    a = np.clip((sat - 0.08) * 3.0 + np.maximum(0, lum_drop - 90) * 0.02, 0, 1)
    a = ndimage.gaussian_filter(a, 0.7)
    a = np.clip((a - 0.25) / 0.5, 0, 1)
    lab, n = ndimage.label(a > 0.5)
    if n:
        sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        keep = np.isin(lab, 1 + np.where(sizes >= 60)[0])
        a = a * ndimage.binary_dilation(keep, iterations=3)
    # 颜色向外填
    solid = a > 0.6
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    col = im[iy, ix]
    # 裁到内容 + 方形
    ys, xs = np.where(a > 0.3)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    s = int(max(y1 - y0, x1 - x0) * (1 + 2 * margin))
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    rgba = np.dstack([col, a * 255]).astype(np.uint8)
    big = np.zeros((s, s, 4), np.uint8)
    sy0, sx0 = cy - s // 2, cx - s // 2
    ys0, xs0 = max(0, sy0), max(0, sx0)
    ys1, xs1 = min(h, sy0 + s), min(w, sx0 + s)
    big[ys0 - sy0:ys1 - sy0, xs0 - sx0:xs1 - sx0] = rgba[ys0:ys1, xs0:xs1]
    # 透明区也填上颜色 (mip 时不混进黑色)
    bb = big.astype(np.float32)
    sol = bb[..., 3] > 150
    if sol.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~sol, return_indices=True)
        bb[..., :3] = bb[iy, ix, :3]
    return Image.fromarray(bb.astype(np.uint8), "RGBA").resize((cell, cell), Image.LANCZOS)


def main():
    out, srcs = sys.argv[1], sys.argv[2:]
    if len(srcs) == 1:
        cutout(srcs[0]).save(out)
    else:
        at = Image.new("RGBA", (2048, 2048))
        for i, p in enumerate(srcs[:4]):
            at.paste(cutout(p), ((i % 2) * 1024, (i // 2) * 1024))
        at.save(out)
    print(out)


if __name__ == "__main__":
    main()
