# 표정 점수 신뢰도 점검 및 개선 계획

작성일: 2026-06-04

## 현재 문제

사용자가 확인한 문제는 타당하다.

- 이전 active 모델은 `neutral/distress` 2분류였기 때문에 웃어도 `기쁨` 수치가 올라갈 수 없는 구조였다.
- UI는 이 값을 일반 표정 퍼센트처럼 보여주고 있어 오해를 만들었다.
- `보정불편`은 raw distress score에 얼굴 검출/일관성/품질 gate를 곱한 값이었지만, UI에서 의미 설명이 부족했다.
- 기존 runtime distress 적용 threshold가 낮아 애매한 표정에서도 불편 신호가 쉽게 보일 수 있었다.

## 현재 active 모델

- 모델: `/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt`
- label policy: `fall_aux4`
- classes: `happiness`, `embarrassed`, `distress`, `neutral`
- accuracy: 78.64%
- macro F1: 78.47%
- happiness F1: 88.43%
- embarrassed F1: 80.04%
- distress F1: 69.16%
- neutral F1: 76.23%

## 캘리브레이션 결과

- 결과 JSON: `/opt/app/project/main/outputs/facial_aux_validation/aihub82_active_calibration_fall_aux4_20260604_032323.json`
- 결과 MD: `/opt/app/project/main/outputs/facial_aux_validation/aihub82_active_calibration_fall_aux4_20260604_032323.md`
- validation rows: 3,600장
- top-label ECE: 0.0309

해석:

- 전체 confidence calibration은 나쁘지 않다.
- 0.9 이상 confidence bin은 평균 confidence 96.83%, 실제 accuracy 97.57%로 꽤 맞다.
- 0.3~0.5 confidence 구간은 흔들림이 크므로 UI에서 `모델확신`과 `신뢰 낮음`을 같이 표시해야 한다.

## Distress threshold

| Threshold | Accuracy | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: | ---: |
| 0.35 | 86.33% | 73.56% | 70.78% | 72.14% |
| 0.45 | 87.03% | 81.79% | 61.89% | 70.46% |
| 0.50 | 87.28% | 85.19% | 59.44% | 70.03% |

적용:

- 기본 distress 적용 threshold를 0.35로 상향했다.
- 얼굴 검출/신뢰가 낮은 경우 threshold를 0.45로 상향했다.
- UI는 `불편 raw`와 `신뢰보정`을 분리해서 표시한다.

## 코드 변경

- `/opt/app/project/main/src/model/struct/video_analysis.py`
  - active AI-Hub82 모델 우선 사용
  - 모델 라벨 목록 및 출력 모드 반환
  - distress threshold 정책 추가
- `/opt/app/project/main/src/app/page.dashboard/view.ts`
  - `top` 대신 `모델확신` 표시
  - `보정불편` 대신 `신뢰보정 불편` 표시
  - `불편 raw / 신뢰보정` 분리 표시
- `/opt/app/project/main/scripts/calibrate_aihub82_facial_scores.py`
  - active 모델 calibration/ECE/threshold sweep 산출

## 다음 학습 전략

단순 epoch 증가보다 현재 약점인 distress/neutral 경계를 집중 개선한다.

1. 성공한 `fall_aux4 large 160` 구성을 기준으로 유지한다.
2. distress loss weight를 1.18로 올려 distress recall을 개선해 본다.
3. 너무 큰 데이터 cap은 child kill 위험이 있어 첫 실험은 3,200/class, val 900/class로 안정화한다.
4. 이후 192px clean agreement set과 more-data balanced set을 순차 실험한다.
5. active 모델보다 macro F1이 높을 때만 승격한다.

현재 백그라운드 supervisor:

- active macro F1: 0.7847
- active accuracy: 0.7864
- running experiment: `fall_aux4_large_160_distress_weighted`
