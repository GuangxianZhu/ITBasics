/* ============================================================================
   1 · 零件建模（全部按图纸尺寸手写：DN80 对夹式蝶阀 + 齿轮齿条单作用执行器）
   ========================================================================== */
const assembly = new T.Group();
scene.add(assembly);

const PARTS = [];   // 零件定义（含说明文字）
const MESHES = [];  // 参与拾取与包围盒计算的网格

function part(def) {
  const d = { insts: [], ...def };
  PARTS.push(d);
  return d;
}
/* 把一组几何注册成一个零件实例；ex = 爆炸位移 [x,y,z,延迟] */
/* 爆炸位移按轴分别缩放：横向拉开、纵向收一点，让画面更像工程爆炸图而不是一根竖条 */
const EX_X = 1.06;
const EX_Y = 0.88;
const EX_Z = 1.2;
function place(def, g, ex = [], opts = {}) {
  assembly.add(g);
  const rec = {
    g,
    part: def,
    ex: ex.map((e) => ({ v: new V3(e[0] * EX_X, e[1] * EX_Y, e[2] * EX_Z), s: e[3] == null ? 0 : e[3] })),
    base: g.position.clone(),
    baseRot: g.rotation.y,
    ...opts,
  };
  def.insts.push(rec);
  g.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      o.userData.part = def;
      MESHES.push(o);
    }
  });
  return rec;
}

/* ------------------------------------------------------------------ 尺寸 */
const R_BORE = 40;      // 衬里内径（DN80）
const R_LINER = 47;     // 衬里外径 = 阀体孔径
const R_OD = 78;        // 阀体最大外径
const FACE = 23;        // 阀体半宽（对夹面）
const Y_NECK0 = 62;     // 阀颈起点
const Y_NECK1 = 110;    // 阀颈顶面
const YA = 122;         // 执行器安装面
const Y_MID = 156;      // 缸体 / 齿轮中心
const Y_TOP = 190;      // 缸体顶面
const CYL = 52;         // 缸体半长（Z）
const CAPT = 13;        // 端盖厚
const PIST_T = 18;      // 活塞厚
const STROKE = 18;      // 活塞行程
const PZ0 = 8;          // 全关时活塞内端面 z
const RACK_X = 15;      // 齿条中心 x
const GEAR_R = 11.6;    // 齿轮齿顶

const cyl = (r, h, seg = 48) => new T.CylinderGeometry(r, r, h, seg);
const cylX = (r, h, x, seg = 48) => cyl(r, h, seg).rotateZ(Math.PI / 2).translate(x, 0, 0);
const cylZ = (r, h, z, seg = 48) => cyl(r, h, seg).rotateX(Math.PI / 2).translate(0, 0, z);

/* ========================================================== 1 阀体 */
const P_BODY = part({
  no: 1, cn: "阀体", en: "BODY", jp: "ボデー",
  mat: "球墨铸铁 GGG40 · 环氧涂层", qty: 1,
  desc: "对夹式阀体，被两片管道法兰夹住。中间的通孔是介质通道，上部铸出阀颈和 ISO 5211 F05 安装平台，执行器直接坐在平台上，阀杆从阀颈中穿过。",
});
place(
  P_BODY,
  group(
    [latheX(lathe([[R_LINER, -FACE], [R_OD, -FACE, 1.8], [R_OD, FACE, 1.8], [R_LINER, FACE]], { segments: 128, radius: 1.2 })), "body"],
    [lathe([[13, Y_NECK0], [27, Y_NECK0, 1.4], [27, Y_NECK1, 1.4], [13, Y_NECK1]], { segments: 72, radius: 1, closed: true }), "body"],
    [
      extrudeY(
        (() => {
          const s = roundRectShape(31, 31, 6);
          for (const [x, y] of [[17.7, 17.7], [-17.7, 17.7], [-17.7, -17.7], [17.7, -17.7]]) s.holes.push(circlePath(x, y, 3.4));
          s.holes.push(circlePath(0, 0, 13));
          return s;
        })(),
        12, Y_NECK1, 1,
      ),
      "body",
    ],
    [lathe([[13.6, -84], [19, -84, 1], [19, -58, 1], [13.6, -58]], { segments: 64, radius: 0.9, closed: true }), "bodyDark"],
  ),
);

