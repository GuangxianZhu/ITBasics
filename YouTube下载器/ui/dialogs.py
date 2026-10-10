"""对话框：播放列表条目选择、设置。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from core import env
from core.options import compress_items

RATE_LIMITS = [("不限速", 0), ("0.5 MB/s", 512 * 1024), ("1 MB/s", 1024 ** 2), ("2 MB/s", 2 * 1024 ** 2),
               ("5 MB/s", 5 * 1024 ** 2), ("10 MB/s", 10 * 1024 ** 2)]


class PlaylistDialog(QDialog):
    """勾选要下载的条目。返回 items 字符串（'1-3,5'），全选时为空串。"""

    def __init__(self, parent, title, entries, selected=None):
        super().__init__(parent)
        self.setWindowTitle("选择要下载的条目")
        self.resize(560, 560)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"<b>{title}</b>　共 {len(entries)} 个"))
        self.lst = QListWidget()
        for idx, name, dur in entries:
            it = QListWidgetItem(f"{idx:>3}.  {name}" + (f"   [{dur}]" if dur else ""))
            it.setData(Qt.UserRole, idx)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if (selected is None or idx in selected) else Qt.Unchecked)
            self.lst.addItem(it)
        self.lst.itemChanged.connect(self._count)
        self.lst.itemDoubleClicked.connect(
            lambda it: it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked))
        v.addWidget(self.lst)
        h = QHBoxLayout()
        for text, fn in [("全选", lambda: self._set_all(True)), ("全不选", lambda: self._set_all(False)),
                         ("反选", self._invert)]:
            b = QPushButton(text); b.clicked.connect(fn); h.addWidget(b)
        h.addStretch()
        self.lbl = QLabel(); h.addWidget(self.lbl)
        v.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._count()

    def _items(self):
        return [self.lst.item(i) for i in range(self.lst.count())]

    def _set_all(self, on):
        for it in self._items():
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _invert(self):
        for it in self._items():
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)

    def _count(self, *_):
        self.lbl.setText(f"已选 {len(self.selected())} / {self.lst.count()}")

    def selected(self):
        return [it.data(Qt.UserRole) for it in self._items() if it.checkState() == Qt.Checked]

    def accept(self):
        if not self.selected():
            QMessageBox.information(self, "提示", "至少选一个")
            return
        super().accept()

    def items_str(self):
        sel = self.selected()
        return "" if len(sel) == self.lst.count() else compress_items(sel)


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(460)
        f = QFormLayout(self)

        self.workers = QSpinBox(); self.workers.setRange(1, 5); self.workers.setValue(cfg.get("workers", 2))
        f.addRow("同时下载", self.workers)

        self.rate = QComboBox()
        for label, val in RATE_LIMITS:
            self.rate.addItem(label, val)
        i = self.rate.findData(cfg.get("ratelimit", 0))
        self.rate.setCurrentIndex(max(0, i))
        f.addRow("每个任务限速", self.rate)

        self.proxy = QLineEdit(cfg.get("proxy", ""))
        self.proxy.setPlaceholderText("空=不用。例：http://127.0.0.1:7890 或 socks5://127.0.0.1:1080")
        f.addRow("代理", self.proxy)

        h = QHBoxLayout()
        self.arch_lbl = QLabel()
        h.addWidget(self.arch_lbl, 1)
        b = QPushButton("清空下载记录"); b.clicked.connect(self._clear); h.addWidget(b)
        f.addRow("下载记录", h)
        self._refresh()

        tip = QLabel("下载记录：勾选「跳过下载过的」时，成功下载的视频会记下 ID，下次自动跳过。"
                     "视频和音频分开记录；只下片段时不记录。")
        tip.setWordWrap(True); tip.setObjectName("meta")
        f.addRow(tip)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _refresh(self):
        self.arch_lbl.setText(f"共 {env.archive_count()} 条")

    def _clear(self):
        if QMessageBox.question(self, "清空", "清空后，下载过的视频会重新下载。确定？") == QMessageBox.Yes:
            env.clear_archive()
            self._refresh()

    def accept(self):
        p = self.proxy.text().strip()
        if p and "://" not in p:
            QMessageBox.information(self, "提示", "代理要带协议头，例如 http://127.0.0.1:7890")
            return
        super().accept()

    def values(self):
        return {"workers": self.workers.value(), "ratelimit": self.rate.currentData(),
                "proxy": self.proxy.text().strip()}
