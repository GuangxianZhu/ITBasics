# -*- coding: utf-8 -*-
"""
把 charts.py 的时序图导出成 draw.io 文件（一张图一页）：
  out/时序图.drawio      中文（原版）
  out/时序图_ja.drawio   日本語（文字查 i18n.py）
  out/时序图_en.drawio   English（同上）

坐标和 SVG 用同一套：1 个阶段 = 100 px，所以 charts.py 里的 0.01 阶段 = 1 px，
所有色块都落在整数像素上，严格对位。色块的 style 里带了 tl=bar;zone=…;sig=…;kind=…，
verify_drawio() 用它把图读回来、重新跑时序检查。

draw.io 里：「表格」图层锁住（表头、行名、网格），「信号」图层是色块，可以直接拖。
正式修改请改 charts.py 再出图，drawio 只是同一份数据的另一种格式。

日语 / 英语版：色块位置和中文版完全一样（同样跑读回检查），只是左边三列和行高按语言放宽，
字号按格子大小自动缩（_fit）。色块 style 里的 sig= 一律写中文信号名，读回检查靠它对上 charts.py。
"""
import os
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

PH = 100          # 1 个阶段的宽度（px）
ZONE_W = 92
SIG_W = 140
NOTE_W = 250
LEFT = ZONE_W + SIG_W + NOTE_W
ROW_H = 26
HEAD1 = 26
HEAD2 = 38
TITLE_H = 96
FONT = 'Microsoft YaHei,sans-serif'   # 没装雅黑的电脑退回无衬线字体
INSET_X = 1       # 色块左右各缩 1 px，相邻的块之间留缝
INSET_Y = 4

# 每种语言的版式。zh 的数值不要动（中文版输出要和以前逐字节相同）
LAYOUTS = {
    'zh': dict(font=FONT, zone_w=ZONE_W, sig_w=SIG_W, note_w=NOTE_W, row_h=ROW_H, fit=False, bar_min=6.5),
    'ja': dict(font='Meiryo UI,Yu Gothic UI,Meiryo,sans-serif', zone_w=100, sig_w=160, note_w=300, row_h=28,
               fit=True, bar_min=6.0),
    'en': dict(font='Segoe UI,Arial,sans-serif', zone_w=112, sig_w=180, note_w=340, row_h=30,
               fit=True, bar_min=6.0),
}


def layout(lang):
    lay = dict(LAYOUTS[lang])
    lay['left'] = lay['zone_w'] + lay['sig_w'] + lay['note_w']
    return lay

LEGEND = ('标记：【推】清洗机 / 温水器侧的前提　【IO】IO 分配　【P】PLC 本方案　【未】还没定　【定】已定'
          '　｜　红虚线框「无」= 没应答')


def _units(s):
    # 全角、圈数字 ①、× 都按 1 个字宽算（宁可字小一点，也别折行）
    return sum(1.0 if ord(ch) > 0x7F else 0.56 for ch in s)


def _wrap(s, width_px, fs):
    maxu = width_px / fs
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


def _cw(ch):
    """日语 / 英语版用的字宽估计（字号的倍数）。比 _units 细一点，免得英文字被缩得太小"""
    o = ord(ch)
    if o > 0x2E7F or 0x2190 <= o <= 0x2BFF:      # 汉字、假名、全角符号、箭头、圈数字
        return 1.0
    if o > 0x7F:                                  # × ° · – 等
        return 0.6
    if ch == ' ':
        return 0.3
    if ch in '.,:;\'|!il()[]/-"`':
        return 0.32
    if ch.isupper() or ch in 'mwMW%@#&':
        return 0.7
    if ch.isdigit():
        return 0.58
    return 0.55


def _cwidth(s):
    return sum(_cw(ch) for ch in s)


