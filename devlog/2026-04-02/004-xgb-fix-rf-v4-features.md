# XGBoost Fallback 수정 + RF v4 피처 개선 + 판단근거 짝수 표시

- **ID**: 004
- **날짜**: 2026-04-02
- **유형**: 버그 수정 + 기능 개선

## 작업 요약
1. XGBoost fallback 수정: `baseline_model.json`에 `fall_classifier.path` 누락 → 추가
2. RF 판단근거 표시 개수를 홀수(7)에서 짝수(6)로 변경
3. RF 피처 v4 개선: area/width 관련 5개 제거, 가속도/자세높이 2개 추가 (16→13개)
4. UI 전체 피처 수 표기 업데이트 (16→13)

## 변경 파일 목록

### XGBoost Fallback 수정
- `_appdata/storage/training/fall-detection/model/baseline_model.json`: `fall_classifier.path` 필드 추가 (`storage/training/fall-detection/fall-classifier/best_model.pkl`)
  - 원인: 학습 시 path 미등록으로 `_person_feature_available()` → False → fallback

### RF 판단근거 짝수 표시
- `src/model/struct/video_analysis.py`: `_scored[:7]` → `_scored[:6]`

### RF 피처 v4 개선
- `src/model/struct/video_analysis.py`:
  - `_RF_FEATURE_COLUMNS`: 16개→13개 (area_mean/area_std/delta_area_mean/width_mean/width_std 제거, delta_y_accel_max/final_height_ratio 추가)
  - `_extract_rf_pipeline_features()`: 가속도/자세높이 계산 로직 추가, motion guard용 보조값 유지
  - `_feat_labels`: 새 피처 라벨 추가
  - `_rf_fall_thresholds`: 새 피처 임계값 추가, 제거된 피처 제거
  - `_RF_DISPLAY_WEIGHTS`: 새 피처 가중치 추가
  - `_EXCLUDE_FROM_BASIS`: `{'area_mean'}` → `set()` (피처 자체 제거됨)
  - level 판정: `final_height_ratio` 역방향 비교 추가

### UI 업데이트
- `src/app/page.pipeline/view.pug`: "16개 통계 특징" → "13개 통계 특징", 설명 변경
- `src/app/page.manual/view.pug`: "16개 통계 특징" → "13개 통계 특징"
- `src/app/page.dashboard/view.ts`: `currentEngineNote()`, `getRiskScoreFormula()` → 13개 + 새 피처 설명

### 재학습 스크립트
- `scripts/retrain_rf_v4.py`: v3 기반 + 새 13개 피처 추출·학습 (실행 중)

## 비고
- 재학습 완료 후 threshold 변경이 필요할 수 있음
- XGBoost 모델 타입: Pipeline(StandardScaler + XGBClassifier), joblib 포맷
