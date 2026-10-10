"""VTT 字幕解析与转换（去掉 <c> 标签、合并 YouTube 自动字幕的滚动重复行）。"""
import re

TS_RE = re.compile(r"((?:\d+:)?\d{1,2}:\d{2}\.\d{3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}\.\d{3})")
TAG_RE = re.compile(r"<[^>]+>")


def _norm_ts(ts):
    """'01:02.345' / '00:01:02.345' -> '00:01:02,345'"""
    parts = ts.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    h, m, s = parts
    return f"{int(h):02d}:{int(m):02d}:{s.replace('.', ',')}"


def parse_vtt(path):
    """返回 [(start, end, [行...]), ...]"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    cues, i = [], 0
    while i < len(lines):
        m = TS_RE.search(lines[i])
        if not m:
            i += 1
            continue
        start, end = _norm_ts(m.group(1)), _norm_ts(m.group(2))
        i += 1
        text = []
        # 只在真正的空行结束（自动字幕里常有只含空格的行）
        while i < len(lines) and lines[i] != "" and not TS_RE.search(lines[i]):
            t = TAG_RE.sub("", lines[i])
            t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
                  .replace("&lt;", "<").replace("&gt;", ">").strip())
            if t:
                text.append(t)
            i += 1
        cues.append((start, end, text))
    return cues


def dedupe_cues(cues):
    """自动字幕每条都重复上一条的行，只保留新出现的行。"""
    out, recent = [], []
    for start, end, text in cues:
        new = [t for t in text if t not in recent]
        if new:
            out.append((start, end, new))
            recent = (recent + new)[-4:]
    return out


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for n, (s, e, text) in enumerate(cues, 1):
            f.write(f"{n}\n{s} --> {e}\n" + "\n".join(text) + "\n\n")


def write_txt(cues, path, with_time=False):
    with open(path, "w", encoding="utf-8") as f:
        for s, _e, text in cues:
            line = " ".join(text)
            f.write(f"[{s.split(',')[0]}] {line}\n" if with_time else line + "\n")


def convert_vtt(path, formats, keep_vtt=False):
    """formats ⊆ {'srt','txt','txt_t'}；返回 (条数, 生成的后缀列表)"""
    import os
    cues = dedupe_cues(parse_vtt(path))
    stem = path[:-4]
    made = []
    if "srt" in formats:
        write_srt(cues, stem + ".srt"); made.append("srt")
    if "txt" in formats:
        write_txt(cues, stem + ".txt"); made.append("txt")
    if "txt_t" in formats:
        write_txt(cues, stem + ".带时间.txt", with_time=True); made.append("带时间.txt")
    if keep_vtt:
        made.append("vtt")
    else:
        os.remove(path)
    return len(cues), made
