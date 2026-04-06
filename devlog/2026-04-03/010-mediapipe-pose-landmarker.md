# MediaPipe PoseLandmarker 클라이언트 사이드 포즈 추정 도입

- **ID**: 010
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
`@mediapipe/tasks-vision` 패키지를 도입하여 웹캠 프리뷰에서 실시간 33-랜드마크 스켈레톤 오버레이를 구현. 서버 분석 시작 없이도 웹캠 활성화만으로 즉시 포즈 표시. Heavy 모델(~17MB)을 Google CDN에서 로드하며, visibility 기반 렌더링(>0.5 실선, 0.15~0.5 점선, <0.15 숨김)으로 가려진 관절도 표시.

## 변경 파일 목록

### package.json (angular)
- **추가**: `@mediapipe/tasks-vision` 의존성

### view.ts
- **추가**: MediaPipe imports (`PoseLandmarker`, `FilesetResolver`, `DrawingUtils`)
- **추가**: `@ViewChild('mpPoseCanvas')` 캔버스 참조
- **추가**: 상태 프로퍼티 — `poseLandmarker`, `mpRunning`, `mpProcessing`, `mpRafId`, `mpInitializing`, `mpReady`, `mpFps`, `mpFrameCount`, `mpFpsTimer`
- **추가**: `MP_POSE_CONNECTIONS` (35쌍), `MP_LANDMARK_COLORS` (부위별 색상)
- **추가**: `initMediaPipePose()` — WASM 런타임 + Heavy 모델 로드, GPU 위임, VIDEO 모드
- **추가**: `startPoseLoop()` — requestAnimationFrame 루프 + 1초 FPS 카운터, 이전 프레임 처리 중 스킵
- **추가**: `stopPoseLoop()` — RAF 취소, 타이머 해제, 캔버스 클리어
- **추가**: `drawMpPose()` — visibility 기반 스켈레톤 드로잉 (실선/점선), 부위별 색상 도트, 얼굴 랜드마크 필터링
- **추가**: `colorWithAlpha()` — hex→rgba 변환 헬퍼
- **수정**: `ensureWebcamReady()` — 웹캠 연결 후 `initMediaPipePose()` 호출
- **수정**: `stopWebcamStream()` — `stopPoseLoop()` 호출 추가
- **수정**: `ngOnDestroy()` — `stopPoseLoop()` 클린업

### view.pug
- **추가**: `#mpPoseCanvas` 캔버스 — 웹캠 활성 시 항상 표시 (z-index 1)
- **추가**: MediaPipe 상태 표시기 — 로딩 중/FPS 표시 (좌상단)
- **수정**: `#realtimeBboxCanvas` — z-index 2로 MediaPipe 위에 레이어링