/* ========================================================== 2 阀座衬圈 */
const P_SEAT = part({
  no: 2, cn: "阀座衬圈", en: "SEAT LINER", jp: "シートライナー",
  mat: "EPDM", qty: 1,
  desc: "整圈橡胶衬里，同时充当两端法兰的密封垫。蝶板压在衬里内壁上形成软密封，所以这种阀门只适合常温水、暖通和弱腐蚀介质。",
});
place(
  P_SEAT,
  group([
    latheX(
      lathe(
        [[R_BORE, -25], [52, -25, 1], [52, -FACE, 0.5], [R_LINER, -FACE], [R_LINER, FACE], [52, FACE, 0.5], [52, 25, 1], [R_BORE, 25]],
        { segments: 128, radius: 0.9 },
      ),
    ),
    "epdm",
  ]),
  [[168, 0, 0, 0.1]],
);

/* ========================================================== 3 蝶板 */
const P_DISC = part({
  no: 3, cn: "蝶板", en: "DISC", jp: "弁体",
  mat: "CF8M 不锈钢 · 电解抛光", qty: 1,
  desc: "圆盘形阀芯，绕阀杆转 90°：盘面与流向平行即全开，垂直即全关。盘缘做成球面，转动时会刮过橡胶衬里，把附着物带走。",
});
{
  const plate = latheX(
    lathe(
      [[0, -7], [30, -7], [36.5, -6.4, 1], [39.2, -4.8, 1], [39.2, 4.8, 1], [36.5, 6.4, 1], [30, 7], [0, 7]],
      { segments: 96, radius: 1.1, closed: false },
    ),
  );
  const hub = extrudeY(roundRectShape(11, 11, 2.4), 46, -23, 1.4, 12);
  const keyway = new T.BoxGeometry(5, 2, 5).translate(0, 22.4, 0);
  place(P_DISC, group([plate, "mirror"], [hub, "mirror"], [keyway, "hole"]), [[-192, 0, 0, 0.18]], { rot: 1 });
}

/* ========================================================== 4 / 5 阀杆 */
const P_STEM = part({
  no: 4, cn: "上阀杆", en: "STEM", jp: "ステム",
  mat: "17-4PH 沉淀硬化不锈钢", qty: 1,
  desc: "把执行器的扭矩送进阀内。中段轴肩被阀体内部台肩挡住，介质压力再高也顶不出去（防吹出结构）；顶端方头插进齿轮轴。",
});
{
  const shaft = lathe(
    [[0, 22], [6.5, 22, 0.5], [6.5, 80, 0.6], [10.5, 80, 0.6], [10.5, 86, 0.6], [6.5, 86, 0.6], [6.5, 132], [0, 132]],
    { segments: 56, radius: 0.6, closed: false },
  );
  const drive = extrudeY(roundRectShape(6, 6, 0.8), 26, 108, 0.8);
  place(P_STEM, group([shaft, "ss"], [drive, "ss"]), [[0, 176, 0, 0.26]], { rot: 1 });
}

const P_LSTEM = part({
  no: 5, cn: "下阀杆", en: "LOWER STEM", jp: "下部ステム",
  mat: "17-4PH 不锈钢", qty: 1,
  desc: "阀杆的下支点。蝶板上下都有支承，转动时不会偏摆，衬里磨损也更均匀。",
});
place(
  P_LSTEM,
  group([
    lathe(
      [[0, -26], [6.5, -26, 0.5], [6.5, -56, 0.5], [10, -56, 0.5], [10, -62, 0.5], [6.5, -62, 0.5], [6.5, -86], [0, -86]],
      { segments: 56, radius: 0.6, closed: false },
    ),
    "ss",
  ]),
  [[0, -156, 0, 0.22]],
);

