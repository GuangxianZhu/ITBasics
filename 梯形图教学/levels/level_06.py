from plc.model import NO, Out, OutT, Rung, Program
from ._common import runner, judge, Fail

ID = 6
TITLE = "第6关 定时器"
KIND = "task"
INTRO = """─( T0 K50 )─  定时器（タイマ）：这一行一直导通，计满设定时间后 T0 的触点闭合。
K 的单位是 0.1 秒：K50 = 5 秒。条件一断开，计时立刻清零。

示例：水在上限（X3 ON）时 T0 开始计时，5 秒后 T0 闭合 → 打开排水阀 Y1。
（降到上限以下 X3 断开 → T0 清零 → 排水停止。）

监视表里 T0 显示"当前秒/设定秒"。"""
TASK = "改成满水 3 秒后就排水。"
EXAMPLE = Program([Rung(NO("X3"), OutT("T0", 50)), Rung(NO("T0"), Out("Y1"))])
SOLUTION = Program([Rung(NO("X3"), OutT("T0", 30)), Rung(NO("T0"), Out("Y1"))])


@judge
def check(p):
    r = runner(p, level=85.0)
    r.run(2.9)
    if r.tank.level < 84.99:
        raise Fail("排水太早了，应该等满 3 秒。")
    r.run(0.3)
    if r.tank.level > 84.99:
        raise Fail("3 秒到了还没开始排水。")
    r.run(10.0)
    if r.tank.level < 79.0:
        raise Fail("降到上限以下后应该停止排水（别改示例的结构）。")
