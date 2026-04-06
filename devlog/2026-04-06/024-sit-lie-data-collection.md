# sit/lie 학습 데이터 수집 및 XG-Posture 6클래스 재학습

- **ID**: 024
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
041 낙상사고 데이터셋에서 sit(앉기) 30클립, lie(누워있기) 40클립을 추출하여 XG-Posture 모델을 6클래스(stand/walk/run/sit/lie/fall) 체계로 재학습 완료.

## 변경 파일 목록

### 스크립트
- `scripts/curate_sit_lie.py` (신규): YOLO bbox aspect ratio 휴리스틱으로 041 N(비낙상) 영상에서 sit 후보 탐색
- `scripts/extract_sit_lie_041.py` (신규): lie — 낙상 영상 마지막 4초 추출 (낙상 후 누워있는 장면), sit — N 영상 중 bbox AR이 낮은 것 복사

### 학습 데이터
- `_appdata/storage/training/fall-detection/intake/sit/`: 30 clips (041 N 영상 중 앉아있는 자세)
- `_appdata/storage/training/fall-detection/intake/lie/`: 39 clips (041 낙상 영상 마지막 4초, 바닥에 누운 상태)

### 모델
- `_appdata/storage/training/fall-detection/xg-posture/xg_posture_model.pkl`: 6클래스 모델
- `_appdata/storage/training/fall-detection/xg-posture/xg_posture_summary.json`: 학습 요약

## 주요 발견사항
1. **FPS 불일치 문제**: 041 영상은 ~60fps (scene_length=600프레임 / 10초 = 60fps)이나 라벨의 fall_end_frame을 30fps로 나누면 영상 길이를 초과. 해결: 영상 마지막 4초를 직접 추출하는 방식으로 전환.
2. **XG-Posture 결과**: 210 샘플, CV accuracy=76.67%, CV F1 macro=69.93%. 6클래스 전체 train recall 96.67~100%.
3. **주요 feature importance**: pose_tilt_mean (0.195), pose_descent_max (0.138), pose_change_mean (0.096)
