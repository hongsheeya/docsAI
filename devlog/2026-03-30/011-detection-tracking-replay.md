# 분석 과정 시각화 (사람 검출 트래킹 리플레이)

- **ID**: 011
- **날짜**: 2026-03-30
- **유형**: 기능 추가

## 작업 요약
RF 파이프라인 분석 결과에서 프레임별 YOLO 사람 검출 bbox 데이터를 수집하여 detection_frames 배열로 응답에 포함. 프론트엔드에 Canvas 기반 트래킹 리플레이 패널 추가 — 재생/정지, 시크 슬라이더, 프레임별 바운딩 박스 시각화 기능 구현.

## 변경 파일 목록

### 백엔드
- `src/model/struct/video_analysis.py`
  - _infer_rf_pipeline: batch_results에서 person bbox를 detection_frames 배열로 수집
  - model_runtime 응답에 detection_frames 필드 추가 (frame_idx, time_sec, detections[{x1,y1,x2,y2,conf}])

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - ViewChild detCanvas 참조 추가
  - detectionReplayIndex, detectionReplayPlaying, detectionReplayTimer 상태 변수
  - getDetectionFrames(), toggleDetectionReplay(), startDetectionReplay(), stopDetectionReplay(), seekDetectionReplay(), drawDetectionFrame() 메서드 구현
  - ngOnDestroy에 stopDetectionReplay 추가
- `src/app/page.dashboard/view.pug`
  - 분석 진단 메모 하단에 사람 검출 트래킹 리플레이 패널 추가
  - Canvas 기반 bbox 오버레이, 재생/정지 버튼, 시크 슬라이더, 프레임 카운터
