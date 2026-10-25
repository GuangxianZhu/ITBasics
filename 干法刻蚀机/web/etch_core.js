// 干法刻蚀机的"核心"：配方、工艺模型、讲解文字。只算数，不碰界面和三维，网页（app.js）和虚幻（MyVRToyBox）共用。
//
// 虚幻那边不跑 JS：tools/export_core.mjs 把这里的文字和配方导出成 output/etcher_content.json，
// 并用 simulateEtch() 算一组"标准答案" output/etcher_golden.json；MyVRToyBox 的 C++ 版（ToyEtchCore）照这里逐行翻译，
// 跑 toy.EtchSelfTest 对答案。改了这里的公式，记得重新跑 export_core.mjs，再同步改 C++。

// ================= 配方 =================
export const PRESETS = [
  { id: 'std', name: '标准（推荐）', r: { P: 10, Ws: 600, Wb: 80, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 30 } },
  { id: 'nobias', name: '不加偏压', r: { P: 10, Ws: 600, Wb: 0, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 30 } },
  { id: 'hibias', name: '偏压太高', r: { P: 10, Ws: 600, Wb: 350, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 60 } },
  { id: 'nopass', name: '只用 Cl₂', r: { P: 30, Ws: 600, Wb: 60, cl2: 180, hbr: 0, o2: 0, T: 60, oe: 30 } },
  { id: 'nooe', name: '不过刻', r: { P: 10, Ws: 600, Wb: 80, cl2: 60, hbr: 120, o2: 4, T: 50, oe: 0 } },
];
export const FIELDS = [
  { k: 'P', name: '腔压', unit: 'mTorr', min: 3, max: 80, step: 1, tip: '气压低，离子方向更直；气压高，自由基多，但更容易往侧面刻' },
  { k: 'Ws', name: '源功率（线圈）', unit: 'W', min: 0, max: 1500, step: 50, tip: '决定等离子体有多"浓"' },
  { k: 'Wb', name: '偏压功率（卡盘）', unit: 'W', min: 0, max: 400, step: 10, tip: '决定离子打下来有多猛（能量）' },
  { k: 'cl2', name: 'Cl₂', unit: 'sccm', min: 0, max: 200, step: 5, tip: '主要的刻蚀气体' },
  { k: 'hbr', name: 'HBr', unit: 'sccm', min: 0, max: 200, step: 5, tip: '刻得温和，产物会沉积在侧壁上保护侧壁，对栅氧的选择比高' },
  { k: 'o2', name: 'O₂', unit: 'sccm', min: 0, max: 20, step: 1, tip: '少量就够：加强侧壁保护；多了会把光刻胶吃掉' },
  { k: 'T', name: '卡盘温度', unit: '°C', min: 20, max: 80, step: 5, tip: '温度高，纯化学反应（往侧面刻）更快' },
  { k: 'oe', name: '过刻', unit: '%', min: 0, max: 100, step: 5, tip: '到终点以后再刻多久，按主刻时间的百分比' },
];

// 配方检查不通过的原因（model() 返回 problemCode，文字查这里）
export const PROBLEMS = {
  lowpower: '源功率太低（< 150 W），点不着等离子体。',
  lowflow: '气体总流量太少（< 10 sccm），点不着等离子体。',
  nogas: '没有 Cl₂ 或 HBr，没有能刻多晶硅的气体。',
};

