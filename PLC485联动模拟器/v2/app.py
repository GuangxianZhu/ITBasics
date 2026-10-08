# -*- coding: utf-8 -*-
"""
v2  清洗机(原IO) ↔ PLC 网关 ↔ 全串口温水器   双向通信演示

运行:  pip install panda3d
       python app.py

操作:
  左侧       清洗机给 PLC 的信号（W0~W3 电平、W4 复位、AD 4-20mA）+ 急停（硬线直达温水器）
             下面是 PLC 给清洗机的 R0~R4（原 IO 的输入）
  右侧       16 个用例 / 故障注入 / 温水器看门狗 有无
  图表上方   窗口 20s/5s/1s，协议切换（虚构 v2 ↔ Modbus RTU）
  空格       暂停/继续     暂停时点时序图看该时刻 IO 和报文逐字段解码
  ← →        移动查看光标（Shift 加大）    [ ] 跳到上/下一条写命令
  R          重置

文件分工:
  codec.py          帧编解码（换协议改这里）
  command_table.py  参数表（照手册填）
  point_map.py      原 IO ↔ 参数 的对应、通信异常时的输出策略、时序参数
  engine.py         PLC 网关 + 温水器模型 + 用例（一般不用改）
  app.py            画面
"""
import os
import math

from panda3d.core import loadPrcFileData

loadPrcFileData('', '''
win-size 1600 900
window-title 清洗机 <-> PLC <-> 串口温水器  双向通信演示 v2
sync-video 1
text-encoding utf8
''')

from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectButton, DGG
from panda3d.core import (
    TextNode, Filename, GeomVertexFormat, GeomVertexData, GeomVertexWriter,
    Geom, GeomLines, GeomTriangles, GeomNode, NodePath, TransparencyAttrib,
    AmbientLight, DirectionalLight, LineSegs, Vec3, Point3,
)

import engine as E
import point_map as PM
from codec import CODECS
from command_table import STATUS_BITS, ALARM_BITS


# ============================================================
#  绘图工具
# ============================================================
class Batch:
    def __init__(self):
        fmt = GeomVertexFormat.getV3c4()
        self.tv = GeomVertexData('t', fmt, Geom.UHStream)
        self.tw = GeomVertexWriter(self.tv, 'vertex')
        self.tc = GeomVertexWriter(self.tv, 'color')
        self.tris = GeomTriangles(Geom.UHStream)
        self.nt = 0
        self.lv = GeomVertexData('l', fmt, Geom.UHStream)
        self.lw = GeomVertexWriter(self.lv, 'vertex')
        self.lc = GeomVertexWriter(self.lv, 'color')
        self.lines = GeomLines(Geom.UHStream)
        self.nl = 0

    def line(self, x1, y1, x2, y2, c):
        self.lw.addData3(x1, 0, -y1)
        self.lc.addData4(*c)
        self.lw.addData3(x2, 0, -y2)
        self.lc.addData4(*c)
        self.lines.addVertices(self.nl, self.nl + 1)
        self.nl += 2

    def dash(self, x1, y1, x2, y2, c, on=4, off=3):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 0.5:
            return
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        s = 0.0
        while s < L:
            e = min(L, s + on)
            self.line(x1 + ux * s, y1 + uy * s, x1 + ux * e, y1 + uy * e, c)
            s += on + off

    def rect(self, x1, y1, x2, y2, c):
        for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
            self.tw.addData3(x, 0, -y)
            self.tc.addData4(*c)
        n = self.nt
        self.tris.addVertices(n, n + 1, n + 2)
        self.tris.addVertices(n, n + 2, n + 3)
        self.nt += 4

    def box(self, x1, y1, x2, y2, c):
        self.line(x1, y1, x2, y1, c)
        self.line(x2, y1, x2, y2, c)
        self.line(x2, y2, x1, y2, c)
        self.line(x1, y2, x1, y1, c)

    def make(self, name='batch'):
        node = GeomNode(name)
        if self.nt:
            g = Geom(self.tv)
            g.addPrimitive(self.tris)
            node.addGeom(g)
        if self.nl:
            g = Geom(self.lv)
            g.addPrimitive(self.lines)
            node.addGeom(g)
        return node


def make_box(sx, sy, sz):
    fmt = GeomVertexFormat.getV3n3()
    vd = GeomVertexData('box', fmt, Geom.UHStatic)
    vw, nw = GeomVertexWriter(vd, 'vertex'), GeomVertexWriter(vd, 'normal')
    tr = GeomTriangles(Geom.UHStatic)
    h = Vec3(sx / 2, sy / 2, sz / 2)
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
             ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
             ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    i = 0
    for n, u, v in faces:
        n, u, v = Vec3(*n), Vec3(*u), Vec3(*v)
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = n + u * su + v * sv
            vw.addData3(p[0] * h[0], p[1] * h[1], p[2] * h[2])
            nw.addData3(n)
        tr.addVertices(i, i + 1, i + 2)
        tr.addVertices(i, i + 2, i + 3)
        i += 4
    g = Geom(vd)
    g.addPrimitive(tr)
    node = GeomNode('box')
    node.addGeom(g)
    return NodePath(node)


