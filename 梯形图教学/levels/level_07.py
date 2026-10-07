from plc.model import NO, Out, OutC, Rst, Rung, Program
from ._common import runner, tap, judge, Fail

ID = 7
TITLE = "第7关 计数器"
KIND = "task"
INTRO = """─( C0 K3 )─  计数器（カウンタ）：这一行每次从 OFF 变成 ON（上升沿）就加 1，
到 3 时 C0 的触点闭合。按住不放只算 1 次。

计数器到了设定值会一直保持，必须用 RST C0（リセット）清零。

示例：每按一次 X0 算一批，按满 3 次点亮完成灯 Y2。"""
TASK = "加一行：按 X1 时把计数器 C0 清零（RST C0），完成灯随之熄灭。"
EXAMPLE = Program([Rung(NO("X0"), OutC("C0", 3)), Rung(NO("C0"), Out("Y2"))])
SOLUTION = Program([Rung(NO("X0"), OutC("C0", 3)), Rung(NO("C0"), Out("Y2")),
                    Rung(NO("X1"), Rst("C0"))])


@judge
def check(p):
    r = runner(p)
    for _ in range(3):
        tap(r, "X0"); r.run(0.05)
    r.run(0.05)
    if not r.plc.output("Y2"):
        raise Fail("按 3 次 X0 后完成灯 Y2 应该亮（原来的两行别删）。")
    tap(r, "X1"); r.run(0.05)
    if r.plc.output("Y2") or r.plc.counter_value("C0") != 0:
        raise Fail("按 X1 后计数器应该清零、完成灯熄灭。")
    tap(r, "X0"); r.run(0.05)
    if r.plc.output("Y2"):
        raise Fail("清零后再按 1 次不应该亮灯。")
