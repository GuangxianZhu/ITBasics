"""P1 验收：梯形图 → 指令表。禁止修改本文件。"""
from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program
from plc.to_il import to_il


def il(cond, out=None):
    return to_il(Program([Rung(cond, out or Out("Y0"))]))


def test_single_contact():
    assert il(NO("X0")) == ["LD X0", "OUT Y0", "END"]
    assert il(NC("X0")) == ["LDI X0", "OUT Y0", "END"]


def test_series():
    assert il(Series([NO("X0"), NC("X1"), NO("M0")])) == \
        ["LD X0", "ANI X1", "AND M0", "OUT Y0", "END"]


def test_parallel():
    assert il(Parallel([NO("X0"), NC("X1"), NO("Y0")])) == \
        ["LD X0", "ORI X1", "OR Y0", "OUT Y0", "END"]


def test_selfhold():
    assert il(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")])) == \
        ["LD X0", "OR Y0", "ANI X1", "OUT Y0", "END"]


def test_anb():
    assert il(Series([NO("X0"), Parallel([NO("X1"), NO("X2")])])) == \
        ["LD X0", "LD X1", "OR X2", "ANB", "OUT Y0", "END"]


def test_orb():
    assert il(Parallel([NO("X0"), Series([NO("X1"), NC("X2")])])) == \
        ["LD X0", "LD X1", "ANI X2", "ORB", "OUT Y0", "END"]


def test_orb_two_series():
    assert il(Parallel([Series([NO("X0"), NO("X1")]), Series([NO("X2"), NO("X3")])])) == \
        ["LD X0", "AND X1", "LD X2", "AND X3", "ORB", "OUT Y0", "END"]


def test_nested():
    tree = Series([Parallel([NO("X0"), Series([NO("X1"), NO("X2")])]), NO("X3")])
    assert il(tree) == ["LD X0", "LD X1", "AND X2", "ORB", "AND X3", "OUT Y0", "END"]


def test_anb_of_two_parallels():
    tree = Series([Parallel([NO("X0"), NO("X1")]), Parallel([NO("X2"), NC("X3")])])
    assert il(tree) == ["LD X0", "OR X1", "LD X2", "ORI X3", "ANB", "OUT Y0", "END"]


def test_normalizes_first():
    tree = Series([Series([NO("X0")]), Series([NC("X1")])])
    assert il(tree) == ["LD X0", "ANI X1", "OUT Y0", "END"]


def test_outputs():
    assert il(NO("X0"), OutT("T0", 50)) == ["LD X0", "OUT T0 K50", "END"]
    assert il(NO("X0"), OutC("C1", 3)) == ["LD X0", "OUT C1 K3", "END"]
    assert il(NO("X0"), Rst("C1")) == ["LD X0", "RST C1", "END"]
    assert il(NO("X0"), Out("M2")) == ["LD X0", "OUT M2", "END"]


def test_multi_rung_and_empty():
    p = Program([Rung(NO("X0"), Out("M0")), Rung(NC("M0"), Out("Y1"))])
    assert to_il(p) == ["LD X0", "OUT M0", "LDI M0", "OUT Y1", "END"]
    assert to_il(Program([])) == ["END"]


def test_to_il_rungs_for_highlight():
    from plc.to_il import to_il_rungs
    p = Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0")),
                 Rung(NO("Y0"), OutT("T0", 50))])
    assert to_il_rungs(p) == [["LD X0", "OR Y0", "ANI X1", "OUT Y0"],
                              ["LD Y0", "OUT T0 K50"]]
