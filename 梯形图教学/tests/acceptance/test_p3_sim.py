"""P3 验收：水槽与无界面联动。禁止修改本文件。"""
import pytest

from plc.model import NO, NC, Series, Parallel, Out, OutT, Rung, Program
from sim.tank import Tank
from sim.runner import Runner


def test_tank_fill_drain_clamp():
    t = Tank()
    t.step(1.0, inlet=True, drain=False)
    assert t.level == pytest.approx(10.0)
    t.step(1.0, inlet=True, drain=True)
    assert t.level == pytest.approx(10.0)
    t.step(5.0, inlet=False, drain=True)
    assert t.level == 0.0


def test_tank_sensors():
    t = Tank(level=19.9)
    assert t.sensors() == {"X2": False, "X3": False}
    t = Tank(level=20.0)
    assert t.sensors() == {"X2": True, "X3": False}
    t = Tank(level=80.0)
    assert t.sensors() == {"X2": True, "X3": True}


def test_tank_overflow():
    t = Tank(level=95.0)
    t.step(1.0, inlet=True, drain=False)
    assert t.level == 100.0 and t.overflow
    t.step(1.0, inlet=True, drain=False)
    assert t.overflow
    t.step(0.5, inlet=False, drain=True)
    assert t.level < 100.0 and not t.overflow


def test_tank_custom_params():
    t = Tank(level=50.0, fill_rate=20.0, drain_rate=5.0, low=10.0, high=60.0)
    t.step(1.0, inlet=True, drain=False)
    assert t.level == pytest.approx(70.0)
    assert t.sensors() == {"X2": True, "X3": True}


def selfhold_with_limit():
    # 启动自保持进水，停止或到上限 X3 停
    return Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1"), NC("X3")]), Out("Y0"))])


def test_runner_time_and_tick():
    r = Runner(Program([]))
    assert r.time == 0.0 and r.tank.level == 0.0
    r.tick()
    assert r.time == pytest.approx(0.01)
    r.run(1.0)
    assert r.time == pytest.approx(1.01)
    assert r.plc.scan_count == 101


def test_runner_selfhold_fill_and_stop():
    r = Runner(selfhold_with_limit())
    r.press("X0"); r.run(0.05); r.release("X0")
    r.run(3.0)
    assert 29.0 < r.tank.level < 32.0
    r.press("X1"); r.run(0.05); r.release("X1")
    lvl = r.tank.level
    r.run(2.0)
    assert r.tank.level == pytest.approx(lvl)
    assert not r.plc.output("Y0")


def test_runner_upper_limit_stops_fill():
    r = Runner(selfhold_with_limit())
    r.press("X0"); r.run(0.05); r.release("X0")
    r.run(15.0)
    assert 80.0 <= r.tank.level < 81.0
    assert not r.tank.overflow and not r.plc.output("Y0")


def test_runner_uses_given_tank():
    t = Tank(level=50.0)
    r = Runner(Program([Rung(NO("X2"), Out("Y1"))]), tank=t)
    assert r.tank is t
    r.run(1.0)
    assert r.tank.level < 50.0


def test_runner_timer_drain_cycle():
    # 满了(X3)等 1 秒后排水，排到下限以下停（用 M0 记住"正在排水"）
    p = Program([
        Rung(NO("X3"), OutT("T0", 10)),
        Rung(Series([Parallel([NO("T0"), NO("M0")]), NO("X2")]), Out("M0")),
        Rung(NO("M0"), Out("Y1")),
    ])
    r = Runner(p, tank=Tank(level=85.0))
    r.run(0.9)
    assert r.tank.level == pytest.approx(85.0)
    r.run(0.3)
    assert r.tank.level < 85.0
    r.run(10.0)
    assert 19.0 < r.tank.level < 20.0
    assert not r.plc.output("Y1")
