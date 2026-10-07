"""离屏截图：python tools/snapshot.py  → docs/shots/P2_ ~ P5_*.png"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from panda3d.core import loadPrcFileData, Filename

loadPrcFileData("", "window-type offscreen\nwin-size 1280 720\naudio-library-name null")

from ui.app_main import PlcApp
from app.demos import DEMOS
from app.draw import draw_program

OUT = os.path.join(ROOT, "docs", "shots")


def shot(app, name):
    app.refresh()
    app.graphicsEngine.renderFrame()
    app.graphicsEngine.renderFrame()
    path = os.path.join(OUT, name)
    assert app.win.saveScreenshot(Filename.fromOsSpecific(path)), name
    print("saved", path)


def run_ms(c, ms):
    for _ in range(ms // 10):
        c.update(0.01)


def main():
    os.makedirs(OUT, exist_ok=True)
    app = PlcApp()
    app.level_select.hide()                        # 启动时默认打开关卡选择，P2/P3 截图先关掉
    c = app.ctrl

    app.pick_demo(0)
    run_ms(c, 100)
    shot(app, "P2_selfhold_off.png")

    app.pick_demo(0)
    c.set_button("X0", True); c.update(0.01)
    c.set_button("X0", False); run_ms(c, 100)
    shot(app, "P2_selfhold_on.png")

    app.pick_demo(3)
    c.set_button("X0", True)
    c.pause()
    c.step_one(); c.step_one()
    shot(app, "P2_step_rung.png")

    app.pick_demo(1)
    c.run()
    run_ms(c, 1500)
    shot(app, "P2_timer.png")

    from sim.tank import Tank
    app.tank_scene.time_fn = lambda: 0.0          # 溢出闪红：固定在"红"的相位

    app.pick_demo(4)
    shot(app, "P3_tank_empty.png")

    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    run_ms(c, 4000)
    shot(app, "P3_tank_filling.png")
    run_ms(c, 6000)
    shot(app, "P3_tank_full.png")

    app.pick_demo(5)
    c.tank = Tank(level=85)
    run_ms(c, 1500)
    shot(app, "P3_drain.png")

    app.pick_demo(0)
    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    run_ms(c, 11000)
    shot(app, "P3_overflow.png")

    # ---------- P4 关卡 ----------
    app.tank_scene.time_fn = lambda: 0.5           # 恢复成"不闪红"的相位
    app.session.passed = {1, 2, 3}
    app.open_levels()
    shot(app, "P4_level_select.png")
    app.level_select._pick(3)                      # 第 4 关，弹出说明
    shot(app, "P4_intro.png")
    app.popup.hide()
    app.judge()                                    # 示例直接判定 → 不通过
    shot(app, "P4_result_fail.png")
    app.popup._close_result()
    app.enter_level(4)                             # 第 5 关 选择题
    app.answer(1)
    shot(app, "P4_quiz.png")
    app.popup.hide()
    app.enter_level(7)                             # 第 8 关，用参考答案跑 20 秒
    app.popup.hide()
    app.load_solution()
    c = app.ctrl
    c.set_button("X0", True); c.update(0.05); c.set_button("X0", False)
    run_ms(c, 20000)
    shot(app, "P4_level8.png")
    app.leave_level()

    # ---- P5 编辑器 ----
    app.enter_level(3)                           # 第 4 关
    app.popup.hide()
    eb = app.editor_bar
    app.sel = ("contact", 0, 2)                  # X1
    shot(app, "P5_select_contact.png")

    app.on_insert_right()                        # X1 右边插入触点，自动选中
    eb.put(eb.addr_entry, "X3")
    app.on_addr_enter("X3")
    app.on_toggle_nc()                           # 变成 b接点 → 参考答案
    ok, msg = app.session.judge()
    print("level4 judge after edits:", ok, msg)
    assert ok, msg
    shot(app, "P5_after_edit.png")

    app.sel = ("coil", 0)
    shot(app, "P5_select_coil.png")

    app.leave_level()
    app.enter_sandbox()
    app.sel = ("contact", 0, 0)
    for addr in ("X1", "X2"):
        app.on_insert_right()
        eb.put(eb.addr_entry, addr)
        app.on_addr_enter(addr)
    app.sel, app.sel2 = ("contact", 0, 0), 1     # 选中 X0~X1 这一段
    app.on_parallel()
    eb.put(eb.addr_entry, "M0")
    app.on_addr_enter("M0")
    shot(app, "P5_parallel_span.png")

    app.sel, app.sel2 = ("contact", 0, 0), None
    app.refresh()
    eb.put(eb.addr_entry, "Z9")
    app.on_addr_enter("Z9")
    shot(app, "P5_bad_address.png")
    app.pick_demo(0)
    app.msg_t = 0.0

    # 梯形图区放大：证明标签不压线
    app.pick_demo(0)
    c.set_button("X0", True); run_ms(c, 100); c.set_button("X0", False); run_ms(c, 100)
    W = 1280 / 720
    app.ladder.region = (-W + 0.1, 0.6, -0.9, 0.9)
    app.ladder.max_scale = 0.5
    for t in (app.il_table, app.mon_table):
        t._destroy(); t._shape = None
    app.il_table.set_rows([], [0, 0.1]); app.mon_table.set_rows([], [0, 0.12, 0.8])
    app.refresh = lambda: app.ladder.redraw(draw_program(c.program, c.plc, c.current_rung))
    shot(app, "P3_labels.png")
    app.destroy()


if __name__ == "__main__":
    main()
