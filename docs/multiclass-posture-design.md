# 다중 자세 클래스 라벨 체계 설계 (이진 → 6-class 전환)

> **FN-20260406-0002** | 작성일: 2026-04-06

---

## 1. 클래스 정의서

### 1.1 6-Class 자세 분류 체계

| # | 코드 | 한국어 | 영어 | 이진 매핑 | 설명 |
|---|------|--------|------|-----------|------|
| 1 | `standing` | 서기 | Standing | N | 두 발로 직립하여 서 있는 자세 |
| 2 | `walking` | 걷기 | Walking | N | 일정한 보폭으로 이동하는 자세 |
| 3 | `sitting` | 앉기 | Sitting | N | 의자/바닥에 앉은 자세 |
| 4 | `running` | 뛰기 | Running | N | 빠른 속도로 이동, 양 발이 동시에 지면에서 떨어지는 순간 존재 |
| 5 | `lying` | 눕기 | Lying | N | 바닥에 누운 자세 (의도적 휴식 포함) |
| 6 | `fall` | 낙상 | Fall | Y | 비자발적으로 급격하게 넘어지는 동작 |

### 1.2 경계 조건 및 라벨링 기준

| 경계 | 구분 기준 |
|------|----------|
| **서기 ↔ 걷기** | 한 발짝 이상 연속 이동 시 walking. 경미한 체중 이동은 standing |
| **걷기 ↔ 뛰기** | center_x 변화율이 walking의 2배 이상 + 양발 동시 이지(離地) 여부 |
| **앉기 ↔ 눕기** | 등이 바닥에 접촉하면 lying. 엉덩이만 지면 접촉이면 sitting |
| **눕기 ↔ 낙상** | **핵심 구분**: 의도적(자발적) 전환 = lying, 비자발적·급격한 전환 = fall |
| | - `center_descent_speed_max > 0.3` + 급격한 `body_tilt_angle` 변화 = fall |
| | - `center_descent_speed_max < 0.2` + 점진적 전환 = lying |

### 1.3 Pose Feature 지표별 자세 특성

| Feature | standing | walking | sitting | running | lying | fall |
|---------|----------|---------|---------|---------|-------|------|
| `body_tilt_angle` | < 15° | < 20° | < 30° | < 25° | > 60° | > 45° (급격) |
| `height_ratio` | > 0.8 | > 0.7 | 0.4~0.7 | > 0.7 | < 0.3 | < 0.3 (급격) |
| `knee_bend_angle` | > 160° | 130~170° | < 120° | < 140° | < 90° | 변동 |
| `horizontal_spread` | Low | Low | Med | Low | High | Med→High |
| `center_descent_speed` | ~0 | Low | ~0 | Low | ~0 | **High (>0.3)** |
| `pose_change_rate` | Low | Med | Low | High | Low | **High (>0.5)** |

---

## 2. 데이터 구조 변경 계획

### 2.1 action_behavior_model.py (완료)
- `POSTURE_CLASSES` dict: 6개 클래스 정의
- `MULTICLASS_ORDER`: `['standing', 'walking', 'sitting', 'running', 'lying', 'fall']`
- `BINARY_TO_MULTICLASS_MAPPING`: Y→fall, N→unknown
- `MULTICLASS_TO_BINARY_MAPPING`: 역매핑
- `DEFAULT_SUMMARY`에 `multiclass_order`, `multiclass_ready` 필드 추가
- `DEFAULT_MODEL`에 `multiclass_order`, `multiclass_ready` 필드 추가

### 2.2 training_summary.json 스키마 변경
```json
{
  "class_order": ["non-fall", "fall"],
  "multiclass_order": ["standing", "walking", "sitting", "running", "lying", "fall"],
  "multiclass_ready": false,
  "dataset": {
    "class_distribution": {
      "non-fall": 100,
      "fall": 50,
      "multiclass_distribution": {
        "standing": 0,
        "walking": 0,
        "sitting": 0,
        "running": 0,
        "lying": 0,
        "fall": 50,
        "unknown": 100
      }
    }
  }
}
```

### 2.3 HITL Feedback 메타데이터 JSON
```json
{
  "feedback_type": "analysis-validation",
  "actual_label": "N",
  "posture_class": "sitting",
  "uploaded_at": "2026-04-06 12:00:00"
}
```
- `posture_class` 필드 추가됨 (빈 문자열이면 이진 라벨만 제공된 것)

### 2.4 intake CSV 확장 (향후)
| 기존 컬럼 | 추가 컬럼 |
|-----------|----------|
| `label` (Y/N) | `posture_class` (6-class 코드) |

---

## 3. 마이그레이션 전략

### 3.1 기존 이진 라벨 데이터
| 현재 라벨 | 전환 후 | 비고 |
|-----------|--------|------|
| Y (낙상) | `fall` | 확정 |
| N (정상) | `unknown` | 세분화 필요 (standing/walking/sitting 등) |

### 3.2 단계적 전환 계획
1. **Phase 1 (현재)**: 이진 분류 유지 + 다중 클래스 메타데이터 수집 시작
   - 피드백 UI에 6-class 옵션 준비 (`multiclassFeedbackEnabled=false`)
   - 피드백 JSON에 `posture_class` 필드 저장 시작
2. **Phase 2**: 다중 클래스 라벨 데이터가 클래스별 최소 50건 확보 시
   - `multiclassFeedbackEnabled=true`로 전환
   - 행동 분류 모델을 6-class RF/XGBoost로 교체
   - `multiclass_ready=true` 설정
3. **Phase 3**: 완전 전환
   - 기존 `unknown` 라벨을 수동/자동 재라벨링
   - 이진 분류 모듈은 호환 어댑터로 유지

---

## 4. 모델 아키텍처 변경점

### 4.1 현재 (이진 분류)
- RandomForestClassifier: `predict_proba()[:, 1]` → P(fall) 스칼라
- 모션 게이트: 이진 majority vote
- 최종 점수: 0.0 ~ 1.0 스칼라

### 4.2 다중 클래스 전환 시
- RandomForestClassifier: `predict_proba()` → 6-class 확률 벡터
- Top-1 자세 + 확률 기반 신뢰도
- 낙상 확률만 별도 추출하여 기존 alert 워크플로와 호환
- `macro_f1` 평가 (클래스 불균형 대응: `class_weight='balanced_subsample'`)

### 4.3 하위 호환
- `to_binary_label(multiclass_label)` 함수로 6-class → Y/N 역변환
- 기존 API 응답 스키마에 `posture_class` 필드를 **추가** (기존 `fall_detected`, `risk_score` 유지)

---

## 5. 프론트엔드 UI 확장

### 5.1 피드백 UI (완료)
- `multiclassFeedbackEnabled=false` 시: 기존 Y/N 2버튼 그대로
- `multiclassFeedbackEnabled=true` 시: 6-class 버튼 그룹 표시
- `setFeedbackPostureClass()` → 자동으로 이진 라벨 역매핑

### 5.2 분석 결과 표시 (향후)
- 6-class 확률 바 차트
- Top-1 자세 배지: `🧍 서기 (87%)`
- 낙상 위험도는 기존 스코어 바 유지
