"""P1 验收：网格布局。禁止修改本文件。"""
from plc.model import NO, NC, Series, Parallel
from plc.layout import layout


def pos(lay):
    return [(c.addr, c.nc, col, row) for c, col, row in lay.cells]


def test_single():
    lay = layout(NO("X0"))
    assert (lay.width, lay.height) == (1, 1)
    assert pos(lay) == [("X0", False, 0, 0)]


def test_series():
    lay = layout(Series([NO("X0"), NC("X1"), NO("X2")]))
    assert (lay.width, lay.height) == (3, 1)
    assert pos(lay) == [("X0", False, 0, 0), ("X1", True, 1, 0), ("X2", False, 2, 0)]


def test_parallel():
    lay = layout(Parallel([NO("X0"), NO("Y0")]))
    assert (lay.width, lay.height) == (1, 2)
    assert pos(lay) == [("X0", False, 0, 0), ("Y0", False, 0, 1)]


def test_selfhold():
    lay = layout(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]))
    assert (lay.width, lay.height) == (2, 2)
    assert pos(lay) == [("X0", False, 0, 0), ("Y0", False, 0, 1), ("X1", True, 1, 0)]


def test_uneven_parallel():
    lay = layout(Parallel([Series([NO("X0"), NO("X1")]), NO("X2")]))
    assert (lay.width, lay.height) == (2, 2)
    assert pos(lay) == [("X0", False, 0, 0), ("X1", False, 1, 0), ("X2", False, 0, 1)]


def test_nested():
    tree = Series([NO("X0"),
                   Parallel([Series([NO("X1"), NO("X2")]),
                             Parallel([NO("X3"), NO("X4")])]),
                   NO("X5")])
    lay = layout(tree)
    assert (lay.width, lay.height) == (4, 3)
    assert pos(lay) == [("X0", False, 0, 0),
                        ("X1", False, 1, 0), ("X2", False, 2, 0),
                        ("X3", False, 1, 1), ("X4", False, 1, 2),
                        ("X5", False, 3, 0)]


def test_layout_normalizes():
    lay = layout(Series([Series([NO("X0")]), NO("X1")]))
    assert (lay.width, lay.height) == (2, 1)
