# Pseudo-label 품질 검수(QC) 도구

- **ID**: 016
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
pseudo-label 데이터셋의 품질을 자동 검증하고 시각 리뷰를 생성하는 스크립트를 작성했다. tiny bbox 필터링, confidence 분포 분석, fall 프레임 bbox overlay 시각화를 수행한다.

## 변경 파일 목록

### 신규 생성
- `scripts/review_person_labels.py`: 품질 검수 스크립트
  - 자동 QC: tiny bbox(< 1% 면적) 10건 필터링, OOB 0건
  - 영상별 confidence 분포 통계 (min/median/max)
  - fall(Y) 영상 167 프레임 bbox overlay 리뷰 이미지 생성
  - val set low-confidence 프레임 리포트

### 생성된 데이터
- `storage/training/fall-detection/person-detect/review/review_report.json`
- `storage/training/fall-detection/person-detect/review/fall_frames/`: 167개 리뷰 이미지

## QC 결과 요약
- 총 bbox: 282 → 필터 후 272 (96.5% 유지)
- val low-conf (< 0.6): 24개 bbox (수동 확인 대상)
