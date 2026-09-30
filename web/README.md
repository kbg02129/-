# 캡컷 에이전트 · iPad 웹 (1단: 무음 점프컷)

서버 없이 iPad Safari 안에서 동작하는 한 장짜리 페이지입니다.

- 분석: Mediabunny 로 오디오를 해독해 10ms 단위 음량(dB) 계산 → 무음 구간 감지
- 렌더링: WebCodecs(H.264 하드웨어 인코더)로 남길 구간만 이어 붙인 MP4 생성.
  브라우저에 AAC 인코더가 없으면 `@mediabunny/aac-encoder`(WASM)로 대체
- 저장: claude.ai 에서는 저장 기능, 일반 브라우저에서는 iPad 공유 시트(비디오 저장 / CapCut)

`index.html` 은 claude.ai Artifact 형식(doctype 없이 본문만)입니다.
다른 곳에 올릴 때는 `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>` 로 감싸서 HTTPS 로 제공하세요 (WebCodecs 는 보안 컨텍스트 필요).
