# Sample 데이터 기반 YOLO 학습 파이프라인 구축

- **ID**: 006
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
`/opt/app/Sample` 데이터를 이용해 낙상 이진 분류용 YOLO 학습 파이프라인을 새로 구성했다.
Python 3.12 전용 가상환경을 만들고 CPU 기반 `torch`·`ultralytics`를 설치한 뒤, BBox 크롭 데이터셋 생성과 실시간 학습 상태 기록을 지원하는 학습 스크립트를 추가했다.

## 변경 파일 목록
- `scripts/train_sample_yolo.py`
  - Sample 원천/라벨 데이터를 스캔해 YOLO 분류용 크롭 데이터셋 생성
  - `training_status.json`, `training_status.md`, `training_summary.json`, `baseline_model.json` 실시간/최종 기록
  - `ultralytics` 학습 콜백으로 에폭별 지표 갱신
- `scripts/run_sample_yolo_training.sh`
  - `.venv-yolo` 가상환경을 활성화해 학습 스크립트를 실행하는 래퍼 추가
- `storage/training/fall-detection/yolo-sample/`
  - Sample 기반 학습용 데이터셋/런 디렉터리 생성
- `storage/training/fall-detection/model/`
  - 현재 학습 상태 및 요약 메타데이터 갱신
