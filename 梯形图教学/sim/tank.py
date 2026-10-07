"""水槽（纯逻辑）"""


class Tank:
    def __init__(self, level=0.0, fill_rate=10.0, drain_rate=10.0, low=20.0, high=80.0):
        self.level = float(level)
        self.fill_rate = fill_rate
        self.drain_rate = drain_rate
        self.low = low
        self.high = high
        self.overflow = False

    def step(self, dt, inlet, drain):
        lv = self.level + (self.fill_rate if inlet else 0) * dt - (self.drain_rate if drain else 0) * dt
        self.level = min(100.0, max(0.0, lv))
        if inlet and lv >= 100.0:
            self.overflow = True
        elif self.level < 100.0:
            self.overflow = False

    def sensors(self):
        return {"X2": self.level >= self.low, "X3": self.level >= self.high}
