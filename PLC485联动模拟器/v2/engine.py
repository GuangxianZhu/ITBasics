# -*- coding: utf-8 -*-
"""
引擎：PLC 网关（主站）+ 温水器模型（从站）+ 总线 + 用例
协议细节都在 codec / command_table / point_map，这里不用改。
"""
import heapq
import bisect
import random

from codec import CODECS, Request
from command_table import PARAMS, NAK
import point_map as PM

BAUD = 9600
RESP_DELAY = 0.015
STEP = 0.002
INLET_T = 22.0
T = PM.TIMING

W_NAMES = {'W0': 'W0 远程', 'W1': 'W1 在线', 'W2': 'W2 通水', 'W3': 'W3 加热', 'W4': 'W4 复位',
           'ES': '急停(硬线)'}
R_NAMES = {r['dst']: '%s %s' % (r['dst'], r['name']) for r in PM.READ_POINTS}
FAULT_NAMES = {'cut': '485断线', 'noise': 'AD噪声', 'adcut': 'AD断线', 'clog': '断流(堵塞)',
               'overtemp': '过热(控制失效)', 'leak': '漏水', 'light': '轻故障(传感器)',
               'heavy': '重故障(灯管断线)', 'bcc': 'BCC/CRC错误', 'lossreply': '响应丢失',
               'reboot': '温水器重启'}
ONCE = ('bcc', 'lossreply', 'reboot')


# ============================================================
#  帧 / 记录
# ============================================================
class Frame:
    def __init__(self, t0, direction, raw, desc, kind, cause=None):
        self.t0 = t0
        self.t1 = t0 + len(raw) * 10.0 / BAUD
        self.dir = direction      # TX: PLC→温水器  RX: 温水器→PLC
        self.raw = raw
        self.desc = desc
        self.kind = kind          # TX: write/poll   RX: ack/nak/data
        self.cause = cause
        self.lost = False
        self.corrupt = False
        self.note = ''

    def hex(self):
        return ' '.join('%02X' % b for b in self.raw)

    @property
    def important(self):
        return self.kind not in ('poll', 'data') or self.lost or self.corrupt


class Recorder:
    def __init__(self):
        self.sig = {}
        self.ana = {}
        self.frames, self.frame_t = [], []
        self.log = []

    def set(self, key, t, v):
        ts, vs = self.sig.setdefault(key, ([], []))
        if not vs or vs[-1] != v:
            ts.append(t)
            vs.append(v)

    def sample(self, key, t, v):
        ts, vs = self.ana.setdefault(key, ([], []))
        ts.append(t)
        vs.append(v)

    def value_at(self, key, t):
        ts, vs = self.sig.get(key, ([], []))
        i = bisect.bisect_right(ts, t) - 1
        return vs[i] if i >= 0 else 0

    def ana_at(self, key, t):
        ts, vs = self.ana.get(key, ([], []))
        i = bisect.bisect_right(ts, t) - 1
        return vs[i] if i >= 0 else None

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

    def ana_between(self, key, a, b):
        ts, vs = self.ana.get(key, ([], []))
        i = max(0, bisect.bisect_left(ts, a) - 1)
        j = bisect.bisect_right(ts, b) + 1
        return [(t, v) for t, v in zip(ts[i:j], vs[i:j]) if a <= t <= b]

    def add_frame(self, f):
        self.frames.append(f)
        self.frame_t.append(f.t0)

    def frames_between(self, a, b):
        i = bisect.bisect_left(self.frame_t, a - 0.05)
        j = bisect.bisect_right(self.frame_t, b)
        return self.frames[i:j]


# ============================================================
#  温水器（从站）—— 全串口，只有急停是硬线
# ============================================================
STOP_FAULTS = {'overheat', 'leak', 'heavy', 'empty', 'estop', 'wd'}
HEAVY_SET = {'heavy', 'empty', 'estop', 'wd'}
FAULT_TEXT = {'overheat': '过热（出口>90℃）', 'leak': '漏水 → 自己停机', 'heavy': '灯管断线（重故障）',
              'empty': '运转中断流 → 空焚保护（重故障）', 'estop': '急停输入（硬线）→ 电源切断',
              'wd': '通信看门狗：2 秒没收到命令 → 自己停机（重故障）'}


