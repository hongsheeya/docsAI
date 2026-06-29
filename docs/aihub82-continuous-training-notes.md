# AI-Hub 82 Continuous Training Notes

## 2026-06-02 점검 결과

현재 AI-Hub 82 표정 모델은 백그라운드 supervisor가 계속 학습합니다.

- supervisor: `/opt/app/project/main/scripts/continuous_aihub82_training_supervisor.py`
- train script: `/opt/app/project/main/scripts/train_facial_emotion_aihub82.py`
- status: `/opt/app/storage/project-main/outputs/continuous_training/aihub82_status.json`
- active summary: `/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_summary.json`
- active model: `/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt`

현재 active 성능:

- macro F1: `0.6198`
- accuracy: `0.6206`
- 약한 클래스: `hurt`, `anxiety`

## 낮은 성능 원인 후보

active summary 기준으로 `hurt`, `anxiety`, `sadness`, `anger` 사이 혼동이 큽니다.

주요 원인 후보:

1. 감정 라벨 자체가 의미적으로 가까워 7-class 단일 분류 난도가 높습니다.
2. validation agreement 기준이 낮으면 애매한 표정이 평가에 포함되어 macro F1이 낮아질 수 있습니다.
3. 일부 원천 zip이 손상되어 skip되고 있어 클래스별 원천 분포가 완전히 균일하지 않을 수 있습니다.
4. 현재 학습은 ZIP 내부 이미지를 매 step 읽고 crop/augmentation을 수행해 시간이 오래 걸립니다.

## 적용한 개선

다음 supervisor 실행부터 적용됩니다.

1. 후보 모델은 active macro F1보다 높을 때만 승격합니다.
2. 후보 학습이 끝나면 per-class F1, confusion pair, root cause, next action을 JSON/MD로 남깁니다.
3. 낮은 성능 기준은 `FALLAI_AIHUB82_LOW_MACRO_F1`, 기본 `0.68`입니다.
4. 반복 속도를 위해 diagnostic run을 먼저 실행합니다.
5. `num_workers=2`, persistent workers, prefetch, early stop을 사용합니다.
6. `val_min_agreement=3` 실험으로 라벨 노이즈 영향을 분리 측정합니다.

## 학습 시간이 긴 이유

현재 실행 중인 기존 run은 다음 조건이라 오래 걸리는 것이 정상입니다.

- `mobilenet_v3_large`
- `image_size=192`
- `batch_size=24`
- `max_train_per_class=12000`
- `max_val_per_class=2500`
- `num_workers=0`
- ZIP 내부 이미지를 매 step 읽고 얼굴 crop/augmentation 수행

반복 개선용으로는 무거운 설정이므로, 이후 run은 더 짧은 diagnostic 설정을 먼저 돌립니다.
