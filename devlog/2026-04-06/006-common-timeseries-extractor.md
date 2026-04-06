# 공통 person timeseries 추출기 구축

- **ID**: 006
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
분산된 RF/XG 피처 추출 파이프라인을 통합하는 공통 시계열 추출기 2개 메서드와 37-feature 칼럼 정의를 `video_analysis.py`에 추가했다. 기존 코드는 수정하지 않고 신규 메서드만 삽입하여 하위 호환성을 유지한다.

## 변경 파일 목록

### 신규 추가 (src/model/struct/video_analysis.py — 4081 → 4636 lines, +555 lines)
- `_XG_FEATURE_COLUMNS` (클래스 변수): 37개 피처 칼럼 정의 (bbox 10 + pose 12 + temporal 5 + transition 4 + gait 3 + lie/fall 3)
- `_extract_unified_timeseries(video_path, input_source)`: YOLO-Pose 기반 통합 시계열 추출기
  - 프레임 샘플링 → YOLO 예측 → 가장 큰 사람 bbox 선택 → 정규화 좌표 bbox + 17포인트 keypoint + 시간 정보를 일괄 추출
  - upload/realtime 모드별 파라미터 자동 분기 (fps, imgsz, conf, max_frames)
  - detection_frames 시각화 데이터도 함께 반환
- `_build_xg_feature_windows(timeseries, vid_meta, window_sec, stride_sec)`: 슬라이딩 윈도우 피처 빌더
  - 37개 피처를 윈도우 단위로 계산: bbox 통계, pose keypoint 파생, temporal transition, FFT 기반 주기성, 선형 회귀 기반 slope
  - Fall용 1.0s/0.5s stride, Posture용 1.5-2.0s 등 유연한 윈도우 설정 지원
