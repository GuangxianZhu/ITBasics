"""把 app.draw.Drawing 画到屏幕区域。不做任何逻辑判断。"""
from panda3d.core import LineSegs, TextNode, NodePath

COLORS = {
    "power": (0.2, 1.0, 0.3, 1), "on": (0.2, 1.0, 0.3, 1),
    "idle": (0.5, 0.5, 0.5, 1), "off": (0.5, 0.5, 0.5, 1),
    "rail": (1, 1, 1, 1), "text": (0.9, 0.9, 0.9, 1), "marker": (1, 0.9, 0.1, 1),
}


class LadderView:
    def __init__(self, parent, font, region):
        """region = (left, right, bottom, top)，aspect2d 坐标"""
        self.root = parent.attachNewNode("ladder_view")
        self.font = font
        self.region = region
        self.max_scale = 0.34
        self.min_scale = 0.11       # 再小就看不清了；放不下时改为纵向滚动
        self.scroll = 0.0           # 滚动量（格）
        self._view_rows = None      # 当前缩放下可见多少格
        self._content_rows = 0
        self._node = None
        l, r, b, t = region
        self.root.setScissor((l - 0.3, 0, b), (r + 0.1, 0, t + 0.12))

    def contains(self, x, y):
        l, r, b, t = self.region
        return l <= x <= r and b <= y <= t

    def screen_to_grid(self, x, y):
        """aspect2d 坐标 → 网格坐标（最近一次 redraw 的变换）。还没画过返回 None"""
        xf = getattr(self, "_xf", None)
        if xf is None:
            return None
        ox, oy, s, sc = xf
        return (x - ox) / s, (oy - y) / s + sc

    def scroll_by(self, rows):
        if self._view_rows is None:
            return
        self.scroll = max(0.0, min(self.scroll + rows, max(0.0, self._content_rows - self._view_rows)))

    def follow(self, y_top, y_bottom):
        """让 [y_top, y_bottom]（格）这段可见"""
        if self._view_rows is None:
            return
        if y_top < self.scroll:
            self.scroll = max(0.0, y_top - 0.5)
        elif y_bottom > self.scroll + self._view_rows:
            self.scroll = y_bottom - self._view_rows + 0.5

    def redraw(self, drawing):
        if self._node is not None:
            self._node.removeNode()
        self._node = self.root.attachNewNode("ladder")
        l, r, b, t = self.region
        gw, gh = drawing.width + 1.2, max(drawing.height, 1)
        s = min((r - l) / gw, (t - b) / gh)
        s = min(s, self.max_scale)
        fits = s >= self.min_scale
        if not fits:
            s = min((r - l) / gw, self.min_scale)
            self._view_rows = (t - b - 0.02) / s
            self._content_rows = drawing.height
            self.scroll = min(self.scroll, max(0.0, self._content_rows - self._view_rows))
        else:
            self._view_rows = None
            self.scroll = 0.0
        ox = l + ((r - l) - drawing.width * s) / 2 + 0.3 * s
        oy = t - ((t - b) - drawing.height * s) / 2 if drawing.height * s < (t - b) else t
        # 靠上对齐更好看
        oy = t - 0.02
        px = lambda x: ox + x * s
        sc = self.scroll
        self._xf = (ox, oy, s, sc)
        py = lambda y: oy - (y - sc) * s
        by_color = {}
        for e in drawing.elems:
            if e.kind in ("line", "rect"):
                by_color.setdefault(e.color, []).append(e)
            else:
                tn = TextNode("t")
                tn.setFont(self.font)
                tn.setText(e.text)
                tn.setAlign(TextNode.ACenter)
                tn.setTextColor(*COLORS[e.color])
                np_ = self._node.attachNewNode(tn)
                np_.setScale(s * 0.26 if e.tag[0] != "marker" else s * 0.45)
                np_.setPos(px(e.x1), 0, py(e.y1) - s * 0.23)
        for color, es in by_color.items():
            ls = LineSegs()
            ls.setThickness(3)
            ls.setColor(*COLORS[color])
            for e in es:
                if e.kind == "line":
                    ls.moveTo(px(e.x1), 0, py(e.y1))
                    ls.drawTo(px(e.x2), 0, py(e.y2))
                else:
                    pts = [(e.x1, e.y1), (e.x2, e.y1), (e.x2, e.y2), (e.x1, e.y2), (e.x1, e.y1)]
                    ls.moveTo(px(pts[0][0]), 0, py(pts[0][1]))
                    for x, y in pts[1:]:
                        ls.drawTo(px(x), 0, py(y))
            self._node.attachNewNode(ls.create())
