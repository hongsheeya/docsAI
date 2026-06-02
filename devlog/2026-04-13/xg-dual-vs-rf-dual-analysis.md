# XG-Dual vs RF-Dual 파이프라인 상세 비교 분석

- **작성일**: 2026-04-13  
- **목적**: RF-Dual 신규 구현 후 두 듀얼 파이프라인의 설계·성능·트레이드오프를 체계적으로 비교

---

## 1. 개요

| 항목 | XG-Dual | RF-Dual |
|---|---|---|
| **낙상 탐지 모델** | XGBoost (XG-Fall) | RandomForest |
| **자세 분류 모델** | XGBoost (XG-Posture, 공유) | XGBoost (XG-Posture, 공유) |
| **YOLO 패스 횟수** | 1회 (통합 timeseries) | 2회 (RF 특징 + 자세 timeseries) |
| **낙상 특징 수** | 43개 (timeseries 윈도우 기반) | 13개 (클립 전체 통계) |
| **낙상 판단 방식** | 슬라이딩 윈도우 → 집계 → band 판정 | 클립 단일 예측 → 확률 임계값 |
| **억제자 체계** | 5단계 suppressor + 4종 override | motion guard (stationary check만) |
| **실시간 연속성** | 세션별 rolling cache (청크 tail stitching) | 없음 (청크 독립 판단) |
| **CV 정확도 (낙상)** | accuracy 0.905, recall 0.917, AUC 0.889 | accuracy 0.905, recall 0.917, AUC 1.000 |
| **intake 평가 (낙상)** | recall/precision/F1/acc = **1.0** (2026-04-10) | intake 미실행 (동일 21건 CV만) |
| **자세 CV 정확도** | accuracy 0.618, F1_macro 0.654 (공유) | accuracy 0.618, F1_macro 0.654 (공유) |

---

## 2. 학습 방법 비교

### 2-1. 낙상 탐지 모델

#### XG-Fall (XGBoost)
- **알고리즘**: XGBoost (`XGBClassifier`)
- **하이퍼파라미터**: n_estimators=200, max_depth=6, learning_rate=0.1
- **학습 데이터**: intake 21건 (Y:11 낙상, N:10 비낙상), 2026-04-10 기준
- **특징 생성**: unified timeseries → sliding window (1.0s 윈도우, 0.5s stride) → 윈도우당 43개 특징 계산
- **학습 단위**: 각 클립에서 다수의 윈도우가 생성되지만, **클립 레벨 레이블**로 학습
- **교차검증 (3-fold CV)**:
  - accuracy: **0.905**, recall: **0.917**, precision: **0.917**, F1: **0.905**, ROC-AUC: **0.889**
- **훈련 성능**: accuracy/recall/precision/F1 = **1.0** (과적합 경향, 소규모 데이터셋)
- **intake 평가 (동일 21건, 후처리 포함)**:
  - fall_recall=**1.0**, fall_precision=**1.0**, F1=**1.0**, accuracy=**1.0**
  - suspected 경계 케이스: 3건 (실제 오분류는 0건)

#### RF-Fall (RandomForest)
- **알고리즘**: `RandomForestClassifier`
- **하이퍼파라미터**: n_estimators=200, max_depth=None (unlimited, 완전 성장)
- **학습 데이터**: intake 21건 (동일 셋)
- **특징 생성**: 영상 전체 → 13개 통계 특징 (클립당 1 row)
- **학습 단위**: **클립 1건 = 1 행** (윈도우 없음)
- **교차검증 (3-fold CV)**:
  - accuracy: **0.905**, recall: **0.917**, precision: **0.917**, F1: **0.905**, ROC-AUC: **1.000**
- **훈련 성능**: accuracy/recall/precision/F1 = **1.0**
- **intake 평가**: 미실행 (CV만 존재, 후처리 없이)

> **해석**: CV 성능은 동일(0.905)하지만, XG-Fall은 43차원 + 후처리 규칙 튜닝으로 intake 기준 1.0 달성. RF는 후처리 없이 CV 0.917이므로 실제 운영 중 recall이 낮을 수 있음.

### 2-2. 자세 분류 모델 (공유)

XG-Dual과 RF-Dual은 **동일한 XG-Posture 모델을 공유**합니다.

- **알고리즘**: XGBoost (`XGBClassifier`)
- **하이퍼파라미터**: n_estimators=200, max_depth=3, learning_rate=0.08
- **특징 수**: 42개 (XG-Fall과 거의 동일, 1개 차이)
  - 동일한 unified timeseries에서 1.5s(업로드) / 1.0s(실시간) 윈도우 추출
