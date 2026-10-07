from app.level_session import LevelSession
from plc.to_il import to_il


def test_flow():
    s = LevelSession()
    p = s.enter(3)
    assert s.level.ID == 4 and to_il(p) == to_il(s.level.EXAMPLE) and p is not s.level.EXAMPLE
    assert s.judge()[0] is False and 4 not in s.passed
    s.load_solution()
    assert s.judge() == (True, "通过！") and 4 in s.passed
    s.restore_example()
    assert to_il(s.program) == to_il(s.level.EXAMPLE)
    assert s.has_next()


def test_quiz():
    s = LevelSession()
    s.enter(4)
    assert s.answer(0)[0] is False and 5 not in s.passed
    assert s.answer(s.level.ANSWER) == (True, "回答正确！") and 5 in s.passed


def test_last_level():
    s = LevelSession()
    s.enter(7)
    assert not s.has_next()
    s.leave()
    assert s.level is None and s.program is None
