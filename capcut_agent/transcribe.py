"""faster-whisper 로 단어 단위 타임스탬프가 있는 전사본을 만든다."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Word

# Whisper 는 기본적으로 "음", "어" 같은 추임새와 말더듬을 지워서 받아쓴다.
# 추임새가 섞인 예시 문장을 initial_prompt 로 주면 들리는 그대로 받아쓰는 경향이 강해진다.
VERBATIM_PROMPTS = {
    "ko": "음, 그러니까 어... 저 저는 음 오늘 어 그 영상을, 영상을 찍어 볼게요.",
    "en": "Um, so, uh... I I think, like, we we should, um, start.",
}


def transcribe(audio_path: str, language: str = "ko", model_size: str = "large-v3",
               device: str = "auto", compute_type: str = "auto") -> list[Word]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper 가 필요합니다: pip install 'capcut-agent[whisper]'"
        ) from e

    if compute_type == "auto":
        compute_type = "int8" if device in ("auto", "cpu") else "float16"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=False,  # 무음은 따로 감지하므로 VAD 로 잘라먹지 않는다
        condition_on_previous_text=False,  # 반복 환각 방지
        initial_prompt=VERBATIM_PROMPTS.get(language),
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text=text, start=float(w.start), end=float(w.end),
                                  prob=float(w.probability)))
    return words


def save_words(words: list[Word], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1), encoding="utf-8"
    )


def load_words(path: str | Path) -> list[Word]:
    return [Word(**w) for w in json.loads(Path(path).read_text(encoding="utf-8"))]
