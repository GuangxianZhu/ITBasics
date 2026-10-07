"""通用小部件：面板卡片、竖向滚动条、分隔条。只显示和转发事件。

拖动统一由 app 的 Dragger 处理：部件在鼠标按下时调用 dragger.start(回调)，
之后每帧回调 (x, y)（aspect2d 坐标），直到鼠标松开。
"""
from direct.gui.DirectGui import DirectFrame, DirectLabel, DGG
from panda3d.core import TextNode, MouseButton

from ui import theme

HEADER_H = 0.065
SCROLL_W = 0.022


class Dragger:
    def __init__(self, base):
        self.base = base
        self.cb = None

    def aspect(self):
        return self.base.getAspectRatio()

    def mouse(self):
        mw = self.base.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return None
        return mw.getMouseX() * self.aspect(), mw.getMouseY()

    def start(self, cb):
        self.cb = cb
        p = self.mouse()
        if p:
            cb(*p, True)

    @property
    def active(self):
        return self.cb is not None

    def update(self):
        if self.cb is None:
            return
        mw = self.base.mouseWatcherNode
        if mw is None or not mw.isButtonDown(MouseButton.one()):
            self.cb = None
            return
        p = self.mouse()
        if p:
            self.cb(*p, False)


class Pane:
    """带标题栏的卡片。content_rect() 是标题栏下方可用区域。"""

    def __init__(self, parent, font, title):
        self.root = parent.attachNewNode("pane")
        self.bg = DirectFrame(parent=self.root, frameColor=theme.PANEL, frameSize=(0, 1, 0, 1))
        self.border = DirectFrame(parent=self.root, frameColor=theme.BORDER, frameSize=(0, 1, 0, 1))
        self.header = DirectFrame(parent=self.root, frameColor=theme.HEADER, frameSize=(0, 1, 0, 1))
        self.title = DirectLabel(parent=self.root, text=title, text_font=font, text_scale=0.038,
                                 text_fg=theme.TITLE, text_align=TextNode.ALeft, frameColor=(0, 0, 0, 0))
        self.border.setBin("background", 0)
        self.bg.setBin("background", 1)
        self.header.setBin("background", 2)
        self.rect = (0, 1, 0, 1)

    def set_rect(self, l, r, b, t):
        self.rect = (l, r, b, t)
        self.border["frameSize"] = (l - 0.003, r + 0.003, b - 0.003, t + 0.003)
        self.bg["frameSize"] = (l, r, b, t)
        self.header["frameSize"] = (l, r, t - HEADER_H, t)
        self.title.setPos(l + 0.025, 0, t - HEADER_H + 0.022)

    def content_rect(self, pad=0.02):
        l, r, b, t = self.rect
        return l + pad, r - pad, b + pad, t - HEADER_H - pad

    def header_y(self):
        """标题栏中线 y（放标题栏里的按钮用）"""
        return self.rect[3] - HEADER_H / 2


class VScroll:
    """竖向滚动条。value = 顶部看到的位置（0 ~ total-view），单位由使用者决定（行/格）。"""

    def __init__(self, parent, dragger, on_change):
        self.dragger, self.on_change = dragger, on_change
        self.track = DirectFrame(parent=parent, frameColor=theme.SCROLL_TRACK,
                                 frameSize=(0, 1, 0, 1), state=DGG.NORMAL)
        self.thumb = DirectFrame(parent=parent, frameColor=theme.SCROLL_THUMB,
                                 frameSize=(0, 1, 0, 1), state=DGG.NORMAL)
        self.thumb.bind(DGG.WITHIN, lambda e: self.thumb.__setitem__("frameColor", theme.ACCENT))
        self.thumb.bind(DGG.WITHOUT, lambda e: self.thumb.__setitem__("frameColor", theme.SCROLL_THUMB))
        self.thumb.bind(DGG.B1PRESS, self._grab)
        self.track.bind(DGG.B1PRESS, self._page)
        self.rect = (0, 1, 0, 1)
        self.total = self.view = 1.0
        self.value = 0.0
        self._key = None
        self.visible = False
        self.set_visible(False)

    def set_rect(self, x, b, t, w=SCROLL_W):
        self.rect = (x, x + w, b, t)
        self.track["frameSize"] = self.rect
        self._key = None

    def set_visible(self, v):
        self.visible = v
        for f in (self.track, self.thumb):
            f.show() if v else f.hide()

    def update(self, total, view, value):
        """内容总长 total、可见长度 view、当前位置 value"""
        self.total, self.view, self.value = total, view, value
        need = total > view + 1e-6
        if need != self.visible:
            self.set_visible(need)
        if not need:
            return
        key = (round(total, 3), round(view, 3), round(value, 3), self.rect)
        if key == self._key:
            return
        self._key = key
        l, r, b, t = self.rect
        h = t - b
        th = max(0.05, h * view / total)
        y_top = t - (h - th) * (value / max(1e-6, total - view))
        self.thumb["frameSize"] = (l + 0.003, r - 0.003, y_top - th, y_top)

    def _pos_to_value(self, y, grab_dy):
        l, r, b, t = self.rect
        h = t - b
        th = max(0.05, h * self.view / self.total)
        frac = (t - (y + grab_dy)) / max(1e-6, h - th)
        return max(0.0, min(self.total - self.view, frac * (self.total - self.view)))

    def _grab(self, _e):
        fs = self.thumb["frameSize"]
        p = self.dragger.mouse()
        if not p:
            return
        dy = fs[3] - p[1]
        self.dragger.start(lambda x, y, first: self.on_change(self._pos_to_value(y, dy)))

    def _page(self, _e):
        p = self.dragger.mouse()
        if not p:
            return
        fs = self.thumb["frameSize"]
        step = self.view * 0.9
        self.on_change(max(0.0, min(self.total - self.view,
                                    self.value + (step if p[1] < fs[2] else -step))))


class Splitter:
    """可拖动的分隔条。平时透明，鼠标移上去高亮。"""

    def __init__(self, parent, dragger, name, on_drag, vertical):
        self.frame = DirectFrame(parent=parent, frameColor=theme.SPLITTER,
                                 frameSize=(0, 1, 0, 1), state=DGG.NORMAL)
        self.frame.bind(DGG.WITHIN, lambda e: self._hover(True))
        self.frame.bind(DGG.WITHOUT, lambda e: self._hover(False))
        self.frame.bind(DGG.B1PRESS, lambda e: dragger.start(
            lambda x, y, first: on_drag(name, x, y)))
        self.dragger = dragger
        self.vertical = vertical
        self.grip = DirectFrame(parent=self.frame, frameColor=theme.BORDER, frameSize=(0, 1, 0, 1))

    def _hover(self, on):
        self.frame["frameColor"] = theme.SPLITTER_HOVER if on else theme.SPLITTER

    def set_rect(self, l, r, b, t):
        self.frame["frameSize"] = (l, r, b, t)
        cx, cy = (l + r) / 2, (b + t) / 2
        if self.vertical:
            self.grip["frameSize"] = (cx - 0.003, cx + 0.003, cy - 0.06, cy + 0.06)
        else:
            self.grip["frameSize"] = (cx - 0.06, cx + 0.06, cy - 0.003, cy + 0.003)
