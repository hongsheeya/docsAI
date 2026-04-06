# RF-Pose 모델 비활성 유지 결정

- **ID**: 009
- **날짜**: 2026-04-03
- **유형**: 설정 변경

## 작업 요약
RF-Pose(bbox 13 + keypoint 12 = 25 features RandomForest 2단계 분류)는 학습 데이터 부족으로 모델 파일 미생성 상태. 사용자 결정에 따라 코드를 유지하되 비활성 상태로 둠. auto fallback 순서(rf-pose → rf-pipeline → person-feature)에서 rf-pose 모델 미존재 시 자동으로 rf-pipeline으로 대체되므로 운영에 영향 없음.

## 변경 파일 목록
없음 (결정 기록만)
