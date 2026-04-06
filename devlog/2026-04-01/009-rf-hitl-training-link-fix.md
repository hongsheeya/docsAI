# RF HITL 학습 반영 경로 복구

- **ID**: 009
- **날짜**: 2026-04-01
- **유형**: 버그 수정 + 기능 보강

## 작업 요약
RF 파이프라인은 HITL 재학습과 실제 추론 경로가 분리되어 있었다. 기존에는 재학습이 `baseline_model`/`best_model.pkl`만 갱신하고, RF 추론은 고정 파일인 `/opt/app/rf_model_server.pkl`만 사용해 피드백 학습 결과가 실제 RF 분석에 반영되지 않았다. 이를 수정해 intake 영상으로 16개 RF 특징을 다시 추출해 프로젝트 로컬 RF 모델을 재학습하고, RF 추론이 해당 모델을 우선 사용하도록 연결했다.

## 변경 파일 목록

### Backend — src/model/struct/video_analysis.py
- RF 활성 모델 경로를 고정 서버 파일 → 프로젝트 로컬 HITL 모델 우선 방식으로 변경
- RF feature 추출 공통 헬퍼 `_extract_rf_pipeline_features()` 추가
- `retrain_rf_pipeline()` 추가: intake Y/N 영상을 기반으로 16-feature RF 모델 재학습
- `retrain_baseline()`에 RF 재학습 단계 통합
- RF runtime meta / trained model info가 프로젝트 로컬 RF HITL 메트릭과 학습 샘플 수를 표시하도록 수정
- RF inference에서 sklearn `Pipeline` 내부 `clf.feature_importances_`도 읽도록 수정