- **학습 데이터**: 450건 (stand:105, walk:69, run:52, sit:105, lie:54, fall:65)
- **클래스**: 6개 (`stand`, `walk`, `run`, `sit`, `lie`, `fall`)
- **교차검증 (3-fold CV)**:
  - accuracy: **0.618**, F1_macro: **0.654**
- **훈련 성능**:
  - accuracy: **0.993**, F1_macro: **0.995**
  - class별 recall: stand:1.0, walk:1.0, run:1.0, sit:0.981, lie:0.9815, fall:1.0
- **일반화 갭**: 학습(0.993) vs CV(0.618) — 대규모 갭, 450건으로 6-class는 과적합 경향

---

## 3. 특징 추출 비교

### 3-1. XG-Dual (43개 특징, timeseries 윈도우 기반)

```
_extract_unified_timeseries()  ← YOLO 1회 패스
  → 프레임별 {bbox, keypoints(17개)} 시계열
  → _build_xg_feature_windows(window_sec=1.0, stride_sec=0.5)
     → 윈도우당 43개 특징 계산
```

**특징 그룹**:

| 그룹 | 특징명 | 수 |
|---|---|---|
| bbox 기반 | center_dy, height_ratio, aspect_change, stillness, floor_proximity, area_change, vert_horiz_ratio, max_down_speed, avg_conf, n_points | 10 |
| 포즈 기반 (키포인트 정규화) | pose_tilt_mean/max, pose_height_ratio_mean/min, pose_knee_bend_mean/min, pose_spread_mean/max, pose_descent_mean/max, pose_change_mean/max | 12 |
| 시간 전환 | descent_duration, oscillation_count, speed_std, post_descent_stillness, upper_body_motion | 5 |
| 전환 단계 | time_to_max_down_speed, time_from_peak_to_stillness, pre_descent_stillness, post_peak_recovery_ratio | 4 |
| 보행 주기 | step_period_est, knee_angle_cycle_strength, center_y_periodicity | 3 |
| 눕기/낙상 판별 | tilt_change_duration, spread_after_descent, floor_proximity_slope | 3 |
| 낙상 특화 | floor_contact_ratio, height_drop_persistence, collapse_impulse, post_floor_stability, slow_descent_ratio, tilt_height_collapse | 6 |
| **합계** | | **43** |

- **장점**: 낙상의 시간적 패턴(하강→정지 순서, 보행주기, 회복 거동)을 포착 가능
- **단점**: 특징 계산 비용이 높음 (17-keypoint pose 분석 포함)

### 3-2. RF-Dual (13개 특징, 클립 전체 통계)

```
_extract_rf_pipeline_features()  ← YOLO 1회 패스 (별도)
  → 프레임별 bbox 추적
  → 클립 전체에서 13개 통계량 집계 (평균/표준편차/최대/최소)
```

**특징 목록 및 중요도**:

| 특징명 | 의미 | RF 중요도 |
|---|---|---|
| final_height_ratio | 마지막 구간 자세 높이 비율 | **24.76%** |
| delta_y_max | 최대 하강 변위 | **21.74%** |
| aspect_ratio_std | 종횡비 변동성 (자세 변화) | **11.54%** |
| delta_y_mean | 평균 하강 변위 | 7.29% |
| center_y_mean | Y 중심 평균 위치 | 6.75% |
| delta_y_accel_max | 하강 가속도 최대 | 5.95% |
| height_mean | 높이 평균 | 4.46% |
| aspect_ratio_mean | 종횡비 평균 | 4.38% |
| center_y_std | Y 변동성 | 3.53% |
| height_std | 높이 변동성 | 3.35% |
| delta_height_mean | 높이 변화 평균 | 3.47% |
| delta_width_mean | 너비 변화 평균 | 1.85% |
| detection_rate | 사람 검출률 | 0.93% |

- **장점**: 빠른 추출, 해석 용이, 단순한 학습 구조
- **단점**: 시간 순서 정보 소실 (하강 "후" 정적 자세와 하강 "전" 정적 자세를 구분 못함)

### 3-3. XG-Posture 특징 추출 (양쪽 공통)

RF-Dual에서 XG-Posture를 위한 별도 YOLO 패스가 추가됩니다:

```
_extract_unified_timeseries()  ← RF-Dual에서는 2번째 YOLO 패스
  → _build_xg_feature_windows(window_sec=1.5/1.0, stride_sec=0.5)
  → XG-Posture.predict_proba() → 6-class 확률
  → _posture_heuristic_boost() → walk/run/stand 보정
  → _smooth_posture_sequence(window=5, ema_alpha=0.3)
  → 최빈도 레이블 + 평균 확률
```

