"""잘라낼 구간 -> 남길 구간(세그먼트) 계산과 원본/편집 타임라인 간 시간 변환."""
from __future__ import annotations

import bisect

from .models import Cut, MediaInfo, Segment, Word


def snap(t: float, media: MediaInfo) -> float:
    """시간을 가장 가까운 프레임 경계로 맞춘다."""
    frames = round(t * media.fps_num / media.fps_den)
    return frames * media.fps_den / media.fps_num


def merge_cuts(cuts: list[Cut], min_gap: float = 0.0) -> list[Cut]:
    """겹치거나 `min_gap` 보다 가까운 구간을 합친다."""
    merged: list[Cut] = []
    for c in sorted(cuts, key=lambda c: c.start):
        if merged and c.start <= merged[-1].end + min_gap:
            last = merged[-1]
            if c.end > last.end:
                reason = last.reason if last.length >= c.length else c.reason
                merged[-1] = Cut(last.start, c.end, reason)
        else:
            merged.append(Cut(c.start, c.end, c.reason))
    return merged


def build_segments(media: MediaInfo, cuts: list[Cut], min_cut: float = 0.1,
                   min_keep: float = 0.2) -> list[Segment]:
    """전체 길이에서 잘라낼 구간을 빼고, 프레임에 맞춘 세그먼트 목록을 만든다.

    - `min_cut` 보다 짧은 컷은 무시한다(점프컷이 너무 잦아지는 것 방지).
    - 컷 사이에 남는 구간이 `min_keep` 보다 짧으면 그 조각도 버린다.
    """
    cuts = [c for c in merge_cuts(cuts, min_gap=min_keep) if c.length >= min_cut]
    segments: list[Segment] = []
    cursor = 0.0
    for c in cuts:
        start, end = max(0.0, c.start), min(media.duration, c.end)
        if start - cursor >= min_keep:
            segments.append(Segment(cursor, start))
        cursor = max(cursor, end)
    if media.duration - cursor >= min_keep:
        segments.append(Segment(cursor, media.duration))

    out = 0.0
    snapped: list[Segment] = []
    max_t = snap(media.duration, media)
    if max_t > media.duration + 1e-6:  # 마지막 프레임 경계가 파일 길이를 넘지 않게
        max_t -= media.fps_den / media.fps_num
    for s in segments:
        a, b = snap(s.src_start, media), min(snap(s.src_end, media), max_t)
        if b - a <= 0:
            continue
        snapped.append(Segment(a, b, out))
        out += b - a
    return snapped


class TimeMap:
    """원본 시간 -> 편집 타임라인 시간."""

    def __init__(self, segments: list[Segment]):
        self.segments = segments
        self._starts = [s.src_start for s in segments]

    def segment_index(self, t: float) -> int | None:
        i = bisect.bisect_right(self._starts, t) - 1
        if i >= 0 and t < self.segments[i].src_end:
            return i
        return None

    def to_output(self, t: float) -> float | None:
        i = self.segment_index(t)
        if i is None:
            return None
        s = self.segments[i]
        return s.out_start + (t - s.src_start)

    def remap_words(self, words: list[Word]) -> list[Word]:
        """편집 후에도 남아 있는 단어만 편집 타임라인 시간으로 옮긴다."""
        out: list[Word] = []
        for w in words:
            mid = (w.start + w.end) / 2
            i = self.segment_index(mid)
            if i is None:
                continue
            s = self.segments[i]
            start = s.out_start + (max(w.start, s.src_start) - s.src_start)
            end = s.out_start + (min(w.end, s.src_end) - s.src_start)
            out.append(Word(w.text, start, end, w.prob))
        return out
