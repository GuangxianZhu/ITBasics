from ui.layout import Layout, MIN_W, MIN_H


def _ok(r):
    l, rr, b, t = r
    return rr > l and t > b


def test_rects_valid_and_disjoint():
    for aspect in (1.33, 16 / 9, 2.4):
        lay = Layout()
        rs = lay.rects(aspect)
        for k, r in rs.items():
            assert _ok(r), (aspect, k, r)
        assert rs["ladder"][1] < rs["tank"][0]
        assert rs["il"][1] < rs["mon"][0]
        assert rs["il"][3] < rs["ladder"][2]
        for k in ("ladder", "il", "mon", "tank"):
            l, r, b, t = rs[k]
            assert -aspect <= l and r <= aspect and -1 <= b and t <= 1


def test_drag_and_minimums():
    lay = Layout()
    a = 16 / 9
    lay.drag("split_x", 10, 0, a)            # 拖到最右也要给水槽留最小宽度
    rs = lay.rects(a)
    assert rs["tank"][1] - rs["tank"][0] >= MIN_W - 1e-6
    lay.drag("split_y", 0, -10, a)
    rs = lay.rects(a)
    assert rs["il"][3] - rs["il"][2] >= MIN_H - 1e-6
    lay.drag("split_t", -10, 0, a)
    rs = lay.rects(a)
    assert rs["il"][1] - rs["il"][0] > 0.2


def test_drag_moves_split():
    lay = Layout()
    a = 16 / 9
    x0 = lay.rects(a)["split_x"][0]
    lay.drag("split_x", 0.0, 0, a)
    assert abs(lay.rects(a)["split_x"][0] + 0.0125) < 1e-6 and lay.rects(a)["split_x"][0] != x0
