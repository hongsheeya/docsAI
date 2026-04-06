# XG 피처 확장 (10→37개) 및 XG-Fall 파이프라인 통합

- **ID**: 007
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
XG-Fall 37-feature binary classifier 추론 + 재학습 파이프라인을 video_analysis.py에 구현했다. 기존 10-feature person-feature 파이프라인 위에 XG-Fall이 최우선 fallback으로 동작하며, 재학습 시 retrain_baseline 체인에 자동 포함된다.

## 변경 파일 목록

### 수정: src/model/struct/video_analysis.py (4637 → 5050 lines, +413 lines)
- **모델 경로 상수**: `_XG_FALL_MODEL_REL_PATH`, `_XG_FALL_SUMMARY_REL_PATH`, `_XG_POSTURE_MODEL_REL_PATH`, `_XG_POSTURE_SUMMARY_REL_PATH` + 캐시 변수
- **모델 헬퍼**: `_xg_fall_model_path()`, `_xg_fall_summary()`, `_xg_fall_available()`, `_get_xg_fall_model()`, `_xg_posture_*()` 동일 세트
- **추론**: `_infer_xg_fall()` — unified timeseries → 37-feature window → XGBoost predict + motion gate + score aggregation
- **재학습**: `retrain_xg_fall()` — intake Y/N 데이터 → unified timeseries → peak window 37-feature extraction → XGBClassifier 학습 + CV + atomic save
- **fallback 체인**: `_infer_with_trained_model()`에 xg-fall 최우선 추가 (xg-fall → person-feature → rf-pipeline → rf-pose)
- **retrain_baseline**: XG-Fall 재학습 단계 추가 (`xg_fall_training` 키)
