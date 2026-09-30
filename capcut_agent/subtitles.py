"""단어 목록 -> 자막 줄 묶기, SRT 저장."""
from __future__ import annotations

from pathlib import Path

from .models import Caption, Word

_PUNCT_END = (".", "?", "!", "…")
_KO_ENDINGS = ("다", "요", "죠", "까")  # 한국어 문장 종결 어미


def build_captions(words: list[Word], max_chars: int = 18, max_duration: float = 4.0,
                   max_gap: float = 0.6, min_duration: float = 0.7) -> list[Caption]:
    """편집 타임라인 기준 단어들을 읽기 좋은 길이의 자막 줄로 묶는다.

    다음 경우 줄을 나눈다: 글자 수 초과, 표시 시간 초과, 단어 사이 공백이 김, 문장 끝.
    """
    captions: list[Caption] = []
    cur: list[Word] = []

    def flush():
        if not cur:
            return
        text = " ".join(w.text for w in cur).strip()
        captions.append(Caption(text, cur[0].start, cur[-1].end))
        cur.clear()

    for w in words:
        if cur:
            text_len = len(" ".join(x.text for x in cur)) + 1 + len(w.text)
            if (text_len > max_chars
                    or w.end - cur[0].start > max_duration
                    or w.start - cur[-1].end > max_gap):
                flush()
        cur.append(w)
        # 문장이 끝났고 충분히 길면 줄을 끊는다
        tail = w.text.rstrip()
        long_enough = len(" ".join(x.text for x in cur)) >= max_chars // 2
        if tail.endswith(_PUNCT_END) or (tail.endswith(_KO_ENDINGS) and long_enough):
            flush()
    flush()

    # 너무 짧게 깜빡이지 않도록 다음 자막 시작 전까지 표시 시간을 늘린다
    for i, c in enumerate(captions):
        limit = captions[i + 1].start if i + 1 < len(captions) else c.end + min_duration
        if c.end - c.start < min_duration:
            c.end = min(c.start + min_duration, limit)
        # 다음 자막과 공백이 짧으면 이어 붙여서 깜빡임 방지
        if i + 1 < len(captions) and 0 < captions[i + 1].start - c.end < 0.3:
            c.end = captions[i + 1].start
    return captions


def _ts(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(captions: list[Caption]) -> str:
    blocks = [f"{i}\n{_ts(c.start)} --> {_ts(c.end)}\n{c.text}\n"
              for i, c in enumerate(captions, 1)]
    return "\n".join(blocks)


def write_srt(captions: list[Caption], path: str | Path) -> None:
    # CapCut 이 한글을 깨뜨리지 않도록 BOM 없는 UTF-8 로 저장
    Path(path).write_text(to_srt(captions), encoding="utf-8")
