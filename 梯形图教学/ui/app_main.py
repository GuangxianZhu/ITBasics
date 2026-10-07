"""ShowBase 子类：组装一切。逻辑全在 app/ 里。"""
from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectSlider, DirectLabel, DirectFrame, DGG
from panda3d.core import TextNode, loadPrcFileData, MouseButton

from app.controller import Controller
from app.demos import DEMOS
from app.draw import draw_program
from app.scene_state import scene_state
from app.views import il_rows, monitor_rows
from ui.fonts import load_cjk_font
from ui.ladder_view import LadderView
from ui.panels import TextTable, make_button
from ui.tank_scene import TankScene

ASPECT = 1280 / 720
BTN_NORMAL = (0.25, 0.28, 0.35, 1)
BTN_SELECTED = (0.2, 0.5, 0.3, 1)


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
        W = ASPECT
        self._mouse_held = set()

        # 示例按钮（6 个，一行；当前项底色不同）
        DirectLabel(parent=self.a2d, text="示例:", text_font=self.font, text_scale=0.045,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(-W + 0.12, 0, 0.93))
        self.demo_btns = []
        for i, (name, _) in enumerate(DEMOS):
            b = make_button(self.a2d, self.font, name, (-W + 0.42 + i * 0.3, 0, 0.93),
                            scale=0.04, size=(-3.4, 3.4, -0.9, 1.0), command=self.pick_demo)
            b["extraArgs"] = [i]
            self.demo_btns.append(b)

        # 梯形图区
        self.ladder = LadderView(self.a2d, self.font, (-W + 0.1, 0.6, -0.1, 0.86))
        # 指令表 / 监视表（行多时自动缩小）
        self._title("指令表（命令リスト）", -W + 0.08, -0.12)
        self._title("监视（モニタ）", -0.9, -0.12)
        self.il_table = TextTable(self.a2d, self.font, -W + 0.08, -0.19, -0.84, 0.056, 0.042, 0.8)
        self.mon_table = TextTable(self.a2d, self.font, -0.9, -0.19, -0.84, 0.056, 0.04, 1.5)

        # 右侧：3D 水槽 + 文字 + 按钮
        self.tank_scene = TankScene(self, self.font)
        rx = 0.68
        self.level_lbl = DirectLabel(parent=self.a2d, text="", text_font=self.font, text_scale=0.05,
                                     text_fg=(0.6, 0.85, 1, 1), frameColor=(0, 0, 0, 0),
                                     pos=(rx, 0, -0.44), text_align=TextNode.ALeft)
        make_button(self.a2d, self.font, "重置水槽", (1.55, 0, -0.43), scale=0.04,
                    size=(-3.2, 3.2, -0.9, 1.0), command=lambda: self.ctrl.reset_tank())
        self.in_btns = {}
        for i, (addr, txt) in enumerate((("X0", "X0 启动"), ("X1", "X1 停止"))):
            b = make_button(self.a2d, self.font, txt, (0.95 + i * 0.5, 0, -0.6), scale=0.04,
                            size=(-5.5, 5.5, -1.2, 1.4))
            b.bind(DGG.B1PRESS, lambda e, a=addr: self.mouse_button(a, True))
            b.bind(DGG.B1RELEASE, lambda e, a=addr: self.mouse_button(a, False))
            self.in_btns[addr] = b

        # 控制栏
        y = -0.93
        make_button(self.a2d, self.font, "▶运行", (-W + 0.2, 0, y), command=lambda: self.ctrl.run())
        make_button(self.a2d, self.font, "暂停", (-W + 0.5, 0, y), command=lambda: self.ctrl.pause())
        make_button(self.a2d, self.font, "单步", (-W + 0.8, 0, y), command=self.on_step_one)
        make_button(self.a2d, self.font, "单轮", (-W + 1.1, 0, y), command=self.on_step_scan)
        DirectLabel(parent=self.a2d, text="慢放", text_font=self.font, text_scale=0.04,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(-0.3, 0, y - 0.01))
        self.slider = DirectSlider(parent=self.a2d, range=(0, 1), value=0, pageSize=0.1,
                                   pos=(0.12, 0, y), scale=0.3, command=self.on_slider)
        self.speed_lbl = DirectLabel(parent=self.a2d, text="0.00秒", text_font=self.font,
                                     text_scale=0.04, text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0),
                                     pos=(0.5, 0, y - 0.01), text_align=TextNode.ALeft)
        self.status = DirectLabel(parent=self.a2d, text="", text_font=self.font, text_scale=0.045,
                                  text_fg=(1, 0.9, 0.2, 1), frameColor=(0, 0, 0, 0),
                                  pos=(0.9, 0, y - 0.01), text_align=TextNode.ALeft)

        # 键盘
        self.accept("space", self.toggle_run)
        self.accept("arrow_right", self.on_step_one)
        self.accept("arrow_down", self.on_step_scan)
        for addr, key in (("X0", "0"), ("X1", "1")):
            self.accept(key, lambda a=addr: self.ctrl.set_button(a, True))
            self.accept(key + "-up", lambda a=addr: self.ctrl.set_button(a, False))
        self.accept("mouse1-up", self.release_mouse_buttons)

        self.taskMgr.add(self.tick, "tick")
        self.pick_demo(0)

    # ---------- 事件转发 ----------
    def _title(self, text, x, y):
        return DirectLabel(parent=self.a2d, text=text, text_font=self.font, text_scale=0.045,
                           text_fg=(0.6, 0.8, 1, 1), frameColor=(0, 0, 0, 0), pos=(x, 0, y),
                           text_align=TextNode.ALeft)

    def pick_demo(self, i):
        self.demo_index = i
        self.ctrl.load(DEMOS[i][1])
        for k, b in enumerate(self.demo_btns):
            b["frameColor"] = BTN_SELECTED if k == i else BTN_NORMAL

    def mouse_button(self, addr, pressed):
        if pressed:
            self._mouse_held.add(addr)
        else:
            self._mouse_held.discard(addr)
        self.ctrl.set_button(addr, pressed)

    def release_mouse_buttons(self):
        """全局鼠标松开：把拖出按钮后才松开的 X0/X1 也复位"""
        for a in list(self._mouse_held):
            self.mouse_button(a, False)

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
        # 保险：鼠标左键已经不在按下状态，但仍有按钮卡着 → 复位
        mw = self.mouseWatcherNode
        if self._mouse_held and mw is not None and not mw.isButtonDown(MouseButton.one()):
            self.release_mouse_buttons()
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
        st = scene_state(c)
        self.tank_scene.update(st)
        self.level_lbl["text"] = st["level_text"]
        mode = "运行" if c.mode == "run" else "暂停"
        self.status["text"] = f"[{mode}] 状态: {c.phase_text or '-'}   扫描次数: {c.plc.scan_count}"
