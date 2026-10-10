"""执行一个任务（在工作线程里跑）。"""
import os
import re
import shutil
import time

from core import options
from core.task import DONE, FAILED, CANCELLED, POST, RUNNING
from post.subtitles import convert_vtt


class Cancelled(Exception):
    pass


def hint(msg):
    m = msg.lower()
    if "sign in to confirm" in m or "not a bot" in m:
        return "YouTube 要求登录验证：在「浏览器登录状态」里选 firefox（Chrome/Edge 需先关闭浏览器）"
    if "429" in m or "too many requests" in m:
        return "请求太频繁：等一会儿再试，或借用浏览器登录状态"
    if "cookie" in m and ("decrypt" in m or "could not copy" in m or "permission" in m):
        return "读取浏览器 cookie 失败：先完全关闭该浏览器，或改用 firefox"
    if "unsupported url" in m:
        return "链接不对，确认是视频/播放列表地址"
    if "drm" in m:
        return "该内容有 DRM 保护，无法下载"
    if "ffmpeg" in m and ("not found" in m or "not installed" in m):
        return "缺少 ffmpeg：重新双击 启动.bat"
    if "http error 403" in m or "unable to extract" in m:
        return "可能是 yt-dlp 太旧，点「更新组件」后重开"
    return ""


class _Logger:
    def __init__(self, task, log):
        self.task, self.log, self.errors, self.skipped = task, log, [], 0

    def debug(self, msg):
        if "has already been recorded in the archive" in msg:
            self.skipped += 1
            self.log(self.task, "已在下载记录里，跳过（可在 ⚙设置 里清空记录）")
            return
        if "There aren't any thumbnails" in msg:
            return
        if msg.startswith("[info] Writing video subtitles") or msg.startswith("[Merger]") \
                or msg.startswith("[ExtractAudio]") or msg.startswith("[EmbedSubtitle]") \
                or msg.startswith("[EmbedThumbnail]") or msg.startswith("[download] Downloading section"):
            # 路径太长，只留文件名
            m = re.match(r'(.*?(?:to|Destination|into)\s*:?\s*"?)(.+?)("?)$', msg)
            if m and (os.sep in m.group(2) or "/" in m.group(2)):
                msg = m.group(1) + os.path.basename(m.group(2)) + m.group(3)
            self.log(self.task, msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        if "No supported JavaScript runtime" in msg:
            msg = "没找到 deno（JS 运行环境），部分格式可能缺失：重新双击 启动.bat"
        self.log(self.task, "⚠ " + msg)

    def error(self, msg):
        if self.task.cancel_requested:
            return  # 取消引起的报错不显示
        self.errors.append(msg)
        self.log(self.task, "❌ " + msg)
        h = hint(msg)
        if h:
            self.log(self.task, "   提示：" + h)


def _fmt_speed(bps):
    if not bps:
        return ""
    for unit in ("B/s", "KB/s", "MB/s"):
        if bps < 1024:
            return f"{bps:.0f} {unit}"
        bps /= 1024
    return f"{bps:.1f} GB/s"


def _fmt_eta(s):
    if s is None:
        return ""
    s = int(s)
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


PP_NAMES = {"Merger": "合并音视频", "ExtractAudio": "转换音频", "EmbedSubtitle": "嵌入字幕",
            "FFmpegMerger": "合并音视频", "FFmpegExtractAudio": "转换音频",
            "FFmpegEmbedSubtitle": "嵌入字幕", "MoveFiles": "整理文件",
            "FFmpegMetadata": "写入信息", "Metadata": "写入信息", "EmbedThumbnail": "写入封面",
            "ThumbnailsConvertor": "转换封面"}


def run(task, log, ffmpeg):
    """执行任务，结束时设置 task.status。log(task, msg) 用于输出日志。"""
    import yt_dlp

    task.status = RUNNING
    os.makedirs(task.opts.out_dir, exist_ok=True)
    logger = _Logger(task, log)
    temp_dir = os.path.join(task.opts.out_dir, ".下载中", str(task.id))
    opts = options.build(task.opts, ffmpeg, temp_dir)
    isolate = task.opts.mode == "audio"
    if isolate:
        # 音频模式整个在临时文件夹里完成，最后再移出来：
        # 否则保存位置已有同名视频时，yt-dlp 会拿它当源文件，转完音频后把视频删掉
        opts["paths"] = {"home": temp_dir, "temp": temp_dir}
    stream_no = [0]

    def on_progress(d):
        if task.cancel_requested:
            raise Cancelled()
        info = d.get("info_dict") or {}
        if info.get("title"):
            task.title = info["title"]
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                task.percent = min(99.9, d.get("downloaded_bytes", 0) * 100 / total)
            task.speed = _fmt_speed(d.get("speed"))
            task.eta = _fmt_eta(d.get("eta"))
            parts = []
            if info.get("playlist_index") and info.get("n_entries"):
                parts.append(f"{info['playlist_index']}/{info['n_entries']}")
            if info.get("requested_formats"):
                kind = "视频流" if stream_no[0] == 0 else "音频流"
                parts.append(kind)
            task.note = " · ".join(parts)
        elif d["status"] == "finished":
            stream_no[0] = (stream_no[0] + 1) % max(1, len(info.get("requested_formats") or [1]))
            task.speed, task.eta = "", ""

    def on_pp(d):
        if task.cancel_requested:
            raise Cancelled()
        if d["status"] == "started":
            task.status = POST
            task.note = PP_NAMES.get(d.get("postprocessor", ""), d.get("postprocessor", ""))
        elif d["status"] == "finished":
            task.status = RUNNING

    opts.update({"logger": logger, "progress_hooks": [on_progress],
                 "postprocessor_hooks": [on_pp], "ignoreerrors": True})
    try:
        info = None
        if task.opts.mode == "subs":
            n = _run_subs(task, log, opts)
            ok = n > 0
        else:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(task.url, download=True)
            ok = (info is not None or logger.skipped > 0) and not logger.errors
        if task.cancel_requested:
            raise Cancelled()
        task.status = DONE if ok else FAILED
        if ok:
            task.percent = 100.0
            task.note = ""
            if logger.skipped:
                task.note = f"跳过 {logger.skipped} 个下载过的" if task.opts.playlist else "下载过，已跳过"
            if isolate:
                _move_tree(temp_dir, task.opts.out_dir)
            _cleanup(temp_dir)
        else:
            task.note = (logger.errors[-1] if logger.errors else "没有下载到文件")[:80]
    except Cancelled:
        task.status = CANCELLED
        task.note = "已取消（再点重试可从断点继续）"
    except Exception as e:  # noqa: BLE001
        if task.cancel_requested or "Cancelled" in type(e).__name__:
            task.status = CANCELLED
            task.note = "已取消（再点重试可从断点继续）"
        else:
            task.status = FAILED
            task.note = str(e).splitlines()[0][:80]
            log(task, f"❌ {e}")
            h = hint(str(e))
            if h:
                log(task, "   提示：" + h)
    task.speed, task.eta = "", ""


def _move_tree(src, dst):
    """把 src 下的成品文件（保持子文件夹结构）移到 dst，同名覆盖。"""
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(target, exist_ok=True)
        for f in files:
            if f.endswith((".part", ".ytdl")):
                continue
            os.replace(os.path.join(root, f), os.path.join(target, f))


def _cleanup(temp_dir):
    shutil.rmtree(temp_dir, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(temp_dir))  # “.下载中”空了就删掉
    except OSError:
        pass


# ---------------------------------------------------------------- 字幕模式
def _run_subs(task, log, opts):
    """逐个语言下载：429 自动等待重试；翻译字幕失败时可改下原文字幕。返回生成的文件数。"""
    import yt_dlp
    total = 0
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(task.url, download=False)
        if not info:
            return 0
        entries = info.get("entries") if info.get("_type") == "playlist" else [info]
        entries = [e for e in (entries or []) if e]
        for k, ent in enumerate(entries):
            if task.cancel_requested:
                raise Cancelled()
            task.title = ent.get("title", "") if len(entries) == 1 else info.get("title", "")
            task.note = f"{k + 1}/{len(entries)}" if len(entries) > 1 else ""
            total += _subs_one(task, log, ydl, ent)
            task.percent = (k + 1) * 100 / len(entries)
    return total


def _pick_fmt(fmts):
    fmts = fmts or []
    return next((f for f in fmts if f.get("ext") == "vtt"), fmts[0] if fmts else None)


def _original_sub(info):
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    vlang = (info.get("language") or "").split("-")[0]
    for k in manual:
        if vlang and k.split("-")[0] == vlang:
            return k, _pick_fmt(manual[k])
    auto = info.get("automatic_captions") or {}
    for k in auto:
        if k.endswith("-orig"):
            return k.replace("-orig", ""), _pick_fmt(auto[k])
    if manual:
        k = next(iter(manual))
        return k, _pick_fmt(manual[k])
    return None, None


def _dl_one(task, log, ydl, info, lang, sub):
    base = os.path.splitext(ydl.prepare_filename(info))[0]
    path = f"{base}.{lang}.{sub.get('ext', 'vtt')}"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sub = dict(sub)
    sub.setdefault("http_headers", info.get("http_headers"))
    waits = [5, 20, 60]
    for attempt in range(len(waits) + 1):
        if task.cancel_requested:
            raise Cancelled()
        try:
            ydl.dl(path, sub, subtitle=True)
            if os.path.exists(path):
                return path
            err = "文件未生成"
        except Exception as e:  # noqa: BLE001
            err = str(e)
        if ("429" in err or "Too Many" in err) and attempt < len(waits):
            w = waits[attempt]
            log(task, f"{lang}: 被限流(429)，{w} 秒后重试（{attempt + 1}/{len(waits)}）")
            task.note = f"限流，等待 {w}s"
            for _ in range(w * 2):
                if task.cancel_requested:
                    raise Cancelled()
                time.sleep(0.5)
            continue
        log(task, f"{lang}: ❌ 下载失败：{err.splitlines()[0][:150]}")
        return None
    return None


def _subs_one(task, log, ydl, info):
    o = task.opts
    subs = info.get("requested_subtitles") or {}
    if not subs:
        log(task, f"⚠ 《{info.get('title', '')}》没有所选语言的字幕")
        return 0
    manual = set((info.get("subtitles") or {}).keys())
    done, failed_tr = [], []
    for i, (lang, sub) in enumerate(subs.items()):
        if i:
            time.sleep(1.5)
        p = _dl_one(task, log, ydl, info, lang, sub)
        if p:
            done.append((lang, p))
        elif lang not in manual:
            failed_tr.append(lang)
    if failed_tr and o.sub_fallback:
        olang, osub = _original_sub(info)
        if olang and osub and olang not in [l for l, _ in done]:
            log(task, f"↪ {', '.join(failed_tr)} 是自动翻译字幕，改下原文字幕 {olang}")
            time.sleep(3)
            p = _dl_one(task, log, ydl, info, olang, osub)
            if p:
                done.append((olang, p))
    n = 0
    conv = [f for f in o.sub_formats if f != "vtt"]
    for lang, path in done:
        if path.lower().endswith(".vtt"):
            cnt, made = convert_vtt(path, conv, keep_vtt="vtt" in o.sub_formats)
            log(task, f"{lang}: {cnt} 条 → {', '.join(made)}")
            n += len(made)
        else:
            log(task, f"{lang}: 已保存 {os.path.basename(path)}")
            n += 1
    return n