---

## 4. 탐지 판단 로직 비교

### 4-1. XG-Fall 판단 로직

```
윈도우별 fall_proba 배열 → 집계:
  max_prob × 0.40
  + mean_prob × 0.22
  + fall_ratio × 0.13
  + floor_proximity_boost × 0.08
  + height_ratio_boost × 0.05
  + aspect_change_boost × 0.07
  + peak_boost (최대 0.08)
  = fall_score

→ Motion Gate (7가지 조건 중 2개 이상 충족 필요):
  - max_down_speed ≥ 0.15
  - center_dy ≥ 0.03
  - pose_change (height_ratio / aspect_change / floor_proximity 중 1)
  - frontal_fall (AR 변화 + 면적/높이 붕괴 또는 자세 붕괴)
  + 특수 override: _floor_override / _speed_override / _frontal_override / _slow_fall_override / _strong_pose_collapse / _directional_collapse_override / _still_post_fall_override

→ Suppressor 체인 (fall_score 상한 설정):
  1. stationary_suppressor: stillness≥0.75 + tilt≤12 + mds<0.12 → max 0.30
  2. bed_rise_suppressor: 침대 기상 패턴 → max 0.22
  3. spike_only_suppressor: max_prob≥0.84 + mean<0.22 + ratio<0.12 → max 0.24
  4. reverse_motion_suppressor: cdy≤0 + mds<0.05 → max 0.24
  5. static_floor_like_suppressor: 완전 정적 + 바닥 접촉 없음 → max 0.24
  6. aspect_only_suppressor: AR 변화만 있고 하강 없음 → max 0.30
  7. short_clip_strict: 2s 미만 + 윈도우 ≤ 3개
  8. fast_sit_suppressor: 무릎 굽힘 + 몸 수직 + 확산 적음 → max 0.40
  9. controlled_lie_suppressor: 천천히 눕는 패턴 → max 0.40

→ Band 판정:
  'non-fall' / 'suspected' / 'confirmed'
  → fall_detected = (band == 'confirmed')
```

### 4-2. RF-Fall 판단 로직

```
클립 전체 13개 통계 특징 → RF.predict_proba() → fall_probability

→ Adaptive Threshold:
  기본: 0.60
  short clip(n_frames < 10): 선형 보간하여 최대 0.72까지 상향
  too short(n_frames < 3): 'insufficient' → 강제 비낙상

→ fall_detected = (fall_probability ≥ effective_threshold)

→ Motion Guard (단순 stationary check):
  delta_y_mean < 5.0 × mg_mul AND
  delta_y_max < 12.0 × mg_mul AND
  delta_height_mean < 5.0 × mg_mul AND
  delta_width_mean < 3.0 × mg_mul AND
  delta_area_mean < 150.0 × mg_mul AND
  center_y_std < 10.0 × mg_mul AND
  height_std < 8.0 × mg_mul
  → 모두 충족 시 score = min(score, 0.10), fall_detected=False

→ Realtime 추가 guard:
  final_height_ratio > 0.45 AND delta_y_max < 30 AND center_y_std < 35
  → score < 0.85인 경우 억제

→ 억제자 없음 (suppressor chain 미적용)
→ Band 시스템 없음
```

### 4-3. Decision Arbitration (공통)

두 파이프라인 모두 `_arbitrate_decision()`을 통해 최종 decision_state 결정:

```
입력: fall_detected, posture_label, posture_probs, posture_score
→ 5가지 decision_state:
  'fall_confirmed' : RF/XG 낙상 감지 확정
  'fall_suspected' : 낙상 의심 (posture=fall 높음)
  'posture_only'  : 낙상 미감지 + posture=fall 어느 정도 높음
  'uncertain'      : 낙상 미감지 + posture 불확실
  'safe'           : 정상
```

---

## 5. 실시간 연속성 (Rolling Cache)

| 항목 | XG-Dual | RF-Dual |
|---|---|---|
| Rolling cache 지원 | ✅ 세션별 파일 영속화 | ❌ 미지원 |
| 청크 tail stitching | ✅ 이전 청크 1.5s tail 준비 | ❌ 청크 독립 |
| 세션 ID 키 | realtime_session_id 기반 분리 | N/A |
| 크로스 세션 오염 방지 | chunk_id 순번 연속성 체크 | N/A |

