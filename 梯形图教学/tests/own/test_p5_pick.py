from plc.model import NO, NC, Series, Parallel, Out, Rung, Program
from plc.engine import PLC
from app.draw import draw_program
from app.pick import hit_test, selection_elems


def sh():
    return Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0"))])


def test_hit_test_contacts_and_coil():
    p = sh()
    d = draw_program(p, PLC(p))
    assert hit_test(d, 1.5, 0.5) == ("contact", 0, 0)
    assert hit_test(d, 1.5, 1.5) == ("contact", 0, 1)
    assert hit_test(d, 2.5, 0.5) == ("contact", 0, 2)
    assert hit_test(d, 3.5, 0.5) == ("coil", 0)
    assert hit_test(d, 3.5, 1.5) is None
    assert hit_test(d, -2, 0.5) is None


def test_selection_rect_and_span():
    p = sh()
    d = draw_program(p, PLC(p))
    [e] = selection_elems(d, ("contact", 0, 2))
    assert e.kind == "rect" and e.color == "marker" and 2 <= e.x1 < e.x2 <= 3
    [s] = selection_elems(d, ("contact", 0, 0), sel2_k=2)
    assert s.x1 < 2 and s.x2 > 2
    assert selection_elems(d, None) == []
    assert selection_elems(d, ("contact", 5, 0)) == []


def test_hit_in_second_rung():
    p = Program([Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y1"))])
    d = draw_program(p, PLC(p))
    assert hit_test(d, 1.5, 2.5) == ("contact", 1, 0)
