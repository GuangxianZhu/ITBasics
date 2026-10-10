"""YouTube 字幕下载器（图形界面）

粘贴链接 → 查看有哪些字幕 → 选语言和格式 → 下载。
依赖：yt-dlp（启动.bat 会自动安装/更新）。不需要 ffmpeg。
"""
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "YouTube 字幕下载器"
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube字幕")

LANG_PRESETS = {
    "日语": "ja",
    "英语": "en",
    "简体中文": "zh-Hans",
    "繁体中文": "zh-Hant",
}


# ---------------------------------------------------------------- VTT 转换
TS_RE = re.compile(r"((?:\d+:)?\d{1,2}:\d{2}\.\d{3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}\.\d{3})")
TAG_RE = re.compile(r"<[^>]+>")


def _norm_ts(ts):
    """'01:02.345' / '00:01:02.345' -> '00:01:02,345'"""
    parts = ts.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    h, m, s = parts
    return f"{int(h):02d}:{int(m):02d}:{s.replace('.', ',')}"


def parse_vtt(path):
    """返回 [(start, end, [行...]), ...]，已去掉 <c> 等内联标签。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    cues, i = [], 0
    while i < len(lines):
        m = TS_RE.search(lines[i])
        if not m:
            i += 1
            continue
        start, end = _norm_ts(m.group(1)), _norm_ts(m.group(2))
        i += 1
        text = []
        # 只在真正的空行结束（自动字幕里常有只含空格的行，不能当成结束）
        while i < len(lines) and lines[i] != "" and not TS_RE.search(lines[i]):
            t = TAG_RE.sub("", lines[i])
            t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
            if t:
                text.append(t)
            i += 1
        cues.append((start, end, text))
    return cues


def dedupe_cues(cues):
    """YouTube 自动字幕是"滚动式"的：每条都重复上一条的行。只保留新出现的行。"""
    out, recent = [], []
    for start, end, text in cues:
        new = [t for t in text if t not in recent]
        if new:
            out.append((start, end, new))
            recent = (recent + new)[-4:]
    return out


def vtt_to_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for n, (s, e, text) in enumerate(cues, 1):
            f.write(f"{n}\n{s} --> {e}\n" + "\n".join(text) + "\n\n")


def vtt_to_txt(cues, path, with_time=False):
    with open(path, "w", encoding="utf-8") as f:
        for s, _e, text in cues:
            line = " ".join(text)
            if with_time:
                f.write(f"[{s.split(',')[0]}] {line}\n")
            else:
                f.write(line + "\n")


# ---------------------------------------------------------------- 界面
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x640")
        self.minsize(640, 520)
        self.q = queue.Queue()
        self.busy = False
        self._build()
        self.after(100, self._poll)

    # ---------- 布局
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        # 链接
        f = ttk.LabelFrame(root, text="① 视频链接（可多个，一行一个；播放列表也行）")
        f.pack(fill="x", **pad)
        self.url_box = tk.Text(f, height=3, wrap="none")
        self.url_box.pack(fill="x", padx=6, pady=6)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(row, text="从剪贴板粘贴", command=self._paste).pack(side="left")
        ttk.Button(row, text="清空", command=lambda: self.url_box.delete("1.0", "end")).pack(side="left", padx=4)
        self.btn_list = ttk.Button(row, text="查看可用字幕", command=self._on_list)
        self.btn_list.pack(side="right")

        # 语言
        f = ttk.LabelFrame(root, text="② 字幕语言")
        f.pack(fill="x", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        self.lang_vars = {}
        for name, code in LANG_PRESETS.items():
            v = tk.BooleanVar(value=code in ("ja", "en"))
            self.lang_vars[code] = v
            ttk.Checkbutton(row, text=f"{name} ({code})", variable=v).pack(side="left", padx=(0, 10))
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(row, text="其他语言代码（逗号分隔，all=全部）：").pack(side="left")
        self.extra_lang = ttk.Entry(row, width=24)
        self.extra_lang.pack(side="left")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="没有人工字幕时用自动字幕", variable=self.auto_var).pack(side="left", padx=10)

        # 格式
        f = ttk.LabelFrame(root, text="③ 输出格式（可多选）")
        f.pack(fill="x", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=6)
        self.fmt_srt = tk.BooleanVar(value=True)
        self.fmt_txt = tk.BooleanVar(value=True)
        self.fmt_txt_t = tk.BooleanVar(value=False)
        self.fmt_vtt = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="SRT（播放器字幕）", variable=self.fmt_srt).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(row, text="TXT 纯文本", variable=self.fmt_txt).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(row, text="TXT 带时间", variable=self.fmt_txt_t).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(row, text="保留原始 VTT", variable=self.fmt_vtt).pack(side="left")

        # 保存位置 + 高级
        f = ttk.LabelFrame(root, text="④ 保存位置")
        f.pack(fill="x", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=6)
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        ttk.Entry(row, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="选择…", command=self._choose_dir).pack(side="left", padx=4)
        ttk.Button(row, text="打开文件夹", command=self._open_dir).pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(row, text="遇到“请登录确认不是机器人”时，借用浏览器登录状态：").pack(side="left")
        self.cookie_var = tk.StringVar(value="不用")
        ttk.Combobox(row, textvariable=self.cookie_var, width=10, state="readonly",
                     values=["不用", "firefox", "edge", "chrome"]).pack(side="left")

        # 按钮
        row = ttk.Frame(root)
        row.pack(fill="x", **pad)
        self.btn_go = ttk.Button(row, text="⬇ 下载字幕", command=self._on_download)
        self.btn_go.pack(side="left", ipadx=12, ipady=4)
        ttk.Button(row, text="更新 yt-dlp", command=self._on_update).pack(side="right")
        self.progress = ttk.Progressbar(row, mode="indeterminate", length=160)
        self.progress.pack(side="left", padx=10)

        # 日志
        f = ttk.LabelFrame(root, text="日志")
        f.pack(fill="both", expand=True, **pad)
        self.log_box = tk.Text(f, height=10, wrap="word", state="disabled")
        sb = ttk.Scrollbar(f, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_box.pack(fill="both", expand=True, padx=(6, 0), pady=6)

    # ---------- 小工具
    def log(self, msg):
        self.q.put(("log", msg))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", val + "\n")
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "done":
                    self._set_busy(False)
                elif kind == "ask_lang":
                    self.extra_lang.delete(0, "end")
                    self.extra_lang.insert(0, val)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_busy(self, b):
        self.busy = b
        state = "disabled" if b else "normal"
        self.btn_go.configure(state=state)
        self.btn_list.configure(state=state)
        if b:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _paste(self):
        try:
            self.url_box.insert("end", self.clipboard_get().strip() + "\n")
        except tk.TclError:
            pass

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)

    def _open_dir(self):
        d = self.out_var.get()
        os.makedirs(d, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def _urls(self):
        return [u.strip() for u in self.url_box.get("1.0", "end").splitlines() if u.strip()]

    def _langs(self):
        langs = [c for c, v in self.lang_vars.items() if v.get()]
        langs += [x.strip() for x in self.extra_lang.get().split(",") if x.strip()]
        return langs

    def _ydl_base(self):
        opts = {"quiet": True, "no_warnings": False, "logger": _Logger(self.log)}
        c = self.cookie_var.get()
        if c != "不用":
            opts["cookiesfrombrowser"] = (c,)
        return opts

    def _run(self, fn, *a):
        if self.busy:
            return
        self._set_busy(True)

        def wrap():
            try:
                fn(*a)
            except Exception as e:  # noqa: BLE001
                self.log(f"❌ 出错：{e}")
                hint = _hint(str(e))
                if hint:
                    self.log("   提示：" + hint)
            finally:
                self.q.put(("done", None))

        threading.Thread(target=wrap, daemon=True).start()

    # ---------- 动作：查看可用字幕
    def _on_list(self):
        urls = self._urls()
        if not urls:
            messagebox.showinfo(APP_TITLE, "先粘贴一个视频链接")
            return
        self._run(self._list_subs, urls[0])

    def _list_subs(self, url):
        import yt_dlp
        self.log(f"🔍 查询：{url}")
        opts = self._ydl_base() | {"skip_download": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            info = (info.get("entries") or [{}])[0] or {}
        self.log(f"🎬 标题：{info.get('title')}")
        manual = sorted((info.get("subtitles") or {}).keys())
        manual = [m for m in manual if m != "live_chat"]
        auto = info.get("automatic_captions") or {}
        orig = [k for k in auto if k.endswith("-orig")]
        self.log("   人工字幕：" + (", ".join(manual) if manual else "（无）"))
        if auto:
            base = [k.replace("-orig", "") for k in orig] or ["?"]
            self.log(f"   自动字幕：原声语言 {', '.join(base)}；可自动翻译成 {len(auto)} 种语言"
                     "（ja / en / zh-Hans 等都有）")
        else:
            self.log("   自动字幕：（无）")
        if not manual and not auto:
            self.log("   ⚠ 这个视频没有任何字幕。")

    # ---------- 动作：下载
    def _on_download(self):
        urls, langs = self._urls(), self._langs()
        if not urls:
            messagebox.showinfo(APP_TITLE, "先粘贴视频链接")
            return
        if not langs:
            messagebox.showinfo(APP_TITLE, "至少选一种语言")
            return
        if not any(v.get() for v in (self.fmt_srt, self.fmt_txt, self.fmt_txt_t, self.fmt_vtt)):
            messagebox.showinfo(APP_TITLE, "至少选一种输出格式")
            return
        self._run(self._download, urls, langs)

    def _download(self, urls, langs):
        import yt_dlp
        out = self.out_var.get()
        os.makedirs(out, exist_ok=True)
        opts = self._ydl_base() | {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": self.auto_var.get(),
            "subtitleslangs": langs,
            "subtitlesformat": "vtt/best",
            "outtmpl": os.path.join(out, "%(title).80B [%(id)s].%(ext)s"),
            "ignoreerrors": True,
        }
        total = 0
        with yt_dlp.YoutubeDL(opts) as ydl:
            for url in urls:
                self.log(f"⬇ 下载：{url}")
                info = ydl.extract_info(url, download=True)
                if not info:
                    self.log("   ⚠ 获取失败，跳过")
                    continue
                entries = info.get("entries") if info.get("_type") == "playlist" else [info]
                for ent in entries or []:
                    if ent:
                        total += self._convert(ent)
        self.log(f"✅ 完成，共生成 {total} 个文件 → {out}")

    def _convert(self, info):
        subs = info.get("requested_subtitles") or {}
        title = info.get("title", "")
        if not subs:
            self.log(f"   ⚠ 《{title}》没有所选语言的字幕")
            return 0
        n = 0
        for lang, d in subs.items():
            path = d.get("filepath")
            if not path or not os.path.exists(path):
                continue
            if not path.lower().endswith(".vtt"):
                self.log(f"   {lang}: 已保存 {os.path.basename(path)}（非 VTT，未转换）")
                n += 1
                continue
            cues = dedupe_cues(parse_vtt(path))
            stem = path[:-4]
            made = []
            if self.fmt_srt.get():
                vtt_to_srt(cues, stem + ".srt"); made.append("srt")
            if self.fmt_txt.get():
                vtt_to_txt(cues, stem + ".txt"); made.append("txt")
            if self.fmt_txt_t.get():
                vtt_to_txt(cues, stem + ".带时间.txt", with_time=True); made.append("带时间.txt")
            if self.fmt_vtt.get():
                made.append("vtt")
            else:
                os.remove(path)
            n += len(made)
            self.log(f"   {lang}: {len(cues)} 条 → {', '.join(made)}")
        return n

    # ---------- 动作：更新 yt-dlp
    def _on_update(self):
        self._run(self._update)

    def _update(self):
        self.log("🔄 更新 yt-dlp …")
        r = subprocess.run([sys.executable.replace("pythonw", "python"), "-m", "pip", "install", "-U", "yt-dlp"],
                           capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        last = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        self.log("   " + last[0])
        self.log("   重新打开程序后生效。")


class _Logger:
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        if msg.startswith("[info] Writing video subtitles"):
            self.log("   " + msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        self.log("   ⚠ " + msg)

    def error(self, msg):
        self.log("   ❌ " + msg)
        h = _hint(msg)
        if h:
            self.log("   提示：" + h)


def _hint(msg):
    m = msg.lower()
    if "sign in to confirm" in m or "not a bot" in m:
        return "YouTube 要求登录验证。在“借用浏览器登录状态”里选 firefox（Chrome/Edge 新版常读不了，需先关闭浏览器）。"
    if "429" in m or "too many requests" in m:
        return "请求太频繁，等几分钟再试，或借用浏览器登录状态。"
    if "cookie" in m and ("decrypt" in m or "could not copy" in m or "permission" in m):
        return "读取浏览器 cookie 失败：先完全关闭该浏览器再试，或改用 firefox。"
    if "unsupported url" in m:
        return "链接不对，确认是 YouTube 视频/播放列表地址。"
    if "http error 403" in m or "unable to extract" in m:
        return "可能是 yt-dlp 太旧，点右下角“更新 yt-dlp”。"
    return ""


def main():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        tk.Tk().withdraw()
        messagebox.showerror(APP_TITLE, "没有安装 yt-dlp。\n请双击 启动.bat，或运行：\npip install -U yt-dlp")
        return
    App().mainloop()


if __name__ == "__main__":
    main()