def make_cyl(r, h, seg=20):
    fmt = GeomVertexFormat.getV3n3()
    vd = GeomVertexData('cyl', fmt, Geom.UHStatic)
    vw, nw = GeomVertexWriter(vd, 'vertex'), GeomVertexWriter(vd, 'normal')
    tr = GeomTriangles(Geom.UHStatic)
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        c, s = math.cos(a), math.sin(a)
        vw.addData3(r * c, r * s, 0); nw.addData3(c, s, 0)
        vw.addData3(r * c, r * s, h); nw.addData3(c, s, 0)
    for i in range(seg):
        b0, t0, b1, t1 = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        tr.addVertices(b0, b1, t1)
        tr.addVertices(b0, t1, t0)
    for z, nz in ((h, 1), (0, -1)):
        ci = vw.getWriteRow()
        vw.addData3(0, 0, z); nw.addData3(0, 0, nz)
        for i in range(seg + 1):
            a = 2 * math.pi * i / seg
            vw.addData3(r * math.cos(a), r * math.sin(a), z); nw.addData3(0, 0, nz)
        for i in range(seg):
            if nz > 0:
                tr.addVertices(ci, ci + 1 + i, ci + 2 + i)
            else:
                tr.addVertices(ci, ci + 2 + i, ci + 1 + i)
    g = Geom(vd)
    g.addPrimitive(tr)
    node = GeomNode('cyl')
    node.addGeom(g)
    return NodePath(node)


def load_cjk_font(loader):
    cands = [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyh.ttf',
             r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\YuGothM.ttc',
             r'C:\Windows\Fonts\meiryo.ttc',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
             '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
             '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
             '/System/Library/Fonts/PingFang.ttc']
    for p in cands:
        if os.path.exists(p):
            try:
                f = loader.loadFont(Filename.fromOsSpecific(p).getFullpath())
                f.setPixelsPerUnit(40)
                return f
            except Exception:
                pass
    print('[警告] 没找到中文字体，中文会显示为方块')
    return None


# ============================================================
#  颜色 / 布局
# ============================================================
BG = (0.08, 0.09, 0.11, 1)
PANEL = (0.12, 0.13, 0.16, 1)
EDGE = (0.25, 0.27, 0.32, 1)
TXT = (0.88, 0.89, 0.92, 1)
DIM = (0.55, 0.57, 0.62, 1)
C_W = (0.55, 0.75, 1.0, 1)        # 清洗机 → PLC
C_R = (0.45, 0.9, 0.6, 1)         # PLC → 清洗机
C_RED = (1.0, 0.35, 0.35, 1)
C_HW = (1.0, 0.68, 0.25, 1)
C_PWR = (1.0, 0.5, 0.15, 1)
C_TX = (0.62, 0.55, 1.0, 1)
C_RX = (0.25, 0.8, 0.62, 1)
C_CUR = (0.3, 0.6, 1.0, 1)
C_INS = (1.0, 0.85, 0.2, 1)
C_AD = (0.4, 0.9, 1.0, 1)
OFFC = (0.22, 0.24, 0.28, 1)
LOG_COL = {'tx': C_TX, 'rx': C_RX, 'nak': (1, 0.5, 0.45, 1), 'alarm': C_RED,
           'hw': C_HW, 'plc': (0.78, 0.8, 0.84, 1), 'op': (0.55, 0.75, 1.0, 1),
           'case': (0.6, 0.85, 1.0, 1)}
LOG_TAG = {'tx': 'TX ', 'rx': 'RX ', 'nak': '!! ', 'alarm': '报警', 'hw': '温水',
           'plc': 'PLC', 'op': '操作', 'case': '用例'}

WIN_W, WIN_H = 1600, 900
CH_X0, CH_X1 = 250, 1100
PX0, PX1 = 352, 1088
PW = PX1 - PX0
ROW_TOP = 40
RH = 23
ROWS = [('W0', 'W0 远程', C_W), ('W1', 'W1 在线', C_W), ('W2', 'W2 通水', C_W),
        ('W3', 'W3 加热', C_W), ('W4', 'W4 复位', C_W), ('ES', '急停 硬线', C_RED),
        ('R0', 'R0 Ready', C_R), ('R1', 'R1 过热', C_R), ('R2', 'R2 漏水', C_R),
        ('R3', 'R3 轻故障', C_R), ('R4', 'R4 重故障', C_RED),
        ('CF', 'PLC通信异常', C_HW), ('PWR', '温水器加热', C_PWR),
        ('TX', '485 TX', C_TX), ('RX', '485 RX', C_RX)]
ROW_Y = {k: ROW_TOP + i * RH for i, (k, _, _) in enumerate(ROWS)}
PV_TOP = ROW_TOP + len(ROWS) * RH + 4
PV_H = 74
CH_BOTTOM = PV_TOP + PV_H + 22
V3_X0, V3_Y0, V3_X1, V3_Y1 = 1110, 0, 1600, 360


