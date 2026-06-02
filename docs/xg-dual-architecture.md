# XG 듀얼 아키텍처 설계서

> **레거시 문서**
> 현재 운영 기본은 `RF-Dual (RF Fall + XG-Posture)`이며, 이 문서는 XG-Dual 설계 이력을 보존하기 위한 참고 자료입니다.
> 최신 운영 기준은 [2026-06-01-current-status-and-training-pipeline.md](2026-06-01-current-status-and-training-pipeline.md) 및 [prototype/fall-detection/README.md](prototype/fall-detection/README.md)를 따릅니다.

> **RF-Pose 삭제 + XGBoost 중심 2단계 체계 재편**
> 작성일: 2026-04-06

---

## 1. 최종 아키텍처

```
입력 영상
  → YOLO-Pose + ByteTrack
  → 공통 시계열 추출 (person_timeseries)
      ├─ XG-Fall (binary: fall / nonfall)
      │    → fall_score → fall_gate / emergency decision
      │
      └─ XG-Posture (multiclass: 6-class)
           → posture_probs → posture_label
```

### 운영 원칙
- **알림/응급 판정**: XG-Fall 결과만 사용
- **화면 표시/설명**: XG-Posture 결과 사용
- **충돌 시**: 안전 우선 (Fall 우선)

---

## 2. RF-Pose 피처 명세 (보존용)

### 2.1 RF-Pose 12개 키포인트 파생 피처

| # | 피처명 | 물리적 의미 | 계산 방식 | 좌표 | 단위 |
|---|--------|------------|-----------|------|------|
| 1 | `body_tilt_angle_mean` | 어깨-엉덩이 기울기 평균 | 어깨중점↔엉덩이중점 직선의 수직 기울기 atan2(\|dx\|, \|dy\|) | 픽셀 | degrees |
| 2 | `body_tilt_angle_max` | 어깨-엉덩이 기울기 최대 | 위와 동일, 전 프레임 max | 픽셀 | degrees |
| 3 | `height_ratio_mean` | 신장 비율 평균 | \|nose_y - ankle_y\| / vid_height | 정규화 | 0~1 ratio |
| 4 | `height_ratio_min` | 신장 비율 최소 (쓰러짐 감지) | 위와 동일, 전 프레임 min | 정규화 | 0~1 ratio |
| 5 | `knee_bend_angle_mean` | 무릎 굽힘 각도 평균 | hip-knee-ankle 3점 각도 (acos) | 픽셀 | degrees |
| 6 | `knee_bend_angle_min` | 무릎 굽힘 각도 최소 | 좌우 무릎 중 min, 전 프레임 min | 픽셀 | degrees |
| 7 | `horizontal_spread_mean` | 수평 확산도 평균 | 유효 키포인트 x좌표 표준편차 | 픽셀 | px std |
| 8 | `horizontal_spread_max` | 수평 확산도 최대 (누운 자세) | 위와 동일, 전 프레임 max | 픽셀 | px std |
| 9 | `center_descent_speed_mean` | 몸 중심 하강 속도 평균 | 연속프레임 (shoulder+hip)/4 center_y 하강량, positive only | 픽셀 | px/frame |
| 10 | `center_descent_speed_max` | 몸 중심 하강 속도 최대 (낙상 순간) | 위와 동일, max | 픽셀 | px/frame |
| 11 | `pose_change_rate_mean` | 자세 변화율 평균 | 연속프레임 keypoint flatten 벡터 코사인 비유사도 (1-cos_sim) | 정규화 | 0~2 |
| 12 | `pose_change_rate_max` | 자세 변화율 최대 | 위와 동일, max | 정규화 | 0~2 |

**신뢰도 필터**: `KP_CONF_MIN = 0.3` — confidence 미달 키포인트는 계산에서 제외

### 2.2 RF Guard 아이디어 (이식 가치 있음)

