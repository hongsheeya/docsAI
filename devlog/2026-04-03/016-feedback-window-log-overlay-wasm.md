# 피드백 클릭 수정, 4초 윈도우, 로그 삭제, 오버레이 피처, WASM 경고 (FN-0025~0029)

- **ID**: 016
- **날짜**: 2026-04-03
- **유형**: 기능 추가 / 버그 수정

## 작업 요약
5개 작업을 일괄 수행: 피드백 버튼 클릭 오류(service.render 누락) 수정, 실시간 윈도우 5→4초·오버랩 2→3초 변경, 로그 개별/전체 삭제 기능 추가, 오버레이 판단 근거에서 모델명 제거 후 핵심 피처값(delta_y_max, final_height_ratio) 표시, MediaPipe PoseLandmarker에 outputSegmentationMasks:false 추가.

## 변경 파일 목록

### view.ts
| 변경 | 내용 |
|------|------|
| FN-0025 | `setFeedbackActualLabel()`, `setLogFeedbackStatus()`, `setLogFeedbackActualLabel()` 메서드 추가 (명시적 service.render 호출) |
| FN-0026 | `realtimeIntervalSec` 5→4, `realtimeOverlapSec` 2→3, `lastNonEmptyOverlayBasis` 캐시로 판단 근거 사라지는 버그 방지 |
| FN-0027 | `deleteLogEntry(entry)` 개별 삭제 + `clearAllLogs()` 전체 삭제 메서드 (Blob URL revoke 포함) |
| FN-0028 | `updateRealtimeOverlay()` 개편: 모델명 제거, `features.delta_y_max`/`final_height_ratio` 피처값 표시, 최대 5항목 |
| FN-0029 | PoseLandmarker 옵션에 `outputSegmentationMasks: false` 추가 (NORM_RECT 경고 최소화) |

### view.pug
| 변경 | 내용 |
|------|------|
| FN-0025 | 업로드 피드백 실제 라벨 버튼 → `setFeedbackActualLabel()` 호출로 변경 |
| FN-0025 | 로그 팝업 피드백 버튼 → `setLogFeedbackStatus()`/`setLogFeedbackActualLabel()` 호출로 변경 |
| FN-0027 | 로그 헤더에 "전체 삭제" 버튼 추가 |
| FN-0027 | 로그 항목별 X 삭제 버튼 추가 (stopPropagation으로 상세 팝업 방지) |
| FN-0028 | 오버레이에서 `realtimeOverlayRuntime` 표시 라인 제거 |
