# Fix missing keypoint interpolation prediction causing false movement

- **ID**: 001
- **날짜**: 2026-04-07
- **유형**: 버그 수정

## 작업 요약
보이지 않거나 신뢰도가 낮은 키포인트가 예측/보간되면서 생기는 가짜 움직임(false vertical/horizontal displacement)을 방지하기 위해 움직임 계산 기능을 수정함.
주요 신체 부위가 화면에 3개 미만으로 보일 때는 `stillness`(정지 비율)를 강제로 1.0으로 설정하고, 중심점의 변화량(`center_dy`, `down_speeds`)을 0.0으로 억제함.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`:
  - `_build_xg_feature_windows` 함수에서 주요 8개 키포인트(어깨, 골반, 무릎, 발목)의 유효성 검사 수행.
  - 신뢰할 수 있는 점이 3개 미만이면, XGBoost 분류기로 전달되는 움직임 특징값(feature value parameter)들을 전부 정지 상태를 나타내는 값(0.0)으로 처리하도록 조건식 추가.
