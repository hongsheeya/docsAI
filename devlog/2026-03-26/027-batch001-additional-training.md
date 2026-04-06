# Validation batch-001 100건 1차 추가학습

- **ID**: 027
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
Validation batch-001(100건)에서 person bbox 추출 → feature 추출 → XGBoost 재학습을 수행. 기존 11영상(194 windows)에 100영상(1,862 windows) 추가로 2,056 windows 기반 학습 완료.

## 결과

### 성능 비교 (기존 vs batch-001)
| 지표 | 기존 (194 samples) | batch-001 (2,056 samples) | 변화 |
|------|-------------------|--------------------------|------|
| F1 | 0.7014 | 0.7141 | +0.013 |
| AUC | 0.8428 | 0.8196 | -0.023 |
| Dataset Y/N | 82/112 | 934/1122 | ×10.6배 |
| Precision | - | 0.7306→0.7141 | - |

### Train/Val Gap (과적합 진단)
| 모델 | Train F1 | Val F1 | Gap |
|------|----------|--------|-----|
| XGBoost | 1.0000 | 0.7141 | 0.286 |
| RandomForest | 1.0000 | 0.6929 | 0.307 |
| LogisticRegression | 0.5228 | 0.4948 | 0.028 |

### 주요 Feature 변화
- floor_proximity가 1위로 상승 (기존 5위)
- max_down_speed 4위 유지
- center_dy 순위 하락 (기존 2위 → 6위 이하)

## 변경 파일 목록
- `storage/training/fall-detection/validation-bbox/`: 100개 영상 bbox JSON
- `storage/training/fall-detection/validation-features/features_combined.csv`: 통합 feature CSV
- `storage/training/fall-detection/fall-classifier/best_model.pkl`: 업데이트된 XGBoost 모델
- `storage/training/fall-detection/fall-classifier/evaluation.json`: 평가 결과
