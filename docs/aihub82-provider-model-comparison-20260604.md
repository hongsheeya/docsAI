# AI-Hub 82 제공 모델 성능 비교

작성일: 2026-06-04

## 결론

AI-Hub 82 제공 모델을 같은 운영 검증셋에서 직접 비교한 결과, 현재 프로젝트 내부 fine-tuned 모델이 더 높다. 따라서 기본 운영 provider는 내부 active 모델을 우선 사용하고, 내부 모델이 없을 때만 제공 모델로 fallback하는 것이 맞다.

## 비교 1: fall_aux4 4분류

- 검증셋: 2,800장
- 클래스: `happiness`, `embarrassed`, `distress`, `neutral`
- class별 support: 700장
- seed: `2026060401`
- min agreement: train 2, val 3
- crop pad ratio: 0.18
- 결과 JSON: `/opt/app/project/main/outputs/facial_aux_validation/aihub82_provider_compare_fall_aux4_20260604_023419.json`

| 모델 | Accuracy | Macro F1 | Distress Precision | Distress Recall | Distress F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 내부 MobileNetV3 fall_aux4 | 69.21% | 69.33% | 58.38% | 58.71% | 58.55% |
| 제공 EmotionNet `model.pth` | 43.43% | 39.94% | 33.25% | 80.00% | 46.98% |
| 제공 EfficientNet-b5 `model_eff.pth` | 57.21% | 55.28% | 41.46% | 82.57% | 55.21% |

해석:

- 제공 모델은 distress recall은 높지만 false positive가 너무 많다.
- 특히 EmotionNet은 `distress`로 과다 예측해 precision이 33.25%까지 떨어진다.
- fall_aux4 운영 기준에서는 제공 모델이 내부 모델보다 낮다.

## 비교 2: distress_vs_neutral 2분류

- 검증셋: 1,800장
- 클래스: `neutral`, `distress`
- class별 support: 900장
- seed: `2026060403`
- min agreement: train 2, val 3
- crop pad ratio: 0.20
- 결과 JSON: `/opt/app/project/main/outputs/facial_aux_validation/aihub82_provider_compare_distress_vs_neutral_20260604_024627.json`

| 모델 | Accuracy | Macro F1 | Distress Precision | Distress Recall | Distress F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 내부 MobileNetV3 active | 70.50% | 70.26% | 67.36% | 79.56% | 72.95% |
| 제공 EmotionNet `model.pth` | 55.22% | 52.92% | 53.62% | 77.33% | 63.33% |
| 제공 EfficientNet-b5 `model_eff.pth` | 61.83% | 60.72% | 58.85% | 78.67% | 67.33% |

해석:

- 현재 active 2분류 모델이 제공 모델 둘 다보다 높다.
- EfficientNet-b5도 내부 active 대비 accuracy -8.67%p, macro F1 -9.54%p, distress F1 -5.62%p 낮다.
- 제공 모델을 그대로 교체하면 낙상 보조 표정 근거에서 오탐이 늘 가능성이 높다.

## 제공 모델 자체 벤치마크와 차이

AI-Hub 제공 패키지 README/검토 문서 기준 자체 benchmark는 다음과 같다.

| 제공 모델 | Validation | Test |
| --- | ---: | ---: |
| EmotionNet | 81.130% | 80.858% |
| EfficientNet-b5 | 83.356% | 83.028% |

이 수치는 제공 패키지의 원래 7-class 표정 분류 benchmark다. 우리 운영 검증은 낙상 보조 목적에 맞게 face crop, agreement filter, distress grouping, neutral guard 기준을 적용한다. 그래서 제공 benchmark 수치가 그대로 운영 성능을 보장하지 않는다.

## 적용한 코드 결정

- 기본 `FACIAL_EMOTION_PROVIDER=auto`는 내부 active AI-Hub82 fine-tuned 모델을 먼저 사용한다.
- 내부 모델이 없을 때만 제공 EmotionNet으로 fallback한다.
- `FACIAL_EMOTION_PROVIDER=external-only`를 명시하면 제공 EmotionNet만 강제 사용할 수 있다.
- `FACIAL_EMOTION_PROVIDER=efficientnet-b5` 또는 `external-efficientnet-b5`를 명시하면 제공 EfficientNet-b5를 shadow/offline 검증용으로 사용할 수 있다.

## 검증 스크립트

- `/opt/app/project/main/scripts/evaluate_aihub82_provider_models.py`

재실행 예시:

```bash
TORCH_NUM_THREADS=1 python3 /opt/app/project/main/scripts/evaluate_aihub82_provider_models.py \
  --label-policy distress_vs_neutral \
  --seed 2026060403 \
  --max-train-per-class 3200 \
  --max-val-per-class 900 \
  --train-min-agreement 2 \
  --val-min-agreement 3 \
  --crop-pad-ratio 0.20 \
  --providers internal,emotionnet,efficientnet-b5
```
