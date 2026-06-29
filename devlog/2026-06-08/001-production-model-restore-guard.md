# 운영 모델 파일 유실 복구 및 재부팅 자동 복원 가드

- **ID**: 001
- **날짜**: 2026-06-08
- **유형**: 장애 복구

## 작업 요약
서버 재부팅 후 운영 모델이 없다고 표시되는 문제를 조사했다. 프로젝트 루트의 `yolov8n-pose.pt`, `yolo11n-pose.pt`, `yolo26n-pose.pt`가 `/opt/app/models/pose/...`를 가리키는 심볼릭 링크였고, 재부팅 후 해당 대상 디렉터리가 없어져 링크가 끊어진 상태였다.

또한 `/opt/app/storage/training/fall-detection/` 아래 운영 모델 아티팩트가 비어 있어 RF, RF-Pose, XG-Fall, XG-Posture 모델을 비상 복구 스크립트로 재생성했다.

재발 방지를 위해 복구된 모델을 `/mnt/data/wiz/model-backup/` 아래에 백업하고, `run.sh` 시작 루틴에 자동 복원 가드를 추가했다. 시작 시 `/opt/app/storage`에 운영 모델이 있으면 백업을 갱신하고, 없으면 백업에서 복원한다. YOLO pose 파일도 백업에서 `/opt/app/models/pose/`와 프로젝트 루트로 복원한다.

## 복구된 주요 파일
- `/opt/app/storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl`
- `/opt/app/storage/training/fall-detection/rf-pose/rf_pose_model.pkl`
- `/opt/app/storage/training/fall-detection/xg-fall/xg_fall_model.pkl`
- `/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl`
- `/mnt/data/wiz/project/main/yolov8n-pose.pt`
- `/mnt/data/wiz/model-backup/`

## 검증
- `bash -n /opt/app/run.sh` 통과
- `joblib.load`로 RF, RF-Pose, XG-Fall, XG-Posture 모델 로드 확인
- YOLO pose 파일이 프로젝트, 앱 모델 경로, 백업 경로에 실제 6.8MB 파일로 존재함을 확인
