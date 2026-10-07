"""P2 示例程序"""
from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program

DEMOS = [
    ("自保持", Program([
        Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0")),
    ])),
    ("定时器", Program([
        Rung(NO("X0"), OutT("T0", 30)),
        Rung(NO("T0"), Out("Y1")),
    ])),
    ("计数器", Program([
        Rung(NO("X0"), OutC("C0", 3)),
        Rung(NO("X1"), Rst("C0")),
        Rung(NO("C0"), Out("Y2")),
    ])),
    ("双线圈", Program([
        Rung(NO("X0"), Out("Y0")),
        Rung(NO("X1"), Out("Y0")),
    ])),
    ("给水到上限", Program([
        Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1"), NC("X3")]), Out("Y0")),
    ])),
    ("满水后排水", Program([
        Rung(NO("X3"), OutT("T0", 10)),
        Rung(Series([Parallel([NO("T0"), NO("M0")]), NO("X2")]), Out("M0")),
        Rung(NO("M0"), Out("Y1")),
    ])),
]
