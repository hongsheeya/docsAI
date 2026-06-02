# Validation 1100영상 기반 RF 재학습 및 16-feature 런타임 호환 복구

- **ID**: 003
- **날짜**: 2026-04-14
- **유형**: 모델 재학습 / 런타임 호환 수정

## 작업 요약
Validation 공개데이터셋을 실제 경로에서 직접 읽어 RF 낙상 모델을 재학습했다.
학습 후 새 모델이 16-feature 포맷(`n_frames`, `width_mean`, `area_mean`, `delta_area_mean` 포함)으로 저장되어 기존 런타임이 이를 pose-확장 모델로 오인하던 문제를 수정했다.

## 학습 데이터
- 원천 경로: `041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/영상`
- 사용 가능 영상 수: Fall 1704, NonFall 568
- 실제 학습 분할: Train Y/N = 450/449, Val Y/N = 100/100
- 총 특징 추출 성공: 1099건 (오류 1건)

## 학습 결과
- 최종 하이퍼파라미터: `n_estimators=300`, `max_depth=None`, `min_samples_leaf=1`, `class_weight=1:3`
- 최종 threshold: `0.37`
- Validation 성능:
  - Accuracy: `0.8950`
  - Precision: `0.8496`
  - Recall: `0.9600`
  - F1: `0.9014`
  - TP/FN/FP/TN = `96 / 4 / 17 / 83`

## 변경 파일 목록

### 학습 스크립트 보정
- `scripts/retrain_rf_v3.py`
  - Validation 실제 경로(`01.원천데이터/영상`)를 자동 탐지하도록 보정

### 런타임 호환 수정
- `src/model/struct/video_analysis.py`
  - RF summary의 `best_config.threshold`도 읽도록 확장
  - 16-feature RF v3 모델 전용 컬럼셋 `_RF_V3_FEATURE_COLUMNS` 추가
  - `n_features_in_ == 16`인 모델은 pose 모델이 아니라 RF v3 모델로 처리하도록 분기 수정

### 번들 동기화
- `bundle/src/model/struct/video_analysis.py`
  - 동일 수정 반영

## 산출물
- 새 모델: `storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl`
- 백업 모델: `storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl.bak.20260414050917`
- 요약 파일: `storage/training/fall-detection/rf-pipeline/training_summary.json`
- 캐시: `storage/training/fall-detection/rf-pipeline/feature_cache_v3.json`
- 그리드 결과: `storage/training/fall-detection/rf-pipeline/grid_search_v3_20260414_050917.json`

## 스모크 테스트
- NonFall `00005_H_A_N_C4.mp4` → `runtime_key=rf-dual`, `fall_detected=False`, `risk_score=0.0333`
- Fall `02311_H_A_FY_C5.mp4` → `runtime_key=rf-dual`, `fall_detected=True`, `risk_score=0.9867`
- 런타임 warning 없음, threshold 메타데이터 `0.37` 정상 반영 확인