// ================= 工艺模型 =================
// 刻蚀速率单位 nm/min。思路：
//   等离子体密度 n ∝ 源功率；离子能量 ≈ 偏压功率 ÷ 离子电流（离子电流 ∝ n）
//   往下刻 = 离子和自由基"串联"：哪个少就被哪个卡住（离子-自由基协同）
//   往侧面刻 = 自由基自己的化学反应，被侧壁钝化层挡掉一部分
export function model(r) {
  const n = (r.Ws / 800) / (1 + r.P / 150);
  const Ei = Math.min(800, 15 + 0.9 * r.Wb / Math.max(n, 0.15));
  const Y = Math.max(0, Math.sqrt(Ei) - Math.sqrt(12)) / (Math.sqrt(115) - Math.sqrt(12));
  const Gn = (r.cl2 + 0.6 * r.hbr) / 100 * Math.sqrt(n) * Math.sqrt(r.P / 20);
  const ion = 1 / (1 / (Gn + 1e-6) + 1 / (1.2 * Y * n + 1e-6));
  const chem = 0.03 * Gn * Math.exp((r.T - 40) / 40);
  const hbrFrac = r.hbr / (r.cl2 + r.hbr + 1);
  const pass = Math.min(0.95, 0.7 * hbrFrac + 0.8 * r.o2 / 20);
  const ERv = 300 * (ion + chem);
  const ERl = 300 * chem * (1 - pass) + 300 * ion * 0.02 * (r.P / 20);
  const Yox = Math.max(0, Math.sqrt(Ei) - Math.sqrt(40)) / (Math.sqrt(115) - Math.sqrt(40));
  const ERox = 300 * 0.03 * Yox * n * (1 - 0.6 * hbrFrac) * (1 - 0.3 * r.o2 / 20) + 0.2;
  const ERmask = 300 * 0.12 * Y * n + 300 * 0.25 * (r.o2 / 20) * Math.sqrt(n) + 1;
  const u = 0.025 + 0.05 * Math.abs(r.P - 12) / 70 + (r.Ws > 1100 ? 0.02 : 0);
  const total = r.cl2 + r.hbr + r.o2;
  let problemCode = '';
  if (r.Ws < 150) problemCode = 'lowpower';
  else if (total < 10) problemCode = 'lowflow';
  else if (r.cl2 + r.hbr < 5) problemCode = 'nogas';
  return { n, Ei, Gn, ERv, ERl, ERox, ERmask, u, pass, sel: ERv / ERox, total, problemCode, problem: problemCode ? PROBLEMS[problemCode] : '' };
}

// ================= 刻蚀过程（按时间推进） =================
// E：一片晶圆的刻蚀状态。深度单位 nm；r[i] 是深度 i nm 处侧壁被往里刻掉多少（钻蚀，nm）
export function newEtch() {
  return { Dc: 0, De: 0, r: new Float32Array(101), maskH: 60, ox: 4, si: 0, gateLoss: 0, t: 0, tEp: null, tMain: 0, timeout: false, uncleared: 1, oesF: 0, pass: 0 };
}
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;

// 主刻 + 过刻期间每帧调用（dt 秒）
export function etchTick(E, M, dt) {
  const k = dt / 60;
  E.t += dt;
  const fc = 1 + M.u, fe = 1 - M.u;
  if (E.Dc < 100) E.Dc = Math.min(100, E.Dc + M.ERv * fc * k);
  else if (E.ox > 0) E.ox = Math.max(0, E.ox - M.ERox * fc * k);
  else E.si += M.ERv * 0.8 * fc * k;
  E.De = Math.min(100, E.De + M.ERv * fe * k);
  const reach = Math.min(100, Math.floor(E.Dc));
  for (let i = 0; i <= reach; i++) E.r[i] = Math.min(30, E.r[i] + M.ERl * k);
  if (E.maskH > 0) E.maskH = Math.max(0, E.maskH - M.ERmask * k);
  else E.gateLoss = Math.min(100, E.gateLoss + M.ERv * 0.9 * k);
  // 晶圆上已经刻穿的面积：刻蚀速率从中心 (1+u) 到边缘 (1-u)，按面积均匀分布
  const s = (1 + M.u - 100 / Math.max(1e-6, M.ERv / 60 * E.t)) / (2 * M.u);
  E.uncleared = 1 - clamp(s, 0, 1);
}

