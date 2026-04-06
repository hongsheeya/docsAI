# 낙상 분류기 학습 및 평가 (LR/RF/XGBoost)

- **ID**: 019
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
FN-0016의 194개 feature window(Y:82, N:112)를 대상으로 LR/RF/XGBoost 3종 분류기를 Stratified 5-Fold CV로 비교 평가했다. XGBoost(F1=0.7014, AUC=0.8428)이 best로 선정되었고, best_model.pkl로 저장. Top feature: max_down_speed, center_dy, n_points.

## 변경 파일 목록

### 신규 생성
- `scripts/train_fall_classifier.py`: 분류기 학습 스크립트 (LR/RF/XGBoost, 5-fold CV)

### 수정
- `storage/training/fall-detection/model/baseline_model.json`: `fall_classifier` 섹션 추가

### 산출물
- `storage/training/fall-detection/fall-classifier/best_model.pkl`: XGBoost 모델
- `storage/training/fall-detection/fall-classifier/evaluation.json`: 평가 결과
- `storage/training/fall-detection/fall-classifier/logisticregression_model.pkl`
- `storage/training/fall-detection/fall-classifier/randomforest_model.pkl`
- `storage/training/fall-detection/fall-classifier/xgboost_model.pkl`

## CV 결과
| 모델 | F1 | AUC-ROC | Accuracy | Precision | Recall |
|------|-----|---------|----------|-----------|--------|
| LogisticRegression | 0.5419 | 0.6480 | 0.6592 | 0.6324 | 0.4750 |
| RandomForest | 0.7012 | 0.8471 | 0.7680 | 0.7786 | 0.6463 |
| **XGBoost** | **0.7014** | 0.8428 | 0.7525 | 0.7306 | 0.6824 |

## Top-5 Feature Importance (XGBoost)
1. max_down_speed: 0.1613
2. center_dy: 0.1447
3. n_points: 0.1395
4. aspect_change: 0.1118
5. floor_proximity: 0.1107
