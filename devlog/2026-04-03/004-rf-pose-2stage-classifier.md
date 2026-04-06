# RF-Pose 2단계 분류 구조 설계 및 구현

- **ID**: 004
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
bbox 13개 통계 특징 + keypoint 12개 포즈 특징 = 총 25개 특징을 사용하는 RF-Pose 파이프라인을 구현했다. 기존 RF 파이프라인과 병행 운영 가능하며, 모델 선택 UI에서 `rf-pose` 옵션으로 선택할 수 있다. HITL 재학습 시 RF-Pose 모델도 함께 학습된다.

## 변경 파일 목록

### Backend (video_analysis.py)
- `_rf_pose_model_path()`, `_rf_pose_summary()`, `_rf_pose_pipeline_available()`: RF-Pose 모델 경로/상태 헬퍼 메서드 추가
- `_get_rf_pose_model()`: mtime 기반 캐시 RF-Pose 모델 로더 추가
- `_get_feat_labels()`: bbox + pose 특징 라벨 딕셔너리를 별도 메서드로 추출
- `_infer_rf_pose_pipeline()`: 25개 특징 기반 RF-Pose 추론 파이프라인 (Motion Guard, Short-clip 적응형 threshold 포함)
- `retrain_rf_pose_pipeline()`: HITL intake 데이터로 RF-Pose 모델 재학습 (3-Fold CV 포함)
- `_infer_with_trained_model()`: rf-pose 라우팅 추가, auto fallback 순서를 rf-pose→rf-pipeline→person-feature로 변경
- `retrain_baseline()`: RF-Pose 재학습 단계 추가
- `_model_options()`: rf-pose 옵션 추가
- `_trained_model_info()`: rf-pose 런타임 우선순위 지원
- `_analysis_engine_summary()`: rf-pose-runtime 런타임 라벨 추가
- `_risk_score_guide()`: rf-pose-runtime 전용 가이드 추가
- 분석 결과 빌드: rf-pose-runtime speed note, overview, label 추가

### 경로 상수
- `_RF_POSE_MODEL_REL_PATH`: `storage/training/fall-detection/rf-pose/rf_pose_model.pkl`
- `_RF_POSE_SUMMARY_REL_PATH`: `storage/training/fall-detection/rf-pose/training_summary.json`