class Heater:
    def __init__(self, sim):
        self.sim = sim
        self.pv = INLET_T
        self.flow = 0.0
        self.estop_in = False
        self.booting_until = -1.0
        self.reset_state()

    def reset_state(self):
        self.remote = self.online = self.run = self.water = False
        self.sv = 60.0
        self.latched = set()
        self.last_rx = self.sim.t
        self.had_flow = False
        self.empty_timer = 0.0

    @property
    def booting(self):
        return self.sim.t < self.booting_until

    @property
    def flow_ok(self):
        return self.flow >= 3.0

    @property
    def stop_fault(self):
        return bool(self.latched & STOP_FAULTS)

    @property
    def demand(self):
        return self.run and self.remote and self.online and not self.stop_fault and not self.booting

    @property
    def power(self):
        return self.demand and self.flow_ok and not self.estop_in

    @property
    def ready(self):
        return self.power and abs(self.pv - self.sv) <= 2.0

    def status_word(self):
        bits = [self.remote, self.run, self.power, self.water, self.ready, self.online, self.flow_ok]
        return sum(1 << i for i, v in enumerate(bits) if v)

    def alarm_word(self):
        L = self.latched
        bits = ['overheat' in L, 'leak' in L, self.sim.fault['light'], bool(L & HEAVY_SET),
                'estop' in L, 'empty' in L, 'heavy' in L, 'wd' in L]
        return sum(1 << i for i, v in enumerate(bits) if v)

    def latch(self, name):
        if name not in self.latched:
            self.latched.add(name)
            if name in STOP_FAULTS:
                self.run = False
            self.sim.log('alarm', '温水器：' + FAULT_TEXT[name])

    def reboot(self):
        self.sim.log('hw', '温水器重启：远程/在线/运转/SV 全部回到出厂值，0.3s 内不应答')
        self.booting_until = self.sim.t + 0.3
        self.reset_state()

    def step(self, dt):
        s = self.sim
        target = 12.0 if (self.water and not s.fault['clog'] and not self.booting) else 0.0
        self.flow += (target - self.flow) * min(1.0, dt / 0.8)
        if self.booting:
            self.pv += (INLET_T - self.pv) * min(1.0, dt / 5.0)
            return
        if self.estop_in:
            self.latch('estop')
        if s.fault['leak']:
            self.latch('leak')
        if s.fault['heavy']:
            self.latch('heavy')
        # 空焚：加热中流量掉了
        if self.demand:
            if self.flow_ok:
                self.had_flow = True
                self.empty_timer = 0.0
            elif self.had_flow:
                self.empty_timer += dt
                if self.empty_timer > 1.0:
                    self.latch('empty')
        else:
            self.had_flow = False
            self.empty_timer = 0.0
        # 看门狗
        if s.watchdog and self.run and s.t - self.last_rx > 2.0:
            self.latch('wd')
        # 温度
        if self.power:
            tgt = 98.0 if s.fault['overtemp'] else self.sv
            self.pv += (tgt - self.pv) * min(1.0, dt / 2.5)
        else:
            k = 5.0 if self.flow_ok else 25.0
            self.pv += (INLET_T - self.pv) * min(1.0, dt / k)
        if self.pv > 90.0:
            self.latch('overheat')

    # ---- 参数读写（和协议无关）----
    def handle(self, req):
        p = PARAMS.get(req.param)
        if p is None:
            return False, None, '03'
        if req.op == 'R':
            if 'R' not in p.rw:
                return False, None, '03'
            return True, {'010': int(round(self.sv * 10)), '100': int(round(self.pv * 10)),
                          '101': self.status_word(), '102': self.alarm_word()}[req.param], None
        if 'W' not in p.rw:
            return False, None, '03'
        v = req.value
        if req.param == '001':
            self.remote = bool(v)
            return True, None, None
        if req.param == '004':
            if self.estop_in:
                return False, None, '05'
            keep = set()
            if self.sim.fault['leak']:
                keep.add('leak')
            if self.sim.fault['heavy']:
                keep.add('heavy')
            if 'overheat' in self.latched and self.pv > 85:
                keep.add('overheat')
            cleared = self.latched - keep
            self.latched = self.latched & keep
            if cleared:
                self.sim.log('hw', '温水器：复位，清除 %s' % '、'.join(sorted(cleared)))
            return True, None, None
        if not self.remote:
            return False, None, '02'
        if req.param == '005':
            self.online = bool(v)
        elif req.param == '003':
            self.water = bool(v)
        elif req.param == '002':
            if v and self.estop_in:
                return False, None, '05'
            if v and self.stop_fault:
                return False, None, '04'
            self.run = bool(v)
        elif req.param == '010':
            if (p.lo is not None and v < p.lo) or (p.hi is not None and v > p.hi):
                return False, None, '06'
            self.sv = v * p.scale
        return True, None, None

    def receive(self, f):
        s = self.sim
        if self.booting:
            return
        req, chk = s.codec.decode_request(f.raw)
        if req is None or not chk:
            if s.codec.silent_on_bad_frame:
                s.log('nak', '温水器：收到校验错的帧 → 按 Modbus 规定不回应')
                return
            req = req or Request(T['station'], 'R', '000')
            return self.reply(req, False, None, '01')
        if req.addr != T['station']:
            return
        self.last_rx = s.t
        ok, val, err = self.handle(req)
        self.reply(req, ok, val, err)

    def reply(self, req, ok, val, err):
        s = self.sim
        raw = s.codec.encode_response(req, ok, val, err)
        p = PARAMS.get(req.param)
        pname = p.name if p else req.param
        if ok and req.op == 'R':
            kind, desc = 'data', '%s 读回' % pname
        elif ok:
            kind, desc = 'ack', 'ACK 写%s' % pname
        else:
            kind, desc = 'nak', 'NAK %s %s' % (err, NAK.get(err, ''))
        s.at(s.t + RESP_DELAY, lambda: s.transmit('RX', raw, desc, kind, deliver=s.gw.on_response))


