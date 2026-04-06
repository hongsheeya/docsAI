# 업로드 분석 모델 라우팅 복구 및 오탐 방지 게이트 적용

- **ID**: 008
- **날짜**: 2026-03-27
- **유형**: 버그 수정

## 작업 요약
업로드 분석이 실제 배포 대상인 person-feature XGBoost 경로를 사용하지 않고, 구형 RF 파이프라인(`/opt/app/rf_model_server.pkl`)만 강제로 타고 있던 문제를 수정했다. 동시에 런타임 스크립트의 `sklearn` 로딩 실패를 해결하고, 명백한 비낙상 장면을 낙상으로 과대판정하던 오탐을 줄이기 위한 motion gate를 추가했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - `model_type` 값을 실제로 반영하도록 수정
  - `auto` 기본값을 person-feature → YOLO legacy → RF 순으로 우선 선택하도록 복구
  - 업로드 분석에서 `_infer_with_trained_model()` 경로를 사용하도록 변경
  - 모델 옵션 기본값을 `auto`로 변경
- `scripts/yolo_fall_runtime.py`
  - `/opt/app/my_libs`를 `sys.path`에 추가해 `best_model.pkl` 언피클 시 `sklearn` 로딩 가능하도록 수정
  - peak window의 `max_down_speed`, `center_dy`, `pose_change`를 이용한 motion gate 추가
- `src/app/page.dashboard/view.ts`
  - 프론트 기본 선택 모델을 `rf-pipeline`에서 `auto`로 변경

## 검증 결과
- WIZ normal build 성공
- `00023_H_A_N_C1.mp4`(비낙상): `fall_score 0.2164`, `fall_detected false`
- `00025_H_A_FY_C3.mp4`(낙상): `fall_score 0.6176`, `fall_detected true`
- 기존 RF 경로의 고정형 0.54~0.56 점수 증상 대신 실제 학습 모델 경로가 동작함을 확인
