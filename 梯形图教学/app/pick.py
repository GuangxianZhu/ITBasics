"""点选：由 Drawing 的坐标做命中测试、生成选中框（纯逻辑）"""
from app.draw import Elem


def _cells(drawing):
    """{('contact',r,k): (x1,y1,x2,y2), ('coil',r): ...}，由 label / coil_label 的位置反推格子"""
    out = {}
    for e in drawing.elems:
        if e.kind != "text":
            continue
        if e.tag[0] == "label":
            out[("contact", e.tag[1], e.tag[2])] = (e.x1 - 0.5, e.y1 - 0.03, e.x1 + 0.5, e.y1 + 0.97)
        elif e.tag[0] == "coil_label":
            out[("coil", e.tag[1])] = (e.x1 - 0.5, e.y1 - 0.03, e.x1 + 0.5, e.y1 + 0.97)
    return out


def hit_test(drawing, gx, gy):
    """网格坐标 → ("contact", r, k) / ("coil", r) / None"""
    for key, (x1, y1, x2, y2) in _cells(drawing).items():
        if x1 <= gx <= x2 and y1 <= gy <= y2:
            return key
    return None


def selection_elems(drawing, sel, sel2_k=None):
    """选中框（黄色 rect）。sel = ("contact", r, k) 或 ("coil", r) 或 None；sel2_k = 跨选的终点触点下标"""
    if sel is None:
        return []
    cells = _cells(drawing)
    if sel not in cells:
        return []
    x1, y1, x2, y2 = cells[sel]
    if sel[0] == "contact" and sel2_k is not None:
        other = cells.get(("contact", sel[1], sel2_k))
        if other:
            x1, y1 = min(x1, other[0]), min(y1, other[1])
            x2, y2 = max(x2, other[2]), max(y2, other[3])
    return [Elem("rect", ("select",), x1 + 0.08, y1 + 0.05, x2 - 0.08, y2 - 0.05, color="marker")]
