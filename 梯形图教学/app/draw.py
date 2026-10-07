"""梯形图 → 绘图元素列表（纯逻辑）。坐标：x 向右、y 向下，单位=格。"""
from dataclasses import dataclass

from plc.model import Contact, Series, Parallel, Out, OutT, OutC, Rst, normalize
from plc.layout import layout
from plc.engine import evaluate


@dataclass
class Elem:
    kind: str
    tag: tuple
    x1: float
    y1: float
    x2: float = 0.0
    y2: float = 0.0
    color: str = "idle"
    text: str = ""


@dataclass
class Drawing:
    elems: list
    width: float
    height: float
    rung_top: list


def _fresh(node):
    """复制树，让每个 Contact 都有独立 id（trace 以 id 为键）"""
    if isinstance(node, Contact):
        return Contact(node.addr, node.nc)
    return type(node)([_fresh(i) for i in node.items])


def _coil_text(out):
    if isinstance(out, OutT):
        return f"{out.addr} K{out.k}"
    if isinstance(out, OutC):
        return f"{out.addr} K{out.k}"
    if isinstance(out, Rst):
        return f"RST {out.addr}"
    return out.addr


def draw_program(program, plc, current_rung=None) -> Drawing:
    conds = [_fresh(normalize(r.cond)) for r in program.rungs]
    lays = [layout(c) for c in conds]
    W = max([1] + [l.width for l in lays])
    tops, y = [], 0
    for l in lays:
        tops.append(y)
        y += l.height + 1
    height = (tops[-1] + lays[-1].height) if lays else 0
    elems = []

    def line(tag, x1, y1, x2, y2, color):
        elems.append(Elem("line", tag, x1, y1, x2, y2, color))

    def wire(r, x1, x2, yy, powered, *extra):
        if x2 > x1 + 1e-9:
            line(("wire", r) + extra, x1, yy, x2, yy, "power" if powered else "idle")

    if lays:
        line(("rail_left",), 0, 0, 0, height, "rail")
        line(("rail_right",), W + 3, 0, W + 3, height, "rail")

    for r, rung in enumerate(program.rungs):
        cond, top = conds[r], tops[r]
        trace = {}
        p = evaluate(cond, plc.get, trace)
        counter = [0]

        def walk(node, col, row, left, tag_id):
            """画 node（左上角在 col,row 格），返回 (w, h)。x 基准：触点占 [col+1, col+2]"""
            if isinstance(node, Contact):
                k = counter[0]; counter[0] += 1
                x0, yc = col + 1, top + row + 0.5
                st = plc.get(node.addr)
                on = (not st) if node.nc else st
                c = "on" if on else "off"
                tag = ("contact", r, k)
                wire(r, x0, x0 + 0.38, yc, left, "in", k)
                wire(r, x0 + 0.62, x0 + 1, yc, trace[id(node)], "out", k)
                line(tag, x0 + 0.38, top + row + 0.2, x0 + 0.38, top + row + 0.8, c)
                line(tag, x0 + 0.62, top + row + 0.2, x0 + 0.62, top + row + 0.8, c)
                if node.nc:
                    line(tag, x0 + 0.3, top + row + 0.8, x0 + 0.7, top + row + 0.2, c)
                elems.append(Elem("text", ("label", r, k), x0 + 0.5, top + row + 0.1,
                                  color="text", text=node.addr))
                return 1, 1
            if isinstance(node, Series):
                cur, tw, th = left, 0, 0
                for it in node.items:
                    w, h = walk(it, col + tw, row, cur, None)
                    cur = trace[id(it)]
                    tw += w
                    th = max(th, h)
                return tw, th
            # Parallel
            subs, ch, mw = [], 0, 0
            for it in node.items:
                w, h = walk(it, col, row + ch, left, None)
                subs.append((it, row + ch, w))
                mw = max(mw, w)
                ch += h
            xr = col + 1 + mw
            for it, rr, w in subs:                       # 窄分支右侧补线
                wire(r, col + 1 + w, xr, top + rr + 0.5, trace[id(it)], "pad", rr)
            if len(subs) > 1:
                y1 = top + subs[0][1] + 0.5
                y2 = top + subs[-1][1] + 0.5
                line(("wire", r, "vl", col, row), col + 1, y1, col + 1, y2,
                     "power" if left else "idle")
                line(("wire", r, "vr", col, row), xr, y1, xr, y2,
                     "power" if trace[id(node)] else "idle")
            return mw, ch

        yc = top + 0.5
        wire(r, 0, 1, yc, True, "lead")
        w, h = walk(cond, 0, 0, True, None)
        wire(r, 1 + w, W + 1, yc, p, "pad")
        lp = bool(plc.last_power[r]) if r < len(plc.last_power) else False
        cc = "on" if lp else "off"
        line(("wire_coil", r), W + 1, yc, W + 1.3, yc, "power" if lp else "idle")
        # 线圈 ( )
        line(("coil", r), W + 1.42, top + 0.2, W + 1.32, top + 0.5, cc)
        line(("coil", r), W + 1.32, top + 0.5, W + 1.42, top + 0.8, cc)
        line(("coil", r), W + 1.58, top + 0.2, W + 1.68, top + 0.5, cc)
        line(("coil", r), W + 1.68, top + 0.5, W + 1.58, top + 0.8, cc)
        wire(r, W + 1.7, W + 3, yc, lp, "tail")
        elems.append(Elem("text", ("coil_label", r), W + 1.5, top + 0.1,
                          color="text", text=_coil_text(rung.out)))
        if current_rung == r:
            elems.append(Elem("text", ("marker", r), -0.6, top + 0.5,
                              color="marker", text="▶"))

    return Drawing(elems, W + 3, height, tops)
