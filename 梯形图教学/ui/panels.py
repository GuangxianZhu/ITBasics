"""指令表、监视表、控制按钮、输入按钮。只负责显示和转发事件。"""
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider, DirectLabel, DGG
from panda3d.core import TextNode

GREEN = (0.3, 1.0, 0.4, 1)
GRAY = (0.85, 0.85, 0.85, 1)


class TextTable:
    """文本表。DirectLabel 只在行数/列数变化时创建；每帧只改 text / text_fg。
    行数多时自动缩小行距和字号，保证不丢行。"""

    def __init__(self, parent, font, x, top, bottom, base_line_h, base_scale, width):
        self.parent, self.font = parent, font
        self.x, self.top, self.bottom = x, top, bottom
        self.base_line_h, self.base_scale, self.width = base_line_h, base_scale, width
        self._shape = None          # (n_rows, n_cols)
        self._bg, self._lbl = [], []
        self._cache = {}

    def _destroy(self):
        for w in self._bg:
            w.destroy()
        for row in self._lbl:
            for w in row:
                w.destroy()
        self._bg, self._lbl, self._cache = [], [], {}

    def _build(self, n, ncols, col_x):
        self._destroy()
        line_h = min(self.base_line_h, (self.top - self.bottom) / max(n, 1))
        scale = self.base_scale * line_h / self.base_line_h
        self.line_h = line_h
        for i in range(n):
            y = self.top - i * line_h
            self._bg.append(DirectFrame(parent=self.parent, frameColor=(0.8, 0.6, 0.1, 0.0),
                                        frameSize=(self.x - 0.01, self.x + self.width,
                                                   y - line_h * 0.3, y + line_h * 0.7)))
            row = []
            for j in range(ncols):
                row.append(DirectLabel(parent=self.parent, text="", text_font=self.font,
                                       text_scale=scale, text_align=TextNode.ALeft,
                                       text_fg=GRAY, frameColor=(0, 0, 0, 0),
                                       pos=(self.x + col_x[j], 0, y)))
            self._lbl.append(row)
        self._shape = (n, ncols)

    def set_rows(self, rows, col_x, highlight=None, on_col=None):
        n = len(rows)
        ncols = len(col_x)
        if self._shape != (n, ncols):
            self._build(n, ncols, col_x)
        for i in range(n):
            hl = bool(highlight) and i in highlight
            if self._cache.get(("bg", i)) != hl:
                self._bg[i]["frameColor"] = (0.8, 0.6, 0.1, 0.55 if hl else 0.0)
                self._cache[("bg", i)] = hl
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
                    self._lbl[i][j]["text_fg"] = GREEN if on else GRAY
                self._cache[(i, "on")] = on


def make_button(parent, font, text, pos, scale=0.045, size=(-3.2, 3.2, -0.9, 1.0), command=None):
    b = DirectButton(parent=parent, text=text, text_font=font, text_scale=1, scale=scale,
                     pos=pos, frameSize=size, frameColor=(0.25, 0.28, 0.35, 1),
                     text_fg=(1, 1, 1, 1), relief=DGG.FLAT, pressEffect=1)
    if command:
        b["command"] = command
    return b
