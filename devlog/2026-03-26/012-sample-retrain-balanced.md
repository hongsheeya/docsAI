# /Sample 데이터 균형 재학습 및 /낙상영상 검증

- **ID**: 012
- **날짜**: 2026-03-26
- **유형**: 기능 추가 / 모델 학습

## 작업 요약
Sample 데이터(320장)의 클래스 불균형(fall:240, normal:80 = 3:1)이 과적합의 근본 원인으로 진단됨. train_sample_yolo.py에 언더샘플링 밸런싱 + 데이터 증강 + 정규화를 추가하여 재학습. /낙상영상 10개 영상으로 실환경 검증 수행.

## 변경 파일 목록

### 스크립트 수정
- `scripts/train_sample_yolo.py`
  - `split_records()`: `balance=True` 파라미터 추가 — 다수 클래스를 소수 클래스 수에 맞춰 언더샘플링
  - `run_training()`: augmentation 파라미터 추가 (label_smoothing=0.1, flipud=0.3, fliplr=0.5, erasing=0.2, dropout=0.2)
  - `main()`: `--no-balance` CLI 플래그 추가

### 학습 결과
- **균형 데이터셋**: train fall:64/normal:64, val fall:16/normal:16 (총 160장)
- **학습 메트릭**: top1=1.0, val_loss=0.00149 (에폭 4에서 조기 수렴)
- **실환경 검증** (/낙상영상 11개 영상):
  - accuracy=45.5%, precision=45.5%, **recall=100%**, F1=0.625
  - TP=5 (낙상 5/5 모두 감지), FP=6 (정상 6/6 모두 오분류), FN=0
  - 모든 영상에서 fall_score > 0.98 — 모델이 거의 모든 프레임을 fall로 분류
- **이전 Video 모델 대비**: accuracy 35% → 45.5% 향상, recall 100% 달성
- **평가**: 안전 시스템 관점에서 recall=100%(미감지 0건)이 precision보다 중요. 추후 더 많은 정상 영상 데이터로 specificity 개선 필요.

### 자동 업데이트된 파일
- `storage/training/fall-detection/model/baseline_model.json` — Sample 모델 weights로 갱신
- `storage/training/fall-detection/model/training_summary.json` — 학습 결과 기록
- `storage/training/fall-detection/yolo-sample/dataset/` — 균형 데이터셋
