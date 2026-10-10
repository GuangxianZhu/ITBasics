"""主窗口：左边选项，右边任务队列 + 日志。界面只读写 Task 字段，不直接碰 yt-dlp。"""
import copy
import os
import queue
import subprocess
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QApplication,
)

from core import env
from core.manager import Manager
from core.probe import probe
from core.options import parse_time
from core.task import DONE, FAILED, CANCELLED, FINISHED, DownloadOptions, Task
from ui.dialogs import PlaylistDialog, SettingsDialog

DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube下载")
QUALITIES = [("最佳", "best"), ("2160p (4K)", "2160"), ("1440p", "1440"), ("1080p", "1080"),
             ("720p", "720"), ("480p", "480"), ("360p", "360")]
AUDIO_FMTS = [("MP3（通用）", "mp3"), ("M4A / AAC", "m4a"), ("Opus（体积小）", "opus"), ("原始（不转码）", "original")]
NAME_TMPLS = [("标题 [ID]", "title_id"), ("标题", "title"), ("上传者 - 标题", "uploader_title")]
COOKIES = [("不用", ""), ("Firefox", "firefox"), ("Edge", "edge"), ("Chrome", "chrome")]
SUB_PRESETS = [("日语", "ja"), ("英语", "en"), ("简体中文", "zh-Hans"), ("繁体中文", "zh-Hant")]
COLS = ["#", "标题", "类型", "进度", "速度", "剩余", "状态"]

STYLE = """
QMainWindow, QWidget { font-size: 10pt; }
QGroupBox { font-weight: 600; border: 1px solid #d0d4da; border-radius: 6px; margin-top: 10px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton#go { background: #2563eb; color: white; font-size: 11pt; font-weight: 600;
                 padding: 9px; border-radius: 6px; border: none; }
QPushButton#go:hover { background: #1d4ed8; }
QPushButton#go:disabled { background: #9db5ea; }
QLabel#title { font-size: 11pt; font-weight: 600; }
QLabel#meta { color: #555; }
QFrame#preview { background: #f6f7f9; border-radius: 6px; }
QProgressBar { border: 1px solid #cfd4db; border-radius: 4px; text-align: center; height: 16px; }
QProgressBar::chunk { background: #22a06b; border-radius: 3px; }
"""


