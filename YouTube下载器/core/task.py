"""下载任务：链接 + 选项 + 状态 + 进度。工作线程写，界面定时读。"""
import itertools
from dataclasses import dataclass, field

_ids = itertools.count(1)

# 状态
WAITING, RUNNING, POST, DONE, FAILED, CANCELLED = "等待", "下载中", "处理中", "完成", "失败", "已取消"
FINISHED = (DONE, FAILED, CANCELLED)


@dataclass
class DownloadOptions:
    mode: str = "video"              # video / audio / subs
    out_dir: str = ""
    name_tmpl: str = "title_id"      # title / title_id / uploader_title
    playlist: bool = False
    cookies: str = ""                # "" / firefox / edge / chrome
    # 视频
    quality: str = "1080"            # best / 2160 / 1440 / 1080 / 720 / 480 / 360
    container: str = "mp4"           # mp4 / mkv
    embed_subs: bool = False
    # 音频
    audio_fmt: str = "mp3"           # mp3 / m4a / opus / original
    audio_kbps: str = "192"
    # 字幕（字幕模式；视频模式嵌入字幕也用 sub_langs / sub_auto）
    sub_langs: list = field(default_factory=lambda: ["en"])
    sub_auto: bool = True
    sub_fallback: bool = True
    sub_formats: list = field(default_factory=lambda: ["srt", "txt"])   # srt / txt / txt_t / vtt
    # ---- P1
    playlist_items: str = ""         # "1,3,5-7"，空=全部
    clip_start: str = ""             # 只下片段：起止时间（"1:20" / "01:02:03" / "80"），空=整段
    clip_end: str = ""
    clip_precise: bool = False       # 精确剪切（重新编码，慢）
    embed_thumb: bool = True         # 写入封面
    add_meta: bool = True            # 写入标题/作者等信息
    add_chapters: bool = True        # 写入章节
    archive_path: str = ""           # 下载记录文件，空=不去重
    ratelimit: int = 0               # 每个任务限速 bytes/s，0=不限
    proxy: str = ""

    @property
    def clipped(self):
        return bool(self.clip_start or self.clip_end)

    def describe(self):
        if self.mode == "video":
            q = "最佳" if self.quality == "best" else f"{self.quality}p"
            s = f"视频 {q} {self.container}" + (" +字幕" if self.embed_subs else "")
        elif self.mode == "audio":
            s = "音频 " + ("原始" if self.audio_fmt == "original" else self.audio_fmt)
        else:
            s = "字幕 " + ",".join(self.sub_langs)
        if self.clipped and self.mode != "subs":
            s += f" ✂{self.clip_start or '0'}-{self.clip_end or '末尾'}"
        if self.playlist and self.playlist_items:
            s += f" #{self.playlist_items}"
        return s


@dataclass
class Task:
    url: str
    opts: DownloadOptions
    id: int = field(default_factory=lambda: next(_ids))
    title: str = ""
    status: str = WAITING
    percent: float = 0.0             # 0~100
    speed: str = ""
    eta: str = ""
    note: str = ""                   # 当前阶段/错误简述
    cancel_requested: bool = False

    def reset(self):
        self.status, self.percent, self.speed, self.eta, self.note = WAITING, 0.0, "", "", ""
        self.cancel_requested = False
