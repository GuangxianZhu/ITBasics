from plc.model import NO, NC, Series, Parallel, Out, Rung, Program
from ._common import runner, judge, Fail

ID = 3
TITLE = "第3关 串联与并联"
KIND = "task"
INTRO = """串联（AND）：几个触点排成一排，要全部导通才有电 ——"而且"。
并联（OR）：几条支路上下叠起来，任意一条导通就有电 ——"或者"。

示例：LD X0 / ANI X3 / OUT Y0
"按住 X0，而且 没到上限" 才进水。
所以就算一直按着 X0，到上限也会自动停。"""
TASK = "加一行：按住 X1，或者 水位到达上限（X3 ON），都打开排水阀 Y1。"
EXAMPLE = Program([Rung(Series([NO("X0"), NC("X3")]), Out("Y0"))])
SOLUTION = Program([Rung(Series([NO("X0"), NC("X3")]), Out("Y0")),
                    Rung(Parallel([NO("X1"), NO("X3")]), Out("Y1"))])


@judge
def check(p):
    r = runner(p, level=50.0)
    r.press("X1"); r.run(1.0); r.release("X1")
    if r.tank.level > 41.0:
        raise Fail("按住 X1 时应该排水。")
    r = runner(p, level=85.0)
    r.run(3.0)
    if r.tank.level >= 80.0:
        raise Fail("水位在上限以上时，就算不按 X1 也应该排水。")
    if r.tank.level < 79.0:
        raise Fail("降到上限以下就该停止排水了。")
    r = runner(p, level=0.0)
    r.press("X0"); r.run(3.0); r.release("X0")
    if r.tank.level < 25.0:
        raise Fail("原来的功能坏了：按住 X0 时应该进水。")
