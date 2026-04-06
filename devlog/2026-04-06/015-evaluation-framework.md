# 전체 시스템 성능 평가 프레임워크 구축

- **ID**: 015
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
RF-Pose 삭제 후 성능 공백 검증을 위한 종합 평가 프레임워크를 구축하였다.
XG-Fall/XG-Posture 개별 평가, 시스템 수준 평가, baseline 비교 리포트 생성을 자동화한다.

## 변경 파일 목록

### 백엔드
- `src/model/struct/video_analysis.py` (6690 lines)
  - `evaluate_system(eval_type)`: 전체/개별 모델 평가 실행 (full/xg-fall/xg-posture/system)
  - `_evaluate_xg_fall()`: intake Y/N 영상으로 특징 추출 → XG-Fall 예측 → recall/precision/F1/FN count/confusion matrix 산출
  - `_evaluate_xg_posture()`: intake 6-class 영상으로 특징 추출 → macro F1, class-wise recall, confusion rates (sit↔fall, lie↔fall, walk↔run) 산출
  - `_evaluate_system_level()`: 모델 가용성, intake 데이터 상태, readiness 지표, coverage 정보 집계
  - `generate_baseline_report()`: evaluate_system(full) + shadow comparison + deletion readiness를 종합한 baseline 리포트 생성 및 JSON 저장

### API
- `src/app/page.dashboard/api.py`
  - `evaluate_system()`: eval_type 파라미터로 평가 유형 지정 가능
  - `baseline_report()`: baseline 비교 리포트 생성

### 평가 지표 커버리지
- **XG-Fall**: fall recall, fall precision, fall F1, FN count, FP count, confusion matrix
- **XG-Posture**: macro F1, class-wise recall, sit↔fall/lie↔fall/walk↔run confusion rates, confusion matrix
- **System**: 모델 가용성, intake 데이터 충분성, feature/class coverage, suppressor count
- **Baseline**: 전체 평가 + shadow comparison + deletion readiness 통합

### 저장 위치
- 평가 리포트: `data/storage/training/fall-detection/evaluation/eval_{type}_{timestamp}.json`
- Baseline 리포트: `data/storage/training/fall-detection/evaluation/baseline_{timestamp}.json`
