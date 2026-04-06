# /낙상영상 YOLO Classification 학습

- **ID**: 009
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
/opt/app/낙상영상 (Y: 5개 영상, N: 7개 영상)에서 프레임을 추출하여 YOLO11n-cls 기반 낙상 분류 모델을 학습했다. 손상 파일(00002) 및 라벨 충돌 파일(00074) 제외, 총 10개 영상에서 300프레임(fall 150/normal 150) 균형 데이터셋 구성. 30에폭 학습 결과 val accuracy 35%로 심한 과적합 발생. 영상 수(10개)가 절대적으로 부족하여 일반화 성능이 낮았다.

## 학습 결과
- 데이터셋: 300프레임 (train 240, val 60), fall 150 / normal 150
- Best top1: 53.3% (epoch 16), Final top1: 35%
- Train loss: 0.5855 → 0.0216 (과적합)
- Val loss: 0.822 → 2.780 (발산)
- Best model: yolo-video/runs/video-yolo-20260326-035558/weights/best.pt

## 변경 파일 목록
### 신규 생성
- `scripts/train_video_yolo.py`: 영상 프레임 추출 및 YOLO 학습 스크립트
- `storage/training/fall-detection/yolo-video/dataset/`: 학습 데이터셋 (train/val)
- `storage/training/fall-detection/yolo-video/dataset_manifest.json`: 데이터셋 매니페스트
- `storage/training/fall-detection/yolo-video/runs/video-yolo-20260326-035558/`: 학습 결과

### 자동 갱신
- `storage/training/fall-detection/model/baseline_model.json`: 최신 모델 경로 갱신
- `storage/training/fall-detection/model/training_summary.json`: 학습 결과 요약 갱신
- `storage/training/fall-detection/model/training_status.json`: 학습 완료 상태