def _tokens(s):
    """折行单位：汉字 / 假名一个字一段，英文一个词（带后面的空格）一段"""
    out, cur = [], ''
    for ch in s:
        if ord(ch) > 0x2E7F:
            if cur:
                out.append(cur)
                cur = ''
            out.append(ch)
        elif ch == ' ':
            out.append(cur + ch)
            cur = ''
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _nlines(s, width_px, fs):
    """估计 draw.io 按词折行以后有几行"""
    maxu = width_px / fs
    n = 0
    for para in s.split('\n'):
        n += 1
        u = 0.0
        for tok in _tokens(para):
            w = _cwidth(tok.rstrip(' '))
            full = _cwidth(tok)
            if u > 0 and u + w > maxu:
                n += 1
                u = 0.0
            if w > maxu:              # 一个词比一行还长，浏览器会把它断开
                n += int(w // maxu)
                full -= maxu * int(w // maxu)
            u += full
    return n


_NB = re.compile(r'(\d) (s|ms|bps|℃)(?![A-Za-z])')


def _nobreak(s):
    """「5 s」「500 ms」中间换成不换行空格，免得数字和单位被拆到两行（只用于日语 / 英语版）"""
    return _NB.sub('\\1\u00a0\\2', s)


def _fit(s, width_px, height_px, fs_max, fs_min, step=0.5):
    """格子放得下的最大字号（draw.io 行高 = 1.2 × 字号）；怎么都放不下就用 fs_min"""
    fs = fs_max
    while fs >= fs_min - 1e-9:
        if _nlines(s, width_px, fs) * fs * 1.2 <= height_px:
            return fs
        fs = round(fs - step, 2)
    return fs_min


class Page:
    def __init__(self, pid):
        self.pid = pid
        self.cells = []
        self.n = 0

    def _id(self):
        self.n += 1
        return f'{self.pid}-{self.n}'

    def box(self, layer, x, y, w, h, text='', style=''):
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(text, {chr(34): "&quot;", chr(10): "&#xa;"})}" '
            f'style="{escape(style)}" vertex="1" parent="{layer}">'
            f'<mxGeometry x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" as="geometry"/></mxCell>')

    def line(self, layer, x0, y0, x1, y1, style):
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" style="endArrow=none;html=1;{escape(style)}" edge="1" parent="{layer}">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x0:g}" y="{y0:g}" as="sourcePoint"/>'
            f'<mxPoint x="{x1:g}" y="{y1:g}" as="targetPoint"/></mxGeometry></mxCell>')


def _txt(fs, color='#111827', align='left', bold=False, extra='', font=FONT):
    return (f'text;html=1;whiteSpace=wrap;overflow=hidden;fontFamily={font};fontSize={fs:g};'
            f'fontColor={color};align={align};verticalAlign=middle;spacingLeft=4;spacingRight=2;'
            f'strokeColor=none;fillColor=none;{"fontStyle=1;" if bold else ""}{extra}')


def _cell(fill, fs, color, bold=False, align='center', font=FONT):
    return (f'rounded=0;whiteSpace=wrap;html=1;fontFamily={font};fontSize={fs:g};fillColor={fill};'
            f'strokeColor=#ffffff;fontColor={color};align={align};verticalAlign=middle;'
            f'{"fontStyle=1;" if bold else ""}')