| Guard | 조건 | 효과 | 원래 위치 |
|-------|------|------|----------|
| **Stationary guard** | delta_y/height/width/area/center_y_std 모두 저값 | score→max(0.10), fall=False | RF-Pipeline + RF-Pose |
| **AR-only guard** | aspect_ratio_std > 0.1, delta_y_max < 15, center_y_std < 15 & score < 0.75 | score→max(0.20), fall=False | RF-Pipeline + RF-Pose |
| **Realtime guard** | 실시간 + score < 0.85 + final_height_ratio > 0.45 + delta_y_max < 30 + center_y_std < 35 | score→max(0.25), fall=False | RF-Pipeline + RF-Pose |
| **Moderate-motion dampener** | fall + score < 0.70 + delta_y_max < 25 + final_height_ratio > 0.50 + accel < 12 | score→max(0.40), fall=False | RF-Pipeline + RF-Pose |
| **Short-clip threshold** | n_frames < 10: effective_threshold = max(base, SHORT_CLIP_MAX * n_frames/SHORT_CLIP_N_FRAMES) | 짧은 영상 오탐 방지 | RF-Pipeline |

### 2.3 RF-Pose 결합 피처 구조 (25개)

```
_combined_columns = _RF_FEATURE_COLUMNS (13) + _POSE_FEATURE_COLUMNS (12)
```

RF-Pose 모델: `RandomForestClassifier(n_estimators=200, class_weight='balanced_subsample')`

---

## 3. XG 이식 피처 명세

### 3.1 기존 XGBoost 10개 피처 (유지)

| # | 피처명 | 설명 |
|---|--------|------|
| 1 | `center_dy` | 수직 이동량 |
| 2 | `height_ratio` | 높이 변화율 |
| 3 | `aspect_change` | 자세 변화 (종횡비) |
| 4 | `stillness` | 정지 상태 비율 |
| 5 | `floor_proximity` | 바닥 근접도 |
| 6 | `area_change` | 면적 변화 |
| 7 | `vert_horiz_ratio` | 수직/수평 이동 비율 |
| 8 | `max_down_speed` | 최대 하강 속도 |
| 9 | `avg_conf` | 평균 검출 신뢰도 |
| 10 | `n_points` | 유효 데이터 포인트 수 |

### 3.2 RF-Pose에서 이식할 12개 피처 (정규화 window 버전)

| # | 원본 | XG 버전 | 변경점 |
|---|------|---------|--------|
| 11 | body_tilt_angle_mean | `pose_tilt_mean` | window 내 정규화 좌표 기반 재계산 |
| 12 | body_tilt_angle_max | `pose_tilt_max` | 동일 |
| 13 | height_ratio_mean | `pose_height_ratio_mean` | vid_height → 정규화 좌표로 통일 |
| 14 | height_ratio_min | `pose_height_ratio_min` | 동일 |
| 15 | knee_bend_angle_mean | `pose_knee_bend_mean` | 동일 (각도는 좌표계 무관) |
| 16 | knee_bend_angle_min | `pose_knee_bend_min` | 동일 |
| 17 | horizontal_spread_mean | `pose_spread_mean` | 정규화 좌표 std |
| 18 | horizontal_spread_max | `pose_spread_max` | 동일 |
| 19 | center_descent_speed_mean | `pose_descent_mean` | bbox 정규화 center_y 기반 |
| 20 | center_descent_speed_max | `pose_descent_max` | 동일 |
| 21 | pose_change_rate_mean | `pose_change_mean` | 정규화 벡터 코사인 비유사도 |
| 22 | pose_change_rate_max | `pose_change_max` | 동일 |

### 3.3 문서 제안 필수 5개 피처 (신규)

