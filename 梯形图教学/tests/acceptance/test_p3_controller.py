"""P3 验收：Controller 接水槽、追加示例、scene_state。禁止修改本文件。"""
import pytest

from plc.model import NO, NC, Series, Parallel, Out, OutT, Rung, Program
from plc.engine import Step
from plc.to_il import to_il
from sim.tank import Tank
from sim.runner import Runner


def fill_to_limit():
    return Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1"), NC("X3")]), Out("Y0"))])


def test_controller_has_tank():
    from app.controller import Controller
    c = Controller(fill_to_limit())
    assert isinstance(c.tank, Tank) and c.tank.level == 0.0 and c.sim_time == 0.0
    t = Tank(level=50.0)
    c2 = Controller(fill_to_limit(), tank=t)
    assert c2.tank is t


def test_controller_matches_runner():
    from app.controller import Controller
    p = fill_to_limit()
    c = Controller(p)
    r = Runner(p)
    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    r.press("X0"); r.run(0.05); r.release("X0")
    for _ in range(30):
        c.update(0.1)
    r.run(3.0)
    assert c.tank.level == pytest.approx(r.tank.level)
    assert c.plc.scan_count == r.plc.scan_count
    assert c.sim_time == pytest.approx(r.time)
    assert 29.0 < c.tank.level < 32.0


def test_controller_reaches_upper_limit():
    from app.controller import Controller
    c = Controller(fill_to_limit())
    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    for _ in range(150):
        c.update(0.1)
    assert 80.0 <= c.tank.level < 81.0
    assert not c.plc.output("Y0") and c.plc.get("X3")


def test_tank_frozen_while_paused():
    from app.controller import Controller
    c = Controller(Program([Rung(NC("X1"), Out("Y0"))]))
    c.update(0.5)
    lvl = c.tank.level
    assert lvl > 0
    c.pause(); c.update(5.0)
    assert c.tank.level == lvl


def test_tank_moves_only_on_output_step():
    from app.controller import Controller
    c = Controller(Program([Rung(NC("X1"), Out("Y0"))]))
    c.pause()
    c.step_scan()                                  # 第 1 轮：Y0 输出刷新后进水
    lvl = c.tank.level
    assert lvl == pytest.approx(0.1)
    assert c.sim_time == pytest.approx(0.01)
    c.step_one(); c.step_one()                     # input, rung0
    assert c.tank.level == pytest.approx(lvl)
    c.step_one()                                   # output
    assert c.tank.level == pytest.approx(lvl + 0.1)


def test_sensors_sampled_at_scan_start():
    from app.controller import Controller
    c = Controller(Program([Rung(NO("X3"), Out("Y2"))]), tank=Tank(level=85.0))
    c.pause()
    s = c.step_one()
    assert s.phase == "input" and c.plc.get("X3") is True and c.plc.get("X2") is True
    c.step_scan()
    assert c.plc.output("Y2") is True


def test_sensors_override_manual_buttons():
    from app.controller import Controller
    c = Controller(Program([Rung(NO("X3"), Out("Y2"))]))
    c.set_button("X3", True)
    c.pause(); c.step_scan()
    assert c.plc.get("X3") is False and c.plc.output("Y2") is False


def test_load_resets_tank_keeps_buttons():
    from app.controller import Controller
    c = Controller(Program([Rung(NC("X1"), Out("Y0"))]))
    c.update(1.0)
    assert c.tank.level > 0
    c.set_button("X0", True)
    old = c.tank
    c.load(Program([Rung(NO("X0"), Out("Y0"))]))
    assert c.tank is not old and c.tank.level == 0.0 and c.sim_time == 0.0
    c.update(0.01)
    assert c.plc.output("Y0") is True


def test_reset_tank():
    from app.controller import Controller
    p = Program([Rung(NC("X1"), Out("Y0"))])
    c = Controller(p)
    c.update(1.0)
    n = c.plc.scan_count
    c.reset_tank()
    assert c.tank.level == 0.0
    assert c.program is p and c.plc.scan_count == n


def test_slow_motion_tank():
    from app.controller import Controller
    c = Controller(Program([Rung(NC("X1"), Out("Y0"))]))   # 每轮 3 步
    c.speed = 0.1
    c.update(0.3)
    assert c.tank.level == pytest.approx(0.1)               # 只完成了 1 轮


def test_new_demos():
    from app.demos import DEMOS
    names = [n for n, _ in DEMOS]
    assert names[:6] == ["自保持", "定时器", "计数器", "双线圈", "给水到上限", "满水后排水"]
    assert to_il(DEMOS[4][1]) == ["LD X0", "OR Y0", "ANI X1", "ANI X3", "OUT Y0", "END"]
    assert to_il(DEMOS[5][1]) == ["LD X3", "OUT T0 K10", "LD T0", "OR M0", "AND X2", "OUT M0",
                                  "LD M0", "OUT Y1", "END"]


def test_scene_state():
    from app.controller import Controller
    from app.scene_state import scene_state
    from app.demos import DEMOS
    c = Controller(DEMOS[5][1], tank=Tank(level=85.0))
    st = scene_state(c)
    assert set(st) == {"level", "inlet_open", "drain_open", "lamp_on", "x2_on", "x3_on",
                       "overflow", "level_text"}
    assert st["level"] == 85.0 and st["level_text"] == "水位 85.0%"
    assert st["drain_open"] is False and st["x3_on"] is False     # 还没扫描过
    c.update(1.2)
    st = scene_state(c)
    assert st["drain_open"] is True and st["inlet_open"] is False
    assert st["x2_on"] is True and st["x3_on"] is True
    assert st["lamp_on"] is False and st["overflow"] is False
    assert st["level"] < 85.0
    assert st["level_text"] == f"水位 {c.tank.level:.1f}%"


def test_scene_state_overflow():
    from app.controller import Controller
    from app.scene_state import scene_state
    from app.demos import DEMOS
    c = Controller(DEMOS[0][1])                 # 自保持，没有上限停
    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    for _ in range(110):
        c.update(0.1)
    st = scene_state(c)
    assert st["level"] == 100.0 and st["overflow"] is True and st["inlet_open"] is True
