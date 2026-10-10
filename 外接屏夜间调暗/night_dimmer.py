# -*- coding: utf-8 -*-
"""
夜间外接屏调暗 (Night Dimmer)
- 用显卡 Gamma 斜坡调暗：Alt+Tab、开始菜单、UAC 都会一起变暗，不会漏亮
- 只调外接屏（非主屏）；只有一块屏时就调这一块
- 按时间自动渐暗/渐亮，托盘图标可手动切换
- 首次运行自动加入开机启动
"""
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import sys
import threading
import time
import winreg

import pystray
from PIL import Image, ImageDraw

APP_NAME = "NightDimmer"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "settings.json")

DEFAULT_CFG = {
    "mode": "auto",          # auto / always_dim / off
    "night_start": "19:00",  # 开始变暗
    "night_end": "07:00",    # 恢复正常
    "fade_minutes": 30,      # 渐变时长
    "night_level": 0.5,      # 夜间亮度 (0.1~1.0)
    "include_primary": False,  # 主屏也调暗
    "autostart_set": False,
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

gdi32.CreateDCW.restype = wt.HDC
gdi32.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.restype = wt.BOOL
gdi32.SetDeviceGammaRamp.argtypes = [wt.HDC, ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [wt.HDC]


# ---------------- 配置 ----------------
def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------- 显示器 ----------------
class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD), ("szDevice", wt.WCHAR * 32)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC,
                                     ctypes.POINTER(wt.RECT), wt.LPARAM)


