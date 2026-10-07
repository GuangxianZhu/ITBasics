"""P4 验收：关卡数据与判定。禁止修改本文件。"""
import pytest

from plc.model import Program
from plc.to_il import to_il
from plc.engine import PLC


def load():
    from levels import ALL_LEVELS
    return ALL_LEVELS


def test_eight_levels_in_order():
    levels = load()
    assert [lv.ID for lv in levels] == list(range(1, 9))


def test_level5_is_quiz_others_are_tasks():
    kinds = {lv.ID: lv.KIND for lv in load()}
    assert kinds[5] == "quiz"
    assert all(kinds[i] == "task" for i in kinds if i != 5)


@pytest.mark.parametrize("idx", range(8))
def test_common_fields(idx):
    lv = load()[idx]
    assert isinstance(lv.TITLE, str) and lv.TITLE.strip()
    assert isinstance(lv.INTRO, str) and lv.INTRO.strip()
    assert isinstance(lv.EXAMPLE, Program)
    to_il(lv.EXAMPLE)
    PLC(lv.EXAMPLE)                      # 地址合法


@pytest.mark.parametrize("idx", [i for i in range(8) if i != 4])
def test_task_level(idx):
    lv = load()[idx]
    assert isinstance(lv.TASK, str) and lv.TASK.strip()
    assert isinstance(lv.SOLUTION, Program)
    PLC(lv.SOLUTION)
    ok, msg = lv.check(lv.SOLUTION)
    assert ok is True, f"第{lv.ID}关参考答案没通过: {msg}"
    assert isinstance(msg, str)
    ok, msg = lv.check(lv.EXAMPLE)
    assert ok is False, f"第{lv.ID}关示例程序不该直接通过"
    assert isinstance(msg, str) and msg.strip()
    ok, _ = lv.check(Program([]))
    assert ok is False


def test_quiz_level():
    lv = load()[4]
    assert isinstance(lv.QUESTION, str) and lv.QUESTION.strip()
    assert isinstance(lv.CHOICES, list) and len(lv.CHOICES) >= 2
    assert isinstance(lv.ANSWER, int) and 0 <= lv.ANSWER < len(lv.CHOICES)


def test_quiz_level_example_has_double_coil():
    lv = load()[4]
    coils = [r.out.addr for r in lv.EXAMPLE.rungs if type(r.out).__name__ == "Out"]
    assert len(coils) != len(set(coils)), "第5关示例应包含双线圈"


def test_level8_example_incomplete():
    lv = load()[7]
    assert len(lv.EXAMPLE.rungs) < len(lv.SOLUTION.rungs)


def test_check_does_not_mutate_program():
    lv = load()[3]
    before = to_il(lv.SOLUTION)
    lv.check(lv.SOLUTION)
    assert to_il(lv.SOLUTION) == before
