"""
table_to_drawio.py — 部品表 + 连接表 → draw.io 管路图（自动排版）

用法:
    python table_to_drawio.py 部品表.csv 连接表.csv
    python table_to_drawio.py 部品表.csv 连接表.csv -o ONB供给.drawio

部品表.csv（列名中日英都认，顺序随意）:
    位号, 种类, 说明
    AV-12, 气动阀, DIW供给
连接表.csv:
    从, 到, 管线种类
    DIW总管, AV-12, DIW

    · 连接表里出现、但部品表里没有的位号 → 红色虚线框，提醒你补
    · 部品表里有、但没有任何连接的 → 灰色，放在最右边一列
    · 循环管路（回流）也能处理
    · CSV 可以是 UTF-8 或 Excel 默认的 Shift_JIS(cp932)

输出的 .drawio 用 draw.io（桌面版或 app.diagrams.net）打开。
每个图形都带 tag / type / desc 属性（右键 → Edit Data 可以看到）。
"""
import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

# ---------------------------------------------------------------- 读 CSV
ALIASES = {
    "tag":  ["位号", "タグ", "タグ番号", "tag", "id", "記号", "记号", "番号", "no"],
    "type": ["种类", "種類", "種別", "种别", "类型", "type", "kind", "区分"],
    "desc": ["说明", "説明", "名称", "名前", "备注", "備考", "desc", "description", "name"],
    "from": ["从", "起点", "接続元", "上流", "from", "source"],
    "to":   ["到", "终点", "接続先", "下流", "to", "target"],
    "line": ["管线种类", "管線", "配管", "流体", "line", "fluid", "medium", "种类", "種類"],
}


def read_csv(path):
    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, newline="", encoding=enc) as f:
                rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
            return rows
        except UnicodeDecodeError:
            continue
    sys.exit(f"读不了 {path} 的编码")


def map_columns(header, keys):
    """按列名找对应列；找不到就按顺序"""
    low = [h.strip().lower() for h in header]
    result, used = {}, set()
    for k in keys:
        for alias in ALIASES[k]:
            if alias.lower() in low and low.index(alias.lower()) not in used:
                result[k] = low.index(alias.lower())
                used.add(result[k])
                break
    if len(result) < len(keys):          # 认不出列名 → 按位置
        free = [i for i in range(len(header)) if i not in used]
        for k in keys:
            if k not in result and free:
                result[k] = free.pop(0)
    return result


def load_parts(path):
    rows = read_csv(path)
    col = map_columns(rows[0], ["tag", "type", "desc"])
    parts = {}
    for r in rows[1:]:
        get = lambda k: r[col[k]].strip() if k in col and col[k] < len(r) else ""
        tag = get("tag")
        if tag:
            parts[tag] = {"type": get("type"), "desc": get("desc")}
    return parts


def load_edges(path):
    rows = read_csv(path)
    col = map_columns(rows[0], ["from", "to", "line"])
    edges = []
    for r in rows[1:]:
        get = lambda k: r[col[k]].strip() if k in col and col[k] < len(r) else ""
        a, b = get("from"), get("to")
        if a and b:
            edges.append((a, b, get("line")))
    return edges


# ---------------------------------------------------------------- 外观
def kind_of(tag, typ):
    s = f"{typ} {tag}".lower()
    rules = [
        ("header", ["总管", "ヘッダ", "マニホールド", "header", "manifold"]),
        ("tank",   ["槽", "タンク", "tank", "bath"]),
        ("pump",   ["泵", "ポンプ", "pump"]),
        ("filter", ["过滤", "フィルタ", "filter"]),
        ("valve",  ["阀", "弁", "バルブ", "valve"]),
        ("sensor", ["传感", "センサ", "计", "計", "sensor", "meter", "switch", "スイッチ"]),
    ]
    for kind, words in rules:
        if any(w in s for w in words):
            return kind
    prefix = re.match(r"[A-Za-z]+", tag)
    p = prefix.group(0).upper() if prefix else ""
    if p in ("AV", "MV", "CV", "SV", "V", "NV", "BV"):
        return "valve"
    if p in ("P", "PU", "PMP"):
        return "pump"
    if p in ("F", "FIL"):
        return "filter"
    if len(p) >= 2 and p[0] in "FPLTCQ" and p[-1] in "MSTIE":  # FM, PS, LS, TS, PT, CT...
        return "sensor"
    return "other"


BELOW = "verticalLabelPosition=bottom;verticalAlign=top;"
SHAPES = {   # style, w, h
    "valve":  ("rhombus;" + BELOW, 40, 40),
    "pump":   ("ellipse;" + BELOW, 50, 50),
    "sensor": ("ellipse;aspect=fixed;" + BELOW, 34, 34),
    "filter": ("shape=hexagon;perimeter=hexagonPerimeter2;" + BELOW, 50, 36),
    "tank":   ("rounded=1;arcSize=6;", 110, 80),
    "header": ("rounded=0;", 24, 60),       # 高度按分支数伸长
    "other":  ("rounded=1;", 100, 44),
}
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
           "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]


