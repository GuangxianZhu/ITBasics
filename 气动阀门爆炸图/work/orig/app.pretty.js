;(() => {
  var fe = document.getElementById("c"),
    mn = new Dr({ canvas: fe, antialias: !0, alpha: !0, preserveDrawingBuffer: !1 })
  mn.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  mn.outputColorSpace = Ne
  mn.toneMapping = Mc
  mn.toneMappingExposure = 1
  mn.shadowMap.enabled = !0
  mn.shadowMap.type = vc
  mn.setClearColor(0, 0)
  var yi = new Qi(),
    m_ = new ji(mn)
  yi.environment = m_.fromScene(new ro(), 0.04).texture
  yi.environmentIntensity = 0.95
  var _e = new Ce(32, 1, 2, 8e3),
    Zn = new so(_e, fe)
  Zn.enableDamping = !0
  Zn.dampingFactor = 0.08
  Zn.minDistance = 120
  Zn.maxDistance = 3e3
  var Ln = new Is(16777215, 2.1)
  Ln.castShadow = !0
  Ln.shadow.mapSize.set(2048, 2048)
  Object.assign(Ln.shadow.camera, { left: -430, right: 430, top: 430, bottom: -430, near: 10, far: 1600 })
  Ln.shadow.bias = -4e-4
  Ln.shadow.normalBias = 0.5
  yi.add(Ln, Ln.target)
  var jh = new Is(14674175, 0.7)
  jh.position.set(-300, 220, -320)
  yi.add(jh)
  var co = new ie(new Ki(6e3, 6e3).rotateX(-Math.PI / 2), new Wr({ opacity: 0.22 }))
  co.receiveShadow = !0
  yi.add(co)
  var ho = (i, t) => new j(i, t)
  function g_(i, t, e = !1) {
    let n = i.length,
      s = []
    for (let r = 0; r < n; r++) {
      let o = i[r],
        a = o[2] !== void 0 ? o[2] : t
      if ((!e && (r === 0 || r === n - 1)) || a <= 0) {
        s.push([o[0], o[1]])
        continue
      }
      let c = i[(r - 1 + n) % n],
        l = i[(r + 1) % n],
        h = c[0] - o[0],
        u = c[1] - o[1],
        d = Math.hypot(h, u),
        f = l[0] - o[0],
        g = l[1] - o[1],
        _ = Math.hypot(f, g),
        m = Math.min(a, d * 0.45, _ * 0.45)
      ;(s.push([o[0] + (h / d) * m, o[1] + (u / d) * m]), s.push([o[0] + (f / _) * m, o[1] + (g / _) * m]))
    }
    return (e && s.push(s[0]), s)
  }
  var __ = (i) => i.slice(0, -1).map((t, e) => [t, i[e + 1]])
  function Xc(i, t = 72) {
    let e = []
    for (let n of i) {
      if (n.length < 2 || n.every((r) => r[0] <= 1e-6)) continue
      let s = n.map((r) => ho(Math.max(0, r[0]), r[1]))
      ;(s.length === 2 && s[0].distanceTo(s[1]) < 1e-6) || e.push(new kr(s, t))
    }
    return Gh(e)
  }
  var le = (i, t = 0.7, e = !1, n = 72) => Xc(__(g_(i, t, e)), n),
    We = (i) => i.rotateZ(-Math.PI / 2),
    ao = (i) => i.rotateX(Math.PI / 2)
  function Te(i, t, e = 0.6, n = 36) {
    let s = new Vr(i, {
      depth: Math.max(t - 2 * e, 0.01),
      bevelEnabled: e > 0,
      bevelThickness: e,
      bevelSize: e,
      bevelOffset: -e,
      bevelSegments: 1,
      curveSegments: n,
      steps: 1,
    })
    return (s.translate(0, 0, e), Wh(s, 0.55))
  }
  var Dn = (i, t) => i.rotateY(Math.PI / 2).translate(t, 0, 0),
    $n = (i, t) => i.rotateX(-Math.PI / 2).translate(0, t, 0)
  function as(i, t, e) {
    let n = new ts()
    return (n.absarc(i, t, e, 0, Math.PI * 2, !0), n)
  }
  function Qh(i, t, e) {
    let n = new $e()
    return (
      n.moveTo(-i + e, -t),
      n.lineTo(i - e, -t),
      n.absarc(i - e, -t + e, e, -Math.PI / 2, 0),
      n.lineTo(i, t - e),
      n.absarc(i - e, t - e, e, 0, Math.PI / 2),
      n.lineTo(-i + e, t),
      n.absarc(-i + e, t - e, e, Math.PI / 2, Math.PI),
      n.lineTo(-i, -t + e),
      n.absarc(-i + e, -t + e, e, Math.PI, Math.PI * 1.5),
      n
    )
  }
  function Jn(i, t = 0, e = 0) {
    let n = i / Math.sqrt(3),
      s = []
    for (let o = 0; o < 6; o++) {
      let a = e + (o * Math.PI) / 3
      s.push(ho(n * Math.cos(a), n * Math.sin(a)))
    }
    let r = new $e(s)
    return (t > 0 && r.holes.push(as(0, 0, t)), r)
  }
  function Vs(i, t, e, n) {
    let s = 0.6 * n,
      r = Math.min(0.8, i * 0.25),
      o = []
    o.push(
      [
        [0, t],
        [i - r, t],
      ],
      [
        [i - r, t],
        [i, t + r],
      ],
    )
    let a = []
    for (let c = t + r; c < t + e - r - n * 0.5; c += n) a.push([i, c], [i - s, c + n / 2])
    return (
      a.push([i, t + e - r]),
      o.push(a),
      o.push(
        [
          [i, t + e - r],
          [i - r, t + e],
        ],
        [
          [i - r, t + e],
          [0, t + e],
        ],
      ),
      Xc(o, 24)
    )
  }
  var tu = [
      [24, 24],
      [-24, 24],
      [-24, -24],
      [24, -24],
    ],
    x_ = (() => {
      let n = (o, a) => {
          let c = Math.hypot(o, a) - 31
          for (let [l, h] of tu) {
            let u = Math.hypot(o - l, a - h) - 8.6,
              d = Math.max(6 - Math.abs(c - u), 0) / 6
            c = Math.min(c, u) - (d * d * 6) / 4
          }
          return c
        },
        s = []
      for (let o = 0; o < 220; o++) {
        let a = (o / 220) * Math.PI * 2,
          c = Math.cos(a),
          l = Math.sin(a),
          h = 0,
          u = 60
        for (let d = 0; d < 30; d++) {
          let f = (h + u) / 2
          n(f * c, f * l) < 0 ? (h = f) : (u = f)
        }
        s.push(ho(h * c, h * l))
      }
      return s
    })()
  function eu(i) {
    let t = new $e(x_)
    for (let [e, n] of tu) t.holes.push(as(e, n, 4.6))
    return (t.holes.push(as(0, 0, i)), t)
  }
  function y_(i, t, e) {
    let n = []
    for (let s = 0; s < i; s++) {
      let r = (s / i) * Math.PI * 2,
        o = (Math.PI * 2) / i
      for (let [a, c] of [
        [0, t],
        [0.14, t],
        [0.34, e],
        [0.5, e],
        [0.7, t],
      ])
        n.push(ho(c * Math.cos(r + o * a), c * Math.sin(r + o * a)))
    }
    return new $e(n)
  }
  var Oc = class extends Be {
      constructor(t, e, n, s, r, o) {
        ;(super(), Object.assign(this, { len: t, rc: e, turns: n, oy: s, oz: r, dir: o }))
      }
      getPoint(t, e = new A()) {
        let n = this.turns,
          s = t * n,
          r = 0.85,
          o = Math.min(1, Math.max(0, (s - r) / (n - 2 * r))),
          a = s * Math.PI * 2
        return e.set(
          this.dir * (1.3 + o * (this.len - 2.6)),
          this.oy + this.rc * Math.cos(a),
          this.oz + this.rc * Math.sin(a),
        )
      }
    },
    v_ = {
      cast: { color: 12830668, metalness: 1, roughness: 0.42 },
      sus: { color: 13159633, metalness: 1, roughness: 0.3 },
      mirror: { color: 15790837, metalness: 1, roughness: 0.05 },
      ptfe: { color: 15921386, metalness: 0, roughness: 0.62, sheen: 0.3, sheenColor: 16777215 },
      alu: { color: 12041669, metalness: 0.9, roughness: 0.4 },
      aluCast: { color: 11120825, metalness: 0.85, roughness: 0.52 },
      aluDark: { color: 9344415, metalness: 0.85, roughness: 0.45 },
      blue: { color: 1855150, metalness: 0.12, roughness: 0.42, clearcoat: 0.45, clearcoatRoughness: 0.3 },
      zinc: { color: 11843774, metalness: 1, roughness: 0.28 },
      black: { color: 2500910, metalness: 0.55, roughness: 0.4 },
      rubber: { color: 1184274, metalness: 0, roughness: 0.75 },
      wear: { color: 14208425, metalness: 0, roughness: 0.6 },
      brass: { color: 11832405, metalness: 1, roughness: 0.58 },
      coil: { color: 1776929, metalness: 0, roughness: 0.36, clearcoat: 0.6, clearcoatRoughness: 0.25 },
      gray: { color: 7041402, metalness: 0, roughness: 0.55 },
      yellow: { color: 15843630, metalness: 0, roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.2 },
      red: { color: 13777450, metalness: 0, roughness: 0.38, clearcoat: 0.4 },
      nickel: { color: 13817306, metalness: 1, roughness: 0.22 },
      spring: { color: 3093563, metalness: 0.6, roughness: 0.36 },
      hole: { color: 526603, metalness: 0, roughness: 0.95 },
      fblue: { color: 2782932, metalness: 0, roughness: 0.42 },
    },
    M_ = (i) => new Xr({ ...v_[i], side: sn }),
    uo = new dn()
  yi.add(uo)
  var xi = [],
    Hs = [],
    gn = [0, 150, 0, 0.16]
  function te(i, t, e, n, s, r) {
    let o = { no: i, cn: t, jp: e, m: n, qty: s, desc: r, inst: [] }
    return (xi.push(o), o)
  }
  function Kt(...i) {
    let t = new dn()
    for (let [e, n] of i) t.add(new ie(e, M_(n)))
    return t
  }
  function vi(i) {
    let t = new dn()
    return ((i.rotation.y = Math.PI), t.add(i), t)
  }
  function jt(i, t, e = [], n = {}) {
    uo.add(t)
    let s = { g: t, ex: e.map((r) => ({ v: new A(r[0], r[1], r[2]), s: r[3] })), ...n }
    return (
      i.inst.push(s),
      t.traverse((r) => {
        r.isMesh && ((r.castShadow = r.receiveShadow = !0), (r.userData.part = i), Hs.push(r))
      }),
      s
    )
  }
  var ge = 88,
    S_ = 13,
    b_ = te(
      1,
      "阀体",
      "ボデー",
      "SUS316 (CF8M) 精铸",
      1,
      "三片式球阀的中间体，承受管道压力。顶部铸出阀颈和 ISO 5211 F05 安装平台，执行器直接坐在上面。",
    )
  jt(
    b_,
    Kt(
      [Dn(Te(eu(22), 60, 1.2), -30), "cast"],
      [
        le(
          [
            [6.5, 22],
            [18, 22, 0],
            [18, 46],
            [13, 46],
            [13, 36],
            [6.5, 36],
          ],
          0.8,
          !0,
        ),
        "cast",
      ],
      [
        $n(
          Te(
            (() => {
              let i = Qh(30, 30, 8)
              for (let t of [-1, 1]) for (let e of [-1, 1]) i.holes.push(as(17.7 * t, 17.7 * e, 3.4))
              return (i.holes.push(as(0, 0, 16)), i)
            })(),
            10,
            1,
          ),
          46,
        ),
        "cast",
      ],
    ),
  )
  var E_ = te(
    2,
    "端盖",
    "エンドキャップ",
    "SUS316",
    2,
    "两端的管道连接件（内螺纹 Rc1）。内侧凸台压住阀座，拆下 4 根螺柱就能把阀芯整体抽出维修，这就是三片式的好处。",
  )
  for (let i of [1, -1]) {
    let t = Kt(
      [Dn(Te(eu(12.5), 10, 1), 30), "cast"],
      [Dn(Te(Jn(41, 12.5, 0), 24, 1.2), 40), "cast"],
      [
        We(
          le(
            [
              [19.6, 22],
              [21.8, 22],
              [21.8, 30],
              [19.6, 30],
            ],
            0.5,
            !0,
          ),
        ),
        "cast",
      ],
    )
    jt(E_, i > 0 ? t : vi(t), [[105 * i, 0, 0, 0.28]])
  }
  var T_ = te(
    3,
    "球体",
    "ボール",
    "SUS316 镜面抛光",
    1,
    "带通孔的球。通孔与管道同轴时全开，绕阀杆转 90\xB0 后实心面挡住流道即全关。表面抛光是为了和 PTFE 阀座贴合得更紧。",
  )
  {
    let e = Math.sqrt(243.75),
      n = []
    for (let r = 0; r <= 60; r++) {
      let o = -e + (2 * e * r) / 60
      n.push([Math.sqrt(Math.max(0, 20 * 20 - o * o)), o])
    }
    let s = We(
      Xc(
        [
          n,
          [
            [12.5, e],
            [12.5, -e],
          ],
        ],
        128,
      ),
    )
    jt(T_, Kt([s, "mirror"]), [[0, -85, 0, 0.7]], { rot: !0 })
  }
  var w_ = te(
    4,
    "阀座",
    "シート",
    "PTFE",
    2,
    "软密封环。内侧锥面贴住球面，靠介质压力和端盖预紧把球压实，实现“零泄漏”关断。",
  )
  for (let i of [1, -1]) {
    let t = Kt([
      We(
        le(
          [
            [12.6, 16],
            [16, 12.9],
            [19.5, 14.4],
            [19.5, 22],
            [12.6, 22],
          ],
          0.4,
          !0,
          96,
        ),
      ),
      "ptfe",
    ])
    jt(w_, i > 0 ? t : vi(t), [[48 * i, 0, 0, 0.48]])
  }
  var A_ = te(
    5,
    "阀体垫片",
    "ボデーガスケット",
    "PTFE",
    2,
    "夹在阀体与端盖之间的密封圈，防止介质从中缝漏出。",
  )
  for (let i of [1, -1]) {
    let t = Kt([
      We(
        le(
          [
            [23, 28],
            [27, 28],
            [27, 30],
            [23, 30],
          ],
          0.3,
          !0,
          96,
        ),
      ),
      "ptfe",
    ])
    jt(A_, i > 0 ? t : vi(t), [[70 * i, 0, 0, 0.38]])
  }
  var R_ = te(6, "双头螺柱", "スタッドボルト", "SUS304 M8", 4, "贯穿两个端盖和阀体，把三片夹成一体。")
  for (let [i, t] of [
    [-24, 24],
    [24, 24],
    [24, -24],
    [-24, -24],
  ])
    jt(R_, Kt([We(Vs(4, 0, 100, 1.25)).translate(-50, t, i), "zinc"]), [[210, 0, 0, 0.18]])
  var C_ = te(
    7,
    "六角螺母",
    "六角ナット",
    "SUS304 M8",
    8,
    "两端各 4 个，按对角顺序均匀拧紧，避免端盖歪斜导致阀座受力不均。",
  )
  for (let i of [1, -1])
    for (let [t, e] of [
      [-24, 24],
      [24, 24],
      [24, -24],
      [-24, -24],
    ])
      jt(C_, Kt([Dn(Te(Jn(13, 4.1, 0), 6.5, 0.8), i > 0 ? 40 : -46.5).translate(0, e, t), "zinc"]), [
        [i > 0 ? 232 : -160, 0, 0, 0.1],
      ])
  var P_ = te(
    8,
    "阀杆",
    "ステム",
    "SUS316",
    1,
    "把执行器的扭矩传给球体。下端扁榫插进球体槽口；台肩从阀体内侧顶住，压力再高也不会被顶飞（防飞出结构）。",
  )
  {
    let i = new $e(),
      t = Math.acos(4.5 / 6),
      e = Math.sqrt(36 - 20.25)
    ;(i.moveTo(4.5, -e),
      i.lineTo(4.5, e),
      i.absarc(0, 0, 6, t, Math.PI - t),
      i.lineTo(-4.5, -e),
      i.absarc(0, 0, 6, Math.PI + t, Math.PI * 2 - t),
      jt(
        P_,
        Kt(
          [
            le(
              [
                [0, 20],
                [6, 20],
                [6, 24],
                [9, 24],
                [9, 27.5],
                [6, 27.5],
                [6, 58],
                [0, 58],
              ],
              0.6,
            ),
            "sus",
          ],
          [$n(Te(i, 14, 0.5), 58), "sus"],
          [new Ge(15, 6, 5.5, 2, 0.8).translate(0, 17, 0), "sus"],
        ),
        [[0, 40, 0, 0.54]],
        { rot: !0 },
      ))
  }
  var I_ = te(
    9,
    "止推垫片",
    "スラストワッシャ",
    "PTFE",
    1,
    "垫在阀杆台肩上方，减小转动摩擦，同时是第一道阀杆密封。",
  )
  jt(
    I_,
    Kt([
      le(
        [
          [6.3, 27.5],
          [11, 27.5],
          [11, 29.5],
          [6.3, 29.5],
        ],
        0.3,
        !0,
      ),
      "ptfe",
    ]),
    [[0, 28, 0, 0.6]],
  )
  var L_ = te(
    10,
    "阀杆填料",
    "ステムパッキン",
    "PTFE V 形",
    2,
    "V 形截面，被轴向压紧后唇口张开贴住阀杆，是阀杆处的主密封。",
  )
  for (let [i, t, e] of [
    [38, 64, 0.46],
    [41.5, 70, 0.44],
  ])
    jt(
      L_,
      Kt([
        le(
          [
            [6.2, i + 1.2],
            [9.35, i],
            [12.5, i + 1.2],
            [12.5, i + 3.5],
            [9.35, i + 2.3],
            [6.2, i + 3.5],
          ],
          0.2,
          !0,
        ),
        "ptfe",
      ]),
      [[0, t, 0, e]],
    )
  var D_ = te(11, "填料压盖", "パッキン押え", "SUS304", 1, "把螺母的压紧力均匀传到填料上。")
  jt(
    D_,
    Kt([
      le(
        [
          [6.3, 45],
          [12.7, 45],
          [12.7, 47],
          [15, 47],
          [15, 49.5],
          [6.3, 49.5],
        ],
        0.4,
        !0,
      ),
      "sus",
    ]),
    [[0, 80, 0, 0.4]],
  )
  var nu = te(
    12,
    "碟形弹簧",
    "皿ばね",
    "SUS631",
    2,
    "两片对扣串联。填料磨损变薄时，碟簧回弹补偿，压紧力不会掉，减少日常补拧。",
  )
  jt(
    nu,
    Kt([
      le(
        [
          [6.5, 50.5],
          [12, 49.5],
          [12, 50.2],
          [6.5, 51.2],
        ],
        0.2,
        !0,
      ),
      "zinc",
    ]),
    [[0, 90, 0, 0.36]],
  )
  jt(
    nu,
    Kt([
      le(
        [
          [6.5, 51.2],
          [12, 52.2],
          [12, 52.9],
          [6.5, 51.9],
        ],
        0.2,
        !0,
      ),
      "zinc",
    ]),
    [[0, 95, 0, 0.34]],
  )
  var U_ = te(
    13,
    "阀杆螺母",
    "ステムナット",
    "SUS304 M12 薄型",
    1,
    "压紧碟簧和填料。拧得过紧会让操作扭矩变大，执行器选型时要算进去。",
  )
  jt(U_, Kt([$n(Te(Jn(19, 6.1, Math.PI / 6), 3.1, 0.5), 52.9), "zinc"]), [[0, 105, 0, 0.3]])
  var N_ = te(
    14,
    "连接轴套",
    "カップリング",
    "S45C 镀镍",
    1,
    "外方内扁：把阀杆的双扁头转接到执行器齿轮轴的方孔，让不同厂家的阀和执行器能配在一起。",
  )
  jt(N_, Kt([new Ge(15, 14, 15, 2, 1.2).translate(0, 63, 0), "nickel"]), [[0, 120, 0, 0.22]], { rot: !0 })
  var F_ = te(
    15,
    "安装螺栓",
    "取付ボルト",
    "SUS304 M6",
    4,
    "从阀体平台下方穿上来，拧进执行器底部螺孔。F05 法兰的螺孔分布圆直径 50 mm。",
  )
  for (let i of [-1, 1])
    for (let t of [-1, 1])
      jt(
        F_,
        Kt(
          [$n(Te(Jn(10, 0, Math.PI / 6), 5, 0.6), 41).translate(17.7 * i, 0, 17.7 * t), "zinc"],
          [Vs(3, 46, 18, 1).translate(17.7 * i, 0, 17.7 * t), "zinc"],
        ),
        [[0, -9, 0, 0.2]],
      )
  var O_ = te(
    16,
    "执行器缸体",
    "シリンダボデー",
    "A6063 硬质阳极氧化",
    1,
    "铝型材缸体。内腔是活塞的气缸；侧面是 NAMUR 标准接口，可直接安装电磁阀；顶面平台可装限位开关盒。",
  )
  {
    let i = (() => {
        let o = new $e()
        ;(o.moveTo(-27, -32),
          o.lineTo(27, -32),
          o.absarc(27, -23, 9, -Math.PI / 2, 0),
          o.lineTo(36, 23),
          o.absarc(27, 23, 9, 0, Math.PI / 2))
        for (let a of [16, -16])
          (o.lineTo(a + 2.6, 32), o.lineTo(a + 1.6, 29.8), o.lineTo(a - 1.6, 29.8), o.lineTo(a - 2.6, 32))
        return (
          o.lineTo(-27, 32),
          o.absarc(-27, 23, 9, Math.PI / 2, Math.PI),
          o.lineTo(-36, -23),
          o.absarc(-27, -23, 9, Math.PI, Math.PI * 1.5),
          o.holes.push(as(0, 0, 27)),
          o
        )
      })(),
      t = (n, s, r) => new es(n, 48).rotateX(r ? -Math.PI / 2 : Math.PI / 2).translate(0, s, 0),
      e = (n) => new es(2.8, 32).translate(n, ge, 36.08)
    jt(
      O_,
      Kt(
        [Dn(Te(i, 140, 1.5), -70).translate(0, ge, 0), "alu"],
        [new Ge(80, 3.6, 32, 2, 1.2).translate(0, 121.8, 0), "alu"],
        [t(9.7, 123.65, !0), "hole"],
        [t(8.6, 55.9, !1), "hole"],
        [e(-12), "hole"],
        [e(12), "hole"],
      ),
      [gn],
    )
  }
  var B_ = te(
    17,
    "齿轮轴",
    "ピニオン",
    "合金钢 镀镍",
    1,
    "整台执行器的输出轴。两根齿条从两侧咬住它，活塞走直线、它就转圈；顶端扁槽是 NAMUR 标准，用来带动指示器或限位开关。",
  )
  jt(
    B_,
    Kt(
      [
        le(
          [
            [0, 70],
            [8, 70],
            [8, 104],
            [9, 104],
            [9, 134],
            [0, 134],
          ],
          0.8,
        ),
        "nickel",
      ],
      [$n(Te(y_(16, 11.2, 15.2), 28, 0.5), 76), "nickel"],
      [new Ge(14, 1.2, 3.6, 2, 0.4).translate(0, 134.3, 0), "hole"],
    ),
    [gn, [0, 75, 0, 0.56]],
    { rot: !0 },
  )
  var z_ = te(
    18,
    "活塞（带齿条）",
    "ピストン（ラック）",
    "ADC12 + NBR O 形圈",
    2,
    "头部装有 O 形圈（密封）和导向环（防偏磨），后面伸出齿条。两只活塞反向移动，齿条分别在齿轮两侧，于是直线推力变成 90\xB0 转动。",
  )
  for (let i of [1, -1]) {
    let t = []
    for (let n = 0; n < 9; n++)
      t.push([new Ge(2.6, 22, 4.2, 2, 0.6).translate(-19 + n * 5.1, ge, 13), "aluCast"])
    let e = Kt(
      [
        We(
          le(
            [
              [0, 26],
              [26.5, 26],
              [26.5, 48],
              [0, 48],
            ],
            0.9,
          ),
        ).translate(0, ge, 0),
        "aluCast",
      ],
      [new Hr(26.3, 1.25, 14, 96).rotateY(Math.PI / 2).translate(41, ge, 0), "rubber"],
      [
        We(
          le(
            [
              [26.35, 31],
              [26.8, 31],
              [26.8, 35],
              [26.35, 35],
            ],
            0.15,
            !0,
          ),
        ).translate(0, ge, 0),
        "wear",
      ],
      [new Ge(48, 22, 8, 2, 1).translate(2, ge, 19), "aluCast"],
      ...t,
    )
    jt(z_, i > 0 ? e : vi(e), [gn, [85 * i, 0, 0, 0.48]], { slide: -i })
  }
  var k_ = te(
    19,
    "复位弹簧",
    "リターンスプリング",
    "60Si2Mn 涂层",
    6,
    "每侧 3 根。通气时被活塞压缩储能；一旦断气，它们把活塞推回中间，阀门自动关闭，这就是“失气关”（FC）。",
  )
  for (let i of [1, -1])
    for (let t of [90, 210, 330]) {
      let e = (t * Math.PI) / 180,
        n = ge + 12 * Math.sin(e),
        s = 12 * Math.cos(e) * i
      jt(
        k_,
        Kt([new Gr(new Oc(28, 6.4, 7, n, s, i), 420, 1.3, 10, !1), "spring"]),
        [gn, [115 * i, 0, 0, 0.4]],
        { spring: i },
      )
    }
  var V_ = te(
    20,
    "执行器端盖",
    "エンドキャップ",
    "ADC12 粉末喷涂",
    2,
    "封住气缸两端，内侧托住弹簧。外侧中央是行程调节螺钉。",
  )
  for (let i of [1, -1]) {
    let t = Kt(
      [Dn(Te(Qh(36, 32, 10), 14, 1.6), 70).translate(0, ge, 0), "blue"],
      [
        We(
          le(
            [
              [0, 84],
              [9.5, 84],
              [9.5, 85.6],
              [0, 85.6],
            ],
            0.4,
          ),
        ).translate(0, ge, 0),
        "blue",
      ],
    )
    jt(V_, i > 0 ? t : vi(t), [gn, [150 * i, 0, 0, 0.32]])
  }
  var H_ = te(21, "端盖螺钉", "キャップボルト", "SCM435 发黑 M5", 8, "内六角圆柱头螺钉，每个端盖 4 颗。")
  for (let i of [1, -1])
    for (let [t, e] of [
      [28, 24],
      [-28, 24],
      [-28, -24],
      [28, -24],
    ]) {
      let n = Kt(
        [
          We(
            le(
              [
                [0, 84],
                [4, 84],
                [4, 89],
                [0, 89],
              ],
              0.6,
            ),
          ).translate(0, ge + e, t),
          "black",
        ],
        [Dn(Te(Jn(4, 0, 0), 0.4, 0), 89.02).translate(0, ge + e, t), "hole"],
        [We(Vs(2.5, 64, 20, 0.8)).translate(0, ge + e, t), "black"],
      )
      jt(H_, i > 0 ? n : vi(n), [gn, [195 * i, 0, 0, 0.26]])
    }
  var G_ = te(
    22,
    "行程调节螺钉",
    "ストローク調整ボルト",
    "SUS304 M8",
    2,
    "顶住活塞的行程终点，可以把 0\xB0 和 90\xB0 两个终点各微调约 \xB15\xB0，让球孔和管道对得更正。",
  )
  for (let i of [1, -1]) {
    let t = Kt(
      [Dn(Te(Jn(13, 4.1, 0), 5, 0.7), 86).translate(0, ge, 0), "zinc"],
      [We(Vs(4, 0, 26, 1.25)).translate(72, ge, 0), "zinc"],
      [new Ge(0.8, 8, 1.6, 1, 0.2).translate(98.1, ge, 0), "hole"],
    )
    jt(G_, i > 0 ? t : vi(t), [gn, [150 * i, 0, 0, 0.32], [25 * i, 0, 0, 0.3]])
  }
  var W_ = te(23, "卡簧", "止め輪", "弹簧钢", 1, "卡在齿轮轴的环槽里，限制齿轮轴的上下窜动。")
  {
    let i = new $e(),
      t = 0.35
    ;(i.absarc(0, 0, 11.5, t, Math.PI * 2 - t, !1),
      i.absarc(0, 0, 9.2, Math.PI * 2 - t, t, !0),
      jt(W_, Kt([$n(Te(i, 1.2, 0.25), 124.1), "black"]), [gn, [0, 62, 0, 0.5]], { rot: !0 }))
  }
  var X_ = te(
    24,
    "位置指示器",
    "開度インジケータ",
    "PA66 + 色标",
    1,
    "装在齿轮轴顶端随轴转动。红色箭头与管道平行表示开，转到垂直表示关，现场一眼就能看出阀位。",
  )
  {
    let i = new $e()
    ;(i.moveTo(-13, -2.6),
      i.lineTo(5, -2.6),
      i.lineTo(5, -7),
      i.lineTo(14, 0),
      i.lineTo(5, 7),
      i.lineTo(5, 2.6),
      i.lineTo(-13, 2.6),
      jt(
        X_,
        Kt(
          [
            le(
              [
                [0, 134],
                [17, 134],
                [17, 138],
                [0, 138],
              ],
              0.6,
            ),
            "black",
          ],
          [
            le(
              [
                [0, 138],
                [16, 138],
                [16, 146],
                [0, 146],
              ],
              1.2,
            ),
            "yellow",
          ],
          [$n(Te(i, 1.8, 0.3), 146), "red"],
        ),
        [gn, [0, 100, 0, 0]],
        { rot: !0 },
      ))
  }
  var Gs = [gn, [0, 0, 85, 0.06]],
    Y_ = te(
      25,
      "电磁阀",
      "電磁弁",
      "铝合金阀体 + 24 V DC 线圈",
      1,
      "NAMUR 安装的二位三通电磁阀。线圈通电，压缩空气进入执行器中间腔；断电，中间腔经消声器排气，弹簧关阀。",
    )
  {
    let i = Dn(Te(Jn(12, 0, 0), 3, 0.5), 60).translate(0, 89, 50)
    jt(
      Y_,
      Kt(
        [new Ge(60, 26, 22, 2, 1.6).translate(0, ge, 47), "aluDark"],
        [new Ge(28, 32, 28, 3, 2.4).translate(46, 89, 50), "coil"],
        [
          We(
            le(
              [
                [0, 29.5],
                [5, 29.5],
                [5, 32.5],
                [0, 32.5],
              ],
              0.3,
            ),
          ).translate(0, 89, 50),
          "nickel",
        ],
        [i, "nickel"],
        [
          le(
            [
              [0, 101],
              [3, 101],
              [3, 103.2],
              [0, 103.2],
            ],
            0.5,
          ).translate(-20, 0, 47),
          "red",
        ],
      ),
      Gs,
    )
  }
  var q_ = te(26, "线圈插头", "コネクタ", "DIN 43650 A 型", 1, "接线插头，压住线圈并引出电缆。")
  jt(
    q_,
    Kt(
      [new Ge(22, 22, 16, 3, 2).translate(46, 89, 72), "gray"],
      [
        ao(
          le(
            [
              [0, 80],
              [2.4, 80],
              [2.4, 80.8],
              [0, 80.8],
            ],
            0.3,
          ),
        ).translate(46, 89, 0),
        "nickel",
      ],
      [
        le(
          [
            [0, 70],
            [4.6, 70],
            [4.6, 78],
            [0, 78],
          ],
          0.6,
        ).translate(46, 0, 72),
        "gray",
      ],
    ),
    [...Gs, [0, 0, 35, 0.04]],
  )
  var Z_ = te(
    27,
    "消声器",
    "サイレンサ",
    "烧结青铜",
    2,
    "排气口的多孔青铜塞，降低排气噪声，也挡住灰尘进入阀内。",
  )
  for (let i of [ge - 6, ge + 6])
    jt(
      Z_,
      Kt([
        We(
          le(
            [
              [0, -30],
              [3.4, -30],
              [3.4, -32],
              [4.6, -32],
              [4.6, -40],
              [0, -40],
            ],
            0.6,
          ),
        ).translate(0, i, 47),
        "brass",
      ]),
      [...Gs, [-30, 0, 0, 0.04]],
    )
  var $_ = te(
    28,
    "快插接头",
    "ワンタッチ継手",
    "镀镍黄铜 + PBT",
    1,
    "Φ6 气管插进去就锁住，按下蓝色释放环可拔出。",
  )
  jt(
    $_,
    Kt(
      [
        le(
          [
            [0, 101],
            [4.6, 101],
            [4.6, 107],
            [5.2, 107],
            [5.2, 110.5],
            [0, 110.5],
          ],
          0.5,
        ).translate(8, 0, 47),
        "nickel",
      ],
      [
        le(
          [
            [3, 110.5],
            [5.5, 110.5],
            [5.5, 112.6],
            [3, 112.6],
          ],
          0.4,
          !0,
        ).translate(8, 0, 47),
        "fblue",
      ],
      [new es(3, 32).rotateX(-Math.PI / 2).translate(8, 112.62, 47), "hole"],
    ),
    [...Gs, [0, 25, 0, 0.04]],
  )
  var J_ = te(
    29,
    "电磁阀螺钉",
    "取付ねじ",
    "SUS304 M5",
    2,
    "把电磁阀固定在 NAMUR 接口上，中间夹着 O 形圈对准气口。",
  )
  for (let i of [-22, 22])
    jt(
      J_,
      Kt(
        [
          ao(
            le(
              [
                [0, 58],
                [4, 58],
                [4, 62],
                [0, 62],
              ],
              0.5,
            ),
          ).translate(i, ge, 0),
          "zinc",
        ],
        [ao($n(Te(Jn(4, 0, 0), 0.4, 0), 62.02)).translate(i, ge, 0), "hole"],
        [ao(Vs(2.5, 38, 20, 0.8)).translate(i, ge, 0), "zinc"],
      ),
      [...Gs, [0, 0, 40, 0.02]],
    )
  var iu = matchMedia("(prefers-reduced-motion: reduce)").matches,
    xt = {
      t: 1,
      tTarget: null,
      th: 0,
      thTarget: 0,
      labels: innerWidth >= 760,
      sel: null,
      hover: null,
      moved: !1,
    },
    su = (i) => (i < 0.5 ? 4 * i * i * i : 1 - Math.pow(-2 * i + 2, 3) / 2),
    K_ = (i, t) => su(Math.min(1, Math.max(0, (i - t * 0.6) / 0.4))),
    Ns = new A()
  function Bc() {
    let i = S_ * -xt.th
    for (let t of xi)
      for (let e of t.inst) {
        Ns.set(0, 0, 0)
        for (let n of e.ex) Ns.addScaledVector(n.v, K_(xt.t, n.s))
        ;(e.rot && (e.g.rotation.y = xt.th),
          e.slide && (Ns.x += e.slide * i),
          e.spring && ((Ns.x += e.spring * (48 - i)), (e.g.scale.x = (28 + i) / 28)),
          e.g.position.copy(Ns))
      }
  }
  var Yc = new Ze(),
    bx = new ui()
  function j_(i = Yc) {
    ;(uo.updateMatrixWorld(!0), i.makeEmpty())
    for (let t of Hs) i.expandByObject(t)
    return i
  }
  var Bs = document.getElementById("info"),
    Q_ = document.getElementById("ctrl"),
    Ex = document.querySelector(".left"),
    ks = document.getElementById("bom"),
    ve = { top: 0, bottom: 0, right: 0, left: 0 }
  function ru() {
    let i = fe.clientWidth,
      t = fe.clientHeight,
      e = i < 760,
      n = Q_.getBoundingClientRect(),
      s = document.getElementById("app").getBoundingClientRect(),
      r = Math.max(0, s.bottom - n.top)
    document.documentElement.style.setProperty("--ctrl-h", r + "px")
    let o = document.querySelector(".tb").getBoundingClientRect()
    if (((ve.bottom = r), (ve.top = e ? o.bottom - s.top + 6 : 0), e && !Bs.hidden)) {
      let a = Bs.getBoundingClientRect()
      ve.bottom = Math.max(ve.bottom, s.bottom - a.top + 6)
    }
    ;((ve.right = !ks.hidden && !e ? ks.offsetWidth + 16 : 0),
      (ve.left = !e && i >= 900 ? Math.min(i * 0.3, o.right - s.left + 8) : 0))
  }
  function ou() {
    let i = fe.clientWidth,
      t = fe.clientHeight
    _e.setViewOffset(i, t, (ve.right - ve.left) / 2, (ve.bottom - ve.top) / 2, i, t)
  }
  var au = new A(0.95, 0.58, 1.3).normalize(),
    Fs = null,
    zs = null
  function Xh(i) {
    let t = xt.t,
      e = fe.clientWidth,
      n = fe.clientHeight,
      s = i > 0.5 ? (xt.labels ? 46 : 22) : Math.min(64, e * 0.08),
      r = ve.left + s,
      o = e - ve.right - s,
      a = ve.top + s,
      c = n - ve.bottom - s
    ;((xt.t = i), Bc(), uo.updateMatrixWorld(!0))
    let l = [],
      h = new Ze(),
      u = new Ze()
    for (let m of Hs) {
      ;(m.geometry.boundingBox || m.geometry.computeBoundingBox(),
        h.copy(m.geometry.boundingBox).applyMatrix4(m.matrixWorld),
        u.union(h))
      for (let p of [h.min.x, h.max.x])
        for (let T of [h.min.y, h.max.y]) for (let S of [h.min.z, h.max.z]) l.push(new A(p, T, S))
    }
    ;((xt.t = t), Bc())
    let d = u.getCenter(new A()),
      f = u.getSize(new A()).length() * 1.6,
      g = new A(),
      _ = new A()
    for (let m = 0; m < 7; m++) {
      ;(_e.position.copy(d).addScaledVector(au, f),
        _e.lookAt(d),
        (_e.near = Math.max(2, f / 50)),
        (_e.far = f * 6),
        _e.updateProjectionMatrix(),
        _e.updateMatrixWorld())
      let p = 1 / 0,
        T = -1 / 0,
        S = 1 / 0,
        y = -1 / 0
      for (let b of l) {
        let [M, C] = Hc(b)
        ;((p = Math.min(p, M)), (T = Math.max(T, M)), (S = Math.min(S, C)), (y = Math.max(y, C)))
      }
      let N = Math.max((T - p) / Math.max(60, o - r), (y - S) / Math.max(60, c - a)),
        R = (2 * f * Math.tan(to.degToRad(_e.fov) / 2)) / n
      ;(g.setFromMatrixColumn(_e.matrixWorld, 0), _.setFromMatrixColumn(_e.matrixWorld, 1))
      let P = (p + T) / 2 - (r + o) / 2,
        L = (S + y) / 2 - (a + c) / 2
      ;(d.addScaledVector(g, P * R).addScaledVector(_, -L * R), (f *= N * 0.97))
    }
    return { target: d, dist: Math.max(f, 140), center: u.getCenter(new A()) }
  }
  function fo() {
    ;((Fs = Xh(0)),
      (zs = Xh(1)),
      cu(!0),
      Ln.position.copy(zs.center).add(new A(120, 600, 160)),
      Ln.target.position.copy(zs.center))
  }
  var Nc = new A()
  function cu(i) {
    if (!Fs || (xt.moved && !i)) return
    let t = su(Math.min(1, xt.t / 0.82))
    Nc.lerpVectors(Fs.target, zs.target, t)
    let e = Fs.dist + (zs.dist - Fs.dist) * t
    ;(Zn.target.copy(Nc),
      _e.position.copy(Nc).addScaledVector(au, e),
      (_e.near = Math.max(2, e / 50)),
      (_e.far = e * 6),
      _e.updateProjectionMatrix())
  }
  function zc() {
    ;(ru(), ou(), xt.moved || fo())
  }
  function lu() {
    let i = fe.clientWidth,
      t = fe.clientHeight
    ;(mn.setSize(i, t, !1), (_e.aspect = i / t), ru(), ou(), xt.moved ? _e.updateProjectionMatrix() : fo())
  }
  Zn.addEventListener("start", () => {
    xt.moved = !0
  })
  var Yh = "http://www.w3.org/2000/svg",
    kc = document.getElementById("leaders"),
    Vc = document.getElementById("balloons"),
    qn = xi.map((i) => {
      let t = document.createElement("button")
      ;((t.className = "bln"),
        (t.textContent = i.no),
        t.setAttribute("aria-label", `${i.no} ${i.cn}`),
        t.addEventListener("click", (s) => {
          ;(s.stopPropagation(), mo(i))
        }),
        Vc.appendChild(t))
      let e = document.createElementNS(Yh, "line"),
        n = document.createElementNS(Yh, "circle")
      return (
        n.setAttribute("r", "2"),
        kc.append(e, n),
        { p: i, b: t, ln: e, dot: n, x: 0, y: 0, ax: 0, ay: 0, init: !1 }
      )
    }),
    qh = new Ze(),
    oo = new A()
  function Hc(i) {
    return (
      oo.copy(i).project(_e),
      [((oo.x + 1) / 2) * fe.clientWidth, ((1 - oo.y) / 2) * fe.clientHeight, oo.z]
    )
  }
  function tx() {
    let i = xt.labels ? Math.min(1, Math.max(0, (xt.t - 0.55) / 0.25)) : 0
    if (
      ((Vc.style.opacity = kc.style.opacity = i),
      (Vc.style.visibility = kc.style.visibility = i > 0 ? "visible" : "hidden"),
      i <= 0)
    ) {
      for (let l of qn) l.init = !1
      return
    }
    let t = fe.clientWidth,
      e = fe.clientHeight,
      [n, s] = Hc(Yc.getCenter(new A()))
    for (let l of qn) {
      let h = l.p.inst[0]
      qh.makeEmpty().expandByObject(h.g)
      let [u, d] = Hc(qh.getCenter(new A()))
      ;((l.ax = u), (l.ay = d), (l.off = u < 0 || u > t - ve.right || d < ve.top || d > e - ve.bottom))
      let f = u - n,
        g = d - s,
        _ = Math.hypot(f, g) || 1
      ;((f /= _),
        (g /= _),
        (l.tx = u + f * 44),
        (l.ty = d + g * 40),
        l.init || ((l.x = l.tx), (l.y = l.ty)),
        (l.nx = l.x + (l.tx - l.x) * 0.5),
        (l.ny = l.y + (l.ty - l.y) * 0.5))
    }
    let r = 14,
      o = t - ve.right - 14,
      a = ve.top + 14,
      c = e - ve.bottom - 14
    for (let l = 0; l < 8; l++) {
      for (let h = 0; h < qn.length; h++)
        for (let u = h + 1; u < qn.length; u++) {
          let d = qn[h],
            f = qn[u]
          if (d.off || f.off) continue
          let g = f.nx - d.nx,
            _ = f.ny - d.ny,
            m = Math.hypot(g, _)
          if (m < 25) {
            m < 0.01 && ((g = 1), (_ = 0))
            let p = (25 - m) / 2 / (m || 1)
            ;((d.nx -= g * p), (d.ny -= _ * p), (f.nx += g * p), (f.ny += _ * p))
          }
        }
      for (let h of qn) ((h.nx = Math.min(o, Math.max(r, h.nx))), (h.ny = Math.min(c, Math.max(a, h.ny))))
    }
    for (let l of qn) {
      ;((l.x = l.nx),
        (l.y = l.ny),
        (l.init = !0),
        (l.b.hidden = l.off),
        (l.ln.style.display = l.dot.style.display = l.off ? "none" : ""),
        (l.b.style.transform = `translate(${l.x.toFixed(1)}px,${l.y.toFixed(1)}px)`))
      let h = l.x - l.ax,
        u = l.y - l.ay,
        d = Math.hypot(h, u) || 1,
        f = l.x - (h / d) * 11,
        g = l.y - (u / d) * 11
      ;(l.ln.setAttribute("x1", l.ax.toFixed(1)),
        l.ln.setAttribute("y1", l.ay.toFixed(1)),
        l.ln.setAttribute("x2", f.toFixed(1)),
        l.ln.setAttribute("y2", g.toFixed(1)),
        l.dot.setAttribute("cx", l.ax.toFixed(1)),
        l.dot.setAttribute("cy", l.ay.toFixed(1)))
      let _ = xt.sel === l.p
      ;(l.b.classList.toggle("sel", _), l.ln.classList.toggle("sel", _), l.dot.classList.toggle("sel", _))
    }
  }
  var Fc = new Ht()
  function po() {
    Fc.set(getComputedStyle(document.documentElement).getPropertyValue("--hl").trim() || "#d98e0b")
    for (let i of Hs) {
      let t = i.userData.part
      t === xt.sel
        ? (i.material.emissive.copy(Fc), (i.material.emissiveIntensity = 0.55))
        : t === xt.hover
          ? (i.material.emissive.copy(Fc), (i.material.emissiveIntensity = 0.22))
          : (i.material.emissiveIntensity = 0)
    }
  }
  function mo(i) {
    ;((xt.sel = i), po())
    for (let e of nx) e.el.classList.toggle("sel", e.p === i)
    let t = Bs.hidden
    if (!i) {
      ;((Bs.hidden = !0), (document.getElementById("hint").hidden = !1), !t && fe.clientWidth < 760 && zc())
      return
    }
    ;((document.getElementById("i-no").textContent = i.no),
      (document.getElementById("i-cn").textContent = i.cn),
      (document.getElementById("i-jp").textContent = i.jp),
      (document.getElementById("i-mat").textContent = i.m),
      (document.getElementById("i-qty").textContent = i.qty + " 件"),
      (document.getElementById("i-desc").textContent = i.desc),
      (Bs.hidden = !1),
      (document.getElementById("hint").hidden = !0),
      fe.clientWidth < 760 && (ks.hidden ? zc() : qc(!1)))
  }
  document.getElementById("i-close").addEventListener("click", () => mo(null))
  var Zh = new Jr(),
    $h = new j()
  function hu(i) {
    let t = fe.getBoundingClientRect()
    ;($h.set(((i.clientX - t.left) / t.width) * 2 - 1, -((i.clientY - t.top) / t.height) * 2 + 1),
      Zh.setFromCamera($h, _e))
    let e = Zh.intersectObjects(Hs, !1)[0]
    return e ? e.object.userData.part : null
  }
  var Os = null
  fe.addEventListener("pointerdown", (i) => {
    Os = { x: i.clientX, y: i.clientY }
  })
  fe.addEventListener("pointerup", (i) => {
    ;(Os && Math.hypot(i.clientX - Os.x, i.clientY - Os.y) < 6 && mo(hu(i)), (Os = null))
  })
  fe.addEventListener("pointermove", (i) => {
    if (i.pointerType !== "mouse" || i.buttons) return
    let t = hu(i)
    t !== xt.hover && ((xt.hover = t), po(), (fe.style.cursor = t ? "pointer" : ""))
  })
  fe.addEventListener("pointerleave", () => {
    xt.hover && ((xt.hover = null), po(), (fe.style.cursor = ""))
  })
  var ex = document.getElementById("bom-list")
  document.getElementById("bom-count").textContent =
    `${xi.length} 种 \xB7 ${xi.reduce((i, t) => i + t.qty, 0)} 件`
  var nx = xi.map((i) => {
      let t = document.createElement("button")
      return (
        (t.className = "row"),
        (t.type = "button"),
        (t.innerHTML = `<span class="n">${i.no}</span><span class="nm">${i.cn}<span>${i.jp}</span></span><span class="q">\xD7${i.qty}</span><span class="m">${i.m}</span>`),
        t.addEventListener("click", () => mo(i)),
        ex.appendChild(t),
        { p: i, el: t }
      )
    }),
    uu = document.getElementById("b-bom")
  function qc(i) {
    ;((ks.hidden = !i), uu.setAttribute("aria-pressed", String(i)), zc())
  }
  uu.addEventListener("click", () => qc(ks.hidden))
  document.getElementById("bom-close").addEventListener("click", () => qc(!1))
  var Gc = document.getElementById("r-ex"),
    ix = document.getElementById("o-ex"),
    sx = document.getElementById("b-play-t")
  function go() {
    let i = Math.round(xt.t * 100)
    ;((Gc.value = i), (ix.textContent = i + "%"), (sx.textContent = xt.t > 0.5 ? "装配" : "爆炸"))
  }
  Gc.addEventListener("input", () => {
    ;((xt.tTarget = null), (xt.t = Gc.value / 100), go())
  })
  document.getElementById("b-play").addEventListener("click", () => {
    let i = xt.t > 0.5 ? 0 : 1
    iu ? ((xt.t = i), go()) : (xt.tTarget = i)
  })
  var Wc = document.getElementById("b-lbl")
  Wc.setAttribute("aria-pressed", String(xt.labels))
  Wc.addEventListener("click", () => {
    ;((xt.labels = !xt.labels), Wc.setAttribute("aria-pressed", String(xt.labels)))
  })
  document.getElementById("b-view").addEventListener("click", () => {
    ;((xt.moved = !1), fo())
  })
  var Jh = document.getElementById("chip"),
    du = document.getElementById("cap"),
    rx = document.getElementById("b-act-t"),
    lo = {
      open: "<b>当前全开。</b>球体通孔与管道同轴；中间腔有压缩空气，两只活塞被推到外侧，6 根弹簧处于压缩状态。",
      closing:
        "<b>关阀中：</b>电磁阀断电，中间腔经消声器排气 → 弹簧把两只活塞推向中间 → 齿条带着齿轮轴顺时针转 90\xB0 → 球体通孔转到与管道垂直。",
      closed:
        "<b>当前全关。</b>实心球面堵住流道，被 PTFE 阀座压紧。断气后靠弹簧保持关闭，所以停电、断气时阀门自动关（失气关 FC）。",
      opening:
        "<b>开阀中：</b>电磁阀通电，压缩空气进入中间腔 → 两只活塞被推向两端、压缩弹簧 → 齿轮轴逆时针转 90\xB0 → 通孔转回与管道同轴。",
    }
  function fu(i) {
    ;((Jh.className = "chip " + i),
      (Jh.textContent = { open: "全开", closed: "全关", moving: "动作中" }[i]))
  }
  document.getElementById("b-act").addEventListener("click", () => {
    let i = xt.thTarget === 0
    ;((xt.thTarget = i ? -Math.PI / 2 : 0),
      (rx.textContent = i ? "开阀" : "关阀"),
      (du.innerHTML = i ? lo.closing : lo.opening),
      iu ? ((xt.th = xt.thTarget), pu()) : fu("moving"))
  })
  function pu() {
    let i = xt.thTarget !== 0
    ;(fu(i ? "closed" : "open"), (du.innerHTML = i ? lo.closed : lo.open))
  }
  function Zc() {
    let i = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--shadow-a")) || 0.25
    ;((xt.shadowA = i), po())
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", Zc)
  new MutationObserver(Zc).observe(document.documentElement, {
    attributes: !0,
    attributeFilter: ["data-theme"],
  })
  var Kh = performance.now()
  function mu(i) {
    let t = Math.min(0.05, (i - Kh) / 1e3)
    if (((Kh = i), xt.tTarget !== null)) {
      let e = Math.sign(xt.tTarget - xt.t)
      ;((xt.t += e * t * 0.55),
        ((e > 0 && xt.t >= xt.tTarget) || (e < 0 && xt.t <= xt.tTarget) || e === 0) &&
          ((xt.t = xt.tTarget), (xt.tTarget = null)),
        go())
    }
    if (xt.th !== xt.thTarget) {
      let e = Math.sign(xt.thTarget - xt.th)
      ;((xt.th += e * t * 1.25),
        ((e > 0 && xt.th >= xt.thTarget) || (e < 0 && xt.th <= xt.thTarget)) &&
          ((xt.th = xt.thTarget), pu()))
    }
    ;(Bc(),
      cu(!1),
      j_(),
      (co.position.y = Yc.min.y - 0.4),
      (co.material.opacity = (xt.shadowA ?? 0.22) * (1 - Math.min(1, xt.t * 1.5))),
      Zn.update(),
      mn.render(yi, _e),
      tx(),
      requestAnimationFrame(mu))
  }
  new ResizeObserver(lu).observe(fe)
  lu()
  Zc()
  go()
  requestAnimationFrame(mu)
  window.__valve = { st: xt, parts: xi, fit: fo, camera: _e, controls: Zn }
})()