/* ========================================================== 6 轴套 */
const P_BUSH = part({
  no: 6, cn: "轴套", en: "BUSHING", jp: "ブッシュ",
  mat: "PTFE 复合铜背衬", qty: 2,
  desc: "上下各一个，承受阀杆传来的径向力，同时把钢对钢的摩擦换成自润滑摩擦，操作扭矩能降一半。",
});
place(P_BUSH, group([lathe([[6.8, 96], [12.5, 96, 0.5], [12.5, 108, 0.5], [6.8, 108]], { segments: 56, radius: 0.5, closed: true }), "ptfe"]), [[0, 112, 0, 0.28]]);
place(P_BUSH, group([lathe([[6.8, -78], [13.4, -78, 0.5], [13.4, -66, 0.5], [6.8, -66]], { segments: 56, radius: 0.5, closed: true }), "ptfe"]), [[0, -112, 0, 0.28]]);

/* ========================================================== 7 O 形圈 */
const P_ORING = part({
  no: 7, cn: "O 形圈", en: "O-RING", jp: "Oリング",
  mat: "NBR 70 Shore A", qty: 2,
  desc: "阀杆处的第一道密封：拦住沿阀杆往上爬的介质，防止从阀颈泄漏到执行器里。",
});
place(P_ORING, group([new T.TorusGeometry(8.4, 1.5, 12, 40).rotateX(Math.PI / 2).translate(0, 90, 0), "nbr"]), [[0, 140, 0, 0.3]]);
place(P_ORING, group([new T.TorusGeometry(8.4, 1.5, 12, 40).rotateX(Math.PI / 2).translate(0, 94, 0), "nbr"]), [[0, 128, 0, 0.3]]);

/* ========================================================== 8 止推垫片 */
const P_WASHER = part({
  no: 8, cn: "止推垫片", en: "THRUST WASHER", jp: "スラストワッシャ",
  mat: "PTFE", qty: 1,
  desc: "夹在阀杆轴肩与阀体之间，把轴向的压紧力变成低摩擦的端面滑动。",
});
place(P_WASHER, group([lathe([[6.8, 86], [13, 86, 0.3], [13, 88, 0.3], [6.8, 88]], { segments: 56, radius: 0.3, closed: true }), "ptfe"]), [[0, 100, 0, 0.26]]);

/* ========================================================== 9 执行器缸体 */
const P_CYL = part({
  no: 9, cn: "执行器缸体", en: "CYLINDER BODY", jp: "シリンダボデー",
  mat: "A6063 铝型材 · 硬质阳极氧化", qty: 1,
  desc: "铝挤压缸体，内孔就是气缸。两侧装端盖、中间穿出齿轮轴；侧面按 NAMUR 标准布置气口，可以直接贴装电磁阀。",
});
{
  const barrelShape = roundRectShape(30, 34, 14, 0, Y_MID);
  const barrel = extrudeZ(barrelShape, CYL * 2, -CYL, 1.4, 44);
  const pad = extrude(roundRectShape(18, 18, 5, 0, Y_MID), 8, 0.8).rotateY(Math.PI / 2).translate(34, 0, 0);
  const topPad = extrudeY(roundRectShape(16, 16, 4), 4, Y_TOP - 1, 0.6);
  place(
    P_CYL,
    group(
      [barrel, "alu"],
      [pad, "aluDark"],
      [topPad, "aluDark"],
      [cylX(3.2, 1.6, 41.8).translate(0, Y_MID, 0), "hole"],
      [cylX(3.2, 1.6, 41.8).translate(0, Y_MID - 28, 0), "hole"],
    ),
    [[0, 186, 0, 0.14]],
  );
}

/* ========================================================== 10 端盖 */
const P_CAP = part({
  no: 10, cn: "执行器端盖", en: "END CAP", jp: "エンドキャップ",
  mat: "ADC12 压铸 · 粉末喷涂", qty: 2,
  desc: "封住气缸两端，内侧是弹簧的支承面，中心装行程调节螺钉。拆下它就能抽出活塞、更换密封件。",
});
function buildCap(dir) {
  const s = roundRectShape(30, 34, 14, 0, Y_MID);
  for (const [x, y] of [[22, 26], [-22, 26], [-22, -26], [22, -26]]) s.holes.push(circlePath(x, Y_MID + y, 2.8));
  s.holes.push(circlePath(0, Y_MID - 24, 4.2));
  const plate = extrudeZ(s, CAPT, CYL, 1.4, 44);
  const spigot = cylZ(31, 9, CYL - 5, 64);
  const ring = new T.TorusGeometry(29.6, 1.5, 10, 64).translate(0, 0, CYL - 10);
  const g = group([plate, "blue"], [spigot, "aluDark"], [ring, "nbr"]);
  if (dir < 0) g.rotation.y = Math.PI;
  return g;
}
place(P_CAP, buildCap(1), [[0, 186, 232, 0.2]]);
place(P_CAP, buildCap(-1), [[0, 186, -232, 0.2]]);

