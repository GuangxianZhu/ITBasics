# -*- coding: utf-8 -*-
"""
三菱 PLC  IO ↔ RS-485 联动演示  (KELK 温水器 / 虚构协议)

运行:  pip install panda3d
       python plc485_sim.py

操作:
  左侧按钮        X0~X6 输入、SV 设定、急停（按下锁定，再按解除）
  右侧用例        点击自动演示 16 个用例（会先重置）
  右侧故障注入    断线 / 断流 / 过温 / BCC错误 / 响应丢失 / 现场停止
  空格            暂停 / 继续
  暂停时          点击时序图任意位置 → 查看该时刻 IO 和最近的报文（逐字段解码）
                  ← →  移动查看光标（Shift 加大步长）   [  ]  跳到上 / 下一条命令帧
  R               重置

说明:
  * 协议是虚构的，全部集中在 FakeProtocol 一个类。换成真规格书时只改这个类
    （以及 Heater.receive 里对应的命令处理）。
  * 急停走硬线，不经过 485：X4 直接接温水器的急停回路；485 只是事后补发停止并确认。
  * Y12「加热许可」也是硬线：通信异常时 PLC 断开它，温水器靠硬线停下。
"""
import os
import math
import heapq
import bisect

from panda3d.core import loadPrcFileData