# ============================================================
#  PLC 网关（主站）
# ============================================================
class Gateway:
    def __init__(self, sim):
        self.sim = sim
        self.prev = {k: 0 for k in sim.WKEYS}
        self.actual = {}                 # param → (原始值, 读到的时刻)
        self.queue = []
        self.txn = None
        self.next_free = 0.0
        self.next_poll = 0.0
        self.poll_idx = 0
        self.cycle_start = 0.0
        self.fail = 0
        self.last_ok = -99.0
        self.comm_fault = False
        self._recover_logged = False
        self.ma_f = None
        self.ad_fault = False
        self.sv_target = None
        self.mismatch = False
        self.first = True
        self.wstate = {wp['param']: dict(last_desired=None, last_write=-99.0, hold_until=0.0,
                                         attempts=0, mismatch=False, new=False, cause=None)
                       for wp in PM.WRITE_POINTS}
        self.R = {r['dst']: 0 for r in PM.READ_POINTS}

    # ---------- 工具 ----------
    def desired(self, wp):
        W = self.sim.W
        if wp['src'] == 'AD':
            return None if self.sv_target is None else int(round(self.sv_target * 10))
        return W[wp['src']]

    def queued(self, param):
        for c in self.queue:
            if c['param'] == param and c['op'] == 'W':
                return c
        return None

    def enqueue_write(self, param, value, desc, cause=None, front=False):
        c = self.queued(param)
        if c:
            c['value'] = value
            c['desc'] = desc
            return
        c = dict(op='W', param=param, value=value, desc=desc, cause=cause, tries=0, poll=False)
        if front:
            self.queue.insert(0, c)
        else:
            self.queue.append(c)

    def wdesc(self, wp, v):
        if wp['param'] == '010':
            return '写 SV=%.1f℃' % (v / 10.0)
        return '写 %s=%d' % (wp['name'], v)

    # ---------- 扫描 ----------
    def scan(self, dt):
        s, W, t = self.sim, self.sim.W, self.sim.t
        # ---- AD 处理 ----
        A = PM.AD
        ma = s.ad_effective()
        bad = ma < A['broken_below'] or ma > A['over_above']      # 用原始值立刻判断，不等滤波
        if bad != self.ad_fault:
            self.ad_fault = bad
            if bad:
                s.log('alarm', 'AD %.2fmA 超出范围 → AD 断线：不写新 SV（保持 %s），轻故障 ON' %
                      (ma, '%.1f℃' % self.sv_target if self.sv_target else '-'))
            else:
                s.log('plc', 'AD 恢复正常 → 轻故障(AD) 解除')
                self.ma_f = ma
        if not bad:
            self.ma_f = ma if self.ma_f is None else self.ma_f + (ma - self.ma_f) * min(1.0, dt / A['filter_tau'])
            settled = abs(ma - self.ma_f) < A['settle']                # 等稳定了再更新设定
            tr = A['t_min'] + (self.ma_f - A['ma_min']) / (A['ma_max'] - A['ma_min']) * (A['t_max'] - A['t_min'])
            tr = max(A['t_min'], min(A['t_max'], tr))
            if self.sv_target is None or (settled and abs(tr - self.sv_target) >= A['deadband']):
                self.sv_target = round(tr, 1)

        # ---- 复位 ----
        if W['W4'] and not self.prev['W4']:
            self.do_reset()
        self.prev = dict(W)

        # ---- 对账 ----
        if self.first:
            for wp in PM.WRITE_POINTS:
                self.wstate[wp['param']]['last_desired'] = self.desired(wp)
            self.first = False
        if not self.comm_fault:
            self.reconcile()
        self.mismatch = any(st['mismatch'] for st in self.wstate.values())

        # ---- 输出 ----
        for rp in PM.READ_POINTS:
            src = self.actual.get(rp['param'])
            v = (src[0] >> rp['bit']) & 1 if src else 0
            stale = (src is None) or (t - src[1] > T['stale'])
            if self.comm_fault or stale:
                pol = rp['on_comm_fault']
                if pol == 'off':
                    v = 0
                elif pol == 'on' and self.comm_fault:
                    v = 1
            for a in rp.get('also', []):
                if getattr(self, a):
                    v = 1
            if rp['fault'] and PM.FAULT_ACTIVE_LOW:
                v = 1 - v
            self.R[rp['dst']] = int(v)
        self.comm()

    def do_reset(self):
        s, t = self.sim, self.sim.t
        if self.comm_fault:
            if self.fail == 0 and t - self.last_ok < T['recover_ok']:
                self.comm_fault = False
                s.log('plc', 'W4 复位：通信正常 → 解除通信异常（重故障 OFF）')
            else:
                s.log('plc', 'W4 复位：通信仍不通 → 不能解除，重故障保持 ON')
                return
        for st in self.wstate.values():
            st['mismatch'] = False
            st['attempts'] = 0
            st['hold_until'] = 0.0
        self.enqueue_write(PM.RESET['param'], PM.RESET['value'], '写 复位=1（转发 W4）',
                           ('W4', t), front=True)

    def reconcile(self):
        s, t = self.sim, self.sim.t
        alarm = self.actual.get('102')
        for wp in PM.WRITE_POINTS:
            p = wp['param']
            st = self.wstate[p]
            d = self.desired(wp)
            if d is None:
                continue
            if wp['src'] != 'W0' and not self.sim.W['W0']:
                continue          # 清洗机没给远程：除「远程」本身外什么都不写
            if d != st['last_desired']:
                st['last_desired'] = d
                st['attempts'] = 0
                st['mismatch'] = False
                st['new'] = True
                st['hold_until'] = 0.0
                st['cause'] = (wp['src'], t)
            nd = wp.get('needs')
            if nd and not st['new']:
                an = self.actual.get(nd[0])
                rb = self.actual.get(wp['readback'][0])
                if an is None or not (an[0] >> nd[1] & 1) or (rb and rb[1] > an[1]):
                    continue      # 前提位（例：远程）还没确认，或状态比读回值旧 → 先等
            if wp.get('hold_if_alarm') and d and not st['new']:
                rb = self.actual.get(wp['readback'][0])
                if alarm is None or (rb and rb[1] > alarm[1]) or \
                        any(alarm[0] >> b & 1 for b in wp['hold_if_alarm']):
                    continue      # 报警字还没读到最新的，或者温水器有停机类报警 → 不硬写
            if t < st['hold_until'] or t - st['last_write'] < T['write_min_interval']:
                continue
            if self.queued(p):
                self.queued(p)['value'] = d
                continue
            if st['new']:
                st['new'] = False
                self.enqueue_write(p, d, self.wdesc(wp, d), st['cause'])
                continue
            rbp, bit = wp['readback']
            a = self.actual.get(rbp)
            if a is None:
                continue
            av = (a[0] >> bit) & 1 if bit is not None else a[0]
            fresh = a[1] > st['last_write'] + 0.05 and t - a[1] < T['stale']
            if not fresh:
                continue
            if av == d:
                st['attempts'] = 0
                continue
            if st['mismatch'] or t - st['last_write'] < T['resend_interval']:
                continue
            st['attempts'] += 1
            if st['attempts'] > T['mismatch_limit']:
                st['mismatch'] = True
                s.log('alarm', '对账：%s 写了 %d 次读回仍不对 → 指令不一致（轻故障）' % (wp['name'], T['mismatch_limit']))
                continue
            s.log('plc', '对账：%s 期望=%s 实际=%s → 重写' % (
                wp['name'], d if bit is not None else '%.1f' % (d / 10.0),
                av if bit is not None else '%.1f' % (av / 10.0)))
            self.enqueue_write(p, d, self.wdesc(wp, d) + '（对账）')

    # ---------- 通信 ----------
    def comm(self):
        t = self.sim.t
        if self.txn:
            if t >= self.txn['deadline']:
                self.on_fail('超时无响应')
            return
        if t < self.next_free:
            return
        if self.queue:
            return self.send(self.queue.pop(0))
        if t < self.next_poll:
            return
        param = PM.POLL[self.poll_idx]
        if self.poll_idx == 0:
            self.cycle_start = t
        self.poll_idx = (self.poll_idx + 1) % len(PM.POLL)
        if self.comm_fault:
            self.next_poll = t + T['poll_cycle_fault']
        elif self.poll_idx == 0:
            self.next_poll = max(t, self.cycle_start + T['poll_cycle'])
        else:
            self.next_poll = t
        self.send(dict(op='R', param=param, value=None, desc='读 %s' % PARAMS[param].name,
                       cause=None, tries=0, poll=True))

    def send(self, c):
        s = self.sim
        req = Request(T['station'], c['op'], c['param'], c['value'])
        raw = s.codec.encode_request(req)
        corrupt = False
        if s.once['bcc'] and not c['poll']:
            s.once['bcc'] = False
            raw = raw[:-1] + bytes([raw[-1] ^ 0x5A])
            corrupt = True
        f = s.transmit('TX', raw, c['desc'], 'poll' if c['poll'] else 'write',
                       cause=c['cause'] if c['tries'] == 0 else None, deliver=s.heater.receive)
        if corrupt:
            f.corrupt = True
            f.note = '线路噪声：校验码被破坏'
        if not c['poll']:
            tag = '（重发%d）' % c['tries'] if c['tries'] else ''
            s.log('tx', '%s%s  %s' % (c['desc'], tag, f.hex()))
            if c['param'] in self.wstate:
                self.wstate[c['param']]['last_write'] = s.t
        self.txn = dict(c, req=req, frame=f, deadline=f.t1 + T['timeout'])

    def on_fail(self, reason):
        s, c = self.sim, self.txn
        self.txn = None
        self.next_free = s.t + T['gap']
        self.fail += 1
        if not self.comm_fault:
            s.log('nak', '%s %s（连续失败 %d/%d）' % (c['desc'], reason, self.fail, T['fail_limit']))
        if not c['poll'] and c['tries'] < T['write_retry'] and not self.comm_fault:
            c['tries'] += 1
            self.queue.insert(0, c)
        if self.fail >= T['fail_limit'] and not self.comm_fault:
            self.comm_fault = True
            self._recover_logged = False
            n = len([q for q in self.queue if not q['poll']])
            self.queue.clear()
            s.log('alarm', 'PLC：通信异常（锁存）→ 重故障 ON、Ready OFF%s' % ('，丢弃 %d 条待写' % n if n else ''))

    def on_response(self, f):
        s, t = self.sim, self.sim.t
        if not self.txn:
            return
        c = self.txn
        r = s.codec.decode_response(f.raw, c['req'])
        if not r.check_ok:
            return self.on_fail('响应校验错')
        if not r.ok and r.err == '01':
            return self.on_fail('对方回 NAK01 校验错')
        self.txn = None
        self.next_free = t + T['gap']
        self.fail = 0
        self.last_ok = t
        if self.comm_fault and not self._recover_logged:
            s.log('plc', '通信已恢复 → 重故障仍保持，等清洗机复位(W4)')
            self._recover_logged = True
        if r.ok:
            if c['op'] == 'R':
                self.actual[c['param']] = (r.value, t)
            else:
                s.log('rx', 'ACK %s  %s' % (c['desc'], f.hex()))
        else:
            s.log('nak', 'NAK%s %s：%s 被拒绝' % (r.err, NAK.get(r.err, ''), c['desc']))
            st = self.wstate.get(c['param'])
            if st:
                st['hold_until'] = t + T['nak_wait']
                st['attempts'] = max(0, st['attempts'] - 1)


