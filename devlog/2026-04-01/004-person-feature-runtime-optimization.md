# Person-Feature 런타임 최적화

- **ID**: 004
- **날짜**: 2026-04-01
- **유형**: 성능 개선

## 작업 요약
RF 파이프라인 대비 person-feature(XGBoost) 파이프라인의 과도한 지연 원인을 분석하고, 인프로세스 실행·모델 캐시·추적 프레임 수 축소를 적용했다. subprocess 기반 초기화 비용과 과도한 추적 프레임 처리량을 줄여 반복 호출 시 지연을 크게 낮추는 방향으로 개선했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - person-feature 추론을 subprocess 우선 구조에서 인프로세스 캐시 모듈 우선 구조로 변경
  - 실패 시 subprocess fallback 유지
- `scripts/yolo_fall_runtime.py`
  - YOLO detector / XGBoost classifier 캐시 추가
  - balanced 프로필 `track_imgsz` 및 `vid_stride` 조정
