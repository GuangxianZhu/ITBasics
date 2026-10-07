"""离屏截图：python tools/snapshot.py  → docs/shots/P2_*.png"""
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
