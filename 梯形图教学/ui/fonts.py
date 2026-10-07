"""中日文字体加载"""
import os

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
            _font = loader.loadFont(path)
            _font.setPixelsPerUnit(48)
            return _font
    print("警告：未找到中日文字体，文字可能显示为方块")
    _font = loader.loadFont("cmss12")
    return _font
