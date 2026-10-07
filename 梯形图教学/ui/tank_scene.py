"""3D 水槽场景：独立 DisplayRegion + 独立相机。只读 scene_state，不做逻辑判断。"""
from panda3d.core import (Camera, PerspectiveLens, NodePath, LineSegs, TextNode,
                          TransparencyAttrib)

from ui.geom import make_box, make_cylinder

H = 3.0            # 槽高
HALF = 1.0         # 槽半宽
PIPE_Z = 3.75      # 进水管口高度
GREEN = (0.25, 1.0, 0.35, 1)
GRAY = (0.5, 0.5, 0.5, 1)
WATER = (0.2, 0.5, 1.0, 0.55)


class TankScene:
    def __init__(self, base, font, region=(0.68, 1.0, 0.33, 0.97), bg=(0.07, 0.08, 0.1, 1)):
        self.base = base
        from panda3d.core import ClockObject
        self.time_fn = lambda: ClockObject.getGlobalClock().getFrameTime()
        self.root = NodePath("tank_scene")
        self.root.setTransparency(TransparencyAttrib.MAlpha)

        # 相机 + 独立 DisplayRegion（sort 大于 render2d 的，保证画在 2D 背景之上）
        cam = Camera("tank_cam")
        lens = PerspectiveLens()
        w = (region[1] - region[0]) * base.win.getXSize()
        h = (region[3] - region[2]) * base.win.getYSize()
        lens.setAspectRatio(w / h)
        lens.setFov(38)
        cam.setLens(lens)
        self.cam_np = self.root.attachNewNode(cam)
        self.cam_np.setPos(6.2, -8.8, 5.6)
        self.cam_np.lookAt(0.6, 0, 1.6)
        self.dr = base.win.makeDisplayRegion(*region)
        self.dr.setSort(20)
        self.dr.setClearColorActive(True)
        self.dr.setClearColor(bg)
        self.dr.setClearDepthActive(True)
        self.dr.setCamera(self.cam_np)

        r = self.root
        # 槽体（半透明）+ 轮廓
        self.glass = make_box(-HALF, HALF, -HALF, HALF, 0, H, "glass")
        self.glass.reparentTo(r)
        self.glass.setColorScale(0.8, 0.9, 1.0, 0.25)
        self.glass.setBin("fixed", 50); self.glass.setDepthWrite(False)
        ls = LineSegs(); ls.setThickness(3)
        c = [(-HALF, -HALF), (HALF, -HALF), (HALF, HALF), (-HALF, HALF)]
        for z in (0, H):
            ls.moveTo(c[0][0], c[0][1], z)
            for x, y in c[1:] + [c[0]]:
                ls.drawTo(x, y, z)
        for x, y in c:
            ls.moveTo(x, y, 0); ls.drawTo(x, y, H)
        self.outline = r.attachNewNode(ls.create())
        self.outline.setBin("fixed", 60); self.outline.setDepthWrite(False)

        # 水
        self.water = make_box(-HALF + 0.05, HALF - 0.05, -HALF + 0.05, HALF - 0.05, 0, 1.0, "water")
        self.water.reparentTo(r)
        self.water.setColorScale(*WATER)
        self.water.setBin("fixed", 40); self.water.setDepthWrite(False)

        # 上限 / 下限开关
        self.x3 = self._switch("X3 上限", 0.8 * H, font)
        self.x2 = self._switch("X2 下限", 0.2 * H, font)

        # 进水管 + 阀 + 水柱
        pipe = make_box(-3.0, 0.15, -0.15, 0.15, PIPE_Z - 0.15, PIPE_Z + 0.15, "inlet_pipe")
        pipe.reparentTo(r); pipe.setColorScale(0.6, 0.65, 0.7, 1)
        mouth = make_box(-0.15, 0.15, -0.15, 0.15, PIPE_Z - 0.5, PIPE_Z + 0.15, "mouth")
        mouth.reparentTo(r); mouth.setColorScale(0.6, 0.65, 0.7, 1)
        self.inlet_valve = make_box(-1.9, -1.5, -0.25, 0.25, PIPE_Z - 0.25, PIPE_Z + 0.25, "inlet_valve")
        self.inlet_valve.reparentTo(r)
        self._label("Y0 给水阀", (-1.7, 0, PIPE_Z + 0.45), font, r)
        self.column = make_box(-0.07, 0.07, -0.07, 0.07, 0, 1.0, "column")
        self.column.reparentTo(r); self.column.setColorScale(*WATER)
        self.column.setBin("fixed", 40); self.column.setDepthWrite(False)

        # 排水管 + 阀 + 出水
        dpipe = make_box(HALF - 0.05, 3.2, -0.12, 0.12, 0.12, 0.36, "drain_pipe")
        dpipe.reparentTo(r); dpipe.setColorScale(0.6, 0.65, 0.7, 1)
        self.drain_valve = make_box(1.5, 1.9, -0.2, 0.2, 0.05, 0.45, "drain_valve")
        self.drain_valve.reparentTo(r)
        self._label("Y1 排水阀", (1.7, 0, 0.75), font, r)
        self.stream = make_box(2.95, 3.15, -0.08, 0.08, -0.9, 0.2, "stream")
        self.stream.reparentTo(r); self.stream.setColorScale(*WATER)
        self.stream.setBin("fixed", 40); self.stream.setDepthWrite(False)

        # 完成灯
        self.lamp = make_cylinder(0.28, 0, 0.5, cx=-2.2, cy=0.0, name="lamp")
        self.lamp.reparentTo(r)
        self._label("Y2 完成灯", (-2.2, 0, 0.95), font, r)

        # 地面板
        floor = make_box(-3.4, 3.6, -1.6, 1.6, -1.0, -0.9, "floor")
        floor.reparentTo(r); floor.setColorScale(0.22, 0.24, 0.28, 1)

    def _label(self, text, pos, font, parent, scale=0.3):
        tn = TextNode("lbl")
        tn.setFont(font); tn.setText(text); tn.setAlign(TextNode.ACenter)
        tn.setTextColor(0.9, 0.9, 0.9, 1)
        n = parent.attachNewNode(tn)
        n.setScale(scale); n.setPos(*pos); n.setBillboardPointEye()
        return n

    def _switch(self, text, z, font):
        box = make_box(-0.7, -0.3, -HALF - 0.3, -HALF, z - 0.15, z + 0.15, "sw")
        box.reparentTo(self.root)
        self._label(text, (-1.45, -HALF - 0.3, z - 0.1), font, self.root, 0.26)
        return box

    def update(self, st):
        """st = app.scene_state.scene_state(ctrl) 的结果。只改已有节点。"""
        lv = st["level"] / 100.0 * H
        if lv > 0.01:
            self.water.show(); self.water.setSz(lv)
        else:
            self.water.hide()
        self.x3.setColorScale(*(GREEN if st["x3_on"] else GRAY))
        self.x2.setColorScale(*(GREEN if st["x2_on"] else GRAY))
        self.inlet_valve.setColorScale(*(GREEN if st["inlet_open"] else (0.8, 0.25, 0.2, 1)))
        self.drain_valve.setColorScale(*(GREEN if st["drain_open"] else (0.8, 0.25, 0.2, 1)))
        if st["inlet_open"]:
            top = PIPE_Z - 0.5
            surf = max(lv, 0.0)
            self.column.show()
            self.column.setZ(surf); self.column.setSz(max(top - surf, 0.01))
        else:
            self.column.hide()
        (self.stream.show if st["drain_open"] else self.stream.hide)()
        self.lamp.setColorScale(*((1.0, 0.9, 0.2, 1) if st["lamp_on"] else (0.3, 0.28, 0.12, 1)))
        flash = st["overflow"] and int(self.time_fn() * 2) % 2 == 0
        self.outline.setColorScale(*((1, 0.1, 0.1, 1) if flash else (0.85, 0.9, 1.0, 1)))
