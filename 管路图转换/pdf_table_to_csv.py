"""
pdf_table_to_csv.py — 把 PDF 里的表格（如 控制对象表）提取成 CSV

用法:
    python pdf_table_to_csv.py 控制对象表.pdf
    python pdf_table_to_csv.py 控制对象表.pdf --pages 3-8        # 只处理第3~8页
    python pdf_table_to_csv.py 控制对象表.pdf --no-lines         # 表格没有画格线时

依赖:
    pip install pdfplumber

输出（和 PDF 同一个文件夹下的 <PDF名>_tables/）:
    tables_main.csv    列数和第一张表相同的表格，跨页合并成一张（重复的表头自动去掉）
    table_pX_N.csv     列数不同的其他表格，单独保存
    preview.txt        每张表前几行的预览

注意: 只能处理"文字 PDF"（文字能用鼠标选中的）。扫描件需要先 OCR。
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("缺少 pdfplumber  →  pip install pdfplumber")


def parse_pages(spec, n):
    if not spec:
        return list(range(n))
    pages = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.update(range(int(a) - 1, int(b)))
        else:
            pages.add(int(part) - 1)
    return sorted(p for p in pages if 0 <= p < n)


def clean(row):
    return [" ".join((c or "").split()) for c in row]


def main():
    ap = argparse.ArgumentParser(description="PDF 表格 → CSV")
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="页码范围，例如 1-5,8")
    ap.add_argument("--no-lines", action="store_true",
                    help="按文字对齐找表格（表格没有格线时用）")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    outdir = pdf_path.with_name(pdf_path.stem + "_tables")
    outdir.mkdir(exist_ok=True)

    settings = {}
    if args.no_lines:
        settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}

    main_rows, header, ncol = [], None, None
    extras, preview = [], []
    text_chars = 0

    with pdfplumber.open(pdf_path) as pdf:
        pages = parse_pages(args.pages, len(pdf.pages))
        for pi in pages:
            page = pdf.pages[pi]
            text_chars += len(page.chars)
            for ti, table in enumerate(page.extract_tables(settings), 1):
                rows = [clean(r) for r in table]
                rows = [r for r in rows if any(r)]
                if not rows:
                    continue
                preview.append(f"--- 第{pi + 1}页 表{ti}: {len(rows)}行 × {len(rows[0])}列")
                preview += ["  " + " | ".join(c[:15] for c in r) for r in rows[:4]]

                if header is None:
                    header, ncol = rows[0], len(rows[0])
                    main_rows.append(header)
                    rows = rows[1:]
                if len(rows) and len(rows[0]) == ncol:
                    if rows[0] == header:          # 每页重复的表头
                        rows = rows[1:]
                    main_rows += rows
                else:
                    extras.append((pi + 1, ti, rows))

    if text_chars == 0:
        print("⚠ PDF 里没有文字，可能是扫描件。需要先做 OCR，本脚本无法处理。")
        return

    if len(main_rows) <= 1 and not extras:
        print("没找到表格。如果表格没有画格线，试试加 --no-lines")
        return

    def write(name, rows):
        with (outdir / name).open("w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)

    write("tables_main.csv", main_rows)
    for p, t, rows in extras:
        write(f"table_p{p}_{t}.csv", rows)
    (outdir / "preview.txt").write_text("\n".join(preview), encoding="utf-8")

    print("\n".join(preview[:40]))
    print(f"\n主表: {len(main_rows) - 1} 行 × {ncol} 列 → tables_main.csv")
    if extras:
        print(f"其他表格: {len(extras)} 个（列数不同，单独保存）")
    print(f"保存在: {outdir.resolve()}")
    print("\n下一步: 在 Excel 里打开 tables_main.csv，确认后整理成 部品表.csv（位号, 种类, 说明）")


if __name__ == "__main__":
    main()
