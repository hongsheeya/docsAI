# 임계값 정합화·엔진 동기화·HITL 재학습 보강·모델 비교 보고서

- **ID**: 005
- **날짜**: 2026-03-30
- **유형**: 기능 추가 / 버그 수정 / 리팩토링

## 작업 요약
FN-20260330-0001~0006 6개 작업을 일괄 수행했다. 낙상 판정 임계값 0.5 통일, RF fast/balanced 해상도 차별화, XGBoost 0점 진단 보완, trained-yolo 고아 코드 제거 및 엔진 표시 동기화, HITL 재학습 예외 처리 보강, XGBoost vs RF 비교 보고서 추가.

## 변경 파일 목록

### 백엔드 (video_analysis.py)
- `fall_decision_threshold = 0.5` 통일 (FN-0001)
- `_RF_YOLO_IMGSZ = 640` / `_RF_YOLO_IMGSZ_FAST = 320` 상수 추가, `_infer_rf_pipeline`에 `yolo_imgsz` 분기 적용 (FN-0002)
- `_analysis_profiles()` 설명 현실화 (fast 10~20초, balanced 30~60초) (FN-0002)
- `_infer_person_feature` 진단 `pf_summary` 추가 (사람 미검출/윈도우 부족/정상) (FN-0003)
- `_infer_with_trained_model` person-feature 0점 시 RF fallback 로직 (FN-0003)
- `_infer_yolo_cls` 고아 코드(`training_samples`, `runtime_mode`, `rf_metric_ready` 참조) 제거 (FN-0004)
- `retrain_baseline()` `except Exception: pass` → 에러 캡처 + 타임스탬프 추가 (FN-0005)
- `_model_comparison_report()` XGBoost vs RF 비교 보고서 메서드 추가, `prototype_info`에 포함 (FN-0006)
- `_emergency_protocol()` medium trigger 문구 `risk_score >= 0.5`로 수정 (FN-0001)

### 백엔드 (video_baseline.py)
- `decision_threshold` / `threshold` 4곳 모두 0.5로 변경 (FN-0001)

### 스크립트 (yolo_fall_runtime.py)
- `--threshold` argparse 기본값 2곳 0.5로 변경 (FN-0001)

### 프론트엔드 (view.ts)
- `currentEngineLabel()` / `currentEngineNote()` 메서드 추가 — 모델 선택에 따라 엔진 라벨 동적 반영 (FN-0004)
- `submitAnalysisFeedback` 재학습 에러 표시 개선 (FN-0005)

### 프론트엔드 (view.pug)
- 상단 카드 및 Live Preview의 엔진 라벨을 `currentEngineLabel()` / `currentEngineNote()`로 치환 (FN-0004)