/* ========================================================== 11 活塞齿条 */
const P_PIST = part({
  no: 11, cn: "活塞（带齿条）", en: "PISTON + RACK", jp: "ピストン（ラック）",
  mat: "ADC12 + NBR 密封圈", qty: 2,
  desc: "活塞与齿条做成一体。两只活塞相对运动，齿条分别咬在齿轮两侧，于是直线推力变成 90° 转角——这就是齿轮齿条执行器的全部秘密。",
});
function buildPiston() {
  const body = latheZ(lathe([[0, 0], [29, 0, 1.2], [29, PIST_T, 1.2], [0, PIST_T]], { segments: 64, radius: 1, closed: false }));
  const oring = new T.TorusGeometry(29, 1.5, 10, 64).translate(0, 0, 2.6);
  const guide = latheZ(lathe([[28.3, 13], [30.3, 13, 0.3], [30.3, 16.4, 0.3], [28.3, 16.4]], { segments: 64, radius: 0.3, closed: true }));
  const rack = new T.BoxGeometry(6, 16, 30).translate(RACK_X, Y_MID, -7);
  const teeth = [];
  for (let i = 0; i < 8; i++) teeth.push(new T.BoxGeometry(4, 14.6, 1.9).translate(RACK_X - 4, Y_MID, -20 + i * 3.73));
  return group([body, "aluDark"], [oring, "nbr"], [guide, "nbr"], [rack, "aluDark"], ...teeth.map((t) => [t, "aluDark"]));
}
{
  const a = buildPiston();
  a.position.set(0, 0, PZ0);
  place(P_PIST, a, [[0, 186, 124, 0.22]], { slide: 1 });
  const b = buildPiston();
  b.rotation.y = Math.PI;
  b.position.set(0, 0, -PZ0);
  place(P_PIST, b, [[0, 186, -124, 0.22]], { slide: -1 });
}

/* ========================================================== 12 齿轮轴 */
const P_PINION = part({
  no: 12, cn: "齿轮轴", en: "PINION", jp: "ピニオン",
  mat: "合金钢 · 镀镍", qty: 1,
  desc: "执行器的输出轴。下端方孔接阀杆方头，中间是和齿条啮合的齿轮，顶端扁槽按 NAMUR 标准做阀位指示或限位开关接口。",
});
{
  const shaft = lathe(
    [[0, YA - 6], [7, YA - 6, 0.6], [7, Y_MID - 14, 0.6], [7, Y_TOP + 12], [0, Y_TOP + 12]],
    { segments: 56, radius: 0.6, closed: false },
  );
  const gear = extrudeY(gearShape(16, 8.6, GEAR_R, 7), 26, Y_MID - 13, 0.7, 8);
  const slot = new T.BoxGeometry(9, 3.4, 3.4).translate(0, Y_TOP + 10.2, 0);
  place(P_PINION, group([shaft, "nickel"], [gear, "nickel"], [slot, "hole"]), [[0, 292, 0, 0.28]], { rot: 1 });
}

/* ========================================================== 13 复位弹簧 */
const P_SPRING = part({
  no: 13, cn: "复位弹簧", en: "RETURN SPRING", jp: "リターンスプリング",
  mat: "60Si2Mn 磷化", qty: 4,
  desc: "单作用执行器的储能元件。通气时被压缩；一旦断气或断电，它把活塞推回中间，阀门自动回到关闭位——这就是“失气关”（FC）。",
});
const SPR_L0 = 26;
const springGeo = helixGeo(5, 6.5, SPR_L0, 1.8);
function placeSpring(x, dir, ex) {
  const g = new T.Group();
  g.add(new T.Mesh(springGeo, mat("spring")));
  g.position.set(x, Y_MID, dir * (PZ0 + PIST_T));
  if (dir < 0) g.rotation.y = Math.PI;
  place(P_SPRING, g, ex, { spring: dir });
}
placeSpring(24, 1, [[0, 186, 172, 0.24]]);
placeSpring(-24, 1, [[0, 186, 172, 0.24]]);
placeSpring(24, -1, [[0, 186, -172, 0.24]]);
placeSpring(-24, -1, [[0, 186, -172, 0.24]]);

