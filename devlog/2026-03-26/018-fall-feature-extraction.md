# bbox 궤적 기반 낙상 feature 추출

- **ID**: 018
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
fine-tuned person detector의 bbox 추적 데이터(FN-0012)를 기반으로, track별 슬라이딩 윈도우(1초/0.5초 stride)로 7+α개 모션 feature를 추출하는 스크립트를 작성·실행했다. 11개 영상에서 총 194개 feature window(Y:82, N:112)를 생성.

## 변경 파일 목록

### 신규 생성
- `scripts/extract_fall_features.py`: bbox 궤적 feature 추출 스크립트
  - 입력: `person-bbox/*.json` (FN-0012 산출물)
  - 슬라이딩 윈도우: 1초 단위, 0.5초 stride
  - Feature: center_dy, height_ratio, aspect_change, stillness, floor_proximity, area_change, vert_horiz_ratio, max_down_speed, avg_conf, n_points
  - 출력: per-video CSV + 통합 `fall_features_all.csv` + `feature_summary.json`

### 산출물
- `storage/training/fall-detection/fall-features/fall_features_all.csv`: 194행 통합 CSV (76KB)
- `storage/training/fall-detection/fall-features/feature_summary.json`: 요약 통계
- `storage/training/fall-detection/fall-features/{video_name}.csv`: 11개 per-video CSV

## Feature 분포 (Y vs N 평균)
| Feature | Y(낙상) | N(정상) |
|---------|---------|---------|
| center_dy | +0.0133 | -0.0074 |
| height_ratio | -0.0125 | +0.0506 |
| aspect_change | +0.0240 | -0.0149 |
| stillness | 0.9276 | 0.9055 |
| floor_proximity | 0.6371 | 0.6972 |
| area_change | +0.0255 | +0.0685 |
