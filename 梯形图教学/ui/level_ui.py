"""关卡相关界面：关卡选择、说明弹窗、结果弹窗、顶部关卡栏。只显示和转发事件。"""
from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import TextNode

from ui.panels import make_button

PANEL = (0.16, 0.18, 0.22, 0.97)
TITLE_FG = (0.6, 0.85, 1, 1)
TEXT_FG = (0.92, 0.92, 0.92, 1)
OK_FG = (0.4, 1, 0.5, 1)
NG_FG = (1, 0.5, 0.4, 1)
BTN_PASSED = (0.2, 0.45, 0.28, 1)
BTN_NORMAL = (0.25, 0.28, 0.35, 1)


def _label(parent, font, text, pos, scale, fg=TEXT_FG, align=TextNode.ALeft, wrap=None):
    kw = dict(text_wordwrap=wrap) if wrap else {}
    return DirectLabel(parent=parent, text=text, text_font=font, text_scale=scale,
                       text_fg=fg, text_align=align, frameColor=(0, 0, 0, 0), pos=pos, **kw)


class Modal:
    """全屏半透明遮罩 + 中间面板。挡住后面的点击。"""

    def __init__(self, a2d, w, h):
        self.root = DirectFrame(parent=a2d, frameColor=(0, 0, 0, 0.55),
                                frameSize=(-2, 2, -1, 1), state="normal", sortOrder=50)
        self.panel = DirectFrame(parent=self.root, frameColor=PANEL, frameSize=(-w, w, -h, h))
        self.root.setBin("gui-popup", 0)          # 永远画在梯形图等每帧新建的节点之上
        self.root.hide()

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def clear(self):
        for c in self.panel.getChildren():
            c.removeNode()


class LevelSelect(Modal):
    def __init__(self, a2d, font, levels, on_pick, on_free, on_sandbox=None):
        super().__init__(a2d, 1.1, 0.75)
        self.font, self.levels, self.on_pick, self.on_free = font, levels, on_pick, on_free
        self.on_sandbox = on_sandbox

    def open(self, passed):
        self.clear()
        _label(self.panel, self.font, "选择关卡（ステージ選択）", (0, 0, 0.6), 0.065, TITLE_FG, TextNode.ACenter)
        for i, lv in enumerate(self.levels):
            col, row = i % 2, i // 2
            done = lv.ID in passed
            text = lv.TITLE + ("（已通过）" if done else "")
            b = make_button(self.panel, self.font, text, (-0.52 + col * 1.04, 0, 0.38 - row * 0.2),
                            scale=0.045, size=(-10.5, 10.5, -1.4, 1.7), command=self._pick)
            b["extraArgs"] = [i]
            b["frameColor"] = BTN_PASSED if done else BTN_NORMAL
        make_button(self.panel, self.font, "自由示例（不判定）", (-0.72, 0, -0.62), scale=0.045,
                    size=(-6, 6, -1.0, 1.3), command=self._free)
        make_button(self.panel, self.font, "空白沙盒", (-0.1, 0, -0.62), scale=0.045,
                    size=(-4, 4, -1.0, 1.3), command=self._sandbox)
        make_button(self.panel, self.font, "关闭", (0.55, 0, -0.62), scale=0.045,
                    size=(-3, 3, -1.0, 1.3), command=self.hide)
        _label(self.panel, self.font, f"已通过 {len(passed)}/{len(self.levels)}",
               (1.0, 0, -0.64), 0.04, TEXT_FG, TextNode.ARight)
        self.show()

    def _pick(self, i):
        self.hide()
        self.on_pick(i)

    def _free(self):
        self.hide()
        self.on_free()

    def _sandbox(self):
        self.hide()
        if self.on_sandbox:
            self.on_sandbox()