// 光谱终点：等离子体本身有一点底光；刻多晶硅时含硅产物的谱线和刻蚀速率成正比。
// plasma 0~1（辉光强度），etching 是否在刻，noise 是加在原始信号上的噪声（网页用随机数，标准答案用 0）。
// 返回这一帧的原始信号；刚判到终点时 E.tEp 从 null 变成当时的 E.t
export function oesTick(E, M, dt, plasma, etching, noise = 0) {
  const amp = 0.86 * clamp(M.ERv / 150, 0.15, 1);
  const target = plasma > 0 ? plasma * 0.12 + (etching ? amp * E.uncleared : 0) : 0;
  const oes = target + (plasma > 0 ? noise : 0);
  E.oesF = lerp(E.oesF, oes, Math.min(1, dt * 3));
  if (etching && E.tEp === null && E.t > 3 && E.oesF < 0.12 + amp * 0.5) E.tEp = E.t;
  return oes;
}

// 主刻最多等多久（秒），到时还没终点就算"没刻完"
export const MAIN_TIMEOUT = 180;

// 跑完一片后的 5 项判定（文字在 RESULT_TEXT 里，同样的顺序）
export function evaluate(E) {
  const rmax = Math.max(...E.r);
  const residue = E.De < 99.9;
  return {
    rmax, residue,
    ok: [!E.timeout && !residue, rmax <= 6, E.ox >= 2 && E.si === 0, E.maskH >= 10, E.tMain <= 120],
  };
}

// 只算刻蚀那一段（主刻到终点 + 过刻），固定步长、没有噪声：给 export_core.mjs 出标准答案，C++ 版逐行对照。
// 起辉以后等离子体已经稳定（plasma = 1），光谱滤波值从底光 0.12 开始。
export function simulateEtch(R, dt = 0.05) {
  const M = model(R);
  if (M.problem) return { M, problemCode: M.problemCode };
  const E = newEtch();
  E.oesF = 0.12;
  while (E.tEp === null && E.t <= MAIN_TIMEOUT) {
    etchTick(E, M, dt);
    oesTick(E, M, dt, 1, true, 0);
  }
  if (E.tEp === null) E.timeout = true;
  E.tMain = E.t;
  const tOver = E.timeout ? 0 : E.tMain * R.oe / 100;
  for (let t = 0; t + 1e-9 < tOver; t += dt) {
    etchTick(E, M, dt);
    oesTick(E, M, dt, 1, true, 0);
  }
  return { M, E, res: evaluate(E) };
}

// ================= 讲解文字 =================
// 讲解里的 {名字} 换成配方 / 模型里的数：fillText(text, { ...R, valve, Ei, oeSec })
export const fillText = (t, v) => t.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));

