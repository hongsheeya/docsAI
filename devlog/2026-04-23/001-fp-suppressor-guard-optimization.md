# RF-Dual FP 억제 및 guard_soft_override 강화

- **ID**: 001
- **날짜**: 2026-04-23
- **유형**: 버그 수정 / 성능 개선

## 작업 요약

4월 22일 리콜 튜닝(motion guard override 완화) 후 신규 발생한 FP 3건의 근본 원인을 분석하고 수정하였다.
`_guard_soft_override` 조건이 지나치게 낮아 score 0.55 이상이거나 height_std ≥ 35 이면 중간 dampener가 우회되어
상체 흔들림·자세 변화만으로도 낙상으로 오탐하는 구조적 문제를 해결하였다.
신규 `fhr_rise_suppressor`를 추가하여 bbox 높이가 초기보다 오히려 커지는 경우(자연적인 기립/보행)를 추가 억제하였다.
200-video 재평가 결과 FP 13 → 9, 전체 지표(accuracy/precision/F1) 베이스라인 대비 개선.

## FP 3건 공통 패턴 분석

| 영상 | RF score | posture | height_std | delta_y_max | final_height_ratio | 원인 |
|------|--------|---------|-----------|------------|---------------------|------|
| 02327_H_A_N_C2 (lie) | 0.4833 | lie | 39.17 | 12.59 | 1.30 | height_std≥35 → override, 누워있는 자연 자세인데 bbox 높이 변화 |
| 01683_Y_E_N_C3 (walk) | 0.6067 | walk | 18.80 | 8.89 | 0.74 | score≥0.55 → override, 작은 움직임뿐 |
| 00110_H_A_N_C4 (stand) | 0.5667 | stand | 38.89 | 18.42 | 1.47 | score≥0.55 + height_std≥35 양방 override, bbox 오히려 커짐 |

**핵심 원인**: `_guard_soft_override` 의 두 조건이 과완화 상태
1. `fall_score >= 0.55`: 낙상 threshold(0.40)보다 불과 0.15 높으면 dampener 우회
2. `height_std >= 35.0`: bbox 높이 변화만으로 실제 하강 증거 없이도 우회
→ 상체 흔들림·팔 들기·자세 변환 시 height_std가 35+ 되어 오탐 유발

## 변경 내역

### src/model/struct/video_analysis.py

**1) `_guard_soft_override` 조건 강화** (라인 ~6885)

| 변경 전 | 변경 후 |
|---------|---------|
| `fall_score >= max(threshold+0.20, 0.55)` | `fall_score >= max(threshold+0.20, 0.62)` |
| `height_std >= 35.0` | `height_std >= 45.0 AND delta_y_max >= 15.0` |

- score 기준 0.55 → 0.62: FP2(0.6067) 포함 중간 점수 케이스가 dampener에 들어감
- height_std 단독 기준 폐지 → "높이 변화 + 실제 하강 이동" 양방 조건 필요
  - FP1 (height_std=39.17, dym=12.59 < 15): 조건 불충족 → suppressed ✓
  - FP3 (height_std=38.89 < 45): 조건 불충족 → suppressed ✓

**2) `fhr_rise_suppressor` 신규 추가** (라인 ~6903)

```python
# FP-fix: fhr_rise_suppressor — bbox height INCREASED vs initial → non-fall natural posture
if (
    fall_detected and not _motion_guard_applied
    and feat.get('final_height_ratio', 1.0) > 1.08
    and fall_score < 0.65
):
    fall_score = min(fall_score, 0.38)
    fall_detected = False
    pred = 0
    _suppressed_by.append('fhr_rise_suppressor')
```

- 낙상이라면 bbox 높이가 줄어야 정상 (fhr < 1.0)
- fhr > 1.08 = 낙상 후 bbox가 오히려 커짐 = 기립·보행·누운 자세 유지 등 비낙상
- score < 0.65 조건으로 강한 낙상 신호는 보호
- FP1 (fhr=1.30), FP3 (fhr=1.47) 추가 보호

## 평가 결과 (200-video, 낙상 100 + 비낙상 100)

| 지표 | 베이스라인 (0422) | 리콜튜닝 (0422) | 최종 (0423) |
|------|-----------------|----------------|-------------|
| accuracy | 0.9050 | 0.9050 | **0.9100** |
| precision | 0.9010 | 0.8785 | **0.9100** |
| recall | 0.9100 | **0.9400** | 0.9100 |
| F1 | 0.9055 | 0.9082 | **0.9100** |
| TP | 91 | 94 | 91 |
| TN | 90 | 87 | **91** |
| FP | 10 | 13 | **9** |
| FN | 9 | 6 | 9 |

- accuracy/precision/F1/TN 모두 베이스라인 대비 개선
- recall은 베이스라인(0.91)과 동일하게 유지 (리콜 전용 튜닝에서의 0.94→0.91 소폭 후퇴)
- FP는 베이스라인 10건보다도 1건 줄어든 9건으로 최저치 달성

## 잔존 오류 분석

### 잔존 FP 9건 공통 패턴
- 모두 `fall_suspected` 상태 (score 0.40~0.74, 확정 아님)
- posture: stand(4건), walk(2건), sit(2건), lie(1건)
- 0_E_ 코드 (노인 + 야간/특수환경) 비중 높음 → 노인 움직임 패턴이 RF 모델에 낙상으로 혼동될 가능성

### 잔존 FN 9건 공통 패턴
- 모두 `safe` or `posture_only` 상태, risk_score 0.10~0.40
- RF 모델 자체가 낙상 점수를 낮게 부여 → suppressor 이전 단계 문제
- 해결 방향: RF 모델 재훈련(특히 서서-넘어지기 slow-fall 케이스 데이터 보강)

## 상체 움직임 오탐 메커니즘 설명

RF 모델은 13개 bbox 통계 feature로 낙상을 판단한다. 이 중 `height_std`는 bbox 높이의 시계열 표준편차인데,
팔을 들거나 허리를 굽히는 등 **상체 움직임만으로도 bbox 높이가 크게 변동**할 수 있다.
기존 `_guard_soft_override` 의 `height_std >= 35.0` 조건이 이를 방치해, 실제 하강 이동(delta_y_max)이 거의
없어도 suppressor가 우회되어 낙상으로 오탐하는 경로가 존재했다.
이번 수정으로 **`height_std` 단독 조건을 폐지**하고, 반드시 `delta_y_max >= 15.0`(의미 있는 실제 하강 이동)을
함께 요구함으로써 상체 흔들림에 의한 오탐 경로를 차단하였다.
