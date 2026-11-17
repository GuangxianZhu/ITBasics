# -*- coding: utf-8 -*-
"""
范例 2：带底座的轴承座 + 台阶轴 + 法兰 6 颗螺钉（轴线沿 X 方向）
学习要点：
  1. 轴类零件用 revolve()：profile 写成 (半径, 轴向位置)，像画半个剖面
  2. 沿 X 方向的零件统一用 axis='X'，at 的 x 是轴向中心
  3. 套在轴上的零件（轴承座）用 tube()，内径要比轴大一点点（留间隙），否则会被判成"穿插"
  4. 圆周均布的螺钉：先做 1 颗，再用 polar() 绕轴复制
  5. 零件之间的高度关系全部从变量算：轴心高 = 底座高 + 座体外半径
"""
import qbkit as K

K.reset()

# ---------------- 尺寸（mm）
BASE_L, BASE_W, BASE_T = 90, 70, 10      # 底座
HUB_RO, HUB_RI, HUB_L = 28, 16.2, 40     # 轴承座外半径、内孔半径、长度
AXIS_Z = BASE_T + HUB_RO                 # 轴心高度：轴承座外圆的底刚好贴着底座上表面
FLANGE_R, FLANGE_T = 27, 6               # 法兰半径、厚度（贴在轴承座 +X 端面）
# 注意：法兰半径不能大于 HUB_RO（=轴心到底座上表面的距离），否则法兰下缘会插进底座。
# 第一版写成 34，自动检查报了 base × flange 穿插，改成 27 后通过。
SCREW_R, SCREW_HEAD_R, SCREW_HEAD_H = 2.5, 4.2, 3.0
SCREW_PCD = 21.5                         # 螺钉分布圆半径：要满足 内孔半径+头半径 < PCD < 法兰半径-头半径

cast = K.mat('cast_iron', '#6f7780', metal=0.5, rough=0.6)
shaft_m = K.mat('shaft_steel', '#d0d5db', metal=1.0, rough=0.2)
screw_m = K.mat('screw', '#2a2c30', metal=0.6, rough=0.4)

# ---------------- 底座
base = K.box('base', (BASE_L, BASE_W, BASE_T), at=(0, 0, BASE_T / 2), mat=cast, bevel=1)
for sx in (-1, 1):
    for sy in (-1, 1):
        K.hole(base, 4.5, at=(sx * 35, sy * 25, BASE_T / 2), axis='Z')

# ---------------- 轴承座（空心圆筒，轴线沿 X）
hub = K.tube('bearing_housing', HUB_RO, HUB_RI, HUB_L, at=(0, 0, AXIS_Z), axis='X', mat=cast)

# ---------------- 法兰：贴在轴承座 +X 端面上
flange_x = HUB_L / 2 + FLANGE_T / 2
flange = K.tube('flange', FLANGE_R, HUB_RI, FLANGE_T, at=(flange_x, 0, AXIS_Z), axis='X', mat=cast)

# ---------------- 台阶轴：profile = (半径, 轴向位置)，轴向位置以轴的中心为 0
shaft_profile = [
    (0, -45), (12, -45),        # 左端面
    (12, -25), (16, -25),       # 台阶：Φ24 → Φ32
    (16, 30), (10, 30),         # 穿过轴承座的那一段 Φ32，然后变细
    (10, 60), (0, 60),          # 右端 Φ20 输出段
]
shaft = K.revolve('shaft', shaft_profile, at=(0, 0, AXIS_Z), axis='X', mat=shaft_m)

# ---------------- 法兰螺钉：先做 1 颗（在法兰正上方），再绕 X 轴均布 6 颗
screw_x = HUB_L / 2 + FLANGE_T + SCREW_HEAD_H / 2           # 螺钉头贴在法兰外端面
head = K.cyl('screw', SCREW_HEAD_R, SCREW_HEAD_H, at=(screw_x, 0, AXIS_Z + SCREW_PCD), axis='X', mat=screw_m)
K.polar(head, 6, axis='X', center_pt=(0, 0, AXIS_Z), prefix='screw')

for o in (base, hub, flange, shaft):
    K.info(o)

# 轴的 Φ32 段 (半径 16) 和轴承座内孔 (半径 16.2) 之间留 0.2 mm 间隙，所以不会穿插。
# 轴承座外圆底部和底座上表面相切（接触），属于正常。
ALLOW_TOUCH = []
