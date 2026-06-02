# RF-Dual YOLO Single-Pass 통합

- **ID**: 004
- **날짜**: 2026-04-13
- **유형**: 성능 최적화

## 작업 요약
RF-Dual 파이프라인이 YOLO를 2회 실행하던 구조를 1회로 통합하여 추론 속도를 대폭 개선했다.
기존에는 RF 피처 추출용(`_extract_rf_pipeline_features`)과 Posture 타임시리즈용(`_extract_unified_timeseries`)을 각각 호출했으나, 이제 unified timeseries 1회 추출 후 RF 13-feature 통계를 역산(denormalize)하여 단일 패스로 처리한다.

## 변경 파일 목록

### video_analysis.py (`src/model/struct/video_analysis.py`)

#### `_extract_unified_timeseries()` 시그니처 변경
- `target_fps_override`, `max_frames_override` 옵션 파라미터 추가
- RF-Dual이 RF 호환 fps(realtime:3, upload:2)로 호출 가능
- 기존 호출부(xg-dual 등)는 영향 없음 (기본값 None → 기존 동작 유지)

#### `_compute_rf_features_from_timeseries()` 신규 메서드
- unified timeseries (정규화 [0,1] 좌표) → 리사이즈 px 좌표로 역산
- 역산 공식: `center_y_px = cy_norm * resize_height` (resize 로직 동일 적용)
- 동일한 13개 통계 피처 계산 (detection_rate, center_y_mean/std, height_mean/std, aspect_ratio_mean/std, delta_y_mean/max, delta_height_mean, delta_width_mean, delta_y_accel_max, final_height_ratio)
- motion guard 보조값도 포함 (width_mean/std, area_mean/std, delta_area_mean)
- `_from_rolling` 플래그가 있는 롤링 캐시 엔트리 제외

#### `_infer_rf_dual()` 재작성
- **이전**: `_extract_rf_pipeline_features()` (YOLO #1) → `_extract_unified_timeseries()` (YOLO #2)
- **이후**: `_extract_unified_timeseries(target_fps_override=3)` (YOLO 1회) → `_compute_rf_features_from_timeseries()` (CPU 역산)
- YOLO 패스 2회 → 1회로 감소, 영상 디코딩도 1회로 절감
- `_perf` 타이밍에 `single_pass_extract`, `rf_feature_derive` 키 추가
- `runtime_inference.single_pass: True` 마커로 single-pass 모드 식별

### 영향 범위
- RF 단독 모드(`rf`)는 기존 `_extract_rf_pipeline_features()` 그대로 유지 → 변경 없음
- XG-Dual은 `_extract_unified_timeseries()` 기본 파라미터 사용 → 변경 없음
- `_extract_unified_timeseries` 호출부: xg-dual, rf-dual만 사용, 둘 다 정상

## 기대 효과
- **실시간 처리 시간**: YOLO 추론이 전체 시간의 ~70% 차지 → 약 40-50% 시간 절감 예상
- **영상 I/O**: cv2.VideoCapture + 프레임 샘플링이 1회로 줄어 webm 디코딩 비용 절감
- **메모리**: 프레임 이미지 배열이 1세트만 존재
