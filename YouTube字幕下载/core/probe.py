"""解析链接：标题、时长、缩略图、可用画质和字幕（不下载）。"""
from dataclasses import dataclass, field


@dataclass
class ProbeResult:
    url: str
    title: str = ""
    uploader: str = ""
    duration: str = ""
    is_playlist: bool = False
    count: int = 0
    heights: list = field(default_factory=list)
    manual_subs: list = field(default_factory=list)
    auto_orig: list = field(default_factory=list)
    auto_count: int = 0
    thumb_bytes: bytes = b""
    error: str = ""


def _dur(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _thumb_url(info):
    thumbs = info.get("thumbnails") or []
    jpgs = [t for t in thumbs if ".jpg" in (t.get("url") or "")]
    pool = jpgs or thumbs
    if pool:
        # 选宽度不超过 640 的最大一张，避免下大图
        pool = sorted(pool, key=lambda t: t.get("width") or 0)
        small = [t for t in pool if (t.get("width") or 0) <= 640]
        return (small or pool)[-1].get("url")
    return info.get("thumbnail")


def probe(url, cookies="", playlist=False):
    import yt_dlp
    r = ProbeResult(url=url)
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": not playlist, "extract_flat": "in_playlist"}
    if cookies:
        opts["cookiesfrombrowser"] = (cookies,)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                r.is_playlist = True
                r.title = info.get("title", "")
                r.uploader = info.get("uploader") or info.get("channel") or ""
                r.count = len(list(info.get("entries") or []))
            else:
                r.title = info.get("title", "")
                r.uploader = info.get("uploader") or info.get("channel") or ""
                r.duration = _dur(info.get("duration"))
                r.heights = sorted({f.get("height") for f in info.get("formats") or []
                                    if f.get("height") and f.get("vcodec") not in (None, "none")},
                                   reverse=True)
                r.manual_subs = sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat")
                auto = info.get("automatic_captions") or {}
                r.auto_orig = [k.replace("-orig", "") for k in auto if k.endswith("-orig")]
                r.auto_count = len(auto)
            tu = _thumb_url(info)
            if tu:
                try:
                    r.thumb_bytes = ydl.urlopen(tu).read()
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # noqa: BLE001
        r.error = str(e).splitlines()[0]
    return r
