# Motion Guard 추가 — 정지 상태 오탐 수정 및 분석 시간 UI 표시

- **ID**: 006
- **날짜**: 2026-03-30
- **유형**: 버그 수정

## 작업 요약
RF, Trained-YOLO 모델이 정지 상태 사람을 낙상으로 오판(fall_prob=57.5%)하는 문제를 motion guard 후처리 로직으로 해결. 또한 분석 소요 시간을 UI에 표시하고, 실시간 모드에서 model_type을 명시적으로 전달하도록 수정.

## 원인 분석
- RF 모델의 feature importance 중 `aspect_ratio_std`(22.0%), `aspect_ratio_mean`(21.3%)이 전체의 44%를 차지
- 정지 상태 사람(서 있거나 앉아 있음)의 `aspect_ratio_mean ≈ 0.36~0.5`가 학습 데이터의 낙상 패턴과 유사하게 인식됨
- delta 피처(움직임 관련)가 전체 importance의 12%에 불과하여 정적/동적 구분이 약함

## 변경 파일 목록

### 백엔드 (video_analysis.py)
- `src/model/struct/video_analysis.py`
  - `_infer_rf_pipeline()`: Step 5-1에 feature 기반 motion guard 추가 (7개 조건: delta_y_mean<5, delta_y_max<12, delta_height_mean<5, delta_width_mean<3, delta_area_mean<150, center_y_std<10, height_std<8)
  - `_check_video_stationary()`: 신규 헬퍼 메서드 — 프레임 간 차분으로 영상 움직임 확인 (4프레임 샘플링, 160x90 다운스케일)
  - `_infer_yolo_cls()`: frame-differencing 기반 motion guard 추가 (threshold=1.5, 실제 낙상 비디오 0% 오차단율)
  - 결과에 `motion_guard` 정보(applied, is_stationary, checks) 포함
  - summary 메시지에 motion guard 적용 시 별도 안내 표시

### 프론트엔드
- `src/app/page.dashboard/view.pug`
  - 낙상 감지 여부 칸에 "분석 소요: X초" 표시 추가
  - 낙상 감지 시 텍스트 빨간색(`text-red-600`)으로 강조
- `src/app/page.dashboard/view.ts`
  - `getElapsedSec()` 메서드 추가 — runtime_inference.elapsed_sec 또는 perf.total에서 소요 시간 추출
  - `handleRealtimeChunk()`에 `model_type: this.selectedModelType` 추가 — 실시간 모드에서 모델 선택 명시적 전달

## 테스트 결과
- 정지 상태 사람: Raw fall_prob=0.54 → motion guard 후 0.15 (낙상 아님)
- 실제 낙상 특징: Raw fall_prob=0.525 → motion guard 미적용 (정상 낙상 감지)
- Person-feature(XGBoost): 기존 motion_gate로 score ≤ 0.35 제한 (수정 불필요)
