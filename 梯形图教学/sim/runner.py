"""无界面联动：按钮 + 传感器 → PLC → 水槽"""
from plc.engine import PLC
from sim.tank import Tank


class Runner:
    def __init__(self, program, tank=None, scan_ms=10):
        self.program = program
        self.tank = tank if tank is not None else Tank()
        self.scan_ms = scan_ms
        self.plc = PLC(program, scan_ms)
        self.time = 0.0
        self._buttons = {}

    def press(self, addr):
        self._buttons[addr] = True

    def release(self, addr):
        self._buttons[addr] = False

    def tick(self):
        for a, v in self._buttons.items():
            self.plc.set_input(a, v)
        for a, v in self.tank.sensors().items():
            self.plc.set_input(a, v)
        self.plc.scan()
        dt = self.scan_ms / 1000
        self.tank.step(dt, self.plc.output("Y0"), self.plc.output("Y1"))
        self.time += dt

    def run(self, seconds):
        for _ in range(round(seconds * 1000 / self.scan_ms)):
            self.tick()
