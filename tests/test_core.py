from capcut_agent.analyze import detect_disfluencies, normalize, words_to_cuts
from capcut_agent.media import normalize_fps, parse_silencedetect
from capcut_agent.models import Cut, MediaInfo, Word
from capcut_agent.pipeline import make_plan
from capcut_agent.subtitles import build_captions, to_srt
from capcut_agent.timeline import TimeMap, build_segments, merge_cuts
from fractions import Fraction


def W(*items):
    """("텍스트", 시작, 끝) 튜플들 -> Word 리스트"""
    return [Word(t, s, e) for t, s, e in items]


def media(duration=10.0):
    return MediaInfo("x.mp4", duration, 1920, 1080, 30, 1)


def test_normalize():
    assert normalize("으으으음...") == "으으음"
    assert normalize("저는,") == "저는"


def test_fillers_and_repeats():
    words = W(("음", 0, .3), ("저는", .5, .8), ("저는", .9, 1.2), ("오늘", 1.3, 1.6),
              ("어", 1.7, 1.9), ("학교에", 2.0, 2.4), ("갔어요", 2.5, 2.9))
    marks = detect_disfluencies(words)
    assert marks == {0: "filler", 1: "repeat", 4: "filler"}


def test_repeat_across_filler_and_retake():
    words = W(("오늘은", 0, .4), ("영상을", .5, .9), ("음", 1.0, 1.2),
              ("오늘은", 1.5, 1.9), ("영상을", 2.0, 2.4), ("찍어요", 2.5, 2.9))
    marks = detect_disfluencies(words)
    assert marks == {0: "retake", 1: "retake", 2: "filler"}


def test_stutter_prefix():
    words = W(("그래", 0, .2), ("그래서", .3, .7), ("좋아요", .8, 1.2))
    assert detect_disfluencies(words) == {0: "stutter"}


def test_words_to_cuts_extends_to_next_kept_word():
    words = W(("음", 1.0, 1.3), ("안녕하세요", 1.6, 2.2))
    cuts = words_to_cuts(words, {0: "filler"})
    assert len(cuts) == 1
    assert abs(cuts[0].start - 0.97) < 1e-9 and abs(cuts[0].end - 1.57) < 1e-9


def test_parse_silencedetect():
    log = ("[silencedetect @ 0x1] silence_start: 1.5\n"
           "[silencedetect @ 0x1] silence_end: 3.0 | silence_duration: 1.5\n"
           "[silencedetect @ 0x1] silence_start: 8.2\n")
    cuts = parse_silencedetect(log, duration=10.0)
    assert [(c.start, c.end) for c in cuts] == [(1.5, 3.0), (8.2, 10.0)]


def test_normalize_fps():
    assert normalize_fps(Fraction(2997, 100)) == (30000, 1001)
    assert normalize_fps(Fraction(25)) == (25, 1)


def test_merge_and_segments_are_frame_aligned():
    m = media(10.0)
    cuts = [Cut(2.0, 3.0, "silence"), Cut(2.9, 4.0, "filler"), Cut(7.01, 7.05, "filler")]
    assert len(merge_cuts(cuts)) == 2
    segs = build_segments(m, cuts, min_cut=0.1)
    assert [(s.src_start, s.src_end) for s in segs] == [(0.0, 2.0), (4.0, 10.0)]
    assert segs[1].out_start == 2.0
    for s in segs:  # 30fps 프레임 경계
        assert abs(s.src_start * 30 - round(s.src_start * 30)) < 1e-9


def test_short_kept_islands_are_dropped():
    segs = build_segments(media(10.0), [Cut(2.0, 3.0, "silence"), Cut(3.1, 5.0, "silence")])
    assert [(s.src_start, s.src_end) for s in segs] == [(0.0, 2.0), (5.0, 10.0)]


def test_timemap_remap():
    tm = TimeMap(build_segments(media(10.0), [Cut(2.0, 4.0, "silence")]))
    assert tm.to_output(1.0) == 1.0
    assert tm.to_output(3.0) is None
    assert tm.to_output(5.0) == 3.0
    kept = tm.remap_words(W(("a", 1, 1.5), ("b", 2.5, 3.0), ("c", 4.5, 5.0)))
    assert [(w.text, w.start) for w in kept] == [("a", 1.0), ("c", 2.5)]


def test_captions_split_and_srt():
    words = W(("안녕하세요", 0, .6), ("여러분", .7, 1.1), ("오늘은", 1.2, 1.5),
              ("캡컷", 1.6, 1.9), ("편집을", 2.0, 2.4), ("해볼게요.", 2.5, 3.0),
              ("시작합니다", 5.0, 5.8))
    caps = build_captions(words, max_chars=12)
    assert [c.text for c in caps] == ["안녕하세요 여러분", "오늘은 캡컷 편집을", "해볼게요.", "시작합니다"]
    srt = to_srt(caps)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,")
    assert "4\n00:00:05,000 --> 00:00:05,800\n시작합니다" in srt


def test_make_plan_end_to_end():
    words = W(("음", 0.2, 0.5), ("안녕하세요", 0.8, 1.4), ("오늘은", 3.0, 3.4),
              ("오늘은", 3.5, 3.9), ("캡컷을", 4.0, 4.5), ("배워요.", 4.6, 5.2))
    silences = [Cut(1.5, 2.9, "silence"), Cut(5.3, 10.0, "silence")]
    plan = make_plan(media(10.0), words, silences)
    reasons = {c.reason for c in plan.cuts}
    assert {"silence", "filler", "repeat"} <= reasons
    texts = " ".join(c.text for c in plan.captions)
    assert texts == "안녕하세요 오늘은 캡컷을 배워요."
    out_len = plan.segments[-1].out_end
    assert 3.0 < out_len < 4.5
    # 자막은 편집본 길이 안에 있어야 한다
    assert all(0 <= c.start < c.end <= out_len + 0.8 for c in plan.captions)
