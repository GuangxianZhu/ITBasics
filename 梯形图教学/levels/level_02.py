from plc.model import NO, NC, Out, Rung, Program
from ._common import runner, judge, Fail

ID = 2
TITLE = "第2关 b接点"
KIND = "task"
INTRO = """─┤/├─  b接点（常闭触点）：元件 OFF 时导通，ON 时断开。
指令表里写成 LDI / ANI / ORI（I = Inverse，取反）。

示例：LDI X3 / OUT Y0
X3 是上限液位开关。水没到上限 → X3 OFF → b接点导通 → 一直进水；
到了上限 → X3 ON → b接点断开 → 停止进水。

现实里"停止按钮""急停"也常用 b接点：线断了等于按了停止，更安全。"""
TASK = "加一行：水位低于下限（X2 OFF）时点亮指示灯 Y2。提示：用 X2 的 b接点。"
EXAMPLE = Program([Rung(NC("X3"), Out("Y0"))])
SOLUTION = Program([Rung(NC("X3"), Out("Y0")), Rung(NC("X2"), Out("Y2"))])


@judge
def check(p):
    r = runner(p, level=0.0)
    r.run(0.5)
    if not r.plc.output("Y2"):
        raise Fail("水位低于下限时，Y2 应该亮。")
    r.run(3.0)
    if r.tank.level < 20.0:
        raise Fail("水应该自动往上涨（原来的第 1 行别删）。")
    if r.plc.output("Y2"):
        raise Fail("水位超过下限后，Y2 应该熄灭。")
    r.run(10.0)
    if not (80.0 <= r.tank.level < 81.0):
        raise Fail("水位应该停在上限附近。")
