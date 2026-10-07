"""界面分区计算（纯函数，不依赖 panda3d）。坐标 = aspect2d：x ∈ [-aspect, aspect]，y ∈ [-1, 1]。

  ┌──────────────── top ────────────────┐
  │ ladder               │              │
  │                      │    tank      │
  ├──────── split_y ─────┤              │
  │ il      │ mon        │              │
  └─────────┴────────────┴──────────────┘
  │──────────────── bottom ─────────────│
"""
TOP_H = 0.12
BOT_H = 0.12
M = 0.02            # 外边距
GAP = 0.025         # 面板间距（也是分隔条宽度）
MIN_W = 0.45        # 面板最小宽
MIN_H = 0.3         # 面板最小高


class Layout:
    def __init__(self, fx=0.64, fy=0.55, ft=0.4):
        self.fx = fx    # 左区占中间区宽度的比例
        self.fy = fy    # 梯形图占左区高度的比例
        self.ft = ft    # 指令表占下方表格区宽度的比例

    def rects(self, aspect):
        a = aspect
        L, R = -a + M, a - M
        T, B = 1 - TOP_H - M, -1 + BOT_H + M
        W, H = R - L, T - B
        fx = _clamp(self.fx, (MIN_W + GAP / 2) / W, 1 - (MIN_W + GAP / 2) / W)
        xs = L + fx * W
        fy = _clamp(self.fy, (MIN_H + GAP / 2) / H, 1 - (MIN_H + GAP / 2) / H)
        ys = T - fy * H
        lw = xs - GAP / 2 - L
        ft = _clamp(self.ft, (MIN_W * 0.6 + GAP / 2) / lw, 1 - (MIN_W * 0.6 + GAP / 2) / lw)
        xt = L + ft * lw
        g = GAP / 2
        return {
            "top": (-a, a, 1 - TOP_H, 1),
            "bottom": (-a, a, -1, -1 + BOT_H),
            "ladder": (L, xs - g, ys + g, T),
            "il": (L, xt - g, B, ys - g),
            "mon": (xt + g, xs - g, B, ys - g),
            "tank": (xs + g, R, B, T),
            "split_x": (xs - g, xs + g, B, T),
            "split_y": (L, xs - g, ys - g, ys + g),
            "split_t": (xt - g, xt + g, B, ys - g),
        }

    def drag(self, name, x, y, aspect):
        """拖动分隔条到 (x, y)（aspect2d 坐标），更新比例"""
        a = aspect
        L, R = -a + M, a - M
        T, B = 1 - TOP_H - M, -1 + BOT_H + M
        if name == "split_x":
            self.fx = _clamp((x - L) / (R - L), 0.05, 0.95)
        elif name == "split_y":
            self.fy = _clamp((T - y) / (T - B), 0.05, 0.95)
        elif name == "split_t":
            xs = L + self.fx * (R - L)
            self.ft = _clamp((x - L) / (xs - GAP / 2 - L), 0.05, 0.95)


def _clamp(v, lo, hi):
    if lo > hi:
        return (lo + hi) / 2
    return max(lo, min(hi, v))
