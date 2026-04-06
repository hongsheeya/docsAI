# XG-Dual 추론 파이프라인 구현 (XG-Fall + XG-Posture 동시 추론)

- **ID**: 011
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
XG-Fall(binary, 1.0s window)과 XG-Posture(6-class, 1.5s window)를 공유 timeseries에서 한 번에 추론하는 `_infer_xg_dual()` 메서드를 구현하고, 디스패처 fallback 최상위에 등록했다. 결과에 posture_probs, decision_state, explain 포함.

## 변경 파일 목록

### 수정 파일
- `src/model/struct/video_analysis.py`
  - `_infer_xg_dual()`: ~220 lines. 공유 timeseries → Fall 1.0s + Posture 1.5s → smoothing → arbitration → 통합 결과
  - `_xg_dual_empty_result()`: timeseries 부족 시 빈 결과 반환
  - `_infer_with_trained_model()`: xg-dual을 fallback chain 최상위에 추가, xg_dual_ready / xg_posture_ready 변수 추가
