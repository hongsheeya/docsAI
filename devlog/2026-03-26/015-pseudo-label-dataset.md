# Pseudo-label 데이터셋 생성 (YOLO Person Detect 형식)

- **ID**: 015
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
FN-0012에서 추출된 person-bbox JSON을 YOLO detection 학습용 데이터셋으로 변환하는 스크립트를 작성했다. 2fps 스파스 + Y 영상 midpoint 밀집(10fps) 샘플링, conf >= 0.4 필터링을 적용하여 270개 이미지와 282개 bbox 라벨을 생성했다.

## 변경 파일 목록

### 신규 생성
- `scripts/build_person_dataset.py`: bbox JSON → YOLO detect 데이터셋 변환 스크립트
  - 영상 단위 train/val 분할 (Y/N 비율 유지)
  - 4K 영상에서 프레임 추출 → JPG 85% 품질 저장
  - YOLO txt 라벨: `0 cx cy w h` (normalized)
  - dataset.yaml + dataset_manifest.json 생성

### 수정
- `scripts/extract_person_bbox.py`: 영상 이름 충돌 수정 (Y/N 라벨 접두사 추가)

### 생성된 데이터
- `storage/training/fall-detection/person-detect/dataset/`: 270 이미지, 282 bbox
  - images/train/ (156장), images/val/ (114장)
  - labels/train/, labels/val/ (대응 txt)
  - dataset.yaml, dataset_manifest.json
