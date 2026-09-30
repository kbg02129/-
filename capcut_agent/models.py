"""파이프라인 전체에서 공유하는 데이터 구조."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int
    height: int
    fps_num: int  # 예: 30000
    fps_den: int  # 예: 1001  -> 29.97fps
    has_video: bool = True
    has_audio: bool = True
    audio_rate: int = 48000
    audio_channels: int = 2

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Cut:
    """원본 영상에서 잘라낼 구간."""
    start: float
    end: float
    reason: str  # silence | filler | repeat | stutter | retake | llm

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class Segment:
    """남길 구간. src_* 는 원본 시간, out_start 는 편집된 타임라인 시간."""
    src_start: float
    src_end: float
    out_start: float = 0.0

    @property
    def duration(self) -> float:
        return self.src_end - self.src_start

    @property
    def out_end(self) -> float:
        return self.out_start + self.duration


@dataclass
class Caption:
    text: str
    start: float  # 편집된 타임라인 기준
    end: float


@dataclass
class EditPlan:
    media: MediaInfo
    words: list[Word]
    cuts: list[Cut]
    segments: list[Segment]
    captions: list[Caption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