// 15 步：现在在干什么（now）、为什么（why）。过刻蚀那步在主刻超时的时候用 nowTimeout
export const STEP_TEXT = [
  { name: '打开晶圆盒', now: '晶圆盒放在装载口上，盒门和设备的门对接后一起打开。',
    why: '晶圆一直关在盒子里，开门也是对着设备里的洁净空间开，不接触车间空气里的颗粒。' },
  { name: '取片、对准', now: 'EFEM 里的大气机械手从盒里取出这一片，放到对准器上转一圈，找晶圆边上的缺口（notch）。',
    why: '让每片晶圆都以同样的方向、正好居中地进腔。' },
  { name: '放进负载锁', now: '负载锁现在是大气压。外门打开，机械手把晶圆放到里面的支撑针上，关门。',
    why: '负载锁是大气和真空之间的"过渡间"，两扇门永远不会同时打开。' },
  { name: '负载锁抽真空', now: '把负载锁从 760 Torr（一个大气压）抽到约 0.1 Torr。',
    why: '传输腔和工艺腔一直是真空。每次只抽这个小腔，几十秒就好，也不会把空气和水汽带进去。' },
  { name: '送进工艺腔', now: '内门打开，真空机械手取片；工艺腔闸阀打开，机械手伸进去，三根升降针把晶圆接过去；机械手退出，关闸阀，针降下，晶圆落到卡盘上。',
    why: '机械手的叉子托在晶圆下面，所以要靠升降针"接力"，叉子才抽得出来。' },
  { name: '吸附晶圆、通背氦', now: '卡盘里的电极加上约 1200 V 高压（估计值），静电把晶圆吸平；晶圆背面通氦气，约 10 Torr。',
    why: '真空里没有空气导热。背面的氦气把晶圆的热传给通着冷却液的卡盘，晶圆温度才控得住。' },
  { name: '通气、稳压', now: '质量流量计按配方通入 Cl₂ {cl2} / HBr {hbr} / O₂ {o2} sccm；摆阀关到约 {valve}%，把腔压稳在 {P} mTorr。',
    why: '气压低，离子一路上很少撞到别的分子，打下来的方向更直；气压高，自由基多，但方向性变差。' },
  { name: '起辉', now: '线圈加 {Ws} W、13.56 MHz 射频，电磁场穿过陶瓷窗把气体电离，腔里亮起来。匹配器自动调谐，反射功率很快降到接近 0。',
    why: '源功率只决定等离子体有多"浓"（离子和自由基有多少），基本不决定离子打下来有多猛。' },
  { name: '主刻蚀（到终点）', now: '卡盘加 {Wb} W 偏压，晶圆上方形成一层"鞘层"，离子被加速到约 {Ei} eV，垂直打下来；氯自由基和离子一起，把多晶硅变成 SiCl₄ 气体抽走。光谱仪盯着含硅产物的谱线，刻穿时谱线变暗，就是终点。',
    why: '离子负责"往下打"，自由基负责"化学反应"，两个一起比各自单干快得多，而且主要往下刻（各向异性）。' },
  { name: '过刻蚀', now: '到终点后按配方再刻 {oe}%（约 {oeSec} 秒），把边缘刻得慢的地方清干净。', nowTimeout: '主刻了 180 秒还没到终点，不再等了。',
    why: '晶圆中间和边缘的刻蚀速率差几个百分点。这时下面的栅氧已经露出来，靠 HBr / O₂ 带来的高选择比，栅氧几乎不被刻。' },
  { name: '关射频、停气', now: '关掉偏压和源功率，等离子体熄灭；停气，摆阀全开，把腔抽回本底真空。',
    why: '先把残留的腐蚀性气体抽干净，等会儿开闸阀时才不会跑进传输腔。' },
  { name: '去吸附', now: '抽掉背面的氦气，关掉卡盘高压，等残余电荷放掉。',
    why: '电荷没放干净就顶升降针，晶圆可能会跳片甚至碎掉。' },
  { name: '传出到负载锁', now: '升降针顶起晶圆，闸阀打开，真空机械手伸到晶圆下面接走，送回负载锁。',
    why: '和送进来是反过来的动作。' },
  { name: '负载锁回大气', now: '往负载锁里充氮气，从 0.1 Torr 回到 760 Torr。',
    why: '充的是干燥氮气而不是空气：晶圆表面还带着少量氯，碰到水汽会腐蚀。' },
  { name: '放回晶圆盒', now: '外门打开，大气机械手把刻好的晶圆放回原来的槽，关上盒门。',
    why: '一盒 25 片就这样一片接一片地跑；几个工艺腔可以同时各刻一片。' },
];

export const EXPLAIN = {
  ready: ['准备好了', '晶圆盒里又放了一片新的晶圆。可以先到"配方"里改参数，再点"开始"。', '每次只改一两个参数，对比结果最容易看出它的作用。'],
  badRecipe: ['配方检查没通过', '{problem}到"配方"里改一下再开始。'],
  done: ['完成', '晶圆已经放回晶圆盒。结果在弹窗里；关掉弹窗还能看左下角的剖面和曲线。'],
};

