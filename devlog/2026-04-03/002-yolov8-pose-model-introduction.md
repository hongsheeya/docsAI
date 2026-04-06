# YOLOv8-Pose 모델 도입 — bbox + 관절 keypoints 동시 탐지

- **ID**: 002
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
YOLOv8n(detect only)에서 YOLOv8n-Pose로 모델을 교체하여 bbox와 17개 COCO keypoints를 동시 추출. detection_frames에 keypoints 필드 추가. 프론트엔드 bbox 오버레이에 스켈레톤 시각화(관절 점 + 연결선) 렌더링 구현.

## 변경 파일 목록

### video_analysis.py
- `_RF_YOLO_MODEL`: `yolov8n.pt` → `yolov8n-pose.pt`
- COCO keypoint 상수/스켈레톤 연결쌍 정의 (`_COCO_KEYPOINTS`, `_COCO_SKELETON`)
- `_extract_rf_pipeline_features()`: pose 결과에서 keypoints 추출, `all_frame_keypoints` 반환 추가
- `detection_frames`에 각 detection별 `keypoints` 필드(17×3: x,y,conf) 추가 (원본 해상도 좌표)
- 모든 런타임 라벨 문자열에서 `YOLOv8n` → `YOLOv8n-Pose` 반영

### view.ts
- `drawBboxesOnCanvas()`: COCO 스켈레톤 연결선(노란색) + 관절 점(머리=분홍, 팔=시안, 다리=초록) 렌더링
- `drawDetectionFrame()`: detection replay에도 동일한 스켈레톤 시각화 적용

### yolov8n-pose.pt (신규)
- Ultralytics에서 자동 다운로드된 YOLOv8n-Pose 모델 파일 (6.8MB)
