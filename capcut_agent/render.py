"""ffmpeg 로 컷 편집된 영상을 렌더링한다 (CapCut 에 그대로 불러올 수 있는 MP4)."""
from __future__ import annotations

import subprocess

from .media import _find_binary
from .models import MediaInfo, Segment


def build_filter(segments: list[Segment], media: MediaInfo, subtitles: str | None = None) -> str:
    """trim/atrim 으로 구간을 잘라 concat 으로 이어 붙이는 filtergraph."""
    parts: list[str] = []
    pads: list[str] = []
    for i, s in enumerate(segments):
        a, b = f"{s.src_start:.6f}", f"{s.src_end:.6f}"
        if media.has_video:
            parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
            pads.append(f"[v{i}]")
        if media.has_audio:
            parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
            pads.append(f"[a{i}]")
    v, a = int(media.has_video), int(media.has_audio)
    outs = ("[cv]" if v else "") + ("[outa]" if a else "")
    parts.append(f"{''.join(pads)}concat=n={len(segments)}:v={v}:a={a}{outs}")
    if v:
        if subtitles:
            parts.append(f"[cv]subtitles=filename='{_escape(subtitles)}'"
                         ":force_style='FontName=Apple SD Gothic Neo,FontSize=18,Bold=1,"
                         "Outline=2,MarginV=40'[outv]")
        else:
            parts.append("[cv]null[outv]")
    return ";".join(parts)


def _escape(path: str) -> str:
    # filtergraph 안에서 경로 특수문자 이스케이프
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(media: MediaInfo, segments: list[Segment], out_path: str,
           burn_subtitles: str | None = None, crf: int = 18, preset: str = "medium") -> None:
    if not segments:
        raise RuntimeError("남길 구간이 없습니다. 무음 기준(--noise-db)을 확인하세요.")
    graph = build_filter(segments, media, burn_subtitles)
    cmd = [_find_binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-stats",
           "-i", media.path, "-filter_complex", graph]
    if media.has_video:
        cmd += ["-map", "[outv]", "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-pix_fmt", "yuv420p", "-r", f"{media.fps_num}/{media.fps_den}"]
    if media.has_audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True)
