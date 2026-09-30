#!/usr/bin/env python3
"""Step 0: OS 감지 + 환경 점검 (표준 라이브러리만 사용).

    python3 scripts/doctor.py

출력 전체를 복사해서 전달하면 된다. 아무것도 설치하지 않고, 설치 명령만 알려준다.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

OK, NG, WARN = "✓", "✗", "!"
missing: list[str] = []  # 설치 명령


def line(mark: str, label: str, detail: str = "") -> None:
    print(f"  {mark} {label:<22} {detail}")


def detect_track() -> tuple[str, str]:
    system, machine = platform.system(), platform.machine()
    if system == "Darwin" and machine == "arm64":
        return "A", "Mac Apple Silicon · mlx-whisper"
    if system == "Windows" and machine in ("AMD64", "x86_64"):
        return "C", "Windows · faster-whisper · MP4 export 보너스"
    return "fallback", f"{system} {machine} · faster-whisper"


def draft_root() -> Path | None:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Movies/CapCut/User Data/Projects/com.lveditor.draft"
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return local / "CapCut/User Data/Projects/com.lveditor.draft"
    return None


def inspect_drafts(root: Path) -> None:
    """가장 최근 초안 하나를 열어 CapCut 이 쓰는 파일 형식과 암호화 여부를 본다."""
    drafts = sorted((d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
                    key=lambda d: d.stat().st_mtime, reverse=True)
    line(OK, "초안 개수", str(len(drafts)))
    if not drafts:
        line(WARN, "초안 형식", "초안이 없음 → CapCut 에서 빈 프로젝트 1개 만들고 다시 실행")
        return
    d = drafts[0]
    names = sorted(p.name for p in d.iterdir() if p.suffix == ".json")
    line(OK, "최근 초안", d.name)
    line(OK, "json 파일", ", ".join(names) or "(없음)")
    for fname in ("draft_info.json", "draft_content.json"):
        f = d / fname
        if not f.exists():
            continue
        raw = f.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
            keys = ", ".join(k for k in ("version", "new_version", "duration", "fps") if k in data)
            line(OK, fname, f"평문 JSON ({len(raw):,} bytes · {keys})")
        except (UnicodeDecodeError, json.JSONDecodeError):
            line(NG, fname, f"평문 아님 → 암호화된 형식 ({len(raw):,} bytes)")
    meta = d / "draft_meta_info.json"
    if meta.exists():
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            keys = [k for k in ("tm_duration", "draft_fold_path", "draft_root_path", "draft_id") if k in m]
            line(OK, "draft_meta_info.json", "키: " + ", ".join(keys))
        except Exception:
            line(WARN, "draft_meta_info.json", "읽기 실패")


def main() -> int:
    print("캡컷 에이전트 · Step 0 환경 점검\n")
    track, desc = detect_track()
    print(f"[OS]  {platform.system()} {platform.machine()}  →  트랙 {track} ({desc})")
    if sys.platform == "darwin":
        print(f"      macOS {platform.mac_ver()[0]}")

    print("\n[도구]")
    py = sys.version_info
    if py >= (3, 11):
        line(OK, "python", platform.python_version())
    else:
        line(NG, "python", f"{platform.python_version()} (3.11+ 필요)")
        missing.append("brew install python@3.11" if sys.platform == "darwin"
                       else "https://www.python.org/downloads/ 에서 3.11+ 설치")

    if sys.platform == "darwin":
        if shutil.which("brew"):
            line(OK, "brew", shutil.which("brew"))
        else:
            line(NG, "brew", "없음")
            missing.insert(0, '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            ver = subprocess.run([path, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
            line(OK, tool, ver[:60])
        else:
            line(NG, tool, "없음")
            cmd = {"darwin": "brew install ffmpeg", "win32": "winget install ffmpeg"}.get(
                sys.platform, "sudo apt install ffmpeg")
            if cmd not in missing:
                missing.append(cmd)

    print("\n[CapCut 초안 폴더]")
    root = draft_root()
    if root is None:
        line(WARN, "초안 폴더", "이 OS 는 CapCut 데스크톱 미지원")
    elif root.is_dir():
        line(OK, "경로", str(root))
        try:
            inspect_drafts(root)
        except PermissionError:
            line(NG, "접근", "권한 없음 → 시스템 설정 > 개인정보 보호 > 전체 디스크 접근에 터미널 추가")
    else:
        line(NG, "경로", f"{root} 없음")
        missing.append("CapCut 설치 후 1회 실행 (https://www.capcut.com/download)  "
                       "※ 설정 > 초안 위치를 바꿨다면 그 경로를 알려주세요")

    print("\n[디스크]")
    free = shutil.disk_usage(Path.home()).free / 1024**3
    line(OK if free >= 5 else NG, "홈 여유 공간", f"{free:.1f} GB (5GB+ 필요: Whisper 모델 ~3GB)")
    if free < 5:
        missing.append("디스크 5GB 이상 확보")

    print()
    if missing:
        print("[설치 필요] 아래를 순서대로 실행한 뒤 다시 점검하세요:")
        for i, cmd in enumerate(missing, 1):
            print(f"  {i}. {cmd}")
        return 1
    print("[결과] 모든 항목 통과 → 1단(무음 점프컷 드래프트) 진행 가능")
    return 0


if __name__ == "__main__":
    sys.exit(main())
