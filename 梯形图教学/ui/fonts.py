"""中日文字体加载"""
import os

from panda3d.core import Filename

CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]

_font = None


def load_cjk_font(loader):
    global _font
    if _font is not None:
        return _font
    for path in CANDIDATES:
        if os.path.exists(path):
            try:
                # Windows 路径要先转成 Panda3D 格式（C:/... → /c/...）
                f = loader.loadFont(Filename.fromOsSpecific(path).getFullpath())
            except (IOError, OSError, TypeError):
                continue
            if f is None or not f.isValid():
                continue
            _font = f
            _font.setPixelsPerUnit(48)
            return _font
    print("警告：未找到中日文字体，文字可能显示为方块")
    _font = loader.loadFont("cmss12")
    return _font
