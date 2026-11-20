/* PLC 网关模拟器内核（清洗机 ↔ PLC ↔ 温水器）
 *
 * 离散事件模拟：给定参数 + 操作脚本，一次算完整段时间，输出信号 / 帧 / 日志轨迹。
 * 网页（ui.js）只负责画，不参与计算。Node 里也能直接 require 这个文件跑（见 test_core.js）。
 *
 * 做法按 ../时序图/README.md 第 3～5 节。
 * 换协议改这几处：
 *   - 温水器串口帧：改 SU_CMD 和 suReq / suRsp
 *   - 清洗机侧 Modbus：改 MB_ADDR
 *   - 状态位 / 报警编号：改 ST 和 ALM
 * 文字不写在这里：日志、信号名都只记 key，显示时由 i18n.js 翻译（中 / 英 / 日）。
 */
(function (root) {
  'use strict';

  // ------------------------------------------------------------------ 参数
  // [id, 分组, 默认值, 最小, 最大, 步长, 单位, 标记]
  // 单位：ms / s / n（次数）/ C（℃）/ Cps（℃/s）/ bps / bool
  // 标记：推 = 清洗机 / 温水器侧的前提，P = PLC 本方案，未 = 还没定，假 = 演示用的值
  const PARAM_DEFS = [
    ['fcPoll', 'fc', 500, 100, 5000, 50, 'ms', '推'],
    ['fcTimeout', 'fc', 1000, 100, 5000, 50, 'ms', '推'],
    ['fcRetry', 'fc', 3, 1, 10, 1, 'n', '推'],
    ['fcGap', 'fc', 50, 0, 500, 5, 'ms', '推'],
    ['resetHold', 'fc', 5, 0.2, 20, 0.1, 's', '推'],
    ['pwrPulse', 'fc', 1, 0.1, 5, 0.1, 's', '假'],
    ['fcReact', 'fc', 500, 0, 5000, 50, 'ms', '假'],
    ['fcStopOnHeavy', 'fc', true, 0, 0, 0, 'bool', '未'],
    ['autoRunDelay', 'fc', 2, 0, 20, 0.5, 's', '假'],
    ['valveDelay', 'fc', 1, 0, 10, 0.5, 's', '假'],

    ['plcBootWait', 'plc', 30, 0, 120, 1, 's', 'P'],
    ['suPoll', 'plc', 3000, 200, 20000, 100, 'ms', '推'],
    ['suTimeout', 'plc', 1000, 50, 5000, 50, 'ms', '推'],
    ['suRetry', 'plc', 3, 1, 10, 1, 'n', '推'],
    ['suGap', 'plc', 50, 0, 500, 5, 'ms', '推'],
    ['fcLossTime', 'plc', 5, 1, 60, 0.5, 's', '未'],
    ['settle', 'plc', 100, 0, 2000, 10, 'ms', 'P'],
    ['plcScan', 'plc', 10, 1, 100, 1, 'ms', '假'],
    ['slaveDelay', 'plc', 5, 0, 200, 1, 'ms', '假'],
    ['plcRestart', 'plc', 2, 0.1, 30, 0.1, 's', '假'],
    ['mismatchLimit', 'plc', 3, 1, 10, 1, 'n', 'P'],
    ['optReadback', 'plc', true, 0, 0, 0, 'bool', 'P'],
    ['optResetRead', 'plc', true, 0, 0, 0, 'bool', 'P'],
    ['optCutPower', 'plc', true, 0, 0, 0, 'bool', 'P'],
    ['optDetailOnErr', 'plc', true, 0, 0, 0, 'bool', 'P'],

    ['htBoot', 'ht', 30, 0, 120, 1, 's', '推'],
    ['htRespDelay', 'ht', 10, 1, 500, 1, 'ms', '推'],
    ['htRate', 'ht', 4, 0.2, 20, 0.2, 'Cps', '假'],
    ['htCool', 'ht', 2, 0.2, 20, 0.2, 'Cps', '假'],
    ['htBand', 'ht', 0.5, 0.1, 5, 0.1, 'C', '假'],
    ['htStabTime', 'ht', 2, 0, 30, 0.5, 's', '假'],
    ['htLightLatch', 'ht', true, 0, 0, 0, 'bool', '未'],
    ['htWatchdog', 'ht', 0, 0, 60, 1, 's', '推'],

    ['suBaud', 'link', 9600, 0, 0, 0, 'bps', '推'],
    ['fcBaud', 'link', 19200, 0, 0, 0, 'bps', '推'],
  ];
  const BAUDS = [2400, 4800, 9600, 19200, 38400, 57600, 115200];

  function defaults() {
    const o = {};
    PARAM_DEFS.forEach(d => { o[d[0]] = d[2]; });
    return o;
  }
  // 内部一律用 ms
  function normalize(Pin) {
    const P = defaults();
    Object.keys(Pin || {}).forEach(k => { if (k in P) P[k] = Pin[k]; });
    PARAM_DEFS.forEach(d => { if (d[6] === 's') P[d[0]] = P[d[0]] * 1000; });
    return P;
  }

  // ------------------------------------------------------------------ 协议定义（换协议改这里）
  // 温水器状态位
  const ST = { RUN: 1, FLOW: 2, HEAT: 4, STB: 8, SERR: 16, CERR: 32, LEAK: 64, SER: 128 };
  const ST_NAMES = ['RUN', 'FLOW', 'HEAT', 'STB', 'SERR', 'CERR', 'LEAK', 'SER'];
  // 报警编号。两边编号相同，PLC 按编号直接换算；121 以后是 PLC 自己产生的
  const ALM = { leak: 5, stop: 17, cont: 40, cfTimeout: 121, cfNak: 122, cfMism: 123, fcLoss: 124, notSerial: 125, plcRestart: 126 };
  // 清洗机侧 Modbus 寄存器地址
  const MB_ADDR = { temp: 0x0000, alarm: 0x0100 };
  const MB_ALARM_WORDS = 32;
  // 温水器串口命令：sub = 时序图上按命令分行时用的小类
  const SU_CMD = {
    WF: { sub: 'flow' }, WT: { sub: 'temp' }, WR: { sub: 'run' }, WE: { sub: 'rst' }, WB: { sub: 'rst' },
    RS: { sub: 'stat' }, RT: { sub: 'rb' }, RA: { sub: 'det' },
  };

  const asc = s => Array.from(s, c => c.charCodeAt(0));
  const hex2 = n => (n & 255).toString(16).toUpperCase().padStart(2, '0');
  const hex4 = n => (n & 65535).toString(16).toUpperCase().padStart(4, '0');
  const dec4 = n => String(n).padStart(4, '0');

  function crc16(bytes) {
    let c = 0xFFFF;
    for (const b of bytes) {
      c ^= b;
      for (let i = 0; i < 8; i++) c = (c & 1) ? (c >>> 1) ^ 0xA001 : c >>> 1;
    }
    return c;
  }
  function withCrc(body) { const c = crc16(body); return body.concat([c & 255, c >> 8]); }

  // 串口请求：STX | 站号 2 | 命令 2 | [数据 4] | ETX | SUM 2（站号～ETX 的加算和，低 8 位，ASCII 十六进制）
  function suFrame(body) {
    const b = asc(body).concat([3]);
    const sum = b.reduce((a, x) => a + x, 0) & 255;
    return [2].concat(b, asc(hex2(sum)));
  }
  function suReq(cmd, data) {
    return {
      bytes: suFrame('01' + cmd + (data || '')),
      fields: [['STX', '02'], ['ADDR', '01'], ['CMD', cmd]].concat(data ? [['DATA', data]] : [], [['ETX', '03'], ['SUM', '']]),
    };
  }
  function suAck() { return { bytes: [6].concat(asc('01')), fields: [['ACK', '06'], ['ADDR', '01']] }; }
  function suNak(code) { return { bytes: [0x15].concat(asc('01' + code)), fields: [['NAK', '15'], ['ADDR', '01'], ['CODE', String(code)]] }; }
  function suRsp(cmd, data) {
    return {
      bytes: suFrame('01' + cmd + data),
      fields: [['STX', '02'], ['ADDR', '01'], ['CMD', cmd], ['DATA', data.length > 16 ? data.slice(0, 16) + '…(' + data.length + ')' : data], ['ETX', '03'], ['SUM', '']],
    };
  }
  function fillSum(fr) {
    const f = fr.fields.find(x => x[0] === 'SUM');
    if (f) f[1] = String.fromCharCode(fr.bytes[fr.bytes.length - 2], fr.bytes[fr.bytes.length - 1]);
    return fr;
  }

  // ------------------------------------------------------------------ 时序图的行（顺序固定，和原来的图一致）
  // type: dig 电平 / st 状态段 / bus 帧 / ana 模拟量
  const ZONES = ['fc_int', 'fc_in', 'fc_out', 'su_out', 'su_in', 'su_st', 'plc', 'inj'];
  const ROWS = [
    { id: 'fc.mode', zone: 'fc_int', type: 'st' },
    { id: 'fc.vin', zone: 'fc_int', type: 'dig' },
    { id: 'fc.vdr', zone: 'fc_int', type: 'dig' },
    { id: 'fc.alm', zone: 'fc_int', type: 'st' },
    { id: 'io.pon', zone: 'fc_in', type: 'dig' },
    { id: 'io.poff', zone: 'fc_in', type: 'dig' },
    { id: 'io.flow', zone: 'fc_in', type: 'dig' },
    { id: 'io.run', zone: 'fc_in', type: 'dig' },
    { id: 'io.rst', zone: 'fc_in', type: 'dig' },
    { id: 'io.bz', zone: 'fc_in', type: 'dig' },
    { id: 'mb.req', zone: 'fc_in', type: 'bus' },
    { id: 'mb.rsp', zone: 'fc_out', type: 'bus' },
    { id: 'do.stb', zone: 'fc_out', type: 'dig', kind: 'green' },
    { id: 'do.hvy', zone: 'fc_out', type: 'dig', kind: 'fault' },
    { id: 'do.lgt', zone: 'fc_out', type: 'dig', kind: 'fault' },
    { id: 'po.pon', zone: 'su_out', type: 'dig' },
    { id: 'po.poff', zone: 'su_out', type: 'dig' },
    { id: 'su.tx', zone: 'su_out', type: 'bus' },
    { id: 'su.rx', zone: 'su_in', type: 'bus' },
    { id: 'ht.pwr', zone: 'su_st', type: 'dig' },
    { id: 'ht.rdy', zone: 'su_st', type: 'st' },
    { id: 'ht.flow', zone: 'su_st', type: 'dig' },
    { id: 'ht.run', zone: 'su_st', type: 'dig' },
    { id: 'ht.heat', zone: 'su_st', type: 'dig' },
    { id: 'ht.stb', zone: 'su_st', type: 'dig', kind: 'green' },
    { id: 'ht.alm', zone: 'su_st', type: 'st' },
    { id: 'ht.sv', zone: 'su_st', type: 'st' },
    { id: 'ht.pv', zone: 'su_st', type: 'ana' },
    { id: 'plc.on', zone: 'plc', type: 'st' },
    { id: 'plc.st', zone: 'plc', type: 'st' },
    { id: 'plc.fail', zone: 'plc', type: 'st' },
    { id: 'plc.cf', zone: 'plc', type: 'st' },
    { id: 'plc.fcl', zone: 'plc', type: 'dig', kind: 'fault' },
    { id: 'plc.ct', zone: 'plc', type: 'st' },
    { id: 'plc.cs', zone: 'plc', type: 'st' },
    { id: 'ln.mb', zone: 'inj', type: 'st' },
    { id: 'ln.su', zone: 'inj', type: 'st' },
  ];
  // 串口发送按命令分行时的小类顺序
  const SU_SUBS = ['flow', 'temp', 'run', 'stat', 'rb', 'rst', 'det'];

  // 视图预设 = 原来 4 块图各自用到的信号
  const VIEWS = {
    all: null,
    startup: ['io.pon', 'io.poff', 'io.flow', 'mb.req', 'mb.rsp', 'do.hvy', 'po.pon', 'po.poff', 'su.tx', 'su.rx', 'ht.pwr', 'ht.rdy', 'ht.sv', 'plc.st'],
    supply: ['fc.mode', 'fc.vin', 'fc.vdr', 'io.flow', 'io.run', 'mb.req', 'mb.rsp', 'do.stb', 'su.tx', 'su.rx', 'ht.flow', 'ht.run', 'ht.heat', 'ht.stb', 'ht.sv', 'ht.pv'],
    poll: ['mb.req', 'mb.rsp', 'do.stb', 'su.tx', 'su.rx', 'ht.stb', 'ht.pv', 'plc.cs'],
    alarm: ['fc.alm', 'io.pon', 'io.flow', 'io.run', 'io.rst', 'io.bz', 'mb.req', 'mb.rsp', 'do.stb', 'do.hvy', 'do.lgt', 'po.pon', 'po.poff', 'su.tx', 'su.rx',
      'ht.pwr', 'ht.rdy', 'ht.run', 'ht.heat', 'ht.alm', 'plc.on', 'plc.st', 'plc.fail', 'plc.cf', 'plc.fcl', 'ln.mb', 'ln.su'],
  };

  // ------------------------------------------------------------------ 脚本动作
  // p: 参数种类（temp ℃ / n 次数 / alm 报警种类 / 无）
  const ACTIONS = [
    { id: 'fc.start', g: 'fc' }, { id: 'fc.end', g: 'fc' },
    { id: 'fc.manStart', g: 'fc', p: 'temp', d: 50 }, { id: 'fc.manStop', g: 'fc' },
    { id: 'fc.autoStart', g: 'fc', p: 'temp', d: 50 }, { id: 'fc.autoStop', g: 'fc' },
    { id: 'fc.setTemp', g: 'fc', p: 'temp', d: 60 },
    { id: 'fc.reset', g: 'fc' }, { id: 'fc.buzzer', g: 'fc' },
    { id: 'su.cut', g: 'inj' }, { id: 'su.fix', g: 'inj' },
    { id: 'mb.cut', g: 'inj' }, { id: 'mb.fix', g: 'inj' },
    { id: 'plc.off', g: 'inj' }, { id: 'plc.on', g: 'inj' },
    { id: 'ht.alarm', g: 'inj', p: 'alm', d: 'stop' }, { id: 'ht.clear', g: 'inj' },
    { id: 'ht.local', g: 'inj' }, { id: 'ht.serial', g: 'inj' },
    { id: 'su.drop', g: 'inj', p: 'n', d: 1 }, { id: 'su.nak', g: 'inj', p: 'n', d: 3 },
  ];

  // 场景 = 原来 9 张图 + 追加的几种。t 单位 s
  const SCENARIOS = [
    { id: '1-1', block: 1, view: 'startup', end: 42, focus: [0, 40], script: [[0, 'fc.start']] },
    { id: '1-2', block: 1, view: 'startup', end: 86, focus: [30, 84], script: [[0, 'fc.start'], [38, 'fc.end'], [48, 'fc.start']] },
    { id: '2-1', block: 2, view: 'supply', end: 62, focus: [32, 60], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [52, 'fc.manStop']] },
    { id: '2-2', block: 2, view: 'supply', end: 70, focus: [32, 68], script: [[0, 'fc.start'], [34, 'fc.autoStart', 50], [56, 'fc.autoStop']] },
    { id: '3-1', block: 3, view: 'poll', end: 50, focus: [40, 49], script: [[0, 'fc.start'], [34, 'fc.manStart', 50]] },
    { id: '4-1', block: 4, view: 'alarm', end: 72, focus: [44, 70], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'ht.alarm', 'stop'], [54, 'ht.clear'], [56, 'fc.buzzer'], [59, 'fc.reset']] },
    { id: '4-1b', block: 4, view: 'alarm', end: 72, focus: [44, 70], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'ht.alarm', 'cont'], [54, 'ht.clear'], [59, 'fc.reset']] },
    { id: '4-2', block: 4, view: 'alarm', end: 112, focus: [44, 110], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'su.cut'], [58, 'su.fix'], [60, 'fc.end'], [63, 'fc.start'], [99, 'fc.reset']] },
    { id: '4-3', block: 4, view: 'alarm', end: 74, focus: [44, 72], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'mb.cut'], [58, 'mb.fix'], [62, 'fc.reset']] },
    { id: '4-4', block: 4, view: 'alarm', end: 78, focus: [44, 76], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'plc.off'], [56, 'plc.on'], [64, 'fc.reset']] },
    { id: 'x-1', block: 5, view: 'alarm', end: 58, focus: [42, 56], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [44, 'su.drop', 1]] },
    { id: 'x-2', block: 5, view: 'alarm', end: 60, focus: [42, 58], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [44, 'su.nak', 3]] },
    { id: 'x-3', block: 5, view: 'alarm', end: 54, focus: [28, 52], script: [[0, 'ht.local'], [0, 'fc.start'], [38, 'ht.serial'], [40, 'fc.reset']] },
    { id: 'x-4', block: 5, view: 'alarm', end: 78, focus: [44, 76], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'ht.alarm', 'stop'], [52, 'fc.reset'], [60, 'ht.clear'], [64, 'fc.reset']] },
    { id: 'x-5', block: 5, view: 'alarm', end: 44, focus: [0, 42], params: { plcBootWait: 5 }, script: [[0, 'fc.start']] },
    { id: 'x-6', block: 5, view: 'alarm', end: 72, focus: [44, 70], script: [[0, 'fc.start'], [34, 'fc.manStart', 50], [46, 'ht.alarm', 'leak'], [54, 'ht.clear'], [59, 'fc.reset']] },
  ];

  // ------------------------------------------------------------------ 模拟
  function simulate(Pin, script, endSec) {
    const P = normalize(Pin);
    const END = endSec * 1000;
    let now = 0, seq = 0, fid = 0;

    // ---- 事件队列（小顶堆）
    const heap = [];
    function at(t, fn) {
      const e = { t: t < now ? now : t, s: seq++, fn };
      let i = heap.push(e) - 1;
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (heap[p].t < e.t || (heap[p].t === e.t && heap[p].s < e.s)) break;
        heap[i] = heap[p]; i = p;
      }
      heap[i] = e;
    }
    function pop() {
      const top = heap[0], e = heap.pop();
      if (heap.length) {
        let i = 0;
        for (;;) {
          let c = 2 * i + 1;
          if (c >= heap.length) break;
          if (c + 1 < heap.length && (heap[c + 1].t < heap[c].t || (heap[c + 1].t === heap[c].t && heap[c + 1].s < heap[c].s))) c++;
          if (e.t < heap[c].t || (e.t === heap[c].t && e.s < heap[c].s)) break;
          heap[i] = heap[c]; i = c;
        }
        heap[i] = e;
      }
      return top;
    }
    const after = (d, fn) => at(now + d, fn);

    // ---- 轨迹
    const tr = { sig: {}, frames: [], ana: { pv: [] }, log: [], marks: [], links: [] };
    const meas = {
      firstComm: [], runDelay: [], stbDelay: [], almDelay: [], suCutDetect: [], mbCutDetect: [], resetClear: [], resetResult: [],
      mbMaxResp: 0, mbFrames: 0, suFrames: 0, suFail: 0, mbFail: 0, suBusy: 0,
    };
    function S(id, v, k, a) {
      const arr = tr.sig[id] || (tr.sig[id] = []);
      let last = arr[arr.length - 1];
      if (last && last.t === now) { arr.pop(); last = arr[arr.length - 1]; }
      if (last && last.v === v && last.k === k && JSON.stringify(last.a) === JSON.stringify(a)) return;
      arr.push({ t: now, v, k, a });
    }
    function log(who, lvl, k, a) { tr.log.push({ t: now, who, lvl, k, a: a || [] }); }
    function mark(k, a, kind) { tr.marks.push({ t: now, k, a: a || [], kind: kind || 'model' }); }
    function link(r0, t0, r1, t1) { if (t1 - t0 <= 2500) tr.links.push({ r0, t0, r1, t1 }); }

    // ---- 线路
    const line = { mb: { cut: false, ep: 0 }, su: { cut: false, ep: 0 } };
    const charMs = { mb: 10000 / P.fcBaud, su: 10000 / P.suBaud };
    function lineOk(bus, rec) { return !line[bus].cut && line[bus].ep === rec.ep; }
    function setLine(bus, cut) {
      if (line[bus].cut === cut) return;
      line[bus].cut = cut; line[bus].ep++;
      S('ln.' + bus, cut ? 'x.cut' : '', cut ? 'fault' : null);
    }
    // 发一帧：记进轨迹，返回记录（t1 = 发完的时刻）
    function tx(bus, row, fr, meta) {
      const rec = Object.assign({
        id: ++fid, bus, row, t0: now, t1: now + fr.bytes.length * charMs[bus], bytes: fr.bytes, fields: fr.fields,
        ok: 'ok', ep: line[bus].ep, cutAtStart: line[bus].cut,
      }, meta);
      if (line[bus].cut) rec.ep = -1; // 线已经断着：肯定送不到
      tr.frames.push(rec);
      if (bus === 'mb') meas.mbFrames++; else { meas.suFrames++; meas.suBusy += rec.t1 - rec.t0; }
      return rec;
    }
    function noReply(row, bus, t0, pair) {
      tr.frames.push({ id: ++fid, bus, row, t0, t1: now, code: 'NONE', lab: { k: 'f.NONE' }, bytes: [], fields: [], ok: 'none', pair, kind: 'none' });
    }

    // ================================================================ 温水器
    const H = {
      pwr: false, rdy: false, gen: 0, mode: 'serial', flow: false, run: false, sv: 250, pv: 25, stb: false, stbT: null,
      cause: { stop: false, cont: false, leak: false }, lat: { stop: false, cont: false, leak: false },
      drop: 0, nak: 0, lastRx: 0, almAt: null, stbAt: null, pvRec: null,
    };
    const hHeat = () => H.pwr && H.run && !H.lat.stop && !H.lat.leak;
    function hStatus() {
      let s = 0;
      if (H.run) s |= ST.RUN;
      if (H.flow) s |= ST.FLOW;
      if (hHeat()) s |= ST.HEAT;
      if (H.stb) s |= ST.STB;
      if (H.lat.stop || H.lat.leak) s |= ST.SERR;
      if (H.lat.cont) s |= ST.CERR;
      if (H.lat.leak) s |= ST.LEAK;
      if (H.mode === 'serial') s |= ST.SER;
      return s;
    }
    function hAlmList() {
      const a = [];
      if (H.lat.leak) a.push(ALM.leak);
      if (H.lat.stop) a.push(ALM.stop);
      if (H.lat.cont) a.push(ALM.cont);
      return a;
    }
    function hTrace() {
      S('ht.pwr', H.pwr ? 1 : 0);
      S('ht.rdy', !H.pwr ? '' : H.rdy ? (H.mode === 'serial' ? 'x.ready' : 'x.local') : 'x.booting', !H.pwr ? null : H.rdy ? (H.mode === 'serial' ? 'green' : 'fault') : 'gray');
      S('ht.flow', H.flow ? 1 : 0);
      S('ht.run', H.run ? 1 : 0);
      S('ht.heat', hHeat() ? 1 : 0);
      S('ht.stb', H.stb ? 1 : 0);
      const al = [];
      ['leak', 'stop', 'cont'].forEach(x => {
        if (H.lat[x]) al.push(H.cause[x] ? 'al.' + x : 'al.' + x + '.lat');
      });
      S('ht.alm', al.length ? 'x.list' : '', al.length ? (al.every(x => /\.lat$/.test(x)) ? 'tbd' : 'fault') : null, al);
      S('ht.sv', H.pwr ? 'x.temp' : '', 'val', [(H.sv / 10).toFixed(1)]);
    }
    function hPower(on) {
      if (on === H.pwr) return;
      H.pwr = on; H.rdy = false; H.gen++;
      H.flow = H.run = H.stb = false; H.stbT = null; H.stbAt = null;
      if (on) {
        H.sv = 250;
        H.lat = { stop: H.cause.stop, cont: H.cause.cont, leak: H.cause.leak };
        H.lastRx = now;
        const g = H.gen;
        log('ht', 'info', 'l.htPowerOn', [P.htBoot / 1000]);
        after(P.htBoot, () => {
          if (H.gen !== g) return;
          H.rdy = true; log('ht', 'info', 'l.htReady'); mark('m.htReady'); hTrace();
        });
      } else {
        log('ht', 'warn', 'l.htPowerOff');
      }
      hTrace();
    }
    function hAlarm(type) {
      H.cause[type] = true;
      if (!H.pwr) return;
      H.lat[type] = true; H.almAt = now;
      if (type !== 'cont') { H.run = false; H.flow = false; H.stb = false; H.stbT = null; }
      log('ht', 'err', 'l.htAlarm', ['al.' + type, ALM[type]]);
      hTrace();
    }
    function hClear() {
      H.cause = { stop: false, cont: false, leak: false };
      if (!P.htLightLatch) H.lat.cont = false;
      log('ht', 'info', 'l.htCauseGone');
      hTrace();
    }
    function hTick() {
      const dt = 0.05;
      const target = hHeat() ? H.sv / 10 : 25, rate = (hHeat() ? P.htRate : P.htCool) * dt;
      const d = target - H.pv;
      H.pv += Math.abs(d) <= rate ? d : Math.sign(d) * rate;
      // 安定：加热中，|PV − SV| 在范围内保持一段时间
      if (hHeat() && Math.abs(H.pv - H.sv / 10) <= P.htBand * (H.stb ? 2 : 1)) {
        if (H.stbT === null) H.stbT = now;
        if (!H.stb && now - H.stbT >= P.htStabTime) { H.stb = true; H.stbAt = now; log('ht', 'info', 'l.htStable', [(H.sv / 10).toFixed(1)]); hTrace(); }
      } else {
        H.stbT = null;
        if (H.stb) { H.stb = false; H.stbAt = null; hTrace(); }
      }
      if (P.htWatchdog > 0 && H.pwr && H.rdy && H.run && now - H.lastRx > P.htWatchdog) {
        H.run = false; H.flow = false; log('ht', 'err', 'l.htWatchdog'); hTrace();
      }
      if (H.pvRec === null || Math.abs(H.pv - H.pvRec) >= 0.05) { H.pvRec = H.pv; tr.ana.pv.push({ t: now, v: H.pv }); }
      after(50, hTick);
    }
    // 收到一帧（已经确认线是通的）
    function hRx(rec, job) {
      if (!H.pwr || !H.rdy) { rec.ok = 'ignored'; return; }
      H.lastRx = now;
      if (H.drop > 0) { H.drop--; rec.ok = 'ignored'; log('inj', 'warn', 'l.injDrop'); return; }
      let rsp, lab, kind = 'on';
      const cmd = job.cmd, v = job.data ? parseInt(job.data, 10) : 0;
      const nak = c => { rsp = suNak(c); lab = { k: 'f.NAK' + c }; kind = c === 1 ? 'fault' : 'gray'; };
      const ack = () => { rsp = suAck(); lab = { k: 'f.ACK' }; };
      if (H.nak > 0) { H.nak--; nak(1); log('inj', 'warn', 'l.injNak'); }
      else if (cmd === 'RS') {
        const s = hStatus(); rsp = suRsp('RS', hex4(s)); lab = { k: 'f.rRS', a: [s] };
        if (s & (ST.SERR | ST.LEAK)) kind = 'fault';
        rsp.val = s;
      } else if (cmd === 'RT') { rsp = suRsp('RT', dec4(H.sv)); lab = { k: 'f.rRT', a: [(H.sv / 10).toFixed(1)] }; rsp.val = H.sv; }
      else if (cmd === 'RA') {
        const list = hAlmList(), nib = new Array(128).fill(0);
        list.forEach(n => { nib[(n - 1) >> 2] |= 1 << ((n - 1) & 3); });
        rsp = suRsp('RA', nib.map(x => x.toString(16).toUpperCase()).join('')); lab = { k: 'f.rRA', a: [list.join(', ')] }; kind = list.length ? 'fault' : 'on';
        rsp.val = list;
      } else if (H.mode !== 'serial') nak(2);
      else if (cmd === 'WF') {
        if (v) { H.flow = true; ack(); }
        else if (H.flow && !H.run) { H.flow = false; ack(); }
        else nak(2);
      } else if (cmd === 'WT') {
        if (v < 250 || v > 850) nak(1); else { H.sv = v; ack(); }
      } else if (cmd === 'WR') {
        if (v) {
          if (H.lat.stop || H.lat.leak || !H.flow) nak(2);
          else { if (!H.run) { H.run = true; if (W.runOnAt !== null) { meas.runDelay.push(now - W.runOnAt); W.runOnAt = null; } } ack(); }
        } else if (H.run) { H.run = false; ack(); }
        else nak(2);
      } else if (cmd === 'WE') {
        ['stop', 'cont', 'leak'].forEach(x => { if (!H.cause[x]) H.lat[x] = false; });
        log('ht', 'info', hAlmList().length ? 'l.htResetKeep' : 'l.htResetOk'); ack();
      } else if (cmd === 'WB') ack();
      else nak(1);
      hTrace();
      const g = H.gen;
      after(P.htRespDelay, () => {
        if (H.gen !== g || !H.pwr) return;
        const r = tx('su', 'su.rx', fillSum(rsp), { code: rsp.fields[0][0] === 'STX' ? 'r' + cmd : rsp.fields[0][0], lab, kind, pair: rec.id, sub: job.sub, periodic: job.periodic });
        rec.pair = r.id;
        at(r.t1, () => {
          if (!lineOk('su', r)) { r.ok = 'lost'; return; }
          plcSuRx(r, rsp);
        });
      });
    }

    // ================================================================ 清洗机
    const W = {
      started: false, io: { pon: false, poff: false, flow: false, run: false, rst: false, bz: false },
      q: [], txn: null, freeAt: 0, pollGen: 0, lastRead: -1e9, readFail: 0, bits: [], prevBits: '',
      alm: {}, mode: 'off', di: { hvy: false, lgt: false, stb: false }, vin: false, vdr: false, seqGen: 0,
      runOnAt: null, rstAt: null,
    };
    function wTrace() {
      S('fc.mode', 'wm.' + W.mode, W.mode === 'alarm' ? 'fault' : W.mode === 'off' ? 'gray' : 'val');
      S('fc.vin', W.vin ? 1 : 0); S('fc.vdr', W.vdr ? 1 : 0);
      const a = Object.keys(W.alm).filter(k => W.alm[k]).map(k => 'wa.' + k);
      S('fc.alm', a.length ? 'x.list' : '', 'fault', a);
    }
    function wSet(name, v) {
      if (W.io[name] === v) return;
      W.io[name] = v; S('io.' + name, v ? 1 : 0);
      if (name === 'run' && v) W.runOnAt = now;
      plcWake();
    }
    function wPulse(name) { wSet(name, true); after(P.pwrPulse, () => wSet(name, false)); }
    function wAlarm(k) { if (W.alm[k]) return; W.alm[k] = true; log('fc', 'err', 'l.wAlarm', ['wa.' + k]); wTrace(); }

    // ---- Modbus 主站
    function mbEnq(job, front) { if (front) W.q.unshift(job); else W.q.push(job); mbPump(); }
    function mbWrite(v, init) {
      // 新的写把还没发的旧写顶掉（只关心最后要的温度）
      W.q = W.q.filter(j => j.type !== 'write');
      mbEnq({ type: 'write', val: v, init: !!init }, true);
    }
    function mbPump() {
      if (W.txn || !W.q.length) return;
      if (now < W.freeAt) { at(W.freeAt, mbPump); return; }
      const job = W.q.shift();
      job.att = (job.att || 0) + 1;
      let body, meta;
      if (job.type === 'write') {
        body = [1, 6, MB_ADDR.temp >> 8, MB_ADDR.temp & 255, job.val >> 8, job.val & 255];
        meta = { code: 'MW', lab: { k: 'f.MW', a: [(job.val / 10).toFixed(1)] }, sub: 'w', kind: 'on' };
      } else {
        body = [1, 3, MB_ADDR.alarm >> 8, MB_ADDR.alarm & 255, 0, MB_ALARM_WORDS];
        meta = { code: 'MR', lab: { k: 'f.MR' }, sub: 'r', kind: 'on', periodic: true };
        W.lastRead = now;
      }
      const bytes = withCrc(body);
      const fields = [['ADDR', hex2(bytes[0])], ['FC', hex2(bytes[1])], ['REG', hex2(bytes[2]) + hex2(bytes[3])],
        [job.type === 'write' ? 'VAL' : 'CNT', hex2(bytes[4]) + hex2(bytes[5])], ['CRC', hex2(bytes[6]) + hex2(bytes[7])]];
      meta.attempt = job.att;
      const rec = tx('mb', 'mb.req', { bytes, fields }, meta);
      const txn = W.txn = { job, rec, done: false };
      at(rec.t1, () => {
        if (!lineOk('mb', rec)) rec.ok = 'lost';
        else if (!G.on) rec.ok = 'ignored';
        else plcMbRx(job, rec, txn);
        at(rec.t1 + P.fcTimeout, () => {
          if (txn.done) return;
          txn.done = true; W.txn = null;
          rec.noresp = true; noReply('mb.rsp', 'mb', rec.t1, rec.id);
          meas.mbFail++;
          mbFail(job);
        });
      });
    }
    function mbDone(txn, r, rsp) {
      if (txn.done) { r.ok = 'late'; return; }
      txn.done = true; W.txn = null; W.freeAt = now + P.fcGap;
      meas.mbMaxResp = Math.max(meas.mbMaxResp, now - txn.rec.t1);
      const job = txn.job;
      if (job.type === 'write') {
        if (job.init) { W.mode = W.mode === 'init' ? 'idle' : W.mode; log('fc', 'info', 'l.wInitOk'); wTrace(); wPollStart(); }
      } else {
        W.readFail = 0; W.bits = rsp.val;
        schedRead();
      }
      mbPump();
    }
    function mbFail(job) {
      if (job.type === 'write') {
        log('fc', 'warn', 'l.wWriteTimeout', [job.att, P.fcRetry]);
        if (job.att < P.fcRetry) { mbEnq(job, true); return; }
        if (job.init) wAlarm('init');
        else { wAlarm('tset'); wStop('tset'); }
        mbPump();
      } else {
        W.readFail++;
        log('fc', 'warn', 'l.wReadTimeout', [W.readFail, P.fcRetry]);
        if (W.readFail >= P.fcRetry) wAlarm('read');
        schedRead(); mbPump();
      }
    }
    function schedRead() {
      const g = W.pollGen, t = Math.max(now, W.lastRead + P.fcPoll);
      at(t, () => {
        if (W.pollGen !== g) return;
        if (!W.q.some(j => j.type === 'read') && !(W.txn && W.txn.job.type === 'read')) mbEnq({ type: 'read' });
      });
    }
    function wPollStart() { W.pollGen++; W.lastRead = now - P.fcPoll + Math.min(P.fcPoll, 200); schedRead(); }
    function wInit() { W.mode = 'init'; wTrace(); mbWrite(250, true); }

    // ---- 动作
    function wStart() {
      W.started = true; W.pollGen++; W.q = [];
      log('fc', 'info', 'l.wStart');
      wPulse('pon'); wSet('flow', true);
      wInit();
    }
    function wEnd() {
      log('fc', 'info', 'l.wEnd');
      W.seqGen++; W.pollGen++; W.q = [];
      wSet('run', false); wSet('flow', false); W.vin = W.vdr = false;
      wPulse('poff');
      W.mode = 'off'; wTrace();
    }
    function wSupplyOn(temp) {
      wSet('flow', true); wSet('run', true); mbWrite(Math.round(temp * 10));
    }
    function wManStart(temp) {
      if (!W.started) return;
      W.seqGen++; W.mode = 'man'; W.vin = true; log('fc', 'info', 'l.wManStart', [temp.toFixed(1)]);
      wSupplyOn(temp); wTrace();
    }
    function wManStop() {
      if (W.mode !== 'man') return;
      const g = ++W.seqGen;
      log('fc', 'info', 'l.wManStop');
      wSet('run', false); mbWrite(250); W.mode = 'idle'; wTrace();
      after(P.valveDelay, () => { if (W.seqGen === g) { W.vin = false; wTrace(); } });
    }
    function wAutoStart(temp) {
      if (!W.started) return;
      const g = ++W.seqGen;
      W.mode = 'prep'; W.vdr = true; log('fc', 'info', 'l.wAutoPrep'); wTrace();
      after(P.autoRunDelay, () => {
        if (W.seqGen !== g) return;
        W.mode = 'wait'; log('fc', 'info', 'l.wAutoRun', [temp.toFixed(1)]);
        wSupplyOn(temp); wTrace();
        if (W.di.stb) wAutoSupply();
      });
    }
    function wAutoSupply() {
      const g = W.seqGen;
      W.mode = 'sup'; W.vin = true; log('fc', 'info', 'l.wAutoSupply'); mark('m.supply'); wTrace();
      after(P.valveDelay, () => { if (W.seqGen === g) { W.vdr = false; wTrace(); } });
    }
    function wAutoStop() {
      if (!['prep', 'wait', 'sup'].includes(W.mode)) return;
      const g = ++W.seqGen;
      W.mode = 'stopdly'; W.vdr = true; log('fc', 'info', 'l.wAutoSupStop'); wTrace();
      after(P.valveDelay, () => { if (W.seqGen === g) { W.vin = false; wTrace(); } });
      after(P.autoRunDelay, () => {
        if (W.seqGen !== g) return;
        log('fc', 'info', 'l.wAutoPrepStop');
        wSet('run', false); mbWrite(250); W.mode = 'idle'; wTrace();
        after(P.valveDelay, () => { if (W.seqGen === g) { W.vdr = false; wTrace(); } });
      });
    }
    function wStop(why) {
      const was = W.io.run;
      W.seqGen++;
      wSet('run', false); wSet('flow', false); W.vin = W.vdr = false;
      if (W.mode !== 'alarm' || was) log('fc', 'err', 'l.wStop', ['wa.' + why]);
      W.mode = 'alarm';
      if (was && why !== 'tset') mbWrite(250);
      wTrace();
    }
    function wReset() {
      log('fc', 'info', 'l.wReset', [P.resetHold / 1000]);
      W.alm.read = false; // 报警读取异常：画面上无条件解除
      W.rstAt = now; wSet('rst', true); wTrace();
      after(P.resetHold, () => {
        wSet('rst', false);
        const ok = !W.di.hvy && !W.di.lgt && W.bits.length === 0;
        W.rstAt = null;
        meas.resetResult.push({ t: now, ok });
        if (ok) {
          const needInit = W.alm.init;
          W.alm = {};
          if (W.mode === 'alarm') W.mode = W.started ? 'idle' : 'off';
          log('fc', 'info', 'l.wResetOk'); mark('m.resetOk');
          if (needInit) wInit();
        } else {
          log('fc', 'err', 'l.wResetNg', [W.di.hvy ? 1 : 0, W.di.lgt ? 1 : 0, W.bits.join(', ') || '-']); mark('m.resetNg', [], 'fault');
        }
        wTrace();
      });
    }
    function wBuzzer() { log('fc', 'info', 'l.wBuzzer'); wSet('bz', true); after(300, () => wSet('bz', false)); }
    // 输入点（PLC 的 DO）变了
    function wDI() {
      const hvy = !G.on || G.out.hvy, lgt = !G.on || G.out.lgt, stb = G.on && G.out.stb;
      const p = W.di; W.di = { hvy, lgt, stb };
      if (hvy && !p.hvy && W.started) {
        wAlarm('heavy');
        after(P.fcReact, () => { if (W.alm.heavy && P.fcStopOnHeavy && W.mode !== 'alarm') wStop('heavy'); });
      }
      if (lgt && !p.lgt && W.started) wAlarm('light');
      if (stb && !p.stb && W.mode === 'wait') wAutoSupply();
    }

    // ================================================================ PLC 网关
    let G;
    function gNew() {
      return {
        on: true, gen: G ? G.gen + 1 : 0, st: 'off', waitUntil: 0, cutUntil: -1,
        in: Object.assign({}, W.io), out: { stb: false, hvy: false, lgt: false, pon: false, poff: false },
        cacheTemp: 250, cacheAt: 0, cache: { st: 0, alm: [], valid: false }, detailFor: 0,
        cmd: { run: false, flow: false, temp: null }, dKey: '', dSince: 0, seqBusy: false, rbTemp: null, edgeRun: 0,
        q: [], txn: null, suFreeAt: 0, lastStatusAt: -1e9, fail: 0, nakc: 0, mism: 0,
        cf: null, notSerial: false, restart: false, fcLossAct: false, fcLossLatch: false, lastFcRx: 0,
        wakes: {}, cause: null, ponAt: null, lastRsp: {},
      };
    }
    G = gNew();
    function plcWakeAt(t) {
      const q = Math.ceil((t + 1e-6) / P.plcScan) * P.plcScan; // 对到下一个扫描周期
      if (G.wakes[q]) return;
      G.wakes[q] = 1;
      const g = G.gen;
      at(q, () => { if (G.gen !== g) return; delete G.wakes[q]; plcLogic(); });
    }
    function plcWake() { if (G.on) plcWakeAt(now); }

    function plcTrace() {
      S('plc.on', G.on ? 'x.run' : 'x.down', G.on ? 'green' : 'fault');
      S('plc.st', G.on ? 'st.' + G.st : '', G.st === 'cfstop' ? 'fault' : G.st === 'off' ? 'gray' : 'val');
      const n = Math.max(G.fail, G.nakc, G.mism);
      S('plc.fail', G.on && n ? 'x.num' : '', 'val', [n]);
      const lat = [];
      if (G.on) {
        if (G.cf) lat.push('cf.' + G.cf);
        if (G.notSerial) lat.push('cf.notSerial');
        if (G.restart) lat.push('cf.restart');
        if (G.fcLossLatch) lat.push('cf.fcLoss');
      }
      S('plc.cf', lat.length ? 'x.list' : '', 'fault', lat);
      S('plc.fcl', G.on && G.fcLossAct ? 1 : 0);
      S('plc.ct', G.on ? 'x.temp' : '', 'val', [(G.cacheTemp / 10).toFixed(1)]);
      S('plc.cs', G.on && G.cache.valid ? 'x.status' : '', 'val', [G.cache.st]);
    }
    function plcAlarmBits() {
      const a = G.st === 'run' || G.st === 'cfstop' ? G.cache.alm.slice() : [];
      if (G.cf === 'timeout') a.push(ALM.cfTimeout);
      if (G.cf === 'nak') a.push(ALM.cfNak);
      if (G.cf === 'mismatch') a.push(ALM.cfMism);
      if (G.fcLossLatch) a.push(ALM.fcLoss);
      if (G.notSerial) a.push(ALM.notSerial);
      if (G.restart) a.push(ALM.plcRestart);
      return a.sort((x, y) => x - y);
    }
    // 输出点
    function plcOut() {
      const s = G.cache.st, run = G.st === 'run';
      const o = {
        stb: run && !G.cf && !G.fcLossLatch && !!(s & ST.STB),
        hvy: !!(G.cf || G.notSerial || G.restart || G.fcLossLatch || (run && (s & (ST.SERR | ST.LEAK)))),
        lgt: !!(G.restart || (run && (s & ST.CERR))),
        pon: !!G.in.pon, poff: !!G.in.poff || now < G.cutUntil,
      };
      const p = G.out; G.out = o;
      const c = G.cause; G.cause = null;
      let diChanged = false;
      ['stb', 'hvy', 'lgt'].forEach(k => {
        if (o[k] === p[k]) return;
        diChanged = true;
        S('do.' + k, o[k] ? 1 : 0);
        if (c) link(c.row, c.t, 'do.' + k, now);
        if (k === 'stb' && o.stb && H.stbAt !== null) { meas.stbDelay.push(now - H.stbAt); H.stbAt = null; mark('m.stbDo', [], 'green'); }
        if ((k === 'hvy' || k === 'lgt') && o[k] && H.almAt !== null) { meas.almDelay.push(now - H.almAt); H.almAt = null; }
        if (k === 'hvy' && o.hvy) mark('m.heavy', [], 'fault');
        if (k === 'hvy' && !o.hvy && W.rstAt !== null) meas.resetClear.push(now - W.rstAt);
      });
      if (o.pon !== p.pon) { S('po.pon', o.pon ? 1 : 0); if (o.pon) hPower(true); }
      if (o.poff !== p.poff) { S('po.poff', o.poff ? 1 : 0); if (o.poff) hPower(false); }
      plcTrace();
      if (diChanged) after(1, wDI);
    }

    // ---- 清洗机侧：Modbus 从站（自带功能：收到就回，读写都只碰 PLC 内部寄存器）
    function plcMbRx(job, rec, txn) {
      G.lastFcRx = now;
      if (G.fcLossAct) { G.fcLossAct = false; log('plc', 'info', 'l.pFcBack'); plcWake(); }
      let body, lab, kind = 'on', val;
      if (job.type === 'write') {
        if (G.cacheTemp !== job.val || G.cmd.temp !== job.val) { G.cacheTemp = job.val; G.cacheAt = now; plcWake(); }
        body = rec.bytes.slice(0, 6); lab = { k: 'f.rMW' };
      } else {
        val = plcAlarmBits();
        const words = new Array(MB_ALARM_WORDS).fill(0);
        val.forEach(n => { words[(n - 1) >> 4] |= 1 << ((n - 1) & 15); });
        body = [1, 3, MB_ALARM_WORDS * 2];
        words.forEach(w => body.push(w >> 8, w & 255));
        lab = val.length ? { k: 'f.rMRa', a: [val.join(', ')] } : { k: 'f.rMR0' };
        if (val.length) kind = 'fault';
      }
      const g = G.gen;
      after(P.slaveDelay, () => {
        if (G.gen !== g || !G.on) return;
        const bytes = withCrc(body);
        const fields = job.type === 'write'
          ? [['ADDR', hex2(bytes[0])], ['FC', hex2(bytes[1])], ['REG', hex2(bytes[2]) + hex2(bytes[3])], ['VAL', hex2(bytes[4]) + hex2(bytes[5])], ['CRC', hex2(bytes[6]) + hex2(bytes[7])]]
          : [['ADDR', hex2(bytes[0])], ['FC', hex2(bytes[1])], ['BC', hex2(bytes[2])], ['DATA', MB_ALARM_WORDS + ' words'], ['CRC', hex2(bytes[bytes.length - 2]) + hex2(bytes[bytes.length - 1])]];
        const key = job.type + ':' + (val ? val.join(',') : '');
        const changed = job.type === 'read' && G.lastRsp.mb !== undefined && G.lastRsp.mb !== key;
        if (job.type === 'read') G.lastRsp.mb = key;
        const r = tx('mb', 'mb.rsp', { bytes, fields }, { code: job.type === 'write' ? 'rMW' : 'rMR', lab, kind, pair: rec.id, sub: job.type === 'write' ? 'w' : 'r', periodic: job.type === 'read', changed });
        rec.pair = r.id; if (changed) rec.changed = true;
        at(r.t1, () => {
          if (G.gen !== g) { r.ok = 'lost'; return; }
          if (!lineOk('mb', r)) { r.ok = 'lost'; return; }
          mbDone(txn, r, { val });
        });
      });
    }

    // ---- 温水器侧：串口主站
    function suEnq(job) { job.sub = job.sub || SU_CMD[job.cmd].sub; G.q.push(job); suPump(); }
    function suPump() {
      if (!G.on || G.txn || !G.q.length) return;
      if (G.st !== 'run' && G.st !== 'init') { G.q.length = 0; return; } // 装置结束 / 等 30 s / 已切电源：不发任何帧
      const g = G.gen;
      if (now < G.suFreeAt) { at(G.suFreeAt, () => { if (G.gen === g) suPump(); }); return; }
      const job = G.q[0];
      job.att = (job.att || 0) + 1;
      const lab = { k: 'f.' + job.cmd + (job.cmd === 'WF' || job.cmd === 'WR' ? (parseInt(job.data, 10) ? '1' : '0') : ''), a: job.cmd === 'WT' ? [(parseInt(job.data, 10) / 10).toFixed(1)] : [] };
      const rec = tx('su', 'su.tx', fillSum(suReq(job.cmd, job.data)), { code: job.cmd, lab, kind: 'on', sub: job.sub, periodic: !!job.periodic, attempt: job.att, why: job.kind });
      if (job.link) { link(job.link.row, job.link.t, 'su.tx', now); job.link = null; }
      const txn = G.txn = { job, rec, done: false };
      at(rec.t1, () => {
        if (G.gen !== g) { rec.ok = 'lost'; return; }
        if (lineOk('su', rec)) hRx(rec, job); else rec.ok = 'lost';
        at(rec.t1 + P.suTimeout, () => {
          if (G.gen !== g || txn.done) return;
          txn.done = true; G.txn = null;
          rec.noresp = true; noReply('su.rx', 'su', rec.t1, rec.id);
          meas.suFail++;
          G.fail++;
          log('plc', 'warn', 'l.pTimeout', [G.fail, P.suRetry]);
          if (G.fail >= P.suRetry) commFault('timeout');
          else { plcTrace(); suPump(); }
        });
      });
    }
    function plcSuRx(r, rsp) {
      const txn = G.txn;
      if (!G.on || !txn || txn.done || txn.rec.id !== r.pair) { r.ok = 'late'; return; }
      txn.done = true; G.txn = null; G.suFreeAt = now + P.suGap;
      const job = txn.job, head = rsp.fields[0][0];
      if (head === 'NAK' && rsp.fields[2][1] === '1') {
        // 「数据异常」：算通信失败
        meas.suFail++; G.nakc++;
        log('plc', 'warn', 'l.pNak1', [G.nakc, P.suRetry]);
        if (G.nakc >= P.suRetry) commFault('nak');
        else { plcTrace(); suPump(); }
        return;
      }
      if (G.fail || G.nakc) log('plc', 'info', 'l.pRecovered');
      G.fail = 0; G.nakc = 0;
      G.q.shift();
      if (head === 'NAK') { log('plc', 'info', 'l.pNak2', [txn.rec.lab.k]); if (job.onBusy) job.onBusy(); }
      else if (job.cmd === 'RS') onStatus(rsp.val, job, r);
      else if (job.onOk) job.onOk(rsp.val);
      if (!G.q.length) plcWake();
      suPump();
    }
    function commFault(type) {
      const first = !G.cf;
      G.cf = G.cf || type;
      G.q.length = 0; G.txn = null; G.seqBusy = false; G.fail = 0; G.nakc = 0; G.mism = 0;
      log('plc', 'err', 'l.pCommFault', ['cf.' + type]);
      if (first) {
        mark('m.commFault', ['cf.' + type], 'fault');
        if (line.su.cutAt != null) { meas.suCutDetect.push(now - line.su.cutAt); line.su.cutAt = null; }
      }
      if (P.optCutPower) {
        G.st = 'cfstop'; G.cutUntil = now + P.pwrPulse;
        log('plc', 'err', 'l.pCutPower');
        plcWakeAt(G.cutUntil);
      } else G.lastStatusAt = now;
      G.cause = { row: 'su.rx', t: now };
      plcOut();
    }
    function clearLatches(s) {
      const had = G.cf || G.restart || G.fcLossLatch || G.notSerial;
      G.cf = null; G.restart = false; G.fcLossLatch = G.fcLossAct; G.mism = 0;
      if (s !== null) G.notSerial = !(s & ST.SER);
      if (had) log('plc', 'info', G.fcLossLatch || G.notSerial ? 'l.pLatchKeep' : 'l.pLatchClr');
    }
    function onStatus(s, job, r) {
      G.lastStatusAt = now;
      const key = 's:' + s;
      if (G.lastRsp.su !== undefined && G.lastRsp.su !== key) { r.changed = true; const q = tr.frames.find(f => f.id === r.pair); if (q) q.changed = true; }
      G.lastRsp.su = key;
      G.cache.st = s; G.cache.valid = true;
      if (job.kind === 'init') {
        if (G.ponAt !== null) { meas.firstComm.push(now - G.ponAt); G.ponAt = null; }
        G.notSerial = !(s & ST.SER);
        if (G.notSerial) { log('plc', 'err', 'l.pNotSerial'); mark('m.notSerial', [], 'fault'); }
        else log('plc', 'info', 'l.pInitOk');
        G.st = 'run';
        G.cmd = { run: !!(s & ST.RUN), flow: !!(s & ST.FLOW), temp: null };
      }
      if (job.kind === 'reset') clearLatches(s);
      if (job.kind === 'readback') checkReadback(s);
      if (G.st !== 'run') return; // 读回 3 次不一致 → 已经按通信异常处理
      const err = s & (ST.SERR | ST.CERR | ST.LEAK);
      if (!err) { G.cache.alm = []; G.detailFor = 0; }
      else if ((!P.optDetailOnErr || err !== G.detailFor) && !G.q.some(j => j.cmd === 'RA')) {
        suEnq({ cmd: 'RA', onOk: list => { G.cache.alm = list; G.detailFor = err; log('plc', 'info', 'l.pDetail', [list.join(', ') || '-']); } });
      }
      G.cause = { row: 'su.rx', t: now };
      plcWake();
    }
    // 写完读回核对（ACK 只表示收到）
    function seqJobs(D, full) {
      const t = dec4(D.temp), jobs = [];
      if (D.run && (full || !G.cmd.run)) jobs.push(['WF', '0001'], ['WT', t], ['WR', '0001']);
      else if (!D.run && (full || G.cmd.run)) { if (full || D.temp !== G.cmd.temp) jobs.push(['WT', t]); jobs.push(['WR', '0000'], ['WF', '0000']); }
      else jobs.push(['WT', t]);
      return jobs;
    }
    function startSeq(D, full, lk) {
      const jobs = seqJobs(D, full);
      G.cmd = { run: D.run, flow: D.flow, temp: D.temp };
      G.seqBusy = true;
      log('plc', 'info', full ? 'l.pResend' : 'l.pSeq', [jobs.map(j => j[0] + (j[0] === 'WT' ? '' : j[1].slice(-1))).join(' → ')]);
      jobs.forEach((j, i) => {
        const job = { cmd: j[0], data: j[1], kind: 'seq' };
        if (i === 0 && lk) job.link = lk;
        if (i === jobs.length - 1 && !P.optReadback) job.onOk = job.onBusy = () => { G.seqBusy = false; plcWake(); };
        suEnq(job);
      });
      if (P.optReadback) {
        suEnq({ cmd: 'RT', kind: 'readback', onOk: v => { G.rbTemp = v; } });
        suEnq({ cmd: 'RS', kind: 'readback', sub: 'rb' });
      }
    }
    function checkReadback(s) {
      const D = G.cmd, cant = s & (ST.SERR | ST.LEAK);
      const bad = G.rbTemp !== D.temp || (!cant && (!!(s & ST.RUN) !== D.run || !!(s & ST.FLOW) !== D.flow));
      if (!bad) { G.mism = 0; G.seqBusy = false; log('plc', 'info', 'l.pRbOk'); return; }
      G.mism++;
      log('plc', 'warn', 'l.pRbNg', [G.mism, P.mismatchLimit]);
      if (G.mism >= P.mismatchLimit) { commFault('mismatch'); return; }
      startSeq(D, true, null);
    }
    function reconcile() {
      if (G.st !== 'run' || G.notSerial) return;
      const run = !!(G.in.run && G.in.flow) && !G.fcLossLatch;
      const D = { run, flow: run, temp: G.cacheTemp };
      const key = run + '|' + D.temp;
      if (key !== G.dKey) { G.dKey = key; G.dSince = now; }
      if (D.run === G.cmd.run && D.flow === G.cmd.flow && D.temp === G.cmd.temp) return;
      if (G.seqBusy) return;
      if (now < G.dSince + P.settle) { plcWakeAt(G.dSince + P.settle); return; }
      const lk = D.run !== G.cmd.run ? (G.fcLossLatch ? null : { row: 'io.run', t: G.edgeRun }) : { row: 'mb.req', t: G.cacheAt };
      startSeq(D, false, lk);
    }
    function doReset() {
      if (G.st !== 'run') { log('plc', 'warn', 'l.pRstIgnored', ['st.' + G.st]); return; }
      log('plc', 'info', 'l.pRst');
      suEnq({ cmd: 'WE', data: '0001', kind: 'reset', link: { row: 'io.rst', t: now } });
      const wb = { cmd: 'WB', data: '0001', kind: 'reset' };
      if (!P.optResetRead) wb.onOk = wb.onBusy = () => { clearLatches(null); plcWake(); };
      suEnq(wb);
      if (P.optResetRead) suEnq({ cmd: 'RS', kind: 'reset', sub: 'rb' });
    }
    // 一次扫描
    function plcLogic() {
      if (!G.on) return;
      const i = Object.assign({}, W.io), p = G.in;
      G.in = i;
      const rise = k => i[k] && !p[k];
      if (i.run !== p.run) G.edgeRun = now;
      if (rise('pon')) {
        // 转发远程电源投入，从这一刻起计 30 s，期间不发任何帧
        G.st = 'wait'; G.waitUntil = now + P.plcBootWait; G.ponAt = now;
        G.q.length = 0; G.txn = null; G.seqBusy = false; G.fail = G.nakc = G.mism = 0;
        G.cmd = { run: false, flow: false, temp: null }; G.dKey = '';
        G.cache = { st: 0, alm: [], valid: false }; G.detailFor = 0; G.lastRsp.su = undefined;
        G.lastFcRx = now;
        log('plc', 'info', 'l.pPowerOn', [P.plcBootWait / 1000]);
        plcWakeAt(G.waitUntil);
      }
      if (rise('poff')) {
        G.st = 'off'; G.q.length = 0; G.txn = null; G.seqBusy = false; G.fail = G.nakc = 0;
        G.cache = { st: 0, alm: [], valid: false };
        log('plc', 'info', 'l.pPowerOff');
      }
      if (G.st === 'wait' && now >= G.waitUntil) {
        G.st = 'init'; mark('m.waitDone'); log('plc', 'info', 'l.pWaitDone');
        suEnq({ cmd: 'RS', kind: 'init' });
      }
      if (rise('rst')) doReset();
      if (rise('bz') && G.st === 'run') suEnq({ cmd: 'WB', data: '0001', kind: 'reset', link: { row: 'io.bz', t: now } });
      // 清洗机断线：一段时间没收到请求
      if (G.st !== 'off' && !G.fcLossAct) {
        if (now - G.lastFcRx >= P.fcLossTime) {
          G.fcLossAct = true; G.fcLossLatch = true;
          log('plc', 'err', 'l.pFcLoss', [P.fcLossTime / 1000]); mark('m.fcLoss', [], 'fault');
          if (line.mb.cutAt != null) { meas.mbCutDetect.push(now - line.mb.cutAt); line.mb.cutAt = null; }
        } else plcWakeAt(G.lastFcRx + P.fcLossTime);
      }
      reconcile();
      if (G.st === 'run' && !G.q.length && !G.txn) {
        if (now >= G.lastStatusAt + P.suPoll) suEnq({ cmd: 'RS', kind: 'poll', periodic: true });
        else plcWakeAt(G.lastStatusAt + P.suPoll);
      }
      plcOut();
    }
    function plcPower(on) {
      if (on === G.on) return;
      if (!on) {
        G.on = false; G.gen++;
        if (G.txn && !G.txn.done && G.txn.rec.t1 > now) G.txn.rec.ok = 'lost';
        log('plc', 'err', 'l.pDown'); mark('m.plcDown', [], 'fault');
        // 断电：所有 DO 掉电。故障 DO 是 b 接点 → 接点断开 = 报警
        S('do.stb', 0); S('do.hvy', 1); S('do.lgt', 1); S('po.pon', 0); S('po.poff', 0);
        plcTrace();
        after(1, wDI);
      } else {
        const g = G.gen;
        after(P.plcRestart, () => {
          if (G.gen !== g) return;
          G = gNew(); G.on = true; G.restart = true; G.lastFcRx = now; G.st = 'init';
          G.out = { stb: false, hvy: true, lgt: true, pon: false, poff: false };
          log('plc', 'info', 'l.pUp'); mark('m.plcUp');
          suEnq({ cmd: 'RS', kind: 'init' });
          plcOut(); plcWake();
        });
      }
    }

    // ================================================================ 跑
    // 初始状态
    ROWS.forEach(r => { if (r.type === 'dig') { now = 0; S(r.id, 0); } });
    S('ln.mb', ''); S('ln.su', '');
    hTrace(); wTrace(); plcTrace();
    tr.ana.pv.push({ t: 0, v: 25 }); H.pvRec = 25;
    after(50, hTick);

    const act = {
      'fc.start': () => wStart(), 'fc.end': () => wEnd(),
      'fc.manStart': p => wManStart(+p || 50), 'fc.manStop': () => wManStop(),
      'fc.autoStart': p => wAutoStart(+p || 50), 'fc.autoStop': () => wAutoStop(),
      'fc.setTemp': p => { log('fc', 'info', 'l.wSetTemp', [(+p).toFixed(1)]); mbWrite(Math.round(+p * 10)); },
      'fc.reset': () => wReset(), 'fc.buzzer': () => wBuzzer(),
      'su.cut': () => { setLine('su', true); line.su.cutAt = now; log('inj', 'err', 'l.injSuCut'); },
      'su.fix': () => { setLine('su', false); log('inj', 'info', 'l.injSuFix'); },
      'mb.cut': () => { setLine('mb', true); line.mb.cutAt = now; log('inj', 'err', 'l.injMbCut'); },
      'mb.fix': () => { setLine('mb', false); log('inj', 'info', 'l.injMbFix'); },
      'plc.off': () => plcPower(false), 'plc.on': () => plcPower(true),
      'ht.alarm': p => hAlarm(p || 'stop'), 'ht.clear': () => hClear(),
      'ht.local': () => { H.mode = 'local'; log('inj', 'warn', 'l.injLocal'); hTrace(); },
      'ht.serial': () => { H.mode = 'serial'; log('inj', 'info', 'l.injSerial'); hTrace(); },
      'su.drop': p => { H.drop += Math.max(1, +p || 1); },
      'su.nak': p => { H.nak += Math.max(1, +p || 1); },
    };
    (script || []).forEach(ev => {
      const t = ev[0] * 1000;
      if (!act[ev[1]] || !(t >= 0)) return;
      at(t, () => { mark('a.' + ev[1], ev[2] === undefined || ev[2] === null ? [] : [ev[1] === 'ht.alarm' ? 'al.' + ev[2] : ev[2]], 'script'); act[ev[1]](ev[2]); });
    });

    let guard = 0;
    while (heap.length) {
      const e = pop();
      if (e.t > END) break;
      now = e.t; e.fn();
      if (++guard > 3e6) { log('inj', 'err', 'l.guard'); break; }
    }
    now = END;
    // 收尾：还没发完的帧截到结束时刻
    tr.frames.forEach(f => { if (f.t1 > END) f.t1 = END; });
    tr.frames.sort((a, b) => a.t0 - b.t0 || a.id - b.id);
    meas.suBusyPct = meas.suBusy / END * 100;
    return { P, end: END, tr, meas };
  }

  const api = { PARAM_DEFS, BAUDS, ZONES, ROWS, SU_SUBS, VIEWS, ACTIONS, SCENARIOS, ST, ST_NAMES, ALM, defaults, simulate };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SimCore = api;
})(typeof window !== 'undefined' ? window : globalThis);