/* ========================================================== 14 端盖螺钉 */
const P_SCREW = part({
  no: 14, cn: "端盖螺钉", en: "CAP SCREW", jp: "キャップボルト",
  mat: "SUS304 M5 × 22", qty: 8,
  desc: "内六角圆柱头螺钉，每个端盖 4 颗，按对角顺序拧紧，避免端盖被压歪、活塞偏磨。",
});
function screwZ(zFace, dir) {
  const head = cylZ(4.4, 5, zFace + dir * 2.5, 32);
  const shaft = cylZ(2.5, 22, zFace - dir * 11, 24);
  const socket = cylZ(2.2, 1.8, zFace + dir * 4.6, 6);
  return group([head, "zinc"], [shaft, "zinc"], [socket, "hole"]);
}
for (const [x, y] of [[22, 26], [-22, 26], [-22, -26], [22, -26]]) {
  const a = screwZ(CYL + CAPT, 1);
  a.position.set(x, Y_MID + y, 0);
  place(P_SCREW, a, [[0, 186, 268, 0.26]]);
  const b = screwZ(-(CYL + CAPT), -1);
  b.position.set(x, Y_MID + y, 0);
  place(P_SCREW, b, [[0, 186, -268, 0.26]]);
}

/* ========================================================== 15 行程调节螺钉 */
const P_STOP = part({
  no: 15, cn: "行程调节螺钉", en: "STROKE STOP", jp: "ストローク調整ボルト",
  mat: "SUS304 M8 × 30", qty: 2,
  desc: "限制活塞的行程终点，可以把 0° 和 90° 两个位置各微调几度，让蝶板与管道对得更正。",
});
function stopScrew(dir) {
  const head = extrudeZ(hexShape(14, 4.2), 7, 0, 0.5).translate(0, 0, dir * (CYL + CAPT));
  const shaft = cylZ(4, 26, dir * (CYL + CAPT - 8), 24);
  const g = group([head, "zinc"], [shaft, "zinc"]);
  if (dir < 0) g.rotation.y = Math.PI;
  return g;
}
place(P_STOP, stopScrew(1), [[0, 186, 292, 0.3]]);
place(P_STOP, stopScrew(-1), [[0, 186, -292, 0.3]]);

/* ========================================================== 16 位置指示器 */
const P_IND = part({
  no: 16, cn: "位置指示器", en: "POSITION INDICATOR", jp: "開度インジケータ",
  mat: "PA66 + 色标", qty: 1,
  desc: "装在齿轮轴顶端，随轴一起转。红色箭头与管道平行是开，转到垂直是关——现场不接线也能一眼看出阀位。",
});
{
  const arrow = new T.Shape();
  arrow.moveTo(-4, -2.4); arrow.lineTo(9, -2.4); arrow.lineTo(9, -6.4);
  arrow.lineTo(18, 0); arrow.lineTo(9, 6.4); arrow.lineTo(9, 2.4); arrow.lineTo(-4, 2.4);
  const g = new T.Group();
  g.add(new T.Mesh(extrudeY(roundRectShape(16, 12, 4, -3, 0), 3, 0, 0.6), mat("black")));
  g.add(new T.Mesh(extrudeY(arrow, 1.8, 3.1, 0.4), mat("red")));
  g.add(new T.Mesh(lathe([[0, 0], [7.4, 0, 0.4], [7.4, 3.4, 0.4], [0, 3.4]], { segments: 40, radius: 0.4, closed: false }), mat("nickel")));
  g.position.set(0, Y_TOP + 12, 0);
  place(P_IND, g, [[0, 186, 0, 0.12], [0, 116, 0, 0.32]], { rot: 1 });
}

