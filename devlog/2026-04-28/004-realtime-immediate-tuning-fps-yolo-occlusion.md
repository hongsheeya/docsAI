# 실시간 즉시 적용 튜닝 (FPS·YOLO·Occlusion·Guard)

- **ID**: 004
- **날짜**: 2026-04-28
- **유형**: 성능 최적화

## 작업 요약
발표 직전 바로 체감 가능한 개선만 우선 반영했다. 브라우저 포즈 오버레이 FPS를 상향하고, RF-Dual 실시간 청크 간격을 줄였으며, 실시간 YOLO 추론 해상도를 낮춰 처리량을 높였다. 또한 keypoint visibility 기반 occlusion 감쇠와 guard 미세조정을 추가해 가림/애매한 장면의 오탐을 더 보수적으로 억제했다.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - MediaPipe 오버레이 스로틀: `83ms (~12fps)` → `66ms (~15fps)`
  - RF-Dual 실시간 청크 spawn 간격: `1500ms` → `1200ms`
  - 포즈 루프 시작 시 `mpLastFrameTime` 초기화 추가
  - 문서 비가시 상태에서는 canvas draw를 스킵해 불필요한 브라우저 부하 감소

### 백엔드
- `src/model/struct/video_analysis.py`
  - realtime 전용 YOLO 파라미터 분리
    - `_RF_REALTIME_CONF_THRES = 0.18`
    - `_RF_REALTIME_YOLO_IMGSZ = 416`
  - `_extract_rf_pipeline_features()`에서 realtime 경로에 위 파라미터 사용
  - `_infer_rf_dual()`에 posture window 기반 visibility 지표 집계 추가
    - `avg_conf`
    - `lower_body_visibility`
  - occlusion-like 상태에서 marginal fall score를 낮추는 `occlusion_confidence_damp` 추가
  - realtime motion guard 및 moderate-motion dampener 임계값 소폭 강화
  - runtime inference에 occlusion 디버그 정보 노출

## 기대 효과
- 브라우저 오버레이 반응성 소폭 개선
- 실시간 결과 갱신 주기 개선
- YOLO 실시간 처리량 증가
- 가림/부분 관측 장면에서 오탐 감소 기대
- 학습 없이 바로 적용 가능한 안정화 효과 확보

## 검증
- `wiz project build --project=main` 정상 완료
