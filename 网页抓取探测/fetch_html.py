"""
fetch_html.py  —  抓取内网网页，保存 HTML，并输出"这个页面是怎么做的"的结构摘要

用法:
    python fetch_html.py                      # 运行后再输入网址
    python fetch_html.py 网址
    python fetch_html.py 网址 --auth sspi     # 指定登录方式
    python fetch_html.py 网址 --no-proxy      # 内网地址被公司代理挡住时
    python fetch_html.py 网址 --insecure      # https 证书报错时

登录方式 --auth:
    auto  (默认) 先不登录试一次，返回 401 再用 Windows 账号自动登录
    none   不登录
    sspi   用当前 Windows 登录身份（打开网页不用输密码的系统，多半是这种）
    ntlm   手动输入 域\\用户名 和密码
    basic  浏览器弹出用户名密码小窗口的那种

依赖:
    pip install requests beautifulsoup4
    pip install requests-negotiate-sspi     # 用 sspi 时需要（仅 Windows）
    pip install requests-ntlm               # 用 ntlm 时需要

结果保存在  probe_<主机名>_<时间>/  文件夹里:
    page.html      原始 HTML（可以用浏览器或 VS Code 打开看）
    headers.json   服务器返回的响应头
    summary.txt    结构摘要（和屏幕输出一样）
    table_N.csv    页面里的每个表格（Excel 可直接打开）

注意: 只做 GET 读取，不会提交任何表单。请勿短时间内反复大量运行。
"""
import argparse
import csv
import datetime
import getpass
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    sys.exit("缺少 requests  →  pip install requests")

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# 在 <script> 里找"像是数据接口"的地址
API_HINT = re.compile(
    r"""["']([^"'\s<>]*?(?:/api/|\.ashx|\.asmx|\.svc|\.json|/Get[A-Z]\w*|/Search\w*|/Load\w*|/List\w*)[^"'\s<>]*)["']"""
)


# ---------------------------------------------------------------- 输出
class Tee:
    """同时打印到屏幕和 summary.txt"""

    def __init__(self):
        self.lines = []

    def __call__(self, *args):
        text = " ".join(str(a) for a in args)
        print(text)
        self.lines.append(text)

    def save(self, path):
        path.write_text("\n".join(self.lines), encoding="utf-8")


# ---------------------------------------------------------------- 请求
def make_auth(mode):
    if mode == "none":
        return None
    if mode == "sspi":
        from requests_negotiate_sspi import HttpNegotiateAuth
        return HttpNegotiateAuth()
    if mode == "ntlm":
        from requests_ntlm import HttpNtlmAuth
        user = input("用户名 (域\\用户名): ")
        return HttpNtlmAuth(user, getpass.getpass("密码: "))
    if mode == "basic":
        user = input("用户名: ")
        return (user, getpass.getpass("密码: "))
    raise ValueError(mode)


PIP_NAME = {"requests_negotiate_sspi": "requests-negotiate-sspi",
            "requests_ntlm": "requests-ntlm"}


def fetch(url, auth_mode, session, out):
    modes = ["none", "sspi"] if auth_mode == "auto" else [auth_mode]
    resp = None
    for m in modes:
        try:
            auth = make_auth(m)
        except ImportError as e:
            out(f"[跳过 {m}] 缺少库 → pip install {PIP_NAME.get(e.name, e.name)}")
            continue
        try:
            resp = session.get(url, auth=auth, timeout=30)
        except requests.exceptions.ProxyError:
            out("连接被代理挡住了，试试加 --no-proxy")
            raise
        except requests.exceptions.SSLError:
            out("https 证书校验失败，试试加 --insecure")
            raise
        except requests.exceptions.ConnectionError:
            out("连不上服务器。检查: 网址拼写 / 是否在公司内网或VPN / 是否需要 --no-proxy")
            raise
        out(f"[登录方式 {m}] HTTP {resp.status_code}")
        if resp.status_code != 401:
            return resp, m
        out("   服务器要求的认证:", resp.headers.get("WWW-Authenticate"))
    return resp, (modes[-1] if resp is not None else None)


def fix_encoding(resp):
    # requests 对没写 charset 的 HTML 默认按 ISO-8859-1，日文会乱码
    ctype = resp.headers.get("Content-Type", "")
    if "charset" not in ctype.lower():
        m = re.search(rb'charset=["\']?([\w-]+)', resp.content[:3000], re.I)
        resp.encoding = m.group(1).decode() if m else resp.apparent_encoding


# ---------------------------------------------------------------- 分析
def cell_text(cell):
    return " ".join(cell.get_text(" ", strip=True).split())


