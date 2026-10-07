"""统一查询器 界面。

窗口模式:  python app.py [数据文件夹]
命令行:    python app.py [数据文件夹] --cli A-101 [--machine 机台A]
           python app.py [数据文件夹] --check
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from core import QueryDB, export

DEFAULT_DIR = Path(__file__).parent / "sample_data"


def run_cli(db, key, machine, check):
    results = db.check() if check else db.query(key, machine)
    for name, df in results.items():
        print(f"\n===== {name}（{len(df)}）=====")
        print(df.to_string(index=False) if len(df) else "（无）")


def run_gui(db):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title("统一查询器")
    root.geometry("1100x650")
    state = {"db": db, "results": {}}

    bar = ttk.Frame(root, padding=6)
    bar.pack(fill="x")
    ttk.Label(bar, text="输入（报警号 / 符号 / 地址 / 参数号 / 配置项 / 关键字）:").pack(side="left")
    entry = ttk.Entry(bar, width=24)
    entry.pack(side="left", padx=4)
    machine = ttk.Combobox(bar, width=10, state="readonly")
    machine.pack(side="left", padx=4)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6)
    status = ttk.Label(root, padding=4)
    status.pack(fill="x")

    def refresh_machines():
        machine["values"] = ["全部机台"] + state["db"].machines
        machine.current(0)
        status["text"] = f"数据文件夹: {state['db'].data_dir}"

    def show(results):
        state["results"] = results
        for tab in nb.tabs():
            nb.forget(tab)
        for name, df in results.items():
            frame = ttk.Frame(nb)
            cols = list(df.columns)
            tree = ttk.Treeview(frame, columns=cols, show="headings")
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=max(80, min(260, len(str(c)) * 18)), anchor="w")
            for row in df.itertuples(index=False):
                tag = ("bad",) if any("不存在" in str(v) for v in row) else ()
                tree.insert("", "end", values=list(row), tags=tag)
            tree.tag_configure("bad", foreground="red")
            ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            xs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
            tree.grid(row=0, column=0, sticky="nsew")
            ys.grid(row=0, column=1, sticky="ns")
            xs.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            nb.add(frame, text=f"{name}（{len(df)}）")

    def do_query(_=None):
        key = entry.get().strip()
        if not key:
            return
        m = machine.get()
        show(state["db"].query(key, None if m == "全部机台" else m))

    def do_check():
        show(state["db"].check())

    def do_export():
        if not state["results"]:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel", "*.xlsx")])
        if path:
            export(state["results"], path)
            status["text"] = f"已导出: {path}"

    def do_reload(new_dir=None):
        try:
            state["db"] = QueryDB(new_dir or state["db"].data_dir)
            refresh_machines()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    def do_open():
        d = filedialog.askdirectory()
        if d:
            do_reload(d)

    for text, cmd in [("查询", do_query), ("一致性检查", do_check), ("导出Excel", do_export),
                      ("重新读取", do_reload), ("选择文件夹", do_open)]:
        ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
    entry.bind("<Return>", do_query)

    refresh_machines()
    entry.focus()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default=DEFAULT_DIR)
    ap.add_argument("--cli", metavar="关键字")
    ap.add_argument("--machine")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)
    db = QueryDB(a.data_dir)
    if a.cli or a.check:
        run_cli(db, a.cli, a.machine, a.check)
    else:
        run_gui(db)


if __name__ == "__main__":
    sys.exit(main())