def page_xml(c, idx, zones, frame_w, colors, lang='zh', t=lambda s: s):
    navy, head_bg, fault, green, grid = colors
    lay = layout(lang)
    fit, font = lay['fit'], lay['font']
    if fit:
        t0 = t

        def t(s):
            return _nobreak(t0(s))
    ZW, SW, NW, RH, LF = lay['zone_w'], lay['sig_w'], lay['note_w'], lay['row_h'], lay['left']
    n = len(c['phases'])
    W = LF + n * PH + 20

    def X(x):
        return LF + round((x - 1) * PH, 4)

    def txt(fs, *a, **k):
        return _txt(fs, *a, font=font, **k)

    def cell(*a, **k):
        return _cell(*a, font=font, **k)

    rows, zone = [], None
    for r in c['rows']:
        if r['t'] == 'zone':
            zone = r['z']
            continue
        rows.append((zone, r))
    table_top = TITLE_H + HEAD1 + HEAD2
    table_h = len(rows) * RH

    pg = Page(f'p{idx}')
    T, S = f'p{idx}-table', f'p{idx}-sig'   # 两个图层

    # 标题
    title = f"{c['id']}  {t(c['title'])}"
    q = t('这张图回答：') + t(c['q'])
    legend = t(LEGEND)
    if fit:
        pg.box(T, 10, 8, W - 20, 30, title, txt(_fit(title, W - 30, 26, 18, 12), navy, bold=True))
        pg.box(T, 10, 40, W - 20, 24, q, txt(_fit(q, W - 30, 20, 12, 8), '#374151'))
        pg.box(T, 10, 66, W - 20, 26, legend, txt(_fit(legend, W - 30, 22, 10, 7), '#6b7280'))
    else:
        pg.box(T, 10, 8, W - 20, 30, title, txt(18, navy, bold=True))
        pg.box(T, 10, 40, W - 20, 24, q, txt(12, '#374151'))
        pg.box(T, 10, 66, W - 20, 22, legend, txt(10, '#6b7280'))

    # 表头
    y0 = TITLE_H
    for x, w, label in ((0, ZW, '区分'), (ZW, SW, '信号'), (ZW + SW, NW, '备考')):
        pg.box(T, x, y0, w, HEAD1 + HEAD2, t(label), cell(navy, 12, '#ffffff', bold=True))
    circled = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'
    for k, name in enumerate(c['phases'], start=1):
        name = t(name)
        pg.box(T, X(k), y0, PH, HEAD1, circled[k - 1], cell(navy, 13, '#ffffff'))
        fs = _fit(name, PH - 6, HEAD2 - 4, 10.5, 7) if fit else 10.5
        pg.box(T, X(k), y0 + HEAD1, PH, HEAD2, name, cell(head_bg, fs, '#1f2937'))

    # 行底色、行名、备考
    y = table_top
    spans = []
    for z, r in rows:
        dark, light = zones[z][1], zones[z][2]
        if not spans or spans[-1][0] != z:
            spans.append([z, y, y + RH])
        else:
            spans[-1][2] = y + RH
        pg.box(T, ZW, y, SW + NW, RH, '', f'rounded=0;fillColor={light};strokeColor=#ffffff;')
        name, note = t(r['name']), t(r.get('note', ''))
        if fit:
            fs_name = _fit(name, SW - 12, RH - 4, 11.5, 8)
            fs = _fit(note, NW - 12, RH - 4, 9.5, 6.5)
        else:
            fs_name = 11.5
            fs = 9.5 if len(_wrap(note, NW - 10, 9.5)) <= 2 else 8.5
        pg.box(T, ZW, y, SW, RH, name, txt(fs_name))
        pg.box(T, ZW + SW, y, NW, RH, note, txt(fs, '#4b5563', extra='spacingTop=0;'))
        pg.line(T, LF, y + RH, LF + n * PH, y + RH, 'strokeColor=#e5e7eb;strokeWidth=1;')
        y += RH

    # 分区标签 + 分区分隔粗线
    for z, ya, yb in spans:
        name, dark, light = zones[z]
        name = t(name)
        one = (yb - ya) < RH * 1.5
        if fit:
            # 保留换行 / 合成一行，哪个字大用哪个
            best = None
            joined = name.replace('\n', ' ' if lang == 'en' else '')
            for label in (name, joined):
                ls = label.split('\n')
                fs = min(10 if one else 12, (ZW - 8) / max(max(_cwidth(s) for s in ls), 1),
                         (yb - ya - 4) / (1.2 * len(ls)))
                if best is None or fs > best[1] + 1e-9:
                    best = (label, fs)
            label, fs = best
        else:
            label = name.replace('\n', '') if one else name
            widest = max(_units(s) for s in label.split('\n'))
            fs = min(10 if one else 12, (ZW - 8) / max(widest, 1))
        pg.box(T, 0, ya, ZW, yb - ya, label, cell(light, round(fs, 1), dark, bold=True))
        pg.line(T, 0, yb, LF + n * PH, yb, f'strokeColor={dark};strokeWidth=2;')
    pg.line(T, 0, table_top, LF + n * PH, table_top, f'strokeColor={navy};strokeWidth=2;')
    # 阶段竖线（虚线）
    for k in range(1, n + 2):
        pg.line(T, X(k), table_top, X(k), table_top + table_h, f'strokeColor={grid};dashed=1;strokeWidth=1;')
    pg.line(T, LF, TITLE_H, LF, table_top + table_h, f'strokeColor={navy};strokeWidth=2;')

    # 色块（信号图层）
    y = table_top
    for z, r in rows:
        dark, light = zones[z][1], zones[z][2]
        for b in r['bars']:
            x0, x1, text = b[0], b[1], t(b[2])
            kind = b[3] if len(b) > 3 else 'on'
            frame = x1 is None          # 短帧（固定宽度）
            if frame:
                x1 = x0 + frame_w
            bx0, bx1 = X(x0) + INSET_X, X(x1) - INSET_X
            w = round(bx1 - bx0, 4)
            tag = f'tl=bar;zone={z};sig={r["name"]};kind={kind};{"fr=1;" if frame else ""}'
            units = _cwidth(text) if fit else _units(text)
            fsz = max(lay['bar_min'], min(10.5, (w - 6) / max(units, 1)))
            fsz = round(fsz, 1)
            base = f'rounded=0;whiteSpace=nowrap;html=1;fontFamily={font};fontSize={fsz:g};spacing=0;{tag}'
            if kind == 'txt':
                style = (f'text;html=1;whiteSpace=nowrap;fontFamily={font};fontSize=10;fontStyle=1;'
                         f'fontColor={dark};align=left;verticalAlign=middle;spacingLeft=3;fillColor=none;strokeColor=none;{tag}')
            elif kind == 'val':
                style = base + f'fillColor={light};strokeColor={dark};fontColor={dark};'
            elif kind == 'tbd':
                style = base + 'fillColor=#ffffff;strokeColor=#9ca3af;dashed=1;fontColor=#6b7280;fontStyle=1;'
            elif kind == 'none':
                style = base + f'fillColor=#fdecec;strokeColor={fault};dashed=1;strokeWidth=1.5;fontColor={fault};fontStyle=1;'
            else:
                fill = {'fault': fault, 'green': green, 'gray': '#9ca3af'}.get(kind, dark)
                style = base + f'fillColor={fill};strokeColor=none;fontColor=#ffffff;fontStyle=1;'
            pg.box(S, bx0, y + INSET_Y, w, RH - 2 * INSET_Y, text, style)
        y += RH

    # 注记
    yy = table_top + table_h + 18
    pg.box(T, 10, yy, 200, 20, t('【注记】'), txt(12, '#111827', bold=True))
    yy += 22
    for i, note in enumerate(c.get('notes', []), start=1):
        s = f'※{i} {t(note)}'
        nl = _nlines(s, W - 28 - 12, 11.5) if fit else len(_wrap(s, W - 40, 11.5))
        h = 18 * nl + 2
        pg.box(T, 14, yy, W - 28, h, s, txt(11.5, '#1f2937', extra='verticalAlign=top;'))
        yy += h
    H = yy + 20

    name = escape(f"{c['id']} {t(c['title'])}", {'"': '&quot;'})
    return (f'<diagram id="chart-{c["id"]}" name="{name}">'
            f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" guides="1" tooltips="1" connect="0" '
            f'arrows="0" fold="1" page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0">'
            f'<root><mxCell id="p{idx}-0"/>'
            f'<mxCell id="{T}" value="{escape(t("表格"))}" style="locked=1;" parent="p{idx}-0"/>'
            f'<mxCell id="{S}" value="{escape(t("信号"))}" parent="p{idx}-0"/>'
            + ''.join(pg.cells) + '</root></mxGraphModel></diagram>')


