# XG-Posture 행동분류 feature 중요도 및 연관성 정리

- **ID**: 001
- **날짜**: 2026-04-15
- **유형**: 문서 업데이트

## 작업 목적
현재 XG-Posture 6-class 모델이 어떤 특징을 중심으로 동작하는지, 그리고 각 행동 분류가 어떤 feature 조합으로 구분되는지를 운영 관점에서 정리했다.

> 주의: XGBoost는 class별 feature importance를 직접 제공하지 않으므로, 아래 정리는 `training_summary.json`의 전역 feature importance와 `video_analysis.py`의 후처리/휴리스틱 규칙, 그리고 현재 런타임 동작을 함께 해석한 결과다.

## 1. 모델이 가장 크게 보는 전역 feature
상위 중요 feature는 다음 순서로 해석할 수 있다.

1. `stillness` — **0.2102**
2. `pose_change_mean` — **0.1221**
3. `pose_spread_max` — **0.0854**
4. `spread_after_descent` — **0.0539**
5. `pose_spread_mean` — **0.0504**
6. `floor_proximity` — **0.0498**
7. `tilt_height_collapse` — **0.0420**
8. `tilt_change_duration` — **0.0361**
9. `avg_conf` — **0.0341**
10. `pose_change_max` — **0.0289**
11. `pose_tilt_mean` — **0.0288**
12. `pose_knee_bend_mean` — **0.0264**
13. `post_floor_stability` — **0.0203**
14. `pose_height_ratio_mean` — **0.0189**
15. `floor_proximity_slope` — **0.0174**

즉, 이 모델은 크게 보면 아래 세 축을 본다.

- **정적 자세 축**: `stillness`, `pose_tilt_mean`, `pose_height_ratio_mean`, `pose_knee_bend_mean`
- **동적 변화 축**: `pose_change_mean`, `pose_change_max`, `tilt_change_duration`, `descent_duration`
- **바닥 접근/붕괴 축**: `floor_proximity`, `spread_after_descent`, `tilt_height_collapse`, `floor_proximity_slope`, `floor_contact_ratio`

## 2. 행동별 핵심 해석

### 2.1 서기(`stand`)
서기는 **가장 안정적이고, 상체가 비교적 수직이며, 무릎 굽힘이 적고, 키 비율이 높은 상태**를 본다.

핵심 연관 feature:
- `stillness` 높음
- `pose_tilt_mean` 낮음
- `pose_height_ratio_mean` 높음
- `pose_knee_bend_mean` 낮음
- `avg_conf`가 너무 낮지 않아야 함

실무 해석:
- 사람이 거의 움직이지 않으면서 upright posture를 유지하면 서기로 분류된다.
- 앉기와의 구분은 주로 **무릎 굽힘 + 상체 기울기 + 높이 비율**에서 갈린다.
-
### 2.2 걷기(`walk`)
걷기는 **정지하지 않고, 주기적인 아래/위 움직임과 다리 리듬이 있는 상태**를 본다.

핵심 연관 feature:
- `stillness` 낮음
- `center_y_periodicity`
- `knee_angle_cycle_strength`
- `step_period_est`
- `speed_std`
- `upper_body_motion`

실무 해석:
- 걷기는 단순한 이동이 아니라 **리듬성**이 중요하다.
- 서기와의 차이는 “움직임이 있느냐”이고, 뛰기와의 차이는 “그 움직임이 얼마나 빠르고 강한가”이다.

### 2.3 뛰기(`run`)
뛰기는 **걷기보다 훨씬 강한 속도 변화와 리듬**을 본다.

핵심 연관 feature:
- `stillness` 매우 낮음
- `speed_std` 높음
- `center_y_periodicity` 높음
- `step_period_est`가 더 짧음
- `upper_body_motion` 높음
- `knee_angle_cycle_strength`도 보조 신호로 작동

실무 해석:
- 걷기와 뛰기의 차이는 거의 항상 **속도/주기 차이**로 잡힌다.
- 모델은 “움직임이 많다”보다 “빠르고 주기적인 움직임이 있다”를 뛰기의 기준으로 본다.

### 2.4 앉기(`sit`)
앉기는 **정지 상태에 가깝지만 무릎이 접히고, 상체는 완전히 눕지 않은 상태**를 본다.

