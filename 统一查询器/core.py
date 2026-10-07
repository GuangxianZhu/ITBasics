"""统一查询器 核心逻辑：读取 Excel → 建立关系 → 查询 / 一致性检查 / 导出。

换成实际文件时，基本只需要改下面的【适配设置】。
"""
import re
from pathlib import Path
import pandas as pd

# ======================== 【适配设置】 ========================
# file: 文件名（可用通配符，如 "报警*.xlsx" 可一次读多个文件）
# cols: 标准字段 → 实际列名。id/name 必填，其余为“引用其他文件的列”
FILES = {
    "alarm":  {"file": "报警.xlsx",
               "cols": {"id": "报警号", "name": "报警内容",
                        "symbol": "触发符号", "param": "相关参数"}},
    "param":  {"file": "参数.xlsx",
               "cols": {"id": "参数号", "name": "参数名", "symbol": "相关符号"}},
    "config": {"file": "固定配置.xlsx",
               "cols": {"id": "配置项", "name": "说明",
                        "alarm": "关联报警", "symbol": "关联符号"}},
    "symbol": {"file": "地址符号.xlsx",
               "cols": {"id": "符号", "name": "说明"}},
}
MACHINE_PREFIX = "机台"          # 地址符号文件里，以此开头的列 = 各机台的地址
SEP = r"[,，、;；/\s]+"           # 一个单元格里写多个引用时的分隔符
# =============================================================

LABEL = {"alarm": "报警", "param": "参数", "config": "固定配置", "symbol": "符号"}


