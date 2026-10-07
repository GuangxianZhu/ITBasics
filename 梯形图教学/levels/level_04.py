from plc.model import NO, NC, Series, Parallel, Out, Rung, Program
from ._common import runner, tap, judge, Fail

ID = 4
TITLE = "第4关 自保持（自己保持回路）"
KIND = "task"
INTRO = """按钮一松开就 OFF，可我们想要"按一下就一直进水"。
办法：把输出 Y0 自己的触点并联在启动按钮旁边。

LD X0 / OR Y0 / ANI X1 / OUT Y0
按 X0 → Y0 ON → Y0 的触点也闭合 → 松开 X0 后电从 Y0 那条支路继续走 → 保持
按 X1（b接点断开）→ Y0 OFF → 支路也断 → 停止

这叫自保持（自己保持回路），几乎每个 PLC 程序里都有。"""
TASK = "示例程序会一直进水直到溢出。改一下：水位到上限（X3）时也自动停止进水。"
EXAMPLE = Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0"))])
SOLUTION = Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1"), NC("X3")]), Out("Y0"))])


@judge
def check(p):
    r = runner(p)
    tap(r, "X0")
    r.run(3.0)
    if r.tank.level < 25.0:
        raise Fail("按一下 X0 后应该一直进水（自保持）。")
    r.run(10.0)
    if r.tank.overflow or r.tank.level >= 81.0:
        raise Fail("水满溢出了！到上限 X3 时应该停止进水。")
    if r.tank.level < 80.0:
        raise Fail("水位没到上限就停了。")
    r = runner(p)
    tap(r, "X0"); r.run(2.0); tap(r, "X1")
    lvl = r.tank.level
    r.run(2.0)
    if abs(r.tank.level - lvl) > 0.01:
        raise Fail("按 X1 应该停止进水。")