핵심 연관 feature:
- `stillness` 높음
- `pose_knee_bend_mean` 높음
- `pose_tilt_mean` 낮거나 중간
- `pose_height_ratio_mean` 서기보다 낮음
- `floor_proximity`는 눕기보다 약함

실무 해석:
- 앉기는 서기와 달리 **무릎 굽힘**이 중요하고, 눕기와 달리 **상체 기울기와 바닥 밀착 증거가 부족**해야 한다.
- 현재 후처리도 앉기 판단을 먼저 살리고, 눕기는 더 강한 기울기/바닥 증거가 있어야 넘어가도록 조정되어 있다.

### 2.5 눕기(`lie`)
눕기는 **상체가 크게 기울고, 키 비율이 낮아지며, 바닥과의 접촉/근접이 강하게 나타나는 상태**를 본다.

핵심 연관 feature:
- `pose_tilt_mean` / `pose_tilt_max` 높음
- `pose_height_ratio_mean` / `pose_height_ratio_min` 낮음
- `floor_proximity` 높음
- `floor_contact_ratio` 높음
- `pose_spread_mean`, `pose_spread_max`, `spread_after_descent` 높음
- `tilt_height_collapse` 높음

실무 해석:
- 앉기와 눕기의 핵심 차이는 **상체 기울기 + 바닥 밀착 + 높이 붕괴**의 조합이다.
- 현재 런타임 보정도 이 구간을 더 타이트하게 잡도록 되어 있다.

### 2.6 낙상(`fall`)
낙상은 **갑작스러운 자세 붕괴와 수직 방향 하강**을 본다.

핵심 연관 feature:
- `pose_change_mean` 매우 중요
- `tilt_change_duration`
- `descent_duration`
- `max_down_speed`
- `floor_proximity_slope`
- `collapse_impulse`
- `height_drop_persistence`
- `post_floor_stability`

실무 해석:
- 낙상은 단순히 누워 있는 것과 다르다.
- 모델은 “결과 자세”보다 **변화 과정**을 더 중요하게 본다.
- 즉, 급격한 하강과 붕괴가 있었는지가 핵심이며, 눕기보다 동적인 특징이 더 강해야 낙상으로 간다.

## 3. 행동 간 구분 기준 요약

### 서기 vs 걷기
- 서기: `stillness` 높음, `pose_tilt_mean` 낮음
- 걷기: `center_y_periodicity`, `knee_angle_cycle_strength`, `step_period_est`가 살아남

### 걷기 vs 뛰기
- 걷기: 주기성은 있지만 속도 변화가 완만
- 뛰기: `speed_std`와 리듬이 더 강하고 `step_period_est`가 짧음

### 서기 vs 앉기
- 서기: 무릎이 덜 접힘, 상체 수직
- 앉기: `pose_knee_bend_mean`이 높고, 높이 비율이 낮아짐

### 앉기 vs 눕기
- 앉기: 상체가 비교적 upright, 바닥 밀착 약함
- 눕기: `pose_tilt_mean`/`pose_tilt_max` 높고 `floor_proximity`/`floor_contact_ratio`가 강함

### 눕기 vs 낙상
- 눕기: 결과 자세 중심
- 낙상: `pose_change_mean`, `collapse_impulse`, `descent_duration` 같은 **변화 과정** 중심

## 4. 운영 관점에서의 결론
현재 posture 모델은 단순히 “어떤 자세를 하고 있나”만 보는 것이 아니라 다음을 함께 본다.

- **정지/움직임 여부**: `stillness`
- **몸의 기울기**: `pose_tilt_mean`, `pose_tilt_max`
- **몸의 높이 붕괴 여부**: `pose_height_ratio_mean`, `pose_height_ratio_min`
- **관절 접힘**: `pose_knee_bend_mean`
- **바닥 근접/접촉**: `floor_proximity`, `floor_contact_ratio`
- **자세 변화의 급격함**: `pose_change_mean`, `tilt_change_duration`, `descent_duration`
- **동작 리듬**: `center_y_periodicity`, `knee_angle_cycle_strength`, `step_period_est`

즉, 한 줄로 요약하면:

- **서기/걷기/뛰기**는 “움직임의 리듬과 속도”
- **앉기/눕기**는 “상체 기울기와 하체 접힘, 바닥 밀착”
- **낙상**은 “급격한 붕괴와 하강 과정”

## 5. 참고 파일
- `storage/training/fall-detection/xg-posture/training_summary.json`
- `src/model/struct/video_analysis.py`

---

2026-04-15
