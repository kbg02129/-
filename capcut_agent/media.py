"""ffmpeg / ffprobe 래퍼: 미디어 정보, 오디오 추출, 무음 감지."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from fractions import Fraction

from .models import Cut, MediaInfo


def _find_binary(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    if name == "ffmpeg":
        try:  # pip install imageio-ffmpeg 으로 설치한 정적 바이너리 사용
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
    raise RuntimeError(
        f"{name} 를 찾을 수 없습니다. macOS 라면 `brew install ffmpeg` 로 설치하세요."
    )


def probe(path: str) -> MediaInfo:
    """ffprobe 로 해상도/프레임레이트/길이를 읽는다. ffprobe 가 없으면 ffmpeg 출력을 파싱한다."""
    try:
        ffprobe = _find_binary("ffprobe")
    except RuntimeError:
        return _probe_with_ffmpeg(path)

    out = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration") or (video or audio)["duration"])

    fps = Fraction(30000, 1001)
    if video:
        rate = video.get("r_frame_rate") or video.get("avg_frame_rate") or "30000/1001"
        if rate != "0/0":
            fps = Fraction(rate)
    num, den = normalize_fps(fps)
    return MediaInfo(
        path=path,
        duration=duration,
        width=int(video["width"]) if video else 1920,
        height=int(video["height"]) if video else 1080,
        fps_num=num,
        fps_den=den,
        has_video=video is not None,
        has_audio=audio is not None,
        audio_rate=int(audio.get("sample_rate", 48000)) if audio else 48000,
        audio_channels=int(audio.get("channels", 2)) if audio else 2,
    )


def _probe_with_ffmpeg(path: str) -> MediaInfo:
    proc = subprocess.run(
        [_find_binary("ffmpeg"), "-hide_banner", "-i", path], capture_output=True, text=True
    )
    err = proc.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise RuntimeError(f"미디어 정보를 읽을 수 없습니다: {path}")
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    size = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    fps_m = re.search(r"([\d.]+) fps", err)
    num, den = normalize_fps(Fraction(fps_m[1]) if fps_m else Fraction(30000, 1001))
    audio = re.search(r"Audio:.*?(\d+) Hz", err)
    return MediaInfo(
        path=path,
        duration=duration,
        width=int(size[1]) if size else 1920,
        height=int(size[2]) if size else 1080,
        fps_num=num,
        fps_den=den,
        has_video=size is not None,
        has_audio=audio is not None,
        audio_rate=int(audio[1]) if audio else 48000,
    )


_NTSC = {23.976: (24000, 1001), 29.97: (30000, 1001), 59.94: (60000, 1001)}


def normalize_fps(fps: Fraction) -> tuple[int, int]:
    """29.97 같은 근사값을 정확한 분수(30000/1001)로 맞춘다."""
    value = float(fps)
    for approx, exact in _NTSC.items():
        if abs(value - approx) < 0.01:
            return exact
    rounded = round(value)
    if abs(value - rounded) < 0.01:
        return rounded, 1
    fps = fps.limit_denominator(1001)
    return fps.numerator, fps.denominator


def extract_audio(path: str, wav_path: str, sample_rate: int = 16000) -> str:
    """음성 인식용 모노 WAV 추출."""
    subprocess.run(
        [_find_binary("ffmpeg"), "-y", "-v", "error", "-i", path,
         "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", wav_path],
        check=True,
    )
    return wav_path


def detect_silence(path: str, noise_db: float = -35.0, min_silence: float = 0.6,
                   duration: float | None = None) -> list[Cut]:
    """ffmpeg silencedetect 필터로 무음 구간을 찾는다."""
    proc = subprocess.run(
        [_find_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return parse_silencedetect(proc.stderr, duration)


def parse_silencedetect(log: str, duration: float | None = None) -> list[Cut]:
    cuts: list[Cut] = []
    start = None
    for line in log.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m[1]))
            continue
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            cuts.append(Cut(start, float(m[1]), "silence"))
            start = None
    if start is not None and duration is not None:  # 파일 끝까지 무음
        cuts.append(Cut(start, duration, "silence"))
    return cuts
