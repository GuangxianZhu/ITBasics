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
from ui.layout import Layout
from ui.widgets import Dragger, Pane, VScroll, Splitter, SCROLL_W
from ui import theme

BTN_NORMAL = theme.BTN
BTN_SELECTED = theme.BTN_SELECTED


class PlcApp(ShowBase):
    def __init__(self):
        loadPrcFileData("", "window-title PLC 梯形图教学\nwin-size 1280 720\nwin-min-size 960 600")
        ShowBase.__init__(self)
        self.disableMouse()
        self.setBackgroundColor(*theme.BG[:3])
        self.win.setClearColor(theme.BG)
        self.win.setClearColorActive(True)
        DirectFrame(parent=self.render2d, frameColor=theme.BG,
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
        self._mouse_held = set()

        self.dragger = Dragger(self)
        self.layout = Layout()
        self.aspect = self.getAspectRatio()
        font = self.font

        # 顶栏 / 底栏底色；三个锚点跟着窗口角落走
        self.top_bg = DirectFrame(parent=self.a2d, frameColor=theme.BAR, frameSize=(0, 1, 0, 1))
        self.bot_bg = DirectFrame(parent=self.a2d, frameColor=theme.BAR, frameSize=(0, 1, 0, 1))
        self.anchor_tl = self.a2d.attachNewNode("anchor_tl")
        self.anchor_bl = self.a2d.attachNewNode("anchor_bl")
        self.anchor_br = self.a2d.attachNewNode("anchor_br")

        # 顶栏：关卡 + 示例按钮（当前项底色不同）
        ty = -0.06
        make_button(self.anchor_tl, font, "关卡", (0.12, 0, ty), scale=0.04,
                    size=(-2, 2, -0.9, 1.1), command=self.open_levels)
        self.demo_bar = self.anchor_tl.attachNewNode("demo_bar")
        self.demo_btns = []
        for i, (name, _) in enumerate(DEMOS):
            b = make_button(self.demo_bar, font, name, (0.42 + i * 0.3, 0, ty),
                            scale=0.04, size=(-3.4, 3.4, -0.9, 1.1), command=self.pick_demo)
            b["extraArgs"] = [i]
            self.demo_btns.append(b)

        # 四个面板
        self.p_ladder = Pane(self.a2d, font, "梯形图（ラダー図）")
        self.p_il = Pane(self.a2d, font, "指令表（命令リスト）")
        self.p_mon = Pane(self.a2d, font, "监视（モニタ）")
        self.p_tank = Pane(self.a2d, font, "水槽（タンク）")
        self.ladder = LadderView(self.a2d, font, (0, 1, 0, 1))
        self.il_table = TextTable(self.a2d, font, 0, 0, -0.5, 0.056, 0.042, 0.8)
        self.mon_table = TextTable(self.a2d, font, 0, 0, -0.5, 0.056, 0.04, 1.0)
        self.sb_ladder = VScroll(self.a2d, self.dragger, self.ladder.set_scroll)
        self.sb_il = VScroll(self.a2d, self.dragger, self.il_table.set_offset)
        self.sb_mon = VScroll(self.a2d, self.dragger, self.mon_table.set_offset)

        # 水槽面板：3D 视图 + 水位 + 按钮
        self.tank_scene = TankScene(self, font)
        self.tank_ui = self.a2d.attachNewNode("tank_ui")
        self.level_lbl = DirectLabel(parent=self.tank_ui, text="", text_font=font, text_scale=0.05,
                                     text_fg=theme.TITLE, frameColor=(0, 0, 0, 0),
                                     text_align=TextNode.ALeft)
        self.reset_btn = make_button(self.tank_ui, font, "重置水槽", (0, 0, 0), scale=0.036,
                                     size=(-3.2, 3.2, -0.9, 1.1), command=lambda: self.ctrl.reset_tank())
        self.in_btns = {}
        for i, (addr, txt) in enumerate((("X0", "X0 启动"), ("X1", "X1 停止"))):
            b = make_button(self.tank_ui, font, txt, (0, 0, 0), scale=0.04,
                            size=(-4.6, 4.6, -1.2, 1.5))
            b.bind(DGG.B1PRESS, lambda e, a=addr: self.mouse_button(a, True))
            b.bind(DGG.B1RELEASE, lambda e, a=addr: self.mouse_button(a, False))
            self.in_btns[addr] = b

        # 分隔条（拖动改面板大小）
        self.splitters = {n: Splitter(self.a2d, self.dragger, n, self.on_split, vertical=(n != "split_y"))
                          for n in ("split_x", "split_y", "split_t")}

        # 底栏：控制按钮（左）+ 状态（右）
        by = 0.06
        bl = self.anchor_bl
        make_button(bl, font, "▶ 运行", (0.17, 0, by), scale=0.04, size=(-3.2, 3.2, -0.9, 1.1),
                    command=lambda: self.ctrl.run())
        make_button(bl, font, "暂停", (0.47, 0, by), scale=0.04, size=(-3.2, 3.2, -0.9, 1.1),
                    command=lambda: self.ctrl.pause())
        make_button(bl, font, "单步", (0.77, 0, by), scale=0.04, size=(-3.2, 3.2, -0.9, 1.1),
                    command=self.on_step_one)
        make_button(bl, font, "单轮", (1.07, 0, by), scale=0.04, size=(-3.2, 3.2, -0.9, 1.1),
                    command=self.on_step_scan)
        DirectLabel(parent=bl, text="慢放", text_font=font, text_scale=0.038,
                    text_fg=theme.TEXT_DIM, frameColor=(0, 0, 0, 0), pos=(1.36, 0, by - 0.012))
        self.slider = DirectSlider(parent=bl, range=(0, 1), value=0, pageSize=0.1,
                                   pos=(1.68, 0, by), scale=0.24, command=self.on_slider,
                                   frameColor=(1, 1, 1, 0.12), frameSize=(-1, 1, -0.02, 0.02),
                                   thumb_frameColor=theme.ACCENT, thumb_relief=DGG.FLAT,
                                   thumb_frameSize=(-0.05, 0.05, -0.09, 0.09))
        self.speed_lbl = DirectLabel(parent=bl, text="0.00秒", text_font=font,
                                     text_scale=0.038, text_fg=theme.TEXT, frameColor=(0, 0, 0, 0),
                                     pos=(1.97, 0, by - 0.012), text_align=TextNode.ALeft)
        self.status = DirectLabel(parent=self.anchor_br, text="", text_font=font, text_scale=0.042,
                                  text_fg=theme.WARN, frameColor=(0, 0, 0, 0),
                                  pos=(-0.05, 0, by - 0.014), text_align=TextNode.ARight)

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
        self.level_bar = LevelBar(self.anchor_tl, self.font, 0.3, -0.06, self.show_intro,
                                  self.restore_example, self.load_solution, self.judge)
        self.level_select = LevelSelect(self.a2d, self.font, self.session.levels,
                                        self.enter_level, self.leave_level, self.enter_sandbox)
        # 编辑器工具栏（梯形图区上方一行）
        self.editor_bar = EditorBar(self.a2d, self.font, 0, 0, self)
        self._toolbar_on = None
        self.accept("window-event", self.on_window_event)
        self.relayout()
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
        x, y = mw.getMouseX() * self.aspect, mw.getMouseY()
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
        x, y = mw.getMouseX() * self.aspect, mw.getMouseY()
        if self.ladder.contains(x, y):
            self.ladder.scroll_by(d * 1.5)
        for t in (self.il_table, self.mon_table):
            if t.contains(x, y):
                t.scroll_by(d * 2)

    # ---------- 布局 ----------
    def on_window_event(self, win):
        if win is not self.win:
            return
        a = self.getAspectRatio()
        size = (win.getXSize(), win.getYSize())
        if abs(a - self.aspect) > 1e-4 or size != getattr(self, "_win_size", None):
            self._win_size = size
            self.relayout()

    def on_split(self, name, x, y):
        self.layout.drag(name, x, y, self.aspect)
        self.relayout()

    def relayout(self):
        a = self.aspect = self.getAspectRatio()
        rs = self.layout.rects(a)
        self.top_bg["frameSize"] = rs["top"]
        self.bot_bg["frameSize"] = rs["bottom"]
        self.anchor_tl.setPos(-a, 0, 1)
        self.anchor_bl.setPos(-a, 0, -1)
        self.anchor_br.setPos(a, 0, -1)
        for name, pane in (("ladder", self.p_ladder), ("il", self.p_il),
                           ("mon", self.p_mon), ("tank", self.p_tank)):
            pane.set_rect(*rs[name])
        for name, sp in self.splitters.items():
            sp.set_rect(*rs[name])

        # 梯形图面板：标题栏下面一条工具栏（可编辑时），再下面是图 + 滚动条
        l, r, b, t = self.p_ladder.content_rect()
        self._toolbar_on = self.editable
        if self._toolbar_on:
            rows = self.editor_bar.place_at(l, t - 0.025, r)
            t -= rows * EditorBar.ROW_H + 0.01
        self.ladder.set_region((l + 0.1, r - SCROLL_W - 0.015, b, t))
        self.sb_ladder.set_rect(r - SCROLL_W, b, t)

        # 两张表
        for pane, table, sb in ((self.p_il, self.il_table, self.sb_il),
                                (self.p_mon, self.mon_table, self.sb_mon)):
            l, r, b, t = pane.content_rect()
            table.set_geometry(l + 0.01, t - 0.03, b + 0.01, r - l - SCROLL_W - 0.025)
            sb.set_rect(r - SCROLL_W, b, t)

        # 水槽：上面 3D，下面水位 + 按钮
        l, r, b, t = self.p_tank.content_rect(pad=0.012)
        ctrl_h = 0.27
        fx = lambda x: (x / a + 1) / 2
        fy = lambda y: (y + 1) / 2
        self.tank_scene.set_region((fx(l), fx(r), fy(b + ctrl_h), fy(t)))
        self.level_lbl.setPos(l + 0.02, 0, b + ctrl_h - 0.085)
        self.reset_btn.setPos(r - 0.14, 0, b + ctrl_h - 0.07)
        w = r - l
        self.in_btns["X0"].setPos(l + w * 0.27, 0, b + 0.075)
        self.in_btns["X1"].setPos(l + w * 0.73, 0, b + 0.075)

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
        self.dragger.update()
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
        self.sb_ladder.update(*self.ladder.scroll_metrics())
        il = il_rows(c.program)
        hl = {i for i, (r, _) in enumerate(il) if r is not None and r == c.current_rung}
        self.il_table.set_rows([("" if r is None else str(r + 1), t) for r, t in il],
                               [0, 0.1], highlight=hl)
        self.sb_il.update(*self.il_table.scroll_metrics())
        mon = monitor_rows(c.program, c.plc)
        mw_ = self.mon_table.width
        self.mon_table.set_rows([(a, n, v) for a, n, v, _ in mon], [0, 0.12, max(0.5, mw_ - 0.22)],
                                on_col=[m[3] for m in mon])
        self.sb_mon.update(*self.mon_table.scroll_metrics())
        st = scene_state(c)
        self.tank_scene.update(st)
        self.level_lbl["text"] = st["level_text"]
        if self.msg_t > 0:
            self.status["text"] = "! " + self.msg
            self.status["text_fg"] = theme.ERR
            self.status["text_scale"] = 0.04
        else:
            mode = "运行" if c.mode == "run" else "暂停"
            self.status["text"] = f"[{mode}] 状态: {c.phase_text or '-'}   扫描次数: {c.plc.scan_count}"
            self.status["text_fg"] = theme.WARN
            self.status["text_scale"] = 0.045

    def _sync_toolbar(self):
        eb = self.editor_bar
        eb.set_visible(self.editable)
        if self.editable != self._toolbar_on:
            self.relayout()
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
