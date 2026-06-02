# RF 낙상 모델 피처 확장 검토

- **ID**: 008
- **날짜**: 2026-04-13
- **유형**: 리서치 / 설계

## 작업 요약
RF 낙상 모델의 13-feature bbox 통계에 12개 keypoint-based pose feature를 추가하여 25-feature로 확장할 수 있는지 검토했다. 기술적으로 완전히 타당하며, 대부분의 코드가 이미 존재한다. 하위 호환성 분기를 코드에 미리 삽입했다.

## 검토 결과

### 타당성: ✅ 높음
- Unified timeseries에 **keypoint 데이터가 이미 포함** (추가 YOLO pass 불필요)
- `_extract_pose_features()` 메서드로 12개 pose feature 계산 로직 이미 완비
- RF-Pose 학습/추론 코드가 deprecated 상태지만 reference로 활용 가능
- `_compute_rf_features_from_timeseries()`에 약 20줄 추가로 통합 가능

### 추가 가능한 핵심 Feature

| Feature | 효과 | 비고 |
|---------|------|------|
| `body_tilt_angle_mean/max` | **높음** — 낙상 시 기울기 각도 급증 | 각도이므로 좌표계 무관 |
| `height_ratio_mean/min` | **높음** — 서기/쓰러짐 직접 반영 | 비율 기반 |
| `center_descent_speed_mean/max` | **높음** — bbox delta_y와 보완적 | 몸 중심 4-keypoint 기반 |
| `knee_bend_angle_mean/min` | 중간 — 무너지는 과정 포착 | 하체 keypoint conf 의존 |
| `horizontal_spread_mean/max` | 중간 — 누운 자세 식별 | std 값 |
| `pose_change_rate_mean/max` | 중간 — 급격한 자세 변화 감지 | 코사인 비유사도 |

### 예상 개선
- F1 3-7% 개선, 특히 **위양성(FP) 감소** 효과 예상
- 앉기↔눕기 오분류 개선 (bbox만으로는 구분 어려운 케이스)

### 리스크
- **학습 데이터 부족**: intake 디렉토리가 비어 25-feature 모델 학습 불가 (데이터 축적 필요)
- **과적합**: 13→25 feature 증가 시 데이터 부족 환경에서 과적합 가능
- **RF-Pose deprecated 이유 불명**: shadow mode 비교 테스트로 재검증 필요

### 구현 준비
`_compute_rf_features_from_timeseries()`에 하위 호환성 분기를 삽입:
- RF 모델의 `n_features_in_`가 13보다 크면 자동으로 pose feature 추출/추가
- 기존 13-feature 모델은 변경 없이 동작

## 변경 파일 목록

### `src/model/struct/video_analysis.py`
- `_compute_rf_features_from_timeseries()`: 하위 호환 pose feature 확장 분기 추가
  - `rf_model.n_features_in_ > 13` → `_POSE_FEATURE_COLUMNS` 12개 추가
  - timeseries keypoints → `_extract_pose_features()` → feat_df 확장
  - 기존 13-feature 모델: 변경 없음
