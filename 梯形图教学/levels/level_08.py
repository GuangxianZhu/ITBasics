from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program
from ._common import runner, tap, judge, Fail

ID = 8
TITLE = "第8关 综合：自动循环"
KIND = "task"
INTRO = """把学过的全用上。按一次 X0 后自动运行：
给水到上限 → 等 2 秒 → 排水到下限以下 → 再给水……排水 3 次后停止，完成灯亮。

M0 = 运行中（自保持，X1 或计满 3 次就停）
M1 = 排水中（自保持，排到下限以下结束）
进水和排水用 M1 互锁（インターロック），不会同时开。

示例程序缺了两行，所以现在只会进水、不会排水。"""
TASK = "补上缺的两行：① 排水状态 M1：LD T0 / OR M1 / AND X2 / OUT M1　② 数排水次数：LD M1 / OUT C0 K3"

_RUN = Rung(Series([Parallel([NO("X0"), NO("M0")]), NC("X1"), NC("C0")]), Out("M0"))
_FILL = Rung(Series([NO("M0"), NC("M1"), NC("X3")]), Out("Y0"))
_WAIT = Rung(Series([NO("X3"), NO("M0")]), OutT("T0", 20))
_DRAIN_STATE = Rung(Series([Parallel([NO("T0"), NO("M1")]), NO("X2")]), Out("M1"))
_DRAIN = Rung(NO("M1"), Out("Y1"))
_COUNT = Rung(NO("M1"), OutC("C0", 3))
_LAMP = Rung(NO("C0"), Out("Y2"))
_RESET = Rung(NO("X1"), Rst("C0"))

EXAMPLE = Program([_RUN, _FILL, _WAIT, _DRAIN, _LAMP, _RESET])
SOLUTION = Program([_RUN, _FILL, _WAIT, _DRAIN_STATE, _DRAIN, _COUNT, _LAMP, _RESET])


@judge
def check(p):
    r = runner(p)
    tap(r, "X0")
    drains, prev, top = 0, False, 0.0
    both_open = False
    for _ in range(700):                      # 70 秒
        r.run(0.1)
        y1 = r.plc.output("Y1")
        if y1 and not prev:
            drains += 1
        prev = y1
        top = max(top, r.tank.level)
        if r.plc.output("Y0") and y1:
            both_open = True
    if r.tank.overflow or top >= 81.0:
        raise Fail("水溢出了。")
    if both_open:
        raise Fail("进水阀和排水阀同时开了，互锁没做好。")
    if drains == 0:
        raise Fail("一次也没有排水。")
    if drains != 3:
        raise Fail(f"应该排水 3 次，实际 {drains} 次。")
    if not r.plc.output("Y2"):
        raise Fail("排水 3 次后完成灯 Y2 应该亮。")
    if r.plc.output("Y0") or r.plc.output("Y1") or r.tank.level >= 20.0:
        raise Fail("3 次后应该排空并停止。")