/* ========================================================== 17 电磁阀 */
const P_SOL = part({
  no: 17, cn: "电磁阀", en: "SOLENOID VALVE", jp: "電磁弁",
  mat: "铝合金阀体 + NBR 密封", qty: 1,
  desc: "NAMUR 贴面安装的二位五通阀。通电时把压缩空气送进执行器中间腔，断电时把中间腔接排气口——一套电信号就完成了“开 / 关”。",
});
{
  const bodyG = extrudeZ(roundRectShape(17, 18, 4, 55, Y_MID), 40, -20, 1.2);
  place(P_SOL, group([bodyG, "aluDark"], [cylX(3, 1.8, 38.6), "hole"]), [[0, 186, 0, 0.16], [152, 0, 0, 0.3]]);
}

/* ========================================================== 18 线圈 */
const P_COIL = part({
  no: 18, cn: "线圈", en: "SOLENOID COIL", jp: "ソレノイドコイル",
  mat: "24 V DC · 6 W", qty: 1,
  desc: "通电产生电磁力推动阀芯换向。外壳上带手动应急按钮，调试时不给电也能捅一下试阀。",
});
{
  const g = new T.Group();
  g.add(new T.Mesh(cylX(15, 22, 83, 40).translate(0, Y_MID, 0), mat("coil")));
  g.add(new T.Mesh(cylX(9.4, 5, 72.6, 24).translate(0, Y_MID, 0), mat("nickel")));
  g.add(new T.Mesh(cylX(6, 3.4, 95.6, 24).translate(0, Y_MID, 0), mat("black")));
  place(P_COIL, g, [[0, 186, 0, 0.16], [226, 0, 0, 0.34]]);
}

/* ========================================================== 19 消声器 */
const P_MUFF = part({
  no: 19, cn: "消声器", en: "SILENCER", jp: "サイレンサ",
  mat: "烧结青铜", qty: 2,
  desc: "拧在电磁阀的排气口上。多孔青铜把排气的啸叫压下去，顺便挡住灰尘从排气口吸进阀内。",
});
for (const dir of [1, -1]) {
  const g = group(
    [cylZ(5, 9, dir * 24.5, 32).translate(64, Y_MID - 10, 0), "brass"],
    [cylZ(6, 2.4, dir * 30.2, 32).translate(64, Y_MID - 10, 0), "brass"],
  );
  place(P_MUFF, g, [[0, 186, 0, 0.16], [124, 0, dir * 86, 0.3]]);
}

/* ========================================================== 20 快插接头 */
const P_FIT = part({
  no: 20, cn: "快插接头", en: "PUSH-IN FITTING", jp: "ワンタッチ継手",
  mat: "黄铜镀镍 + PBT", qty: 1,
  desc: "Φ8 气管插进去就被卡爪锁住，按下蓝色释放环即可拔出。装在电磁阀的进气口上。",
});
{
  const x = 55, z = 0;
  const g = group(
    [cyl(6.4, 8, 32).translate(x, Y_MID + 21, z), "nickel"],
    [cyl(5.2, 16, 32).translate(x, Y_MID + 31, z), "nickel"],
    [cyl(6.6, 5, 32).translate(x, Y_MID + 27, z), "sealBlue"],
    [cyl(3.4, 22, 20).translate(x, Y_MID + 31, z), "hole"],
  );
  place(P_FIT, g, [[0, 186, 0, 0.16], [158, 58, 0, 0.32]]);
}

/* ========================================================== 21 电磁阀螺钉 */
const P_VSCREW = part({
  no: 21, cn: "电磁阀螺钉", en: "MOUNTING SCREW", jp: "取付ねじ",
  mat: "SUS304 M5 × 30", qty: 2,
  desc: "把电磁阀压在 NAMUR 界面上，中间夹着 O 形圈对准两个气口。",
});
for (const z of [13, -13]) {
  const g = group(
    [cylX(4.2, 5, 74.6, 32).translate(0, Y_MID + 22, 0), "zinc"],
    [cylX(2.5, 26, 60, 24).translate(0, Y_MID + 22, 0), "zinc"],
  );
  g.position.z = z;
  place(P_VSCREW, g, [[0, 186, 0, 0.16], [168, 0, z * 3.4, 0.32]]);
}
