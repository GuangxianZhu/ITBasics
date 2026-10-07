"""ShowBase 子类：组装一切。逻辑全在 app/ 里。"""
from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectSlider, DirectLabel, DirectFrame, DGG
from panda3d.core import TextNode, loadPrcFileData

from app.controller import Controller
from app.demos import DEMOS
from app.draw import draw_program
from app.views import il_rows, monitor_rows
from ui.fonts import load_cjk_font
from ui.ladder_view import LadderView
from ui.panels import TextTable, make_button, GREEN

ASPECT = 1280 / 720


class PlcApp(ShowBase):
    def __init__(self):
        loadPrcFileData("", "window-title PLC 梯形图教学\nwin-size 1280 720")
        ShowBase.__init__(self)
        self.disableMouse()
        self.setBackgroundColor(0.13, 0.14, 0.16)
        self.win.setClearColor((0.13, 0.14, 0.16, 1))
        self.win.setClearColorActive(True)
        DirectFrame(parent=self.render2d, frameColor=(0.13, 0.14, 0.16, 1),
                    frameSize=(-1, 1, -1, 1), sortOrder=-100)
        self.font = load_cjk_font(self.loader)
        self.ctrl = Controller(DEMOS[0][1])
        self.demo_index = 0
        self.a2d = self.aspect2d
        W = ASPECT   # aspect2d 横向 [-W, W]，纵向 [-1, 1]

        # 示例按钮
        DirectLabel(parent=self.a2d, text="示例:", text_font=self.font, text_scale=0.045,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(-W + 0.12, 0, 0.93))
        self.demo_btns = []
        for i, (name, _) in enumerate(DEMOS):
            b = make_button(self.a2d, self.font, name, (-W + 0.38 + i * 0.3, 0, 0.93),
                            size=(-3.2, 3.2, -0.9, 1.0), command=self.pick_demo, )
            b["extraArgs"] = [i]
            self.demo_btns.append(b)

        # 梯形图区
        self.ladder = LadderView(self.a2d, self.font, (-W + 0.1, 0.62, -0.05, 0.86))
        # 指令表 / 监视表
        self.il_title = self._title("指令表（命令リスト）", -W + 0.08, -0.12)
        self.mon_title = self._title("监视（モニタ）", -0.05, -0.12)
        self.il_table = TextTable(self.a2d, self.font, -W + 0.08, -0.19, 0.056, 12, 0.042, 0.75)
        self.mon_table = TextTable(self.a2d, self.font, -0.05, -0.19, 0.056, 12, 0.04, 1.05)

        # 右侧：输入
        rx = 0.85
        self._title("输入（入力）", rx, 0.85)
        self.in_btns = {}
        specs = [("X0", "X0 启动（按住=ON）", True), ("X1", "X1 停止（按住=ON）", True),
                 ("X2", "X2 下限（点=切换）", False), ("X3", "X3 上限（点=切换）", False)]
        for i, (addr, txt, momentary) in enumerate(specs):
            b = make_button(self.a2d, self.font, txt, (rx + 0.43, 0, 0.74 - i * 0.12),
                            scale=0.04, size=(-10.5, 10.5, -1.2, 1.4))
            if momentary:
                b.bind(DGG.B1PRESS, lambda e, a=addr: self.ctrl.set_button(a, True))
                b.bind(DGG.B1RELEASE, lambda e, a=addr: self.ctrl.set_button(a, False))
            else:
                b["command"] = self.toggle
                b["extraArgs"] = [addr]
            self.in_btns[addr] = b
        self.toggles = {"X2": False, "X3": False}

        # 控制栏
        y = -0.93
        make_button(self.a2d, self.font, "▶运行", (-W + 0.2, 0, y), command=self.ctrl.run)
        make_button(self.a2d, self.font, "暂停", (-W + 0.5, 0, y), command=self.ctrl.pause)
        make_button(self.a2d, self.font, "单步", (-W + 0.8, 0, y), command=self.on_step_one)
        make_button(self.a2d, self.font, "单轮", (-W + 1.1, 0, y), command=self.on_step_scan)
        DirectLabel(parent=self.a2d, text="慢放", text_font=self.font, text_scale=0.04,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(-0.5, 0, y - 0.01))
        self.slider = DirectSlider(parent=self.a2d, range=(0, 1), value=0, pageSize=0.1,
                                   pos=(0.05, 0, y), scale=0.3, command=self.on_slider)
        self.speed_lbl = DirectLabel(parent=self.a2d, text="0.00秒", text_font=self.font,
                                     text_scale=0.04, text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0),
                                     pos=(0.4, 0, y - 0.01), text_align=TextNode.ALeft)
        self.status = DirectLabel(parent=self.a2d, text="", text_font=self.font, text_scale=0.045,
                                  text_fg=(1, 0.9, 0.2, 1), frameColor=(0, 0, 0, 0),
                                  pos=(0.8, 0, y - 0.01), text_align=TextNode.ALeft)

        # 键盘
        self.accept("space", self.toggle_run)
        self.accept("arrow_right", self.on_step_one)
        self.accept("arrow_down", self.on_step_scan)
        for addr, key in (("X0", "0"), ("X1", "1")):
            self.accept(key, self.ctrl.set_button, [addr, True])
            self.accept(key + "-up", self.ctrl.set_button, [addr, False])

        self.taskMgr.add(self.tick, "tick")

    # ---------- 事件转发 ----------
    def _title(self, text, x, y):
        return DirectLabel(parent=self.a2d, text=text, text_font=self.font, text_scale=0.045,
                           text_fg=(0.6, 0.8, 1, 1), frameColor=(0, 0, 0, 0), pos=(x, 0, y),
                           text_align=TextNode.ALeft)

    def pick_demo(self, i):
        self.demo_index = i
        self.ctrl.load(DEMOS[i][1])

    def toggle(self, addr):
        self.toggles[addr] = not self.toggles[addr]
        self.ctrl.set_button(addr, self.toggles[addr])

    def toggle_run(self):
        self.ctrl.pause() if self.ctrl.mode == "run" else self.ctrl.run()

    def on_step_one(self):
        self.ctrl.pause()
        self.ctrl.step_one()

    def on_step_scan(self):
        self.ctrl.pause()
        self.ctrl.step_scan()

    def on_slider(self):
        v = round(self.slider["value"] * 20) / 20
        self.ctrl.speed = v
        self.speed_lbl["text"] = f"{v:.2f}秒"

    # ---------- 每帧 ----------
    def tick(self, task):
        self.ctrl.update(globalClock.getDt())
        self.refresh()
        return task.cont

    def refresh(self):
        c = self.ctrl
        self.ladder.redraw(draw_program(c.program, c.plc, c.current_rung))
        il = il_rows(c.program)
        hl = {i for i, (r, _) in enumerate(il) if r is not None and r == c.current_rung}
        self.il_table.set_rows([("" if r is None else str(r + 1), t) for r, t in il],
                               [0, 0.1], highlight=hl)
        mon = monitor_rows(c.program, c.plc)
        self.mon_table.set_rows([(a, n, v) for a, n, v, _ in mon], [0, 0.12, 0.8],
                                on_col=[m[3] for m in mon])
        mode = "运行" if c.mode == "run" else "暂停"
        self.status["text"] = f"[{mode}] 状态: {c.phase_text or '-'}   扫描次数: {c.plc.scan_count}"