# ============================================================
#  仿真总控
# ============================================================
class Sim:
    WKEYS = ['W0', 'W1', 'W2', 'W3', 'W4']

    def __init__(self):
        self.codec_idx = 0
        self.watchdog = False
        self.reset()

    @property
    def codec(self):
        return CODECS[self.codec_idx]

    def reset(self):
        self.t = 0.0
        self.events = []
        self.seq = 0
        self.W = {k: 0 for k in self.WKEYS}
        self.ES = 0
        self.press_until = {}
        self.ad_ma = 12.0
        self.noise_v = 0.0
        self.next_noise = 0.0
        self.fault = {k: False for k in ('cut', 'noise', 'adcut', 'clog', 'overtemp', 'leak', 'light', 'heavy')}
        self.once = {'bcc': False, 'lossreply': False}
        self.rec = Recorder()
        self.heater = Heater(self)
        self.gw = Gateway(self)
        self.script = []
        self.next_sample = 0.0
        self.new_frames = []
        self.record()

    def at(self, t, fn):
        heapq.heappush(self.events, (t, self.seq, fn))
        self.seq += 1

    def log(self, kind, text):
        self.rec.log.append((self.t, kind, text))

    def ad_effective(self):
        if self.fault['adcut']:
            return 0.0
        return self.ad_ma + (self.noise_v if self.fault['noise'] else 0.0)

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
                self.log('nak', '%s 在线路上丢失（PLC 收不到）' % desc)
                return
            if deliver:
                deliver(f)
        self.at(f.t1, done)
        return f

    # ---- 操作 ----
    def set_w(self, k, v, src='操作'):
        v = 1 if v else 0
        if k == 'ES':
            if self.ES != v:
                self.ES = v
                self.log('hw' if v else ('case' if src == '用例' else 'op'),
                         '急停 → %d（硬线直接到温水器，不经过 PLC）' % v)
            return
        if self.W[k] != v:
            self.W[k] = v
            self.log('case' if src == '用例' else 'op', '%s → %d' % (W_NAMES[k], v))

    def press(self, k, src='操作'):
        self.W[k] = 1
        self.press_until[k] = self.t + 0.3
        self.log('case' if src == '用例' else 'op', '按下 %s' % W_NAMES[k])

    def set_ma(self, v, src='操作'):
        v = max(0.0, min(22.0, round(v, 2)))
        if v != self.ad_ma:
            self.ad_ma = v
            self.log('case' if src == '用例' else 'op', 'AD → %.2f mA' % v)

    def set_fault(self, name, v=1):
        if name == 'reboot':
            self.heater.reboot()
        elif name in self.once:
            self.once[name] = True
            self.log('op', '故障 %s：下一条写命令生效' % FAULT_NAMES[name])
        else:
            self.fault[name] = bool(v)
            self.log('op', '故障 %s → %s' % (FAULT_NAMES[name], 'ON' if v else 'OFF'))

    def set_watchdog(self, v):
        self.watchdog = bool(v)
        self.log('op', '温水器看门狗 → %s' % ('有(2s)' if v else '无'))

    def do_action(self, a):
        k = a[0]
        if k == 'w':
            self.set_w(a[1], a[2], '用例')
        elif k == 'press':
            self.press(a[1], '用例')
        elif k == 'ma':
            self.set_ma(a[1], '用例')
        elif k == 'fault':
            self.set_fault(a[1], a[2] if len(a) > 2 else 1)
        elif k == 'wd':
            self.set_watchdog(a[1])
        elif k == 'note':
            self.log('case', a[1])

    def load_case(self, case):
        self.reset()
        self.watchdog = False
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
                self.W[k] = 0
                del self.press_until[k]
        if self.t >= self.next_noise:
            self.noise_v = random.uniform(-0.25, 0.25)
            self.next_noise = self.t + 0.1
        self.heater.estop_in = bool(self.ES)        # 硬线！
        self.gw.scan(dt)
        self.heater.step(dt)
        self.record()

    def record(self):
        t, r = self.t, self.rec
        for k in self.WKEYS:
            r.set(k, t, self.W[k])
        r.set('ES', t, self.ES)
        for k, v in self.gw.R.items():
            r.set(k, t, v)
        r.set('CF', t, int(self.gw.comm_fault))
        r.set('PWR', t, int(self.heater.power))
        if t >= self.next_sample:
            r.sample('PV', t, self.heater.pv)
            r.sample('SVH', t, self.heater.sv)
            r.sample('SVT', t, self.gw.sv_target)
            r.sample('MA', t, self.gw.ma_f)
            self.next_sample = t + 0.05


