# XGBoost 기본 모델 전환, UI 통일화, 실시간 로그/팝업 구현

- **ID**: 015
- **날짜**: 2026-04-03
- **유형**: 기능 추가 / 리팩토링

## 작업 요약

FN-20260403-0017~0024 8건을 일괄 수행. 스켈레톤 표시 버그 수정, 분석 시간 표시 보정, XGBoost v2를 기본 모델로 전환, 실시간 오버레이 판단근거 확장(4항목), 전체 텍스트 리뷰(RF v4→RF 보조, XGBoost→XGBoost v2), 파이프라인/매뉴얼 페이지 최신화, UI 너비 통일(max-w-[1800px]), 실시간 분석 로그 리스트+팝업 상세+피드백/재학습 기능 추가.

## 변경 파일 목록

### view.ts (page.dashboard)
- FN-0017: @ViewChild setter 패턴으로 `_mpPoseCanvasRef` 변경, ResizeObserver lazy init, drawMpPose querySelector fallback + canvas size 0 fallback
- FN-0018: `modelSpeedHint()` 웹캠 분기 추가 (RF ~3초, XGBoost ~8초)
- FN-0019: `selectedModelType` 기본값 'person-feature', `currentEngineLabel()`/`currentEngineNote()` 텍스트 갱신
- FN-0020: `updateRealtimeOverlay()` basis 2→4개 (모델명, 확률, 검출프레임, Guard, Short-clip, 소요시간)
- FN-0024: realtimeLogEntries[] 등 12개 상태변수 추가, pushRealtimeLog/openLogDetail/closeLogDetail/logRiskClass/logRiskDotClass/submitLogFeedback/cleanupLogBlobUrls 메서드 구현

### view.pug (page.dashboard)
- FN-0017: canvas에 data-mp-pose-canvas 속성 추가
- FN-0023: max-w-7xl → max-w-[1800px] (nav, hero, footer 3곳)
- FN-0024: 인라인 피드백 섹션에 `*ngIf="inputMode !== 'webcam'"` 추가, 실시간 로그 리스트 UI + 팝업 모달 (~100줄) 추가

### video_analysis.py (server model)
- FN-0018: realtime_chunk_sec 4→5
- FN-0019: _model_options() default→'person-feature', fallback 순서 변경, _analysis_engine_summary()/_analysis_diagnostics() XGBoost 우선
- FN-0021: 전체 텍스트 리뷰 (~20곳), RF v4→RF 보조, XGBoost→XGBoost v2, 4초→5초

### page.pipeline/view.pug
- FN-0022: XGBoost v2 흐름도 추가(violet), RF→RF 보조 리네이밍, 비교 테이블 갱신
- FN-0023: max-w-7xl → max-w-[1800px]

### page.manual/view.pug
- FN-0022: 모델 선택 순서 변경(XGBoost 기본), 4초→5초, RF v4→RF 보조, 임계값 설명 갱신
