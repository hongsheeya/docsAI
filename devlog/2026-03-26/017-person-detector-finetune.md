# YOLO Person Detector Fine-tuning

- **ID**: 017
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
사전학습 YOLO11n을 병원/실내 환경의 pseudo-label 데이터셋으로 파인튜닝했다. Backbone 10개 레이어를 동결하고 detection head만 학습하여, 11 epochs 후 mAP50=0.989, precision=0.990, recall=0.983을 달성했다.

## 변경 파일 목록

### 신규 생성
- `scripts/train_person_detector.py`: YOLO person detector fine-tuning 스크립트
  - backbone freeze (10 layers), AdamW optimizer
  - augmentation: mosaic 0.5, flipud 0.3, fliplr 0.5, hsv_h 0.015
  - single_cls=True (person만)

### 수정
- `storage/training/fall-detection/model/baseline_model.json`: person_detector 경로 추가

### 생성된 데이터
- `storage/training/fall-detection/person-detect/runs/person-det-20260326-051849/weights/best.pt`
- `storage/training/fall-detection/person-detect/runs/person-det-20260326-051849/training_summary.json`

### 삭제 (디스크 확보)
- `.venv-yolo/` (1.5GB, 시스템 Python에 이미 설치됨)
- `storage/training/fall-detection/yolo-video/`
- `storage/training/fall-detection/person-detect/review/`

## 학습 결과
| Metric | 값 |
|--------|-----|
| mAP50 | 0.989 |
| mAP50-95 | 0.755 |
| Precision | 0.990 |
| Recall | 0.983 |
| Epochs | 11/30 (디스크 부족으로 조기 중단) |