def list_monitors():
    """返回 [(设备名, 是否主屏)]"""
    result = []

    def cb(hmon, hdc, rect, lp):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(mi)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            result.append((mi.szDevice, bool(mi.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return result


# ---------------- Gamma ----------------
_floor = {}  # 每个屏幕系统允许的最低亮度（被限幅时自动探测）


def _set_ramp(device, level):
    hdc = gdi32.CreateDCW("DISPLAY", device, None, None)
    if not hdc:
        return False
    ramp = ((wt.WORD * 256) * 3)()
    for i in range(256):
        v = min(int(i * 257 * level), 65535)
        ramp[0][i] = ramp[1][i] = ramp[2][i] = v
    ok = bool(gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)))
    gdi32.DeleteDC(hdc)
    return ok


def apply_level(device, level):
    """设置亮度；如果被 Windows 限幅，自动退到能用的最低值。返回实际亮度"""
    level = max(level, _floor.get(device, 0.0))
    while level < 1.0:
        if _set_ramp(device, level):
            return level
        level = round(level + 0.05, 2)
        _floor[device] = level
    _set_ramp(device, 1.0)
    return 1.0


# ---------------- 时间 → 亮度 ----------------
def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def auto_level(cfg, now=None):
    now = now or datetime.datetime.now()
    t = now.hour * 60 + now.minute + now.second / 60
    s, e = _minutes(cfg["night_start"]), _minutes(cfg["night_end"])
    length = (e - s) % 1440
    since_start = (t - s) % 1440
    if since_start >= length:
        f = 0.0
    else:
        fade = max(cfg["fade_minutes"], 0.01)
        until_end = (e - t) % 1440
        f = min(1.0, since_start / fade, until_end / fade)
    return 1.0 - f * (1.0 - cfg["night_level"])


# ---------------- 开机启动 ----------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            cmd = f'"{_pythonw()}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def is_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


# ---------------- 主逻辑 ----------------
class Dimmer:
    def __init__(self):
        self.cfg = load_cfg()
        self.dimmed = set()
        self.current = 1.0
        self.running = True
        self.lock = threading.Lock()

    def targets(self, mons):
        if self.cfg["include_primary"] or len(mons) == 1:
            return [d for d, _ in mons]
        return [d for d, primary in mons if not primary]

    def wanted_level(self):
        mode = self.cfg["mode"]
        if mode == "off":
            return 1.0
        if mode == "always_dim":
            return self.cfg["night_level"]
        return auto_level(self.cfg)

    def tick(self):
        with self.lock:
            mons = list_monitors()
            tg = set(self.targets(mons))
            level = self.wanted_level()
            actual = 1.0
            for dev in tg:
                if level < 0.999:
                    actual = apply_level(dev, level)
                    self.dimmed.add(dev)
                elif dev in self.dimmed:
                    _set_ramp(dev, 1.0)
                    self.dimmed.discard(dev)
            # 不再是目标的屏幕（比如取消了“主屏也调暗”）恢复原样
            for dev in list(self.dimmed - tg):
                _set_ramp(dev, 1.0)
                self.dimmed.discard(dev)
            self.current = actual if tg else 1.0

    def loop(self, icon):
        while self.running:
            try:
                self.tick()
                icon.title = f"夜间调暗：{round(self.current * 100)}%"
            except Exception:
                pass
            time.sleep(2)  # 每 2 秒重设一次，睡眠/切分辨率后会自动恢复

    def restore_all(self):
        with self.lock:
            for dev, _ in list_monitors():
                if dev in self.dimmed:
                    _set_ramp(dev, 1.0)
            self.dimmed.clear()

    # ---- 托盘菜单 ----
    def _setter(self, key, value):
        def f(icon, item):
            self.cfg[key] = value
            save_cfg(self.cfg)
            threading.Thread(target=self.tick, daemon=True).start()
        return f

    def _is(self, key, value):
        return lambda item: self.cfg[key] == value

    def build_menu(self):
        M, I = pystray.Menu, pystray.MenuItem
        levels = [0.7, 0.5, 0.3, 0.15]
        return M(
            I("自动（按时间）", self._setter("mode", "auto"), checked=self._is("mode", "auto"), radio=True),
            I("一直调暗", self._setter("mode", "always_dim"), checked=self._is("mode", "always_dim"), radio=True),
            I("不调暗", self._setter("mode", "off"), checked=self._is("mode", "off"), radio=True),
            M.SEPARATOR,
            I("夜间亮度", M(*[
                I(f"{int(v * 100)}%", self._setter("night_level", v),
                  checked=self._is("night_level", v), radio=True) for v in levels
            ])),
            I("夜间时段", M(*[
                I(f"{a} ～ {b}", self._time_setter(a, b),
                  checked=self._time_is(a, b), radio=True)
                for a, b in [("18:00", "07:00"), ("19:00", "07:00"),
                             ("20:00", "07:00"), ("21:00", "06:00"), ("22:00", "06:00")]
            ])),
            I("主屏也调暗", self._toggle("include_primary"),
              checked=lambda item: self.cfg["include_primary"]),
            I("开机自动启动", self._toggle_autostart, checked=lambda item: is_autostart()),
            M.SEPARATOR,
            I("退出（恢复亮度）", self.quit),
        )

    def _time_setter(self, a, b):
        def f(icon, item):
            self.cfg["night_start"], self.cfg["night_end"] = a, b
            save_cfg(self.cfg)
            threading.Thread(target=self.tick, daemon=True).start()
        return f

    def _time_is(self, a, b):
        return lambda item: self.cfg["night_start"] == a and self.cfg["night_end"] == b

    def _toggle(self, key):
        def f(icon, item):
            self.cfg[key] = not self.cfg[key]
            save_cfg(self.cfg)
            threading.Thread(target=self.tick, daemon=True).start()
        return f

    def _toggle_autostart(self, icon, item):
        set_autostart(not is_autostart())

    def quit(self, icon, item):
        self.running = False
        self.restore_all()
        icon.stop()


def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=(200, 255, 60, 255))      # 月亮
    d.ellipse((22, 0, 72, 50), fill=(0, 0, 0, 0))             # 挖出月牙
    return img


def single_instance():
    kernel32.CreateMutexW(None, False, "Global\\NightDimmer_SingleInstance")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not single_instance():
        return
    app = Dimmer()
    if not app.cfg.get("autostart_set"):
        try:
            set_autostart(True)
        except Exception:
            pass
        app.cfg["autostart_set"] = True
        save_cfg(app.cfg)

    icon = pystray.Icon(APP_NAME, make_icon(), "夜间调暗", app.build_menu())
    threading.Thread(target=app.loop, args=(icon,), daemon=True).start()
    try:
        icon.run()
    finally:
        app.running = False
        app.restore_all()


if __name__ == "__main__":
    main()
