"""离屏截图：python tools/snapshot.py  → docs/shots/P2_*.png"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from panda3d.core import loadPrcFileData, Filename

loadPrcFileData("", "window-type offscreen\nwin-size 1280 720\naudio-library-name null")

from ui.app_main import PlcApp
from app.demos import DEMOS

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
    app.destroy()


if __name__ == "__main__":
    main()
