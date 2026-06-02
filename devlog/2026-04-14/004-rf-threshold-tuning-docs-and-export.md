# RF threshold 0.35 미세조정·업로드 재평가·문서 및 배포 패키지 정리

- **ID**: 004
- **날짜**: 2026-04-14
- **유형**: 평가 / 문서 업데이트 / 배포 산출물 생성

## 작업 요약
Validation 재학습 RF 모델을 기준으로 threshold sweep을 수행해 운영 임계값을 `0.37`에서 `0.35`로 미세조정했다.
기존 업로드 영상을 전수 재평가해 FP/FN 목록을 자동 추출했고, 결과를 반영해 파이프라인 문서·프로젝트 개요·README를 최신 상태로 갱신한 뒤 독립 배포용 모델 ZIP 패키지를 생성했다.

## 평가 및 조정 결과
- Validation 기준 기존 threshold `0.37`
  - Accuracy: `0.8950`
  - Precision: `0.8496`
  - Recall: `0.9600`
  - F1: `0.9014`
  - TP/FN/FP/TN = `96 / 4 / 17 / 83`
- 미세조정 threshold `0.35`
  - Accuracy: `0.9000`
  - Precision: `0.8448`
  - Recall: `0.9800`
  - F1: `0.9074`
  - TP/FN/FP/TN = `98 / 2 / 18 / 82`
- 기존 업로드 영상 재평가 결과
  - 총 재평가 레코드: `36`
  - 고유 원본 영상: `4`
  - False Positive: `0`
  - False Negative: `0`

## 변경 파일 목록

### 평가 스크립트/산출물
- `scripts/evaluate_rf_validation_and_uploads.py`
  - Validation threshold sweep 및 FP/FN 자동 추출 스크립트 추가
- `scripts/reevaluate_existing_uploads.py`
  - 기존 업로드 영상 재평가 스크립트 추가
- `storage/training/fall-detection/evaluation/rf_validation_eval_20260414.json`
  - Validation 재평가 결과 저장
- `storage/training/fall-detection/evaluation/existing_uploads_reeval_20260414.json`
  - 업로드 재평가 결과 저장

### 운영 설정 반영
- `storage/training/fall-detection/rf-pipeline/training_summary.json`
  - 운영 threshold를 `0.35`로 갱신
  - `threshold_tuning`, `tuned_thresholds`, 이전 결과 메타데이터 추가
- `_appdata/storage/training/fall-detection/rf-pipeline/training_summary.json`
  - 런타임 mirror summary 동일 반영

### 문서/UI 갱신
- `README.md`
  - 현재 운영 모델 상태와 최신 지표 반영
- `docs/prototype/fall-detection/README.md`
  - 2026-04-14 운영 상태 요약 추가
- `PROJECT_OVERVIEW.md`
  - RF/XG-Posture 최신 메트릭, 모델 위치, 로드맵, 이슈 현황 반영
- `src/app/page.pipeline/view.pug`
  - RF 16-feature 파이프라인, threshold 35%, 최신 성능 지표 반영

### 모델 배포 패키지
- `storage/training/fall-detection/export/rf-dual-validation-20260414/`
  - RF fall 모델, XG-Posture 모델, summary, 평가 JSON, manifest 정리
- `storage/training/fall-detection/export/rf-dual-validation-20260414.zip`
  - 독립 배포용 ZIP 패키지 생성

## 산출물
- 모델 패키지: `storage/training/fall-detection/export/rf-dual-validation-20260414.zip`
- SHA256: `b893f10c4bc9c5218f4433edf9a34fea46fd58c73fdf07d74a7b57048891f10d`

## 검증 메모
- `prototype_info` 기준 운영 threshold가 `0.35`로 노출됨을 확인
- 업로드 대표 샘플 `00005_H_A_N_C4.mp4`, `00110_H_A_N_C1.mp4`, `00582_H_D_N_C8.mp4`, `02311_H_A_FY_C5.mp4`가 모두 기대 라벨과 일치
