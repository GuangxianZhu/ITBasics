"""P1 验收：扫描引擎。禁止修改本文件。"""
import pytest

from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program, Contact, normalize
from plc.engine import PLC, evaluate, Step


def prog(*rungs):
    return Program(list(rungs))


def selfhold():
    # LD X0 / OR Y0 / ANI X1 / OUT Y0
    return prog(Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0")))


# ---------- model ----------

def test_normalize_flatten_and_collapse():
    a, b, c = NO("X0"), NO("X1"), NO("X2")
    assert normalize(Series([a, Series([b, c])])) == Series([a, b, c])
    assert normalize(Parallel([Parallel([a, b]), c])) == Parallel([a, b, c])
    assert normalize(Series([a])) == a
    assert normalize(Series([Parallel([a])])) == a


def test_normalize_does_not_mutate():
    inner = Series([NO("X1"), NO("X2")])
    tree = Series([NO("X0"), inner])
    normalize(tree)
    assert len(tree.items) == 2 and tree.items[1] is inner


def test_normalize_empty_raises():
    with pytest.raises(ValueError):
        normalize(Series([]))


def test_bad_address_raises():
    with pytest.raises(ValueError):
        PLC(prog(Rung(NO("Z0"), Out("Y0"))))
    with pytest.raises(ValueError):
        PLC(prog(Rung(NO("X0"), Out("YY"))))


# ---------- 基本 ----------

def test_initial_state():
    plc = PLC(selfhold())
    assert plc.get("Y0") is False and plc.output("Y0") is False
    assert plc.get("M5") is False and plc.timer_ms("T0") == 0 and plc.counter_value("C0") == 0
    assert plc.scan_count == 0 and plc.last_power == [False]


def test_simple_coil():
    plc = PLC(prog(Rung(NO("X0"), Out("Y0"))))
    plc.set_input("X0", True)
    assert plc.output("Y0") is False          # 还没扫描
    plc.scan()
    assert plc.output("Y0") is True and plc.get("Y0") is True
    assert plc.scan_count == 1 and plc.last_power == [True]


def test_nc_contact_on_unwritten_device():
    plc = PLC(prog(Rung(NC("M0"), Out("Y1"))))
    plc.scan()
    assert plc.output("Y1") is True


def test_input_sampled_only_at_input_phase():
    plc = PLC(prog(Rung(NO("X0"), Out("Y0"))))
    plc.set_input("X0", True)
    it = plc.steps()
    s = next(it)
    assert s == Step("input", None, None)
    plc.set_input("X0", False)                # 采样之后才变化，本轮不受影响
    for _ in it:
        pass
    assert plc.output("Y0") is True
    plc.scan()
    assert plc.output("Y0") is False


def test_output_refreshed_only_at_output_phase():
    plc = PLC(prog(Rung(NO("X0"), Out("Y0"))))
    plc.set_input("X0", True)
    steps = []
    it = plc.steps()
    steps.append(next(it))                    # input
    steps.append(next(it))                    # rung 0
    assert steps[-1] == Step("rung", 0, True)
    assert plc.get("Y0") is True              # 映像已变
    assert plc.output("Y0") is False          # 端子还没变
    steps.append(next(it))                    # output
    assert steps[-1] == Step("output", None, None)
    assert plc.output("Y0") is True
    with pytest.raises(StopIteration):
        next(it)


def test_steps_sequence():
    p = prog(Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y1")), Rung(NC("X1"), Out("Y2")))
    plc = PLC(p)
    plc.set_input("X0", True)
    got = list(plc.steps())
    assert got == [
        Step("input", None, None),
        Step("rung", 0, True),
        Step("rung", 1, False),
        Step("rung", 2, True),
        Step("output", None, None),
    ]
    assert plc.last_power == [True, False, True]


# ---------- 自保持 ----------

def test_selfhold():
    plc = PLC(selfhold())
    plc.set_input("X0", True); plc.scan()
    assert plc.output("Y0")
    plc.set_input("X0", False); plc.scan(); plc.scan()
    assert plc.output("Y0")                   # 松开启动仍保持
    plc.set_input("X1", True); plc.scan()
    assert not plc.output("Y0")               # 停止
    plc.set_input("X1", False); plc.scan()
    assert not plc.output("Y0")               # 松开停止不会自己恢复


def test_selfhold_stop_wins_when_both_pressed():
    plc = PLC(selfhold())
    plc.set_input("X0", True); plc.set_input("X1", True); plc.scan()
    assert not plc.output("Y0")


# ---------- 扫描顺序 / 双线圈 ----------

def test_same_scan_propagation_forward():
    plc = PLC(prog(Rung(NO("X0"), Out("M0")), Rung(NO("M0"), Out("Y0"))))
    plc.set_input("X0", True); plc.scan()
    assert plc.output("Y0")


def test_propagation_backward_needs_two_scans():
    plc = PLC(prog(Rung(NO("M0"), Out("Y0")), Rung(NO("X0"), Out("M0"))))
    plc.set_input("X0", True); plc.scan()
    assert not plc.output("Y0")
    plc.scan()
    assert plc.output("Y0")


def test_double_coil_last_wins():
    plc = PLC(prog(Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y0"))))
    plc.set_input("X0", True)
    it = plc.steps()
    next(it); next(it)                        # input, rung0
    assert plc.get("Y0") is True              # 第 1 行写了 ON
    for _ in it:
        pass
    assert plc.output("Y0") is False          # 第 2 行写 OFF，最后一行说了算


# ---------- 定时器 ----------

def timer_prog():
    return prog(Rung(NO("X0"), OutT("T0", 5)),     # 0.5 秒
                Rung(NO("T0"), Out("Y0")))


def test_timer_reaches_exactly():
    plc = PLC(timer_prog(), scan_ms=10)
    plc.set_input("X0", True)
    for _ in range(49):
        plc.scan()
    assert plc.timer_ms("T0") == 490
    assert not plc.get("T0") and not plc.output("Y0")
    plc.scan()
    assert plc.timer_ms("T0") == 500
    assert plc.get("T0") and plc.output("Y0")      # 同一轮后面的行就能看到


def test_timer_caps_and_resets_when_unpowered():
    plc = PLC(timer_prog(), scan_ms=10)
    plc.set_input("X0", True)
    for _ in range(100):
        plc.scan()
    assert plc.timer_ms("T0") == 500 and plc.get("T0")
    plc.set_input("X0", False); plc.scan()
    assert plc.timer_ms("T0") == 0 and not plc.get("T0") and not plc.output("Y0")


def test_timer_scan_ms_parameter():
    plc = PLC(timer_prog(), scan_ms=100)
    plc.set_input("X0", True)
    for _ in range(4):
        plc.scan()
    assert not plc.get("T0")
    plc.scan()
    assert plc.get("T0")


def test_rst_timer():
    p = prog(Rung(NO("X0"), OutT("T0", 100)), Rung(NO("X1"), Rst("T0")))
    plc = PLC(p, scan_ms=10)
    plc.set_input("X0", True)
    for _ in range(10):
        plc.scan()
    assert plc.timer_ms("T0") == 100
    plc.set_input("X1", True); plc.scan()
    assert plc.timer_ms("T0") == 0


# ---------- 计数器 ----------

def counter_prog():
    return prog(Rung(NO("X0"), OutC("C0", 3)),
                Rung(NO("X1"), Rst("C0")),
                Rung(NO("C0"), Out("Y0")))


def pulse(plc, addr, hold_scans=3):
    plc.set_input(addr, True)
    for _ in range(hold_scans):
        plc.scan()
    plc.set_input(addr, False)
    plc.scan()


def test_counter_counts_rising_edges_only():
    plc = PLC(counter_prog())
    pulse(plc, "X0", hold_scans=10)
    assert plc.counter_value("C0") == 1
    pulse(plc, "X0")
    assert plc.counter_value("C0") == 2 and not plc.output("Y0")
    pulse(plc, "X0")
    assert plc.counter_value("C0") == 3 and plc.get("C0") and plc.output("Y0")


def test_counter_stops_at_k_and_holds():
    plc = PLC(counter_prog())
    for _ in range(5):
        pulse(plc, "X0")
    assert plc.counter_value("C0") == 3 and plc.output("Y0")


def test_counter_reset():
    plc = PLC(counter_prog())
    for _ in range(3):
        pulse(plc, "X0")
    pulse(plc, "X1")
    assert plc.counter_value("C0") == 0 and not plc.get("C0") and not plc.output("Y0")
    pulse(plc, "X0")
    assert plc.counter_value("C0") == 1


def test_counter_first_scan_already_on_counts():
    plc = PLC(counter_prog())
    plc.set_input("X0", True); plc.scan()
    assert plc.counter_value("C0") == 1


# ---------- evaluate / trace ----------

def test_evaluate_basic():
    state = {"X0": False, "X1": True, "X2": True}
    read = lambda a: state.get(a, False)
    tree = Series([Parallel([NO("X0"), NO("X1")]), NC("X2")])
    assert evaluate(tree, read) is False
    state["X2"] = False
    assert evaluate(tree, read) is True


def test_evaluate_trace():
    x0, x1, x2 = NO("X0"), NO("X1"), NC("X2")
    par = Parallel([x0, x1])
    tree = Series([par, x2])
    state = {"X0": False, "X1": True, "X2": True}
    trace = {}
    assert evaluate(tree, lambda a: state.get(a, False), trace) is False
    assert trace[id(x0)] is False
    assert trace[id(x1)] is True
    assert trace[id(par)] is True
    assert trace[id(x2)] is False          # 左端有电，但 b接点被打开
    assert trace[id(tree)] is False


def test_evaluate_trace_no_power_downstream():
    a, b = NO("X0"), NO("X1")
    tree = Series([a, b])
    trace = {}
    evaluate(tree, lambda addr: addr == "X1", trace)
    assert trace[id(a)] is False
    assert trace[id(b)] is False           # 自身导通但左边没电
