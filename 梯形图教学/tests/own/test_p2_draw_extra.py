from plc.model import NO, NC, Series, Parallel, Out, Rung, Program
from plc.engine import PLC
from app.draw import draw_program


def test_reused_contact_instance_does_not_break_trace():
    x = NO("X0")
    p = Program([Rung(Series([x, x]), Out("Y0"))])
    plc = PLC(p)
    plc.set_input("X0", True); plc.scan()
    d = draw_program(p, plc)
    assert {e.color for e in d.elems if e.tag[:3] == ("contact", 0, 1)} == {"on"}
    assert {e.color for e in d.elems if e.tag == ("wire_coil", 0)} == {"power"}


def test_narrow_branch_padded():
    p = Program([Rung(Series([Parallel([NO("X0"), Series([NO("X1"), NO("X2")])]), NC("X3")]), Out("Y0"))])
    d = draw_program(p, PLC(p))
    assert any(e.tag[:3] == ("wire", 0, "pad") for e in d.elems)
