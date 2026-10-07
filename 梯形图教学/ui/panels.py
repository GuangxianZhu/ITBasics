"""指令表、监视表、控制按钮、输入按钮。只负责显示和转发事件。"""
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider, DirectLabel, DGG
from panda3d.core import TextNode

GREEN = (0.3, 1.0, 0.4, 1)
GRAY = (0.85, 0.85, 0.85, 1)


class TextTable:
    """固定行数的文本表；每帧 set_rows 更新，不新建节点"""
    def __init__(self, parent, font, x, top, line_h, n, scale, width):
        self.rows = []
        self.bg = []
        self.line_h = line_h
        self.n = n
        self.width = width
        self.x = x
        self.top = top
        for i in range(n):
            y = top - i * line_h
            bg = DirectFrame(parent=parent, frameColor=(1, 0.8, 0.1, 0.0),
                             frameSize=(x - 0.01, x + width, y - line_h * 0.3, y + line_h * 0.7))
            cols = []
            self.bg.append(bg)
            self.rows.append(cols)
        self.font, self.scale, self.parent = font, scale, parent
        self._texts = [[] for _ in range(n)]

    def set_rows(self, rows, col_x, highlight=None, on_col=None):
        """rows: list of tuples of str；highlight: set of row index；on_col: [bool]"""
        for i in range(self.n):
            for t in self._texts[i]:
                t.destroy()
            self._texts[i] = []
            hl = highlight is not None and i in highlight
            self.bg[i]["frameColor"] = (0.8, 0.6, 0.1, 0.55 if hl else 0.0)
            if i >= len(rows):
                continue
            y = self.top - i * self.line_h
            on = on_col[i] if on_col else False
            for j, txt in enumerate(rows[i]):
                lbl = DirectLabel(parent=self.parent, text=str(txt), text_font=self.font,
                                  text_scale=self.scale, text_align=TextNode.ALeft,
                                  text_fg=GREEN if on else GRAY, frameColor=(0, 0, 0, 0),
                                  pos=(self.x + col_x[j], 0, y))
                self._texts[i].append(lbl)


def make_button(parent, font, text, pos, scale=0.045, size=(-3.2, 3.2, -0.9, 1.0), command=None):
    b = DirectButton(parent=parent, text=text, text_font=font, text_scale=1, scale=scale,
                     pos=pos, frameSize=size, frameColor=(0.25, 0.28, 0.35, 1),
                     text_fg=(1, 1, 1, 1), relief=DGG.FLAT, pressEffect=1)
    if command:
        b["command"] = command
    return b
