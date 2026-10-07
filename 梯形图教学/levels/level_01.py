from plc.model import NO, Out, Rung, Program
from ._common import runner, judge, Fail

ID = 1
TITLE = "第1关 a接点与线圈"
KIND = "task"
INTRO = """梯形图从左往右读：左边是条件，右边是输出。

─┤ ├─  a接点（常开触点）：元件 ON 时导通
─( )─  线圈（コイル）：这一行导通 → 元件 ON

示例：LD X0 / OUT Y0
按住 X0（启动）→ Y0（给水阀）打开 → 水位上升
松开 → 阀门关闭。按钮是"按住才 ON"的。"""
TASK = "加一行：按住 X1（停止按钮）时打开 Y1（排水阀）。"
EXAMPLE = Program([Rung(NO("X0"), Out("Y0"))])
SOLUTION = Program([Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y1"))])


@judge
def check(p):
    r = runner(p, level=50.0)
    r.press("X1"); r.run(2.0)
    if r.tank.level > 32.0:
        raise Fail("按住 X1 两秒，水位应该下降约 20%，但没有降下来。")
    r.release("X1"); r.run(0.05)
    lvl = r.tank.level
    r.run(1.0)
    if abs(r.tank.level - lvl) > 0.01:
        raise Fail("松开 X1 后水位还在变化，排水阀应该关上。")
    r.press("X0"); r.run(1.0); r.release("X0")
    if r.tank.level < lvl + 9.0:
        raise Fail("原来的功能坏了：按住 X0 时应该进水。")
