# 웹캠 UX 전면 개선 + 실시간 오버레이 + 휴리스틱 fallback 수정

- **ID**: 014
- **날짜**: 2026-04-03
- **유형**: 기능 추가 / UI 개선 / 버그 수정

## 작업 요약
FN-0011~0016 일괄 수행. Bbox 오버레이 비활성화(성능), 스켈레톤 항상 표시 확인, 기본 웹캠 모드, 화면 대형화, 실시간 점수 오버레이, RF 휴리스틱 fallback 복합 개선(최소 검출 완화+YOLO conf 하향+프레임 샘플링 강화)을 적용했다.

## 변경 파일 목록

### view.ts (page.dashboard)
- `bboxOverlayEnabled: boolean = false` — bbox 캔버스 렌더링 비활성화 (FN-0011)
- `drawRealtimeBboxOverlay()`, `startUploadBboxLoop()` — early return guard 추가 (FN-0011)
- `inputMode` 초기값 `'upload'` → `'webcam'` (FN-0013)
- `ngOnInit()` — webcam 모드일 때 `ensureWebcamReady()` 자동 호출 (FN-0013)
- 7개 오버레이 필드 추가: `realtimeOverlayScore`, `realtimeOverlayLevel`, `realtimeOverlayLabel`, `realtimeOverlayBasis`, `realtimeOverlayRuntime`, `realtimeOverlayFlash`, `realtimeOverlayFlashTimer` (FN-0015)
- `updateRealtimeOverlay()` 메서드 신규 — 누적 점수%, 등급, 라벨, 판단근거 요약, 런타임키 계산 (FN-0015)
- `dispatchRealtimeChunk()` — 결과 수신 후 `updateRealtimeOverlay()` 호출 (FN-0015)
- `ngOnDestroy()` — flash 타이머 정리 추가 (FN-0015)

### view.pug (page.dashboard)
- 분석 섹션 컨테이너: `max-w-7xl` → `max-w-[1800px]` (FN-0014)
- 웹캠 영역: `min-height: 500px` → `70vh` (FN-0014)
- realtimeBboxCanvas 주석 처리 (FN-0011)
- 기존 미니 감지 패널 → 확대된 실시간 오버레이로 교체: 점수 바, 판단 근거, 런타임, flash 효과 (FN-0015)

### video_analysis.py (model/struct)
- `_extract_rf_pipeline_features()` 시그니처에 `input_source` 파라미터 추가 (FN-0016)
- webcam-live 시 `_RF_TARGET_FPS` 2→4 (프레임 샘플링 강화) (FN-0016-C)
- webcam-live 시 YOLO conf 0.25→0.15 (검출률 향상) (FN-0016-B)
- webcam-live 시 최소 검출 프레임 2→1 (완화) (FN-0016-A)
- `_infer_rf_pose_pipeline()`, `_infer_rf_pipeline()` 호출부에 `input_source` 전달

### 미변경 확인 (FN-0012)
- `stopRealtimeAnalysis()`는 이미 `stopPoseLoop()` 미호출 — 스켈레톤이 분석 중단 후에도 유지됨
- 설계상 정상 동작 확인, 코드 변경 불필요
