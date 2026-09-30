"""pycapcut 으로 CapCut 초안(프로젝트)을 만든다.

잘라낸 영상을 새로 렌더링하는 대신, 원본 영상을 남길 구간마다 잘라 붙인 타임라인과
자막 텍스트 트랙을 만든다. CapCut 에서 열면 컷 위치를 조정하거나 자막을 고치면서
이어서 편집할 수 있다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .models import Caption, MediaInfo, Segment

US = 1_000_000  # pycapcut 은 마이크로초 단위


def default_draft_dir() -> Path | None:
    """CapCut 이 초안을 저장하는 기본 폴더 (CapCut 설정 > 초안 위치 에서 확인 가능)."""
    home = Path.home()
    candidates = []
    if sys.platform == "darwin":
        candidates.append(home / "Movies/CapCut/User Data/Projects/com.lveditor.draft")
    elif sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        candidates.append(local / "CapCut/User Data/Projects/com.lveditor.draft")
    for c in candidates:
        if c.is_dir():
            return c
    return None


def unique_name(folder: Path, name: str) -> str:
    if not (folder / name).exists():
        return name
    i = 2
    while (folder / f"{name}_{i}").exists():
        i += 1
    return f"{name}_{i}"


def to_timeline_us(segments: list[Segment], material_duration: int) -> list[tuple[int, int, int]]:
    """세그먼트 -> (원본 시작, 타임라인 시작, 길이) 마이크로초.

    반올림 오차로 틈이나 겹침이 생기지 않도록 타임라인 위치는 앞 조각 끝에 이어 붙이고,
    원본 범위가 소재 길이를 넘지 않게 자른다.
    """
    out: list[tuple[int, int, int]] = []
    cursor = 0
    for s in segments:
        src = round(s.src_start * US)
        dur = min(round(s.duration * US), material_duration - src)
        if dur <= 0:
            continue
        out.append((src, cursor, dur))
        cursor += dur
    return out


def captions_to_us(captions: list[Caption], total: int) -> list[tuple[str, int, int]]:
    """자막 -> (텍스트, 시작, 길이) 마이크로초. 한 트랙에 겹치지 않게 정리한다."""
    out: list[tuple[str, int, int]] = []
    prev_end = 0
    for c in captions:
        start = max(round(c.start * US), prev_end)
        end = min(round(c.end * US), total)
        if end - start < US // 10:  # 0.1초 미만은 버림
            continue
        out.append((c.text, start, end - start))
        prev_end = end
    return out


def build_draft(media: MediaInfo, segments: list[Segment], captions: list[Caption],
                draft_dir: str | Path, draft_name: str, *, font_size: float = 7.0,
                subtitle_y: float = -0.8, replace: bool = False) -> Path:
    try:
        import pycapcut as cc
    except ImportError as e:
        raise RuntimeError("pycapcut 이 필요합니다: pip install pycapcut") from e

    draft_dir = Path(draft_dir)
    draft_dir.mkdir(parents=True, exist_ok=True)
    if not replace:
        draft_name = unique_name(draft_dir, draft_name)

    folder = cc.DraftFolder(str(draft_dir))
    script = folder.create_draft(draft_name, media.width, media.height,
                                 fps=round(media.fps), allow_replace=replace)
    script.add_track(cc.TrackType.video)
    script.add_track(cc.TrackType.text, "자막")

    material = cc.VideoMaterial(media.path)
    total = 0
    for src, dst, dur in to_timeline_us(segments, material.duration):
        script.add_segment(cc.VideoSegment(material, cc.Timerange(dst, dur),
                                           source_timerange=cc.Timerange(src, dur)))
        total = dst + dur

    style = cc.TextStyle(size=font_size, bold=True, align=1, auto_wrapping=True)
    border = cc.TextBorder(color=(0.0, 0.0, 0.0), width=40.0)
    for text, start, dur in captions_to_us(captions, total):
        script.add_segment(cc.TextSegment(text, cc.Timerange(start, dur), style=style,
                                          border=border,
                                          clip_settings=cc.ClipSettings(transform_y=subtitle_y)), "자막")

    script.save()
    return draft_dir / draft_name
