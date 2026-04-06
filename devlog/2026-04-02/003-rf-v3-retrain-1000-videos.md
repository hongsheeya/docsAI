# RF v3 대규모 재학습 — 1000영상 + 정확도 최적화

- **ID**: 003
- **날짜**: 2026-04-02
- **유형**: 기능 추가 / 모델 재학습

## 작업 요약
RF 파이프라인을 1000개 영상(학습 800 + 검증 200)으로 대규모 재학습 수행. 12개 하이퍼파라미터 조합 × 36개 threshold 그리드 탐색으로 정확도를 대폭 향상. 8단계 증분 학습으로 학습 곡선 추적.

## 성능 변화 (v2 → v3)
| 지표 | v2 (이전) | v3 (현재) | 변화 |
|------|----------|----------|------|
| Accuracy | 83.9% | 90.5% | +6.6% |
| Precision | 76.2% | 87.2% | +11.0% |
| Recall | 99.0% | 95.0% | -4.0% |
| F1 | 86.1% | 90.9% | +4.8% |
| Threshold | 0.25 | 0.42 | — |

## 최종 하이퍼파라미터
- n_estimators=300, max_depth=None, min_samples_leaf=2, class_weight=balanced
- Threshold: 0.42

## 학습 곡선 (Recall ≥ 0.95 기준)
| Stage | 학습 수 | Acc | Prec | Rec | F1 | Thr |
|-------|---------|-----|------|-----|-----|-----|
| 1 | 100 | 0.875 | 0.820 | 0.950 | 0.880 | 0.44 |
| 2 | 200 | 0.880 | 0.833 | 0.950 | 0.888 | 0.43 |
| 3 | 300 | 0.890 | 0.848 | 0.950 | 0.896 | 0.40 |
| 4 | 400 | 0.890 | 0.848 | 0.950 | 0.896 | 0.44 |
| 5 | 500 | 0.895 | 0.856 | 0.950 | 0.900 | 0.47 |
| 6 | 600 | 0.910 | 0.880 | 0.950 | 0.913 | 0.45 |
| 7 | 700 | 0.910 | 0.880 | 0.950 | 0.913 | 0.44 |
| 8 | 800 | 0.915 | 0.888 | 0.950 | 0.918 | 0.42 |

## 데이터 구성
- 학습: Fall 400 + NonFall 400 = 800 (Fall FY/BY/SY 혼합, NonFall N/N)
- 검증: Fall 100 + NonFall 100 = 200
- 총 1000개 영상 사용

## 변경 파일 목록

### 스크립트 생성
- `scripts/retrain_rf_v3.py` — 1000영상 대규모 학습 + 그리드 탐색 스크립트

### 모델 업데이트
- `storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl` — v3 모델로 교체 (이전 모델 .bak 백업)
- `storage/training/fall-detection/rf-pipeline/training_summary.json` — 학습 요약
- `storage/training/fall-detection/rf-pipeline/grid_search_v3_*.json` — v3 그리드 탐색 결과

### Threshold 적용
- `src/model/struct/video_analysis.py` — `fall_decision_threshold` 0.25 → 0.42, 관련 주석 업데이트
- `src/app/page.pipeline/view.pug` — RF 낙상 임계값 표시 "25%" → "42%"
- `src/app/page.dashboard/view.ts` — getRiskScoreFormula() RF formula "threshold(25%)" → "threshold(42%)"
