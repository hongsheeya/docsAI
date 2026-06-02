# 영속 모델 저장 경로 고정

- **ID**: 003
- **날짜**: 2026-05-04
- **유형**: 버그 수정

## 작업 요약
모델 저장 경로가 `_appdata/storage`를 따라가며 Pod/컨테이너 재생성 시 유실되던 구조를 수정했다. RF, XG-Fall, XG-Posture, RF-Pose 모델과 각 `training_summary.json`의 기준 경로를 `/opt/app/storage/training/fall-detection/` 아래 영속 경로로 승격했다.

기존 `_appdata` 위치에 모델이 남아 있으면 첫 접근 시 `/opt/app/storage/...`로 자동 복사되도록 로딩 경로도 보강했다. 비상 복구 스크립트와 직접 학습 스크립트도 같은 영속 경로를 사용하도록 맞췄다.

## 원문 요청사항
```text
아니 모델을 왜 거기다가 저장을 해서 날리는건데. /opt/app 에 저장을 해야 안날라간다고. 하... 또 모델 새로 만들어야하잔항. 그동안의 devlog 다 찾아서 학습해. 데이터는 확보해놨어
```

## 변경 파일 목록
- 백엔드
  - `src/model/struct/video_analysis.py`: 모델/요약 경로를 `/opt/app/storage/training/fall-detection/` 기준으로 승격하고, 기존 `_appdata` 자산 자동 복사 로직 추가
- 스크립트
  - `scripts/emergency_restore_models.py`: 비상 복구 모델 생성 경로를 `/opt/app/storage/...`로 변경하고 RF/XG-Fall/XG-Posture를 같은 영속 위치에 복구하도록 보강
  - `scripts/direct_train.py`: 재학습 출력 경로를 `/opt/app/storage/...` 기준으로 변경하고 intake는 legacy/data 위치를 우선 탐색하도록 수정
- Devlog
  - `devlog.md`: 작업 요약 행 추가
  - `devlog/2026-05-04/003-persistent-model-storage-path-fix.md`: 상세 기록 추가