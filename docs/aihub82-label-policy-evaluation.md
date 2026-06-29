# AI-Hub 82 Label Policy Evaluation

Updated: 2026-06-04

## 결론

AI-Hub 82 표정 모델은 낙상을 직접 판단하는 모델이 아니라 낙상 판단 보조 근거를 만드는 모델입니다. 따라서 `기쁨/당황/분노/불안/상처/슬픔/중립` 7개 표정을 모두 세밀하게 맞히는 것보다, 낙상 판단에 필요한 불편/고통 계열 신호를 안정적으로 잡는 방향이 더 적합합니다.

기존 active 모델의 confusion matrix를 같은 검증셋에서 재해석한 결과, 애매한 부정 표정을 하나의 `distress` 계열로 병합하면 지표가 크게 개선됩니다.

## Active 7-Class 기준

- model: `aihub82_facial_emotion_mobilenetv3.pt`
- dataset: AI-Hub 82 Korean facial emotion compound image
- validation rows: `17,500`
- accuracy: `0.6300`
- macro F1: `0.6215`

약한 클래스:

- `hurt`: F1 `0.3950`
- `anxiety`: F1 `0.4666`
- `sadness`: F1 `0.5701`
- `anger`: F1 `0.6536`

주요 혼동은 `hurt -> sadness`, `sadness -> hurt`, `anxiety -> anger`, `anxiety -> embarrassed`, `hurt -> anxiety`처럼 부정/불편 표정 내부에서 많이 발생합니다.

## 정책별 재해석 검증

| 정책 | 클래스 구성 | Accuracy | Macro F1 | 해석 |
|---|---:|---:|---:|---|
| 기존 7분류 | happiness, embarrassed, anger, anxiety, hurt, sadness, neutral | `0.6300` | `0.6215` | 세부 감정 간 혼동이 커서 낮음 |
| `fall_aux4` | happiness, embarrassed, distress, neutral | `0.8078` | `0.7787` | 낙상 보조용으로 가장 균형적 |
| `distress_binary` | non_distress, distress | `0.8333` | `0.8313` | 불편/비불편 판단만 보면 가장 안정적 |
| `distress_vs_neutral` | neutral, distress | `0.8922` | `0.8447` | 기쁨/당황을 제거하면 높지만, 실제 서비스 음성 샘플이 줄어듦 |
| `drop_hurt_anxiety_keep5` | happiness, embarrassed, anger, sadness, neutral | `0.8181` | `0.8153` | 약한 클래스를 제거하면 수치는 오르지만 불편 근거 손실 위험 |

## 적용 방향

1. 운영 모델 후보는 `fall_aux4`를 우선 검증합니다.
2. 낙상 점수 보정에는 `distress_binary` 또는 `fall_aux4`의 `distress` 확률을 사용합니다.
3. `distress_vs_neutral`은 성능 검증용으로만 사용하고, 실제 운영에서는 기쁨/당황 제거로 인한 음성 데이터 부족 위험을 확인한 뒤 적용합니다.
4. 7분류 모델은 포트폴리오/분석 설명용 세부 감정 표시에는 쓸 수 있지만, 낙상 보조 점수의 주 모델로는 적합도가 낮습니다.

## 이번 코드 변경

- `train_facial_emotion_aihub82.py`
  - `--label-policy seven|fall_aux4|distress_binary|distress_vs_neutral` 추가
  - `--crop-pad-ratio` 추가
  - `--augment-strength none|light|medium` 추가
- `continuous_aihub82_training_supervisor.py`
  - 빠른 반복 실험을 grouped label policy 중심으로 변경
  - CPU/shared-memory 안전을 위해 `num_workers=0` 유지
- `video_analysis.py`
  - `distress`, `non_distress` 라벨을 런타임 표정 보조 점수에서 해석하도록 추가