def norm(v) -> str:
    """统一写法：去空格、转大写、1001.0 → 1001。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s.upper()


def split_refs(v) -> list[str]:
    return [norm(x) for x in re.split(SEP, str(v)) if norm(x)] if norm(v) else []


class QueryDB:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.tables: dict[str, pd.DataFrame] = {}
        self.edges = pd.DataFrame(columns=["src_kind", "src", "dst_kind", "dst"])
        self.addr = pd.DataFrame(columns=["符号", "机台", "地址"])
        self.machines: list[str] = []
        self.load()

    # ---------- 读取 ----------
    def _read(self, pattern):
        frames = []
        for path in sorted(self.data_dir.glob(pattern)):
            for sheet, df in pd.read_excel(path, sheet_name=None, dtype=str).items():
                df = df.dropna(how="all")
                df["来源"] = f"{path.name}/{sheet}"
                frames.append(df)
        if not frames:
            raise FileNotFoundError(f"找不到文件: {self.data_dir / pattern}")
        return pd.concat(frames, ignore_index=True).fillna("")

    def load(self):
        edges = []
        for kind, spec in FILES.items():
            df = self._read(spec["file"])
            cols = spec["cols"]
            missing = [c for c in cols.values() if c not in df.columns]
            if missing:
                raise KeyError(f"{spec['file']} 缺少列: {missing}（请改 core.py 的适配设置）")
            df["_id"] = df[cols["id"]].map(norm)
            df = df[df["_id"] != ""].reset_index(drop=True)
            self.tables[kind] = df
            for ref_kind, col in cols.items():
                if ref_kind in ("id", "name"):
                    continue
                for src, cell in zip(df["_id"], df[col]):
                    edges += [(kind, src, ref_kind, d) for d in split_refs(cell)]
        self.edges = pd.DataFrame(edges, columns=self.edges.columns).drop_duplicates()

        sym = self.tables["symbol"]
        self.machines = [c for c in sym.columns if str(c).startswith(MACHINE_PREFIX)]
        if self.machines:
            long = sym.melt(id_vars="_id", value_vars=self.machines,
                            var_name="机台", value_name="地址")
            long["地址"] = long["地址"].map(norm)
            self.addr = long[long["地址"] != ""].rename(columns={"_id": "符号"})

    # ---------- 关系 ----------
    def linked(self, kind, ids, want):
        """与 (kind, ids) 直接相连的 want 类型的 id（两个方向都查）。"""
        ids = set(ids)
        e = self.edges
        fwd = e[(e.src_kind == kind) & e.src.isin(ids) & (e.dst_kind == want)].dst
        bwd = e[(e.dst_kind == kind) & e.dst.isin(ids) & (e.src_kind == want)].src
        return set(fwd) | set(bwd)

    def _rows(self, kind, ids, machine=None):
        df = self.tables[kind]
        out = df[df["_id"].isin(ids)].copy()
        lost = sorted(set(ids) - set(df["_id"]))
        if lost:   # 被引用了，但文件里不存在
            filler = pd.DataFrame({"_id": lost})
            filler[FILES[kind]["cols"]["id"]] = lost
            filler[FILES[kind]["cols"]["name"]] = "（文件中不存在！）"
            out = pd.concat([out, filler], ignore_index=True).fillna("")
        if kind == "symbol" and machine:
            out = out.drop(columns=[m for m in self.machines if m != machine])
        return out.drop(columns="_id")

    # ---------- 查询 ----------
    def find(self, key):
        """判断输入的是什么：返回 [(kind, id), ...]"""
        k = norm(key)
        hits = [(kind, k) for kind, df in self.tables.items() if k in set(df["_id"])]
        for s in self.addr[self.addr["地址"] == k]["符号"].unique():
            hits.append(("symbol", s))
        return hits

    def search(self, key):
        """模糊搜索：编号或名称里包含关键字的全部列出。"""
        k = norm(key)
        rows = []
        for kind, df in self.tables.items():
            name_col = FILES[kind]["cols"]["name"]
            m = df["_id"].str.contains(k, regex=False) | \
                df[name_col].str.upper().str.contains(k, regex=False)
            for _, r in df[m].iterrows():
                rows.append({"类型": LABEL[kind], "编号": r["_id"], "名称": r[name_col]})
        return pd.DataFrame(rows, columns=["类型", "编号", "名称"])

    def query(self, key, machine=None):
        """返回 {表名: DataFrame}。找不到时返回模糊搜索候选。"""
        hits = self.find(key)
        if not hits:
            return {"候选（模糊匹配）": self.search(key)}

        res = {"alarm": set(), "symbol": set(), "param": set(), "config": set()}
        for kind, i in hits:
            res[kind].add(i)
            if kind == "alarm":
                res["symbol"] |= self.linked("alarm", [i], "symbol")
                res["param"] |= self.linked("alarm", [i], "param")
                res["param"] |= self.linked("symbol", res["symbol"], "param")
                res["config"] |= self.linked("alarm", [i], "config")
            elif kind == "symbol":
                res["alarm"] |= self.linked("symbol", [i], "alarm")
                res["param"] |= self.linked("symbol", [i], "param")
            elif kind == "param":
                res["symbol"] |= self.linked("param", [i], "symbol")
                res["alarm"] |= self.linked("param", [i], "alarm")
                res["alarm"] |= self.linked("symbol", res["symbol"], "alarm")
            elif kind == "config":
                res["alarm"] |= self.linked("config", [i], "alarm")
                res["symbol"] |= self.linked("config", [i], "symbol")
            res["config"] |= self.linked("symbol", res["symbol"], "config")

        out = {}
        for kind in ("alarm", "symbol", "param", "config"):
            if res[kind]:
                title = "符号与地址" if kind == "symbol" else LABEL[kind]
                out[title] = self._rows(kind, res[kind], machine)
        return out

    # ---------- 一致性检查 ----------
    def check(self):
        e = self.edges
        out = {}
        for kind in ("symbol", "param", "alarm"):
            bad = e[(e.dst_kind == kind) & ~e.dst.isin(self.tables[kind]["_id"])]
            if len(bad):
                out[f"引用了不存在的{LABEL[kind]}"] = pd.DataFrame({
                    "引用方": bad.src_kind.map(LABEL), "编号": bad.src, "不存在的": bad.dst})
        used = set(e[e.dst_kind == "symbol"].dst) | set(e[e.src_kind == "symbol"].src)
        sym = self.tables["symbol"]
        unused = sym[~sym["_id"].isin(used)]
        if len(unused):
            out["没被任何文件引用的符号"] = unused.drop(columns="_id")
        if self.machines:
            gap = sym[(sym[self.machines].apply(lambda c: c.map(norm)) == "").any(axis=1)]
            if len(gap):
                out["部分机台缺地址的符号"] = gap.drop(columns="_id")
        return out or {"结果": pd.DataFrame({"信息": ["没有发现问题"]})}


def export(results: dict, path):
    with pd.ExcelWriter(path) as w:
        for name, df in results.items():
            df.to_excel(w, sheet_name=name[:31], index=False)
