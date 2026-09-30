"""capcut-agent 명령줄 도구.

    capcut-agent input.mp4                # CapCut 초안(컷 편집 + 자막 트랙) 생성
    capcut-agent input.mp4 --llm          # Claude 로 NG/버벅임 추가 검토
    capcut-agent input.mp4 --render       # 초안과 함께 컷 편집된 MP4 도 렌더링
    capcut-agent input.mp4 --dry-run      # 초안/영상 없이 분석 결과와 SRT 만 확인
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import media as media_mod
from .analyze import DetectOptions
from .pipeline import PlanOptions, make_plan, summarize
from .subtitles import write_srt
from .transcribe import load_words, save_words, transcribe


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="capcut-agent",
                                description="무음·버벅임 자동 컷 편집 + 자막 생성 (CapCut 용)")
    p.add_argument("input", help="원본 영상 파일")
    p.add_argument("-o", "--out-dir", help="결과 폴더 (기본: 원본 옆 <이름>_capcut)")
    p.add_argument("--lang", default="ko", help="언어 코드 (기본 ko)")

    g = p.add_argument_group("음성 인식")
    g.add_argument("--model", default="large-v3", help="Whisper 모델 (tiny/base/small/medium/large-v3)")
    g.add_argument("--device", default="auto", help="auto / cpu / cuda")
    g.add_argument("--transcript", help="이전에 저장한 transcript.json 재사용 (음성 인식 건너뜀)")

    g = p.add_argument_group("컷 편집")
    g.add_argument("--noise-db", type=float, default=-35.0, help="이 소리 크기(dB) 이하를 무음으로 봄 (기본 -35)")
    g.add_argument("--min-silence", type=float, default=0.6, help="이 길이(초) 이상 무음만 자름 (기본 0.6)")
    g.add_argument("--keep", type=float, default=0.15, help="무음 앞뒤로 남길 여유(초) (기본 0.15)")
    g.add_argument("--no-silence", action="store_true", help="무음 컷 끄기")
    g.add_argument("--no-disfluency", action="store_true", help="버벅임 컷 끄기")
    g.add_argument("--keep-repeats", action="store_true", help="반복/다시 말하기는 자르지 않음 (추임새만)")
    g.add_argument("--fillers", help="추임새 목록 직접 지정 (쉼표 구분, 예: 음,어,그니까)")
    g.add_argument("--llm", action="store_true", help="Claude 로 NG·버벅임·오타 추가 검토 (ANTHROPIC_API_KEY 필요)")

    g = p.add_argument_group("CapCut 초안 (pycapcut)")
    g.add_argument("--draft-dir", help="CapCut 초안 폴더 (기본: CapCut 기본 위치, 없으면 결과 폴더)")
    g.add_argument("--draft-name", help="초안 이름 (기본: <파일이름>_자동편집)")
    g.add_argument("--replace", action="store_true", help="같은 이름의 초안이 있으면 덮어쓰기")
    g.add_argument("--no-draft", action="store_true", help="CapCut 초안을 만들지 않음")
    g.add_argument("--max-chars", type=int, default=18, help="자막 한 줄 최대 글자 수 (기본 18)")
    g.add_argument("--font-size", type=float, default=7.0, help="자막 글자 크기 (CapCut 기준, 기본 7)")
    g.add_argument("--subtitle-y", type=float, default=-0.8,
                   help="자막 세로 위치 (-1 맨 아래 ~ 1 맨 위, 기본 -0.8)")

    g = p.add_argument_group("영상 렌더링 (선택)")
    g.add_argument("--render", action="store_true", help="컷 편집된 MP4 도 ffmpeg 로 렌더링")
    g.add_argument("--burn", action="store_true", help="자막을 입힌 MP4 렌더링 (--render 포함)")
    g.add_argument("--crf", type=int, default=18, help="화질 (낮을수록 고화질, 기본 18)")
    g.add_argument("--dry-run", action="store_true", help="초안/영상 없이 분석 결과와 SRT 만 생성")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        print(f"파일이 없습니다: {src}", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir) if args.out_dir else src.with_name(f"{src.stem}_capcut")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("1/5 미디어 정보 확인")
    info = media_mod.probe(str(src))
    print(f"    {info.width}x{info.height} {info.fps:.3f}fps, {info.duration:.1f}s")

    print("2/5 무음 구간 감지")
    silences = [] if args.no_silence else media_mod.detect_silence(
        str(src), args.noise_db, args.min_silence, info.duration)
    print(f"    무음 {len(silences)}곳")

    transcript_path = out_dir / "transcript.json"
    if args.transcript:
        print("3/5 전사본 불러오기")
        words = load_words(args.transcript)
    else:
        print(f"3/5 음성 인식 (Whisper {args.model}) — 영상 길이에 따라 몇 분 걸릴 수 있습니다")
        with tempfile.TemporaryDirectory() as tmp:
            wav = media_mod.extract_audio(str(src), str(Path(tmp) / "audio.wav"))
            words = transcribe(wav, language=args.lang, model_size=args.model, device=args.device)
        save_words(words, transcript_path)
    print(f"    단어 {len(words)}개")

    detect = DetectOptions(
        language=args.lang,
        fillers=set(f.strip() for f in args.fillers.split(",")) if args.fillers else set(),
        remove_repeats=not args.keep_repeats,
    )
    extra, corrections = {}, {}
    if args.llm and words:
        print("4/5 Claude 로 편집 검토")
        from .analyze import detect_disfluencies
        from .llm import review
        extra, corrections = review(words, hints=detect_disfluencies(words, detect))
        print(f"    추가 삭제 후보 {len(extra)}단어, 자막 수정 {len(corrections)}곳")
    else:
        print("4/5 버벅임 감지 (규칙 기반)")

    plan = make_plan(
        info, words, silences,
        PlanOptions(silence_keep=args.keep, cut_silence=not args.no_silence,
                    cut_disfluency=not args.no_disfluency, max_chars=args.max_chars),
        detect, extra_marks=extra, corrections=corrections,
    )

    srt = out_dir / f"{src.stem}.srt"
    write_srt(plan.captions, srt)
    (out_dir / "edit_plan.json").write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(summarize(plan))

    draft_path = None
    video = out_dir / f"{src.stem}_edited.mp4"
    if args.dry_run:
        print("5/5 --dry-run: 초안/렌더링 건너뜀")
    else:
        if not args.no_draft:
            print("5/5 CapCut 초안 생성 (pycapcut)")
            from .draft import build_draft, default_draft_dir
            draft_dir = Path(args.draft_dir).expanduser() if args.draft_dir else default_draft_dir()
            if draft_dir is None:
                draft_dir = out_dir
                print("    CapCut 초안 폴더를 찾지 못해 결과 폴더에 저장합니다 (--draft-dir 로 지정 가능)")
            draft_path = build_draft(
                info, plan.segments, plan.captions, draft_dir,
                args.draft_name or f"{src.stem}_자동편집",
                font_size=args.font_size, subtitle_y=args.subtitle_y, replace=args.replace)
        if args.render or args.burn:
            print("    MP4 렌더링 (ffmpeg)")
            from .render import render
            render(info, plan.segments, str(video),
                   burn_subtitles=str(srt) if args.burn else None, crf=args.crf)

    print(f"\n완료! 결과 폴더: {out_dir}")
    print(f"  자막: {srt.name}")
    if (args.render or args.burn) and not args.dry_run:
        print(f"  영상: {video.name}")
    if draft_path:
        print(f"  CapCut 초안: {draft_path}")
        print("CapCut 을 열면 초안 목록에 나타납니다. 안 보이면 CapCut 을 다시 시작하세요.")
        if draft_path.parent == out_dir:
            print("(이 초안 폴더를 CapCut 설정 > 초안 위치 폴더로 옮겨야 CapCut 에서 보입니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
