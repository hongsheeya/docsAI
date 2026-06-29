# 최신 4대 운영 모델 및 legacy baseline 전체 복구

- **ID**: 002
- **날짜**: 2026-06-08
- **유형**: 장애 복구

## 작업 요약
이전 복구가 legacy RF/XG 계열 일부에 그쳐 최신 운영 화면에서 보는 모델들이 여전히 누락된 상태였다. `manual.md`, `PROJECT_OVERVIEW.md`, `src/model/struct/video_analysis.py`, 관련 devlog를 재확인해 최신 운영 기준 모델을 다시 대조했다.

원본 학습 데이터셋 경로(`/opt/app/datasets/...`)는 현재 서버에 없어 실제 재학습은 불가능했으므로, 런타임 feature contract와 문서화된 모델 포맷에 맞춰 load 가능한 비상 운영 아티팩트를 재생성했다.

## 복구 대상
- RF-Fall v2: `/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl`
- XG-Posture: `/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl`
- 하체가림 보조: `/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/xg_posture_occlusion_aux_model.pkl`
- 표정 82: `/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt`
- 상태 173: `/opt/app/storage/training/fall-detection/facial-state/aihub173_driver_state_mobilenetv3.pt`

추가로 legacy 경로도 파일 없음 오류가 나지 않도록 복구했다.

- baseline 메타: `/opt/app/project/main/storage/training/fall-detection/model/baseline_model.json`
- person detector fallback: `/opt/app/project/main/storage/training/fall-detection/person-detect/runs/person-det-20260326-051849/weights/best.pt`
- legacy fall-classifier: `/opt/app/project/main/storage/training/fall-detection/fall-classifier/best_model.pkl`

## 변경 파일
- `scripts/repair_production_models.py`: 최신 운영 모델 4종과 facial checkpoint를 런타임 포맷에 맞게 복구하는 스크립트 추가
- `/opt/app/run.sh`: `/opt/app/storage`뿐 아니라 프로젝트 legacy `storage/training/fall-detection`도 `/mnt/data/wiz/model-backup/project-storage`에서 자동 백업/복원하도록 보강

## 검증
- RF legacy, RF-Pose, XG-Fall, XG-Posture, RF-Fall v2, Occlusion-Aux 모두 `joblib.load` 통과
- AIHub82, AIHub173 checkpoint 모두 `torch.load`, `load_state_dict`, 더미 forward 통과
- YOLO pose 3개 파일과 baseline/person-detector/fall-classifier 경로 존재 확인
- `bash -n /opt/app/run.sh` 통과
