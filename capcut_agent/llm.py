"""(선택) Claude 로 전사본을 검토해 규칙으로 못 잡는 버벅임/NG 구간과 오타를 찾는다."""
from __future__ import annotations

import json

from .models import Word

MODEL = "claude-opus-5-5"

SYSTEM = """당신은 유튜브/숏폼 영상 편집자입니다. 음성 인식으로 만든 단어 목록을 보고,
최종 영상에서 잘라내야 할 단어와 자막에서 고쳐야 할 오인식 단어를 찾습니다.

잘라낼 것:
- 추임새 (음, 어, 그..., 저기 등 의미 없는 소리)
- 말더듬, 같은 단어/구절의 불필요한 반복
- 말을 하다가 멈추고 다시 시작한 부분(NG, 다시 말하기): 앞의 실패한 시도를 지우고 마지막으로 제대로 말한 버전을 남긴다
- "다시 할게요", "잠깐만" 처럼 촬영 중 혼잣말

남길 것:
- 의미를 가진 강조 반복("정말 정말 좋아요"), 말투의 개성, 문장 연결에 필요한 접속사
- 확실하지 않으면 남긴다. 너무 많이 잘라서 문장이 어색해지는 것이 더 나쁘다.

오인식 수정: 문맥상 명백히 잘못 받아쓴 단어만 고친다(맞춤법·띄어쓰기 포함)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "removals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer", "description": "첫 단어 인덱스"},
                    "end": {"type": "integer", "description": "마지막 단어 인덱스(포함)"},
                    "reason": {"type": "string", "enum": ["filler", "stutter", "repeat", "retake", "aside"]},
                },
                "required": ["start", "end", "reason"],
                "additionalProperties": False,
            },
        },
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["removals", "corrections"],
    "additionalProperties": False,
}


def format_transcript(words: list[Word]) -> str:
    lines = []
    for i, w in enumerate(words):
        gap = w.start - words[i - 1].end if i else 0.0
        pause = f" (쉼 {gap:.1f}s)" if gap >= 0.5 else ""
        lines.append(f"[{i}]{pause} {w.text}")
    return "\n".join(lines)


def review(words: list[Word], hints: dict[int, str] | None = None) -> tuple[dict[int, str], dict[int, str]]:
    """Claude 검토 결과: (삭제할 인덱스 -> 이유, 수정할 인덱스 -> 새 텍스트)."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("Claude 검토에는 anthropic 패키지가 필요합니다: pip install 'capcut-agent[llm]'") from e

    hint_text = ""
    if hints:
        hint_text = ("\n\n참고: 규칙 기반 감지기가 표시한 후보 인덱스입니다(틀릴 수 있음): "
                     + ", ".join(f"{i}:{r}" for i, r in sorted(hints.items())))

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{
            "role": "user",
            "content": "단어 목록([인덱스] 단어):\n\n" + format_transcript(words) + hint_text,
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude 가 요청을 처리하지 않았습니다(refusal). --no-llm 으로 다시 실행하세요.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude 응답이 max_tokens 에서 잘렸습니다. 영상을 나눠서 처리하세요.")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    n = len(words)
    removals: dict[int, str] = {}
    for r in data["removals"]:
        for i in range(max(0, r["start"]), min(n - 1, r["end"]) + 1):
            removals[i] = r["reason"]
    corrections = {c["index"]: c["text"] for c in data["corrections"] if 0 <= c["index"] < n}
    return removals, corrections