loadPrcFileData('', '''
win-size 1600 900
window-title PLC IO <-> RS-485 联动演示 (虚构协议)
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

# ============================================================
#  常量
# ============================================================
BAUD = 9600            # bps, 8N1 → 每字节 10 bit
RESP_DELAY = 0.015     # 温水器收到后多久开始回复 (s)
STEP = 0.002           # 仿真步长 (s)
INLET_T = 22.0         # 入口水温 ℃

STX, ETX = 0x02, 0x03


# ============================================================
#  虚构协议（只有这里和 Heater.receive 需要换成真规格）
# ============================================================
class FakeProtocol:
    """
    请求:  STX | 站号(2) | 命令(2) | 数据(n) | ETX | BCC
    响应:  STX | 站号(2) | 命令(2) | 'A'/'N' | 数据(n) | ETX | BCC
    BCC = 站号 ~ ETX 的 XOR，全部 ASCII
    """
    ADDR = b'01'
    CMD = {'RM': '远程切换', 'RN': '运转', 'ST': '停止', 'SV': '写设定温度',
           'RS': '读状态', 'AR': '报警复位'}
    NAK = {'01': 'BCC错误', '02': '本地模式中', '03': '联锁不成立(流量/许可)',
           '04': '报警中/原因未消除', '05': '急停输入中'}

    @staticmethod
    def bcc(body):
        x = 0
        for b in body:
            x ^= b
        return x

    def build_request(self, cmd, data=''):
        body = self.ADDR + cmd.encode() + data.encode() + bytes([ETX])
        return bytes([STX]) + body + bytes([self.bcc(body)])

    def build_response(self, cmd, ok, data=''):
        body = self.ADDR + cmd.encode() + (b'A' if ok else b'N') + data.encode() + bytes([ETX])
        return bytes([STX]) + body + bytes([self.bcc(body)])

    def parse(self, raw, is_response):
        if len(raw) < 7 or raw[0] != STX or raw[-2] != ETX:
            return None
        p = {'addr': raw[1:3].decode(errors='replace'),
             'cmd': raw[3:5].decode(errors='replace'),
             'bcc_ok': raw[-1] == self.bcc(raw[1:-1]),
             'bcc_calc': self.bcc(raw[1:-1])}
        if is_response:
            p['ok'] = raw[5:6] == b'A'
            p['data'] = raw[6:-2].decode(errors='replace')
        else:
            p['data'] = raw[5:-2].decode(errors='replace')
        return p

    # 状态数据: PV(4位 ×0.1℃) + 流量(3位 ×0.1L/min) + 状态位(2位HEX)
    @staticmethod
    def encode_status(pv, flow, bits):
        return '%04d%03d%02X' % (int(round(pv * 10)), int(round(flow * 10)), bits)

    @staticmethod
    def decode_status(data):
        return {'pv': int(data[0:4]) / 10.0, 'flow': int(data[4:7]) / 10.0,
                'bits': int(data[7:9], 16)}

    BITS = ['远程', '运转中', '加热电源', '流量OK', '报警', 'E1空焚', 'E2过温', 'E3急停']

    def fields(self, raw, is_response):
        """给详情面板用：逐字段拆开"""
        h = lambda bs: ' '.join('%02X' % b for b in bs)
        out = [('STX', h(raw[0:1]), '帧头')]
        out.append(('站号', h(raw[1:3]), "'%s'" % raw[1:3].decode(errors='replace')))
        c = raw[3:5].decode(errors='replace')
        out.append(('命令', h(raw[3:5]), "'%s' %s" % (c, self.CMD.get(c, '?'))))
        if is_response:
            k = raw[5:6].decode(errors='replace')
            out.append(('结果', h(raw[5:6]), "'%s' %s" % (k, 'ACK 正常' if k == 'A' else 'NAK 拒绝')))
            data = raw[6:-2]
        else:
            data = raw[5:-2]
        ds = data.decode(errors='replace')
        meaning = "'%s'" % ds if ds else '(无)'
        if is_response and c == 'RS' and len(ds) == 9:
            s = self.decode_status(ds)
            on = [n for i, n in enumerate(self.BITS) if s['bits'] >> i & 1]
            meaning = 'PV=%.1f℃ 流量=%.1f 位:%s' % (s['pv'], s['flow'], ','.join(on) or '无')
        elif is_response and raw[5:6] == b'N':
            meaning = "'%s' %s" % (ds, self.NAK.get(ds, '?'))
        elif c == 'SV' and ds:
            meaning = "'%s' = %.1f℃" % (ds, int(ds) / 10.0)
        out.append(('数据', h(data) if data else '-', meaning))
        out.append(('ETX', h(raw[-2:-1]), '帧尾'))
        calc = self.bcc(raw[1:-1])
        ok = '✓' if calc == raw[-1] else '✗ 不符!'
        out.append(('BCC', h(raw[-1:]), '计算值=%02X %s' % (calc, ok)))
        return out


# ============================================================
#  帧 / 记录器
# ============================================================
class Frame:
    def __init__(self, t0, direction, raw, desc, kind, cause=None):
        self.t0 = t0
        self.t1 = t0 + len(raw) * 10.0 / BAUD
        self.dir = direction      # 'TX' PLC→温水器 / 'RX' 温水器→PLC
        self.raw = raw
        self.desc = desc
        self.kind = kind          # TX: cmd/poll   RX: ack/nak/status
        self.cause = cause        # (信号key, 时刻) 用于画因果虚线
        self.lost = False
        self.corrupt = False
        self.note = ''

    def hex(self):
        return ' '.join('%02X' % b for b in self.raw)

    @property
    def important(self):
        return self.kind not in ('poll', 'status') or self.lost


class Recorder:
    def __init__(self):
        self.sig = {}
        self.pv_t, self.pv_v = [], []
        self.frames, self.frame_t = [], []
        self.log = []

    def set(self, key, t, v):
        ts, vs = self.sig.setdefault(key, ([], []))
        if not vs or vs[-1] != v:
            ts.append(t)
            vs.append(v)

    def value_at(self, key, t):
        ts, vs = self.sig.get(key, ([], []))
        i = bisect.bisect_right(ts, t) - 1
        return vs[i] if i >= 0 else 0

    def segments(self, key, a, b):
        ts, vs = self.sig.get(key, ([], []))
        i = bisect.bisect_right(ts, a) - 1
        v = vs[i] if i >= 0 else 0
        out, cur, j = [], a, i + 1
        while j < len(ts) and ts[j] < b:
            out.append((cur, ts[j], v))
            cur, v = ts[j], vs[j]
            j += 1
        out.append((cur, b, v))
        return out

    def add_frame(self, f):
        self.frames.append(f)
        self.frame_t.append(f.t0)

    def frames_between(self, a, b):
        i = bisect.bisect_left(self.frame_t, a - 0.05)
        j = bisect.bisect_right(self.frame_t, b)
        return self.frames[i:j]

    def pv_between(self, a, b):
        i = max(0, bisect.bisect_left(self.pv_t, a) - 1)
        j = bisect.bisect_right(self.pv_t, b) + 1
        return list(zip(self.pv_t[i:j], self.pv_v[i:j]))


# ============================================================
#  温水器模型（从站）
# ============================================================
class Heater:
    def __init__(self, sim):
        self.sim = sim
        self.remote = False
        self.running = False
        self.sv = 80.0
        self.pv = INLET_T
        self.flow = 0.0
        self.alarm = None          # 'E1' 空焚  'E2' 过温  'E3' 急停
        self.empty_timer = 0.0
        # 硬线输入
        self.estop_in = False      # X4 直接接过来
        self.permit_in = False     # PLC Y12
        self.valve_in = False      # X2 通水阀

    @property
    def flow_ok(self):
        return self.flow >= 3.0

    @property
    def power(self):
        # 加热电源：硬线条件（急停/许可）+ 自身状态
        return (self.running and self.permit_in and not self.estop_in
                and self.alarm is None)

    def bits(self):
        b = 0
        for i, v in enumerate([self.remote, self.running, self.power, self.flow_ok,
                               self.alarm is not None, self.alarm == 'E1',
                               self.alarm == 'E2', self.alarm == 'E3']):
            if v:
                b |= 1 << i
        return b

    def set_alarm(self, code, text):
        if self.alarm is None:
            self.alarm = code
            self.running = False
            self.sim.log('alarm', '温水器报警 %s：%s' % (code, text))

    def step(self, dt):
        sim = self.sim
        target = 12.0 if (self.valve_in and not sim.fault['clog']) else 0.0
        self.flow += (target - self.flow) * min(1.0, dt / 0.8)

        if self.estop_in:
            self.set_alarm('E3', '急停输入（硬线）→ 电源已切断')
        if self.running and not self.permit_in:
            self.running = False
            sim.log('hw', '温水器：Y12 加热许可(硬线)断开 → 停止加热')
        if self.running and not self.flow_ok:
            self.empty_timer += dt
            if self.empty_timer > 0.8:
                self.set_alarm('E1', '运转中流量不足 → 空焚保护')
        else:
            self.empty_timer = 0.0

        if self.power:
            tgt = 98.0 if sim.fault['overtemp'] else self.sv
            self.pv += (tgt - self.pv) * min(1.0, dt / 2.5)
        else:
            k = 5.0 if self.flow_ok else 25.0
            self.pv += (INLET_T - self.pv) * min(1.0, dt / k)
        if self.pv > 90.0:
            self.set_alarm('E2', '出口温度 > 90℃')

    def local_stop(self):
        if self.running:
            self.running = False
        self.sim.log('hw', '温水器：现场面板被按了停止（PLC 并不知道）')

    # ---- 收到 PLC 的帧 ----
    def receive(self, f):
        sim, pr = self.sim, self.sim.proto
        p = pr.parse(f.raw, False)
        cmd = p['cmd'] if p else '??'
        if p is None or not p['bcc_ok']:
            return self.reply(cmd, False, '01')
        d = p['data']
        if cmd == 'RS':
            return self.reply(cmd, True, pr.encode_status(self.pv, self.flow, self.bits()))
        if cmd == 'RM':
            self.remote = d == '1'
            return self.reply(cmd, True)
        if cmd == 'ST':                      # 停止：本地模式也接受（安全优先）
            self.running = False
            return self.reply(cmd, True)
        if not self.remote:
            return self.reply(cmd, False, '02')
        if cmd == 'SV':
            self.sv = int(d) / 10.0
            return self.reply(cmd, True)
        if cmd == 'RN':
            if self.alarm:
                return self.reply(cmd, False, '04')
            if not self.flow_ok or not self.permit_in or self.estop_in:
                return self.reply(cmd, False, '03')
            self.running = True              # 已在运转也回 ACK（幂等）
            return self.reply(cmd, True)
        if cmd == 'AR':
            if self.estop_in:
                return self.reply(cmd, False, '05')
            if self.alarm == 'E2' and self.pv > 85:
                return self.reply(cmd, False, '04')
            self.alarm = None
            return self.reply(cmd, True)
        return self.reply(cmd, False, '01')

    def reply(self, cmd, ok, data=''):
        sim = self.sim
        raw = sim.proto.build_response(cmd, ok, data)
        if cmd == 'RS' and ok:
            kind, desc = 'status', '状态回复'
        elif ok:
            kind, desc = 'ack', 'ACK %s' % cmd
        else:
            kind, desc = 'nak', 'NAK %s %s' % (data, sim.proto.NAK.get(data, ''))
        sim.at(sim.t + RESP_DELAY,
               lambda: sim.transmit('RX', raw, desc, kind, deliver=sim.plc.on_response))


# ============================================================
#  PLC 逻辑（主站）
# ============================================================
class PLC:
    POLL = 0.5
    TIMEOUT = 0.2
    RETRY = 3
    GAP = 0.005

    def __init__(self, sim):
        self.sim = sim
        self.prev = {k: 0 for k in sim.XKEYS}
        self.queue = []
        self.txn = None
        self.next_free = 0.0
        self.next_poll = 0.0
        self.status = None
        self.want_run = False
        self.estop_latched = False
        self.comm_alarm = False
        self.plc_alarm = None
        self.mismatch = 0
        self.Y = {'Y10': 0, 'Y11': 0, 'Y12': 0, 'Y13': 0}

    # ---- 状态位读取 ----
    def sbit(self, i):
        return bool(self.status and (self.status['bits'] >> i) & 1)

    def enqueue(self, cmd, data, desc, cause=None):
        if cmd == 'SV':                       # 设定值只保留最新一条
            self.queue = [c for c in self.queue if c['cmd'] != 'SV']
        self.queue.append({'cmd': cmd, 'data': data, 'desc': desc,
                           'cause': cause, 'poll': False, 'tries': 0})

    def on_sv_change(self):
        s = self.sim
        if s.X['X1']:
            self.enqueue('SV', '%04d' % int(round(s.sv * 10)), '写设定温度 SV=%.1f℃' % s.sv)
        else:
            s.log('plc', 'SV=%.1f℃ 存入 D 寄存器（未在线，上线时再写）' % s.sv)

    def try_start(self, cause):
        s, X = self.sim, self.sim.X
        why = []
        if not X['X1']:
            why.append('未在线X1')
        if not X['X2']:
            why.append('未通水X2')
        if self.estop_latched:
            why.append('急停未复位')
        if self.comm_alarm:
            why.append('通信异常未复位')
        if self.plc_alarm:
            why.append('PLC报警未复位')
        if self.sbit(4):
            why.append('温水器报警中')
        if why:
            s.log('plc', 'X3↑ 但 PLC 联锁不成立：%s → 不发送' % '、'.join(why))
            return
        s.log('plc', 'X3↑ 联锁OK → 排队：SV 写入 + RN 运转')
        self.enqueue('SV', '%04d' % int(round(s.sv * 10)), '写设定温度 SV=%.1f℃' % s.sv, cause)
        self.enqueue('RN', '', '运转', cause)

    def reset_alarms(self):
        s, X = self.sim, self.sim.X
        if X['X4']:
            s.log('plc', 'X6 确认：急停仍按下 → 不能复位')
            return
        self.estop_latched = False
        self.comm_alarm = False
        self.plc_alarm = None
        self.mismatch = 0
        s.log('plc', 'X6 确认：PLC 侧报警复位，Y12 许可恢复')
        if X['X1']:
            self.enqueue('AR', '', '报警复位', ('X6', s.t))
        if X['X3']:
            s.log('plc', '注意：X3 仍为 ON，不会自动再启动 → 需重新给上升沿')

    # ---- 每个扫描周期 ----
    def scan(self):
        s, X, t = self.sim, self.sim.X, self.sim.t
        rise = lambda k: X[k] and not self.prev[k]
        fall = lambda k: not X[k] and self.prev[k]

        if rise('X4'):
            self.estop_latched = True
            self.want_run = False
            s.log('hw', 'X4 急停：硬线直接切断温水器电源（不经过485）')
            self.enqueue('ST', '', '停止（急停后补发确认）', ('X4', t))
        if fall('X4'):
            s.log('plc', '急停已解除 → 请按 X6 确认复位')
        if rise('X6'):
            self.reset_alarms()
        if rise('X1'):
            s.log('plc', 'X1 在线：开始轮询，同步远程/SV')
            self.next_poll = t
            if X['X0']:
                self.enqueue('RM', '1', '切换远程', ('X1', t))
            self.enqueue('SV', '%04d' % int(round(s.sv * 10)), '写设定温度 SV=%.1f℃' % s.sv)
        if fall('X1'):
            s.log('plc', 'X1 离线：停止通信，Y12 许可断开')
            self.want_run = False
        if rise('X0'):
            self.enqueue('RM', '1', '切换远程', ('X0', t))
        if fall('X0'):
            self.enqueue('RM', '0', '切换本地', ('X0', t))
        if rise('X3'):
            self.try_start(('X3', t))
        if fall('X3') and (self.want_run or self.sbit(1)):
            self.want_run = False
            self.enqueue('ST', '', '停止', ('X3', t))
        if rise('X5'):
            self.want_run = False
            s.log('plc', 'X5 停止按钮')
            self.enqueue('ST', '', '停止', ('X5', t))
        self.prev = dict(X)

        # ---- 输出 ----
        self.Y['Y12'] = int(bool(X['X1'] and not self.estop_latched and not self.comm_alarm))
        fresh = self.status is not None and not self.comm_alarm and X['X1']
        self.Y['Y10'] = int(fresh and self.sbit(1))
        self.Y['Y13'] = int(fresh and self.sbit(0))
        self.Y['Y11'] = int(self.estop_latched or self.comm_alarm or bool(self.plc_alarm)
                            or (fresh and self.sbit(4)))
        s.heater.permit_in = bool(self.Y['Y12'])
        self.comm()

    # ---- 通信调度（半双工：一问一答）----
    def comm(self):
        s, t = self.sim, self.sim.t
        if self.txn:
            if t >= self.txn['deadline']:
                self.retry('超时无响应')
            return
        if t < self.next_free:
            return
        if not s.X['X1']:
            if self.queue:
                s.log('plc', '未在线：%d 条命令不发送（上线时再同步）' % len(self.queue))
                self.queue.clear()
            return
        if self.queue:
            self.send(self.queue.pop(0))
        elif t >= self.next_poll:
            self.next_poll = t + (1.0 if self.comm_alarm else self.POLL)
            self.send({'cmd': 'RS', 'data': '', 'desc': '读状态', 'cause': None,
                       'poll': True, 'tries': 0})

    def send(self, c):
        s = self.sim
        raw = s.proto.build_request(c['cmd'], c['data'])
        corrupt = False
        if not c['poll'] and s.once['bcc']:
            s.once['bcc'] = False
            raw = raw[:-1] + bytes([raw[-1] ^ 0x5A])
            corrupt = True
        f = s.transmit('TX', raw, c['desc'], 'poll' if c['poll'] else 'cmd',
                       cause=c['cause'] if c['tries'] == 0 else None,
                       deliver=s.heater.receive)
        f.corrupt = corrupt
        if corrupt:
            f.note = '线路噪声：BCC 被破坏'
        if not c['poll']:
            tag = '（重发%d）' % c['tries'] if c['tries'] else ''
            s.log('tx', '%s %s%s  %s' % (c['cmd'], c['desc'], tag, f.hex()))
        self.txn = dict(c, frame=f, deadline=f.t1 + self.TIMEOUT)

    def retry(self, reason):
        s, c = self.sim, self.txn
        self.txn = None
        self.next_free = s.t + self.GAP
        if c['poll'] and self.comm_alarm:
            return
        c['tries'] += 1
        if c['tries'] <= self.RETRY:
            s.log('nak', '%s %s → 重发 (%d/%d)' % (c['cmd'], reason, c['tries'], self.RETRY))
            self.queue.insert(0, c)
        else:
            s.log('alarm', '%s 重试 %d 次失败 → 通信异常' % (c['cmd'], self.RETRY))
            if not self.comm_alarm:
                self.comm_alarm = True
                self.want_run = False
                s.log('hw', 'PLC：Y12 加热许可(硬线)断开 → 温水器靠硬线停下')

    def on_response(self, f):
        s = self.sim
        p = s.proto.parse(f.raw, True)
        if not self.txn:
            return
        c = self.txn
        if p is None or not p['bcc_ok'] or p['cmd'] != c['cmd']:
            return self.retry('响应异常')
        self.txn = None
        self.next_free = s.t + self.GAP
        if self.comm_alarm and c['poll']:
            pass
        if p['ok']:
            if c['cmd'] == 'RS':
                self.on_status(s.proto.decode_status(p['data']))
                if self.comm_alarm and not getattr(self, '_recover_logged', False):
                    s.log('plc', '通信已恢复 → 请按 X6 确认复位')
                    self._recover_logged = True
                return
            s.log('rx', 'ACK %s  %s' % (c['cmd'], f.hex()))
            if c['cmd'] == 'RN':
                self.want_run = True
                self.mismatch = 0
            elif c['cmd'] == 'ST':
                self.want_run = False
            elif c['cmd'] == 'AR':
                self._recover_logged = False
        else:
            code = p['data']
            if code == '01':
                self.txn = c
                return self.retry('NAK01 BCC错误')
            s.log('nak', 'NAK %s %s：%s 被拒绝' % (code, s.proto.NAK.get(code, ''), c['cmd']))
            if c['cmd'] == 'RN':
                self.want_run = False

    def on_status(self, st):
        s = self.sim
        old = self.status
        self.status = st
        b = st['bits']
        if b >> 4 & 1 and not (old and old['bits'] >> 4 & 1):
            code = 'E1 空焚' if b >> 5 & 1 else 'E2 过温' if b >> 6 & 1 else 'E3 急停' if b >> 7 & 1 else '?'
            s.log('alarm', 'PLC 读到温水器报警 %s → Y11 报警' % code)
            self.want_run = False
        # 对账：PLC 认为在运转，温水器却说停着
        if self.want_run and not (b >> 1 & 1) and not (b >> 4 & 1):
            self.mismatch += 1
            if self.mismatch >= 2:
                self.plc_alarm = '运转状态不一致'
                self.want_run = False
                s.log('alarm', '对账：PLC 要求运转，温水器连续 2 次回报停止 → 状态不一致报警')
        else:
            self.mismatch = 0


# ============================================================
#  仿真总控
# ============================================================
class Sim:
    XKEYS = ['X0', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6']

    def __init__(self):
        self.proto = FakeProtocol()
        self.reset()

    def reset(self):
        self.t = 0.0
        self.events = []
        self.seq = 0
        self.X = {k: 0 for k in self.XKEYS}
        self.press_until = {}
        self.sv = 80.0
        self.fault = {'cut': False, 'clog': False, 'overtemp': False}
        self.once = {'bcc': False, 'lossreply': False}
        self.rec = Recorder()
        self.heater = Heater(self)
        self.plc = PLC(self)
        self.script = []
        self.next_pv = 0.0
        self.new_frames = []
        self.rec.set('SV', 0.0, self.sv)
        self.record()

    def at(self, t, fn):
        heapq.heappush(self.events, (t, self.seq, fn))
        self.seq += 1

    def log(self, kind, text):
        self.rec.log.append((self.t, kind, text))

    # ---- 总线 ----
    def transmit(self, direction, raw, desc, kind, cause=None, deliver=None):
        f = Frame(self.t, direction, raw, desc, kind, cause)
        self.rec.add_frame(f)
        self.new_frames.append(f)

        def done():
            if self.fault['cut']:
                f.lost = True
                f.note = '485 断线：对方没收到'
                return
            if direction == 'RX' and kind in ('ack', 'nak') and self.once['lossreply']:
                self.once['lossreply'] = False
                f.lost = True
                f.note = '响应在线路上丢失（注入）'
                self.log('nak', 'RX %s 在线路上丢失（PLC 收不到）' % desc)
                return
            if deliver:
                deliver(f)
        self.at(f.t1, done)
        return f

    # ---- 操作 ----
    def set_x(self, k, v, src='操作'):
        v = 1 if v else 0
        if self.X[k] != v:
            self.X[k] = v
            self.log('case' if src == '用例' else 'op', '%s → %d' % (INPUT_NAMES[k], v))

    def press(self, k, src='操作'):
        self.X[k] = 1
        self.press_until[k] = self.t + 0.3
        self.log('case' if src == '用例' else 'op', '按下 %s' % INPUT_NAMES[k])

    def set_sv(self, v):
        v = max(25.0, min(85.0, round(v, 1)))
        if v != self.sv:
            self.sv = v
            self.rec.set('SV', self.t, v)
            self.plc.on_sv_change()

    def set_fault(self, name, v):
        if name in self.fault:
            self.fault[name] = bool(v)
            self.log('op', '故障 %s → %s' % (FAULT_NAMES[name], 'ON' if v else 'OFF'))
        elif name in self.once:
            self.once[name] = True
            self.log('op', '故障 %s：下一条命令生效' % FAULT_NAMES[name])
        elif name == 'localstop':
            self.heater.local_stop()

    def do_action(self, a):
        k = a[0]
        if k == 'x':
            self.set_x(a[1], a[2], '用例')
        elif k == 'press':
            self.press(a[1], '用例')
        elif k == 'fault':
            self.set_fault(a[1], a[2] if len(a) > 2 else 1)
        elif k == 'sv':
            self.log('case', 'SV → %.1f℃' % a[1])
            self.set_sv(a[1])
        elif k == 'note':
            self.log('case', a[1])

    def load_case(self, case):
        self.reset()
        self.script = sorted(case[2], key=lambda x: x[0])
        self.log('case', '%s 开始' % case[0])

    # ---- 推进 ----
    def step(self, dt):
        end = self.t + dt
        while self.events and self.events[0][0] <= end:
            te, _, fn = heapq.heappop(self.events)
            self.t = max(self.t, te)
            fn()
        self.t = end
        while self.script and self.script[0][0] <= self.t:
            self.do_action(self.script.pop(0)[1])
        for k, u in list(self.press_until.items()):
            if self.t >= u:
                self.X[k] = 0
                del self.press_until[k]
        self.heater.estop_in = bool(self.X['X4'])   # 硬线！
        self.heater.valve_in = bool(self.X['X2'])
        self.plc.scan()
        self.heater.step(dt)
        self.record()

    def record(self):
        t, r = self.t, self.rec
        for k in self.XKEYS:
            r.set(k, t, self.X[k])
        for k, v in self.plc.Y.items():
            r.set(k, t, v)
        r.set('PWR', t, int(self.heater.power))
        if t >= self.next_pv:
            r.pv_t.append(t)
            r.pv_v.append(self.heater.pv)
            self.next_pv = t + 0.05


INPUT_NAMES = {'X0': 'X0 远程', 'X1': 'X1 在线', 'X2': 'X2 通水', 'X3': 'X3 加热ON',
               'X4': 'X4 急停', 'X5': 'X5 停止', 'X6': 'X6 确认/复位'}
FAULT_NAMES = {'cut': '485断线', 'clog': '断流(堵塞)', 'overtemp': '过温(控制失效)',
               'bcc': 'BCC错误', 'lossreply': '响应丢失', 'localstop': '现场面板停止'}

# ============================================================
#  用例
# ============================================================
BASE = [(0.3, ('x', 'X0', 1)), (1.0, ('x', 'X1', 1)), (2.0, ('x', 'X2', 1)), (4.0, ('x', 'X3', 1))]
PRE = [(0.3, ('x', 'X0', 1)), (1.0, ('x', 'X1', 1)), (2.0, ('x', 'X2', 1))]

CASES = [
    ('① 正常启动',
     '远程→在线→通水→加热ON。看 X3 上升沿后排队发出 SV 和 RN，ACK 回来后加热电源 ON；'
     'Y10 运转中灯要等下一次轮询读到状态才亮（有延迟）。',
     BASE),
    ('② 加热OFF停止',
     '运转中把 X3 拉低 → 下降沿发 ST 停止 → 电源 OFF，之后关水。',
     BASE + [(11, ('x', 'X3', 0)), (14, ('x', 'X2', 0))]),
    ('③ 停止按钮',
     '运转中按 X5 停止 → 发 ST。X3 仍为 ON 也不会自动再启动，要重新给 X3 上升沿。',
     BASE + [(11, ('press', 'X5')), (16, ('x', 'X3', 0)), (16.5, ('x', 'X3', 1))]),
    ('④ 修改设定温度',
     '运转中改 SV：PLC 只在值变化时发一次 SV 写入；PV 曲线跟着走。',
     BASE + [(10, ('sv', 60)), (14, ('sv', 75))]),
    ('⑤ 联锁：未通水就加热',
     '没通水就给加热 ON → PLC 自己判断联锁不成立，一帧都不发。通水后重新给上升沿才启动。',
     [(0.3, ('x', 'X0', 1)), (1.0, ('x', 'X1', 1)), (3.0, ('x', 'X3', 1)),
      (6.0, ('x', 'X2', 1)), (8.5, ('x', 'X3', 0)), (9.0, ('x', 'X3', 1))]),
    ('⑥ 通水未稳定就加热',
     'X2 刚打开流量还没上来就加热 → PLC 联锁过了（只看 X2），温水器自己检查流量回 NAK03。两层联锁。',
     [(0.3, ('x', 'X0', 1)), (1.0, ('x', 'X1', 1)), (3.0, ('x', 'X2', 1)),
      (3.1, ('x', 'X3', 1)), (7.0, ('x', 'X3', 0)), (7.5, ('x', 'X3', 1))]),
    ('⑦ 本地模式拒绝',
     '没切远程就加热 → 温水器回 NAK02 本地模式。切远程后再给上升沿就正常。（ST 停止在本地也接受）',
     [(1.0, ('x', 'X1', 1)), (2.0, ('x', 'X2', 1)), (4.0, ('x', 'X3', 1)),
      (8.0, ('x', 'X0', 1)), (10.0, ('x', 'X3', 0)), (10.5, ('x', 'X3', 1))]),
    ('⑧ 运行中断流→空焚',
     '运转中流量掉了 → 温水器自己保护（E1）停电源 → PLC 下次轮询才知道 → Y11。'
     '恢复流量后按 X6 确认，再给 X3 上升沿。',
     BASE + [(9, ('fault', 'clog', 1)), (13, ('fault', 'clog', 0)), (15, ('press', 'X6')),
             (17, ('x', 'X3', 0)), (17.5, ('x', 'X3', 1))]),
    ('⑨ 急停→解除→确认',
     '急停瞬间：加热电源同一时刻掉下（硬线），485 的 ST 是之后补发的。'
     '解除后按 X6 → 发 AR 复位，再给 X3 上升沿。',
     BASE + [(9, ('x', 'X4', 1)), (12, ('x', 'X4', 0)), (13.5, ('press', 'X6')),
             (16, ('x', 'X3', 0)), (16.5, ('x', 'X3', 1))]),
    ('⑩ 急停未解除就确认',
     '急停还按着就按 X6 → PLC 拒绝复位。解除后再按 X6 才有效。',
     BASE + [(8, ('x', 'X4', 1)), (10, ('press', 'X6')), (12, ('x', 'X4', 0)),
             (13, ('press', 'X6')), (15, ('x', 'X3', 0)), (15.5, ('x', 'X3', 1))]),
    ('⑪ 过温报警',
     '控制失效 PV 冲过 90℃ → 温水器 E2 自停 → PLC 轮询读到报警。温度降下来后 X6 复位。',
     BASE + [(8, ('fault', 'overtemp', 1)), (12.5, ('fault', 'overtemp', 0)),
             (15, ('press', 'X6')), (17, ('x', 'X3', 0)), (17.5, ('x', 'X3', 1))]),
    ('⑫ 485断线',
     '线断了：轮询超时→重发3次→通信异常 → PLC 断开 Y12 硬线许可 → 温水器停。'
     '接回后通信恢复，但要人按 X6 确认才复位。',
     BASE + [(9, ('fault', 'cut', 1)), (13, ('fault', 'cut', 0)), (15, ('press', 'X6')),
             (17, ('x', 'X3', 0)), (17.5, ('x', 'X3', 1))]),
    ('⑬ BCC错误→NAK→重发',
     '噪声把 SV 帧的 BCC 弄坏 → 温水器回 NAK01 → PLC 自动重发 → 成功。暂停后点那几帧看 BCC 校验。',
     PRE + [(3.9, ('fault', 'bcc')), (4.0, ('x', 'X3', 1))]),
    ('⑭ 响应丢失→超时重发',
     '温水器执行了 SV 但 ACK 在线上丢了 → PLC 超时重发 → 温水器再执行一次（幂等，结果不变）。',
     PRE + [(3.9, ('fault', 'lossreply')), (4.0, ('x', 'X3', 1))]),
    ('⑮ 现场停止(状态不一致)',
     '有人在温水器面板上按了停止，PLC 不知道 → 轮询对账连续 2 次不一致 → 报警，不自作主张重发 RN。',
     BASE + [(9, ('fault', 'localstop')), (13, ('press', 'X6')),
             (15, ('x', 'X3', 0)), (15.5, ('x', 'X3', 1))]),
    ('⑯ 断线中急停仍有效',
     '485 刚断（还没判定通信异常）就按急停 → 电源照样立刻断。这就是急停必须走硬线的原因。',
     BASE + [(9, ('fault', 'cut', 1)), (9.1, ('x', 'X4', 1)), (12, ('x', 'X4', 0)),
             (12.5, ('fault', 'cut', 0)), (14, ('press', 'X6')),
             (16, ('x', 'X3', 0)), (16.5, ('x', 'X3', 1))]),
]


# ============================================================
#  绘图小工具
# ============================================================
class Batch:
    """一次性堆线段和矩形，生成一个 GeomNode（2D, pixel2d 坐标, y 向下）"""

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
    """沿 +Z 的圆柱，底面在 z=0"""
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
    base = 2 * (seg + 1)
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
             '/System/Library/Fonts/PingFang.ttc',
             '/System/Library/Fonts/Hiragino Sans GB.ttc']
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
C_IN = (0.55, 0.75, 1.0, 1)
C_OUT = (0.45, 0.9, 0.6, 1)
C_RED = (1.0, 0.35, 0.35, 1)
C_HW = (1.0, 0.68, 0.25, 1)
C_PWR = (1.0, 0.5, 0.15, 1)
C_TX = (0.62, 0.55, 1.0, 1)
C_RX = (0.25, 0.8, 0.62, 1)
C_CUR = (0.3, 0.6, 1.0, 1)
C_INS = (1.0, 0.85, 0.2, 1)
LOG_COL = {'tx': C_TX, 'rx': C_RX, 'nak': (1, 0.5, 0.45, 1), 'alarm': C_RED,
           'hw': C_HW, 'plc': (0.78, 0.8, 0.84, 1), 'op': (0.55, 0.75, 1.0, 1),
           'case': (0.6, 0.85, 1.0, 1)}
LOG_TAG = {'tx': 'TX ', 'rx': 'RX ', 'nak': '!! ', 'alarm': '报警', 'hw': '硬线',
           'plc': 'PLC', 'op': '操作', 'case': '用例'}

# 时序图
CH_X0, CH_X1 = 250, 1100
PX0, PX1 = 352, 1088
PW = PX1 - PX0
ROW_TOP = 40
RH = 26
ROWS = [('X0', 'X0 远程', C_IN), ('X1', 'X1 在线', C_IN), ('X2', 'X2 通水', C_IN),
        ('X3', 'X3 加热ON', C_IN), ('X5', 'X5 停止', C_IN), ('X6', 'X6 确认', C_IN),
        ('X4', 'X4 急停 硬线', C_RED), ('Y12', 'Y12 许可 硬线', C_HW),
        ('PWR', '加热电源', C_PWR), ('Y10', 'Y10 运转中', C_OUT),
        ('Y11', 'Y11 报警', C_RED), ('TX', '485 TX', C_TX), ('RX', '485 RX', C_RX)]
PV_TOP = ROW_TOP + len(ROWS) * RH + 4
PV_H = 80
CH_BOTTOM = PV_TOP + PV_H + 22
ROW_Y = {k: ROW_TOP + i * RH for i, (k, _, _) in enumerate(ROWS)}

# 3D 视口（右上）
V3_X0, V3_Y0, V3_X1, V3_Y1 = 1110, 0, 1600, 380
WIN_W, WIN_H = 1600, 900


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

        self.sim = Sim()
        self.paused = False
        self.speed = 1.0
        self.W = 20.0
        self.inspect_t = None
        self.case_desc = '自由操作模式：用左侧按钮自己拨 IO，或点右侧用例自动演示。'
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

    # ---------------- 文本工具 ----------------
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

    # ---------------- 静态背景 ----------------
    def build_static(self):
        b = Batch()
        for x1, y1, x2, y2 in ((0, 0, 242, 900), (CH_X0, 0, CH_X1, CH_BOTTOM),
                               (CH_X0, CH_BOTTOM + 6, 700, 900),
                               (708, CH_BOTTOM + 6, CH_X1, 900),
                               (V3_X0, V3_Y1 + 6, 1600, 900)):
            b.rect(x1, y1, x2, y2, PANEL)
            b.box(x1, y1, x2, y2, EDGE)
        for i, (k, _, _) in enumerate(ROWS):
            y = ROW_TOP + i * RH
            if i % 2 == 0:
                b.rect(CH_X0 + 1, y, CH_X1 - 1, y + RH, (1, 1, 1, 0.025))
        b.line(PX0, ROW_TOP, PX0, PV_TOP + PV_H, EDGE)
        b.line(CH_X0, ROW_Y['TX'], CH_X1, ROW_Y['TX'], EDGE)
        b.line(CH_X0, PV_TOP - 2, CH_X1, PV_TOP - 2, EDGE)
        np = self.pixel2d.attachNewNode(b.make('static'))
        np.setTransparency(TransparencyAttrib.MAlpha)

        for i, (k, name, col) in enumerate(ROWS):
            self.text(CH_X0 + 8, ROW_TOP + i * RH + 18, name, 13, col)
        self.text(CH_X0 + 8, PV_TOP + 20, 'PV ℃', 13, C_PWR)
        self.text(CH_X0 + 8, PV_TOP + 38, '-- SV', 12, C_HW)
        self.text(CH_X0 + 8, PV_TOP + 56, '-- 90 过温', 12, C_RED)
        self.text(10, 24, 'IO 面板（PLC 输入）', 15, TXT)
        self.text(10, 382, 'PLC 输出', 15, TXT)
        self.text(10, 540, '温水器状态（PLC 读到的）', 15, TXT)
        self.text(V3_X0 + 10, V3_Y1 + 28, '使用用例（点击自动演示）', 15, TXT)
        self.text(V3_X0 + 10, 694, '故障注入', 15, TXT)
        self.text(CH_X0 + 10, CH_BOTTOM + 26, '通信 / 事件日志', 14, TXT)
        self.text(10, 838, '空格 暂停/继续   R 重置\n暂停时点时序图查看\n←→ 移动  [ ] 跳命令帧',
                  12, DIM)

    # ---------------- 按钮 ----------------
    def button(self, label, x, y, w, h, cmd, args=None, size=14):
        return DirectButton(parent=self.pixel2d, text=label, text_scale=size,
                            text_fg=TXT, text_pos=(w / 2, -h / 2 - size * 0.35),
                            frameSize=(0, w, -h, 0), pos=(x, 0, -y),
                            frameColor=(0.22, 0.24, 0.28, 1), relief=DGG.FLAT,
                            command=cmd, extraArgs=args or [], pressEffect=1)

    def build_buttons(self):
        self.xbtn = {}
        for i, k in enumerate(['X0', 'X1', 'X2', 'X3']):
            self.xbtn[k] = self.button(INPUT_NAMES[k], 10, 38 + i * 40, 222, 34,
                                       self.ui_toggle, [k])
        self.xbtn['X5'] = self.button('X5 停止', 10, 200, 108, 34, self.ui_press, ['X5'])
        self.xbtn['X6'] = self.button('X6 确认/复位', 124, 200, 108, 34, self.ui_press, ['X6'], 13)
        self.xbtn['X4'] = self.button('X4 急停（按下锁定）', 10, 244, 222, 50,
                                      self.ui_toggle, ['X4'], 15)
        self.text(10, 322, 'SV', 14, DIM)
        self.sv_tn, _ = self.text(118, 322, '', 15, TXT, 'center')
        for dx, lbl, d in ((34, '-5', -5), (64, '-1', -1), (150, '+1', 1), (180, '+5', 5)):
            self.button(lbl, dx, 304, 28, 26, self.ui_sv, [d], 13)

        self.btn_pause = self.button('暂停', 10, 700, 222, 32, self.toggle_pause)
        self.spd_btn = {}
        for i, sp in enumerate([0.1, 0.25, 0.5, 1.0]):
            self.spd_btn[sp] = self.button('%gx' % sp, 10 + i * 56, 738, 52, 28,
                                           self.set_speed, [sp], 13)
        self.button('重置', 10, 772, 222, 30, self.reset)

        self.win_btn = {}
        for i, w in enumerate([20.0, 5.0, 1.0]):
            self.win_btn[w] = self.button('%gs' % w, 930 + i * 54, 8, 50, 22,
                                          self.set_window, [w], 12)

        for i, case in enumerate(CASES):
            c, r = i % 2, i // 2
            self.button(case[0], V3_X0 + 8 + c * 241, V3_Y1 + 40 + r * 31, 236, 27,
                        self.run_case, [i], 13)
        self.fbtn = {}
        for i, f in enumerate(['cut', 'clog', 'overtemp', 'bcc', 'lossreply', 'localstop']):
            c, r = i % 2, i // 2
            lbl = FAULT_NAMES[f] + ('（一次）' if f in ('bcc', 'lossreply', 'localstop') else '')
            self.fbtn[f] = self.button(lbl, V3_X0 + 8 + c * 241, 704 + r * 31, 236, 27,
                                       self.ui_fault, [f], 13)

    # ---------------- 动态文本 ----------------
    def build_texts(self):
        self.lamp_y = {'Y10': 400, 'Y11': 428, 'Y12': 456, 'Y13': 484}
        names = {'Y10': 'Y10 运转中', 'Y11': 'Y11 报警', 'Y12': 'Y12 加热许可（硬线）',
                 'Y13': 'Y13 远程中'}
        for k, y in self.lamp_y.items():
            self.text(42, y + 17, names[k], 13, TXT)
        self.status_tn, _ = self.text(12, 566, '', 13, TXT)
        self.head_tn, _ = self.text(CH_X0 + 10, 24, '', 14, TXT)
        self.tick_pool = [self.text(0, 0, '', 11, DIM, 'center') for _ in range(24)]
        self.lbl_pool = [self.text(0, 0, '', 10, TXT, 'center') for _ in range(60)]
        self.log_pool = [self.text(CH_X0 + 10, CH_BOTTOM + 50 + i * 17, '', 12, TXT)
                         for i in range(21)]
        self.detail_tn, _ = self.text(716, CH_BOTTOM + 26, '', 12, TXT)
        self.case_tn, _ = self.text(V3_X0 + 10, 818, '', 13, (0.75, 0.85, 1, 1),
                                    wrap=470 / 13.0)
        self.v3_tn, _ = self.text(V3_X0 + 8, 18, '', 12, TXT)

    # ---------------- 3D ----------------
    def build_3d(self):
        dr = self.camNode.getDisplayRegion(0)
        dr.setDimensions(V3_X0 / WIN_W, V3_X1 / WIN_W, 1 - V3_Y1 / WIN_H, 1 - V3_Y0 / WIN_H)
        dr.setClearColorActive(True)
        dr.setClearColor((0.13, 0.14, 0.17, 1))
        dr.setClearDepthActive(True)
        self.camLens.setAspectRatio((V3_X1 - V3_X0) / float(V3_Y1 - V3_Y0))
        self.camLens.setFov(52)
        self.camera.setPos(-0.2, -11.5, 3.6)
        self.camera.lookAt(-0.2, 0, 1.6)

        al = AmbientLight('a')
        al.setColor((0.45, 0.45, 0.5, 1))
        dl = DirectionalLight('d')
        dl.setColor((0.8, 0.8, 0.75, 1))
        dnp = self.render.attachNewNode(dl)
        dnp.setHpr(-30, -45, 0)
        self.render.setLight(self.render.attachNewNode(al))
        self.render.setLight(dnp)

        def solid(np, col, pos, parent=None):
            np.reparentTo(parent or self.render)
            np.setColor(*col)
            np.setPos(*pos)
            return np

        def glass(np, col, pos):
            solid(np, col, pos)
            np.setTransparency(TransparencyAttrib.MAlpha)
            np.setDepthWrite(False)
            np.setBin('transparent', 10)
            return np

        # 地面
        solid(make_box(11, 4, 0.05), (0.2, 0.21, 0.24, 1), (0, 0, -0.03))
        # PLC
        solid(make_box(1.3, 0.9, 1.8), (0.25, 0.3, 0.28, 1), (-3.8, 0, 0.9))
        self.leds = {}
        for i, k in enumerate(['Y10', 'Y11', 'Y12', 'Y13']):
            led = solid(make_box(0.18, 0.05, 0.14), (0.2, 0.2, 0.2, 1),
                        (-4.15 + i * 0.24, -0.47, 1.45))
            led.setLightOff()
            self.leds[k] = led
        # 急停按钮
        solid(make_box(0.6, 0.6, 0.5), (0.9, 0.75, 0.1, 1), (-2.5, -0.6, 0.25))
        self.estop3d = solid(make_cyl(0.22, 0.18), (0.6, 0.05, 0.05, 1), (-2.5, -0.6, 0.5))
        # 温水器机柜（半透明）
        glass(make_box(2.4, 1.3, 3.4), (0.6, 0.7, 0.8, 0.12), (2.6, 0, 1.7))
        # 石英管 + 卤素灯
        self.lamps = []
        for x in (2.1, 3.1):
            glass(make_cyl(0.32, 2.6), (0.8, 0.9, 1.0, 0.22), (x, 0, 0.35))
            lp = solid(make_cyl(0.07, 2.4), (0.3, 0.3, 0.3, 1), (x, 0, 0.45))
            lp.setLightOff()
            self.lamps.append(lp)
        # 水路：入口 → 管1上 → 跨到管2 → 管2下 → 出口
        self.path = [Point3(-0.6, 0, 0.25), Point3(2.1, 0, 0.25), Point3(2.1, 0, 3.05),
                     Point3(3.1, 0, 3.05), Point3(3.1, 0, 0.25), Point3(4.9, 0, 0.25)]
        ls = LineSegs()
        ls.setThickness(4)
        ls.setColor(0.35, 0.45, 0.6, 1)
        ls.moveTo(self.path[0])
        for p in self.path[1:]:
            ls.drawTo(p)
        np = self.render.attachNewNode(ls.create())
        np.setLightOff()
        seglen = [(self.path[i + 1] - self.path[i]).length() for i in range(len(self.path) - 1)]
        self.path_len = sum(seglen)
        self.seglen = seglen
        self.drops = []
        for i in range(26):
            d = solid(make_box(0.13, 0.13, 0.13), (0.3, 0.6, 1, 1), (0, 0, 0))
            d.setLightOff()
            self.drops.append(d)
        self.flow_phase = 0.0
        # 485 线 / 硬线
        ls = LineSegs()
        ls.setThickness(3)
        ls.setColor(*C_TX)
        ls.moveTo(-3.15, 0, 1.25)
        ls.drawTo(1.4, 0, 1.25)
        np = self.render.attachNewNode(ls.create())
        np.setLightOff()
        ls = LineSegs()
        ls.setThickness(3)
        ls.setColor(1, 1, 1, 1)
        ls.moveTo(-3.15, 0, 0.7)
        ls.drawTo(1.4, 0, 0.7)
        self.hw_line = self.render.attachNewNode(ls.create())
        self.hw_line.setLightOff()

        def label(s, pos, col=TXT, sc=0.32):
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
        label('PLC（三菱）', (-3.8, -0.5, 2.05))
        label('急停', (-2.5, -0.9, 0.85), C_RED, 0.26)
        label('KELK 温水器', (2.6, -0.7, 3.65))
        label('RS-485', (-0.9, 0, 1.4), C_TX, 0.28)
        label('硬线：急停 / Y12许可', (-0.9, 0, 0.82), C_HW, 0.24)
        solid(make_box(1.7, 0.05, 1.35), (0.05, 0.06, 0.07, 1), (2.6, -0.7, 2.05)).setLightOff()
        self.disp3d = label('', (2.6, -0.76, 2.5), (0.3, 1, 0.6, 1), 0.26)

    def path_point(self, s):
        s = s % self.path_len
        for i, L in enumerate(self.seglen):
            if s <= L:
                return self.path[i] + (self.path[i + 1] - self.path[i]) * (s / L), i
            s -= L
        return self.path[-1], len(self.seglen) - 1

    def update_3d(self, rdt):
        sim, h, plc = self.sim, self.sim.heater, self.sim.plc
        blink = int(globalClock.getFrameTime() * 4) % 2 == 0
        for k, led in self.leds.items():
            on = plc.Y[k]
            col = {'Y10': (0.2, 1, 0.4, 1), 'Y11': (1, 0.2, 0.2, 1),
                   'Y12': (1, 0.65, 0.1, 1), 'Y13': (0.3, 0.6, 1, 1)}[k]
            led.setColor(*(col if on else (0.18, 0.18, 0.18, 1)))
        for lp in self.lamps:
            if h.power:
                lp.setColor(1.0, 0.65 + 0.1 * math.sin(globalClock.getFrameTime() * 20), 0.2, 1)
            else:
                lp.setColor(0.3, 0.3, 0.3, 1)
        self.estop3d.setZ(0.42 if sim.X['X4'] else 0.5)
        self.estop3d.setColor(*((1, 0.1, 0.1, 1) if sim.X['X4'] and blink else (0.6, 0.05, 0.05, 1)))
        if sim.X['X4']:
            self.hw_line.setColor(*((1, 0.1, 0.1, 1) if blink else (0.4, 0.05, 0.05, 1)))
        elif plc.Y['Y12']:
            self.hw_line.setColor(*C_HW)
        else:
            self.hw_line.setColor(0.3, 0.25, 0.2, 1)
        # 水流
        if not self.paused:
            self.flow_phase += h.flow * 0.08 * rdt * max(self.speed, 0.25)
        heat = max(0.0, min(1.0, (h.pv - INLET_T) / 60.0))
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
        # 485 报文小方块
        for f in sim.new_frames:
            if f.kind in ('poll', 'status') and len(self.packets3d) > 8:
                continue
            col = C_TX if f.dir == 'TX' else C_RX
            if f.kind == 'nak':
                col = C_RED
            small = f.kind in ('poll', 'status')
            pk = make_box(0.16 if small else 0.26, 0.16 if small else 0.26, 0.16 if small else 0.26)
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
            x = -3.15 + 4.55 * (u if f.dir == 'TX' else 1 - u)
            pk.setPos(x, 0, 1.25 + (0.0 if f.dir == 'TX' else 0.18))
            if age < 0.7:
                keep.append(item)
            else:
                pk.removeNode()
        self.packets3d = keep
        a = h.alarm or ''
        self.disp3d.setText('%s %s\nPV %.1f℃\nSV %.1f℃\n%s' % (
            'REMOTE' if h.remote else 'LOCAL', 'RUN' if h.running else 'STOP',
            h.pv, h.sv, a))
        self.disp3d.setTextColor(*((1, 0.3, 0.3, 1) if a else (0.3, 1, 0.6, 1)))

    # ---------------- UI 回调 ----------------
    def ui_toggle(self, k):
        self.sim.set_x(k, not self.sim.X[k])

    def ui_press(self, k):
        self.sim.press(k)

    def ui_sv(self, d):
        self.sim.log('op', '操作 SV %+d' % d)
        self.sim.set_sv(self.sim.sv + d)

    def ui_fault(self, f):
        if f in self.sim.fault:
            self.sim.set_fault(f, not self.sim.fault[f])
        else:
            self.sim.set_fault(f, 1)

    def run_case(self, i):
        self.sim.load_case(CASES[i])
        self.case_desc = CASES[i][0] + '\n' + CASES[i][1]
        self.paused = False
        self.inspect_t = None
        self.clear_packets()

    def reset(self):
        self.sim.reset()
        self.case_desc = '自由操作模式：用左侧按钮自己拨 IO，或点右侧用例自动演示。'
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

    # ---------------- 主循环 ----------------
    def update(self, task):
        rdt = min(globalClock.getDt(), 0.1)
        if not self.paused:
            n = int(round(rdt * self.speed / STEP))
            for _ in range(max(1, n)):
                self.sim.step(STEP)
        self.update_3d(rdt)
        self.redraw_acc += rdt
        if self.redraw_acc >= 1 / 30.0 or self.paused:
            self.redraw_acc = 0.0
            self.redraw()
        return task.cont

    # ---------------- 时序图 ----------------
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

        # 网格 / 刻度
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

        # 数字信号
        for key, _, col in ROWS:
            if key in ('TX', 'RX'):
                continue
            top = ROW_Y[key]
            for a, e, off, al in spans:
                c = (col[0], col[1], col[2], al)
                prev = None
                for s, t2, v in rec.segments(key, a, e):
                    x1, x2 = self.tx(s, off), self.tx(t2, off)
                    y = top + 5 if v else top + RH - 5
                    if v:
                        b.rect(x1, top + 5, x2, top + RH - 5, (col[0], col[1], col[2], 0.16 * al))
                    if prev is not None and prev != y:
                        b.line(x1, prev, x1, y, c)
                    b.line(x1, y, x2, y, c)
                    prev = y

        # 报文块
        li = 0
        for a, e, off, al in spans:
            for f in rec.frames_between(a, e):
                if f.t0 < a:
                    continue
                top = ROW_Y[f.dir]
                x1 = self.tx(f.t0, off)
                x2 = max(self.tx(f.t1, off), x1 + (2 if f.kind in ('poll', 'status') else 4))
                if f.kind == 'nak':
                    col = C_RED
                elif f.corrupt:
                    col = (1, 0.6, 0.2, 1)
                else:
                    col = C_TX if f.dir == 'TX' else C_RX
                strong = f.important
                alpha = al * (1.0 if strong else 0.4)
                y1, y2 = (top + 4, top + RH - 4) if strong else (top + 9, top + RH - 7)
                if f.lost:
                    b.box(x1, y1, x2 + 2, y2, (1, 0.25, 0.25, al))
                    b.line(x1, y1, x2 + 2, y2, (1, 0.25, 0.25, al))
                else:
                    b.rect(x1, y1, x2, y2, (col[0], col[1], col[2], alpha))
                if f.cause and f.dir == 'TX':
                    ck, ct = f.cause
                    if a <= ct <= e and ck in ROW_Y:
                        b.dash(self.tx(ct, off), ROW_Y[ck] + RH / 2, x1, top + 4,
                               (C_TX[0], C_TX[1], C_TX[2], 0.7 * al))
                if strong and li < len(self.lbl_pool):
                    tn, np = self.lbl_pool[li]
                    p = sim.proto.parse(f.raw, f.dir == 'RX')
                    s = p['cmd'] if p else '?'
                    if f.dir == 'RX' and p:
                        s = 'A' if p['ok'] else 'N' + p['data']
                    if f.lost:
                        s += '×'
                    tn.setText(s)
                    tn.setTextColor(1, 1, 1, al)
                    np.setPos((x1 + x2) / 2, 0, -(top + 3))
                    np.show()
                    li += 1
        for tn, np in self.lbl_pool[li:]:
            np.hide()

        # PV / SV
        def py(v):
            return PV_TOP + PV_H - 4 - (max(15, min(100, v)) - 15) / 85.0 * (PV_H - 8)
        for a, e, off, al in spans:
            b.dash(self.tx(a, off), py(90), self.tx(e, off), py(90), (1, 0.3, 0.3, 0.5 * al), 3, 4)
            for s, t2, v in rec.segments('SV', a, e):
                b.dash(self.tx(s, off), py(v), self.tx(t2, off), py(v), (C_HW[0], C_HW[1], C_HW[2], al))
            pts = [(t, v) for t, v in rec.pv_between(a, e) if a <= t <= e]
            for (t1, v1), (t2, v2) in zip(pts, pts[1:]):
                b.line(self.tx(t1, off), py(v1), self.tx(t2, off), py(v2),
                       (C_PWR[0], C_PWR[1], C_PWR[2], al))

        # 光标
        b.rect(cur_x - 1, ROW_TOP - 4, cur_x + 1, PV_TOP + PV_H, C_CUR)
        if self.paused and self.inspect_t is not None:
            it = self.inspect_t
            off = ws if it >= ws else ws - self.W
            ix = self.tx(it, off)
            b.rect(ix - 1, ROW_TOP - 4, ix + 1, PV_TOP + PV_H, C_INS)

        # 左侧灯 / 按钮颜色
        for k, y in self.lamp_y.items():
            on = sim.plc.Y[k]
            col = {'Y10': C_OUT, 'Y11': C_RED, 'Y12': C_HW, 'Y13': C_IN}[k]
            b.rect(14, y + 4, 34, y + 22, col if on else (0.22, 0.22, 0.25, 1))
        for k, btn in self.xbtn.items():
            on = sim.X[k]
            if k == 'X4':
                c = (0.85, 0.1, 0.1, 1) if on else (0.4, 0.08, 0.08, 1)
            else:
                c = (0.18, 0.5, 0.32, 1) if on else (0.22, 0.24, 0.28, 1)
            btn['frameColor'] = c
        for f, btn in self.fbtn.items():
            on = sim.fault.get(f) or sim.once.get(f)
            btn['frameColor'] = (0.7, 0.42, 0.1, 1) if on else (0.22, 0.24, 0.28, 1)
        for sp, btn in self.spd_btn.items():
            btn['frameColor'] = (0.2, 0.35, 0.6, 1) if sp == self.speed else (0.22, 0.24, 0.28, 1)
        for w, btn in self.win_btn.items():
            btn['frameColor'] = (0.2, 0.35, 0.6, 1) if w == self.W else (0.22, 0.24, 0.28, 1)
        self.btn_pause['text'] = '继续（空格）' if self.paused else '暂停（空格）'

        if self.chart_np:
            self.chart_np.removeNode()
        self.chart_np = self.pixel2d.attachNewNode(b.make('chart'))
        self.chart_np.setTransparency(TransparencyAttrib.MAlpha)
        self.chart_np.setRenderModeThickness(1.6)

        self.update_texts()

    def update_texts(self):
        sim, h, plc = self.sim, self.sim.heater, self.sim.plc
        state = '暂停' if self.paused else '运行 %gx' % self.speed
        self.head_tn.setText('时序图   t = %.3f s   [%s]   窗口' % (sim.t, state))
        self.sv_tn.setText('%.1f ℃' % sim.sv)
        st = plc.status
        if st:
            b = st['bits']
            on = [n for i, n in enumerate(sim.proto.BITS) if b >> i & 1]
            sline = 'PV %.1f℃   流量 %.1f L/min\n状态位 %02X\n%s' % (st['pv'], st['flow'], b,
                                                             ' '.join(on) or '-')
        else:
            sline = '（还没读到状态）'
        comm = '通信异常' if plc.comm_alarm else ('等待响应' if plc.txn else '空闲')
        extra = []
        if plc.estop_latched:
            extra.append('急停锁定')
        if plc.plc_alarm:
            extra.append(plc.plc_alarm)
        self.status_tn.setText('%s\n\n485：%s  待发 %d 条\nPLC 要求运转：%s\n%s' % (
            sline, comm, len(plc.queue), '是' if plc.want_run else '否', ' '.join(extra)))

        # 日志
        logs = sim.rec.log
        if self.paused and self.inspect_t is not None:
            logs = [l for l in logs if l[0] <= self.inspect_t + 1e-6]
        logs = logs[-len(self.log_pool):]
        for i, (tn, np) in enumerate(self.log_pool):
            if i < len(logs):
                t, k, s = logs[i]
                line = '%8.3f %s %s' % (t, LOG_TAG[k], s)
                if len(line) > 52:
                    line = line[:51] + '…'
                tn.setText(line)
                tn.setTextColor(*LOG_COL[k])
            else:
                tn.setText('')

        self.detail_tn.setText(self.detail_text())
        self.case_tn.setText(self.case_desc)
        flt = [FAULT_NAMES[k] for k, v in sim.fault.items() if v]
        self.v3_tn.setText('3D 视图   故障：%s' % ('、'.join(flt) if flt else '无'))

    def detail_text(self):
        sim, rec = self.sim, self.sim.rec
        if not (self.paused and self.inspect_t is not None):
            return ('报文详情\n\n运行中…\n按空格暂停，或直接点时序图，\n'
                    '可查看任意时刻的 IO 和报文。\n\n'
                    '图例：\n 实心块 = 命令/应答\n 淡色细块 = 轮询\n 红色 = NAK\n'
                    ' 红框× = 线上丢失\n 紫色虚线 = 哪个 IO 引起的')
        t = self.inspect_t
        v = lambda k: rec.value_at(k, t)
        lines = ['查看光标 t = %.3f s' % t,
                 'X0远程=%d X1在线=%d X2通水=%d X3加热=%d' % (v('X0'), v('X1'), v('X2'), v('X3')),
                 'X4急停=%d Y12许可=%d 电源=%s' % (v('X4'), v('Y12'), 'ON' if v('PWR') else 'OFF'),
                 'Y10运转=%d Y11报警=%d Y13远程=%d' % (v('Y10'), v('Y11'), v('Y13'))]
        fr = rec.frames_between(t - 0.6, t + 0.6)
        if not fr:
            lines.append('\n附近没有报文')
            return '\n'.join(lines)
        inside = [f for f in fr if f.t0 <= t <= f.t1 + 0.002]
        f = inside[0] if inside else min(fr, key=lambda f: min(abs(f.t0 - t), abs(f.t1 - t)))
        lines.append('')
        lines.append('%s  %s   %.3f→%.3f s' % (f.dir, f.desc, f.t0, f.t1))
        lines.append('%d 字节 @%dbps = %.1f ms' % (len(f.raw), BAUD, (f.t1 - f.t0) * 1000))
        lines.append(f.hex())
        for name, hx, meaning in sim.proto.fields(f.raw, f.dir == 'RX'):
            lines.append(' %-4s %-14s %s' % (name, hx, meaning))
        if f.note:
            lines.append('※ ' + f.note)
        return '\n'.join(lines)


if __name__ == '__main__':
    App().run()