def write_drawio(charts, path, zones, frame_w, colors, lang='zh', t=lambda s: s):
    pages = [page_xml(c, i, zones, frame_w, colors, lang, t) for i, c in enumerate(charts, start=1)]
    xml = ('<mxfile host="charts.py" agent="render.py" version="24.0.0">' + ''.join(pages) + '</mxfile>\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)


def read_back(path, left=LEFT):
    """把 drawio 读回成 charts 的形状（只读色块），给 check_timing 用。left = 左边三列的总宽（按语言不同）"""
    tree = ET.parse(path)
    out = []
    for d in tree.getroot().findall('diagram'):
        cid = d.get('id')[len('chart-'):]
        rows = {}
        order = []
        for cell in d.iter('mxCell'):
            st = cell.get('style') or ''
            if 'tl=bar;' not in st:
                continue
            kv = dict(p.split('=', 1) for p in st.split(';') if '=' in p)
            g = cell.find('mxGeometry')
            x0 = (float(g.get('x')) - INSET_X - left) / PH + 1
            x1 = (float(g.get('x')) + float(g.get('width')) + INSET_X - left) / PH + 1
            key = (kv['zone'], kv['sig'])
            if key not in rows:
                rows[key] = []
                order.append(key)
            rows[key].append((round(x0, 4), None if kv.get('fr') == '1' else round(x1, 4),
                              cell.get('value') or '', kv['kind']))
        crow = []
        last = None
        for z, sig in order:
            if z != last:
                crow.append(dict(t='zone', z=z))
                last = z
            crow.append(dict(t='row', name=sig, note='', bars=rows[(z, sig)], tbd=False))
        out.append(dict(id=cid, rows=crow))
    return out


def verify_drawio(path, charts, frame_w, check_timing, left=LEFT):
    """drawio 读回来以后：① 每个色块的位置和 charts.py 一致 ② 时序检查照样通过"""
    problems = []
    back = {c['id']: c for c in read_back(path, left)}
    for c in charts:
        b = back.get(c['id'])
        if not b:
            problems.append(f"[{c['id']}] drawio 里没有这一页")
            continue
        want = []
        zone = None
        for r in c['rows']:
            if r['t'] == 'zone':
                zone = r['z']
                continue
            for bar in r['bars']:
                x1 = bar[1] if bar[1] is not None else bar[0] + frame_w
                want.append((zone, r['name'], round(bar[0], 4), round(x1, 4)))
        got = []
        for r in b['rows']:
            if r['t'] == 'zone':
                zone = r['z']
                continue
            for bar in r['bars']:
                x1 = bar[1] if bar[1] is not None else round(bar[0] + frame_w, 4)
                got.append((zone, r['name'], bar[0], x1))
        if sorted(want) != sorted(got):
            diff = set(want) ^ set(got)
            problems.append(f"[{c['id']}] drawio 色块位置和 charts.py 不一致：{sorted(diff)[:4]}")
        problems += check_timing(b)
    return problems
