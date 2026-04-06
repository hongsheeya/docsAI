# 실시간 분석 성능 최적화

- **ID**: 003
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
실시간 웹캠 분석의 성능을 모니터링하고 최적화하는 4가지 개선사항 구현:
(1) 클라이언트 체크 round-trip 프로파일링, (2) 적응형 분석 간격, (3) 서버 모델 워밍업 엔드포인트, (4) 서버 실시간 프레임 샘플링 최적화.

## 변경 파일 목록

### 프론트엔드 (view.ts)
- `src/app/page.dashboard/view.ts`: 성능 프로파일링 변수 추가 (realtimePerfStats, realtimeRoundTripHistory, realtimeServerTimeHistory, realtimeAdaptiveEnabled 등). dispatchRealtimeChunk()에 round-trip 타이밍 측정 및 적응형 간격 로직 추가. startRealtimeAnalysis()에 모델 워밍업 호출 및 perf stats 초기화. stopRealtimeAnalysis()에 perf stats 리셋.

### 프론트엔드 (view.pug)
- `src/app/page.dashboard/view.pug`: 실시간 성능 모니터링 패널 추가 — 평균 RTT, 서버 처리 시간, 현재 간격, 폐기 건수, 적응형 간격 토글.

### API (api.py)
- `src/app/page.dashboard/api.py`: `warmup_models()` 함수 추가 — 실시간 세션 시작 전 YOLO + RF 모델 사전 로드.

### 서버 (video_analysis.py)
- `src/model/struct/video_analysis.py`: `warmup_models()` 메서드 추가 — YOLO, RF-Pipeline, RF-Pose 모델을 메모리에 선제 로드. 실시간 프레임 샘플링 최적화 (target_fps 4→3, max_frames 12캡, YOLO imgsz 640→480).
