"""P2 验收：app/ 层（绘图元素、运行控制、表格）。禁止修改本文件。"""
import pytest

from plc.model import NO, NC, Series, Parallel, Out, OutT, OutC, Rst, Rung, Program
from plc.engine import PLC, Step


def selfhold():
    return Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0"))])


def by_tag(d, *prefix):
    return [e for e in d.elems if e.tag[:len(prefix)] == prefix]


# ======================= app.draw =======================

def test_app_does_not_import_panda3d():
    import subprocess, sys, os
    code = ("import sys, app.draw, app.controller, app.views, app.demos;"
            "sys.exit(1 if any(m.split('.')[0]=='panda3d' for m in sys.modules) else 0)")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert subprocess.run([sys.executable, "-c", code], cwd=root).returncode == 0


def test_draw_geometry_selfhold():
    from app.draw import draw_program
    p = selfhold()
    d = draw_program(p, PLC(p))
    # W = 2, 线圈在 [3,4]，右母线 x=5
    assert d.width == 5 and d.height == 2 and d.rung_top == [0]
    expect = {0: (0, 0), 1: (0, 1), 2: (1, 0)}     # k -> (col,row)
    for k, (col, row) in expect.items():
        es = by_tag(d, "contact", 0, k)
        assert es, f"缺少 contact 0 {k}"
        for e in es:
            xs = [e.x1, e.x2] if e.kind != "text" else [e.x1]
            ys = [e.y1, e.y2] if e.kind != "text" else [e.y1]
            assert all(col + 1 - 1e-6 <= x <= col + 2 + 1e-6 for x in xs)
            assert all(row - 1e-6 <= y <= row + 1 + 1e-6 for y in ys)
    for e in by_tag(d, "coil", 0):
        assert 3 - 1e-6 <= min(e.x1, e.x2) and max(e.x1, e.x2) <= 4 + 1e-6
    rr = by_tag(d, "rail_right")
    assert rr and all(e.x1 == 5 and e.x2 == 5 for e in rr)
    rl = by_tag(d, "rail_left")
    assert rl and all(e.x1 == 0 and e.x2 == 0 for e in rl)


def test_draw_labels():
    from app.draw import draw_program
    p = Program([Rung(Series([NO("X0"), NC("M3")]), OutT("T0", 50)),
                 Rung(NO("X1"), Rst("C0"))])
    d = draw_program(p, PLC(p))
    assert [e.text for e in by_tag(d, "label", 0, 0)] == ["X0"]
    assert [e.text for e in by_tag(d, "label", 0, 1)] == ["M3"]
    assert [e.text for e in by_tag(d, "coil_label", 0)] == ["T0 K50"]
    assert [e.text for e in by_tag(d, "coil_label", 1)] == ["RST C0"]
    assert all(e.kind == "text" and e.color == "text" for e in by_tag(d, "label"))


def test_draw_multi_rung_layout_and_coil_alignment():
    from app.draw import draw_program
    p = Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0")),   # 2x2
                 Rung(Series([NO("X0"), NO("X1"), NO("X2")]), Out("Y1")),              # 3x1
                 Rung(NO("X3"), Out("Y2"))])                                           # 1x1
    d = draw_program(p, PLC(p))
    assert d.rung_top == [0, 3, 5]
    assert d.width == 6 and d.height == 6
    for r in range(3):
        es = by_tag(d, "coil", r)
        assert es
        assert all(4 - 1e-6 <= min(e.x1, e.x2) and max(e.x1, e.x2) <= 5 + 1e-6 for e in es)
        top = d.rung_top[r]
        assert all(top - 1e-6 <= min(e.y1, e.y2) and max(e.y1, e.y2) <= top + 1 + 1e-6 for e in es)
    # 第 2 行第 0 个触点在 y ∈ [5,6]
    for e in by_tag(d, "contact", 2, 0):
        assert 5 - 1e-6 <= min(e.y1, e.y2) and max(e.y1, e.y2) <= 6 + 1e-6


def test_draw_empty_program():
    from app.draw import draw_program
    p = Program([])
    d = draw_program(p, PLC(p))
    assert d.rung_top == [] and d.height == 0


def colors(d, *prefix):
    return {e.color for e in by_tag(d, *prefix)}


def test_draw_colors_selfhold_states():
    from app.draw import draw_program
    p = selfhold()
    plc = PLC(p)
    plc.scan()
    d = draw_program(p, plc)
    assert colors(d, "contact", 0, 0) == {"off"}       # X0 常开，OFF
    assert colors(d, "contact", 0, 1) == {"off"}       # Y0 常开，OFF
    assert colors(d, "contact", 0, 2) == {"on"}        # X1 常闭，X1 OFF → 导通
    assert colors(d, "coil", 0) == {"off"}
    assert colors(d, "wire_coil", 0) == {"idle"}
    assert colors(d, "rail_left") == {"rail"}

    plc.set_input("X0", True); plc.scan()
    plc.set_input("X0", False); plc.scan()
    d = draw_program(p, plc)
    assert colors(d, "contact", 0, 0) == {"off"}
    assert colors(d, "contact", 0, 1) == {"on"}
    assert colors(d, "coil", 0) == {"on"}
    assert colors(d, "wire_coil", 0) == {"power"}
    assert "power" in colors(d, "wire", 0)

    plc.set_input("X1", True); plc.scan()
    d = draw_program(p, plc)
    assert colors(d, "contact", 0, 2) == {"off"}       # 常闭被按开
    assert colors(d, "coil", 0) == {"off"}
    assert colors(d, "wire_coil", 0) == {"idle"}


