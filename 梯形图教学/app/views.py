"""指令表行、监视表行"""
from plc.model import Contact, Series, Parallel, Out, OutT, OutC, Rst
from plc.to_il import to_il_rungs

IO_NAMES = {
    "X0": "启动按钮（起動ボタン）",  "X1": "停止按钮（停止ボタン）",
    "X2": "下限液位（下限レベル）",  "X3": "上限液位（上限レベル）",
    "Y0": "给水阀（給水バルブ）",    "Y1": "排水阀（排水バルブ）",
    "Y2": "完成灯（完了ランプ）",
}
_FIXED = ["X0", "X1", "X2", "X3", "Y0", "Y1", "Y2"]


def il_rows(program):
    rows = []
    for i, line in enumerate(to_il_rungs(program)):
        rows.extend((i, t) for t in line)
    rows.append((None, "END"))
    return rows


def _contacts(node):
    if isinstance(node, Contact):
        yield node.addr
    else:
        for it in node.items:
            yield from _contacts(it)


def monitor_rows(program, plc):
    used = set()
    t_k, c_k = {}, {}
    for rung in program.rungs:
        used.update(_contacts(rung.cond))
        used.add(rung.out.addr)
        if isinstance(rung.out, OutT):
            t_k.setdefault(rung.out.addr, rung.out.k)
        elif isinstance(rung.out, OutC):
            c_k.setdefault(rung.out.addr, rung.out.k)
    extra = []
    for prefix in "MTC":
        extra += sorted((a for a in used if a[0] == prefix), key=lambda a: int(a[1:]))
    rows = []
    for a in _FIXED + extra:
        if a[0] == "T":
            k = t_k.get(a)
            val = f"{plc.timer_ms(a) / 1000:.1f}/" + (f"{k / 10:.1f}" if k is not None else "-")
        elif a[0] == "C":
            k = c_k.get(a)
            val = f"{plc.counter_value(a)}/" + (str(k) if k is not None else "-")
        else:
            val = "ON" if plc.get(a) else "OFF"
        rows.append((a, IO_NAMES.get(a, ""), val, plc.get(a)))
    return rows
