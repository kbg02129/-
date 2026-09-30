# CapCut 에이전트

영상을 넣으면 **무음 구간**과 **버벅거린 부분**(추임새, 말더듬, 반복, 다시 말하기)을 자동으로 잘라내고
**자막**까지 붙인 **CapCut 초안(프로젝트)** 을 만들어 주는 도구입니다.
[pycapcut](https://github.com/GuanYixuan/pyCapCut) 으로 초안을 직접 생성하므로, CapCut 을 열면
컷 편집과 자막이 들어간 타임라인이 바로 보이고 그대로 이어서 편집할 수 있습니다.

```
원본.mp4 ──▶ 무음 감지 (ffmpeg)
         ──▶ 음성 인식 (Whisper, 단어 단위 시간)
         ──▶ 버벅임 감지 (규칙 + 선택적으로 Claude 검토)
         ──▶ CapCut 초안 (pycapcut)
               ├─ 비디오 트랙: 원본에서 남길 구간만 이어 붙인 조각들
               └─ 텍스트 트랙 "자막": 편집된 시간에 맞춘 자막
```

원본 영상을 다시 렌더링하지 않고 **원본을 가리키는 컷**만 만들기 때문에, CapCut 에서 조각 끝을 늘리면
잘려 나간 부분을 되살릴 수 있습니다.

## 설치

```bash
brew install ffmpeg                    # macOS (Windows: winget install ffmpeg)
pip install -e ".[all]"                # pycapcut + faster-whisper + anthropic
```

## 사용법

1. CapCut 을 **종료**합니다 (실행 중이면 새 초안을 못 알아볼 수 있음).
2. 실행:
   ```bash
   capcut-agent 내영상.mp4
   ```
3. CapCut 을 열면 초안 목록에 **`내영상_자동편집`** 이 생겨 있습니다.

초안은 CapCut 기본 초안 폴더에 저장됩니다.

| OS | 기본 초안 폴더 |
|---|---|
| macOS | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` |
| Windows | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` |

폴더 위치를 바꿨다면 CapCut **설정 → 초안 위치** 에서 확인하고 `--draft-dir` 로 지정하세요.

그 밖에 `내영상_capcut/` 폴더에 다음이 생깁니다.

| 파일 | 설명 |
|---|---|
| `내영상.srt` | 편집된 타임라인 기준 자막 (다른 편집기용) |
| `transcript.json` | 음성 인식 결과 (다음 실행 때 `--transcript` 로 재사용하면 빠름) |
| `edit_plan.json` | 어디를 왜 잘랐는지 기록 |

## 자주 쓰는 옵션

```bash
capcut-agent 영상.mp4 --dry-run              # 초안 없이 무엇이 잘릴지만 확인
capcut-agent 영상.mp4 --llm                  # Claude 가 NG·다시 말하기·오타까지 검토
capcut-agent 영상.mp4 --render               # 초안과 함께 컷 편집된 MP4 도 렌더링
capcut-agent 영상.mp4 --burn                 # 자막을 입힌 MP4 렌더링 (CapCut 모바일용)
capcut-agent 영상.mp4 --transcript 영상_capcut/transcript.json --replace   # 음성 인식 없이 다시 편집
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--noise-db` | `-35` | 이 크기(dB) 이하를 무음으로 판단. 배경 소음이 크면 `-30` 정도로 올리기 |
| `--min-silence` | `0.6` | 이 길이(초) 이상의 무음만 자름. 템포를 빠르게 하려면 `0.4` |
| `--keep` | `0.15` | 무음을 자를 때 앞뒤로 남기는 여유(초). 말이 뚝 끊기면 늘리기 |
| `--keep-repeats` | 꺼짐 | 반복·다시 말하기는 두고 추임새만 자르기 |
| `--fillers` | `음,어,으,...` | 추임새 목록 직접 지정 (예: `--fillers 음,어,그니까,약간`) |
| `--no-silence` / `--no-disfluency` | | 무음 컷 / 버벅임 컷 끄기 |
| `--max-chars` | `18` | 자막 한 줄 최대 글자 수 (쇼츠는 `12` 정도 추천) |
| `--font-size` | `7` | 자막 글자 크기 (CapCut 의 크기 값) |
| `--subtitle-y` | `-0.8` | 자막 세로 위치 (-1 맨 아래 ~ 1 맨 위) |
| `--draft-dir` / `--draft-name` | 자동 | 초안 저장 폴더 / 이름 |
| `--replace` | 꺼짐 | 같은 이름 초안 덮어쓰기 (끄면 `_2`, `_3` 을 붙여 새로 만듦) |

## 버벅임을 어떻게 찾나요?

- **추임새**: "음", "어", "으음" 같은 소리 단어
- **반복**: "저는 저는" → 앞의 "저는" 삭제 (중간에 추임새가 끼어 있어도 인식)
- **다시 말하기**: "오늘은 영상을 … 오늘은 영상을 찍어요" → 앞의 실패한 시도를 삭제
- **말더듬**: "그래 그래서" → 앞 조각 삭제
- **`--llm` (Claude)**: 위 규칙으로 못 잡는 NG("잠깐만, 다시 할게요"), 문장을 바꿔 다시 말한 부분,
  음성 인식 오타를 문맥으로 판단합니다. `ANTHROPIC_API_KEY` 환경변수가 필요합니다.

Whisper 는 원래 추임새를 지우고 받아쓰는 경향이 있어서, 추임새가 섞인 예시 문장을 프롬프트로 줘서
들리는 그대로 받아쓰도록 유도합니다.

## 한계 / 문제 해결

- **초안이 안 보여요**: CapCut 을 완전히 종료했다가 다시 여세요. 초안 폴더 경로가 맞는지도 확인하세요.
- **초안이 안 열리거나 비어 있어요**: pycapcut 은 CapCut 이 암호화하지 않은 초안 형식을 씁니다.
  CapCut 버전에 따라 열리지 않을 수 있으니, 그럴 땐 `--render` 로 MP4 를 만든 뒤
  CapCut 의 **텍스트 → 자막 → 자막 가져오기** 로 SRT 를 불러오세요.
- 초안은 원본 영상의 **절대 경로**를 참조합니다. 원본 파일을 옮기면 CapCut 에서 "미디어 없음" 이 뜹니다.
- CapCut 초안의 프레임레이트는 정수만 지원해서 29.97fps 영상은 30fps 초안이 됩니다.
- "정말 정말 좋아요" 같은 의도적인 반복도 잘릴 수 있습니다. 신경 쓰이면 `--keep-repeats` 나 `--llm` 을 쓰세요.

## 테스트

```bash
pip install -e ".[dev]"
pytest
```