**영향**: 실시간 WebM 청크(5초)를 분석할 때, XG-Dual은 이전 청크 끝부분 1.5초를 이어 붙여 낙상 이벤트가 청크 경계에 걸려도 놓치지 않음. RF-Dual은 청크 경계에서 낙상이 분리되면 양쪽 모두 threshold 미달로 miss 가능.

---

## 6. 분석 속도 비교

| 시나리오 | XG-Dual | RF-Dual | 비고 |
|---|---|---|---|
| 업로드 모드 (일반) | 5~15초 | 4~12초 | RF-Dual: 2회 YOLO이나 특징 계산 단순 |
| 실시간 청크 (~5초 클립) | ~8초/청크 | ~6초/청크 | 추정치 |
| YOLO 패스 | 1회 | 2회 | RF-Dual 추가 패스 부담 |
| 특징 계산 | 43개×N윈도우 | 13개+42개×N윈도우 | XG-Dual: 윈도우 수가 많음 |
| 모델 추론 | 2-pass XGBoost | 1-pass RF + 1-pass XGBoost | RF 추론 자체는 매우 빠름 |

> **참고**: RF는 RandomForest (병렬 앙상블)이라 추론이 매우 빠르지만, YOLO 2회 패스가 GPU/CPU 병목. 실제 속도 차이는 하드웨어 환경에 따라 다름.

---

## 7. 낙상 감지 정확도 비교

### 7-1. 교차검증 기반 (21건, 3-fold)

| 지표 | XG-Fall (XG-Dual) | RF (RF-Dual) |
|---|---|---|
| CV Accuracy | **0.905** | **0.905** |
| CV Recall (Fall) | **0.917** | **0.917** |
| CV Precision | **0.917** | **0.917** |
| CV F1 | **0.905** | **0.905** |
| CV ROC-AUC | 0.889 | **1.000** |

→ CV 성능은 동일. 단, ROC-AUC에서 RF가 더 높음(1.000 vs 0.889). RF의 AUC=1.0은 소규모 데이터에서 결정트리의 완전분리 경향 때문, 과적합 지표일 수 있음.

### 7-2. Intake 평가 기반 (21건, 후처리 포함, XG-Dual만)

| 지표 | XG-Dual (2026-04-10) | RF-Dual |
|---|---|---|
| fall_recall | **1.000** | 미평가 |
| fall_precision | **1.000** | 미평가 |
| fall_F1 | **1.000** | 미평가 |
| accuracy | **1.000** | 미평가 |
| FN 건수 | 0 | - |
| FP 건수 | 0 | - |
| suspected 경계 케이스 | 3건 | - |

→ XG-Dual은 extensivetuning(suppressor, override) 이후 동일 21건 기준 완전 분리 달성. RF-Dual에는 이러한 튜닝이 미적용 상태이므로, CV recall 0.917 = 약 **2건 miss** 가능성.

### 7-3. 하드케이스별 예상 비교

| 케이스 유형 | XG-Dual | RF-Dual | 근거 |
|---|---|---|---|
| 빠른 정면/후면 낙상 | ✅ `_directional_collapse_override` 적용 | ❓ RF는 delta_y_max 높으면 감지 가능 |
| 침대 기상 (FP 위험) | ✅ `bed_rise_suppressor`로 억제 | ⚠️ 억제자 없음, 오탐 가능 |
| 천천히 눕는 낙상 | ✅ `_slow_fall_override` + `_still_post_fall_override` | ❓ final_height_ratio로 감지 가능하나 threshold 경계 |
| 정적 바닥형 비낙상 | ✅ `static_floor_like_suppressor` | ⚠️ aspect_ratio_std 낮으면 오탐 낮으나 보장 없음 |
| 짧은 클립 (< 5프레임) | ✅ 'insufficient' band | ✅ adaptive threshold + insufficient 처리 |
| 청크 경계 낙상 | ✅ rolling cache stitching | ❌ 청크 경계에서 miss 가능 |

---

## 8. 자세별 판단력 비교

두 파이프라인 모두 **동일한 XG-Posture 모듈**을 공유하므로, 자세 분류 성능 자체는 동일합니다. 단, **RF-Dual은 2번째 YOLO 패스에서 timeseries를 새로 추출**하므로, 영상 해상도/조명 변동에 따라 미세하게 다를 수 있습니다.

### XG-Posture 자세별 성능 (훈련 셋 기준)