# ---------------------------------------------------------------- 排版
def layers(nodes, edges):
    """从源头开始按 BFS 距离分列；循环里的节点也能分到列"""
    out_e, indeg = defaultdict(list), defaultdict(int)
    for a, b, _ in edges:
        out_e[a].append(b)
        indeg[b] += 1
    layer = {}
    pending = [n for n in nodes if indeg[n] == 0]
    remaining = set(nodes)
    while remaining:
        if not pending:      # 只剩环: 拿入度最小的当起点
            pending = [min(remaining, key=lambda n: (indeg[n], n))]
        q = deque()
        for s in pending:
            if s in remaining:
                layer[s] = 0
                q.append(s)
                remaining.discard(s)
        pending = []
        while q:
            n = q.popleft()
            for m in out_e[n]:
                if m in remaining:
                    layer[m] = layer[n] + 1
                    remaining.discard(m)
                    q.append(m)
    return layer


# ---------------------------------------------------------------- 生成
def build(parts, edges, title):
    connected = []
    for a, b, _ in edges:
        for n in (a, b):
            if n not in connected:
                connected.append(n)
    missing = [n for n in connected if n not in parts]
    lonely = [t for t in parts if t not in connected]

    outdeg = defaultdict(int)
    for a, _, _ in edges:
        outdeg[a] += 1

    layer = layers(connected, edges)
    maxlayer = max(layer.values(), default=-1)
    for t in lonely:
        layer[t] = maxlayer + 2

    # 列内按出现顺序排，算坐标
    cols = defaultdict(list)
    for n in connected + lonely:
        cols[layer[n]].append(n)

    geo, ids = {}, {}
    for L, members in cols.items():
        y = 40
        for n in members:
            info = parts.get(n, {"type": "", "desc": ""})
            kind = kind_of(n, info["type"])
            style, w, h = SHAPES[kind]
            if kind == "header":
                h = max(60, 46 * outdeg[n])
            geo[n] = (60 + L * 190 + (110 - w) / 2, y, w, h, style, kind)
            y += h + (50 if "verticalLabelPosition" in style else 30)
            ids[n] = f"n{len(ids) + 1}"

    mxfile = ET.Element("mxfile", host="table_to_drawio.py")
    diagram = ET.SubElement(mxfile, "diagram", name=title, id="d1")
    model = ET.SubElement(diagram, "mxGraphModel", grid="1", gridSize="10",
                          page="0", arrows="1", connect="1")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    for n, (x, y, w, h, style, kind) in geo.items():
        info = parts.get(n, {"type": "", "desc": ""})
        label = n + (f"<br><font style='font-size:10px'>{info['desc']}</font>" if info["desc"] else "")
        st = style + "whiteSpace=wrap;html=1;fontSize=11;"
        if n in missing:
            st += "dashed=1;strokeColor=#d62728;fontColor=#d62728;"
        elif n in lonely:
            st += "strokeColor=#999999;fontColor=#999999;"
        elif kind == "header":
            st += "fillColor=#dae8fc;strokeColor=#6c8ebf;"
        obj = ET.SubElement(root, "object", id=ids[n], label=label,
                            tag=n, type=info["type"], desc=info["desc"])
        cell = ET.SubElement(obj, "mxCell", style=st, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=f"{x:.0f}", y=f"{y:.0f}",
                      width=str(w), height=str(h), **{"as": "geometry"})

    color = {}
    for i, (a, b, line) in enumerate(edges, 1):
        c = color.setdefault(line, PALETTE[len(color) % len(PALETTE)])
        st = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endSize=6;"
              f"strokeColor={c};strokeWidth=2;fontSize=9;fontColor={c};")
        cell = ET.SubElement(root, "mxCell", id=f"e{i}", value=line, style=st,
                             edge="1", parent="1", source=ids[a], target=ids[b])
        ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})

    return mxfile, missing, lonely, color


def main():
    ap = argparse.ArgumentParser(description="部品表 + 连接表 → draw.io")
    ap.add_argument("parts_csv")
    ap.add_argument("edges_csv")
    ap.add_argument("-o", "--out", help="输出文件名（默认: 连接表名.drawio）")
    args = ap.parse_args()

    parts = load_parts(args.parts_csv)
    edges = load_edges(args.edges_csv)
    out = Path(args.out or Path(args.edges_csv).with_suffix(".drawio"))

    dup = len(edges) - len(set(edges))
    tree, missing, lonely, color = build(parts, edges, out.stem)
    ET.indent(tree)
    ET.ElementTree(tree).write(out, encoding="utf-8", xml_declaration=False)

    print(f"部品 {len(parts)} 个，连接 {len(edges)} 条，管线种类 {len(color)} 种")
    if dup:
        print(f"⚠ 重复的连接: {dup} 条")
    if missing:
        print(f"⚠ 部品表里没有（图上红色虚线）: {', '.join(missing)}")
    if lonely:
        print(f"⚠ 没有任何连接（图上灰色，最右列）: {', '.join(lonely)}")
    print(f"→ {out.resolve()}")


if __name__ == "__main__":
    main()