class InfoPopup(Modal):
    """关卡说明（+任务 / 选择题），以及判定结果。"""

    def __init__(self, a2d, font):
        super().__init__(a2d, 1.15, 0.82)
        self.font = font

    def open_intro(self, lv, on_answer=None, result=None):
        self.clear()
        p, f = self.panel, self.font
        _label(p, f, lv.TITLE, (-1.07, 0, 0.7), 0.062, TITLE_FG)
        _label(p, f, lv.INTRO, (-1.07, 0, 0.56), 0.042, TEXT_FG, wrap=50)
        if lv.KIND == "task":
            _label(p, f, "任务：" + lv.TASK, (-1.07, 0, -0.5), 0.045, (1, 0.9, 0.3, 1), wrap=47)
            make_button(p, f, "开始", (0.9, 0, -0.72), scale=0.05, size=(-3, 3, -0.9, 1.2), command=self.hide)
        else:
            _label(p, f, "问题：" + lv.QUESTION, (-1.07, 0, -0.26), 0.045, (1, 0.9, 0.3, 1), wrap=47)
            for i, c in enumerate(lv.CHOICES):
                b = make_button(p, f, f"{'ABCD'[i]}. {c}", (-0.35, 0, -0.38 - i * 0.1), scale=0.038,
                                size=(-18.5, 18.5, -0.9, 1.2), command=on_answer)
                b["text_align"] = TextNode.ALeft
                b["text_pos"] = (-18, 0)
                b["extraArgs"] = [i]
            if result is not None:
                ok, msg = result
                _label(p, f, msg, (-1.07, 0, -0.8), 0.04, OK_FG if ok else NG_FG, wrap=42)
            make_button(p, f, "先去试试", (0.9, 0, -0.72), scale=0.045, size=(-3.5, 3.5, -0.9, 1.2),
                        command=self.hide)
        self.show()

    def open_result(self, ok, msg, on_next=None):
        self.clear()
        p, f = self.panel, self.font
        self.panel["frameSize"] = (-0.8, 0.8, -0.35, 0.35)
        _label(p, f, "通过！" if ok else "还差一点", (0, 0, 0.18), 0.075, OK_FG if ok else NG_FG, TextNode.ACenter)
        if not ok:
            _label(p, f, msg, (0, 0, 0.02), 0.045, TEXT_FG, TextNode.ACenter, wrap=32)
        make_button(p, f, "确定", (-0.3 if (ok and on_next) else 0, 0, -0.22), scale=0.05,
                    size=(-3, 3, -0.9, 1.2), command=self._close_result)
        if ok and on_next:
            make_button(p, f, "下一关 ▶", (0.3, 0, -0.22), scale=0.05, size=(-3.5, 3.5, -0.9, 1.2),
                        command=lambda: (self._close_result(), on_next()))
        self.show()

    def _close_result(self):
        self.panel["frameSize"] = (-1.15, 1.15, -0.82, 0.82)
        self.hide()


class LevelBar:
    """关卡模式下的顶部栏：标题 + 说明 / 恢复示例 / 参考答案 / 判定"""

    def __init__(self, a2d, font, x0, y, on_intro, on_restore, on_solution, on_judge):
        self.root = a2d.attachNewNode("level_bar")
        self.title = _label(self.root, font, "", (x0, 0, y - 0.015), 0.048, TITLE_FG)
        self.btns = {}
        specs = [("说明", on_intro), ("恢复示例", on_restore), ("参考答案", on_solution), ("判定", on_judge)]
        for i, (txt, cmd) in enumerate(specs):
            self.btns[txt] = make_button(self.root, font, txt, (x0 + 1.02 + i * 0.29, 0, y),
                                         scale=0.04, size=(-3.2, 3.2, -0.9, 1.0), command=cmd)
        self.btns["判定"]["frameColor"] = (0.55, 0.4, 0.1, 1)
        self.root.hide()

    def show_level(self, lv):
        self.title["text"] = lv.TITLE
        quiz = lv.KIND == "quiz"
        for k in ("恢复示例", "参考答案"):
            self.btns[k].show() if not quiz else self.btns[k].hide()
        self.btns["判定"]["text"] = "答题" if quiz else "判定"
        self.root.show()

    def hide(self):
        self.root.hide()