// 结果 5 项（顺序和 evaluate().ok 一样）
export const RESULT_TEXT = [
  { label: '多晶硅刻干净了', hint: '过刻不够：中间先刻穿就判了终点，边缘还没刻完。过刻一般给 20~40%。', hintTimeout: '主刻 180 秒还没到终点：偏压太低，离子没力气，氯几乎刻不动多晶硅。' },
  { label: '侧壁直（钻蚀 ≤ 6 nm）', hint: '往侧面刻掉太多：加 HBr / O₂ 保护侧壁，降低气压或温度。' },
  { label: '栅氧保住了（剩 ≥ 2 nm）', hint: '偏压太高，离子太猛，对栅氧的选择比下降；或者过刻太长。' },
  { label: '光刻胶还有余量（≥ 10 nm）', hint: '光刻胶被打光了，栅极顶部也被刻掉：偏压太高或 O₂ 太多。' },
  { label: '刻得够快（主刻 ≤ 120 秒）', hint: '太慢，产量低：加源功率或偏压。' },
];
export const VERDICT = { ok: '合格：这片晶圆的栅极刻得很好 ✓', bad: '有 {n} 项不合格' };

// 反应腔粒子动画的图例（示意，数量和速度不是真实比例）
export const PARTICLE_NAMES = {
  gas: '气体分子（Cl₂ / HBr）', e: '电子', ion: '离子（Cl⁺ 等）', rad: '自由基（Cl·）', prod: '产物 SiCl₄',
};

// 趋势图的曲线
export const SERIES_TEXT = [
  { k: 'llP', name: '负载锁', unit: 'Torr' },
  { k: 'chP', name: '腔压', unit: 'mTorr' },
  { k: 'srcF', name: '源功率', unit: 'W' },
  { k: 'srcR', name: '反射功率', unit: 'W' },
  { k: 'biasF', name: '偏压', unit: 'W' },
  { k: 'oes', name: '光谱（含硅产物）', unit: '' },
];