def _combo(items, current=None):
    c = QComboBox()
    for label, val in items:
        c.addItem(label, val)
    if current is not None:
        i = c.findData(current)
        if i >= 0:
            c.setCurrentIndex(i)
    return c


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube 下载器")
        self.resize(1200, 820)
        self.setStyleSheet(STYLE)
        self.cfg = env.load_config()
        self.ffmpeg = env.ffmpeg_path()
        self.logq = queue.Queue()
        self.probeq = queue.Queue()
        self.probes = {}          # url -> ProbeResult
        self.rows = {}            # task.id -> row
        self.playlist_sel = {}    # url -> (items 字符串, 已选序号列表)
        self.manager = Manager(self._log_from_worker, self.ffmpeg, workers=self.cfg.get("workers", 2))

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._left_panel())
        split.addWidget(self._right_panel())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([480, 700])
        self.setCentralWidget(split)
        self._status_bar()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(300)

    # ================================================================ 左侧
    def _left_panel(self):
        c = self.cfg
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        # ① 链接
        g = QGroupBox("① 链接（可多个，一行一个）")
        v = QVBoxLayout(g)
        self.url_edit = QPlainTextEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_edit.setFixedHeight(64)
        v.addWidget(self.url_edit)
        h = QHBoxLayout()
        b = QPushButton("粘贴"); b.clicked.connect(self._paste); h.addWidget(b)
        b = QPushButton("清空"); b.clicked.connect(self.url_edit.clear); h.addWidget(b)
        h.addStretch()
        self.btn_probe = QPushButton("🔍 解析"); self.btn_probe.clicked.connect(self._on_probe)
        h.addWidget(self.btn_probe)
        v.addLayout(h)
        lay.addWidget(g)

        # 预览
        self.preview = QFrame(); self.preview.setObjectName("preview")
        ph = QHBoxLayout(self.preview)
        self.thumb = QLabel(); self.thumb.setFixedSize(176, 99); self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#e3e6ea;border-radius:4px;color:#888;")
        self.thumb.setText("预览")
        ph.addWidget(self.thumb)
        pv = QVBoxLayout()
        self.lbl_title = QLabel("粘贴链接后点「解析」"); self.lbl_title.setObjectName("title"); self.lbl_title.setWordWrap(True)
        self.lbl_meta = QLabel(""); self.lbl_meta.setObjectName("meta"); self.lbl_meta.setWordWrap(True)
        self.lbl_fmt = QLabel(""); self.lbl_fmt.setObjectName("meta"); self.lbl_fmt.setWordWrap(True)
        self.lbl_subs = QLabel(""); self.lbl_subs.setObjectName("meta"); self.lbl_subs.setWordWrap(True)
        for x in (self.lbl_title, self.lbl_meta, self.lbl_fmt, self.lbl_subs):
            pv.addWidget(x)
        self.btn_items = QPushButton("☑ 选择条目…"); self.btn_items.clicked.connect(self._on_pick_items)
        self.btn_items.setVisible(False)
        pv.addWidget(self.btn_items, 0, Qt.AlignLeft)
        pv.addStretch()
        ph.addLayout(pv, 1)
        lay.addWidget(self.preview)

        # ② 模式
        g = QGroupBox("② 下载什么")
        v = QVBoxLayout(g)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_video(c), "🎬 视频")
        self.tabs.addTab(self._tab_audio(c), "🎵 音频")
        self.tabs.addTab(self._tab_subs(c), "💬 字幕")
        self.tabs.setCurrentIndex({"video": 0, "audio": 1, "subs": 2}.get(c.get("mode", "video"), 0))
        v.addWidget(self.tabs)
        lay.addWidget(g)

        # ③ 附加选项
        g = QGroupBox("③ 附加选项")
        v = QVBoxLayout(g)
        h = QHBoxLayout()
        self.clip_chk = QCheckBox("只下片段")
        self.clip_chk.setChecked(c.get("clip_on", False))
        h.addWidget(self.clip_chk)
        self.clip_a = QLineEdit(c.get("clip_start", "")); self.clip_a.setPlaceholderText("开始 如 1:20")
        self.clip_b = QLineEdit(c.get("clip_end", "")); self.clip_b.setPlaceholderText("结束（空=末尾）")
        for e in (self.clip_a, self.clip_b):
            e.setMaximumWidth(110)
        h.addWidget(self.clip_a); h.addWidget(QLabel("到")); h.addWidget(self.clip_b); h.addStretch()
        v.addLayout(h)
        self.clip_precise = QCheckBox("精确到秒（重新编码，较慢）")
        self.clip_precise.setToolTip("不勾：从最近的关键帧切，速度快，但起止可能差几秒")
        self.clip_precise.setChecked(c.get("clip_precise", False))
        v.addWidget(self.clip_precise)
        def sync_clip(on):
            for x in (self.clip_a, self.clip_b, self.clip_precise):
                x.setEnabled(on)
        self.clip_chk.toggled.connect(sync_clip); sync_clip(self.clip_chk.isChecked())
        h = QHBoxLayout()
        h.addWidget(QLabel("写入文件："))
        self.thumb_chk = QCheckBox("封面"); self.thumb_chk.setChecked(c.get("embed_thumb", True))
        self.thumb_chk.setToolTip("MP4 / MP3 / M4A / Opus 支持；MKV 和“原始”音频不写")
        self.meta_chk = QCheckBox("标题作者等信息"); self.meta_chk.setChecked(c.get("add_meta", True))
        self.chap_chk = QCheckBox("章节"); self.chap_chk.setChecked(c.get("add_chapters", True))
        self.chap_chk.setToolTip("视频有章节时写入，播放器里可以按章节跳转（片段下载时不写）")
        for x in (self.thumb_chk, self.meta_chk, self.chap_chk):
            h.addWidget(x)
        h.addStretch()
        v.addLayout(h)
        self.archive_chk = QCheckBox("跳过下载过的（视频、音频分别记录）")
        self.archive_chk.setChecked(c.get("use_archive", True))
        v.addWidget(self.archive_chk)
        lay.addWidget(g)

        # ④ 保存
        g = QGroupBox("④ 保存")
        f = QFormLayout(g)
        h = QHBoxLayout()
        self.out_edit = QLineEdit(c.get("out_dir", DEFAULT_OUT))
        h.addWidget(self.out_edit, 1)
        b = QPushButton("选择…"); b.clicked.connect(self._choose_dir); h.addWidget(b)
        b = QPushButton("打开"); b.clicked.connect(lambda: self._open_dir(self.out_edit.text())); h.addWidget(b)
        f.addRow("位置", h)
        self.name_combo = _combo(NAME_TMPLS, c.get("name_tmpl", "title_id"))
        f.addRow("文件名", self.name_combo)
        self.playlist_chk = QCheckBox("链接是播放列表时，下载整个列表")
        self.playlist_chk.setChecked(c.get("playlist", False))
        f.addRow("", self.playlist_chk)
        self.cookie_combo = _combo(COOKIES, c.get("cookies", ""))
        self.cookie_combo.setToolTip("只在出现“请登录确认不是机器人”或频繁 429 时使用；Firefox 最稳")
        f.addRow("浏览器登录状态", self.cookie_combo)
        lay.addWidget(g)

        self.btn_go = QPushButton("⬇  加入队列并开始"); self.btn_go.setObjectName("go")
        self.btn_go.clicked.connect(self._on_add)
        lay.addWidget(self.btn_go)
        lay.addStretch()

        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(w)
        sa.setMinimumWidth(460)
        return sa

    def _tab_video(self, c):
        w = QWidget(); f = QFormLayout(w)
        self.q_combo = _combo(QUALITIES, c.get("quality", "1080"))
        f.addRow("画质（最高）", self.q_combo)
        self.cont_combo = _combo([("MP4（兼容性好）", "mp4"), ("MKV（画质优先）", "mkv")], c.get("container", "mp4"))
        f.addRow("格式", self.cont_combo)
        self.embed_chk = QCheckBox("把字幕嵌入视频（播放器里可开关）")
        self.embed_chk.setChecked(c.get("embed_subs", False))
        f.addRow("", self.embed_chk)
        self.embed_langs = QLineEdit(c.get("embed_langs", "en,ja,zh-Hans"))
        self.embed_langs.setPlaceholderText("语言代码，逗号分隔")
        self.embed_langs.setEnabled(self.embed_chk.isChecked())
        self.embed_chk.toggled.connect(self.embed_langs.setEnabled)
        f.addRow("字幕语言", self.embed_langs)
        return w

    def _tab_audio(self, c):
        w = QWidget(); f = QFormLayout(w)
        self.afmt_combo = _combo(AUDIO_FMTS, c.get("audio_fmt", "mp3"))
        f.addRow("格式", self.afmt_combo)
        self.kbps_combo = _combo([("320 kbps", "320"), ("192 kbps", "192"), ("128 kbps", "128")],
                                 c.get("audio_kbps", "192"))
        f.addRow("码率", self.kbps_combo)
        sync = lambda: self.kbps_combo.setEnabled(self.afmt_combo.currentData() == "mp3")  # noqa: E731
        self.afmt_combo.currentIndexChanged.connect(sync); sync()
        tip = QLabel("YouTube 原始音质约 128~160 kbps，选更高码率不会更清楚。")
        tip.setObjectName("meta"); tip.setWordWrap(True)
        f.addRow("", tip)
        return w

    def _tab_subs(self, c):
        w = QWidget(); v = QVBoxLayout(w)
        grid = QGridLayout()
        self.sub_chks = {}
        chosen = c.get("sub_langs", ["en"])
        for i, (label, code) in enumerate(SUB_PRESETS):
            cb = QCheckBox(f"{label} ({code})"); cb.setChecked(code in chosen)
            self.sub_chks[code] = cb
            grid.addWidget(cb, i // 2, i % 2)
        v.addLayout(grid)
        h = QHBoxLayout()
        h.addWidget(QLabel("其他语言代码"))
        self.sub_extra = QLineEdit(",".join(x for x in chosen if x not in self.sub_chks))
        self.sub_extra.setPlaceholderText("如 ko,fr；all=全部")
        h.addWidget(self.sub_extra)
        v.addLayout(h)
        self.sub_auto = QCheckBox("没有人工字幕时用自动字幕"); self.sub_auto.setChecked(c.get("sub_auto", True))
        self.sub_fb = QCheckBox("翻译字幕被限流时，改下视频原文字幕"); self.sub_fb.setChecked(c.get("sub_fallback", True))
        v.addWidget(self.sub_auto); v.addWidget(self.sub_fb)
        h = QHBoxLayout()
        h.addWidget(QLabel("输出："))
        fm = c.get("sub_formats", ["srt", "txt"])
        self.sub_fmt_chks = {}
        for label, key in [("SRT", "srt"), ("TXT", "txt"), ("TXT 带时间", "txt_t"), ("原始 VTT", "vtt")]:
            cb = QCheckBox(label); cb.setChecked(key in fm)
            self.sub_fmt_chks[key] = cb
            h.addWidget(cb)
        h.addStretch()
        v.addLayout(h)
        return w

    # ================================================================ 右侧
    def _right_panel(self):
        split = QSplitter(Qt.Vertical)

        top = QWidget(); v = QVBoxLayout(top); v.setContentsMargins(8, 8, 8, 0)
        h = QHBoxLayout()
        lbl = QLabel("任务队列"); lbl.setObjectName("title"); h.addWidget(lbl)
        h.addStretch()
        for text, fn in [("取消", self._on_cancel), ("重试", self._on_retry),
                         ("打开文件夹", self._on_open_task_dir), ("清除已完成", self._on_clear)]:
            b = QPushButton(text); b.clicked.connect(fn); h.addWidget(b)
        v.addLayout(h)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        for i, mode in enumerate([QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents,
                                  QHeaderView.Fixed, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                  QHeaderView.Interactive]):
            hh.setSectionResizeMode(i, mode)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(6, 170)
        self.table.doubleClicked.connect(self._on_open_task_dir)
        v.addWidget(self.table)
        split.addWidget(top)

        bot = QWidget(); v = QVBoxLayout(bot); v.setContentsMargins(8, 0, 8, 8)
        v.addWidget(QLabel("日志"))
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFont(QFont("Consolas", 9))
        v.addWidget(self.log_view)
        split.addWidget(bot)
        split.setSizes([460, 260])
        return split

    def _status_bar(self):
        sb = self.statusBar()
        ver = env.ytdlp_version() or "未安装"
        parts = [f"yt-dlp {ver}", "ffmpeg ✓" if self.ffmpeg else "ffmpeg ✗（视频合并/转 MP3 不可用）",
                 "deno ✓" if env.deno_path() else "deno ✗"]
        if not env.has_mutagen():
            parts.append("mutagen ✗（MP4/M4A 写不了封面）")
        self.env_label = QLabel("   ·   ".join(parts))
        sb.addWidget(self.env_label)
        b = QPushButton("⚙ 设置"); b.clicked.connect(self._on_settings)
        sb.addPermanentWidget(b)
        b = QPushButton("更新组件"); b.clicked.connect(self._on_update)
        sb.addPermanentWidget(b)

    # ================================================================ 动作
    def _urls(self):
        return [u.strip() for u in self.url_edit.toPlainText().splitlines() if u.strip()]

    def _paste(self):
        t = QApplication.clipboard().text().strip()
        if t:
            cur = self.url_edit.toPlainText().rstrip()
            self.url_edit.setPlainText((cur + "\n" if cur else "") + t)

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存位置", self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    @staticmethod
    def _open_dir(d):
        os.makedirs(d, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    def _collect(self):
        mode = ["video", "audio", "subs"][self.tabs.currentIndex()]
        langs = [k for k, cb in self.sub_chks.items() if cb.isChecked()]
        langs += [x.strip() for x in self.sub_extra.text().split(",") if x.strip()]
        embed_langs = [x.strip() for x in self.embed_langs.text().split(",") if x.strip()]
        o = DownloadOptions(
            mode=mode, out_dir=self.out_edit.text().strip() or DEFAULT_OUT,
            name_tmpl=self.name_combo.currentData(), playlist=self.playlist_chk.isChecked(),
            cookies=self.cookie_combo.currentData(),
            quality=self.q_combo.currentData(), container=self.cont_combo.currentData(),
            embed_subs=self.embed_chk.isChecked(),
            audio_fmt=self.afmt_combo.currentData(), audio_kbps=self.kbps_combo.currentData(),
            sub_langs=langs if mode == "subs" else embed_langs,
            sub_auto=self.sub_auto.isChecked(), sub_fallback=self.sub_fb.isChecked(),
            sub_formats=[k for k, cb in self.sub_fmt_chks.items() if cb.isChecked()],
            clip_start=self.clip_a.text().strip() if self.clip_chk.isChecked() else "",
            clip_end=self.clip_b.text().strip() if self.clip_chk.isChecked() else "",
            clip_precise=self.clip_precise.isChecked(),
            embed_thumb=self.thumb_chk.isChecked(), add_meta=self.meta_chk.isChecked(),
            add_chapters=self.chap_chk.isChecked(),
            ratelimit=self.cfg.get("ratelimit", 0), proxy=self.cfg.get("proxy", ""),
        )
        if self.archive_chk.isChecked() and mode != "subs":
            o.archive_path = env.archive_path(mode)
        self.cfg.update({
            "mode": mode, "out_dir": o.out_dir, "name_tmpl": o.name_tmpl, "playlist": o.playlist,
            "cookies": o.cookies, "quality": o.quality, "container": o.container,
            "embed_subs": o.embed_subs, "embed_langs": self.embed_langs.text(),
            "audio_fmt": o.audio_fmt, "audio_kbps": o.audio_kbps, "sub_langs": langs,
            "sub_auto": o.sub_auto, "sub_fallback": o.sub_fallback, "sub_formats": o.sub_formats,
            "clip_on": self.clip_chk.isChecked(), "clip_start": self.clip_a.text().strip(),
            "clip_end": self.clip_b.text().strip(), "clip_precise": o.clip_precise,
            "embed_thumb": o.embed_thumb, "add_meta": o.add_meta, "add_chapters": o.add_chapters,
            "use_archive": self.archive_chk.isChecked(),
        })
        env.save_config(self.cfg)
        return o

    def _on_add(self):
        urls = self._urls()
        if not urls:
            QMessageBox.information(self, "提示", "先粘贴视频链接")
            return
        o = self._collect()
        if o.mode == "subs" and not o.sub_langs:
            QMessageBox.information(self, "提示", "至少选一种字幕语言"); return
        if o.mode == "subs" and not o.sub_formats:
            QMessageBox.information(self, "提示", "至少选一种字幕输出格式"); return
        if o.mode != "subs" and o.clipped:
            try:
                a, b = parse_time(o.clip_start), parse_time(o.clip_end)
            except ValueError as e:
                QMessageBox.information(self, "提示", str(e)); return
            if a is not None and b is not None and b <= a:
                QMessageBox.information(self, "提示", "片段的结束时间要晚于开始时间"); return
            if len(urls) > 1:
                if QMessageBox.question(self, "确认", f"{len(urls)} 个链接都按同一个片段时间剪切？") != QMessageBox.Yes:
                    return
        if o.mode in ("video", "audio") and not self.ffmpeg and not (o.mode == "audio" and o.audio_fmt == "original"):
            if QMessageBox.question(self, "缺少 ffmpeg",
                                    "没有 ffmpeg，高画质视频无法合并音视频、也无法转 MP3。\n"
                                    "建议关闭程序后重新双击 启动.bat。\n\n仍然继续？") != QMessageBox.Yes:
                return
        for u in urls:
            t = Task(u, copy.deepcopy(o))
            if o.playlist and u in self.playlist_sel:
                t.opts.playlist_items = self.playlist_sel[u][0]
            p = self.probes.get(u)
            if p and p.title:
                t.title = p.title
            self.manager.add(t)
        self.url_edit.clear()

    def _on_probe(self):
        urls = self._urls()
        if not urls:
            QMessageBox.information(self, "提示", "先粘贴视频链接"); return
        url = urls[0]
        self.btn_probe.setEnabled(False)
        self.lbl_title.setText("解析中…"); self.lbl_meta.setText(""); self.lbl_fmt.setText(""); self.lbl_subs.setText("")
        cookies, pl, px = self.cookie_combo.currentData(), self.playlist_chk.isChecked(), self.cfg.get("proxy", "")
        self.btn_items.setVisible(False)
        threading.Thread(target=lambda: self.probeq.put(probe(url, cookies, pl, px)), daemon=True).start()

    def _show_probe(self, r):
        self.btn_probe.setEnabled(True)
        if r.error:
            self.lbl_title.setText("解析失败")
            self.lbl_meta.setText(r.error[:200])
            self._append_log(f"解析失败：{r.error}")
            from core.runner import hint
            if hint(r.error):
                self._append_log("   提示：" + hint(r.error))
            return
        self.probes[r.url] = r
        self.lbl_title.setText(r.title)
        if r.is_playlist:
            self.lbl_meta.setText(f"播放列表 · {r.count} 个视频 · {r.uploader}")
            self.lbl_fmt.setText("")
            self.lbl_subs.setText("")
            if r.entries:
                self.btn_items.setVisible(True)
                self._update_items_btn(r.url)
        else:
            self.lbl_meta.setText(" · ".join(x for x in (r.uploader, r.duration) if x))
            self.lbl_fmt.setText("可用画质：" + (" / ".join(f"{h}p" for h in r.heights[:8]) or "（无视频流）"))
            subs = "人工字幕：" + (", ".join(r.manual_subs) if r.manual_subs else "无")
            if r.auto_count:
                subs += f"　自动字幕：{', '.join(r.auto_orig) or '?'}（可翻译成 {r.auto_count} 种，易被限流）"
            self.lbl_subs.setText(subs)
        if r.thumb_bytes:
            pm = QPixmap()
            if pm.loadFromData(r.thumb_bytes):
                self.thumb.setPixmap(pm.scaled(self.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.thumb.setText("无预览")

    def _update_items_btn(self, url):
        r = self.probes.get(url)
        if not r:
            return
        sel = self.playlist_sel.get(url)
        n = len(sel[1]) if sel else r.count
        self.btn_items.setText(f"☑ 选择条目…（已选 {n}/{r.count}）")

    def _on_pick_items(self):
        urls = self._urls()
        r = self.probes.get(urls[0]) if urls else None
        if not r or not r.entries:
            QMessageBox.information(self, "提示", "先勾选「下载整个列表」再解析播放列表链接"); return
        prev = self.playlist_sel.get(r.url)
        dlg = PlaylistDialog(self, r.title, r.entries, set(prev[1]) if prev else None)
        if dlg.exec():
            items = dlg.items_str()
            if items:
                self.playlist_sel[r.url] = (items, dlg.selected())
            else:
                self.playlist_sel.pop(r.url, None)
            self._update_items_btn(r.url)

    def _on_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec():
            v = dlg.values()
            self.cfg.update(v)
            env.save_config(self.cfg)
            self.manager.set_workers(v["workers"])
            self._append_log(f"设置已保存：同时下载 {v['workers']} 个"
                             + (f"，限速 {v['ratelimit'] / 1024 / 1024:g} MB/s" if v["ratelimit"] else "")
                             + (f"，代理 {v['proxy']}" if v["proxy"] else "")
                             + "（限速和代理对之后加入的任务生效）")

    def _selected_tasks(self):
        ids = {self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()}
        return [t for t in self.manager.tasks if t.id in ids]

    def _on_cancel(self):
        for t in self._selected_tasks():
            self.manager.cancel(t)

    def _on_retry(self):
        for t in self._selected_tasks():
            self.manager.retry(t)

    def _on_open_task_dir(self, *_):
        ts = self._selected_tasks()
        self._open_dir(ts[0].opts.out_dir if ts else self.out_edit.text())

    def _on_clear(self):
        self.manager.clear_finished()
        self._rebuild_table()

    def _on_update(self):
        self._append_log("🔄 更新 yt-dlp / curl_cffi / deno …")
        py = sys.executable.replace("pythonw.exe", "python.exe")

        def job():
            r = subprocess.run([py, "-m", "pip", "install", "--user", "-U", "-q",
                                "yt-dlp[default,curl-cffi]", "deno"],
                               capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            msg = "✅ 更新完成，重开程序后生效" if r.returncode == 0 else "❌ 更新失败：" + (r.stderr or "")[-300:]
            self.logq.put(msg)
        threading.Thread(target=job, daemon=True).start()

    # ================================================================ 刷新
    def _log_from_worker(self, task, msg):
        self.logq.put(f"[#{task.id}] {msg}")

    def _append_log(self, msg):
        self.log_view.appendPlainText(time.strftime("%H:%M:%S ") + msg)

    def _rebuild_table(self):
        self.table.setRowCount(0)
        self.rows.clear()

    def _tick(self):
        try:
            while True:
                self._append_log(self.logq.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._show_probe(self.probeq.get_nowait())
        except queue.Empty:
            pass

        for t in list(self.manager.tasks):
            row = self.rows.get(t.id)
            if row is None:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.rows[t.id] = row
                it = QTableWidgetItem(str(t.id)); it.setData(Qt.UserRole, t.id)
                self.table.setItem(row, 0, it)
                for col in (1, 2, 4, 5, 6):
                    self.table.setItem(row, col, QTableWidgetItem(""))
                bar = QProgressBar(); bar.setRange(0, 1000)
                self.table.setCellWidget(row, 3, bar)
            self.table.item(row, 1).setText(t.title or t.url)
            self.table.item(row, 1).setToolTip(t.url)
            self.table.item(row, 2).setText(t.opts.describe())
            bar = self.table.cellWidget(row, 3)
            bar.setValue(int(t.percent * 10))
            bar.setFormat(f"{t.percent:.1f}%")
            self.table.item(row, 4).setText(t.speed)
            self.table.item(row, 5).setText(t.eta)
            st = t.status + (f" · {t.note}" if t.note else "")
            item = self.table.item(row, 6)
            item.setText(st); item.setToolTip(st)
            color = {DONE: "#16803c", FAILED: "#c0392b", CANCELLED: "#888888"}.get(t.status)
            item.setForeground(QColor(color) if color else self.table.palette().text().color())

        n = self.manager.active_count()
        self.setWindowTitle(f"YouTube 下载器（{n} 个进行中）" if n else "YouTube 下载器")

    def closeEvent(self, e):
        self._collect()
        if self.manager.active_count():
            if QMessageBox.question(self, "退出", "还有任务没完成，确定退出？\n（未完成的下次重试可从断点继续）") != QMessageBox.Yes:
                e.ignore()
                return
        e.accept()