| # | 피처명 | 설명 | 설계 의도 |
|---|--------|------|----------|
| 23 | `descent_duration` | 하강 지속 시간 (초) | 천천히 앉기 vs 급격한 낙상 구분 |
| 24 | `oscillation_count` | 수직 진동 횟수 | 보행 주기 감지 |
| 25 | `speed_std` | 하강 속도 표준편차 | 일정한 동작 vs 급변 동작 구분 |
| 26 | `post_descent_stillness` | 하강 후 정지 비율 | 낙상 후 거동 불능 vs 앉은 후 활동 |
| 27 | `upper_body_motion` | 상체 움직임량 | 팔/어깨 제어 여부 (낙상 시 제어 상실) |

### 3.4 전이 구간 피처 4개 (신규)

| # | 피처명 | 설명 |
|---|--------|------|
| 28 | `time_to_max_down_speed` | 최대 하강 속도 도달 시간 |
| 29 | `time_from_peak_to_stillness` | 최고점~정지 전환 시간 |
| 30 | `pre_descent_stillness` | 하강 전 정지 비율 |
| 31 | `post_peak_recovery_ratio` | 하강 후 회복(상승) 비율 |

### 3.5 보행 주기 피처 3개 (신규)

| # | 피처명 | 설명 |
|---|--------|------|
| 32 | `step_period_est` | 추정 보행 주기 (FFT 기반) |
| 33 | `knee_angle_cycle_strength` | 무릎 각도 주기성 강도 |
| 34 | `center_y_periodicity` | center_y 주기성 (걷기/뛰기 감지) |

### 3.6 눕기/낙상 구분 피처 3개 (신규)

| # | 피처명 | 설명 |
|---|--------|------|
| 35 | `tilt_change_duration` | 기울기 변화 지속 시간 (점진적 눕기 vs 급격한 낙상) |
| 36 | `spread_after_descent` | 하강 후 수평 확산도 (눕기 → 높은 spread) |
| 37 | `floor_proximity_slope` | 바닥 근접도 변화 기울기 (급격 vs 점진) |

---

## 4. XG-Fall (Binary) 설계

### 4.1 입력
- **37개 피처** (기존 10 + pose 12 + 신규 15)
- **window**: 1.0초 / 0.5초 stride (기존 유지)
- **objective**: `binary:logistic`
- **threshold**: 0.50 (기존 _PERSON_FEATURE_THRESHOLD 유지)

### 4.2 학습 전략
- 기존 XGBoost 학습 흐름 유지 (sliding window, 하이퍼파라미터 탐색, threshold sweep, recall 우선)
- scale_pos_weight로 클래스 불균형 보정
- StratifiedKFold 5-fold CV

### 4.3 후처리
- 기존 motion gate (4-level cascade) 유지
- 신규 suppressor 추가:
  - fast-sit suppressor (무릎 굽힘 크고 기울기 낮으면 억제)
  - controlled-lie suppressor (하강 시간 길고 가속도 낮으면 억제)
  - short-clip stricter threshold (RF 이식)
  - stationary suppressor (이미 존재)
  - aspect-only suppressor (이미 존재)

---

## 5. XG-Posture (Multiclass) 설계

### 5.1 입력
- **동일 37개 피처** (공통 추출기에서 생성)
- **window**: 1.5~2.0초 / 0.5초 stride
- **classes**: `fall / walk / run / sit / lie / stand` (6-class)

### 5.2 학습 전략
- **objective**: `multi:softprob`
- **eval_metric**: `mlogloss`
- **클래스 가중치**: per-class weighting 또는 오버샘플링
- **early stopping** + macro F1 + class-wise recall 모니터링
- **라벨 전파**: 영상 단위 일괄 전파 금지 → window/interval 단위 수동 라벨 필수

### 5.3 후처리 (Temporal Smoothing)
- 최근 3~5 window majority vote
- Exponential moving average
- Class transition constraints (sit→run 불가능, stand→lie는 fall 확인)

---

## 6. 결과 JSON 스키마

