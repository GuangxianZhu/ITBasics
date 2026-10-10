"""运行环境：PATH、ffmpeg、deno、配置文件位置。"""
import json
import os
import shutil
import sysconfig


def add_scripts_to_path():
    """pip --user 装的 deno.exe 在用户 Scripts 目录，通常不在 PATH 里；补上让 yt-dlp 找得到。"""
    dirs = []
    for scheme in (f"{os.name}_user", None):
        try:
            dirs.append(sysconfig.get_path("scripts", scheme) if scheme else sysconfig.get_path("scripts"))
        except KeyError:
            pass
    cur = os.environ.get("PATH", "")
    for d in dirs:
        if d and os.path.isdir(d) and d not in cur:
            cur = d + os.pathsep + cur
    os.environ["PATH"] = cur


def ffmpeg_path():
    """优先用 imageio-ffmpeg 自带的，其次系统 PATH 里的。找不到返回 None。"""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:  # noqa: BLE001
        pass
    return shutil.which("ffmpeg")


def deno_path():
    return shutil.which("deno")


def ytdlp_version():
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- 配置
def _config_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "YouTubeDownloader")
    os.makedirs(d, exist_ok=True)
    return d


CONFIG_PATH = os.path.join(_config_dir(), "config.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