# ============================================================
#  应用
# ============================================================
class App(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()
        self.setBackgroundColor(*BG)
        self.font = load_cjk_font(self.loader)
        if self.font:
            TextNode.setDefaultFont(self.font)
            DGG.setDefaultFont(self.font)
        self.sim = E.Sim()
        self.paused = False
        self.speed = 1.0
        self.W = 20.0
        self.inspect_t = None
        self.case_desc = '自由操作：左侧拨清洗机信号，或点右侧用例自动演示。'
        self.chart_np = None
        self.redraw_acc = 0.0
        self.packets3d = []

        self.build_static()
        self.build_buttons()
        self.build_texts()
        self.build_3d()

        self.accept('space', self.toggle_pause)
        self.accept('r', self.reset)
        for k, d in (('arrow_left', -0.02), ('arrow_right', 0.02),
                     ('shift-arrow_left', -0.2), ('shift-arrow_right', 0.2)):
            self.accept(k, self.move_inspect, [d])
            self.accept(k + '-repeat', self.move_inspect, [d])
        self.accept('[', self.jump_frame, [-1])
        self.accept(']', self.jump_frame, [1])
        self.accept('mouse1', self.on_click)
        self.taskMgr.add(self.update, 'update')

    # ---------- 文本 ----------
    def text(self, x, y, s='', size=14, color=TXT, align='left', wrap=None, parent=None):
        tn = TextNode('t')
        if self.font:
            tn.setFont(self.font)
        tn.setText(s)
        tn.setTextColor(*color)
        tn.setAlign({'left': TextNode.ALeft, 'center': TextNode.ACenter,
                     'right': TextNode.ARight}[align])
        if wrap:
            tn.setWordwrap(wrap)
        np = (parent or self.pixel2d).attachNewNode(tn)
        np.setScale(size)
        np.setPos(x, 0, -y)
        return tn, np

    # ---------- 静态 ----------
    def build_static(self):
        b = Batch()
        for x1, y1, x2, y2 in ((0, 0, 242, 900), (CH_X0, 0, CH_X1, CH_BOTTOM),
                               (CH_X0, CH_BOTTOM + 6, 700, 900),
                               (708, CH_BOTTOM + 6, CH_X1, 900),
                               (V3_X0, V3_Y1 + 6, 1600, 900)):
            b.rect(x1, y1, x2, y2, PANEL)
            b.box(x1, y1, x2, y2, EDGE)
        for i in range(len(ROWS)):
            y = ROW_TOP + i * RH
            if i % 2 == 0:
                b.rect(CH_X0 + 1, y, CH_X1 - 1, y + RH, (1, 1, 1, 0.025))
        b.line(PX0, ROW_TOP, PX0, PV_TOP + PV_H, EDGE)
        for k in ('R0', 'CF', 'TX'):
            b.line(CH_X0, ROW_Y[k], CH_X1, ROW_Y[k], EDGE)
        b.line(CH_X0, PV_TOP - 2, CH_X1, PV_TOP - 2, EDGE)
        np = self.pixel2d.attachNewNode(b.make('static'))
        np.setTransparency(TransparencyAttrib.MAlpha)

        for i, (k, name, col) in enumerate(ROWS):
            self.text(CH_X0 + 8, ROW_TOP + i * RH + 16, name, 12, col)
        self.text(CH_X0 + 8, PV_TOP + 16, 'PV ℃', 12, C_PWR)
        self.text(CH_X0 + 8, PV_TOP + 32, '-- 温水器SV', 11, C_HW)
        self.text(CH_X0 + 8, PV_TOP + 48, '-- AD设定', 11, C_AD)
        self.text(CH_X0 + 8, PV_TOP + 64, '-- 90 过热', 11, C_RED)
        self.text(10, 22, '清洗机 → PLC（原 IO 输出）', 14, C_W)
        self.text(10, 400, 'PLC → 清洗机（原 IO 输入）', 14, C_R)
        self.text(10, 578, 'PLC 网关内部', 14, TXT)
        self.text(V3_X0 + 10, V3_Y1 + 26, '使用用例（点击自动演示）', 14, TXT)
        self.text(V3_X0 + 10, 646, '故障注入 / 温水器设定', 14, TXT)
        self.text(CH_X0 + 10, CH_BOTTOM + 24, '通信 / 事件日志', 13, TXT)
        self.text(10, 852, '空格 暂停  R 重置  暂停时点图\n←→ 移动  [ ] 跳写命令', 11, DIM)

    # ---------- 按钮 ----------
    def button(self, label, x, y, w, h, cmd, args=None, size=13):
        return DirectButton(parent=self.pixel2d, text=label, text_scale=size,
                            text_fg=TXT, text_pos=(w / 2, -h / 2 - size * 0.35),
                            frameSize=(0, w, -h, 0), pos=(x, 0, -y),
                            frameColor=OFFC, relief=DGG.FLAT,
                            command=cmd, extraArgs=args or [], pressEffect=1)

    def build_buttons(self):
        self.wbtn = {}
        for i, k in enumerate(['W0', 'W1', 'W2', 'W3']):
            self.wbtn[k] = self.button(E.W_NAMES[k] + '（电平）', 10, 34 + i * 36, 222, 31,
                                       self.ui_toggle, [k], 14)
        self.wbtn['W4'] = self.button('W4 复位（按一下）', 10, 180, 222, 31, self.ui_press, ['W4'], 14)
        self.text(10, 236, '温度设定 AD', 13, C_AD)
        self.ma_tn, _ = self.text(232, 236, '', 13, TXT, 'right')
        for i, d in enumerate((-2.0, -0.5, 0.5, 2.0)):
            self.button('%+g mA' % d, 10 + i * 56, 244, 52, 26, self.ui_ma, [d], 12)
        self.wbtn['ES'] = self.button('急停（硬线 → 温水器）', 10, 334, 222, 40,
                                      self.ui_toggle, ['ES'], 14)
        self.btn_pause = self.button('暂停', 10, 726, 222, 30, self.toggle_pause)
        self.spd_btn = {}
        for i, sp in enumerate([0.1, 0.25, 0.5, 1.0]):
            self.spd_btn[sp] = self.button('%gx' % sp, 10 + i * 56, 762, 52, 26, self.set_speed, [sp], 12)
        self.button('重置', 10, 794, 222, 28, self.reset)

        self.win_btn = {}
        for i, w in enumerate([20.0, 5.0, 1.0]):
            self.win_btn[w] = self.button('%gs' % w, 936 + i * 52, 8, 48, 22, self.set_window, [w], 12)
        self.codec_btn = self.button('', 700, 8, 228, 22, self.toggle_codec, None, 12)

        for i, case in enumerate(E.CASES):
            c, r = i % 2, i // 2
            self.button(case[0], V3_X0 + 8 + c * 241, V3_Y1 + 36 + r * 28, 236, 25,
                        self.run_case, [i], 12)
        self.fbtn = {}
        keys = ['cut', 'noise', 'adcut', 'clog', 'overtemp', 'leak', 'light', 'heavy',
                'bcc', 'lossreply', 'reboot']
        for i, f in enumerate(keys):
            c, r = i % 2, i // 2
            lbl = E.FAULT_NAMES[f] + ('（一次）' if f in E.ONCE else '')
            self.fbtn[f] = self.button(lbl, V3_X0 + 8 + c * 241, 656 + r * 28, 236, 25,
                                       self.ui_fault, [f], 12)
        self.wd_btn = self.button('', V3_X0 + 8 + 241, 656 + 5 * 28, 236, 25, self.toggle_wd, None, 12)

    def build_texts(self):
        self.lamp_y = {}
        for i, rp in enumerate(PM.READ_POINTS):
            y = 410 + i * 26
            self.lamp_y[rp['dst']] = y
            self.text(42, y + 17, '%s %s' % (rp['dst'], rp['name']), 13, TXT)
        self.pol_tn, _ = self.text(10, 562, '', 11, DIM)
        self.gw_tn, _ = self.text(12, 602, '', 12, TXT, wrap=226 / 12.0)
        self.head_tn, _ = self.text(CH_X0 + 10, 24, '', 13, TXT)
        self.tick_pool = [self.text(0, 0, '', 11, DIM, 'center') for _ in range(24)]
        self.lbl_pool = [self.text(0, 0, '', 9, TXT, 'center') for _ in range(70)]
        self.log_pool = [self.text(CH_X0 + 10, CH_BOTTOM + 44 + i * 16, '', 11, TXT) for i in range(22)]
        self.detail_tn, _ = self.text(716, CH_BOTTOM + 24, '', 11, TXT)
        self.case_tn, _ = self.text(V3_X0 + 10, 830, '', 11, (0.75, 0.85, 1, 1), wrap=474 / 11.0)
        self.v3_tn, _ = self.text(V3_X0 + 8, 18, '', 12, TXT)

    # ---------- 3D ----------
    def build_3d(self):
        dr = self.camNode.getDisplayRegion(0)
        dr.setDimensions(V3_X0 / WIN_W, V3_X1 / WIN_W, 1 - V3_Y1 / WIN_H, 1 - V3_Y0 / WIN_H)
        dr.setClearColorActive(True)
        dr.setClearColor((0.13, 0.14, 0.17, 1))
        dr.setClearDepthActive(True)
        self.camLens.setAspectRatio((V3_X1 - V3_X0) / float(V3_Y1 - V3_Y0))
        self.camLens.setFov(54)
        self.camera.setPos(-1.2, -10.5, 3.4)
        self.camera.lookAt(-1.2, 0, 1.25)
        al = AmbientLight('a')
        al.setColor((0.45, 0.45, 0.5, 1))
        dl = DirectionalLight('d')
        dl.setColor((0.8, 0.8, 0.75, 1))
        dnp = self.render.attachNewNode(dl)
        dnp.setHpr(-30, -45, 0)
        self.render.setLight(self.render.attachNewNode(al))
        self.render.setLight(dnp)

        def solid(np, col, pos):
            np.reparentTo(self.render)
            np.setColor(*col)
            np.setPos(*pos)
            return np

        def glass(np, col, pos):
            solid(np, col, pos)
            np.setTransparency(TransparencyAttrib.MAlpha)
            np.setDepthWrite(False)
            np.setBin('transparent', 10)
            return np

        def line(pts, col, th=3):
            ls = LineSegs()
            ls.setThickness(th)
            ls.setColor(*col)
            ls.moveTo(*pts[0])
            for p in pts[1:]:
                ls.drawTo(*p)
            np = self.render.attachNewNode(ls.create())
            np.setLightOff()
            return np

        solid(make_box(12, 4, 0.05), (0.2, 0.21, 0.24, 1), (-0.5, 0, -0.03))
        # 清洗机
        solid(make_box(1.6, 1.2, 2.6), (0.3, 0.33, 0.4, 1), (-5.2, 0, 1.3))
        # PLC
        solid(make_box(1.1, 0.8, 1.6), (0.25, 0.3, 0.28, 1), (-2.0, 0, 0.8))
        self.leds = {}
        for i, rp in enumerate(PM.READ_POINTS):
            led = solid(make_box(0.15, 0.05, 0.12), (0.2, 0.2, 0.2, 1), (-2.36 + i * 0.18, -0.42, 1.3))
            led.setLightOff()
            self.leds[rp['dst']] = led
        self.cf_led = solid(make_box(0.3, 0.05, 0.14), (0.2, 0.2, 0.2, 1), (-2.0, -0.42, 1.05))
        self.cf_led.setLightOff()
        # 急停
        solid(make_box(0.5, 0.5, 0.4), (0.9, 0.75, 0.1, 1), (-5.2, -0.9, 0.2))
        self.estop3d = solid(make_cyl(0.18, 0.15), (0.6, 0.05, 0.05, 1), (-5.2, -0.9, 0.4))
        # 温水器
        glass(make_box(2.4, 1.3, 3.2), (0.6, 0.7, 0.8, 0.12), (2.6, 0, 1.6))
        self.lamps = []
        for x in (2.1, 3.1):
            glass(make_cyl(0.3, 2.4), (0.8, 0.9, 1.0, 0.22), (x, 0, 0.3))
            lp = solid(make_cyl(0.07, 2.2), (0.3, 0.3, 0.3, 1), (x, 0, 0.4))
            lp.setLightOff()
            self.lamps.append(lp)
        self.path = [Point3(1.0, 0, 0.2), Point3(2.1, 0, 0.2), Point3(2.1, 0, 2.85),
                     Point3(3.1, 0, 2.85), Point3(3.1, 0, 0.2), Point3(4.6, 0, 0.2)]
        line(self.path, (0.35, 0.45, 0.6, 1), 4)
        self.seglen = [(self.path[i + 1] - self.path[i]).length() for i in range(len(self.path) - 1)]
        self.path_len = sum(self.seglen)
        self.drops = []
        for i in range(22):
            d = solid(make_box(0.12, 0.12, 0.12), (0.3, 0.6, 1, 1), (0, 0, 0))
            d.setLightOff()
            self.drops.append(d)
        self.flow_phase = 0.0
        # 线
        self.io_out = line([(-4.4, 0, 1.55), (-2.55, 0, 1.55)], C_W)
        self.io_in = line([(-4.4, 0, 1.25), (-2.55, 0, 1.25)], C_R)
        line([(-1.45, 0, 1.1), (1.4, 0, 1.1)], C_TX)
        self.hw_line = line([(-5.2, -0.9, 0.12), (1.4, -0.9, 0.12), (1.4, 0, 0.12)], (1, 1, 1, 1))

        def label(s, pos, col=TXT, sc=0.36):
            tn = TextNode('l')
            if self.font:
                tn.setFont(self.font)
            tn.setText(s)
            tn.setAlign(TextNode.ACenter)
            tn.setTextColor(*col)
            np = self.render.attachNewNode(tn)
            np.setScale(sc)
            np.setPos(*pos)
            np.setLightOff()
            return tn
        label('清洗机', (-5.2, -0.65, 2.8))
        label('PLC 网关', (-2.0, -0.45, 1.8))
        label('串口温水器', (2.6, -0.7, 3.4))
        label('原 IO', (-3.5, 0, 1.75), C_W, 0.3)
        label('RS-485', (0.0, 0, 1.3), C_TX, 0.32)
        label('急停 硬线', (-1.8, -0.9, 0.25), C_HW, 0.28)
        solid(make_box(1.7, 0.05, 1.2), (0.05, 0.06, 0.07, 1), (2.6, -0.7, 2.0)).setLightOff()
        self.disp3d = label('', (2.6, -0.76, 2.45), (0.3, 1, 0.6, 1), 0.27)

    def path_point(self, s):
        s = s % self.path_len
        for i, L in enumerate(self.seglen):
            if s <= L:
                return self.path[i] + (self.path[i + 1] - self.path[i]) * (s / L), i
            s -= L
        return self.path[-1], len(self.seglen) - 1

    def update_3d(self, rdt):
        sim, h, gw = self.sim, self.sim.heater, self.sim.gw
        blink = int(globalClock.getFrameTime() * 4) % 2 == 0
        for k, led in self.leds.items():
            on = sim.rec.value_at(k, sim.t)
            col = C_RED if k in ('R1', 'R2', 'R4') else (C_HW if k == 'R3' else C_R)
            led.setColor(*(col if on else (0.18, 0.18, 0.18, 1)))
        self.cf_led.setColor(*(C_HW if gw.comm_fault and blink else (0.18, 0.18, 0.18, 1)))
        for lp in self.lamps:
            if h.power:
                lp.setColor(1.0, 0.65 + 0.1 * math.sin(globalClock.getFrameTime() * 20), 0.2, 1)
            else:
                lp.setColor(0.3, 0.3, 0.3, 1)
        self.estop3d.setZ(0.33 if sim.ES else 0.4)
        self.estop3d.setColor(*((1, 0.1, 0.1, 1) if sim.ES and blink else (0.6, 0.05, 0.05, 1)))
        self.hw_line.setColor(*((1, 0.1, 0.1, 1) if sim.ES and blink else (0.55, 0.4, 0.2, 1)))
        anyw = any(sim.W.values())
        self.io_out.setColor(*(C_W if anyw else (0.25, 0.3, 0.4, 1)))
        anyr = any(gw.R.values())
        self.io_in.setColor(*(C_R if anyr else (0.2, 0.35, 0.28, 1)))
        if not self.paused:
            self.flow_phase += h.flow * 0.08 * rdt * max(self.speed, 0.25)
        heat = max(0.0, min(1.0, (h.pv - E.INLET_T) / 60.0))
        for i, d in enumerate(self.drops):
            if h.flow < 0.3:
                d.hide()
                continue
            d.show()
            p, seg = self.path_point(self.flow_phase + i * self.path_len / len(self.drops))
            d.setPos(p)
            if seg >= 3:
                d.setColor(0.3 + 0.7 * heat, 0.6 - 0.35 * heat, 1 - 0.8 * heat, 1)
            else:
                d.setColor(0.3, 0.6, 1, 1)
        for f in sim.new_frames:
            if f.kind in ('poll', 'data') and len(self.packets3d) > 8:
                continue
            col = C_TX if f.dir == 'TX' else C_RX
            if f.kind == 'nak':
                col = C_RED
            small = f.kind in ('poll', 'data')
            sz = 0.14 if small else 0.24
            pk = make_box(sz, sz, sz)
            pk.reparentTo(self.render)
            pk.setLightOff()
            pk.setColor(*col)
            self.packets3d.append([pk, f, 0.0])
        sim.new_frames.clear()
        keep = []
        for item in self.packets3d:
            pk, f, age = item
            if not self.paused:
                age += rdt
            item[2] = age
            u = min(1.0, age / 0.45)
            if f.lost and u > 0.5:
                u = 0.5
                pk.setColor(1, 0.15, 0.15, 1)
            x = -1.45 + 2.85 * (u if f.dir == 'TX' else 1 - u)
            pk.setPos(x, 0, 1.1 + (0.0 if f.dir == 'TX' else 0.16))
            if age < 0.7:
                keep.append(item)
            else:
                pk.removeNode()
        self.packets3d = keep
        al = [ALARM_BITS[i] for i in range(8) if h.alarm_word() >> i & 1]
        if h.booting:
            disp = '启动中…'
        else:
            disp = '%s %s %s\nPV %.1f℃\nSV %.1f℃\n%s' % (
                'REM' if h.remote else 'LOC', 'ONL' if h.online else '---',
                'RUN' if h.run else 'STOP', h.pv, h.sv, ' '.join(al))
        self.disp3d.setText(disp)
        self.disp3d.setTextColor(*((1, 0.35, 0.35, 1) if al else (0.3, 1, 0.6, 1)))

    # ---------- 回调 ----------
    def ui_toggle(self, k):
        cur = self.sim.ES if k == 'ES' else self.sim.W[k]
        self.sim.set_w(k, not cur)

    def ui_press(self, k):
        self.sim.press(k)

    def ui_ma(self, d):
        self.sim.set_ma(self.sim.ad_ma + d)

    def ui_fault(self, f):
        if f in self.sim.fault:
            self.sim.set_fault(f, not self.sim.fault[f])
        else:
            self.sim.set_fault(f, 1)

    def toggle_wd(self):
        self.sim.set_watchdog(not self.sim.watchdog)

    def toggle_codec(self):
        self.sim.codec_idx = (self.sim.codec_idx + 1) % len(CODECS)
        self.reset()
        self.sim.log('op', '协议切换为 %s（引擎、点表都没改）' % self.sim.codec.name)

    def run_case(self, i):
        self.sim.load_case(E.CASES[i])
        self.case_desc = E.CASES[i][0] + '\n' + E.CASES[i][1]
        self.paused = False
        self.inspect_t = None
        self.clear_packets()

    def reset(self):
        wd = self.sim.watchdog
        self.sim.reset()
        self.sim.watchdog = wd
        self.case_desc = '自由操作：左侧拨清洗机信号，或点右侧用例自动演示。'
        self.paused = False
        self.inspect_t = None
        self.clear_packets()

    def clear_packets(self):
        for pk, _, _ in self.packets3d:
            pk.removeNode()
        self.packets3d = []

    def set_speed(self, sp):
        self.speed = sp

    def set_window(self, w):
        self.W = w

    def toggle_pause(self):
        self.paused = not self.paused
        self.inspect_t = self.sim.t if self.paused else None

    def move_inspect(self, d):
        if not self.paused:
            return
        lo = max(0.0, self.sim.t - self.W)
        self.inspect_t = max(lo, min(self.sim.t, self.inspect_t + d * self.W / 20.0))

    def jump_frame(self, d):
        if not self.paused:
            self.toggle_pause()
        fr = [f for f in self.sim.rec.frames if f.important]
        if not fr:
            return
        t = self.inspect_t
        if d > 0:
            nxt = [f for f in fr if f.t0 > t + 1e-6]
            if nxt:
                self.inspect_t = nxt[0].t0
        else:
            prv = [f for f in fr if f.t0 < t - 1e-6]
            if prv:
                self.inspect_t = prv[-1].t0

    def on_click(self):
        if not self.mouseWatcherNode.hasMouse():
            return
        m = self.mouseWatcherNode.getMouse()
        px = (m.x + 1) / 2 * self.win.getXSize()
        py = (1 - m.y) / 2 * self.win.getYSize()
        if not (PX0 <= px <= PX1 and ROW_TOP <= py <= PV_TOP + PV_H):
            return
        if not self.paused:
            self.toggle_pause()
        now = self.sim.t
        ws = math.floor(now / self.W) * self.W
        t = ws + (px - PX0) / PW * self.W
        if t > now:
            t -= self.W
        self.inspect_t = max(0.0, min(now, t))

    # ---------- 主循环 ----------
    def update(self, task):
        rdt = min(globalClock.getDt(), 0.1)
        if not self.paused:
            n = int(round(rdt * self.speed / E.STEP))
            for _ in range(max(1, n)):
                self.sim.step(E.STEP)
        self.update_3d(rdt)
        self.redraw_acc += rdt
        if self.redraw_acc >= 1 / 30.0 or self.paused:
            self.redraw_acc = 0.0
            self.redraw()
        return task.cont

    # ---------- 时序图 ----------
    def spans(self):
        now, W = self.sim.t, self.W
        ws = math.floor(now / W) * W
        out = [(ws, now, ws, 1.0)]
        a = max(now - W + W * 0.03, 0.0)
        if a < ws:
            out.append((a, ws, ws - W, 0.35))
        return out, ws

    def tx(self, t, off):
        return PX0 + (t - off) / self.W * PW

    def redraw(self):
        sim, rec = self.sim, self.sim.rec
        b = Batch()
        spans, ws = self.spans()
        cur_x = self.tx(sim.t, ws)

        step = 1.0 if self.W >= 5 else 0.1
        lab = 5.0 if self.W >= 20 else (1.0 if self.W >= 5 else 0.2)
        n = int(self.W / step + 0.5)
        ti = 0
        for i in range(n + 1):
            x = PX0 + i * PW / n
            tt = ws + i * step
            major = abs((tt / lab) - round(tt / lab)) < 1e-6
            b.line(x, ROW_TOP, x, PV_TOP + PV_H, (1, 1, 1, 0.09 if major else 0.035))
            if major and ti < len(self.tick_pool):
                tn, np = self.tick_pool[ti]
                tn.setText('%gs' % round(tt, 3))
                np.setPos(x, 0, -(PV_TOP + PV_H + 15))
                np.show()
                ti += 1
        for tn, np in self.tick_pool[ti:]:
            np.hide()

        for key, _, col in ROWS:
            if key in ('TX', 'RX'):
                continue
            top = ROW_Y[key]
            for a, e, off, al in spans:
                c = (col[0], col[1], col[2], al)
                prev = None
                for s, t2, v in rec.segments(key, a, e):
                    x1, x2 = self.tx(s, off), self.tx(t2, off)
                    y = top + 4 if v else top + RH - 4
                    if v:
                        b.rect(x1, top + 4, x2, top + RH - 4, (col[0], col[1], col[2], 0.16 * al))
                    if prev is not None and prev != y:
                        b.line(x1, prev, x1, y, c)
                    b.line(x1, y, x2, y, c)
                    prev = y

        li = 0
        for a, e, off, al in spans:
            for f in rec.frames_between(a, e):
                if f.t0 < a:
                    continue
                top = ROW_Y[f.dir]
                x1 = self.tx(f.t0, off)
                x2 = max(self.tx(f.t1, off), x1 + (2 if not f.important else 4))
                if f.kind == 'nak':
                    col = C_RED
                elif f.corrupt:
                    col = (1, 0.6, 0.2, 1)
                else:
                    col = C_TX if f.dir == 'TX' else C_RX
                strong = f.important
                alpha = al * (1.0 if strong else 0.4)
                y1, y2 = (top + 3, top + RH - 3) if strong else (top + 8, top + RH - 6)
                if f.lost:
                    b.box(x1, y1, x2 + 2, y2, (1, 0.25, 0.25, al))
                    b.line(x1, y1, x2 + 2, y2, (1, 0.25, 0.25, al))
                else:
                    b.rect(x1, y1, x2, y2, (col[0], col[1], col[2], alpha))
                if f.cause and f.dir == 'TX':
                    ck, ct = f.cause
                    if a <= ct <= e and ck in ROW_Y:
                        b.dash(self.tx(ct, off), ROW_Y[ck] + RH / 2, x1, top + 3,
                               (C_TX[0], C_TX[1], C_TX[2], 0.7 * al))
                if strong and li < len(self.lbl_pool):
                    tn, np = self.lbl_pool[li]
                    s = self.short_label(f)
                    tn.setText(s)
                    tn.setTextColor(1, 1, 1, al)
                    np.setPos((x1 + x2) / 2, 0, -(top + 2))
                    np.show()
                    li += 1
        for tn, np in self.lbl_pool[li:]:
            np.hide()

        def py(v):
            return PV_TOP + PV_H - 4 - (max(15, min(100, v)) - 15) / 85.0 * (PV_H - 8)
        for a, e, off, al in spans:
            b.dash(self.tx(a, off), py(90), self.tx(e, off), py(90), (1, 0.3, 0.3, 0.5 * al), 3, 4)
            for key, col, dashed in (('SVT', C_AD, True), ('SVH', C_HW, True), ('PV', C_PWR, False)):
                pts = [(t, v) for t, v in rec.ana_between(key, a, e) if v is not None]
                for (t1, v1), (t2, v2) in zip(pts, pts[1:]):
                    c = (col[0], col[1], col[2], al)
                    if dashed and int(t1 * 20) % 2:
                        continue
                    b.line(self.tx(t1, off), py(v1), self.tx(t2, off), py(v2), c)

        b.rect(cur_x - 1, ROW_TOP - 4, cur_x + 1, PV_TOP + PV_H, C_CUR)
        if self.paused and self.inspect_t is not None:
            it = self.inspect_t
            off = ws if it >= ws else ws - self.W
            ix = self.tx(it, off)
            b.rect(ix - 1, ROW_TOP - 4, ix + 1, PV_TOP + PV_H, C_INS)

        # 左侧灯 + 按钮
        for k, y in self.lamp_y.items():
            on = sim.gw.R[k]
            col = C_RED if k in ('R1', 'R2', 'R4') else (C_HW if k == 'R3' else C_R)
            b.rect(14, y + 4, 34, y + 22, col if on else (0.22, 0.22, 0.25, 1))
        # AD 条
        ma = sim.ad_effective()
        b.rect(10, 278, 232, 290, (0.18, 0.2, 0.24, 1))
        b.rect(10 + 222 * 4 / 22, 278, 10 + 222 * 20 / 22, 290, (0.2, 0.3, 0.35, 1))
        mx = 10 + 222 * max(0.0, min(22.0, ma)) / 22.0
        b.rect(10, 279, mx, 289, C_AD if not sim.gw.ad_fault else C_RED)
        for k, btn in self.wbtn.items():
            on = sim.ES if k == 'ES' else sim.W[k]
            if k == 'ES':
                c = (0.85, 0.1, 0.1, 1) if on else (0.4, 0.08, 0.08, 1)
            else:
                c = (0.2, 0.42, 0.65, 1) if on else OFFC
            btn['frameColor'] = c
        for f, btn in self.fbtn.items():
            on = sim.fault.get(f) or sim.once.get(f)
            btn['frameColor'] = (0.7, 0.42, 0.1, 1) if on else OFFC
        self.wd_btn['text'] = '温水器看门狗：%s' % ('有（2s 自停）' if sim.watchdog else '无')
        self.wd_btn['frameColor'] = (0.2, 0.5, 0.32, 1) if sim.watchdog else (0.45, 0.22, 0.22, 1)
        self.codec_btn['text'] = '协议：%s' % sim.codec.name
        for sp, btn in self.spd_btn.items():
            btn['frameColor'] = (0.2, 0.35, 0.6, 1) if sp == self.speed else OFFC
        for w, btn in self.win_btn.items():
            btn['frameColor'] = (0.2, 0.35, 0.6, 1) if w == self.W else OFFC
        self.btn_pause['text'] = '继续（空格）' if self.paused else '暂停（空格）'

        if self.chart_np:
            self.chart_np.removeNode()
        self.chart_np = self.pixel2d.attachNewNode(b.make('chart'))
        self.chart_np.setTransparency(TransparencyAttrib.MAlpha)
        self.chart_np.setRenderModeThickness(1.6)
        self.update_texts()

    def short_label(self, f):
        """时序图上帧块的小标签"""
        if f.lost:
            return '×'
        if f.dir == 'TX':
            if f.kind == 'poll':
                return 'R'
            names = {'001': '远', '005': '线', '003': '水', '002': '热', '004': '复', '010': 'SV'}
            for wp in PM.WRITE_POINTS + [PM.RESET]:
                if wp['name'] in f.desc:
                    return names.get(wp['param'], 'W')
            return 'W'
        if f.kind == 'nak':
            return 'NAK'
        return 'A' if f.kind == 'ack' else ''

    def update_texts(self):
        sim, gw, h = self.sim, self.sim.gw, self.sim.heater
        state = '暂停' if self.paused else '运行 %gx' % self.speed
        self.head_tn.setText('时序图  t = %.3f s  [%s]' % (sim.t, state))
        sv = gw.sv_target
        A = PM.AD
        self.ma_tn.setText('%.2fmA → %s' % (sim.ad_effective(),
                                            'AD断线' if gw.ad_fault else ('%.1f℃' % sv if sv else '-')))
        self.pol_tn.setText('故障输出极性：%s（point_map 可改）' %
                            ('0=故障 b接点' if PM.FAULT_ACTIVE_LOW else '1=故障 a接点'))
        st = gw.actual.get('101')
        al = gw.actual.get('102')
        pv = gw.actual.get('100')
        svr = gw.actual.get('010')
        lines = []
        lines.append('通信：%s   连续失败 %d   待写 %d' % (
            '异常(锁存)' if gw.comm_fault else '正常', gw.fail, len(gw.queue)))
        lines.append('读回 PV %s  SV %s' % ('%.1f' % (pv[0] / 10.0) if pv else '-',
                                         '%.1f' % (svr[0] / 10.0) if svr else '-'))
        if st:
            lines.append('状态：' + ' '.join(n for i, n in enumerate(STATUS_BITS) if n and st[0] >> i & 1))
        if al:
            lines.append('报警：' + (' '.join(n for i, n in enumerate(ALARM_BITS) if al[0] >> i & 1) or '无'))
        extra = []
        if gw.ad_fault:
            extra.append('AD断线')
        if gw.mismatch:
            extra.append('指令不一致')
        if extra:
            lines.append('PLC 判断：' + ' '.join(extra))
        self.gw_tn.setText('\n'.join(lines))

        logs = sim.rec.log
        if self.paused and self.inspect_t is not None:
            logs = [l for l in logs if l[0] <= self.inspect_t + 1e-6]
        logs = logs[-len(self.log_pool):]
        for i, (tn, np) in enumerate(self.log_pool):
            if i < len(logs):
                t, k, s = logs[i]
                line = '%8.3f %s %s' % (t, LOG_TAG[k], s)
                if len(line) > 56:
                    line = line[:55] + '…'
                tn.setText(line)
                tn.setTextColor(*LOG_COL[k])
            else:
                tn.setText('')
        self.detail_tn.setText(self.detail_text())
        self.case_tn.setText(self.case_desc)
        flt = [E.FAULT_NAMES[k] for k, v in sim.fault.items() if v]
        self.v3_tn.setText('3D   故障：%s' % ('、'.join(flt) if flt else '无'))

    def detail_text(self):
        sim, rec = self.sim, self.sim.rec
        if not (self.paused and self.inspect_t is not None):
            return ('报文详情\n\n运行中… 按空格暂停或直接点时序图，\n'
                    '查看任意时刻的 IO 和报文。\n\n'
                    '图例：\n 实心块 = 写命令/应答\n 淡色细块 = 轮询读\n 红色 = NAK\n'
                    ' 橙色 = 校验被破坏\n 红框× = 线上丢失\n 紫色虚线 = 哪个信号引起的\n\n'
                    'PV 图：橙=PV  黄虚=温水器SV  青虚=AD设定')
        t = self.inspect_t
        v = lambda k: rec.value_at(k, t)
        ma = rec.ana_at('MA', t)
        lines = ['查看光标 t = %.3f s' % t,
                 '清洗机→ W0远程=%d W1在线=%d W2通水=%d W3加热=%d W4复位=%d' % tuple(
                     v(k) for k in ('W0', 'W1', 'W2', 'W3', 'W4')),
                 '        AD=%s  急停=%d' % ('%.2fmA' % ma if ma is not None else '-', v('ES')),
                 '→清洗机 R0 Ready=%d R1过热=%d R2漏水=%d R3轻=%d R4重=%d' % tuple(
                     v(k) for k in ('R0', 'R1', 'R2', 'R3', 'R4')),
                 '        PLC通信异常=%d  温水器加热=%d' % (v('CF'), v('PWR'))]
        fr = rec.frames_between(t - 0.6, t + 0.6)
        if not fr:
            lines.append('\n附近没有报文')
            return '\n'.join(lines)
        inside = [f for f in fr if f.t0 <= t <= f.t1 + 0.002]
        f = inside[0] if inside else min(fr, key=lambda f: min(abs(f.t0 - t), abs(f.t1 - t)))
        lines.append('')
        lines.append('%s  %s   %.3f→%.3f s' % (f.dir, f.desc, f.t0, f.t1))
        lines.append('%d 字节 @%dbps = %.1f ms   [%s]' % (len(f.raw), E.BAUD, (f.t1 - f.t0) * 1000,
                                                     sim.codec.name))
        lines.append(f.hex())
        for name, hx, meaning in sim.codec.fields(f.raw, f.dir == 'RX'):
            lines.append(' %-4s %-14s %s' % (name, hx, meaning))
        if f.note:
            lines.append('※ ' + f.note)
        return '\n'.join(lines)


if __name__ == '__main__':
    App().run()