# ============================================================
#  用例
# ============================================================
BASE = [(0.3, ('w', 'W0', 1)), (0.6, ('w', 'W1', 1)), (1.0, ('w', 'W2', 1)), (2.0, ('w', 'W3', 1))]

CASES = [
    ('① 正常启动',
     '清洗机依次给 远程→在线→通水→加热（全是电平）。PLC 每个变化写一次；AD 12mA=55℃ 一上来就对账写入。'
     'PV 到 SV±2℃ 后温水器给 Ready，PLC 下次轮询才输出 R0。',
     BASE),
    ('② AD 改温度',
     'AD 从 12mA 拉到 16mA(70℃)，再降到 8mA(40℃)。看 PLC 滤波后才写 SV，SV 读回后对上。',
     BASE + [(10, ('ma', 16.0)), (15, ('ma', 8.0))]),
    ('③ AD 噪声不刷屏',
     'AD 有 ±0.25mA 抖动。滤波 + 0.5℃ 死区 + 0.5s 最短写间隔 → 只偶尔写一次，不会每个周期都发 SV。',
     BASE + [(6, ('fault', 'noise', 1)), (16, ('fault', 'noise', 0))]),
    ('④ AD 断线',
     '4-20mA 线断了（0mA）→ PLC 判 AD 断线：不发新 SV、保持原设定、轻故障 R3 ON。接回自动解除。',
     BASE + [(9, ('fault', 'adcut', 1)), (14, ('fault', 'adcut', 0))]),
    ('⑤ 温水器重启→自动补回',
     '温水器重启，远程/在线/运转/SV 全丢了。短暂没应答不到 3 次 → 不报故障；'
     '读回状态和清洗机电平对不上 → PLC 对账自动重写。这就是「电平语义」。',
     BASE + [(10, ('fault', 'reboot'))]),
    ('⑥ 485 断线→复位',
     '断线 → 连续 3 次失败 → 通信异常锁存：R4 重故障 ON、R0 Ready OFF。'
     '接回后重故障不自动消失，清洗机按 W4 复位才解除（和原 IO 一样）。',
     BASE + [(9, ('fault', 'cut', 1)), (12, ('fault', 'cut', 0)), (15, ('press', 'W4'))]),
    ('⑦ 断线中按复位',
     '线还没接回就按 W4 → PLC 拒绝复位，重故障保持。接回后再按才有效。',
     BASE + [(9, ('fault', 'cut', 1)), (11, ('press', 'W4')), (13, ('fault', 'cut', 0)),
             (15, ('press', 'W4'))]),
    ('⑧ 断线·温水器无看门狗',
     '断线后清洗机看到重故障，把 W3 加热拉低 —— 但命令送不过去！温水器没有看门狗，按最后的命令继续加热（看「加热电源」）。危险。',
     BASE + [(0, ('wd', False)), (9, ('fault', 'cut', 1)), (11, ('w', 'W3', 0)),
             (16, ('fault', 'cut', 0)), (18, ('press', 'W4'))]),
    ('⑨ 断线·温水器有看门狗',
     '同样断线，但温水器 2 秒收不到命令自己停机。对比 ⑧ 的「加热电源」行。所以手册里一定要查看门狗。',
     BASE + [(0, ('wd', True)), (9, ('fault', 'cut', 1)), (11, ('w', 'W3', 0)),
             (16, ('fault', 'cut', 0)), (18, ('press', 'W4'))]),
    ('⑩ 过热',
     '控制失效 PV 冲过 90℃ → 温水器自停 → R1 过热。降温后 W4 复位；W3 一直是 ON，'
     '复位后 PLC 对账会自动把运转写回去（IO 电平语义，和 v1 的边沿不同）。',
     BASE + [(6, ('fault', 'overtemp', 1)), (13, ('fault', 'overtemp', 0)), (15, ('press', 'W4'))]),
    ('⑪ 漏水',
     '漏水 → 温水器自己停机 → R2 漏水。漏水消除后 W4 复位，运转自动恢复。',
     BASE + [(9, ('fault', 'leak', 1)), (13, ('fault', 'leak', 0)), (15, ('press', 'W4'))]),
    ('⑫ 轻故障',
     '传感器类轻故障 → R3 ON，但温水器继续加热。原因消失自动解除。',
     BASE + [(9, ('fault', 'light', 1)), (14, ('fault', 'light', 0))]),
    ('⑬ 重故障',
     '灯管断线 → R4 重故障 → 温水器停。修好后 W4 复位。',
     BASE + [(9, ('fault', 'heavy', 1)), (12, ('fault', 'heavy', 0)), (14, ('press', 'W4'))]),
    ('⑭ 急停（硬线）',
     '急停直接切温水器电源，不经过 PLC；PLC 是靠下次轮询读到报警字才把 R4 给清洗机。解除后 W4 复位。',
     BASE + [(9, ('w', 'ES', 1)), (12, ('w', 'ES', 0)), (14, ('press', 'W4'))]),
    ('⑮ 线路干扰',
     '一次校验错 + 一次响应丢失：PLC 自动重发，连续失败没到 3 次 → 不报故障。'
     '（切到 Modbus 再跑：校验错时温水器不回应，只能等超时）',
     BASE + [(7, ('fault', 'bcc')), (7.05, ('ma', 13.0)), (11, ('fault', 'lossreply')),
             (11.05, ('ma', 14.0))]),
    ('⑯ 远程未给',
     '清洗机没给 W0 远程：PLC 只管「远程」这一点，其它点先不写（在线/通水/加热都记着）。W0 一给上，对账把其它点一次补齐。',
     [(0.6, ('w', 'W1', 1)), (1.0, ('w', 'W2', 1)), (2.0, ('w', 'W3', 1)), (8.0, ('w', 'W0', 1))]),
]