def test_draw_contact_on_without_power():
    # 触点颜色只看自身是否导通，不看左边有没有电
    from app.draw import draw_program
    p = Program([Rung(Series([NO("X0"), NO("X1")]), Out("Y0"))])
    plc = PLC(p)
    plc.set_input("X1", True); plc.scan()
    d = draw_program(p, plc)
    assert colors(d, "contact", 0, 0) == {"off"}
    assert colors(d, "contact", 0, 1) == {"on"}
    assert colors(d, "wire_coil", 0) == {"idle"}


def test_draw_marker():
    from app.draw import draw_program
    p = Program([Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y1"))])
    plc = PLC(p)
    assert by_tag(draw_program(p, plc), "marker") == []
    d = draw_program(p, plc, current_rung=1)
    ms = by_tag(d, "marker")
    assert len(ms) == 1 and ms[0].tag == ("marker", 1)
    assert ms[0].kind == "text" and ms[0].text == "▶" and ms[0].color == "marker"
    assert ms[0].x1 < 0
    assert d.rung_top[1] - 1e-6 <= ms[0].y1 <= d.rung_top[1] + 1 + 1e-6


def test_all_elements_have_known_kind_and_color():
    from app.draw import draw_program
    p = Program([Rung(Series([Parallel([NO("X0"), Series([NO("X1"), NC("X2")])]), NO("M0")]), OutC("C0", 3))])
    plc = PLC(p); plc.scan()
    d = draw_program(p, plc, current_rung=0)
    for e in d.elems:
        assert e.kind in ("line", "rect", "text")
        assert e.color in ("power", "idle", "on", "off", "text", "marker", "rail")
        assert isinstance(e.tag, tuple) and e.tag
    assert len(by_tag(d, "contact")) >= 4


# ======================= app.controller =======================

def test_controller_initial():
    from app.controller import Controller
    c = Controller(selfhold())
    assert c.mode == "run" and c.speed == 0
    assert c.mid_scan is False and c.last_step is None
    assert c.current_rung is None and c.phase_text == ""
    assert isinstance(c.plc, PLC) and c.plc.scan_ms == 10


def test_controller_step_one_sequence():
    from app.controller import Controller
    p = Program([Rung(NO("X0"), Out("Y0")), Rung(NO("X1"), Out("Y1"))])
    c = Controller(p)
    c.pause()
    c.set_button("X0", True)
    s = c.step_one()
    assert s == Step("input", None, None) and c.mid_scan and c.current_rung is None
    assert c.phase_text == "输入采样"
    s = c.step_one()
    assert s == Step("rung", 0, True) and c.current_rung == 0 and c.phase_text == "执行第 1 行"
    s = c.step_one()
    assert s == Step("rung", 1, False) and c.current_rung == 1 and c.phase_text == "执行第 2 行"
    assert c.plc.output("Y0") is False
    s = c.step_one()
    assert s == Step("output", None, None) and not c.mid_scan and c.current_rung is None
    assert c.phase_text == "输出刷新" and c.plc.output("Y0") is True
    s = c.step_one()
    assert s.phase == "input" and c.plc.scan_count == 1
    assert c.last_step == s


def test_controller_step_scan():
    from app.controller import Controller
    c = Controller(selfhold())
    c.pause()
    c.step_scan()
    assert c.plc.scan_count == 1 and not c.mid_scan
    c.step_one(); c.step_one()
    assert c.mid_scan
    c.step_scan()                        # 走完当前这轮
    assert c.plc.scan_count == 2 and not c.mid_scan


def test_controller_pause_does_nothing():
    from app.controller import Controller
    c = Controller(selfhold())
    c.pause()
    c.update(1.0)
    assert c.plc.scan_count == 0 and c.mode == "pause"


def test_controller_run_realtime():
    from app.controller import Controller
    c = Controller(selfhold(), scan_ms=10)
    c.update(0.1)
    assert c.plc.scan_count == 10
    c.update(0.005); c.update(0.005)
    assert c.plc.scan_count == 11
    assert not c.mid_scan


def test_controller_run_cap_100():
    from app.controller import Controller
    c = Controller(selfhold(), scan_ms=10)
    c.update(5.0)
    assert c.plc.scan_count == 100
    c.update(0.01)
    assert c.plc.scan_count == 101        # 多余的累计时间被丢掉了


def test_controller_resume_mid_scan_finishes_partial():
    from app.controller import Controller
    p = Program([Rung(NO("X0"), Out("Y0"))])
    c = Controller(p, scan_ms=10)
    c.pause(); c.set_button("X0", True)
    c.step_one(); c.step_one()            # input, rung0
    c.run()
    c.update(0.01)
    assert c.plc.scan_count == 1 and not c.mid_scan and c.plc.output("Y0")


def test_controller_slow_motion():
    from app.controller import Controller
    p = Program([Rung(NO("X0"), Out("Y0"))])     # 每轮 3 步
    c = Controller(p)
    c.speed = 0.5
    c.update(1.2)
    assert c.last_step == Step("rung", 0, False) and c.mid_scan
    c.update(0.3)                         # 累计 1.5 → 第 3 步
    assert c.last_step == Step("output", None, None) and c.plc.scan_count == 1


def test_controller_load_resets():
    from app.controller import Controller
    c = Controller(selfhold())
    c.set_button("X0", True)
    c.update(0.1)
    c.pause(); c.step_one()
    p2 = Program([Rung(NO("X0"), Out("Y2"))])
    c.load(p2)
    assert c.program is p2 and c.plc.scan_count == 0
    assert not c.mid_scan and c.last_step is None and c.current_rung is None
    c.step_scan()
    assert c.plc.output("Y2") is True     # 按钮状态保留


def test_controller_set_button_immediate():
    from app.controller import Controller
    c = Controller(selfhold())
    c.set_button("X1", True)
    c.pause(); c.step_one()
    assert c.plc.get("X1") is True


# ======================= app.views =======================

def test_io_names():
    from app.views import IO_NAMES
    for a in ["X0", "X1", "X2", "X3", "Y0", "Y1", "Y2"]:
        assert IO_NAMES[a].strip()


def test_il_rows():
    from app.views import il_rows
    p = Program([Rung(Series([Parallel([NO("X0"), NO("Y0")]), NC("X1")]), Out("Y0")),
                 Rung(NO("Y0"), OutT("T0", 50))])
    assert il_rows(p) == [(0, "LD X0"), (0, "OR Y0"), (0, "ANI X1"), (0, "OUT Y0"),
                          (1, "LD Y0"), (1, "OUT T0 K50"), (None, "END")]
    assert il_rows(Program([])) == [(None, "END")]


def test_monitor_rows_order_and_values():
    from app.views import monitor_rows, IO_NAMES
    p = Program([
        Rung(NO("X0"), OutT("T1", 50)),
        Rung(NO("M2"), Out("M10")),
        Rung(NO("X1"), OutC("C0", 3)),
        Rung(NO("T1"), Out("M1")),
        Rung(NO("C3"), Rst("T0")),
    ])
    plc = PLC(p, scan_ms=100)
    rows = monitor_rows(p, plc)
    addrs = [r[0] for r in rows]
    assert addrs == ["X0", "X1", "X2", "X3", "Y0", "Y1", "Y2",
                     "M1", "M2", "M10", "T0", "T1", "C0", "C3"]
    d = {r[0]: r for r in rows}
    assert d["X0"][1] == IO_NAMES["X0"] and d["M1"][1] == ""
    assert d["X0"][2] == "OFF" and d["X0"][3] is False
    assert d["T1"][2] == "0.0/5.0"
    assert d["T0"][2] == "0.0/-"
    assert d["C0"][2] == "0/3"
    assert d["C3"][2] == "0/-"

    plc.set_input("X0", True); plc.set_input("X1", True)
    for _ in range(32):
        plc.scan()
    d = {r[0]: r for r in monitor_rows(p, plc)}
    assert d["X0"][2] == "ON" and d["X0"][3] is True
    assert d["T1"][2] == "3.2/5.0" and d["T1"][3] is False
    assert d["C0"][2] == "1/3"
    for _ in range(20):
        plc.scan()
    d = {r[0]: r for r in monitor_rows(p, plc)}
    assert d["T1"][2] == "5.0/5.0" and d["T1"][3] is True
    assert d["M1"][2] == "ON"


def test_monitor_rows_minimal():
    from app.views import monitor_rows
    p = Program([Rung(NO("X0"), Out("Y0"))])
    assert [r[0] for r in monitor_rows(p, PLC(p))] == ["X0", "X1", "X2", "X3", "Y0", "Y1", "Y2"]


# ======================= app.demos =======================

def test_demos():
    from app.demos import DEMOS
    from plc.to_il import to_il
    names = [n for n, _ in DEMOS]
    assert names[:4] == ["自保持", "定时器", "计数器", "双线圈"]
    expect = [
        ["LD X0", "OR Y0", "ANI X1", "OUT Y0", "END"],
        ["LD X0", "OUT T0 K30", "LD T0", "OUT Y1", "END"],
        ["LD X0", "OUT C0 K3", "LD X1", "RST C0", "LD C0", "OUT Y2", "END"],
        ["LD X0", "OUT Y0", "LD X1", "OUT Y0", "END"],
    ]
    for (name, prog), il in zip(DEMOS[:4], expect):
        assert isinstance(prog, Program)
        assert to_il(prog) == il, name
        PLC(prog)
