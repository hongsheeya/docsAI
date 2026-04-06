# 최종 추가학습 모델 웹 분석 파이프라인 적용

- **ID**: 030
- **날짜**: 2026-03-26
- **유형**: 설정 변경

## 작업 요약

Validation batch-001 추가학습 모델(XGBoost F1=0.7499)을 웹 분석 파이프라인의 운영 모델로 반영했다. `baseline_model.json` 메타데이터를 갱신하고, cascade 파이프라인(person-feature → trained-yolo → heuristic) 전 단계의 정상 동작을 검증했다.

## 변경 내역

### 1. baseline_model.json 메타데이터 갱신

| 필드 | 변경 전 | 변경 후 |
|------|---------|---------|
| `fall_classifier.cv_f1` | 0.7014 | **0.7499** |
| `fall_classifier.cv_auc` | 0.8428 | **0.8600** |
| `fall_classifier.training_samples` | (없음) | **2250** |
| `fall_classifier.training_videos` | (없음) | **111** |
| `fall_classifier.training_source` | (없음) | original 11 + validation batch-001 100 |
| `fall_classifier.updated_at` | (없음) | 2026-03-26 |

### 2. 모델 파일 상태 (이미 업데이트됨)

- `best_model.pkl` (458KB): Pipeline(StandardScaler + XGBClassifier(n_estimators=200, max_depth=6))
- 이전 세션에서 batch-001 재학습 시 이미 교체됨

### 3. training_summary.json 보강

- `fall_classifier` 섹션 추가 (type, cv_f1, cv_auc, training_samples, training_source)

### 4. Cascade 파이프라인 검증 결과

| 단계 | 상태 | 비고 |
|------|------|------|
| person-feature (XGBoost) | ✅ READY | Person detector + XGBoost classifier 모두 존재, **우선 사용** |
| trained-yolo (YOLO-cls) | ✅ READY | YOLO11n-cls weights 존재 |
| heuristic-fallback | ✅ READY | 항상 사용 가능 |

### 5. 추론 흐름

```
웹 업로드 → video_analysis._infer_with_trained_model()
  → _person_feature_available() == True
    → _infer_person_feature()
      → yolo_fall_runtime.py person-feature mode
        → Person detection (YOLO custom weights)
        → ByteTrack tracking (vid_stride, track_conf)
        → Feature extraction (10 features per 5s window)
        → XGBoost prediction (best_model.pkl)
      → 결과 반환 (fall_score, events, analysis_basis)
```

## 변경 파일 목록

### 수정
- `storage/training/fall-detection/model/baseline_model.json` — fall_classifier 메트릭 및 메타데이터 갱신
- `storage/training/fall-detection/model/training_summary.json` — fall_classifier 섹션 추가
