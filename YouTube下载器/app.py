"""YouTube 下载器 —— 视频 / 音频 / 字幕。双击 启动.bat 运行。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import env  # noqa: E402

env.add_scripts_to_path()


def main():
    missing = []
    for mod in ("PySide6", "yt_dlp"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        msg = "缺少组件：" + ", ".join(missing) + "\n请双击 启动.bat 安装。"
        try:
            import tkinter.messagebox as mb
            mb.showerror("YouTube 下载器", msg)
        except Exception:  # noqa: BLE001
            print(msg)
        return

    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
