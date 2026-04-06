# MediaPipe 포즈 감지 성능 최적화 (화면 렉 개선)

- **ID**: 013
- **날짜**: 2026-04-03
- **유형**: 성능 개선

## 작업 요약
웹캠 모드에서 화면 렉의 주요 원인이 MediaPipe Heavy 모델의 매 프레임 실행(~60fps)과 매 프레임 캔버스 버퍼 재할당임을 확인. 3가지 최적화를 적용하여 GPU/CPU 부하를 대폭 감소시킴.

## 변경 파일 목록

### 프론트엔드 — view.ts (page.dashboard)
1. **Heavy → Lite 모델 전환**: `pose_landmarker_heavy` → `pose_landmarker_lite`. 추론 시간 3~5배 단축, 실시간 오버레이 용도로 충분한 정확도.
2. **프레임 스로틀 12fps**: `requestAnimationFrame` 루프에 `MP_FRAME_INTERVAL_MS`(~83ms) 간격 체크 추가. 60fps → 12fps로 GPU 추론 횟수 5배 감소.
3. **캔버스 리사이즈 분리**: `drawMpPose()`에서 매 프레임 `canvas.width/height` 재설정 제거. `ResizeObserver`로 크기 변경 시에만 버퍼 재할당.
4. **리소스 정리**: `stopPoseLoop()`에서 `ResizeObserver.disconnect()` 추가.
