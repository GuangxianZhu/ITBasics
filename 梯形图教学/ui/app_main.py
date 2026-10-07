"""ShowBase 子类：组装一切。逻辑全在 app/ 里。"""
from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectSlider, DirectLabel, DirectFrame, DGG
import copy

from panda3d.core import TextNode, loadPrcFileData, MouseButton, KeyboardButton

from app.controller import Controller
from app.demos import DEMOS
from app.draw import draw_program
from app.scene_state import scene_state
from app.views import il_rows, monitor_rows
from app.level_session import LevelSession
from app import editor as ed
from app.editor import EditError, History
from app.pick import hit_test, selection_elems
from plc.model import Contact, Out, OutT, OutC, Rst, Rung, Program
from ui.fonts import load_cjk_font
from ui.ladder_view import LadderView
from ui.panels import TextTable, make_button
from ui.tank_scene import TankScene
from ui.level_ui import LevelSelect, InfoPopup, LevelBar
from ui.editor_ui import EditorBar

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
        self.history = History(self.ctrl.program)
        self.sandbox = False
        self.sel = None            # ("contact", r, k) / ("coil", r) / None
        self.sel2 = None           # 跨选的终点触点下标
        self.msg, self.msg_t = "", 0.0
        self._drawing = None
        self._shown_sel = "init"
        self.a2d = self.aspect2d
        W = ASPECT
        self._mouse_held = set()

        # 示例按钮（6 个，一行；当前项底色不同）
        make_button(self.a2d, self.font, "关卡", (-W + 0.12, 0, 0.93), scale=0.04,
                    size=(-2, 2, -0.9, 1.0), command=self.open_levels)
        self.demo_bar = self.a2d.attachNewNode("demo_bar")
        self.demo_btns = []
        for i, (name, _) in enumerate(DEMOS):
            b = make_button(self.demo_bar, self.font, name, (-W + 0.42 + i * 0.3, 0, 0.93),
                            scale=0.04, size=(-3.4, 3.4, -0.9, 1.0), command=self.pick_demo)
            b["extraArgs"] = [i]
            self.demo_btns.append(b)

        # 梯形图区
        self.ladder = LadderView(self.a2d, self.font, (-W + 0.1, 0.6, -0.04, 0.78))
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
        self.accept("space", self._guard, [self.toggle_run])
        self.accept("arrow_right", self._guard, [self.on_step_one])
        self.accept("arrow_down", self._guard, [self.on_step_scan])
        for addr, key in (("X0", "0"), ("X1", "1")):
            self.accept(key, self._guard, [self.ctrl_button, addr, True])
            self.accept(key + "-up", self.ctrl_button, [addr, False])
        self.accept("delete", self._guard, [self.on_delete_key])
        self.accept("control-z", self._guard, [self.on_undo])
        self.accept("control-y", self._guard, [self.on_redo])
        self.accept("mouse1", self.on_click)
        self.accept("mouse1-up", self.release_mouse_buttons)
        self.accept("wheel_up", self.on_wheel, [-1])
        self.accept("wheel_down", self.on_wheel, [1])

        # 关卡
        self.session = LevelSession()
        self.level_bar = LevelBar(self.a2d, self.font, -W + 0.3, 0.93, self.show_intro,
                                  self.restore_example, self.load_solution, self.judge)
        self.level_select = LevelSelect(self.a2d, self.font, self.session.levels,
                                        self.enter_level, self.leave_level, self.enter_sandbox)
        # 编辑器工具栏（梯形图区上方一行）
        self.editor_bar = EditorBar(self.a2d, self.font, -W + 0.06, 0.835, self)
        self.popup = InfoPopup(self.a2d, self.font)
        self.taskMgr.add(self.tick, "tick")
        self.pick_demo(0)
        self.open_levels()

    # ---------- 事件转发 ----------
    def _title(self, text, x, y):
        return DirectLabel(parent=self.a2d, text=text, text_font=self.font, text_scale=0.045,
                           text_fg=(0.6, 0.8, 1, 1), frameColor=(0, 0, 0, 0), pos=(x, 0, y),
                           text_align=TextNode.ALeft)

    def _set_program(self, prog):
        """换一个"当前程序"：新建 History，清空选中，载入 PLC"""
        self.history = History(prog)
        self.sel = self.sel2 = None
        self.ctrl.load(prog)

    def pick_demo(self, i):
        self.demo_index = i
        self.sandbox = False
        self._set_program(copy.deepcopy(DEMOS[i][1]))          # 自由示例改的是副本
        for k, b in enumerate(self.demo_btns):
            b["frameColor"] = BTN_SELECTED if k == i else BTN_NORMAL

    def enter_sandbox(self):
        self.session.leave()
        self.level_bar.hide()
        self.demo_bar.show()
        self.sandbox = True
        for b in self.demo_btns:
            b["frameColor"] = BTN_NORMAL
        self._set_program(Program([Rung(Contact("X0"), Out("Y0"))]))

    # ---------- 关卡 ----------
    def open_levels(self):
        self.level_select.open(self.session.passed)

    def enter_level(self, i):
        self.sandbox = False
        self._set_program(self.session.enter(i))
        self.demo_bar.hide()
        self.level_bar.show_level(self.session.level)
        self.show_intro()

    def leave_level(self):
        self.session.leave()
        self.level_bar.hide()
        self.demo_bar.show()
        self.pick_demo(self.demo_index)

    def show_intro(self, result=None):
        self.popup.open_intro(self.session.level, on_answer=self.answer, result=result)

    def restore_example(self):
        self.do(ed.replace_program, self.session.level.EXAMPLE)    # 进 History，能撤销
        self.sel = self.sel2 = None

    def load_solution(self):
        self.do(ed.replace_program, self.session.level.SOLUTION)
        self.sel = self.sel2 = None

    def judge(self):
        if self.session.level.KIND == "quiz":
            self.show_intro(self.session.last_result)
            return
        ok, msg = self.session.judge()
        self.popup.open_result(ok, msg, self.next_level if self.session.has_next() else None)

    def answer(self, choice):
        self.session.answer(choice)
        self.show_intro(self.session.last_result)

    def next_level(self):
        self.enter_level(self.session.index + 1)

    # ---------- 编辑 ----------
    @property
    def editable(self):
        lv = self.session.level
        return not (lv is not None and lv.KIND == "quiz")

    def say(self, text):
        self.msg, self.msg_t = text, 6.0

    def do(self, op, *args, **kw):
        """执行一个编辑操作（进 History）。成功后重新载入 PLC；失败显示消息。"""
        try:
            self.history.apply(op, *args, **kw)
        except EditError as e:
            self.say(str(e))
            return False
        self._edited()
        return True

    def _edited(self):
        self.ctrl.load(self.history.program)
        self._validate_sel()

    def _validate_sel(self):
        prog = self.history.program
        ok = True
        if self.sel is not None:
            try:
                if self.sel[0] == "contact":
                    ed.contact_at(prog, self.sel[1], self.sel[2])
                    if self.sel2 is not None:
                        ed.contact_at(prog, self.sel[1], self.sel2)
                elif self.sel[1] >= len(prog.rungs):
                    ok = False
            except EditError:
                ok = False
        if not ok:
            self.sel = self.sel2 = None

    def _guard(self, fn, *args):
        """地址框有焦点时，快捷键不响应"""
        if self.editor_bar.typing():
            return
        fn(*args)

    def ctrl_button(self, addr, pressed):
        self.ctrl.set_button(addr, pressed)

    def _need_contact(self):
        if not self.editable:
            raise EditError("选择题关卡不能编辑")
        if self.sel is None or self.sel[0] != "contact":
            raise EditError("请先点选一个触点")
        return self.sel[1], self.sel[2]

    def _need_row(self):
        if self.sel is None:
            raise EditError("请先点选一行里的触点或线圈")
        return self.sel[1]

    def _try(self, fn):
        try:
            fn()
        except EditError as e:
            self.say(str(e))

    def on_insert_right(self):
        def f():
            r, k = self._need_contact()
            if self.do(ed.insert_series, r, k, Contact("X0"), after=True):
                self.sel, self.sel2 = ("contact", r, k + 1), None
        self._try(f)

    def on_insert_left(self):
        def f():
            r, k = self._need_contact()
            if self.do(ed.insert_series, r, k, Contact("X0"), after=False):
                self.sel, self.sel2 = ("contact", r, k), None
        self._try(f)

    def on_parallel(self):
        def f():
            r, k = self._need_contact()
            k2 = self.sel2
            if self.do(ed.add_parallel, r, k, Contact("X0"), k2=k2):
                self.sel, self.sel2 = ("contact", r, (k if k2 is None else k2) + 1), None
        self._try(f)

    def on_delete(self):
        def f():
            r, k = self._need_contact()
            if self.do(ed.delete_contact, r, k):
                self.sel = self.sel2 = None
        self._try(f)

    def on_delete_key(self):
        if self.sel is not None and self.sel[0] == "coil":
            self.say("线圈不能删，可以用“行−”删整行")
        else:
            self.on_delete()

    def on_toggle_nc(self):
        def f():
            r, k = self._need_contact()
            c = ed.contact_at(self.history.program, r, k)
            self.do(ed.set_contact, r, k, nc=not c.nc)
        self._try(f)

    def on_addr_enter(self, text):
        def f():
            r, k = self._need_contact()
            ok = self.do(ed.set_contact, r, k, addr=text.strip().upper())
            self.editor_bar.mark_bad(self.editor_bar.addr_entry, not ok)
        self._try(f)

    # 线圈
    def _coil_row(self):
        if not self.editable:
            raise EditError("选择题关卡不能编辑")
        if self.sel is None or self.sel[0] != "coil":
            raise EditError("请先点选一个线圈")
        return self.sel[1]

    def _set_out(self, kind, text=None, ktext=None):
        r = self._coil_row()
        eb = self.editor_bar
        addr = (eb.get(eb.coil_addr) if text is None else text).strip().upper()
        ktxt = (eb.get(eb.coil_k) if ktext is None else ktext).strip()
        defaults = {"OUT": ("Y0", "YM"), "OUT T": ("T0", "T"), "OUT C": ("C0", "C"), "RST": ("C0", "TC")}
        d, prefixes = defaults[kind]
        if not addr or addr[0] not in prefixes:
            addr = d                                            # 类型和地址前缀不匹配 → 用默认地址
        try:
            k = int(ktxt) if ktxt else (10 if kind == "OUT T" else 3)
        except ValueError:
            self.say("K 必须是整数")
            eb.mark_bad(eb.coil_k)
            return
        out = {"OUT": lambda: Out(addr), "OUT T": lambda: OutT(addr, k),
               "OUT C": lambda: OutC(addr, k), "RST": lambda: Rst(addr)}[kind]()
        ok = self.do(ed.set_output, r, out)
        eb.mark_bad(eb.coil_addr, not ok)
        eb.mark_bad(eb.coil_k, not ok)
        if ok:
            self._shown_sel = "refresh"

    def on_out(self): self._try(lambda: self._set_out("OUT"))
    def on_out_t(self): self._try(lambda: self._set_out("OUT T"))
    def on_out_c(self): self._try(lambda: self._set_out("OUT C"))
    def on_rst(self): self._try(lambda: self._set_out("RST"))

    def on_coil_enter(self, text=None):
        def f():
            r = self._coil_row()
            out = self.history.program.rungs[r].out
            kind = {Out: "OUT", OutT: "OUT T", OutC: "OUT C", Rst: "RST"}[type(out)]
            self._set_out(kind)
        self._try(f)

    # 行 / 撤销
    def on_add_rung(self):
        def f():
            if not self.editable:
                raise EditError("选择题关卡不能编辑")
            idx = None if self.sel is None else self.sel[1] + 1
            if self.do(ed.add_rung, idx):
                n = (len(self.history.program.rungs) - 1) if idx is None else idx
                self.sel, self.sel2 = ("contact", n, 0), None
        self._try(f)

    def on_del_rung(self):
        def f():
            r = self._need_row()
            if self.do(ed.delete_rung, r):
                self.sel = self.sel2 = None
        self._try(f)

    def _move(self, d):
        def f():
            r = self._need_row()
            if self.do(ed.move_rung, r, d):
                self.sel = (self.sel[0], r + d) + tuple(self.sel[2:])
        self._try(f)

    def on_move_up(self): self._move(-1)
    def on_move_down(self): self._move(1)

    def on_undo(self):
        if self.history.undo():
            self._edited()
        else:
            self.say("没有可撤销的操作")

    def on_redo(self):
        if self.history.redo():
            self._edited()
        else:
            self.say("没有可重做的操作")

    def on_click(self):
        """点选梯形图里的触点 / 线圈。Shift+点第二个触点 = 选一段"""
        mw = self.mouseWatcherNode
        if (mw is None or not mw.hasMouse() or not self.editable or self._drawing is None
                or not self.popup.root.isHidden() or not self.level_select.root.isHidden()):
            return
        x, y = mw.getMouseX() * ASPECT, mw.getMouseY()
        if not self.ladder.contains(x, y):
            return
        self.editor_bar.release_focus()
        g = self.ladder.screen_to_grid(x, y)
        hit = hit_test(self._drawing, *g) if g else None
        shift = mw.getModifierButtons().isDown(KeyboardButton.shift())
        if (shift and hit and hit[0] == "contact" and self.sel and self.sel[0] == "contact"
                and self.sel[1] == hit[1] and hit[2] != self.sel[2]):
            k1, k2 = sorted((self.sel[2], hit[2]))
            self.sel, self.sel2 = ("contact", hit[1], k1), k2
        else:
            self.sel, self.sel2 = hit, None
        self.editor_bar.clear_marks()

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

    def on_wheel(self, d):
        mw = self.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return
        x, y = mw.getMouseX() * ASPECT, mw.getMouseY()
        if self.ladder.contains(x, y):
            self.ladder.scroll_by(d * 1.5)
        for t in (self.il_table, self.mon_table):
            if t.contains(x, y):
                t.scroll_by(d * 2)

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
        dt = globalClock.getDt()
        self.msg_t = max(0.0, self.msg_t - dt)
        self.ctrl.update(dt)
        self.refresh()
        return task.cont

    def refresh(self):
        c = self.ctrl
        # 弹窗打开时关掉 3D 视图（DisplayRegion 画在 2D 之上，会挡住弹窗）
        modal = not self.popup.root.isHidden() or not self.level_select.root.isHidden()
        self.tank_scene.dr.setActive(not modal)
        d = draw_program(c.program, c.plc, c.current_rung)
        self._drawing = d
        d.elems.extend(selection_elems(d, self.sel, self.sel2))
        self._sync_toolbar()
        if c.current_rung is not None:
            top = d.rung_top[c.current_rung]
            self.ladder.follow(top, top + 1.5)
        self.ladder.redraw(d)
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
        if self.msg_t > 0:
            self.status["text"] = "! " + self.msg
            self.status["text_fg"] = (1, 0.45, 0.35, 1)
            self.status["text_scale"] = 0.04
        else:
            mode = "运行" if c.mode == "run" else "暂停"
            self.status["text"] = f"[{mode}] 状态: {c.phase_text or '-'}   扫描次数: {c.plc.scan_count}"
            self.status["text_fg"] = (1, 0.9, 0.2, 1)
            self.status["text_scale"] = 0.045

    def _sync_toolbar(self):
        eb = self.editor_bar
        eb.set_visible(self.editable)
        kind = None if self.sel is None else self.sel[0]
        eb.set_mode(kind)
        key = (self.sel, id(self.history.program), len(self.history._undo), len(self.history._redo))
        if key == self._shown_sel and self._shown_sel != "refresh":
            return
        self._shown_sel = key
        prog = self.history.program
        try:
            if kind == "contact":
                eb.put(eb.addr_entry, ed.contact_at(prog, self.sel[1], self.sel[2]).addr)
            elif kind == "coil":
                out = prog.rungs[self.sel[1]].out
                eb.put(eb.coil_addr, out.addr)
                eb.put(eb.coil_k, str(out.k) if hasattr(out, "k") else "")
        except EditError:
            pass
