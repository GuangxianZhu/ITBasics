# -*- coding: utf-8 -*-
"""
范例 1：L 形安装支架 + 4 颗螺栓
学习要点：
  1. 先把所有尺寸写成变量，后面只用变量计算位置，不要到处写死数字
  2. at 是物体中心：放在地面上的板，中心 z = 板厚 / 2
  3. 打孔用 hole()，螺栓的位置和孔的位置用同一组变量算出来，保证对齐
  4. 螺栓头"坐"在板面上：螺栓头中心 z = 板面高度 + 头高 / 2
"""
import qbkit as K

K.reset()

# ---------------- 尺寸（mm）
BASE_L, BASE_W, T = 120, 80, 6          # 底板 长 x 宽，板厚
WALL_H = 70                              # 竖板高度（从底板上表面算起）
HOLE_R = 3.3                             # M6 螺栓过孔半径
HOLE_DX, HOLE_DY = 40, 25                # 底板孔距中心的偏移
BOLT_R, HEAD_R, HEAD_H = 3.0, 5.0, 4.0   # 螺杆半径、螺栓头半径、头高

steel = K.mat('steel', '#b8bec6', metal=0.9, rough=0.35)
bolt_m = K.mat('bolt_black', '#2b2d31', metal=0.6, rough=0.4)

# ---------------- 底板：放在地面上
base = K.box('base_plate', (BASE_L, BASE_W, T), at=(0, 0, T / 2), mat=steel, bevel=0.8)

# ---------------- 竖板：立在底板后边缘（y 正方向），底面贴着底板上表面
wall = K.box('wall_plate', (BASE_L, T, WALL_H), at=(0, BASE_W / 2 - T / 2, T + WALL_H / 2), mat=steel, bevel=0.8)

# ---------------- 底板上打 4 个孔（避开竖板）
hole_pts = [(sx * HOLE_DX, sy * HOLE_DY - 5) for sx in (-1, 1) for sy in (-1, 1)]
for (x, y) in hole_pts:
    K.hole(base, HOLE_R, at=(x, y, T / 2), axis='Z')

# ---------------- 每个孔里放一颗螺栓：螺杆穿过底板，螺栓头压在底板上表面
for i, (x, y) in enumerate(hole_pts, start=1):
    # 螺杆只做到板底（z=0），不往下伸出，否则会低于地面
    shank = K.cyl(f'bolt_{i}_shank', BOLT_R, T, at=(x, y, T / 2), mat=bolt_m)
    head = K.cyl(f'bolt_{i}_head', HEAD_R, HEAD_H, at=(x, y, T + HEAD_H / 2), mat=bolt_m)
    K.join(head, shank)                  # 头和杆合成一个零件
    head.name = f'bolt_{i}'

K.info(base)
K.info(wall)

# 螺杆和孔壁之间有 0.3 mm 间隙，不会穿插；螺栓头底面贴着板面，属于"接触"，正常。
ALLOW_TOUCH = []