// ================= 零件 =================
// [id, 子系统, 名字, 作用]
export const PART_INFO = [
  ['foup', '整机', '晶圆盒（FOUP）', '一盒最多 25 片晶圆，前门密封。晶圆在厂里搬来搬去时一直关在盒子里，不接触车间空气。'],
  ['loadport', '整机', '装载口', '放晶圆盒的台子。自动对位，把盒门和设备的门对接后一起打开。'],
  ['efem', '整机', 'EFEM 前端模块', '大气压下的洁净小房间。顶上的风机过滤单元（FFU）一直往下吹洁净空气，颗粒落不到晶圆上。'],
  ['atmrobot', '整机', '大气机械手', '在晶圆盒、对准器、负载锁之间搬晶圆。'],
  ['aligner', '整机', '对准器', '转动晶圆，找到边上的缺口（notch），让每片晶圆以同样的方向、居中地进腔。'],
  ['loadlock', '整机', '负载锁 ×2', '大气和真空之间的"过渡间"。两扇门永远不会同时打开；每次只抽这个小腔，几十秒就好，也不会把空气带进真空。'],
  ['vtm', '整机', '真空传输腔', '一直保持真空。中间的真空机械手把晶圆送到各个工艺腔。'],
  ['vtmrobot', '整机', '真空机械手', '在真空里工作的双连杆机械手，通过闸阀进出工艺腔和负载锁。'],
  ['pm23', '整机', '工艺腔 PM2 / PM3', '和 PM1 同型号。几个腔可以同时各刻一片晶圆，提高产量。'],
  ['rack', '整机', '射频电源和控制柜', '13.56 MHz 射频电源、腔体控制器都装在这里。'],
  ['coil', '工艺腔 · 源', '平面线圈', '通 13.56 MHz 射频电流，交变磁场在腔里感应出电场，把电子加速、撞电离气体分子（电感耦合，ICP）。功率越大，等离子体越浓。分内外两组，调两组的功率比可以调中心和边缘的均匀性。'],
  ['window', '工艺腔 · 源', '陶瓷介质窗', '让线圈的电磁场透进腔里，同时把气体和等离子体挡在里面。用氧化铝陶瓷：不导电、耐腐蚀。'],
  ['rfcover', '工艺腔 · 源', '射频屏蔽罩', '罩住线圈，不让射频辐射到外面。'],
  ['srcmatch', '工艺腔 · 源', '源匹配器', '里面有两个可变电容，自动调到"阻抗匹配"，让电源的功率都送进等离子体，反射回来的接近 0。'],
  ['nozzle', '工艺腔 · 源', '中心进气喷嘴', '工艺气体从陶瓷窗中心喷进腔里。'],
  ['chamber', '工艺腔 · 腔体', '腔体', '铝做的真空容器，内壁有耐等离子体涂层（如氧化钇），减少腐蚀和掉颗粒。'],
  ['liner', '工艺腔 · 腔体', '内衬', '可以拆下来的保护套。脏了整个换下来清洗，不用清洗腔体本身。消耗件。'],
  ['baffle', '工艺腔 · 腔体', '约束环（挡板）', '把等离子体限制在晶圆上方，气体从缝隙流向下面的排气口。'],
  ['slit', '工艺腔 · 腔体', '闸阀', '工艺腔和传输腔之间的门。刻蚀时关着，腐蚀性气体跑不到传输腔里。'],
  ['oes', '工艺腔 · 腔体', '观察窗 + 光谱仪（OES）', '一直看着等离子体发的光。多晶硅刻穿时，含硅产物的谱线会突然变暗，用它判断"终点"。'],
  ['cmg', '工艺腔 · 腔体', '真空计（电容薄膜规）', '测腔压，读数和气体种类无关。摆阀按它的读数调开度。'],
  ['esc', '工艺腔 · 卡盘', '静电卡盘', '陶瓷里埋着电极，加高压用静电把晶圆吸平；底座通冷却液控温，晶圆背面通氦气导热。它也是下电极，偏压从这里加上去。'],
  ['edgering', '工艺腔 · 卡盘', '边缘环', '套在晶圆外圈，让晶圆边缘上方的电场和中间一样平，边缘也能刻直。会被等离子体慢慢吃掉，是消耗件。'],
  ['insring', '工艺腔 · 卡盘', '绝缘环', '石英做的，把带射频的卡盘和接地的腔体隔开。'],
  ['pins', '工艺腔 · 卡盘', '升降针 ×3', '把晶圆顶起来，机械手的叉子才能伸到晶圆下面接送。'],
  ['biasmatch', '工艺腔 · 卡盘', '偏压匹配器', '把偏压射频送到卡盘上。偏压决定离子打到晶圆上的能量。'],
  ['pendulum', '工艺腔 · 排气', '摆阀', '一块会摆动的阀板，调节抽气口开多大，把腔压稳在设定值。'],
  ['turbo', '工艺腔 · 排气', '分子泵', '转子每分钟几万转，把气体分子"打"向出口，把腔抽到高真空。后面还接着干泵和尾气处理（在楼下）。'],
  ['gasbox', '工艺腔 · 气路', '气体盒', '每路气体一个质量流量计（MFC），精确控制流量；还有阀门和过滤器。'],
  ['frame', '工艺腔 · 腔体', '机架', '铝型材机架，底下是可调高度的调平脚。升降针的气缸也装在机架上。'],
  ['lines', '工艺腔 · 卡盘', '冷却水管、高压线、背氦管', '蓝管进、红管出，冷却液流过卡盘底座里的水道把热带走；红色细线是卡盘的吸附高压；不锈钢细管送背面氦气。'],
  ['wafer', '晶圆', '晶圆', '300 mm 硅片，上面是 4 nm 栅氧 + 100 nm 多晶硅，再上面是 60 nm 宽的光刻胶线条。刻完剩下的多晶硅就是晶体管的栅极。'],
];
