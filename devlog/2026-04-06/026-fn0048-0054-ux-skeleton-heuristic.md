# FN-0048~0054: UX 버그 수정, 스켈레톤 오버레이, 파이프라인 검증

- **ID**: 026
- **날짜**: 2026-04-06
- **유형**: 기능 추가 | 버그 수정

## 작업 요약
웹캠 전환 버그 수정, 로그 관리 UI 개선, 줌 기능 제거, 업로드 분석 결과 스켈레톤 오버레이 추가, 자세 분류 heuristic boost 임계값 교정, XG-Dual 파이프라인 검증 및 arbitration 보완.

## 변경 파일 목록

### Frontend (view.ts)
- **FN-0048**: `ensureWebcamReady()` — 스트림 보유 시 srcObject 재연결 + MediaPipe 재시작 추가
- **FN-0049**: `clearAllLogs()` 메서드 추가 — cleanupLogBlobUrls + render
- **FN-0050**: `webcamZoom` 프로퍼티 + `setWebcamHwZoom()` 메서드 제거
- **FN-0052**: `drawDetectionFrame()` — 좌표 스케일링 수정 (원본 픽셀→캔버스), COCO-17 스켈레톤/키포인트 렌더링 추가
- **FN-0052**: `getVideoContentRect()` 헬퍼 추가 — object-contain 레터박스 보정
- **FN-0052**: `onUploadVideoTimeUpdate()` 추가 — 영상 재생 시간에 맞춘 검출 프레임 동기화

### Frontend (view.pug)
- **FN-0049**: 로그 헤더에 🗑 전체 삭제 버튼 추가
- **FN-0050**: 줌 슬라이더 UI 전체 제거
- **FN-0051**: 웹캠 그리드 컨테이너에 `overflow-hidden` + `grid-rows-[1fr]` 추가
- **FN-0052**: 업로드 비디오에 `(timeupdate)` 이벤트 바인딩

### Backend (video_analysis.py)
- **FN-0053**: `_posture_heuristic_boost()` Rule 1 임계값 교정
  - `stillness < 0.6` → `0.85` (is_moving 완화, has_body_motion으로 게이트)
  - `speed_std > 0.005` → `0.03` (6배 엄격)
  - `upper_motion > 0.01` → `0.05` (5배 엄격)
  - max boost `0.45` → `0.20` (절반 이하)
- **FN-0054**: `_arbitrate_decision()` — Case 4b 추가: `fall_detected=False` + `posture_label='fall'` 시 fall_suspected/uncertain 처리 (기존엔 safe로 잘못 분류)
