"""运行 / 暂停 / 单步 / 慢放（纯逻辑，不依赖 panda3d）"""
from plc.engine import PLC, Step


class Controller:
    def __init__(self, program, scan_ms=10):
        self.scan_ms = scan_ms
        self.mode = "run"
        self.speed = 0.0
        self._buttons = {}
        self._acc_ms = 0
        self.load(program)

    def load(self, program):
        """换程序：新建 PLC；按钮状态保留"""
        self.program = program
        self.plc = PLC(program, self.scan_ms)
        for addr, v in self._buttons.items():
            self.plc.set_input(addr, v)
        self._gen = None
        self.mid_scan = False
        self.last_step = None
        self._acc_ms = 0

    # ---- 状态派生 ----
    @property
    def current_rung(self):
        s = self.last_step
        return s.rung if (s is not None and s.phase == "rung") else None

    @property
    def phase_text(self) -> str:
        s = self.last_step
        if s is None:
            return ""
        if s.phase == "input":
            return "输入采样"
        if s.phase == "rung":
            return f"执行第 {s.rung + 1} 行"
        return "输出刷新"

    # ---- 操作 ----
    def set_button(self, addr, pressed):
        self._buttons[addr] = bool(pressed)
        self.plc.set_input(addr, bool(pressed))

    def run(self):
        self.mode = "run"

    def pause(self):
        self.mode = "pause"

    def step_one(self) -> Step:
        if self._gen is None:
            self._gen = self.plc.steps()
        s = next(self._gen)
        self.last_step = s
        if s.phase == "output":
            self._gen = None
            self.mid_scan = False
        else:
            self.mid_scan = True
        return s

    def step_scan(self):
        while self.step_one().phase != "output":
            pass

    def update(self, dt):
        if self.mode != "run":
            return
        self._acc_ms += round(dt * 1000)
        if self.speed <= 0:
            n = self._acc_ms // self.scan_ms
            if n > 100:
                n, self._acc_ms = 100, 0
            else:
                self._acc_ms -= n * self.scan_ms
            for _ in range(n):
                self.step_scan()
        else:
            interval = max(1, round(self.speed * 1000))
            n = self._acc_ms // interval
            if n > 1000:
                n, self._acc_ms = 1000, 0
            else:
                self._acc_ms -= n * interval
            for _ in range(n):
                self.step_one()
