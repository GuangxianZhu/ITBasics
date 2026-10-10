"""界面选项 → yt-dlp 参数。整个工具的“翻译层”：加功能基本只改这里。"""
NAME_TEMPLATES = {
    "title": "%(title).120B.%(ext)s",
    "title_id": "%(title).100B [%(id)s].%(ext)s",
    "uploader_title": "%(uploader).40B - %(title).90B.%(ext)s",
}


def base_opts(o, ffmpeg=None, temp_dir=None):
    """所有模式共用。下载中的文件放 temp_dir（每个任务独立，避免同一视频的多个任务互相覆盖），完成后移到 out_dir。"""
    tmpl = NAME_TEMPLATES.get(o.name_tmpl, NAME_TEMPLATES["title_id"])
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
    return opts


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
    if o.embed_subs:
        opts.update({
            "writesubtitles": True,
            "writeautomaticsub": o.sub_auto,
            "subtitleslangs": o.sub_langs,
            "subtitlesformat": "vtt/best",
        })
        opts["postprocessors"] = [{"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False}]
    return opts


def audio_opts(o, ffmpeg=None, temp_dir=None):
    opts = base_opts(o, ffmpeg, temp_dir)
    opts["format"] = "ba/b"
    if o.audio_fmt != "original":
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": o.audio_fmt}
        if o.audio_fmt == "mp3":
            pp["preferredquality"] = o.audio_kbps
        opts["postprocessors"] = [pp]
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
