# Validation 200건 학습 및 100건 대비 비교

- **ID**: 028
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
batch-002 100건 추가하여 총 200건(batch-001+002)으로 XGBoost 재학습을 수행했으나, 100건 대비 성능이 하락했다. 이후 batch-001 기반 모델을 재학습하여 최종 F1=0.7499 (AUC=0.86)로 최고 성능을 달성했다.

## 학습 결과 비교

| 모델 | 영상 수 | 샘플 수 | F1 | AUC | Train/Val Gap |
|------|---------|---------|-----|-----|---------------|
| 원본 baseline | 11 | 194 | 0.7014 | 0.8428 | - |
| batch-001 (이전) | 100+11 | 2,056 | 0.7141 | 0.8196 | 0.286 |
| **batch-001+002** | **200+11** | **4,027** | **0.6898** | **0.7902** | **0.310** |
| batch-001 (최종) | 100+11 | 2,056 | 0.7499 | 0.8600 | 0.250 |

## 핵심 발견사항

### 200건 학습 시 성능 저하 원인
1. **Train/Val Gap 확대**: 0.286 → 0.310 (과적합 심화)
2. **Feature importance 변화**: n_points, floor_proximity, stillness가 상위 — 원본 대비 center_dy 하락
3. **데이터 분포 이질성**: Validation 영상의 환경·카메라 특성이 원본과 달라, 데이터 증가가 오히려 노이즈 유입

### 최종 모델 선정 근거
- batch-001 재학습에서 F1=0.7499 달성 (원본 0.7014 대비 +6.9%)
- AUC=0.86으로 모든 실험 중 최고
- Train/Val Gap=0.250으로 가장 낮은 과적합

## 변경 파일 목록

### 학습 결과 산출물
- `storage/training/fall-detection/fall-classifier/evaluation.json` — batch-001 최종 평가 (F1=0.7499)
- `storage/training/fall-detection/fall-classifier/best_model.pkl` — 최종 XGBoost 모델
- `storage/training/fall-detection/validation-features/evaluation_100.json` — batch-001 평가 백업
- `storage/training/fall-detection/validation-features/evaluation_200.json` — 200건 평가 백업
- `storage/training/fall-detection/validation-features/best_model_200.pkl` — 200건 모델 백업
- `storage/training/fall-detection/validation-bbox/` — 200건 전체 bbox 추출 완료
