/* 内核自检：node test_core.js
 * 查的是 ../时序图/README.md 里定下来的做法有没有被改坏（顺序、等 30 s、3 次判异常、复位才解除…），
 * 以及每个场景都满足半双工（同一条线上的帧不重叠，每个请求都有应答或「无应答」）。 */
'use strict';
const C = require('./core.js');
let fail = 0;
function ok(cond, msg) { if (!cond) { fail++; console.log('  NG  ' + msg); } }
function runScn(id, over) {
  const sc = C.SCENARIOS.find(s => s.id === id);
  return C.simulate(Object.assign(C.defaults(), sc.params || {}, over || {}), sc.script, sc.end);
}
const tx = (r, a, b) => r.tr.frames.filter(f => f.row === 'su.tx' && f.t0 >= a * 1000 && f.t0 < b * 1000).map(f => f.code + (f.code === 'WF' || f.code === 'WR' ? f.lab.k.slice(-1) : ''));
const sigAt = (r, id, t) => { const a = r.tr.sig[id]; let v = null; a.forEach(c => { if (c.t <= t * 1000) v = c.v; }); return v; };
const logAt = (r, k) => r.tr.log.filter(l => l.k === k).map(l => l.t / 1000);

// ---- 所有场景：半双工 + 一问一答
C.SCENARIOS.forEach(sc => {
  const r = runScn(sc.id);
  ['mb', 'su'].forEach(bus => {
    const fr = r.tr.frames.filter(f => f.bus === bus && f.ok !== 'none' && f.ok !== 'late').sort((a, b) => a.t0 - b.t0);
    for (let i = 1; i < fr.length; i++) ok(fr[i].t0 >= fr[i - 1].t1 - 1e-6, sc.id + ' ' + bus + ' 帧重叠 @' + (fr[i].t0 / 1000).toFixed(3));
    r.tr.frames.filter(f => f.bus === bus && (f.row === 'mb.req' || f.row === 'su.tx') && f.t1 < r.end - 1500).forEach(f => {
      const answered = r.tr.frames.some(g => g.pair === f.id);
      ok(answered, sc.id + ' ' + bus + ' 请求没有应答也没有「无应答」 @' + (f.t0 / 1000).toFixed(3));
    });
  });
  console.log(sc.id.padEnd(5), 'frames', String(r.tr.frames.length).padStart(4), ' log', String(r.tr.log.length).padStart(3));
});

// ---- 1-1：满 30 s 之前不发任何帧；先状态读出，再转发 25.0 + 读回
let r = runScn('1-1');
ok(tx(r, 0, 30).length === 0, '1-1 等 30 s 期间发了帧');
ok(tx(r, 30, 31).join(',') === 'RS,WT,RT,RS', '1-1 初始化顺序应为 状态 → 25.0 → 读回，实际 ' + tx(r, 30, 31));
ok(sigAt(r, 'do.hvy', 29) === 0, '1-1 启动等待中不应报重故障');

// ---- 2-1：开始 = 通水 → 温度 → 运转；停止 = 温度 → 运转 OFF → 通水 OFF；之后读回
r = runScn('2-1');
ok(tx(r, 34, 34.6).join(',') === 'WF1,WT,WR1,RT,RS', '2-1 启动顺序 ' + tx(r, 34, 34.6));
ok(tx(r, 52, 52.6).join(',') === 'WT,WR0,WF0,RT,RS', '2-1 停止顺序 ' + tx(r, 52, 52.6));
ok(r.meas.stbDelay.length === 1 && r.meas.stbDelay[0] <= 3000 + 100, '2-1 安定 DO 最多晚一个轮询周期');
ok(r.meas.mbMaxResp < 100, '2-1 清洗机的写应答不应被温水器拖住');