```json
{
  "fall_detected": true,
  "fall_score": 0.84,
  "posture_label": "sit",
  "posture_score": 0.62,
  "posture_probs": {
    "stand": 0.05,
    "walk": 0.03,
    "run": 0.01,
    "sit": 0.62,
    "lie": 0.11,
    "fall": 0.18
  },
  "decision_state": "fall_priority",
  "explain": [
    "max_down_speed high",
    "body_tilt spike",
    "posture ambiguous: sit vs fall"
  ]
}
```

### 상태값 (decision_state)

| 상태 | 조건 | UI 색상 |
|------|------|---------|
| `safe` | XG-Fall 낮음 + XG-Posture stand/walk/run | Green |
| `posture_only` | XG-Fall 낮음 + XG-Posture sit/lie | Blue |
| `fall_suspected` | XG-Fall 중간 (threshold 근처) | Yellow |
| `fall_confirmed` | XG-Fall 높음 (0.75+) | Red |
| `uncertain` | XG-Fall/XG-Posture 충돌 또는 신뢰도 낮음 | Gray |

### Arbitration 규칙

| XG-Fall | XG-Posture | 결정 |
|---------|-----------|------|
| 높음 | sit | `fall_priority` — 경고 유지, "fall/sit 경계" |
| 높음 | lie | `fall_confirmed` — 경고 |
| 높음 | stand/walk | `fall_confirmed` — 경고 |
| 낮음 | lie | `posture_only` — "눕는 자세", 알림 없음 |
| 낮음 | sit | `safe` — "앉은 자세" |
| 낮음 | stand/walk/run | `safe` |
| 중간 | fall | `fall_suspected` — 주의 |

---

## 7. 3-Level 라벨 체계

### Level 1: 위험 라벨
- `fall` / `nonfall`

### Level 2: 자세 라벨
- `stand` / `walk` / `run` / `sit` / `lie`

### Level 3: 옵션 라벨 (메타데이터)
- `transition` — 자세 전환 중
- `uncertain` — 판별 불가
- `occluded` — 가림 상태

---

## 8. HITL 피드백 스키마

```json
{
  "predicted_fall_label": "Y",
  "actual_fall_label": "N",
  "predicted_posture_label": "fall",
  "actual_posture_label": "sit",
  "ambiguity_flag": true,
  "note": "빠르게 의자에 앉은 동작"
}
```

---

## 9. RF-Pose 삭제 로드맵

| 단계 | 이름 | 내용 |
|------|------|------|
| A | deprecate | UI에서 rf-pose 옵션 숨기기. config로만 활성화. |
| B | shadow mode | 서비스 결정 미사용. 백그라운드 비교 로그만. |
| C | hard delete | model_type=rf-pose 분기, 모델 로딩, retrain 함수, UI 옵션 삭제 |
| D | 보존 | pose feature 유틸, keypoint validation, confidence filtering, 문서 |

### 삭제 승인 조건
- Fall recall ≥ 기존 XG 대비 동등
- sit/lie FP ≤ 기존 대비
- Posture macro F1 ≥ RF-Pose shadow 결과
- hard-case lie/fall confusion ≤ 허용 범위

---

## 10. 데이터 수집 최소 목표

| 클래스 | 최소 목표 | 우선순위 |
|--------|----------|---------|
| fall | 1000+ | 기존 데이터 유지 |
| stand | 300+ | 1차 재라벨링 |
| walk | 500+ | 1차 재라벨링 |
| run | 300+ | 2차 자체 촬영 |
| sit | 500+ | 1차 재라벨링 + hard-case |
| lie | 400+ | 2차 자체 촬영 + hard-case |

### Hard-case 세트
- **sit-hard**: 빠른 의자 앉기, 푹 주저앉기, 화면 밖 의자 앉기
- **lie-hard**: 침대 천천히 눕기, 바닥 내려가 눕기, 요가/스트레칭
- **fall-hard**: 무릎 먼저 꿇고 넘어짐, 벽 짚다가 무너짐, 부분 가림 낙상
