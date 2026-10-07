from plc.model import NO, Out, Rung, Program

ID = 5
TITLE = "第5关 扫描周期与双线圈"
KIND = "quiz"
INTRO = """PLC 不是"同时"看整张图，而是一轮一轮地扫描（スキャン）：
① 输入采样：一次性读入所有 X
② 从第 1 行到最后一行，依次计算、写映像
③ 输出刷新：一次性把 Y 映像写到外面

同一个线圈在两行里都写（双线圈 / ダブルコイル），
前一行写的结果会被后一行覆盖。

试试：暂停，按住 X0，用"单步"一步步走，盯着监视表里的 Y0。"""
QUESTION = "只按住 X0（X1 不按），一轮扫描结束后，给水阀 Y0 的输出是？"
CHOICES = [
    "ON：第 1 行已经把 Y0 置成 ON 了",
    "OFF：第 2 行又把 Y0 写成 OFF，最后一行说了算",
    "ON 和 OFF 快速交替闪烁",
    "程序出错，PLC 停止运行",
]
ANSWER = 1
EXAMPLE = Program([Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y0"))])
