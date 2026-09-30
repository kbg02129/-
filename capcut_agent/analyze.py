"""전사본에서 버벅임(추임새, 반복, 말더듬, 다시 말하기)을 찾아 잘라낼 구간으로 바꾼다."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Cut, Word

DEFAULT_FILLERS = {
    "ko": {"음", "어", "으", "음음", "어어", "으음", "흠", "에", "엄", "아아"},
    "en": {"um", "uh", "erm", "er", "ah", "hmm", "mm", "uhm"},
}

_PUNCT = re.compile(r"[\s.,!?…·~\"'“”‘’()\[\]{}\-:;]+")


def normalize(text: str) -> str:
    text = _PUNCT.sub("", text.lower())
    # "으으음" -> "음", "어어어" -> "어어" 처럼 늘어진 소리를 줄인다
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)
    return text


@dataclass
class DetectOptions:
    language: str = "ko"
    fillers: set[str] = field(default_factory=set)
    max_retake_ngram: int = 8
    stutter_max_gap: float = 0.8  # 말더듬으로 볼 두 단어 사이 최대 간격(초)
    remove_fillers: bool = True
    remove_repeats: bool = True

    def filler_set(self) -> set[str]:
        return self.fillers or DEFAULT_FILLERS.get(self.language, set())


def detect_disfluencies(words: list[Word], opts: DetectOptions | None = None) -> dict[int, str]:
    """삭제할 단어 인덱스 -> 이유."""
    opts = opts or DetectOptions()
    norm = [normalize(w.text) for w in words]
    fillers = {normalize(f) for f in opts.filler_set()}
    marked: dict[int, str] = {}

    if opts.remove_fillers:
        for i, n in enumerate(norm):
            if n in fillers or (n and n.strip("음어으") == "" and len(n) <= 3):
                marked[i] = "filler"

    if not opts.remove_repeats:
        return marked

    # 추임새를 뺀 단어열에서 반복을 찾는다 ("저는 음 저는" 도 반복으로 인식)
    idx = [i for i in range(len(words)) if i not in marked and norm[i]]
    seq = [norm[i] for i in idx]

    # 다시 말하기: 같은 구절(n-gram)이 연달아 나오면 앞쪽을 지운다. 긴 구절부터 검사.
    k = 0
    while k < len(seq):
        found = False
        for n in range(min(opts.max_retake_ngram, (len(seq) - k) // 2), 0, -1):
            if seq[k:k + n] == seq[k + n:k + 2 * n]:
                reason = "retake" if n > 1 else "repeat"
                for j in range(k, k + n):
                    marked[idx[j]] = reason
                k += n
                found = True
                break
        if not found:
            k += 1

    # 말더듬: 짧은 조각이 다음 단어의 앞부분인 경우 ("그래 그래서", "저 저는")
    for a, b in zip(idx, idx[1:]):
        if a in marked or b in marked:
            continue
        na, nb = norm[a], norm[b]
        gap = words[b].start - words[a].end
        if na != nb and nb.startswith(na) and len(na) < len(nb) and gap <= opts.stutter_max_gap:
            marked[a] = "stutter"

    return marked


def words_to_cuts(words: list[Word], marked: dict[int, str], pad: float = 0.03) -> list[Cut]:
    """연속된 삭제 단어를 하나의 구간으로 묶는다.

    구간은 첫 삭제 단어 시작부터 다음에 남는 단어 시작 직전까지로 잡아서
    삭제 단어 뒤의 짧은 쉼도 함께 없앤다.
    """
    cuts: list[Cut] = []
    i = 0
    n = len(words)
    while i < n:
        if i not in marked:
            i += 1
            continue
        j = i
        reasons = []
        while j < n and j in marked:
            reasons.append(marked[j])
            j += 1
        prev_end = words[i - 1].end if i > 0 else 0.0
        start = max(prev_end, words[i].start - pad)
        end = words[j].start - pad if j < n else words[j - 1].end + pad
        end = max(end, words[j - 1].end)
        if end > start:
            reason = max(set(reasons), key=reasons.count)
            cuts.append(Cut(start, end, reason))
        i = j
    return cuts


def shrink_silences(silences: list[Cut], keep: float) -> list[Cut]:
    """무음 앞뒤로 `keep` 초씩 여유를 남겨 말이 뚝 끊기지 않게 한다."""
    out = []
    for c in silences:
        s, e = c.start + keep, c.end - keep
        if e - s > 0.05:
            out.append(Cut(s, e, c.reason))
    return out
