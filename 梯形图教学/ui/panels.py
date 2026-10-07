"""指令表、监视表、控制按钮、输入按钮。只负责显示和转发事件。"""
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider, DirectLabel, DGG
from panda3d.core import TextNode

from ui import theme

GREEN = (0.3, 1.0, 0.4, 1)
GRAY = (0.85, 0.85, 0.85, 1)


class TextTable:
    """文本表。DirectLabel 只在行数/列数变化时创建；每帧只改 text / text_fg。
    行数多时自动缩小行距和字号，保证不丢行。"""

    def __init__(self, parent, font, x, top, bottom, base_line_h, base_scale, width):
        self.parent, self.font = parent, font
        self.x, self.top, self.bottom = x, top, bottom
        self.base_line_h, self.base_scale, self.width = base_line_h, base_scale, width
        self._shape = None          # (可见行数, n_cols)
        self.min_line_h = 0.05      # 不再缩小字号，放不下就用滚动条
        self.offset = 0
        self.n_total = 0
        self._bg, self._lbl = [], []
        self._cache = {}

    def _destroy(self):
        for w in self._bg:
            w.destroy()
        for row in self._lbl:
            for w in row:
                w.destroy()
        self._bg, self._lbl, self._cache = [], [], {}

    def set_geometry(self, x, top, bottom, width):
        """面板大小变了：换位置，下次 set_rows 时重建"""
        self.x, self.top, self.bottom, self.width = x, top, bottom, width
        self._shape = None

    def scroll_metrics(self):
        n = self._shape[0] if self._shape else 0
        return self.n_total, n, self.offset

    def set_offset(self, v):
        self.offset = int(round(v))
        self._cache = {k: v for k, v in self._cache.items() if k[0] != "bg"}

    def contains(self, x, y):
        return self.x - 0.01 <= x <= self.x + self.width and self.bottom - 0.03 <= y <= self.top + 0.04

    def scroll_by(self, rows):
        self.offset = max(0, min(self.offset + rows, self.n_total - self._shape[0])) if self._shape else 0

    def _build(self, n, ncols, col_x):
        self._destroy()
        line_h = max(min(self.base_line_h, (self.top - self.bottom) / max(n, 1)), self.min_line_h)
        scale = self.base_scale * line_h / self.base_line_h
        self.line_h = line_h
        for i in range(n):
            y = self.top - i * line_h
            self._bg.append(DirectFrame(parent=self.parent, frameColor=(0, 0, 0, 0),
                                        frameSize=(self.x - 0.01, self.x + self.width,
                                                   y - line_h * 0.3, y + line_h * 0.7)))
            row = []
            for j in range(ncols):
                row.append(DirectLabel(parent=self.parent, text="", text_font=self.font,
                                       text_scale=scale, text_align=TextNode.ALeft,
                                       text_fg=theme.TEXT, frameColor=(0, 0, 0, 0),
                                       pos=(self.x + col_x[j], 0, y)))
            self._lbl.append(row)
        self._shape = (n, ncols)

    def set_rows(self, rows, col_x, highlight=None, on_col=None):
        ncols = len(col_x)
        self.n_total = len(rows)
        avail = self.top - self.bottom
        n = min(len(rows), max(1, int(avail / self.min_line_h) + 1))
        if self._shape != (n, ncols):
            self._build(n, ncols, col_x)
        # 窗口滚动：保证高亮行可见
        self.offset = max(0, min(self.offset, len(rows) - n))
        if highlight:
            lo, hi = min(highlight), max(highlight)
            if lo < self.offset:
                self.offset = lo
            elif hi >= self.offset + n:
                self.offset = hi - n + 1
        off = self.offset
        rows = rows[off:off + n]
        highlight = {h - off for h in highlight} if highlight else None
        on_col = on_col[off:off + n] if on_col else None
        for i in range(n):
            hl = bool(highlight) and i in highlight
            state = (hl, (i + off) % 2)
            if self._cache.get(("bg", i)) != state:
                self._bg[i]["frameColor"] = theme.ROW_HL if hl else (theme.ROW_ZEBRA if state[1] else (0, 0, 0, 0))
                self._cache[("bg", i)] = state
            on = bool(on_col[i]) if on_col else False
            for j in range(ncols):
                txt = str(rows[i][j])
                if self._cache.get((i, j, "t")) != txt:
                    self._lbl[i][j]["text"] = txt
                    self._cache[(i, j, "t")] = txt
                if self._cache.get((i, "on")) != on:
                    pass
            if self._cache.get((i, "on")) != on:
                for j in range(ncols):
                    self._lbl[i][j]["text_fg"] = theme.OK if on else theme.TEXT
                self._cache[(i, "on")] = on


def make_button(parent, font, text, pos, scale=0.045, size=(-3.2, 3.2, -0.9, 1.0), command=None):
    b = DirectButton(parent=parent, text=text, text_font=font, text_scale=1, scale=scale,
                     pos=pos, frameSize=size, frameColor=theme.BTN,
                     text_fg=theme.TEXT, relief=DGG.FLAT, pressEffect=0)
    if command:
        b["command"] = command
    return b
