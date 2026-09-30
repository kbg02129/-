"""분석 단계를 이어 붙여 EditPlan 을 만든다 (렌더링과 분리되어 있어 테스트하기 쉽다)."""
from __future__ import annotations

from dataclasses import dataclass

from .analyze import DetectOptions, detect_disfluencies, shrink_silences, words_to_cuts
from .models import Cut, EditPlan, MediaInfo, Word
from .subtitles import build_captions
from .timeline import TimeMap, build_segments


@dataclass
class PlanOptions:
    silence_keep: float = 0.15  # 무음 구간 앞뒤로 남길 여유(초)
    min_cut: float = 0.1
    min_keep: float = 0.2
    cut_silence: bool = True
    cut_disfluency: bool = True
    max_chars: int = 18


def make_plan(media: MediaInfo, words: list[Word], silences: list[Cut],
              opts: PlanOptions | None = None, detect: DetectOptions | None = None,
              extra_marks: dict[int, str] | None = None,
              corrections: dict[int, str] | None = None) -> EditPlan:
    opts = opts or PlanOptions()
    cuts: list[Cut] = []
    if opts.cut_silence:
        cuts += shrink_silences(silences, opts.silence_keep)

    if opts.cut_disfluency:
        marks = detect_disfluencies(words, detect)
        marks.update(extra_marks or {})
        cuts += words_to_cuts(words, marks)
    elif extra_marks:
        cuts += words_to_cuts(words, extra_marks)

    segments = build_segments(media, cuts, min_cut=opts.min_cut, min_keep=opts.min_keep)

    if corrections:
        words = [Word(corrections.get(i, w.text), w.start, w.end, w.prob) for i, w in enumerate(words)]
    kept = TimeMap(segments).remap_words(words)
    captions = build_captions(kept, max_chars=opts.max_chars)
    return EditPlan(media=media, words=words, cuts=sorted(cuts, key=lambda c: c.start),
                    segments=segments, captions=captions)


def summarize(plan: EditPlan) -> str:
    total = plan.media.duration
    out = plan.segments[-1].out_end if plan.segments else 0.0
    by_reason: dict[str, float] = {}
    for c in plan.cuts:
        by_reason[c.reason] = by_reason.get(c.reason, 0.0) + c.length
    labels = {"silence": "무음", "filler": "추임새", "repeat": "반복", "stutter": "말더듬",
              "retake": "다시 말하기", "aside": "혼잣말"}
    lines = [f"원본 {total:.1f}s -> 편집본 {out:.1f}s  ({total - out:.1f}s 제거, "
             f"{(1 - out / total) * 100 if total else 0:.0f}%)",
             f"세그먼트 {len(plan.segments)}개, 자막 {len(plan.captions)}줄"]
    for r, sec in sorted(by_reason.items(), key=lambda x: -x[1]):
        n = sum(1 for c in plan.cuts if c.reason == r)
        lines.append(f"  - {labels.get(r, r)}: {n}곳, 약 {sec:.1f}s")
    return "\n".join(lines)