// ---- 4-1：停止类报警 → 重故障；复位 5 s 窗口内清掉；解除成功
r = runScn('4-1');
ok(sigAt(r, 'do.hvy', 48) === 1 && sigAt(r, 'do.hvy', 63) === 0, '4-1 重故障 DO');
ok(r.meas.resetClear[0] < 5000 && r.meas.resetResult[0].ok, '4-1 复位窗口内清掉并解除成功');

// ---- 4-2：超时 3 次 → 通信异常 → 切电源 → 停轮询；再启动等 30 s；复位才解除
r = runScn('4-2');
const cf = logAt(r, 'l.pCommFault')[0];
ok(logAt(r, 'l.pTimeout').length === 3 && cf > 49 && cf < 50, '4-2 3 次超时后判通信异常 @' + cf);
ok(sigAt(r, 'ht.pwr', cf + 0.1) === 0, '4-2 判异常时切远程电源');
ok(tx(r, cf + 0.01, 93).length === 0, '4-2 切电源后到再启动满 30 s 之间不应发帧');
ok(sigAt(r, 'do.hvy', 98) === 1 && sigAt(r, 'do.hvy', 100) === 0, '4-2 通信恢复后也要复位才清重故障');

// ---- 4-3：5 s 没请求 → 判断线 → PLC 自己停（运转 OFF → 通水 OFF）
r = runScn('4-3');
const fl = logAt(r, 'l.pFcLoss')[0];
ok(fl > 50 && fl < 51.5, '4-3 清洗机断线判定时刻 ' + fl);
ok(tx(r, fl, fl + 0.5).join(',') === 'WR0,WF0,RT,RS', '4-3 PLC 自己停的顺序 ' + tx(r, fl, fl + 0.5));
ok(sigAt(r, 'do.hvy', 61) === 1 && sigAt(r, 'do.hvy', 63) === 0, '4-3 线修好也要复位');

// ---- 4-4：PLC 停 = 故障接点断开；温水器停不下来；重启后补发停止；复位才解除
r = runScn('4-4');
ok(sigAt(r, 'do.hvy', 47) === 1 && sigAt(r, 'do.lgt', 47) === 1 && sigAt(r, 'do.stb', 47) === 0, '4-4 PLC 停时 DO');
ok(sigAt(r, 'ht.run', 57) === 1, '4-4 PLC 停着时温水器继续运转（没有看门狗）');
ok(sigAt(r, 'ht.run', 59) === 0 && sigAt(r, 'do.hvy', 63) === 1 && sigAt(r, 'do.hvy', 65) === 0, '4-4 重启后补发停止，故障保持到复位');

// ---- 追加
r = runScn('x-1'); ok(logAt(r, 'l.pCommFault').length === 0 && logAt(r, 'l.pRecovered').length === 1, 'x-1 丢一帧不应报异常');
r = runScn('x-2'); ok(logAt(r, 'l.pCommFault').length === 1, 'x-2 NAK 3 次应报通信异常');
r = runScn('x-3'); ok(sigAt(r, 'do.hvy', 35) === 1 && sigAt(r, 'do.hvy', 41) === 0, 'x-3 非串口模式 → 重故障 → 切回后复位');
r = runScn('x-4'); ok(r.meas.resetResult.map(x => x.ok).join() === 'false,true', 'x-4 原因没消除时复位应失败');
r = runScn('x-5'); ok(logAt(r, 'l.pCommFault')[0] < 10, 'x-5 只等 5 s 应在启动时报通信异常');
// 参数：轮询周期越短，安定 DO 越早
ok(runScn('2-1', { suPoll: 500 }).meas.stbDelay[0] <= 600, '参数 suPoll=500 时安定 DO 延迟');
// 参数：不补读时，重故障要等下一次轮询才清
ok(runScn('4-1', { optResetRead: false }).meas.resetClear[0] > runScn('4-1').meas.resetClear[0], '参数 optResetRead=false 时清除更慢');

console.log(fail ? '\n' + fail + ' 项不通过' : '\n全部通过');
process.exit(fail ? 1 : 0);
