"""P5 验收：编辑操作与撤销。禁止修改本文件。"""
import copy

import pytest

from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program
from plc.to_il import to_il


def one():
    return Program([Rung(NO("X0"), Out("Y0"))])


def selfhold():
    return Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0"))])


def il(p):
    return to_il(p)[:-1]          # 去掉 END


def test_build_selfhold_from_scratch():
    from app.editor import append_series, add_parallel
    p = one()
    append_series(p, 0, NC("X1"))
    assert il(p) == ["LD X0", "ANI X1", "OUT Y0"]
    add_parallel(p, 0, 0, NO("Y0"))
    assert il(p) == ["LD X0", "OR Y0", "ANI X1", "OUT Y0"]


def test_contact_at():
    from app.editor import contact_at, EditError
    p = selfhold()
    assert contact_at(p, 0, 0) == NO("X0")
    assert contact_at(p, 0, 1) == NO("Y0")
    assert contact_at(p, 0, 2) == NC("X1")
    with pytest.raises(EditError):
        contact_at(p, 0, 3)
    with pytest.raises(EditError):
        contact_at(p, 1, 0)


def test_insert_series_after_inside_branch():
    from app.editor import insert_series
    p = selfhold()
    insert_series(p, 0, 1, NO("M0"), after=True)          # Y0 支路变成 Y0-M0
    assert il(p) == ["LD X0", "LD Y0", "AND M0", "ORB", "ANI X1", "OUT Y0"]


def test_insert_series_before_single():
    from app.editor import insert_series
    p = one()
    insert_series(p, 0, 0, NC("X5"), after=False)
    assert il(p) == ["LDI X5", "AND X0", "OUT Y0"]


def test_insert_series_after_in_series():
    from app.editor import insert_series
    p = selfhold()
    insert_series(p, 0, 2, NC("X3"))                      # X1 后面加 X3 → 第 4 关参考答案
    assert il(p) == ["LD X0", "OR Y0", "ANI X1", "ANI X3", "OUT Y0"]


def test_add_parallel_span():
    from app.editor import add_parallel
    p = Program([Rung(Series([NO("X0"), NO("X1"), NO("X2")]), Out("Y0"))])
    add_parallel(p, 0, 0, NO("M0"), k2=1)
    assert il(p) == ["LD X0", "AND X1", "OR M0", "AND X2", "OUT Y0"]


def test_add_parallel_to_branch_adds_branch():
    from app.editor import add_parallel
    p = selfhold()
    add_parallel(p, 0, 1, NO("M1"))                       # Y0 是并联支路 → 多一条支路
    assert il(p) == ["LD X0", "OR Y0", "OR M1", "ANI X1", "OUT Y0"]


def test_add_parallel_invalid_span():
    from app.editor import add_parallel, EditError
    p = selfhold()
    before = il(p)
    with pytest.raises(EditError):
        add_parallel(p, 0, 0, NO("M0"), k2=2)             # X0 和 X1 不是同一串联里的兄弟
    with pytest.raises(EditError):
        add_parallel(p, 0, 2, NO("M0"), k2=1)             # k1 > k2
    assert il(p) == before


def test_delete_contact():
    from app.editor import delete_contact, EditError
    p = selfhold()
    delete_contact(p, 0, 1)
    assert il(p) == ["LD X0", "ANI X1", "OUT Y0"]
    delete_contact(p, 0, 0)
    assert il(p) == ["LDI X1", "OUT Y0"]
    with pytest.raises(EditError):
        delete_contact(p, 0, 0)
    assert il(p) == ["LDI X1", "OUT Y0"]


def test_set_contact():
    from app.editor import set_contact, EditError
    p = one()
    set_contact(p, 0, 0, addr="M3")
    assert il(p) == ["LD M3", "OUT Y0"]
    set_contact(p, 0, 0, nc=True)
    assert il(p) == ["LDI M3", "OUT Y0"]
    for bad in ["Z9", "X", "Y-1", "XX1", ""]:
        with pytest.raises(EditError):
            set_contact(p, 0, 0, addr=bad)
    assert il(p) == ["LDI M3", "OUT Y0"]


def test_insert_bad_address_is_atomic():
    from app.editor import insert_series, append_series, add_parallel, EditError
    p = selfhold()
    before = copy.deepcopy(p)
    for op in (lambda: insert_series(p, 0, 0, NO("Q1")),
               lambda: append_series(p, 0, NO("Q1")),
               lambda: add_parallel(p, 0, 0, NO("Q1"))):
        with pytest.raises(EditError):
            op()
    assert to_il(p) == to_il(before)


def test_rung_ops():
    from app.editor import add_rung, delete_rung, move_rung, EditError
    p = one()
    add_rung(p)
    assert il(p) == ["LD X0", "OUT Y0", "LD X0", "OUT Y0"]
    add_rung(p, 0, Rung(NO("X1"), Out("Y1")))
    assert il(p)[:2] == ["LD X1", "OUT Y1"] and len(p.rungs) == 3
    move_rung(p, 0, 1)
    assert il(p)[:4] == ["LD X0", "OUT Y0", "LD X1", "OUT Y1"]
    with pytest.raises(EditError):
        move_rung(p, 0, -1)
    with pytest.raises(EditError):
        move_rung(p, 2, 1)
    delete_rung(p, 1)
    assert il(p) == ["LD X0", "OUT Y0", "LD X0", "OUT Y0"]
    with pytest.raises(EditError):
        delete_rung(p, 5)


def test_set_output():
    from app.editor import set_output, EditError
    p = one()
    set_output(p, 0, OutT("T0", 50))
    assert il(p) == ["LD X0", "OUT T0 K50"]
    set_output(p, 0, Rst("C1"))
    assert il(p) == ["LD X0", "RST C1"]
    for bad in (Out("X0"), Out("T0"), OutT("C0", 5), OutT("T0", 0), OutC("T1", 3), OutC("C1", 0), Rst("Y0")):
        with pytest.raises(EditError):
            set_output(p, 0, bad)
    assert il(p) == ["LD X0", "RST C1"]


def test_ops_keep_normalized():
    from app.editor import insert_series, delete_contact
    from plc.model import normalize
    p = selfhold()
    insert_series(p, 0, 0, NO("M5"))
    delete_contact(p, 0, 1)
    c = p.rungs[0].cond
    assert normalize(c) == c


def test_history():
    from app.editor import History, append_series, set_contact, EditError
    h = History(one())
    assert h.undo() is False and h.redo() is False
    h.apply(append_series, 0, NC("X1"))
    h.apply(set_contact, 0, 0, addr="X2")
    assert il(h.program) == ["LD X2", "ANI X1", "OUT Y0"]
    assert h.undo() is True
    assert il(h.program) == ["LD X0", "ANI X1", "OUT Y0"]
    assert h.undo() is True
    assert il(h.program) == ["LD X0", "OUT Y0"]
    assert h.undo() is False
    assert h.redo() is True
    assert il(h.program) == ["LD X0", "ANI X1", "OUT Y0"]
    h.apply(set_contact, 0, 1, nc=False)                  # 新操作清空 redo
    assert h.redo() is False
    assert il(h.program) == ["LD X0", "AND X1", "OUT Y0"]
    with pytest.raises(EditError):
        h.apply(set_contact, 0, 0, addr="Z1")
    assert il(h.program) == ["LD X0", "AND X1", "OUT Y0"]
    assert h.undo() is True
    assert il(h.program) == ["LD X0", "ANI X1", "OUT Y0"]   # 失败的那次没进历史
