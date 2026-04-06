# RF 파이프라인 fallback 모델 피처 불일치 수정

- **ID**: 012
- **날짜**: 2026-04-03
- **유형**: 버그 수정

## 작업 요약
RF 파이프라인이 heuristic fallback으로 빠지는 문제의 근본 원인을 진단·수정. 서버 fallback 모델(`/opt/app/rf_model_server.pkl`)이 16피처로 학습되어 있었으나, 코드의 `_RF_FEATURE_COLUMNS`는 13피처. 재학습 중 HITL 모델이 일시 부재 시 16피처 모델로 fallback → 피처 불일치 → predict 예외 → heuristic fallback 발생.

## 변경 파일 목록

### 모델 파일
- `/opt/app/rf_model_server.pkl`: 16피처 모델 → 13피처 HITL 모델로 교체

### 백엔드 — video_analysis.py
- `retrain_rf_pipeline()`: `joblib.dump()` 직접 호출 → atomic write (tempfile → `os.replace()`) 변경. 재학습 완료 후 서버 fallback 모델 자동 동기화 추가.
- `retrain_rf_pose_pipeline()`: 동일한 atomic write 패턴 적용.

### 백엔드 — api.py
- 임시 `debug_rf_status()` 함수 추가 후 진단 완료 → 삭제. 클린 빌드 수행.