def analyze(html, base_url, outdir, out):
    if BeautifulSoup is None:
        out("\n(未安装 beautifulsoup4，只保存了原始 HTML。pip install beautifulsoup4 后可得到结构摘要)")
        return
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc

    out("\n========== 基本信息 ==========")
    out("标题:", soup.title.get_text(strip=True) if soup.title else "(无)")
    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
    out(f"正文文字量: {len(body_text)} 字")

    # ---- 推测页面是怎么做的
    out("\n========== 页面类型推测 ==========")
    hints = []
    if soup.find("input", {"name": "__VIEWSTATE"}):
        hints.append("ASP.NET WebForms（有 __VIEWSTATE）: 翻页/搜索是整页回发，抓取要带上隐藏字段，相对麻烦")
    if soup.find("input", {"name": "__RequestVerificationToken"}):
        hints.append("ASP.NET MVC（有 __RequestVerificationToken）")
    frames = soup.find_all(["frame", "iframe"])
    if frames:
        hints.append(f"用了 frame/iframe（{len(frames)} 个）: 真正的数据多半在子页面里，见下方地址")
    scripts = soup.find_all("script")
    if len(body_text) < 200 and scripts:
        hints.append("正文几乎为空但有脚本: 数据可能是 JavaScript 加载后才显示的 → 用浏览器 F12 的 Network 找数据请求")
    if soup.find_all("table") and len(body_text) >= 200:
        hints.append("数据直接写在 HTML 表格里: 最好抓，见下方表格")
    for h in hints or ["(没有明显特征，看 page.html 原文)"]:
        out(" •", h)

    if frames:
        out("\n========== 子页面 (frame/iframe) ==========")
        for f in frames:
            src = f.get("src")
            if src:
                out(" ", urljoin(base_url, src))

    # ---- 表格
    tables = soup.find_all("table")
    out(f"\n========== 表格: {len(tables)} 个 ==========")
    saved = 0
    for i, t in enumerate(tables, 1):
        rows = []
        for tr in t.find_all("tr"):
            # 只取本表的单元格，不深入嵌套表格
            if tr.find_parent("table") is not t:
                continue
            cells = [cell_text(c) for c in tr.find_all(["th", "td"], recursive=False)]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        ncol = max(len(r) for r in rows)
        out(f"\n[表格 {i}]  {len(rows)} 行 × 最多 {ncol} 列"
            + ("  (id=" + t.get("id") + ")" if t.get("id") else ""))
        for r in rows[:3]:
            out("   ", " | ".join(c[:20] for c in r[:8]) + (" | …" if len(r) > 8 else ""))
        if len(rows) >= 2:
            path = outdir / f"table_{i}.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as fp:
                csv.writer(fp).writerows(rows)
            saved += 1
    if saved:
        out(f"\n→ 已把 {saved} 个表格存成 table_N.csv")

    # ---- 表单（搜索条件通常在这里）
    forms = soup.find_all("form")
    out(f"\n========== 表单: {len(forms)} 个 ==========")
    for i, fm in enumerate(forms, 1):
        out(f"[表单 {i}] method={fm.get('method', 'GET').upper()}  action={urljoin(base_url, fm.get('action') or '')}")
        for inp in fm.find_all(["input", "select", "textarea"]):
            name = inp.get("name")
            if not name:
                continue
            kind = inp.get("type", inp.name)
            if kind == "hidden":
                out(f"    {name}  (hidden)")
            elif inp.name == "select":
                opts = [o.get_text(strip=True) for o in inp.find_all("option")][:6]
                out(f"    {name}  (下拉: {', '.join(opts)}{' …' if len(opts) == 6 else ''})")
            else:
                out(f"    {name}  ({kind})")

    # ---- 脚本和疑似接口
    out(f"\n========== 脚本: {len(scripts)} 个 ==========")
    api = set()
    for s in scripts:
        if s.get("src"):
            out("  外部:", urljoin(base_url, s["src"]))
        else:
            api.update(API_HINT.findall(s.get_text()))
    if api:
        out("\n疑似数据接口（直接请求这些地址可能比解析 HTML 更简单）:")
        for a in sorted(api)[:30]:
            out("  ", urljoin(base_url, a))

    # ---- 链接
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "#", "mailto:")):
            if href.startswith("javascript:__doPostBack"):
                links.append(f"(回发) {a.get_text(strip=True)[:30]}  {href[:80]}")
            continue
        full = urljoin(base_url, href)
        if urlparse(full).netloc == host:
            links.append(f"{a.get_text(strip=True)[:30]:<30}  {full}")
    uniq = list(dict.fromkeys(links))
    out(f"\n========== 站内链接: {len(uniq)} 个（显示前 40） ==========")
    for l in uniq[:40]:
        out("  ", l)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="抓取网页并分析结构")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--auth", default="auto", choices=["auto", "none", "sspi", "ntlm", "basic"])
    ap.add_argument("--no-proxy", action="store_true", help="不走系统/环境变量里的代理")
    ap.add_argument("--insecure", action="store_true", help="不校验 https 证书")
    args = ap.parse_args()

    url = args.url or input("网址: ").strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) fetch_html.py"
    if args.no_proxy:
        session.trust_env = False
    if args.insecure:
        session.verify = False
        requests.packages.urllib3.disable_warnings()

    out = Tee()
    out("请求:", url)
    resp, mode = fetch(url, args.auth, session, out)
    if resp is None:
        sys.exit("没有发出请求（缺少登录用的库）")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    host = re.sub(r"[^\w.-]", "_", urlparse(url).netloc)
    outdir = Path(f"probe_{host}_{stamp}")
    outdir.mkdir()

    fix_encoding(resp)
    out("最终地址:", resp.url, "（有跳转）" if resp.history else "")
    out("Content-Type:", resp.headers.get("Content-Type"))
    out("编码:", resp.encoding)
    out("服务器:", resp.headers.get("Server"), "|", resp.headers.get("X-Powered-By") or "",
        resp.headers.get("X-AspNet-Version") or "")

    (outdir / "headers.json").write_text(
        json.dumps({"status": resp.status_code, "url": resp.url, "auth": mode,
                    "headers": dict(resp.headers)}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype:
        (outdir / "data.json").write_text(resp.text, encoding="utf-8")
        out("\n返回的是 JSON 数据，已存为 data.json")
    else:
        (outdir / "page.html").write_text(resp.text, encoding="utf-8")
        if resp.status_code == 200:
            analyze(resp.text, resp.url, outdir, out)
        else:
            out(f"\nHTTP {resp.status_code}，只保存了返回内容，没有做分析")

    out.save(outdir / "summary.txt")
    print(f"\n结果保存在: {outdir.resolve()}")


if __name__ == "__main__":
    main()
