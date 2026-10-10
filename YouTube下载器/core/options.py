"""界面选项 → yt-dlp 参数。整个工具的“翻译层”：加功能基本只改这里。"""
import re

NAME_TEMPLATES = {
    "title": "%(title).120B",
    "title_id": "%(title).100B [%(id)s]",
    "uploader_title": "%(uploader).40B - %(title).90B",
}


def parse_time(s):
    """'1:20' / '01:02:03' / '80' / '1:20.5' → 秒（float）；空 → None；格式不对 → ValueError"""
    s = (s or "").strip().replace("：", ":")
    if not s:
        return None
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", s):
        raise ValueError(f"时间格式不对：{s}（例：1:20 或 01:02:03）")
    sec = 0.0
    for part in s.split(":"):
        sec = sec * 60 + float(part)
    return sec


def _ts_label(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def base_opts(o, ffmpeg=None, temp_dir=None):
    """所有模式共用。下载中的文件放 temp_dir（每个任务独立，避免同一视频的多个任务互相覆盖），完成后移到 out_dir。"""
    tmpl = NAME_TEMPLATES.get(o.name_tmpl, NAME_TEMPLATES["title_id"])
    if o.mode != "subs" and o.clipped:
        a, b = parse_time(o.clip_start), parse_time(o.clip_end)
        tmpl += f" [{_ts_label(a or 0)}-{_ts_label(b) if b is not None else 'end'}]"
    tmpl += ".%(ext)s"
    if o.playlist:
        # 播放列表单独建文件夹，并在文件名前加序号
        tmpl = "%(playlist_title).80B/%(playlist_index)03d " + tmpl
    opts = {
        "outtmpl": tmpl,
        "paths": {"home": o.out_dir, **({"temp": temp_dir} if temp_dir else {})},
        "noplaylist": not o.playlist,
        "windowsfilenames": True,
        "retries": 10,
        "fragment_retries": 10,
        "continuedl": True,
        "quiet": True,
        "noprogress": True,
    }
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if o.cookies:
        opts["cookiesfrombrowser"] = (o.cookies,)
    if o.proxy:
        opts["proxy"] = o.proxy
    if o.ratelimit:
        opts["ratelimit"] = o.ratelimit
    if o.playlist and o.playlist_items:
        opts["playlist_items"] = o.playlist_items
    # 下载记录：片段下载不记（同一视频可能要剪不同段），字幕模式不记
    if o.archive_path and o.mode != "subs" and not o.clipped:
        opts["download_archive"] = o.archive_path
    return opts


def _clip(opts, o):
    if not o.clipped:
        return
    from yt_dlp.utils import download_range_func
    a = parse_time(o.clip_start) or 0
    b = parse_time(o.clip_end)
    opts["download_ranges"] = download_range_func(None, [(a, b if b is not None else float("inf"))])
    opts["force_keyframes_at_cuts"] = o.clip_precise


def _meta_pps(o, thumb_ok=True):
    """写入信息/章节/封面的后处理（要排在转码、嵌字幕之后）。返回 (后处理列表, 是否需要下载封面)"""
    pps = []
    if o.add_meta or o.add_chapters:
        pps.append({"key": "FFmpegMetadata", "add_metadata": o.add_meta,
                    "add_chapters": o.add_chapters and not o.clipped})
    want_thumb = o.embed_thumb and thumb_ok
    if want_thumb:
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return pps, want_thumb


def video_opts(o, ffmpeg=None, temp_dir=None):
    opts = base_opts(o, ffmpeg, temp_dir)
    sort = []
    if o.quality != "best":
        sort.append(f"res:{o.quality}")
    if o.container == "mp4":
        # mp4 优先 H.264 + AAC：Windows 自带播放器、PPT、手机都能放
        sort += ["vcodec:h264", "acodec:m4a"]
    opts.update({
        "format": "bv*+ba/b",
        "format_sort": sort,
        "merge_output_format": o.container,
    })
    pps = []
    if o.embed_subs:
        opts.update({
            "writesubtitles": True,
            "writeautomaticsub": o.sub_auto,
            "subtitleslangs": o.sub_langs,
            "subtitlesformat": "vtt/best",
        })
        pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
    # MKV 写封面需要 ffprobe（imageio-ffmpeg 不带），所以只给 MP4 写
    meta, want_thumb = _meta_pps(o, thumb_ok=o.container == "mp4")
    pps += meta
    if want_thumb:
        opts["writethumbnail"] = True
    if pps:
        opts["postprocessors"] = pps
    _clip(opts, o)
    return opts


def audio_opts(o, ffmpeg=None, temp_dir=None):
    opts = base_opts(o, ffmpeg, temp_dir)
    opts["format"] = "ba/b"
    pps = []
    if o.audio_fmt != "original":
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": o.audio_fmt}
        if o.audio_fmt == "mp3":
            pp["preferredquality"] = o.audio_kbps
        pps.append(pp)
    # “原始”多半是 webm，封面写不进去
    meta, want_thumb = _meta_pps(o, thumb_ok=o.audio_fmt != "original")
    pps += meta
    if want_thumb:
        opts["writethumbnail"] = True
    if pps:
        opts["postprocessors"] = pps
    _clip(opts, o)
    return opts


def subs_opts(o, ffmpeg=None, temp_dir=None):
    opts = base_opts(o, ffmpeg, temp_dir)
    opts.update({
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": o.sub_auto,
        "subtitleslangs": o.sub_langs,
        "subtitlesformat": "vtt/best",
    })
    return opts


def build(o, ffmpeg=None, temp_dir=None):
    return {"video": video_opts, "audio": audio_opts, "subs": subs_opts}[o.mode](o, ffmpeg, temp_dir)


def compress_items(indices):
    """[1,2,3,5,7,8] → '1-3,5,7-8'"""
    idx = sorted(set(indices))
    out, i = [], 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
            j += 1
        out.append(str(idx[i]) if i == j else f"{idx[i]}-{idx[j]}")
        i = j + 1
    return ",".join(out)
