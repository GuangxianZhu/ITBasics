/* PLC 网关模拟器 界面。计算全在 core.js，这里只管：参数 / 脚本编辑 → 重新算 → 画时序图、设备示意、日志。
 * 时序图是一整张 SVG（每次重画），导出就是把同一张图按浅色配色再画一遍。 */
(function () {
  'use strict';
  const C = window.SimCore, I = window.I18N, t = I.t;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const store = {
    get(k) { try { return localStorage.getItem('plcgw.' + k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem('plcgw.' + k, v); } catch (e) { /* 预览框里可能没有存储 */ } },
  };

  // ------------------------------------------------------------------ 配色（时序图用；导出固定用浅色）
  const PAL = {
    light: {
      bg: '#ffffff', text: '#1b2430', sub: '#5b6675', grid: '#e6e9ef', low: '#b4bcc8', rowLine: '#edf0f4', cursor: '#1f3864', curB: '#b45309', mark: '#64748b', brk: '#f1f3f7',
      fault: ['#c00000', '#f8d7d7'], green: ['#3f7a2a', '#dff0d6'], gray: ['#8a93a0', '#eceef2'], val: ['#5b6675', '#f1f3f7'],
      zone: {
        fc_int: ['#6b7280', '#ededed'], fc_in: ['#2e75b6', '#ddebf7'], fc_out: ['#7030a0', '#e9e0f2'], su_out: ['#c55a11', '#fbe4d5'],
        su_in: ['#a07800', '#fff2cc'], su_st: ['#548235', '#e2efda'], plc: ['#12707a', '#d7eef0'], inj: ['#44546a', '#d6dce4'],
      },
    },
    dark: {
      bg: '#1a202a', text: '#e6eaf0', sub: '#9aa6b6', grid: '#2a3240', low: '#4a5566', rowLine: '#232b37', cursor: '#8fb0e8', curB: '#f0a35a', mark: '#8b97a8', brk: '#222a36',
      fault: ['#ff7b72', '#4a1f1f'], green: ['#7fc66a', '#1f3a1c'], gray: ['#7b8696', '#2a313c'], val: ['#9aa6b6', '#262e3a'],
      zone: {
        fc_int: ['#9aa3af', '#2a2f37'], fc_in: ['#6aa9e0', '#1c3046'], fc_out: ['#b98ae0', '#32234a'], su_out: ['#e8915a', '#47301f'],
        su_in: ['#d6b24a', '#40381a'], su_st: ['#8fc06d', '#24381c'], plc: ['#5cc0c9', '#17383c'], inj: ['#93a3b8', '#2a323e'],
      },
    },
  };
  // 每个信号的来源（和原来的图同一套标记）
  const ROW_SRC = {
    'fc.vin': '推', 'fc.vdr': '推', 'fc.alm': '推', 'io.pon': 'IO', 'io.poff': 'IO', 'io.flow': '推', 'io.run': '推', 'io.rst': '推', 'io.bz': 'IO',
    'mb.req': '推', 'mb.rsp': 'P', 'do.stb': 'P', 'do.hvy': 'P', 'do.lgt': 'P', 'po.pon': 'IO', 'po.poff': 'P', 'su.tx': '推', 'su.rx': '推',
    'ht.pwr': '推', 'ht.rdy': '推', 'ht.flow': '推', 'ht.run': '推', 'ht.heat': '推', 'ht.stb': '推', 'ht.alm': '推',
    'plc.st': 'P', 'plc.fail': '推', 'plc.cf': 'P', 'plc.fcl': '未', 'plc.ct': 'P', 'plc.cs': 'P',
  };
  const WARP_SCN = ['1-1', '1-2', '4-2', 'x-3', 'x-5'];

  // ------------------------------------------------------------------ 状态
  const S = {
    scn: '2-1', params: C.defaults(), override: {}, script: [], end: 60, focus: [0, 60],
    view: 'supply', rows: new Set(), zoneFold: new Set(),
    hidePeriodic: false, split: false, activeOnly: false, links: true, marks: true, warp: false,
    T: 0, B: null, placeB: false, sel: null,
    u0: 0, ppu: 0.02, playing: false, speed: 1,
    logWho: { fc: true, plc: true, ht: true, inj: true }, logWarn: false,
    theme: 'light',
  };
  let R = null, IDX = null, WARP = null, L = null;

  // ------------------------------------------------------------------ 小工具
  function bs(arr, tt) { // 最后一个 t <= tt 的下标
    let lo = 0, hi = arr.length - 1, r = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m].t <= tt) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }
  function valAt(id, tt) { const a = R.tr.sig[id]; if (!a) return null; const i = bs(a, tt); return i < 0 ? null : a[i]; }
  function pvAt(tt) {
    const a = R.tr.ana.pv, i = bs(a, tt);
    if (i < 0) return a[0].v;
    if (i >= a.length - 1) return a[a.length - 1].v;
    const p = a[i], q = a[i + 1];
    return q.t - p.t > 200 ? p.v : p.v + (q.v - p.v) * (tt - p.t) / (q.t - p.t);
  }
  const fmtS = ms => (ms / 1000).toFixed(3) + ' s';
  function fmtD(ms) {
    const a = Math.abs(ms);
    if (a < 10) return ms.toFixed(1) + ' ms';
    if (a < 1000) return ms.toFixed(0) + ' ms';
    return (ms / 1000).toFixed(a < 10000 ? 2 : 1) + ' s';
  }
  function tw(s, fs) { // 估算文字宽度（中日文按全角）
    let w = 0;
    for (const ch of String(s)) {
      const c = ch.codePointAt(0);
      w += c > 0x2e7f ? fs : c < 0x80 ? (ch === ' ' ? fs * 0.3 : /[A-Z#%@MW→]/.test(ch) ? fs * 0.68 : /[il.,:;'|!]/.test(ch) ? fs * 0.3 : fs * 0.56) : fs * 0.62;
    }
    return w;
  }
  function fit(s, maxW, fs) {
    s = String(s);
    if (tw(s, fs) <= maxW) return s;
    let out = '';
    for (const ch of s) { if (tw(out + ch + '…', fs) > maxW) break; out += ch; }
    return out ? out + '…' : '';
  }
  function statusText(s) {
    const n = [];
    C.ST_NAMES.forEach((k, i) => { if (k !== 'SER' && (s >> i) & 1) n.push(t('sb.' + k)); });
    if (!(s & C.ST.SER)) n.push(t('sb.noSER'));
    return n.length ? n.join('·') : t('sb.idle');
  }
  function stText(c) {
    if (!c || c.v === '' || c.v === null || c.v === undefined) return '';
    switch (c.v) {
      case 'x.list': return c.a.map(x => t(x)).join(' / ');
      case 'x.temp': return c.a[0] + ' ℃';
      case 'x.num': return String(c.a[0]);
      case 'x.status': return statusText(c.a[0]);
      default: return t(c.v, c.a);
    }
  }
  function fLabel(f) {
    let k = f.lab.k;
    const a = f.lab.a || [];
    if (f.code === 'RS' && f.why && I.has('f.RS.' + f.why)) k = 'f.RS.' + f.why;
    if (k === 'f.rRS') return statusText(a[0]);
    return t(k, a);
  }
  const rowName = id => t('r.' + id);
  function logText(l) { return t(l.k, l.a); }
  function markText(m) { return t(m.k, m.a); }
  function toast(msg) { const e = $('#toast'); e.textContent = msg; e.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => { e.hidden = true; }, 1500); }

  // ------------------------------------------------------------------ 跑模拟
  function run() {
    R = C.simulate(S.params, S.script, S.end);
    IDX = { rowFrames: {}, byId: {}, marks: R.tr.marks.slice().sort((a, b) => a.t - b.t) };
    IDX.marks.forEach((m, i) => { m.n = i + 1; });
    R.tr.frames.forEach(f => {
      IDX.byId[f.id] = f;
      (IDX.rowFrames[f.row] || (IDX.rowFrames[f.row] = [])).push(f);
      if (f.row === 'su.tx') { const k = 'su.tx:' + f.sub; (IDX.rowFrames[k] || (IDX.rowFrames[k] = [])).push(f); }
    });
    if (S.sel && !IDX.byId[S.sel]) S.sel = null;
    S.T = clamp(S.T, 0, R.end);
    if (S.B !== null) S.B = clamp(S.B, 0, R.end);
    buildWarp();
  }
  const isRoutine = f => f.periodic && !f.changed && f.ok === 'ok' && !f.noresp;
  const frameShown = f => !(S.hidePeriodic && isRoutine(f));

  // ------------------------------------------------------------------ 时间轴：真实时间 ↔ 压缩空闲后的虚拟时间
  function buildWarp() {
    const segs = [];
    if (!S.warp) { WARP = { segs: [{ t0: 0, t1: R.end, u0: 0, u1: R.end, comp: false }], uEnd: R.end }; return; }
    const ev = [0];
    Object.keys(R.tr.sig).forEach(id => { R.tr.sig[id].forEach((c, i) => { if (i > 0) ev.push(c.t); }); });
    R.tr.frames.forEach(f => { if (!isRoutine(f)) ev.push(f.t0, f.t1); });
    R.tr.marks.forEach(m => ev.push(m.t));
    ev.sort((a, b) => a - b);
    const PAD = 800, MIN = 3000, KEEP = 600;
    const act = [];
    ev.forEach(e => {
      const a = Math.max(0, e - PAD), b = Math.min(R.end, e + PAD), last = act[act.length - 1];
      if (last && a <= last[1]) last[1] = Math.max(last[1], b); else act.push([a, b]);
    });
    let tPrev = 0, u = 0;
    const push = (t0, t1, comp) => { if (t1 <= t0) return; const len = comp ? KEEP : t1 - t0; segs.push({ t0, t1, u0: u, u1: u + len, comp }); u += len; };
    act.forEach(([a, b]) => {
      if (a - tPrev > MIN) push(tPrev, a, true); else a = tPrev;
      push(a, b, false); tPrev = b;
    });
    if (R.end - tPrev > MIN) push(tPrev, R.end, true); else push(tPrev, R.end, false);
    // 合并相邻的不压缩段
    const m = [];
    segs.forEach(s => { const l = m[m.length - 1]; if (l && !l.comp && !s.comp) { l.t1 = s.t1; l.u1 = s.u1; } else m.push(s); });
    WARP = { segs: m, uEnd: u };
  }
  function segOfT(tt) { const a = WARP.segs; let lo = 0, hi = a.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (a[m].t0 <= tt) lo = m; else hi = m - 1; } return a[lo]; }
  function t2u(tt) { const s = segOfT(tt); return s.u0 + (tt - s.t0) * (s.u1 - s.u0) / (s.t1 - s.t0); }
  function u2t(u) {
    const a = WARP.segs; let lo = 0, hi = a.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (a[m].u0 <= u) lo = m; else hi = m - 1; }
    const s = a[lo];
    return s.t0 + (u - s.u0) * (s.t1 - s.t0) / (s.u1 - s.u0);
  }

  // ------------------------------------------------------------------ 行布局
  function rowActive(r) {
    if (r.type === 'ana') return true;
    if (r.type === 'bus') return !!(IDX.rowFrames[r.id] && IDX.rowFrames[r.id].some(frameShown));
    const a = R.tr.sig[r.id] || [];
    return a.length > 1 || (a.length === 1 && a[0].v !== 0 && a[0].v !== '');
  }
  function layoutRows() {
    const out = [];
    C.ZONES.forEach(zone => {
      const rows = C.ROWS.filter(r => r.zone === zone && S.rows.has(r.id) && (!S.activeOnly || rowActive(r)));
      if (!rows.length) return;
      const fold = S.zoneFold.has(zone);
      out.push({ kind: 'zone', zone, h: 21, n: rows.length, fold });
      if (fold) return;
      rows.forEach(r => {
        if (r.id === 'su.tx' && S.split) {
          C.SU_SUBS.forEach(sub => {
            const fr = IDX.rowFrames['su.tx:' + sub];
            if (fr && fr.some(frameShown)) out.push({ kind: 'row', id: 'su.tx:' + sub, base: r, zone, type: 'bus', h: 24 });
          });
        } else out.push({ kind: 'row', id: r.id, base: r, zone, type: r.type, h: r.type === 'ana' ? 66 : 24 });
      });
    });
    return out;
  }

  // ------------------------------------------------------------------ 画时序图
  const chart = $('#chart');
  let drawQueued = false;
  function requestDraw() { if (drawQueued) return; drawQueued = true; requestAnimationFrame(() => { drawQueued = false; chart.innerHTML = draw(); }); }

  function draw(opt) {
    opt = opt || {};
    const exp = !!opt.exp;
    const pal = PAL[exp ? 'light' : S.theme];
    const W = opt.W || chart.clientWidth || 900;
    const narrow = W < 720;
    const LBL = narrow ? 116 : 200, VAL = narrow || exp ? 0 : 96;
    const px0 = LBL + VAL, plotW = Math.max(120, W - px0 - 10);
    const rows = layoutRows();
    const AX = 22, MK = S.marks && IDX.marks.length ? 52 : 0, HEAD = exp ? 46 : 0, top = HEAD + AX + MK;
    let y = top;
    rows.forEach(r => { r.y = y; y += r.h; });
    const bot = y;
    // 导出：标题 + 改过的参数写在图下面
    const foot = [];
    if (exp) {
      const ch = changedParams();
      foot.push(ch.length ? t('ui.exParams') + ch.map(d => t('p.' + d[0]) + ' = ' + S.params[d[0]] + (d[6] === 'bool' ? '' : ' ' + t('u.' + d[6]))).join('； ') : t('ui.exNone'));
      foot.push(t('ui.fake'));
    }
    const H = bot + AX + (exp ? 16 + foot.length * 15 : 0);
    // 视野
    let u0 = S.u0, ppu = S.ppu;
    if (exp && L) { const uA = S.u0, uB = S.u0 + L.plotW / S.ppu; u0 = uA; ppu = plotW / (uB - uA); }
    const X = tt => px0 + (t2u(tt) - u0) * ppu;
    const tA = u2t(Math.max(0, u0)), tB = u2t(Math.min(WARP.uEnd, u0 + plotW / ppu));
    const xEnd = Math.min(px0 + plotW, X(R.end));
    if (!exp) L = { W, H, px0, plotW, top, bot, rows, LBL, VAL };

    const o = [];
    const fam = getComputedStyle(document.documentElement).getPropertyValue('--font').trim() || 'sans-serif';
    o.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="' + esc(fam) + '" font-size="11">');
    o.push('<defs>'
      + '<pattern id="hat" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="' + pal.fault[1] + '"/><line x1="0" y1="0" x2="0" y2="6" stroke="' + pal.fault[0] + '" stroke-width="1.6"/></pattern>'
      + '<pattern id="brk" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="8" height="8" fill="' + pal.brk + '"/><line x1="0" y1="0" x2="0" y2="8" stroke="' + pal.low + '" stroke-width="1"/></pattern>'
      + '<marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="' + pal.cursor + '"/></marker>'
      + '<clipPath id="cp"><rect x="' + px0 + '" y="' + (HEAD) + '" width="' + plotW + '" height="' + (H - HEAD) + '"/></clipPath>'
      + '<clipPath id="cl"><rect x="0" y="0" width="' + (LBL - 4) + '" height="' + H + '"/></clipPath>'
      + '</defs>');
    o.push('<rect width="' + W + '" height="' + H + '" fill="' + pal.bg + '"/>');
    if (exp) {
      const sc = C.SCENARIOS.find(s => s.id === S.scn);
      o.push('<text x="10" y="20" font-size="15" font-weight="700" fill="' + pal.text + '">' + esc((sc ? sc.id + '　' + t('sc.' + sc.id) : t('ui.title'))) + '</text>');
      o.push('<text x="10" y="38" fill="' + pal.sub + '">' + esc(t('ui.sub') + '　·　' + fmtS(tA) + ' – ' + fmtS(tB)) + '</text>');
    }

    // ---- 刻度
    const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 30000, 60000, 120000];
    const step = steps.find(s => s * ppu >= 74) || 120000;
    const dec = step >= 1000 ? 0 : step >= 100 ? 1 : step >= 10 ? 2 : 3;
    const ticks = [];
    WARP.segs.forEach(sg => {
      if (sg.comp || sg.t1 < tA || sg.t0 > tB) return;
      for (let k = Math.ceil(Math.max(sg.t0, tA) / step) * step; k <= Math.min(sg.t1, tB) + 1e-6; k += step) ticks.push(k);
    });
    const axis = (yy, up) => {
      let lastX = -1e9;
      const a = ['<line x1="' + px0 + '" y1="' + yy + '" x2="' + (px0 + plotW) + '" y2="' + yy + '" stroke="' + pal.low + '"/>'];
      ticks.forEach(k => {
        const x = X(k);
        a.push('<line x1="' + x.toFixed(1) + '" y1="' + yy + '" x2="' + x.toFixed(1) + '" y2="' + (yy + (up ? -4 : 4)) + '" stroke="' + pal.low + '"/>');
        if (x - lastX > 44 && x >= px0 + 12 && x <= px0 + plotW - 4) { a.push('<text x="' + x.toFixed(1) + '" y="' + (up ? yy - 7 : yy + 14) + '" text-anchor="middle" fill="' + pal.sub + '">' + (k / 1000).toFixed(dec) + '</text>'); lastX = x; }
      });
      return a.join('');
    };
    o.push('<g clip-path="url(#cp)">');
    ticks.forEach(k => { const x = X(k).toFixed(1); o.push('<line x1="' + x + '" y1="' + top + '" x2="' + x + '" y2="' + bot + '" stroke="' + pal.grid + '"/>'); });
    o.push('</g>');
    o.push(axis(HEAD + AX, true), axis(bot, false));
    o.push('<text x="' + (px0 - 6) + '" y="' + (HEAD + AX - 7) + '" text-anchor="end" fill="' + pal.sub + '">' + esc(t('ui.time')) + '</text>');
    o.push('<text x="8" y="' + (HEAD + AX - 7) + '" fill="' + pal.sub + '">' + esc(t('ui.signal')) + '</text>');
    if (VAL) o.push('<text x="' + (LBL + 4) + '" y="' + (top - 6) + '" fill="' + pal.cursor + '" font-weight="600">' + esc(t('ui.at') + ' ' + fmtS(S.T)) + '</text>');

    // ---- 每一行
    const inComp = tt => S.warp && segOfT(tt).comp;
    const rowY = {};
    rows.forEach(r => {
      const zc = pal.zone[r.zone];
      if (r.kind === 'zone') {
        o.push('<rect x="0" y="' + r.y + '" width="' + W + '" height="' + r.h + '" fill="' + zc[1] + '"/>');
        o.push('<rect x="0" y="' + r.y + '" width="4" height="' + r.h + '" fill="' + zc[0] + '"/>');
        o.push('<text x="10" y="' + (r.y + 15) + '" font-weight="700" fill="' + pal.text + '">' + (r.fold ? '▸ ' : '▾ ') + esc(t('z.' + r.zone)) + (r.fold ? '  ' + esc(t('ui.hiddenRows', [r.n])) : '') + '</text>');
        return;
      }
      const yc = r.y + r.h / 2;
      rowY[r.id] = yc;
      o.push('<line x1="0" y1="' + (r.y + r.h) + '" x2="' + W + '" y2="' + (r.y + r.h) + '" stroke="' + pal.rowLine + '"/>');
      o.push('<rect x="0" y="' + r.y + '" width="4" height="' + r.h + '" fill="' + zc[0] + '" opacity=".45"/>');
      // 名字 + 来源标记
      const src = ROW_SRC[r.base.id], srcTxt = src ? t('src.' + src) : '';
      const srcW = srcTxt && !narrow ? tw(srcTxt, 9.5) + 10 : 0;
      o.push('<text x="10" y="' + (yc + 4) + '" fill="' + pal.text + '" clip-path="url(#cl)">' + esc(fit(rowName(r.id), LBL - 16 - srcW, 11)) + '</text>');
      if (srcW) o.push('<text x="' + (LBL - 6) + '" y="' + (yc + 3.5) + '" text-anchor="end" font-size="9.5" fill="' + (src === '未' || src === '假' ? pal.fault[0] : pal.sub) + '">' + esc(srcTxt) + '</text>');
      // 光标处的值
      if (VAL) {
        let vt = '', vc = pal.sub;
        if (r.type === 'dig') { const c = valAt(r.id, S.T); const on = c && c.v; vt = on ? 'ON' : 'OFF'; if (on) vc = r.base.kind === 'fault' ? pal.fault[0] : r.base.kind === 'green' ? pal.green[0] : zc[0]; }
        else if (r.type === 'st') { const c = valAt(r.id, S.T); vt = stText(c) || '—'; if (c && c.v && c.k === 'fault') vc = pal.fault[0]; }
        else if (r.type === 'ana') vt = pvAt(S.T).toFixed(1) + ' ℃';
        else { const f = frameAt(r.id, S.T); vt = f ? fLabel(f) : '—'; if (f) vc = pal.text; }
        o.push('<text x="' + (LBL + 4) + '" y="' + (yc + 4) + '" fill="' + vc + '" font-weight="' + (vc === pal.sub ? 400 : 600) + '">' + esc(fit(vt, VAL - 8, 11)) + '</text>');
      }
    });
    o.push('<line x1="' + px0 + '" y1="' + top + '" x2="' + px0 + '" y2="' + bot + '" stroke="' + pal.low + '"/>');
    if (VAL) o.push('<line x1="' + LBL + '" y1="' + top + '" x2="' + LBL + '" y2="' + bot + '" stroke="' + pal.rowLine + '"/>');

    // ---- 波形
    o.push('<g clip-path="url(#cp)">');
    const kindCol = (k, zc) => k === 'fault' ? pal.fault : k === 'green' ? pal.green : k === 'gray' ? pal.gray : k === 'val' ? pal.val : zc;
    rows.forEach(r => {
      if (r.kind !== 'row') return;
      const zc = pal.zone[r.zone], y0 = r.y, h = r.h;
      if (r.type === 'dig') {
        const col = kindCol(r.base.kind, zc), lo = y0 + h - 5, hi = y0 + 5;
        const a = R.tr.sig[r.id] || [];
        let d = '', i = Math.max(0, bs(a, tA));
        const xs = Math.max(px0, X(Math.max(tA, 0)));
        d += 'M' + xs.toFixed(1) + ',' + (a[i] && a[i].v ? hi : lo);
        for (; i < a.length; i++) {
          const c = a[i], t1 = i + 1 < a.length ? a[i + 1].t : R.end;
          if (c.t > tB) break;
          const xa = Math.max(px0 - 2, X(c.t)), xb = Math.min(px0 + plotW + 2, X(t1));
          const yv = c.v ? hi : lo;
          if (c.v && xb - xa > 0.3) {
            o.push('<rect x="' + xa.toFixed(1) + '" y="' + hi + '" width="' + Math.max(1, xb - xa).toFixed(1) + '" height="' + (lo - hi) + '" fill="' + col[1] + '"/>');
            if (xb - Math.max(xa, px0) > 34) o.push('<text x="' + (Math.max(xa, px0) + 5).toFixed(1) + '" y="' + (y0 + h / 2 + 4) + '" fill="' + col[0] + '" font-weight="600">ON</text>');
          }
          d += ' L' + xa.toFixed(1) + ',' + yv + ' L' + xb.toFixed(1) + ',' + yv;
        }
        o.push('<path d="' + d + '" fill="none" stroke="' + col[0] + '" stroke-width="1.4" stroke-linejoin="round"/>');
      } else if (r.type === 'st') {
        const a = R.tr.sig[r.id] || [];
        for (let i = Math.max(0, bs(a, tA)); i < a.length; i++) {
          const c = a[i], t1 = i + 1 < a.length ? a[i + 1].t : R.end;
          if (c.t > tB) break;
          const txt = stText(c);
          if (!txt) continue;
          const xa = Math.max(px0 - 4, X(c.t)), xb = Math.min(px0 + plotW + 4, X(t1)), w = Math.max(1.5, xb - xa);
          const col = c.k === 'tbd' ? pal.gray : kindCol(c.k || 'val', zc);
          o.push('<rect x="' + xa.toFixed(1) + '" y="' + (y0 + 4) + '" width="' + w.toFixed(1) + '" height="' + (h - 8) + '" rx="3" fill="' + col[1] + '" stroke="' + col[0] + '" stroke-width="' + (c.k === 'val' ? 0.6 : 1) + '"' + (c.k === 'tbd' ? ' stroke-dasharray="3 2"' : '') + '/>');
          const xa2 = Math.max(xa, px0), s = fit(txt, xb - xa2 - 8, 11);
          if (s) o.push('<text x="' + (xa2 + 5).toFixed(1) + '" y="' + (y0 + h / 2 + 4) + '" fill="' + (c.k === 'val' || !c.k ? pal.text : col[0]) + '"' + (c.k === 'fault' ? ' font-weight="600"' : '') + '>' + esc(s) + '</text>');
        }
      } else if (r.type === 'bus') {
        const fr = (IDX.rowFrames[r.id] || []).filter(f => frameShown(f) && f.t1 >= tA && f.t0 <= tB && !inComp(f.t0));
        fr.forEach((f, i) => {
          const xa = X(f.t0), xb = X(f.t1), w = Math.max(1.6, xb - xa);
          const sel = S.sel === f.id;
          let fill, stroke, dash = '', txc;
          if (f.ok === 'none') { fill = 'url(#hat)'; stroke = pal.fault[0]; dash = ' stroke-dasharray="3 2"'; txc = pal.fault[0]; }
          else if (f.ok === 'lost' || f.ok === 'late') { fill = pal.bg; stroke = pal.fault[0]; dash = ' stroke-dasharray="3 2"'; txc = pal.fault[0]; }
          else { const col = kindCol(f.kind === 'on' ? null : f.kind, zc); fill = col[1]; stroke = col[0]; txc = f.kind === 'fault' ? col[0] : pal.text; }
          o.push('<rect x="' + xa.toFixed(1) + '" y="' + (y0 + 3) + '" width="' + w.toFixed(1) + '" height="' + (h - 6) + '" rx="2" fill="' + fill + '" stroke="' + (sel ? pal.cursor : stroke) + '" stroke-width="' + (sel ? 2.2 : 1) + '"' + (sel ? '' : dash) + (isRoutine(f) ? ' opacity=".6"' : '') + '/>');
          const lab = fLabel(f) + (f.attempt > 1 ? ' ×' + f.attempt : ''), lw = tw(lab, 10.5);
          const nx = i + 1 < fr.length ? X(fr[i + 1].t0) : px0 + plotW + 200;
          if (lw + 8 <= w) o.push('<text x="' + (Math.max(xa, px0) + 4).toFixed(1) + '" y="' + (y0 + h / 2 + 3.6) + '" font-size="10.5" fill="' + txc + '">' + esc(lab) + '</text>');
          else if (w > 60) { const s = fit(lab, w - 8, 10.5); if (s) o.push('<text x="' + (Math.max(xa, px0) + 4).toFixed(1) + '" y="' + (y0 + h / 2 + 3.6) + '" font-size="10.5" fill="' + txc + '">' + esc(s) + '</text>'); }
          else if (nx - xb >= lw + 9) o.push('<text x="' + (xb + 4).toFixed(1) + '" y="' + (y0 + h / 2 + 3.6) + '" font-size="10.5" fill="' + (f.ok === 'ok' && f.kind !== 'fault' ? pal.sub : pal.fault[0]) + '">' + esc(lab) + '</text>');
        });
      } else if (r.type === 'ana') {
        const pv = R.tr.ana.pv, sv = R.tr.sig['ht.sv'] || [];
        let mx = 55;
        pv.forEach(p => { if (p.v > mx) mx = p.v; });
        sv.forEach(c => { if (c.v && +c.a[0] > mx) mx = +c.a[0]; });
        mx = Math.ceil((mx + 4) / 10) * 10;
        const mn = 20, Y = v => y0 + h - 6 - (v - mn) / (mx - mn) * (h - 12);
        [mn + 5, (mn + 5 + mx) / 2, mx].forEach(v => {
          o.push('<line x1="' + px0 + '" y1="' + Y(v).toFixed(1) + '" x2="' + (px0 + plotW) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + pal.grid + '" stroke-dasharray="2 3"/>');
          o.push('<text x="' + (px0 + 3) + '" y="' + (Y(v) - 2).toFixed(1) + '" font-size="9.5" fill="' + pal.sub + '">' + v.toFixed(0) + '</text>');
        });
        // 设定温度（虚线阶梯）
        let d = '';
        for (let i = Math.max(0, bs(sv, tA)); i < sv.length; i++) {
          const c = sv[i], t1 = i + 1 < sv.length ? sv[i + 1].t : R.end;
          if (c.t > tB) break;
          if (!c.v) continue;
          const yy = Y(+c.a[0]).toFixed(1);
          d += (d ? ' L' : 'M') + Math.max(px0, X(c.t)).toFixed(1) + ',' + yy + ' L' + Math.min(px0 + plotW, X(t1)).toFixed(1) + ',' + yy;
        }
        if (d) o.push('<path d="' + d + '" fill="none" stroke="' + pal.sub + '" stroke-width="1" stroke-dasharray="4 3"/>');
        // 出口温度
        let p = '', lastX = -1e9, i0 = Math.max(0, bs(pv, tA));
        for (let i = i0; i < pv.length; i++) {
          const q = pv[i];
          const x = X(q.t);
          if (x - lastX < 0.7 && i !== i0) continue;
          p += (p ? ' L' : 'M') + x.toFixed(1) + ',' + Y(q.v).toFixed(1); lastX = x;
          if (q.t > tB) break;
        }
        if (p) { const xl = Math.min(px0 + plotW, X(Math.min(tB, R.end))); p += ' L' + xl.toFixed(1) + ',' + Y(pvAt(Math.min(tB, R.end))).toFixed(1); o.push('<path d="' + p + '" fill="none" stroke="' + pal.zone.su_out[0] + '" stroke-width="1.6"/>'); }
      }
    });

    // ---- 省略段
    if (S.warp) WARP.segs.forEach(sg => {
      if (!sg.comp || sg.t1 < tA || sg.t0 > tB) return;
      const xa = X(sg.t0), xb = X(sg.t1);
      o.push('<rect x="' + xa.toFixed(1) + '" y="' + top + '" width="' + (xb - xa).toFixed(1) + '" height="' + (bot - top) + '" fill="url(#brk)" opacity=".8"/>');
      const lab = t('ui.break', [fmtD(sg.t1 - sg.t0)]);
      if (xb - xa > tw(lab, 10.5) + 6) o.push('<text x="' + ((xa + xb) / 2).toFixed(1) + '" y="' + (top + 13) + '" text-anchor="middle" font-size="10.5" fill="' + pal.sub + '">' + esc(lab) + '</text>');
      else o.push('<text transform="translate(' + ((xa + xb) / 2 + 3.5).toFixed(1) + ',' + (top + 8) + ') rotate(90)" font-size="10.5" fill="' + pal.sub + '">' + esc(lab) + '</text>');
    });

    // ---- 因果箭头
    if (S.links) R.tr.links.forEach(lk => {
      if (lk.t1 < tA || lk.t0 > tB || inComp(lk.t1)) return;
      let r1 = lk.r1;
      if (r1 === 'su.tx' && S.split) { const f = (IDX.rowFrames['su.tx'] || []).find(f => Math.abs(f.t0 - lk.t1) < 0.01); if (f) r1 = 'su.tx:' + f.sub; }
      const ya = rowY[lk.r0], yb = rowY[r1];
      if (ya === undefined || yb === undefined) return;
      const xa = X(lk.t0), xb = X(lk.t1), dy = yb > ya ? 9 : -9;
      const mx = xb - xa < 14 ? xa - 12 : (xa + xb) / 2;
      o.push('<path d="M' + xa.toFixed(1) + ',' + (ya + dy) + ' C' + mx.toFixed(1) + ',' + (ya + dy * 3) + ' ' + mx.toFixed(1) + ',' + (yb - dy * 3) + ' ' + xb.toFixed(1) + ',' + (yb - dy) + '" fill="none" stroke="' + pal.cursor + '" stroke-width="1" stroke-dasharray="3 2" opacity=".75" marker-end="url(#arr)"/>');
    });

    // ---- 阶段线
    if (MK) {
      const lane = [-1e9, -1e9, -1e9];
      IDX.marks.forEach(m => {
        if (m.t < tA || m.t > tB || inComp(m.t)) return;
        const x = X(m.t), col = m.kind === 'fault' ? pal.fault[0] : m.kind === 'green' ? pal.green[0] : m.kind === 'script' ? pal.cursor : pal.mark;
        o.push('<line x1="' + x.toFixed(1) + '" y1="' + (HEAD + AX + 6) + '" x2="' + x.toFixed(1) + '" y2="' + bot + '" stroke="' + col + '" stroke-width="' + (m.kind === 'script' ? 1 : 0.8) + '" stroke-dasharray="' + (m.kind === 'script' ? '5 3' : '2 3') + '" opacity=".8"/>');
        const lab = markText(m), lw = tw(lab, 10.5) + 22;
        let ln = lane.findIndex(v => v <= x - 9), text = true;
        if (ln < 0) { ln = lane.indexOf(Math.min.apply(null, lane)); text = false; } // 三行都占了：只画编号
        const by = HEAD + AX + 3 + ln * 16;
        const filled = m.kind === 'script';
        o.push('<rect x="' + (x - 7.5).toFixed(1) + '" y="' + by + '" width="15" height="14" rx="7" fill="' + (filled ? col : pal.bg) + '" stroke="' + col + '"/>');
        o.push('<text x="' + x.toFixed(1) + '" y="' + (by + 10.5) + '" text-anchor="middle" font-size="9.5" font-weight="700" fill="' + (filled ? pal.bg : col) + '">' + m.n + '</text>');
        if (text) { o.push('<text x="' + (x + 11).toFixed(1) + '" y="' + (by + 11) + '" font-size="10.5" fill="' + col + '">' + esc(lab) + '</text>'); lane[ln] = x + lw; }
        else lane[ln] = Math.max(lane[ln], x + 9);
      });
    }

    // ---- 光标
    const cur = (tt, col, dash, name) => {
      if (tt === null || tt < tA || tt > tB) return;
      const x = X(tt).toFixed(1);
      o.push('<line x1="' + x + '" y1="' + (HEAD + 2) + '" x2="' + x + '" y2="' + (bot + 4) + '" stroke="' + col + '" stroke-width="1.3"' + (dash ? ' stroke-dasharray="6 3"' : '') + '/>');
      o.push('<rect x="' + (x - 7) + '" y="' + (bot + 5) + '" width="14" height="13" rx="2" fill="' + col + '"/><text x="' + x + '" y="' + (bot + 15) + '" text-anchor="middle" font-size="9.5" font-weight="700" fill="' + pal.bg + '">' + name + '</text>');
    };
    if (!exp || S.B !== null) { cur(S.T, pal.cursor, false, 'A'); cur(S.B, pal.curB, true, 'B'); }
    if (S.B !== null) {
      const xa = clamp(X(Math.min(S.T, S.B)), px0, px0 + plotW), xb = clamp(X(Math.max(S.T, S.B)), px0, px0 + plotW);
      if (xb - xa > 4) {
        const lab = 'Δ ' + fmtD(Math.abs(S.B - S.T)), lw = tw(lab, 11) + 10, cx = clamp((xa + xb) / 2, px0 + lw / 2, px0 + plotW - lw / 2);
        o.push('<line x1="' + xa.toFixed(1) + '" y1="' + (bot - 8) + '" x2="' + xb.toFixed(1) + '" y2="' + (bot - 8) + '" stroke="' + pal.curB + '" stroke-width="1.2"/>');
        o.push('<rect x="' + (cx - lw / 2).toFixed(1) + '" y="' + (bot - 17) + '" width="' + lw.toFixed(1) + '" height="16" rx="3" fill="' + pal.curB + '"/><text x="' + cx.toFixed(1) + '" y="' + (bot - 5.5) + '" text-anchor="middle" font-weight="700" fill="' + pal.bg + '">' + esc(lab) + '</text>');
      }
    }
    o.push('</g>');
    if (xEnd < px0 + plotW) o.push('<rect x="' + xEnd.toFixed(1) + '" y="' + top + '" width="' + (px0 + plotW - xEnd).toFixed(1) + '" height="' + (bot - top) + '" fill="' + pal.brk + '" opacity=".6"/>');
    if (exp) foot.forEach((s, i) => o.push('<text x="10" y="' + (bot + AX + 18 + i * 15) + '" fill="' + pal.sub + '">' + esc(fit(s, W - 20, 11)) + '</text>'));
    o.push('</svg>');
    return o.join('');
  }
  // 某一行在 tt 时刻（或之前最近）的帧
  function frameAt(rowId, tt) {
    const a = IDX.rowFrames[rowId];
    if (!a) return null;
    let lo = 0, hi = a.length - 1, r = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m].t0 <= tt) { r = m; lo = m + 1; } else hi = m - 1; }
    for (; r >= 0; r--) if (frameShown(a[r])) return a[r];
    return null;
  }

  // ------------------------------------------------------------------ 小地图
  const mini = $('#mini');
  function drawMini() {
    if (!L) return;
    const pal = PAL[S.theme], W = L.W, h = 26, x0 = L.px0, w = L.plotW;
    const X = tt => x0 + t2u(tt) / WARP.uEnd * w;
    const o = ['<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + h + '" viewBox="0 0 ' + W + ' ' + h + '" font-size="10">'];
    o.push('<rect x="' + x0 + '" y="3" width="' + w + '" height="' + (h - 6) + '" fill="' + pal.brk + '" rx="3"/>');
    const band = (id, col, yy, hh) => {
      const a = R.tr.sig[id] || [];
      a.forEach((c, i) => { if (!c.v) return; const t1 = i + 1 < a.length ? a[i + 1].t : R.end; o.push('<rect x="' + X(c.t).toFixed(1) + '" y="' + yy + '" width="' + Math.max(1, X(t1) - X(c.t)).toFixed(1) + '" height="' + hh + '" fill="' + col + '"/>'); });
    };
    band('ht.pwr', pal.zone.su_st[1], 5, 16); band('ht.run', pal.zone.su_out[0], 13, 4); band('do.stb', pal.green[0], 8, 4); band('do.hvy', pal.fault[0], 18, 3);
    IDX.marks.forEach(m => { if (m.kind !== 'script') return; const x = X(m.t).toFixed(1); o.push('<line x1="' + x + '" y1="3" x2="' + x + '" y2="' + (h - 3) + '" stroke="' + pal.cursor + '" stroke-width="1"/>'); });
    const va = x0 + clamp(S.u0, 0, WARP.uEnd) / WARP.uEnd * w, vb = x0 + clamp(S.u0 + L.plotW / S.ppu, 0, WARP.uEnd) / WARP.uEnd * w;
    o.push('<rect x="' + va.toFixed(1) + '" y="1.5" width="' + Math.max(3, vb - va).toFixed(1) + '" height="' + (h - 3) + '" fill="' + pal.cursor + '" fill-opacity=".12" stroke="' + pal.cursor + '" stroke-width="1.4" rx="3"/>');
    const xc = X(S.T).toFixed(1);
    o.push('<line x1="' + xc + '" y1="0" x2="' + xc + '" y2="' + h + '" stroke="' + pal.cursor + '" stroke-width="1.6"/>');
    o.push('<text x="' + (x0 - 6) + '" y="17" text-anchor="end" fill="' + pal.sub + '">0 – ' + (R.end / 1000).toFixed(0) + ' s</text>');
    o.push('</svg>');
    mini.innerHTML = o.join('');
  }
  let miniDrag = false;
  function miniGo(e) {
    if (!L) return;
    const r = mini.getBoundingClientRect(), x = e.clientX - r.left;
    const u = clamp((x - L.px0) / L.plotW, 0, 1) * WARP.uEnd;
    S.u0 = u - L.plotW / S.ppu / 2; clampView(); refreshChart();
  }
  mini.addEventListener('pointerdown', e => { miniDrag = true; mini.setPointerCapture(e.pointerId); miniGo(e); });
  mini.addEventListener('pointermove', e => { if (miniDrag) miniGo(e); });
  mini.addEventListener('pointerup', () => { miniDrag = false; });
  mini.addEventListener('pointercancel', () => { miniDrag = false; });

  // ------------------------------------------------------------------ 视野
  function plotW() { const W = chart.clientWidth || 900; return Math.max(120, W - (W < 720 ? 116 : 296) - 10); }
  function clampView() {
    const pw = plotW(), minP = pw / (WARP.uEnd * 1.04);
    S.ppu = clamp(S.ppu, minP, 60);
    const span = pw / S.ppu, m = span * 0.02;
    S.u0 = clamp(S.u0, -m, Math.max(-m, WARP.uEnd - span + m));
  }
  function fitRange(ta, tb) {
    const ua = t2u(clamp(ta, 0, R.end)), ub = t2u(clamp(tb, 0, R.end));
    S.ppu = plotW() / Math.max(1, (ub - ua) * 1.03); S.u0 = ua - (ub - ua) * 0.015; clampView();
  }
  function zoomAt(f, xPix) {
    const pw = plotW(), px0 = L ? L.px0 : 296;
    const u = S.u0 + (xPix === undefined ? pw / 2 : xPix - px0) / S.ppu;
    const old = S.ppu;
    S.ppu = old * f; clampView();
    S.u0 = u - (xPix === undefined ? pw / 2 : xPix - px0) / S.ppu; clampView();
  }
  function ensureVisible(tt) {
    const pw = plotW(), x = (t2u(tt) - S.u0) * S.ppu;
    if (x < pw * 0.04 || x > pw * 0.96) { S.u0 = t2u(tt) - pw / S.ppu * 0.3; clampView(); }
  }
  function refreshChart() { requestDraw(); requestAnimationFrame(drawMini); updateCurRead(); }

  // ------------------------------------------------------------------ 光标 / 选帧
  function setT(tt, keepView) {
    S.T = clamp(tt, 0, R.end);
    if (!keepView) ensureVisible(S.T);
    updateMimic(); updateLogNow(); refreshChart();
  }
  function selectFrame(f) {
    S.sel = f ? f.id : null;
    if (f) { showBottom('frame'); S.T = f.t0; ensureVisible(f.t0); updateMimic(); updateLogNow(); }
    renderFrame(); refreshChart();
  }
  function updateCurRead() {
    const e = $('#curRead');
    e.innerHTML = '<b class="a">A</b> ' + fmtS(S.T) + (S.B !== null ? '　<b class="b">B</b> ' + fmtS(S.B) + '　Δ ' + fmtD(Math.abs(S.B - S.T)) : '');
    $('#clrB').hidden = S.B === null;
    $('#setB').classList.toggle('on', S.placeB);
  }
  function stepFrame(dir) {
    const list = R.tr.frames.filter(f => frameShown(f) && f.ok !== 'none' && S.rows.has(f.row));
    if (!list.length) return;
    const curT = S.sel ? IDX.byId[S.sel].t0 : S.T;
    let f;
    if (dir > 0) f = list.find(x => x.t0 > curT + 1e-6 || (S.sel && x.t0 === curT && x.id > S.sel));
    else for (let i = list.length - 1; i >= 0; i--) { if (list[i].t0 < curT - 1e-6) { f = list[i]; break; } }
    if (f) selectFrame(f);
  }

  // ------------------------------------------------------------------ 时序图上的操作
  const tip = $('#tip');
  const ptrs = new Map();
  let drag = null, pinch = null;
  function hit(e) {
    if (!L) return null;
    const r = chart.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const row = L.rows.find(q => y >= q.y && y < q.y + q.h) || null;
    const inPlot = x >= L.px0 && x <= L.px0 + L.plotW;
    const tt = inPlot ? clamp(u2t(clamp(S.u0 + (x - L.px0) / S.ppu, 0, WARP.uEnd)), 0, R.end) : null;
    let frame = null;
    if (row && row.kind === 'row' && row.type === 'bus' && inPlot) {
      const tol = 3 / S.ppu;
      const a = (IDX.rowFrames[row.id] || []);
      let best = null, bd = 1e9;
      for (let i = 0; i < a.length; i++) {
        const f = a[i];
        if (f.t0 > tt + tol + 1) break;
        if (!frameShown(f) || f.t1 < tt - tol) continue;
        const d = tt < f.t0 ? f.t0 - tt : tt > f.t1 ? tt - f.t1 : 0;
        if (d < bd) { bd = d; best = f; }
      }
      frame = best;
    }
    return { x, y, row, inPlot, t: tt, frame };
  }
  function showTip(e, hh) {
    if (!hh || !hh.row || hh.row.kind !== 'row' || !hh.inPlot) { tip.hidden = true; return; }
    const r = hh.row;
    let html = '<span class="m">' + fmtS(hh.t) + '</span>　<b>' + esc(rowName(r.id)) + '</b><br>';
    if (r.type === 'bus') {
      if (!hh.frame) { tip.hidden = true; return; }
      const f = hh.frame;
      html += '<b>' + esc(fLabel(f)) + '</b>' + (f.attempt > 1 ? '　' + esc(t('ui.attempt', [f.attempt])) : '') + '<br><span class="m">' + fmtS(f.t0) + '　' + fmtD(f.t1 - f.t0) + (f.bytes.length ? '　' + f.bytes.length + ' ' + esc(t('ui.bytes')) : '') + '</span>';
      if (f.ok !== 'ok') html += '<br>' + esc(t('ui.ok.' + f.ok));
    } else if (r.type === 'ana') {
      const sv = valAt('ht.sv', hh.t);
      html += pvAt(hh.t).toFixed(1) + ' ℃' + (sv && sv.v ? '　（' + esc(rowName('ht.sv')) + ' ' + sv.a[0] + ' ℃）' : '');
    } else {
      const a = R.tr.sig[r.id] || [], i = bs(a, hh.t);
      if (i < 0) { tip.hidden = true; return; }
      const c = a[i], t1 = i + 1 < a.length ? a[i + 1].t : R.end;
      html += '<b>' + esc(r.type === 'dig' ? (c.v ? 'ON' : 'OFF') : (stText(c) || '—')) + '</b><br><span class="m">' + esc(t('ui.since', [fmtS(c.t), fmtS(t1), fmtD(t1 - c.t)])) + '</span>';
    }
    tip.innerHTML = html; tip.hidden = false;
    const tw0 = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = clamp(e.clientX + 14, 4, window.innerWidth - tw0 - 4) + 'px';
    tip.style.top = (e.clientY + 18 + th > window.innerHeight ? e.clientY - th - 10 : e.clientY + 18) + 'px';
  }
  chart.addEventListener('pointerdown', e => {
    if (e.button !== undefined && e.button > 0) return;
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { chart.setPointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
    if (ptrs.size === 2) {
      const p = Array.from(ptrs.values()), r = chart.getBoundingClientRect();
      pinch = { d: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1, ppu: S.ppu, cx: (p[0].x + p[1].x) / 2 - r.left, u: S.u0 + ((p[0].x + p[1].x) / 2 - r.left - L.px0) / S.ppu };
      drag = null;
    } else drag = { x: e.clientX, y: e.clientY, u0: S.u0, moved: false, shift: e.shiftKey };
    tip.hidden = true;
  });
  chart.addEventListener('pointermove', e => {
    if (ptrs.has(e.pointerId)) ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && ptrs.size === 2) {
      const p = Array.from(ptrs.values());
      S.ppu = pinch.ppu * (Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1) / pinch.d; clampView();
      S.u0 = pinch.u - (pinch.cx - L.px0) / S.ppu; clampView(); refreshChart();
      return;
    }
    if (drag) {
      const dx = e.clientX - drag.x;
      if (!drag.moved && Math.abs(dx) > 4 && Math.abs(dx) > Math.abs(e.clientY - drag.y)) { drag.moved = true; chart.classList.add('drag'); }
      if (drag.moved) { S.u0 = drag.u0 - dx / S.ppu; clampView(); refreshChart(); }
      return;
    }
    if (e.pointerType === 'mouse') showTip(e, hit(e));
  });
  function pointerEnd(e) {
    ptrs.delete(e.pointerId);
    if (ptrs.size < 2) pinch = null;
    const d = drag; drag = null; chart.classList.remove('drag');
    if (!d || d.moved || e.type === 'pointercancel') return;
    if (Math.abs(e.clientY - d.y) > 6) return;
    const hh = hit(e);
    if (!hh) return;
    if (hh.row && hh.row.kind === 'zone' && !hh.inPlot) {
      if (S.zoneFold.has(hh.row.zone)) S.zoneFold.delete(hh.row.zone); else S.zoneFold.add(hh.row.zone);
      refreshChart(); return;
    }
    if (!hh.inPlot) return;
    if (hh.frame && !(d.shift || S.placeB)) { selectFrame(hh.frame); return; }
    if (d.shift || S.placeB) { S.B = hh.t; S.placeB = false; refreshChart(); }
    else setT(hh.t, true);
  }
  chart.addEventListener('pointerup', pointerEnd);
  chart.addEventListener('pointercancel', pointerEnd);
  chart.addEventListener('pointerleave', () => { tip.hidden = true; });
  chart.addEventListener('dblclick', e => { const r = chart.getBoundingClientRect(); zoomAt(2, e.clientX - r.left); refreshChart(); });
  chart.addEventListener('wheel', e => {
    const horiz = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    if (!(e.ctrlKey || e.metaKey || e.shiftKey || horiz)) return; // 普通滚轮留给页面滚动
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) { const r = chart.getBoundingClientRect(); zoomAt(Math.exp(-e.deltaY * 0.004), e.clientX - r.left); }
    else { S.u0 += (horiz ? e.deltaX : e.deltaY) / S.ppu; clampView(); }
    refreshChart();
  }, { passive: false });
  document.addEventListener('keydown', e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const k = e.key;
    if (k === 'ArrowLeft' || k === 'ArrowRight') { setT(u2t(clamp(t2u(S.T) + (k === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 80 : 12) / S.ppu, 0, WARP.uEnd))); e.preventDefault(); }
    else if (k === '[') stepFrame(-1);
    else if (k === ']') stepFrame(1);
    else if (k === ' ') { togglePlay(); e.preventDefault(); }
    else if (k === '+' || k === '=') { zoomAt(1.6); refreshChart(); }
    else if (k === '-') { zoomAt(1 / 1.6); refreshChart(); }
    else if (k === 'f') { fitRange(0, R.end); refreshChart(); }
    else if (k === 'Escape') { S.B = null; S.placeB = false; S.sel = null; closePops(); renderFrame(); refreshChart(); }
  });

  // ------------------------------------------------------------------ 播放
  let lastTs = 0;
  function togglePlay() {
    S.playing = !S.playing;
    if (S.playing) { if (S.T >= R.end - 1) S.T = 0; lastTs = 0; requestAnimationFrame(playTick); }
    $('#play').textContent = (S.playing ? '❚❚ ' : '▶ ') + t(S.playing ? 'ui.pause' : 'ui.play');
  }
  function playTick(ts) {
    if (!S.playing) return;
    if (lastTs) {
      const nt = S.T + Math.min(100, ts - lastTs) * S.speed;
      if (nt >= R.end) { setT(R.end); togglePlay(); return; }
      setT(nt);
    }
    lastTs = ts;
    requestAnimationFrame(playTick);
  }

  // ------------------------------------------------------------------ 设备示意
  const LAMPS = {
    fcOut: ['io.pon', 'io.poff', 'io.flow', 'io.run', 'io.rst', 'io.bz'], fcIn: ['do.stb', 'do.hvy', 'do.lgt'],
    plcOut: ['po.pon', 'po.poff'], ht: ['ht.pwr', 'ht.flow', 'ht.run', 'ht.heat', 'ht.stb'],
  };
  const lampCls = id => (id === 'do.stb' || id === 'ht.stb' ? ' g' : id === 'do.hvy' || id === 'do.lgt' ? ' f' : '');
  function buildMimic() {
    const pal = PAL[S.theme];
    const lamps = ids => ids.map(id => '<span class="lamp' + lampCls(id) + '" data-sig="' + id + '"><i></i>' + esc(rowName(id).replace(/[（(].*$/, '')) + '</span>').join('');
    const wire = (bus, baud) => '<div class="wire" id="w-' + bus + '"><div>' + esc(t('ui.w.' + bus)) + ' · ' + baud + ' bps</div><div class="bar"></div><div class="fr"></div><div class="age"></div></div>';
    $('#mimic').innerHTML =
      '<div class="dev" style="--zc:' + pal.zone.fc_in[0] + '"><h3><span>' + esc(t('ui.dev.fc')) + '</span><span class="state" data-st="fc.mode"></span></h3>'
      + '<div class="lamps"><span class="cap">' + esc(t('ui.out')) + '</span>' + lamps(LAMPS.fcOut) + '</div>'
      + '<div class="lamps"><span class="cap">' + esc(t('ui.in')) + '</span>' + lamps(LAMPS.fcIn) + '</div><div class="alm" data-st="fc.alm"></div></div>'
      + wire('mb', S.params.fcBaud)
      + '<div class="dev" style="--zc:' + pal.zone.plc[0] + '"><h3><span>' + esc(t('ui.dev.plc')) + '</span><span class="state" data-st="plc.on"></span></h3>'
      + '<div class="kv"><span data-st="plc.st"></span></div><div class="kv"><span>' + esc(t('ui.cache')) + ' <b data-st="plc.ct"></b></span><span>' + esc(rowName('plc.fail')) + ' <b data-st="plc.fail"></b></span></div>'
      + '<div class="lamps">' + lamps(LAMPS.plcOut) + '</div><div class="alm" data-st="plc.cf"></div></div>'
      + wire('su', S.params.suBaud)
      + '<div class="dev" style="--zc:' + pal.zone.su_st[0] + '"><h3><span>' + esc(t('ui.dev.ht')) + '</span><span class="state" data-st="ht.rdy"></span></h3>'
      + '<div class="lamps">' + lamps(LAMPS.ht) + '</div>'
      + '<div class="kv"><span>' + esc(rowName('ht.sv')) + ' <b data-st="ht.sv"></b></span><span>' + esc(rowName('ht.pv').replace(' ℃', '')) + ' <b id="pvNow"></b></span></div><div class="alm" data-st="ht.alm"></div></div>';
    updateMimic();
  }
  function updateMimic() {
    if (!R) return;
    $$('#mimic [data-sig]').forEach(e => { const c = valAt(e.dataset.sig, S.T); e.classList.toggle('on', !!(c && c.v)); });
    $$('#mimic [data-st]').forEach(e => { const s = stText(valAt(e.dataset.st, S.T)); e.textContent = s || (e.classList.contains('alm') ? '' : '—'); });
    $('#pvNow').textContent = pvAt(S.T).toFixed(1) + ' ℃';
    ['mb', 'su'].forEach(bus => {
      const w = $('#w-' + bus), cut = valAt('ln.' + bus, S.T);
      const isCut = !!(cut && cut.v);
      let f = null;
      const rows = bus === 'mb' ? ['mb.req', 'mb.rsp'] : ['su.tx', 'su.rx'];
      rows.forEach(rid => { const a = IDX.rowFrames[rid] || []; let lo = 0, hi = a.length - 1, r = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m].t0 <= S.T) { r = m; lo = m + 1; } else hi = m - 1; } if (r >= 0 && (!f || a[r].t0 > f.t0)) f = a[r]; });
      const busy = f && f.t1 >= S.T && f.ok !== 'none';
      w.classList.toggle('cut', isCut); w.classList.toggle('busy', !!busy && !isCut);
      const fr = $('.fr', w), age = $('.age', w);
      if (f) {
        const toRight = f.row === 'mb.req' || f.row === 'su.tx';
        fr.textContent = (f.ok === 'none' ? '✕ ' : toRight ? '→ ' : '← ') + fLabel(f);
        fr.classList.toggle('bad', f.ok !== 'ok' || f.kind === 'fault');
        age.textContent = isCut ? t('ui.lineCut') : busy ? t('ui.inflight') : t('ui.ago', [fmtD(S.T - f.t1)]);
      } else { fr.textContent = '—'; fr.classList.remove('bad'); age.textContent = isCut ? t('ui.lineCut') : ''; }
      age.classList.toggle('wst', isCut);
    });
  }

  // ------------------------------------------------------------------ 关键时间
  function renderMetrics() {
    const m = R.meas, P = R.P, out = [];
    const max = a => a.length ? Math.max.apply(null, a) : null;
    const tile = (k, v, x, cls) => out.push('<div class="mt ' + (v === null ? 'na' : cls || '') + '"><div class="n">' + esc(t(k)) + '</div><div class="v">' + (v === null ? '—' : esc(v)) + '</div><div class="x">' + esc(x || '') + '</div></div>');
    const d = v => v === null ? null : fmtD(v);
    tile('mt.firstComm', d(max(m.firstComm)), '');
    tile('mt.runDelay', d(max(m.runDelay)), '');
    tile('mt.stbDelay', d(max(m.stbDelay)), t('mt.worst', [fmtD(P.suPoll)]));
    tile('mt.almDelay', d(max(m.almDelay)), t('mt.worst', [fmtD(P.suPoll)]));
    if (m.suCutDetect.length) tile('mt.suCut', d(max(m.suCutDetect)), '');
    if (m.mbCutDetect.length) tile('mt.mbCut', d(max(m.mbCutDetect)), '');
    const nRst = m.resetResult.length, rc = max(m.resetClear);
    if (nRst) {
      if (rc !== null) tile('mt.resetClear', fmtD(rc), t('mt.window', [fmtD(P.resetHold), fmtD(P.resetHold - rc)]), rc < P.resetHold ? 'ok' : 'bad');
      const ok = m.resetResult.filter(r => r.ok).length, ng = nRst - ok;
      tile('mt.reset', (ok ? t('mt.ok', [ok]) : '') + (ok && ng ? ' · ' : '') + (ng ? t('mt.ng', [ng]) : ''), ng && rc === null ? t('mt.notCleared') : '', ng ? 'bad' : 'ok');
    }
    tile('mt.mbResp', fmtD(m.mbMaxResp), t('mt.limit', [fmtD(P.fcTimeout)]) + ' · ' + t('mt.frames', [m.mbFrames, m.mbFail]), m.mbFail ? 'bad' : 'ok');
    tile('mt.suBusy', m.suBusyPct.toFixed(2) + ' %', t('mt.frames', [m.suFrames, m.suFail]), m.suFail ? 'bad' : 'ok');
    $('#metrics').innerHTML = out.join('');
  }

  // ------------------------------------------------------------------ 日志
  let logRows = [];
  function renderLog() {
    const pal = PAL[S.theme], zc = { fc: pal.zone.fc_in[0], plc: pal.zone.plc[0], ht: pal.zone.su_st[0], inj: pal.fault[0] };
    $('#logFilter').innerHTML = ['fc', 'plc', 'ht', 'inj'].map(w => '<label class="chk"><input type="checkbox" data-who="' + w + '"' + (S.logWho[w] ? ' checked' : '') + '><span style="color:' + zc[w] + ';font-weight:600">' + esc(t('ui.who.' + w)) + '</span></label>').join('')
      + '<span class="vr"></span><label class="chk"><input type="checkbox" id="logWarn"' + (S.logWarn ? ' checked' : '') + '><span>' + esc(t('ui.warnOnly')) + '</span></label>';
    const list = R.tr.log.filter(l => S.logWho[l.who] && (!S.logWarn || l.lvl !== 'info'));
    $('#log').innerHTML = list.map((l, i) => '<div class="li ' + l.lvl + '" data-i="' + i + '" style="--zc:' + zc[l.who] + '"><span class="tm">' + (l.t / 1000).toFixed(3) + '</span><span class="who">' + esc(t('ui.who.' + l.who)) + '</span><span class="tx">' + esc(logText(l)) + '</span></div>').join('');
    logRows = list;
    updateLogNow(true);
  }
  let logNow = -2;
  function updateLogNow(force) {
    if (!logRows) return;
    const i = bs(logRows, S.T);
    if (i === logNow && !force) return;
    logNow = i;
    const els = $('#log').children;
    for (let k = 0; k < els.length; k++) { els[k].classList.toggle('now', k === i); els[k].classList.toggle('future', k > i); }
    if (i >= 0 && els[i] && !$('#pane-log').hidden) {
      const box = $('#log'), el = els[i];
      if (el.offsetTop < box.scrollTop || el.offsetTop + el.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = el.offsetTop - box.clientHeight / 2;
    }
  }
  $('#log').addEventListener('click', e => { const li = e.target.closest('.li'); if (li) setT(logRows[+li.dataset.i].t); });
  $('#logFilter').addEventListener('change', e => {
    if (e.target.dataset.who) S.logWho[e.target.dataset.who] = e.target.checked;
    if (e.target.id === 'logWarn') S.logWarn = e.target.checked;
    renderLog();
  });

  // ------------------------------------------------------------------ 帧详情
  const FLEN = { STX: 1, ETX: 1, ADDR: 0, CMD: 2, SUM: 2, CRC: 2, FC: 1, REG: 2, VAL: 2, CNT: 2, BC: 1, CODE: 1, ACK: 1, NAK: 1 };
  function fieldMeaning(f, name, raw) {
    if (name === 'CMD') { const req = f.row === 'su.rx' && f.pair ? IDX.byId[f.pair] : f; return req ? fLabel(req) : ''; }
    if (name === 'FC') return I.has('fc.' + raw) ? t('fc.' + raw) : '';
    if (name === 'VAL') return (parseInt(raw, 16) / 10).toFixed(1) + ' ℃';
    if (name === 'CNT') return parseInt(raw, 16) + '';
    if (name === 'CODE') return t('f.NAK' + raw).replace(/^NAK\s*/, '');
    if (name === 'DATA') {
      if (f.bus === 'mb') return f.lab.k === 'f.rMR0' ? t('f.rMR0') : f.lab.k === 'f.rMRa' ? t('f.rMRa', f.lab.a) : '';
      if (f.code === 'WT') return (parseInt(raw, 10) / 10).toFixed(1) + ' ℃';
      if (f.code === 'WF' || f.code === 'WR' || f.code === 'WE' || f.code === 'WB') return parseInt(raw, 10) ? 'ON' : 'OFF';
      if (f.code === 'rRS') return statusText(f.lab.a[0]);
      if (f.code === 'rRT') return f.lab.a[0] + ' ℃';
      if (f.code === 'rRA') return f.lab.a[0] ? t('f.rRA', f.lab.a) : t('f.rMR0');
    }
    return '';
  }
  function renderFrame() {
    const box = $('#pane-frame'), f = S.sel ? IDX.byId[S.sel] : null;
    if (!f) { box.innerHTML = '<p class="fine">' + esc(t('ui.noFrame')) + '</p><p class="fine warnline">' + esc(t('ui.fake')) + '</p>'; return; }
    const pair = f.pair ? IDX.byId[f.pair] : null;
    const baud = f.bus === 'mb' ? R.P.fcBaud : R.P.suBaud;
    let h = '<div class="fd-h"><span class="ttl">' + esc(rowName(f.row) + '：' + fLabel(f)) + '</span>'
      + '<span class="m">' + esc(t('ui.start')) + ' ' + fmtS(f.t0) + '　' + esc(t('ui.dur')) + ' ' + fmtD(f.t1 - f.t0) + (f.bytes.length ? '　' + f.bytes.length + ' ' + esc(t('ui.bytes')) + ' @ ' + baud + ' bps' : '') + '</span>'
      + '<span class="st' + (f.ok === 'ok' ? '' : ' bad') + '">' + esc(t('ui.ok.' + f.ok)) + '</span>'
      + (f.attempt > 1 ? '<span class="st bad">' + esc(t('ui.attempt', [f.attempt])) + '</span>' : '')
      + '<span class="sp"></span><button type="button" class="btn" data-nav="-1">◀ ' + esc(t('ui.prev')) + '</button><button type="button" class="btn" data-nav="1">' + esc(t('ui.next')) + ' ▶</button></div>';
    if (pair) {
      const req = f.t0 <= pair.t0 ? f : pair, rsp = req === f ? pair : f;
      h += '<p class="fine">' + esc(t('ui.pair')) + '：<button type="button" class="btn" data-go="' + pair.id + '">' + esc(rowName(pair.row) + '：' + fLabel(pair)) + '　' + fmtS(pair.t0) + '</button>'
        + (rsp.ok !== 'none' ? '　' + esc(t('ui.turn', [fmtD(rsp.t0 - req.t1)])) : '') + '</p>';
    }
    if (f.bytes.length) {
      let pos = 0;
      const fixed = f.fields.reduce((s, x) => s + (x[0] === 'ADDR' ? (f.bus === 'mb' ? 1 : 2) : x[0] === 'DATA' ? 0 : FLEN[x[0]] || 0), 0);
      const rows = [], chips = [];
      f.fields.forEach(x => {
        const n = x[0] === 'ADDR' ? (f.bus === 'mb' ? 1 : 2) : x[0] === 'DATA' ? f.bytes.length - fixed : FLEN[x[0]];
        const b = f.bytes.slice(pos, pos + n); pos += n;
        const hx = b.slice(0, 12).map(v => v.toString(16).toUpperCase().padStart(2, '0')).join(' ') + (b.length > 12 ? ' … (' + b.length + ')' : '');
        const ascii = f.bus === 'su' && b.every(v => v >= 0x20 && v < 0x7f) ? String.fromCharCode.apply(null, b.slice(0, 24)) + (b.length > 24 ? '…' : '') : '';
        chips.push('<span class="fb"><small>' + esc(x[0]) + '</small>' + esc(hx) + '</span>');
        rows.push('<tr><td>' + esc(x[0]) + '　' + esc(t('fld.' + x[0])) + '</td><td class="raw">' + esc(hx) + (ascii ? '　"' + esc(ascii) + '"' : '') + '</td><td>' + esc(fieldMeaning(f, x[0], ascii || (f.bus === 'mb' ? b.map(v => v.toString(16).toUpperCase().padStart(2, '0')).join('') : x[1]))) + '</td></tr>');
      });
      h += '<div class="bytes">' + chips.join('') + '</div><table class="fields"><tr><th>' + esc(t('ui.field')) + '</th><th>' + esc(t('ui.raw')) + '</th><th>' + esc(t('ui.meaning')) + '</th></tr>' + rows.join('') + '</table>';
    }
    h += '<p class="fine warnline">' + esc(t('ui.fake')) + '</p>';
    box.innerHTML = h;
  }
  $('#pane-frame').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.nav) stepFrame(+b.dataset.nav);
    if (b.dataset.go) selectFrame(IDX.byId[+b.dataset.go]);
  });
  function showBottom(tab) {
    $$('#botTabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
    ['log', 'frame', 'notes'].forEach(k => { $('#pane-' + k).hidden = k !== tab; });
    if (tab === 'log') updateLogNow(true);
  }
  $('#botTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) showBottom(b.dataset.tab); });

  // ------------------------------------------------------------------ 场景 / 脚本
  function fillScenarios() {
    const sel = $('#scn');
    const groups = {};
    C.SCENARIOS.forEach(s => { (groups[s.block] || (groups[s.block] = [])).push(s); });
    sel.innerHTML = Object.keys(groups).map(b => '<optgroup label="' + esc(t('b.' + b)) + '">' + groups[b].map(s => '<option value="' + s.id + '">' + esc(s.id.replace('x-', '＋') + '　' + t('sc.' + s.id)) + '</option>').join('') + '</optgroup>').join('');
    sel.value = S.scn;
    $('#scnQ').textContent = t('sq.' + S.scn);
  }
  function loadScenario(id, keepView) {
    const sc = C.SCENARIOS.find(s => s.id === id);
    // 上一个场景自带的参数覆盖先还原
    Object.keys(S.override).forEach(k => { S.params[k] = S.override[k]; });
    S.override = {};
    if (sc.params) Object.keys(sc.params).forEach(k => { S.override[k] = S.params[k]; S.params[k] = sc.params[k]; });
    S.scn = id; S.script = sc.script.map(e => e.slice()); S.end = sc.end; S.focus = sc.focus.slice();
    S.sel = null; S.B = null;
    if (!keepView) {
      S.view = sc.view; S.rows = new Set(C.VIEWS[sc.view] || C.ROWS.map(r => r.id)); S.zoneFold = new Set();
      S.hidePeriodic = sc.view === 'alarm'; S.warp = WARP_SCN.indexOf(id) >= 0; S.split = false; S.activeOnly = false;
    }
    run();
    S.T = clamp(sc.focus[0] * 1000 + 500, 0, R.end);
    fitRange(S.focus[0] * 1000, S.focus[1] * 1000);
    renderAll();
  }
  function renderScript() {
    const acts = g => C.ACTIONS.filter(a => a.g === g).map(a => '<option value="' + a.id + '">' + esc(t('a.' + a.id, [a.p === 'n' ? 'n' : '…']).replace(/\s*…\s*℃?/, '').replace(/[：:]\s*$/, '')) + '</option>').join('');
    const rows = S.script.map((ev, i) => {
      const a = C.ACTIONS.find(x => x.id === ev[1]) || {};
      let arg = '';
      if (a.p === 'temp') arg = '<input type="number" data-k="p" min="25" max="85" step="1" value="' + ev[2] + '" aria-label="℃">';
      else if (a.p === 'n') arg = '<input type="number" data-k="p" min="1" max="20" step="1" value="' + ev[2] + '">';
      else if (a.p === 'alm') arg = '<select data-k="p">' + ['stop', 'cont', 'leak'].map(x => '<option value="' + x + '"' + (ev[2] === x ? ' selected' : '') + '>' + esc(t('al.' + x)) + '</option>').join('') + '</select>';
      return '<tr data-i="' + i + '" class="' + (a.g || '') + '"><td><input type="number" data-k="t" min="0" max="600" step="0.5" value="' + ev[0] + '"></td>'
        + '<td><select class="act" data-k="a"><optgroup label="' + esc(t('ui.gAct.fc')) + '">' + acts('fc') + '</optgroup><optgroup label="' + esc(t('ui.gAct.inj')) + '">' + acts('inj') + '</optgroup></select></td>'
        + '<td class="arg">' + arg + '</td><td><button type="button" class="del" aria-label="delete">✕</button></td></tr>';
    }).join('');
    $('#script').innerHTML = '<tr><th>' + esc(t('ui.time')) + '</th><th>' + esc(t('ui.action')) + '</th><th>' + esc(t('ui.arg')) + '</th><th></th></tr>' + rows;
    $$('#script tr[data-i]').forEach(tr => { $('select.act', tr).value = S.script[+tr.dataset.i][1]; });
    $('#endSec').value = S.end;
  }
  let rerunH = 0;
  function rerun(structural) {
    clearTimeout(rerunH);
    rerunH = setTimeout(() => {
      const keep = [u2t(Math.max(0, S.u0)), u2t(Math.min(WARP.uEnd, S.u0 + plotW() / S.ppu))];
      run();
      fitRange(Math.min(keep[0], R.end), Math.min(keep[1], R.end));
      if (structural) renderScript();
      renderData();
    }, 120);
  }
  $('#script').addEventListener('change', e => {
    const tr = e.target.closest('tr[data-i]');
    if (!tr) return;
    const ev = S.script[+tr.dataset.i], k = e.target.dataset.k;
    if (k === 't') ev[0] = clamp(+e.target.value || 0, 0, 600);
    if (k === 'a') { ev[1] = e.target.value; const a = C.ACTIONS.find(x => x.id === ev[1]); if (a.p) ev[2] = a.d; else ev.length = 2; }
    if (k === 'p') ev[2] = isNaN(+e.target.value) ? e.target.value : +e.target.value;
    S.script.sort((a, b) => a[0] - b[0]);
    rerun(true);
  });
  $('#script').addEventListener('click', e => {
    if (!e.target.classList.contains('del')) return;
    S.script.splice(+e.target.closest('tr').dataset.i, 1); rerun(true);
  });
  $('#addRow').addEventListener('click', () => {
    const last = S.script.length ? S.script[S.script.length - 1][0] : 0;
    S.script.push([Math.min(last + 5, S.end), 'fc.reset']);
    if (last + 10 > S.end) S.end = Math.min(600, last + 15);
    rerun(true);
  });
  $('#restore').addEventListener('click', () => loadScenario(S.scn, true));
  $('#endSec').addEventListener('change', e => { S.end = clamp(+e.target.value || 60, 5, 600); rerun(true); });
  $('#scn').addEventListener('change', e => loadScenario(e.target.value));

  // ------------------------------------------------------------------ 参数
  const changedParams = () => C.PARAM_DEFS.filter(d => S.params[d[0]] !== d[2]);
  function renderParams() {
    const groups = ['fc', 'plc', 'ht', 'link'];
    $('#params').innerHTML = groups.map(g => '<details class="pgroup" open><summary>' + esc(t('g.' + g)) + '</summary>' + C.PARAM_DEFS.filter(d => d[1] === g).map(d => {
      const id = d[0], v = S.params[id], u = d[6];
      let ctl;
      if (u === 'bool') ctl = '<input type="checkbox" id="p-' + id + '" data-p="' + id + '"' + (v ? ' checked' : '') + '>';
      else if (u === 'bps') ctl = '<select id="p-' + id + '" data-p="' + id + '">' + C.BAUDS.map(b => '<option' + (b === v ? ' selected' : '') + '>' + b + '</option>').join('') + '</select><span class="unit">bps</span>';
      else ctl = '<input type="number" id="p-' + id + '" data-p="' + id + '" min="' + d[3] + '" max="' + d[4] + '" step="' + d[5] + '" value="' + v + '"><span class="unit">' + esc(t('u.' + u)) + '</span>';
      const dv = u === 'bool' ? (d[2] ? 'ON' : 'OFF') : d[2] + (u === 'bps' ? '' : ' ' + t('u.' + u));
      return '<div class="prow' + (v !== d[2] ? ' changed' : '') + '" title="' + esc(t('ui.default', [dv])) + '"><label class="name" for="p-' + id + '">' + esc(t('p.' + id)) + '<span class="tag' + (d[7] === '未' || d[7] === '假' ? ' q' : '') + '">' + esc(t('src.' + d[7])) + '</span></label>'
        + '<span class="ctl">' + ctl + '<button type="button" class="undo" data-undo="' + id + '" aria-label="reset">↺</button></span></div>';
    }).join('') + '</details>').join('');
    updateChanged();
  }
  function updateChanged() {
    const n = changedParams().length, b = $('#chg');
    b.hidden = !n; b.textContent = n;
    $('#resetParams').title = t('ui.changed', [n]);
  }
  $('#params').addEventListener('change', e => {
    const id = e.target.dataset.p;
    if (!id) return;
    const d = C.PARAM_DEFS.find(x => x[0] === id);
    let v;
    if (d[6] === 'bool') v = e.target.checked;
    else if (d[6] === 'bps') v = +e.target.value;
    else { v = clamp(+e.target.value, d[3], d[4]); if (isNaN(v)) v = d[2]; e.target.value = v; }
    S.params[id] = v; delete S.override[id];
    e.target.closest('.prow').classList.toggle('changed', v !== d[2]);
    updateChanged(); rerun(false);
  });
  $('#params').addEventListener('click', e => {
    const id = e.target.dataset.undo;
    if (!id) return;
    S.params[id] = C.PARAM_DEFS.find(x => x[0] === id)[2]; delete S.override[id];
    renderParams(); rerun(false);
  });
  $('#resetParams').addEventListener('click', () => { S.params = C.defaults(); S.override = {}; renderParams(); rerun(false); });
  $('#sideTabs').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    $$('#sideTabs button').forEach(x => x.classList.toggle('on', x === b));
    $('#pane-script').hidden = b.dataset.tab !== 'script'; $('#pane-params').hidden = b.dataset.tab !== 'params';
  });

  // ------------------------------------------------------------------ 工具条
  function renderViews() {
    $('#views').innerHTML = ['all', 'startup', 'supply', 'poll', 'alarm'].map(v => '<button type="button" data-v="' + v + '" class="' + (S.view === v ? 'on' : '') + '">' + esc(t('ui.v.' + v)) + '</button>').join('')
      + (S.view === 'custom' ? '<button type="button" class="on">' + esc(t('ui.v.custom')) + '</button>' : '');
    const shown = L ? L.rows.filter(r => r.kind === 'row').length : S.rows.size;
    $('#rowCount').textContent = t('ui.rowsShown', [shown, C.ROWS.length]);
    $('#oHide').checked = S.hidePeriodic; $('#oSplit').checked = S.split; $('#oActive').checked = S.activeOnly;
    $('#oLinks').checked = S.links; $('#oMarks').checked = S.marks; $('#oWarp').checked = S.warp;
  }
  $('#views').addEventListener('click', e => {
    const v = e.target.dataset.v;
    if (!v) return;
    S.view = v; S.rows = new Set(C.VIEWS[v] || C.ROWS.map(r => r.id)); S.zoneFold = new Set();
    renderSigPop(); refreshChart(); requestAnimationFrame(renderViews);
  });
  function renderSigPop() {
    const pal = PAL[S.theme];
    $('#sigPop').innerHTML = C.ZONES.map(z => {
      const rows = C.ROWS.filter(r => r.zone === z), all = rows.every(r => S.rows.has(r.id));
      return '<div class="zg"><label class="zh" style="--zc:' + pal.zone[z][0] + '"><input type="checkbox" data-zone="' + z + '"' + (all ? ' checked' : '') + '>' + esc(t('z.' + z)) + '</label>'
        + rows.map(r => '<label><input type="checkbox" data-row="' + r.id + '"' + (S.rows.has(r.id) ? ' checked' : '') + '>' + esc(rowName(r.id)) + '</label>').join('') + '</div>';
    }).join('');
  }
  $('#sigPop').addEventListener('change', e => {
    const d = e.target.dataset;
    if (d.row) { if (e.target.checked) S.rows.add(d.row); else S.rows.delete(d.row); }
    if (d.zone) C.ROWS.filter(r => r.zone === d.zone).forEach(r => { if (e.target.checked) S.rows.add(r.id); else S.rows.delete(r.id); });
    S.view = 'custom';
    renderSigPop(); refreshChart(); requestAnimationFrame(renderViews);
  });
  function closePops() { $('#sigPop').hidden = true; $('#expPop').hidden = true; }
  $('#sigBtn').addEventListener('click', e => { e.stopPropagation(); const p = $('#sigPop'), was = p.hidden; closePops(); p.hidden = !was; });
  $('#expBtn').addEventListener('click', e => { e.stopPropagation(); const p = $('#expPop'), was = p.hidden; closePops(); p.hidden = !was; });
  document.addEventListener('click', e => { if (!e.target.closest('.pop')) closePops(); });
  const opt = (id, key, fn) => $(id).addEventListener('change', e => { S[key] = e.target.checked; if (fn) fn(); refreshChart(); requestAnimationFrame(renderViews); });
  opt('#oHide', 'hidePeriodic'); opt('#oSplit', 'split'); opt('#oActive', 'activeOnly'); opt('#oLinks', 'links'); opt('#oMarks', 'marks');
  $('#oWarp').addEventListener('change', e => {
    const keep = [u2t(Math.max(0, S.u0)), u2t(Math.min(WARP.uEnd, S.u0 + plotW() / S.ppu))];
    S.warp = e.target.checked; buildWarp(); fitRange(keep[0], keep[1]); refreshChart();
  });
  $('#zIn').addEventListener('click', () => { zoomAt(1.6); refreshChart(); });
  $('#zOut').addEventListener('click', () => { zoomAt(1 / 1.6); refreshChart(); });
  $('#zFit').addEventListener('click', () => { fitRange(0, R.end); refreshChart(); });
  $('#zFocus').addEventListener('click', () => { fitRange(S.focus[0] * 1000, Math.min(R.end, S.focus[1] * 1000)); refreshChart(); });
  $('#setB').addEventListener('click', () => { S.placeB = !S.placeB; updateCurRead(); });
  $('#clrB').addEventListener('click', () => { S.B = null; S.placeB = false; refreshChart(); });
  $('#play').addEventListener('click', togglePlay);
  $('#speed').addEventListener('change', e => { S.speed = +e.target.value; });

  // ------------------------------------------------------------------ 导出
  function download(name, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 800);
  }
  const csv = rows => '﻿' + rows.map(r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
  const baseName = () => 'plc-gateway_' + S.scn + '_' + I.getLang();
  $('#expPop').addEventListener('click', e => {
    const k = e.target.dataset.ex;
    if (!k) return;
    const svg = () => draw({ exp: true, W: Math.max(1200, L ? L.W : 1200) });
    if (k === 'svg') download(baseName() + '.svg', new Blob([svg()], { type: 'image/svg+xml' }));
    else if (k === 'copy') {
      const s = svg();
      (navigator.clipboard ? navigator.clipboard.writeText(s) : Promise.reject()).then(() => toast(t('ui.copied')), () => {
        const ta = document.createElement('textarea'); ta.value = s; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); toast(t('ui.copied')); } catch (err) { /* 复制不了就算了 */ }
        ta.remove();
      });
    } else if (k === 'png') {
      const s = svg(), img = new Image();
      img.onload = () => {
        const cv = document.createElement('canvas'); cv.width = img.width * 2; cv.height = img.height * 2;
        const cx = cv.getContext('2d'); cx.scale(2, 2); cx.drawImage(img, 0, 0);
        cv.toBlob(b => { if (b) download(baseName() + '.png', b); }, 'image/png');
      };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
    } else if (k === 'log') {
      download(baseName() + '_log.csv', new Blob([csv([['t_s', 'who', 'level', 'text']].concat(R.tr.log.map(l => [(l.t / 1000).toFixed(3), t('ui.who.' + l.who), l.lvl, logText(l)])))], { type: 'text/csv' }));
    } else if (k === 'frames') {
      download(baseName() + '_frames.csv', new Blob([csv([['start_s', 'end_s', 'dur_ms', 'row', 'frame', 'bytes', 'hex', 'result', 'attempt']].concat(R.tr.frames.map(f => [(f.t0 / 1000).toFixed(4), (f.t1 / 1000).toFixed(4), (f.t1 - f.t0).toFixed(2), rowName(f.row), fLabel(f), f.bytes.length, f.bytes.map(v => v.toString(16).toUpperCase().padStart(2, '0')).join(' '), t('ui.ok.' + f.ok), f.attempt || ''])))], { type: 'text/csv' }));
    }
    closePops();
  });

  // ------------------------------------------------------------------ 语言 / 主题 / 总装
  function applyStatic() {
    document.documentElement.lang = I.getLang();
    document.title = t('ui.title');
    $$('[data-i]').forEach(e => { e.textContent = t(e.dataset.i); });
    $$('[data-i-title]').forEach(e => { e.title = t(e.dataset.iTitle); });
    $$('#lang button').forEach(b => b.classList.toggle('on', b.dataset.lang === I.getLang()));
    $('#play').textContent = (S.playing ? '❚❚ ' : '▶ ') + t(S.playing ? 'ui.pause' : 'ui.play');
    let framed = false;
    try { framed = window.self !== window.top; } catch (e) { framed = true; }
    $('#exHint').hidden = !framed;
  }
  function renderData() { buildMimic(); renderMetrics(); renderLog(); renderFrame(); refreshChart(); requestAnimationFrame(renderViews); }
  function renderAll() { applyStatic(); fillScenarios(); renderScript(); renderParams(); renderSigPop(); renderViews(); renderData(); }
  $('#lang').addEventListener('click', e => {
    const l = e.target.dataset.lang;
    if (!l) return;
    I.setLang(l); store.set('lang', l); renderAll();
  });
  $('#theme').addEventListener('click', () => {
    S.theme = S.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = S.theme; store.set('theme', S.theme);
    renderSigPop(); renderData();
  });
  let rsH = 0;
  window.addEventListener('resize', () => { clearTimeout(rsH); rsH = setTimeout(() => { clampView(); refreshChart(); }, 80); });

  // 启动
  (function init() {
    const nav = (navigator.language || 'zh').toLowerCase();
    I.setLang(store.get('lang') || (nav.indexOf('ja') === 0 ? 'ja' : nav.indexOf('zh') === 0 ? 'zh' : 'en'));
    const host = document.documentElement.dataset.theme;
    S.theme = store.get('theme') || host || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = S.theme;
    loadScenario('2-1');
    // 第一次布局完再对一次视野（字体、滚动条会改变宽度）
    requestAnimationFrame(() => { fitRange(S.focus[0] * 1000, S.focus[1] * 1000); refreshChart(); });
  })();
  // 调试 / 自动截图用
  window.PLCGW = { S, view(a, b) { fitRange(a * 1000, b * 1000); refreshChart(); }, cursor(a, b) { S.B = b === undefined ? null : b * 1000; setT(a * 1000, true); }, result: () => R, select: id => selectFrame(IDX.byId[id]), svg: () => draw({ exp: true, W: 1400 }) };
})();
