# -*- coding: utf-8 -*-
"""
时序图生成器（表格风格）：读 charts.py，输出
  out/<图号>.svg      每张时序图
  out/时序图.drawio   同样的图，draw.io 格式（一张图一页）
  out/时序图_ja.drawio / 时序图_en.drawio   日语 / 英语版 drawio（翻译在 i18n.py）
  out/图一览.md       所有图 + 信号×图对照表
出图前先做时序对位检查（check_timing），出完把 drawio 读回来再查一遍。

版式：左边 区分 | 信号 | 备考，右边按阶段 ①②③… 分列，信号画成色块。
分区：清洗机→PLC / PLC→清洗机 / PLC→温水器 / 温水器→PLC / 温水器状态 / PLC 内部

用法：python render.py            （或双击 render_charts.bat）
      python render.py --png      （额外输出 PNG，方便贴到 Excel / PPT）
      python render.py 2-1 4-2    （只出指定的图）
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
sys.path.insert(0, HERE)
import charts as C  # noqa: E402
import export_drawio as D  # noqa: E402
import i18n as I  # noqa: E402

FONT_CANDIDATES = ['Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans CJK JP',
                   'SimHei', 'Yu Gothic', 'Meiryo', 'MS Gothic']

# 分区：显示名、深色（色块）、浅色（底色）
ZONES = {
    'fc_int': ('清洗机内部\n（参考）', '#7f7f7f', '#ededed'),
    'fc_in':  ('清洗机\n→ PLC', '#2e75b6', '#ddebf7'),
    'direct': ('清洗机→温水器\n直连', '#44546a', '#d6dce4'),
    'fc_out': ('PLC →\n清洗机', '#7030a0', '#e9e0f2'),
    'su_out': ('PLC →\n温水器', '#c55a11', '#fbe4d5'),
    'su_in':  ('温水器\n→ PLC', '#a07800', '#fff2cc'),
    'su_st':  ('温水器\n状态', '#548235', '#e2efda'),
    'plc':    ('PLC\n内部', '#c00000', '#f8d7d7'),
}

# 版式（英寸）
ZONE_W = 1.15
SIG_W = 1.75
NOTE_W = 3.1
PH_W = 1.32
ROW_H = 0.30
HEAD1 = 0.32
HEAD2 = 0.46
TITLE_H = 1.18
FRAME_W = 0.34     # 短帧宽度（以阶段为单位）
NAVY = '#1f3864'
HEAD_BG = '#dde4f0'
FAULT = '#c00000'
GREEN = '#548235'
GRID = '#c8ccd4'


def pick_font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for n in FONT_CANDIDATES:
        if n in names:
            return n
    return None


def text_units(s):
    return sum(1.0 if ord(ch) > 0x2E7F else 0.56 for ch in s)


def wrap(s, width_in, fs):
    """按宽度折行（中文按 1 字宽，半角按 0.56）"""
    maxu = width_in * 72 / fs
    lines, cur, u = [], '', 0.0
    for ch in s:
        w = 1.0 if ord(ch) > 0x2E7F else 0.56
        if u + w > maxu and cur:
            lines.append(cur)
            cur, u = '', 0.0
        cur += ch
        u += w
    if cur:
        lines.append(cur)
    return lines


def check(c):
    n = len(c['phases'])
    zone = None
    names = set()
    for r in c['rows']:
        if r['t'] == 'zone':
            if r['z'] not in ZONES:
                raise SystemExit(f"[{c['id']}] 未知分区 {r['z']}")
            zone = r['z']
            continue
        if zone is None:
            raise SystemExit(f"[{c['id']}] 信号「{r['name']}」前面没有分区 Z(...)")
        key = (zone, r['name'])
        if key in names:
            raise SystemExit(f"[{c['id']}] 同一分区里信号名重复：{r['name']}")
        names.add(key)
        for b in r['bars']:
            x0 = b[0]
            x1 = b[1] if b[1] is not None else x0 + FRAME_W
            if not (1 <= x0 < x1 <= n + 1 + 1e-9):
                raise SystemExit(f"[{c['id']}] 信号「{r['name']}」的色块 {b} 超出阶段范围 1～{n + 1}")


SERIAL_SKIP = ('远程电源',)          # PLC→温水器 里走 IO 的行，不算串口帧
MODBUS_PAIRS = {'写温度': '写应答', '读报警': '读应答'}


def _items(c, zone, names=None, skip=()):
    out, z = [], None
    for r in c['rows']:
        if r['t'] == 'zone':
            z = r['z']
            continue
        if z != zone or (names and r['name'] not in names) or r['name'].startswith(skip):
            continue
        for b in r['bars']:
            kind = b[3] if len(b) > 3 else 'on'
            if kind == 'txt':
                continue
            x1 = b[1] if b[1] is not None else b[0] + FRAME_W
            out.append((round(b[0], 4), round(x1, 4), b[2], kind, r['name']))
    return out


def _match(reqs, reps, tag):
    """请求和应答：同一时刻同宽，或者没应答 = 紧跟在请求后面的斜线格「无」"""
    warn = []
    spans = sorted({(a, b) for a, b, *_ in reqs})
    used = set()
    busy = []
    for a, b in spans:
        same = [r for r in reps if r[0] == a and r[1] == b]
        miss = [r for r in reps if r[3] == 'none' and r[0] == b]
        if same:
            used.update(id(r) for r in same)
            busy.append((a, b))
        elif miss:
            used.update(id(r) for r in miss)
            busy.append((a, miss[0][1]))
        else:
            warn.append(f'{tag} 请求 {a:g}～{b:g} 没有对应的应答（同一时刻）或「无」（紧跟在后面）')
            busy.append((a, b))
    for r in reps:
        if id(r) not in used:
            warn.append(f'{tag} 应答「{r[2]}」{r[0]:g}～{r[1]:g} 找不到对应的请求')
    busy.sort()
    for (a0, b0), (a1, b1) in zip(busy, busy[1:]):
        if a1 < b0 - 1e-9:
            warn.append(f'{tag} 线上重叠：{a0:g}～{b0:g} 还没完，{a1:g} 又发了')
    return warn


def check_timing(c):
    """时序对位检查：串口（PLC↔温水器）和 Modbus（清洗机↔PLC）各自一条线"""
    warn = _match(_items(c, 'su_out', skip=SERIAL_SKIP), _items(c, 'su_in'), '串口')
    for q, a in MODBUS_PAIRS.items():
        reqs = _items(c, 'fc_in', names={q})
        reps = [r for r in _items(c, 'fc_out', names={a})]
        if reqs or reps:
            warn += _match(reqs, reps, f'Modbus {q}')
    allm = sorted(_items(c, 'fc_in', names=set(MODBUS_PAIRS)))
    for p0, p1 in zip(allm, allm[1:]):
        if p1[0] < p0[1] - 1e-9:
            warn.append(f'Modbus 线上重叠：{p0[4]} {p0[0]:g} 和 {p1[4]} {p1[0]:g}')
    for r in c['rows']:
        if r['t'] != 'row':
            continue
        for b in r['bars']:
            edges = [b[0]] + ([b[1]] if b[1] is not None else [])   # 短帧只看起点
            for x in edges:
                d = abs(x - round(x))
                if 1e-9 < d < 0.095:
                    warn.append(f'「{r["name"]}」{x:g} 离阶段线只差 {d:.2f}：要么压在线上，要么离开 0.1 以上')
    return [f"[{c['id']}] {w}" for w in warn]


def draw_chart(c, font, formats):
    check(c)
    n = len(c['phases'])
    kw = dict(fontfamily=font) if font else {}
    left = ZONE_W + SIG_W + NOTE_W
    W = left + n * PH_W + 0.25

    def X(x):  # 阶段坐标 → 英寸（阶段 k 占 [k, k+1)）
        return left + (x - 1) * PH_W

    # 先算行布局
    rows = []
    zone = None
    for r in c['rows']:
        if r['t'] == 'zone':
            zone = r['z']
            continue
        rows.append((zone, r))
    table_top = TITLE_H + HEAD1 + HEAD2
    table_h = len(rows) * ROW_H
    notes = c.get('notes', [])
    note_lines = []
    for i, t in enumerate(notes, start=1):
        ls = wrap(f'※{i} {t}', W - 0.8, 8.6)   # 留点余量，别把句号单独挤到下一行
        note_lines += ls
    H = table_top + table_h + 0.35 + 0.22 * (len(note_lines) + 1) + 0.25

    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis('off')

    # 标题
    ax.text(0.15, 0.33, f"{c['id']}  {c['title']}", fontsize=14, weight='bold', color=NAVY,
            va='center', **kw)
    ax.text(0.15, 0.66, '这张图回答：' + c['q'], fontsize=9.2, color='#374151', va='center', **kw)
    ax.text(0.15, 0.94, '标记：【推】清洗机 / 温水器侧的前提　【IO】IO 分配　【P】PLC 本方案　'
            '【未】还没定　【定】已定', fontsize=7.6, color='#6b7280',
            va='center', ha='left', **kw)

    # 表头
    y0 = TITLE_H
    for x, w, label in ((0, ZONE_W, '区分'), (ZONE_W, SIG_W, '信号'), (ZONE_W + SIG_W, NOTE_W, '备考')):
        ax.add_patch(Rectangle((x, y0), w, HEAD1 + HEAD2, facecolor=NAVY, edgecolor='white', lw=0.8))
        ax.text(x + w / 2, y0 + (HEAD1 + HEAD2) / 2, label, color='white', fontsize=9.5,
                weight='bold', ha='center', va='center', **kw)
    circled = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'
    for k, name in enumerate(c['phases'], start=1):
        x = X(k)
        ax.add_patch(Rectangle((x, y0), PH_W, HEAD1, facecolor=NAVY, edgecolor='white', lw=0.8))
        ax.text(x + PH_W / 2, y0 + HEAD1 / 2, circled[k - 1], color='white', fontsize=10.5,
                ha='center', va='center', **kw)
        ax.add_patch(Rectangle((x, y0 + HEAD1), PH_W, HEAD2, facecolor=HEAD_BG, edgecolor='white', lw=0.8))
        lines = wrap(name, PH_W - 0.1, 8.2)[:2]
        ax.text(x + PH_W / 2, y0 + HEAD1 + HEAD2 / 2, '\n'.join(lines), color='#1f2937',
                fontsize=8.2, ha='center', va='center', linespacing=1.15, **kw)

    # 行
    y = table_top
    zone_spans = []
    for i, (z, r) in enumerate(rows):
        dark, light = ZONES[z][1], ZONES[z][2]
        if not zone_spans or zone_spans[-1][0] != z:
            zone_spans.append([z, y, y + ROW_H])
        else:
            zone_spans[-1][2] = y + ROW_H
        ax.add_patch(Rectangle((ZONE_W, y), SIG_W + NOTE_W, ROW_H, facecolor=light, edgecolor='white', lw=0.6))
        tbd = r.get('tbd')
        ax.text(ZONE_W + 0.08, y + ROW_H / 2, r['name'] + ('  ?' if tbd else ''), fontsize=8.8,
                va='center', color='#6b7280' if tbd else '#111827', **kw)
        note = r.get('note', '')
        nl = wrap(note, NOTE_W - 0.12, 7.2)
        fs = 7.2 if len(nl) <= 2 else 6.4
        nl = wrap(note, NOTE_W - 0.12, fs)[:2]
        ax.text(ZONE_W + SIG_W + 0.06, y + ROW_H / 2, '\n'.join(nl), fontsize=fs, va='center',
                color='#4b5563', linespacing=1.05, **kw)
        # 时间轴底色 + 网格
        ax.add_patch(Rectangle((left, y), n * PH_W, ROW_H, facecolor='white', edgecolor='none'))
        ax.plot([left, left + n * PH_W], [y + ROW_H, y + ROW_H], color='#e5e7eb', lw=0.6, zorder=1)
        # 色块
        for b in r['bars']:
            x0, x1, text = b[0], b[1], b[2]
            kind = b[3] if len(b) > 3 else 'on'
            if x1 is None:
                x1 = x0 + FRAME_W
            bx0, bx1 = X(x0) + 0.01, X(x1) - 0.01
            by0, bh = y + 0.045, ROW_H - 0.09
            tc, fc, ec, hatch, ls = 'white', dark, 'none', None, '-'
            if kind == 'val':
                fc, tc = light, dark
                ec = dark
            elif kind == 'fault':
                fc = FAULT
            elif kind == 'green':
                fc = GREEN
            elif kind == 'gray':
                fc = '#9ca3af'
            elif kind == 'txt':
                fc, tc = 'none', dark
            elif kind == 'tbd':
                fc, tc, ec, ls = 'white', '#6b7280', '#9ca3af', (0, (3, 2))
            elif kind == 'none':   # 没应答：斜线格
                fc, tc, ec, hatch = 'white', FAULT, FAULT, '////'
            if kind != 'txt':
                ax.add_patch(Rectangle((bx0, by0), bx1 - bx0, bh, facecolor=fc, edgecolor=ec,
                                       lw=0.9, ls=ls, hatch=hatch, zorder=3))
            if text:
                room = (bx1 - bx0 - 0.06) * 72
                fsz = max(5.0, min(7.8, room / max(text_units(text), 1) / 1.02))
                if kind in ('txt',):
                    ax.text(bx0 + 0.04, y + ROW_H / 2, text, fontsize=7.6, color=tc, va='center',
                            ha='left', weight='bold', zorder=4, **kw)
                else:
                    ax.text((bx0 + bx1) / 2, y + ROW_H / 2, text, fontsize=fsz, color=tc,
                            ha='center', va='center', weight='bold' if kind != 'val' else 'normal',
                            zorder=4, bbox=dict(facecolor='white', edgecolor='none', pad=0.6)
                            if kind == 'none' else None, **kw)
        y += ROW_H

    # 分区标签和粗分隔线
    for z, ya, yb in zone_spans:
        name, dark, light = ZONES[z]
        ax.add_patch(Rectangle((0, ya), ZONE_W, yb - ya, facecolor=light, edgecolor='white', lw=0.8))
        one_row = (yb - ya) < ROW_H * 1.5
        label = name.replace('\n', '') if one_row else name
        widest = max(text_units(t) for t in label.split('\n'))
        fsz = min(7.4 if one_row else 8.8, (ZONE_W - 0.1) * 72 / max(widest, 1))
        ax.text(ZONE_W / 2, (ya + yb) / 2, label, fontsize=fsz, weight='bold',
                color=dark, ha='center', va='center', linespacing=1.15, **kw)
        ax.plot([0, left + n * PH_W], [yb, yb], color=dark, lw=1.4, zorder=5)
    ax.plot([0, left + n * PH_W], [table_top, table_top], color=NAVY, lw=1.4, zorder=5)
    # 阶段竖线
    for k in range(1, n + 2):
        ax.plot([X(k), X(k)], [table_top, table_top + table_h], color=GRID, lw=0.8,
                ls=(0, (3, 3)), zorder=2)
    ax.plot([left, left], [TITLE_H, table_top + table_h], color=NAVY, lw=1.2, zorder=5)

    # 注记
    yy = table_top + table_h + 0.35
    ax.text(0.15, yy, '【注记】', fontsize=9.2, weight='bold', color='#111827', va='center', **kw)
    yy += 0.24
    for line in note_lines:
        ax.text(0.2, yy, line, fontsize=8.6, color='#1f2937', va='center', **kw)
        yy += 0.22

    for fmt in formats:
        extra = dict(metadata={'Date': None}) if fmt == 'svg' else dict(dpi=130)
        fig.savefig(os.path.join(OUT, f"{c['id']}.{fmt}"), format=fmt, **extra)
    plt.close(fig)


def write_md(charts):
    lines = ['# 时序图一览', '',
             '> 自动生成，别手改。改 `charts.py` 后双击 `render_charts.bat` 重新生成。', '',
             '每张图左边是 区分 / 信号 / 备考，右边按阶段 ①②③… 分列。备考里的标记：'
             '【推】清洗机 / 温水器侧的前提、【IO】IO 分配、【P】PLC 本方案、【未】还没定、【定】已定。'
             '红色 = 报警 / 异常，斜线格 = 没应答，灰色虚线框 = 待确认。', '',
             '请求和应答画在同一时刻（实际一问一答只要几十 ms）。没应答的请求：斜线格「无」紧跟在请求后面，'
             '表示等到超时（断线图 4-2、4-3、4-4）。出图时 `render.py` 会自动检查对位：串口、Modbus 各一条线，'
             '每个请求都要有同一时刻的应答或紧跟的「无」，同一条线上的帧不能重叠。', '',
             'draw.io 版：[时序图.drawio](时序图.drawio)，一张图一页，坐标和 SVG 相同（1 阶段 = 100 px）。'
             '「表格」图层锁住，「信号」图层可以拖。drawio 里没应答画成红虚线框。', '',
             '日语版 [时序图_ja.drawio](时序图_ja.drawio)、英语版 [时序图_en.drawio](时序图_en.drawio)：'
             '色块位置和中文版一样，文字查 `../i18n.py`，左边三列按语言放宽。', '']
    block = None
    for c in charts:
        if c['block'] != block:
            block = c['block']
            lines += [f'## {block}', '']
        lines += [f"### {c['id']} {c['title']}", '', f"这张图回答：{c['q']}", '',
                  f"![{c['id']}]({c['id']}.svg)", '']
    # 信号 × 图
    keys, use = [], {}
    for c in charts:
        zone = None
        for r in c['rows']:
            if r['t'] == 'zone':
                zone = r['z']
                continue
            k = f"{ZONES[zone][0].replace(chr(10), '')} · {r['name']}"
            if k not in use:
                keys.append(k)
                use[k] = set()
            use[k].add(c['id'])
    ids = [c['id'] for c in charts]
    lines += ['## 信号 × 图', '', '| 分区 · 信号 | ' + ' | '.join(ids) + ' |',
              '|---|' + '|'.join([':-:'] * len(ids)) + '|']
    for k in keys:
        lines.append(f'| {k} | ' + ' | '.join('●' if i in use[k] else '' for i in ids) + ' |')
    lines.append('')
    with open(os.path.join(OUT, '图一览.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def report_missing(missing):
    """i18n.py 里查不到的中文：命令行列出来，并写进 out/缺翻译.txt（照格式补进 i18n.py 就行）"""
    path = os.path.join(OUT, '缺翻译.txt')
    if not missing:
        if os.path.exists(path):
            os.remove(path)
        print('翻译：日语 / 英语全部对上')
        return
    print(f'[缺翻译] {len(missing)} 条，日语 / 英语版先用中文顶着。补进 i18n.py 的 ENTRIES：')
    for s in missing[:8]:
        print('   ', repr(s)[:90])
    if len(missing) > 8:
        print(f'    …… 全部见 {path}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# 把下面几行补进 i18n.py 的 ENTRIES，填上日语和英语，再出一次图\n')
        for s in missing:
            f.write(f"    ({s!r}, '', ''),\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    font = pick_font()
    if not font:
        print('[WARN] 没找到中文字体，图里的中文可能显示成方块')
    plt.rcParams['svg.fonttype'] = 'path'
    plt.rcParams['svg.hashsalt'] = 'timing'
    plt.rcParams['hatch.linewidth'] = 0.6
    formats = ['svg'] + (['png'] if '--png' in sys.argv else [])
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    warns = []
    for c in C.CHARTS:
        check(c)
        warns += check_timing(c)
    for c in C.CHARTS:
        if only and c['id'] not in only:
            continue
        draw_chart(c, font, formats)
        print(f"  {c['id']}  {c['title']}")
    write_md(C.CHARTS)
    colors = (NAVY, HEAD_BG, FAULT, GREEN, GRID)
    dio = os.path.join(OUT, '时序图.drawio')
    D.write_drawio(C.CHARTS, dio, ZONES, FRAME_W, colors)
    warns += [f'(drawio) {w}' for w in D.verify_drawio(dio, C.CHARTS, FRAME_W, check_timing)]
    # 日语 / 英语版：同样的色块，文字查 i18n.py
    missing = []
    for lang in I.LANGS:
        t, miss = I.translator(lang)
        p = os.path.join(OUT, f'时序图_{lang}.drawio')
        D.write_drawio(C.CHARTS, p, ZONES, FRAME_W, colors, lang, t)
        warns += [f'(drawio {lang}) {w}' for w in
                  D.verify_drawio(p, C.CHARTS, FRAME_W, check_timing, D.layout(lang)['left'])]
        missing += [s for s in miss if s not in missing]
    report_missing(missing)
    for w in warns:
        print('[时序检查]', w)
    print(f"时序检查：{'全部对上' if not warns else f'{len(warns)} 处要看'}")
    print(f'完成：{OUT}')


if __name__ == '__main__':
    main()
