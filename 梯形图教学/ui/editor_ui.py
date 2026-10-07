"""编辑器工具栏。只负责显示和转发事件，所有编辑规则在 app/editor.py。"""
from direct.gui.DirectGui import DirectEntry, DirectFrame, DirectLabel
from panda3d.core import TextNode

from ui.panels import make_button

ENTRY_OK = (0.2, 0.23, 0.3, 1)
ENTRY_BAD = (0.7, 0.15, 0.12, 1)


class EditorBar:
    """一行工具栏：左边随选中对象切换（触点工具 / 线圈工具），右边是行操作 + 撤销/重做"""

    def __init__(self, a2d, font, x0, y, h):
        """h: handler 对象，需提供 on_* 方法（见下）"""
        self.font, self.h = font, h
        self.root = a2d.attachNewNode("editor_bar")
        self.contact_bar = self.root.attachNewNode("contact_tools")
        self.coil_bar = self.root.attachNewNode("coil_tools")
        self.common_bar = self.root.attachNewNode("common_tools")
        self.entries = []
        sc = 0.034

        def place(parent, items, x):
            """items: [(text, cmd)]，按字数排开，返回终点 x"""
            btns = {}
            for text, cmd in items:
                half = (len(text) * 0.55 + 0.7) * sc
                b = make_button(parent, font, text, (x + half, 0, y), scale=sc,
                                size=(-(len(text) * 0.55 + 0.7), len(text) * 0.55 + 0.7, -0.9, 1.0),
                                command=cmd)
                btns[text] = b
                x += 2 * half + 0.012
            return x, btns

        def entry(parent, x, width_chars, initial, cmd):
            e = DirectEntry(parent=parent, text_font=font, scale=0.04, pos=(x, 0, y - 0.012),
                            width=width_chars, numLines=1, initialText=initial,
                            frameColor=ENTRY_OK, text_fg=(1, 1, 1, 1), command=cmd,
                            focusInCommand=None, relief=1)
            self.entries.append(e)
            return e

        # 触点工具
        x, self.cbtn = place(self.contact_bar, [
            ("右插触点", h.on_insert_right), ("左插触点", h.on_insert_left),
            ("加并联", h.on_parallel), ("删除", h.on_delete), ("a/b切换", h.on_toggle_nc)], x0)
        self._label(self.contact_bar, "地址:", x + 0.02, y, sc)
        self.addr_entry = entry(self.contact_bar, x + 0.12, 4, "X0", h.on_addr_enter)
        # 线圈工具
        x2, self.kbtn = place(self.coil_bar, [
            ("OUT", h.on_out), ("OUT T", h.on_out_t), ("OUT C", h.on_out_c), ("RST", h.on_rst)], x0)
        self._label(self.coil_bar, "地址:", x2 + 0.02, y, sc)
        self.coil_addr = entry(self.coil_bar, x2 + 0.12, 4, "Y0", h.on_coil_enter)
        self._label(self.coil_bar, "K:", x2 + 0.5, y, sc)
        self.coil_k = entry(self.coil_bar, x2 + 0.58, 4, "", h.on_coil_enter)
        self.left_w = max(x + 0.42, x2 + 0.8) - x0   # 左边（触点/线圈工具）占的宽度
        # 公共：行 / 撤销（右对齐，由 place_at 摆放）
        xc = 0.0
        self.common_w, self.mbtn = place(self.common_bar, [
            ("行+", h.on_add_rung), ("行−", h.on_del_rung), ("上移", h.on_move_up),
            ("下移", h.on_move_down), ("撤销", h.on_undo), ("重做", h.on_redo)], xc)
        self.set_mode(None)

    ROW_H = 0.07

    def place_at(self, l, y, r):
        """把工具栏放到 [l, r] 这一条（y = 第一行中线）。放不下一行就把右边的按钮挪到第二行。返回行数"""
        self.root.setPos(l, 0, y)
        if self.left_w + 0.04 + self.common_w <= r - l:
            self.common_bar.setPos(r - l - self.common_w, 0, 0)
            return 1
        self.common_bar.setPos(0, 0, -self.ROW_H)
        return 2

    def _label(self, parent, text, x, y, sc):
        return DirectLabel(parent=parent, text=text, text_font=self.font, text_scale=sc,
                           text_fg=(0.8, 0.85, 0.9, 1), frameColor=(0, 0, 0, 0),
                           pos=(x, 0, y - 0.012), text_align=TextNode.ALeft)

    def set_mode(self, kind):
        """kind: None / "contact" / "coil" —— 选了什么就显示哪套工具"""
        (self.contact_bar.show if kind != "coil" else self.contact_bar.hide)()
        (self.coil_bar.show if kind == "coil" else self.coil_bar.hide)()

    def set_visible(self, v):
        self.root.show() if v else self.root.hide()

    def typing(self):
        return any(e.guiItem.getFocus() for e in self.entries)

    def mark_bad(self, entry, bad=True):
        entry["frameColor"] = ENTRY_BAD if bad else ENTRY_OK

    def clear_marks(self):
        for e in self.entries:
            self.mark_bad(e, False)

    @staticmethod
    def get(entry):
        return entry.get()

    @staticmethod
    def put(entry, text):
        entry.enterText(text)

    def release_focus(self):
        for e in self.entries:
            e["focus"] = 0
