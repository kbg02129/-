import json
import subprocess

import pytest

from capcut_agent.draft import US, captions_to_us, to_timeline_us, unique_name
from capcut_agent.models import Caption, Segment


def test_timeline_is_contiguous_and_clamped():
    segs = [Segment(0.5, 2.0), Segment(4.0, 4.3333333), Segment(6.0, 10.02)]
    out = to_timeline_us(segs, material_duration=10 * US)
    assert out[0] == (500_000, 0, 1_500_000)
    for (_, dst, dur), (_, nxt, _) in zip(out, out[1:]):
        assert dst + dur == nxt  # 틈/겹침 없음
    src, _, dur = out[-1]
    assert src + dur == 10 * US  # 소재 길이를 넘지 않음


def test_captions_do_not_overlap():
    caps = [Caption("a", 0.0, 1.2), Caption("b", 1.1, 2.0), Caption("c", 2.0, 2.05),
            Caption("d", 2.5, 9.0)]
    out = captions_to_us(caps, total=5 * US)
    assert [t for t, _, _ in out] == ["a", "b", "d"]
    assert out[1][1] == 1_200_000  # 앞 자막 끝에서 시작
    assert out[-1][1] + out[-1][2] == 5 * US


def test_unique_name(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x_2").mkdir()
    assert unique_name(tmp_path, "x") == "x_3"
    assert unique_name(tmp_path, "y") == "y"


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg 없음")
def test_build_draft_end_to_end(tmp_path):
    pytest.importorskip("pycapcut")
    from capcut_agent.draft import build_draft
    from capcut_agent.media import probe

    video = tmp_path / "in.mp4"
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
                    "-f", "lavfi", "-i", "sine=f=440", "-t", "6", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    media = probe(str(video))
    segs = [Segment(0.0, 2.0, 0.0), Segment(3.0, 6.0, 2.0)]
    caps = [Caption("안녕하세요", 0.1, 1.5), Caption("캡컷 자동 편집", 2.0, 4.5)]

    path = build_draft(media, segs, caps, tmp_path / "drafts", "테스트")
    content = json.loads((path / "draft_content.json").read_text(encoding="utf-8"))
    assert (path / "draft_meta_info.json").exists()
    tracks = {t["type"]: t["segments"] for t in content["tracks"]}
    assert [s["source_timerange"]["start"] for s in tracks["video"]] == [0, 3 * US]
    assert [s["target_timerange"]["start"] for s in tracks["video"]] == [0, 2 * US]
    texts = [json.loads(m["content"])["text"] for m in content["materials"]["texts"]]
    assert texts == ["안녕하세요", "캡컷 자동 편집"]
    assert content["duration"] == 5 * US

    # 같은 이름으로 다시 만들면 덮어쓰지 않고 새 이름을 쓴다
    assert build_draft(media, segs, caps, tmp_path / "drafts", "테스트").name == "테스트_2"
