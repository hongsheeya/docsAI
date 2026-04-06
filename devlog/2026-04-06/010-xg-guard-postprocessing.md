# XG Guard 후처리 엔진 이식 (5-suppressor + temporal smoothing + decision arbitration)

- **ID**: 010
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
RF 계열에서 검증된 오탐 억제 규칙을 XG-Fall 후처리로 이식하고(5종 suppressor), XG-Posture temporal smoothing(EMA + majority vote + transition constraint), decision arbitration(6-case) 로직을 구현했다.

## 변경 파일 목록

### 수정 파일
- `src/model/struct/video_analysis.py`
  - `_infer_xg_fall()`: motion gate 뒤에 5가지 suppressor 로직 삽입 (stationary, aspect_only, short_clip, fast_sit, controlled_lie), `_suppressed_by` 리스트를 runtime_inference에 포함, short-clip 적응형 threshold 적용
  - `_POSTURE_TRANSITION_ALLOWED`: 6-class 전이 제약 행렬 (dict of sets)
  - `_smooth_posture_sequence()`: EMA + majority vote + transition constraint 결합 temporal smoother
  - `_DECISION_STATES`: 5개 상태값 상수
  - `_arbitrate_decision()`: Fall vs Posture 충돌 해소 — 6 case 분기 (fall/sit 경계, lie 비상 배제, fall confirmed/suspected, posture_only, fallback)
