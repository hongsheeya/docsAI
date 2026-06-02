# 모델 복구 및 _desc_dur UnboundLocalError 수정

- **ID**: 001
- **날짜**: 2026-04-14
- **유형**: 버그 수정

## 작업 요약
모든 모델이 "33% 정상"만 반환하는 치명적 버그 원인을 진단하고 수정했다.
1. 모델 .pkl 파일이 비영속 컨테이너 스토리지에서 소실된 것을 확인
2. 부트스트랩 학습으로 4개 모델(RF, RF-fallback, XG-Fall, XG-Posture) 재생성
3. `_infer_xg_dual()` 내 `_desc_dur` 변수가 사용 후 할당되는 UnboundLocalError 수정

## 근본 원인
- **모델 소실**: `_appdata/storage/`가 비영속 컨테이너 오버레이에 위치하여 Pod 재생성 시 모델 파일 소실
- **런타임 오류**: `_infer_xg_dual()` line 5597에서 `_desc_dur` 변수를 `static_floor_like_suppressor` 조건에서 사용하나, 실제 할당(`pf.get('descent_duration', 0.0)`)은 line 5616의 `controlled_lie_suppressor` 직전에 위치. Python 3의 스코프 규칙에 의해 `UnboundLocalError` 발생 → xg-dual 추론 실패 → heuristic-fallback(0.33) 반환

## 변경 파일 목록

### 버그 수정
- `src/model/struct/video_analysis.py`
  - `_desc_dur`와 `_post_still` 할당을 line 5596 (static_floor_like_suppressor 직전)으로 이동
  - 기존 line 5616-5617의 중복 할당은 유지 (무해)

### 모델 재생성 (스크립트)
- `scripts/bootstrap_models.py`: 단일 영상에서 ffmpeg 증강으로 intake 데이터 생성
- `scripts/direct_train.py`: YOLO 특징 추출 + RF/XG-Fall/XG-Posture 직접 학습

### 생성된 모델
- `_appdata/storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl` (190KB, 13 features)
- `/opt/app/rf_model_server.pkl` (190KB, RF fallback)
- `_appdata/storage/training/fall-detection/xg-fall/xg_fall_model.pkl` (152KB)
- `_appdata/storage/training/fall-detection/xg-posture/xg_posture_model.pkl` (419KB, 3 classes: stand/walk/fall)

## 검증 결과
- `analyze_upload` API: `runtime_key: xg-dual`, `risk_score: 0.1837`, `behavior_inference.fallback: False`
- heuristic-fallback(0.33) 대신 학습 모델 정상 추론 확인