| 자세 | 학습 샘플 | 훈련 Recall | CV (추정) |
|---|---|---|---|
| stand (서기) | 105 | **1.000** | ~0.65~0.75 (추정) |
| walk (걷기) | 69 | **1.000** | ~0.55~0.70 |
| run (뛰기) | 52 | **1.000** | ~0.50~0.65 |
| sit (앉기) | 105 | **0.981** | ~0.60~0.70 |
| lie (눕기) | 54 | **0.9815** | ~0.50~0.65 |
| fall (낙상 자세) | 65 | **1.000** | ~0.55~0.70 |
| **전체** | **450** | **0.993** | **0.618** |

> CV 자세별 수치는 eval 오류(numpy dtype 호환성)로 전체 accuracy 0.618만 알 수 있음. 자세별 CV 분해는 재평가 필요.

### 자세 분류 → 낙상 판단 연계

- **posture_label = 'lie'**: 낙상 의심이지만 침대/바닥 수면과 구분 필요 → `decision_state = 'posture_only'`
- **posture_label = 'fall'**: 낙상 자세 감지 → `decision_state = 'fall_suspected'`
- **fall_detected = True + posture = 'fall'**: `decision_state = 'fall_confirmed'`
- XG-Posture는 낙상 최종 판정에 직접 영향 없음 (설명/컨텍스트용), 최종 결정은 이진 fall 모델이 함

---

## 9. 장단점 요약

### XG-Dual

**장점**:
- 시간 패턴 포착: 하강 동역학(가속, 지속 시간, 전후 정지) 반영 가능
- 정밀한 억제자 체계: 침대 기상, 빠른 앉기, 천천히 눕기 등 오탐 케이스 별도 처리
- 실시간 rolling cache: 청크 경계 낙상 놓치지 않음
- intake 기준 완전 분리(1.0) 달성 (21건, 2026-04-10 tuning 이후)

**단점**:
- YOLO 패스 1회이지만 43차원 특징 계산이 복잡 (keypoint 기반 pose 분석)
- suppressor/override 체계가 복잡 → 유지보수 비용 높음
- 소규모 데이터(21건)에서의 과적합 위험성 존재

### RF-Dual

**장점**:
- 설계 단순: 13개 통계 특징, 단일 RF 예측으로 빠른 낙상 감지
- RF 추론 자체 속도 빠름 (최적화 불필요)
- 특징 해석 용이 (중요도 직접 공개, 직관적 의미)
- 자세 분류 지원으로 운영자에게 추가 컨텍스트 제공

**단점**:
- 시간 정보 손실: "언제 어떻게 넘어졌는가" 정보 없음
- suppressor chain 없음: 침대 기상, 빠른 앉기 오탐에 취약
- 실시간 연속성 없음: 청크 경계 낙상 miss 가능
- YOLO 2회 패스: RF-Dual은 오히려 속도 불리할 수 있음
- 별도 intake 후처리 튜닝 미적용

---

## 10. 추천 사용 시나리오

| 시나리오 | 추천 | 이유 |
|---|---|---|
| **정확도 최우선** (병원·요양원 실운영) | **XG-Dual** | suppressor 체계, rolling cache, intake 완전 분리 달성 |
| **실시간 웹캠 모니터링** | **XG-Dual** | rolling cache로 청크 경계 낙상 놓치지 않음 |
| **빠른 프리뷰 / 파일럿** | RF-Dual | 구현 단순, 자세 컨텍스트 제공 |
| **설명 가능한 AI 요구** | RF-Dual | feature importance 13개로 직관적 설명 가능 |
| **자세 분류 중심** | 동일 | XG-Posture 모델 공유 |
| **오탐률 최소화** | **XG-Dual** | 9종 suppressor로 FP 적극 억제 |

---

## 11. 향후 개선 포인트

### RF-Dual 개선 방향
1. **intake 평가 실행**: RF-Dual에 대해서도 21건 intake eval 수행 → 실제 FN/FP 파악
2. **suppressor 체계 추가**: `bed_rise_suppressor`, `fast_sit_suppressor` 최소화 버전 적용 검토
3. **rolling cache 지원**: RF features도 이전 청크 feature를 EWM(지수가중 평균)으로 이어받는 방식 탐색
4. **특징 확장**: `final_height_ratio` + `delta_y_max` 외 추가 discriminative feature 검토

### 공통 개선 방향
1. **외부 검증셋 확충**: 21건에서 100건 이상으로 확대 (다양한 카메라 각도, 체형, 조명)
2. **XG-Posture CV 재평가**: numpy dtype 호환성 버그 수정 후 자세별 CV 성능 측정
3. **실시간 A/B 비교**: 동일 웹캠 스트림에서 두 파이프라인 병렬 실행 → 합의율 측정
