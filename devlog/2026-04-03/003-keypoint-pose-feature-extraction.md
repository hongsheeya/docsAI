# Keypoint 기반 자세 특징 추출 설계 및 구현

- **ID**: 003
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
YOLOv8n-Pose에서 추출한 17개 COCO keypoints로부터 6가지 자세 파생 특징(12개 통계값)을 계산하는 `_extract_pose_features()` 메서드 구현. `_infer_rf_pipeline()`에 통합하여 분석 결과에 pose_features 포함.

## 변경 파일 목록

### video_analysis.py
- `_POSE_FEATURE_COLUMNS`: 12개 자세 특징 열 정의
- `_extract_pose_features()`: 6가지 파생 특징 추출 로직 구현
  - 몸 기울기 각도 (어깨-엉덩이 vs 수직)
  - 키 비율 (머리-발 / 영상높이)
  - 무릎 굽힘 각도 (3점 관절 각도)
  - 수평 확산도 (관절 x좌표 분산)
  - 중심 하강 속도 (프레임 간 y 변화)
  - 자세 변화율 (코사인 비유사도)
- `_infer_rf_pipeline()`: pose feature 추출 호출 + `runtime_inference.pose_features`에 결과 포함
- `_feat_labels`에 12개 pose feature 한글 라벨 추가
