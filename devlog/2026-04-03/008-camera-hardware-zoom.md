# 카메라 하드웨어 줌 아웃 — CSS 스케일 제거 및 실제 카메라 제어

- **ID**: 008
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
기존 CSS `transform: scale()` 기반 줌은 화면 크기만 조절할 뿐 카메라 FOV를 변경하지 못함. 하드웨어 줌 API(`MediaStreamTrack.getCapabilities().zoom` + `applyConstraints()`)로 교체하고, `getUserMedia()`에 1920×1080 해상도를 요청하여 FOV를 확보함.

## 변경 파일 목록

### view.ts
- **제거**: `webcamZoom`, `webcamFitMode`, `adjustWebcamZoom()`, `resetWebcamZoom()`, `toggleWebcamFitMode()`
- **추가**: `webcamHwZoomSupported`, `webcamHwZoomMin/Max/Step/Value` 프로퍼티
- **수정**: `ensureWebcamReady()` — `getUserMedia()` 제약조건에 `width: { ideal: 1920 }, height: { ideal: 1080 }` 추가
- **추가**: `initCameraHwZoom()` — 트랙 capabilities에서 zoom 지원 여부 확인, 최솟값(줌 아웃)으로 자동 설정
- **추가**: `setWebcamHwZoom(value)` — 하드웨어 줌 슬라이더 핸들러

### view.pug
- **수정**: 웹캠 video 요소 — CSS transform 제거, `object-contain` 클래스 적용
- **교체**: 기존 CSS 줌/핏 모드 컨트롤 → 하드웨어 줌 슬라이더 (지원 시에만 표시)
