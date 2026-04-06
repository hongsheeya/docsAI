# FallAI 낙상 감지 모델 학습 방법 상세 분석 및 추가 자세 학습 가능성 검토

> **작성일**: 2026-04-03  
> **범위**: RF Pipeline, XGBoost v2 Person-Feature, RF-Pose, HITL 재학습 전 파이프라인 분석  
> **목적**: 현재 학습 방법론을 상세히 기술하고, 걷기·뛰기·앉기·눕기·서기 등 추가 자세 학습 가능성을 검토

---

## 목차

1. [시스템 전체 아키텍처](#1-시스템-전체-아키텍처)
2. [XGBoost v2 Person-Feature Pipeline](#2-xgboost-v2-person-feature-pipeline)
3. [RF Pipeline (RandomForest 13-Feature)](#3-rf-pipeline-randomforest-13-feature)
4. [RF-Pose Pipeline (RandomForest 25-Feature)](#4-rf-pose-pipeline-randomforest-25-feature)
5. [HITL 재학습 시스템](#5-hitl-재학습-시스템)
6. [모델 간 비교 요약](#6-모델-간-비교-요약)
7. [추가 자세 학습 가능성 검토](#7-추가-자세-학습-가능성-검토)
8. [권장 로드맵](#8-권장-로드맵)

---

## 1. 시스템 전체 아키텍처

### 1.1 3중 파이프라인 Fallback 구조

```
사용자 요청
   ├── model_type=person-feature (기본값)
   │     └── XGBoost v2 → 모델 없으면 fallback ↓
   │
   ├── model_type=rf-pipeline
   │     └── RandomForest 13-feature → 모델 없으면 fallback ↓
   │
   └── model_type=rf-pose
         └── RandomForest 25-feature → 모델 없으면 rf-pipeline으로 fallback
```

- **XGBoost v2** (기본): 정규화 좌표 기반 슬라이딩 윈도우 10-feature → `best_model.pkl`
- **RF Pipeline** (보조): 픽셀 좌표 기반 영상 전체 통계 13-feature → `rf_hitl_model.pkl`
- **RF-Pose** (실험): bbox 13 + keypoint 12 = 25-feature → `rf_pose_model.pkl` (현재 비활성)

### 1.2 추론 공통 흐름

```
입력 영상 (.mp4/.webm)
   → YOLOv8n / YOLOv8n-Pose (사람 검출)
   → 피처 추출 (파이프라인별 상이)
   → ML 모델 predict_proba()
   → 후처리 (Motion Guard, Short-clip 보정, Threshold 적용)
   → fall_detected 판정 + risk_score 반환
```

### 1.3 학습 데이터 소스

```
/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/
└── 3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상/
    ├── Y/           # 낙상(Fall) 영상
    │   ├── FY/      # 전방 낙상
    │   ├── BY/      # 후방 낙상
    │   └── SY/      # 측면 낙상
    └── N/           # 비낙상(NonFall) 영상
        └── N/
```

- **AI Hub 공개 데이터셋**: "낙상사고 위험동작 영상-센서 쌍 데이터"
- 각 영상: 약 5~30초, 다양한 카메라 각도/실내 환경
- **현재 사용 규모**: Fall ~1,000건, NonFall ~500건 (XGBoost v2 기준 최대 1,500건)

---

## 2. XGBoost v2 Person-Feature Pipeline

### 2.1 개요

| 항목 | 내용 |
|------|------|
| **모델** | XGBClassifier (scikit-learn Pipeline: StandardScaler → XGBClassifier) |
| **피처 수** | 10개 |
| **좌표계** | 정규화 좌표 (0~1) |
| **분석 단위** | 슬라이딩 윈도우 (1초 윈도우, 0.5초 스트라이드) |
| **YOLO 모델** | yolov8n.pt (detect) + ByteTrack 추적 |
| **학습 스크립트** | `scripts/retrain_xgb_v2.py` |
| **모델 저장** | `storage/training/fall-detection/fall-classifier/best_model.pkl` |

### 2.2 피처 추출 상세

#### 2.2.1 YOLO ByteTrack 추적 단계

```python
# 설정값
YOLO_MODEL = 'yolov8n.pt'       # 사람 검출 전용 (class=0)
conf = 0.30                      # 검출 confidence 임계값
iou = 0.5                        # NMS IoU
imgsz = 352                      # 입력 해상도 (속도 우선)
vid_stride = 6                   # 6프레임마다 1번 검출 (속도 최적화)
tracker = 'bytetrack.yaml'       # ByteTrack 다중 객체 추적
```

**처리 흐름**:
1. 영상을 `vid_stride=6` 간격으로 프레임 추출
2. YOLOv8n으로 사람(class=0) 검출, ByteTrack으로 track_id 할당
3. 각 검출 결과를 **정규화 좌표**로 변환:
   - `cx = (x1 + x2) / 2 / video_width`
   - `cy = (y1 + y2) / 2 / video_height`
   - `w = (x2 - x1) / video_width`
   - `h = (y2 - y1) / video_height`
4. `track_data[track_id]` = `[(frame_idx, cx, cy, w, h, conf), ...]`

#### 2.2.2 슬라이딩 윈도우 분할

```python
window_sec = 1.0    # 1초 윈도우
stride_sec = 0.5    # 0.5초 스트라이드 (50% 오버랩)
```

- 각 `track_id`별로 프레임 시퀀스를 윈도우로 분할
- 윈도우 내 최소 3개 포인트 필요 (미달 시 스킵)
- **한 영상에서 복수의 윈도우** 생성 (예: 10초 영상, 2개 트랙 → ~38개 윈도우)

#### 2.2.3 10개 피처 계산

| # | 피처명 | 수식/설명 | 물리적 의미 |
|---|--------|----------|------------|
| 1 | `center_dy` | `(cy_last - cy_first) / (경과시간_초)` | 수직 이동 속도 (정규화). 양수=하강 |
| 2 | `height_ratio` | `(h_last - h_first) / h_first` | bbox 높이 변화율. 음수=줄어듦(넘어짐) |
| 3 | `aspect_change` | `(w_last/h_last) - (w_first/h_first)` | 종횡비 변화. 양수=가로로 넓어짐 |
| 4 | `stillness` | `(이동거리<0.005인 프레임 수) / (전체-1)` | 정적 상태 비율 (0~1) |
| 5 | `floor_proximity` | `max(cy + h/2)` | 바닥 접근도. 1에 가까우면 바닥 근접 |
| 6 | `area_change` | `(area_last - area_first) / area_first` | bbox 면적 변화율 |
| 7 | `vert_horiz_ratio` | `|dy_total| / (|dx_total| + 1e-6)` | 수직/수평 이동 비율. 크면 수직 우세 |
| 8 | `max_down_speed` | `max(프레임간 cy 변화 / dt)` | 최대 하강 속도 (낙상 순간 포착) |
| 9 | `avg_conf` | `mean(confidence)` | 평균 검출 신뢰도 |
| 10 | `n_points` | 윈도우 내 추적 포인트 수 | 추적 품질 지표 |

### 2.3 학습 과정 상세 (retrain_xgb_v2.py)

#### Phase 1: 영상 수집

```python
# 기본 설정
n_fall_train = 800      # Fall 학습용
n_fall_val = 200        # Fall 검증용
n_nonfall_train = 400   # NonFall 학습용
n_nonfall_val = 100     # NonFall 검증용
seed = 42               # 재현 가능한 셔플
```

- 총 **1,500건** 영상 사용 (확장 가능)
- `random.Random(seed=42).shuffle()` 로 재현 가능한 분할

#### Phase 2: 피처 추출

- 각 영상에서 YOLO ByteTrack → 슬라이딩 윈도우 → 10개 피처
- 100건마다 진행 상황 보고 (처리 속도, ETA)
- 결과를 JSON 캐시로 저장 (`--skip-extract`로 캐시 재사용 가능)

#### Phase 3: 데이터 변환

- 영상 레벨 → **윈도우 레벨** flatten
- 한 영상의 라벨(Y/N)이 해당 영상의 모든 윈도우에 전파
- `inf/nan → 0.0` 치환
- 클래스 불균형 비율(`N건수/Y건수`) 계산 → `scale_pos_weight`에 활용

#### Phase 4: HP Grid Search + Threshold Sweep

**10가지 하이퍼파라미터 조합** 탐색:

| 설정명 | max_depth | n_estimators | learning_rate | scale_pos_weight | min_child_weight | subsample | colsample |
|--------|-----------|-------------|---------------|------------------|------------------|-----------|-----------|
| base-6-200-0.1 | 6 | 200 | 0.1 | 1.0 | 1 | 0.8 | 0.8 |
| base-6-300-0.1 | 6 | 300 | 0.1 | 1.0 | 1 | 0.8 | 0.8 |
| deep-8-300-0.05 | 8 | 300 | 0.05 | 1.0 | 1 | 0.8 | 0.8 |
| deep-8-500-0.05 | 8 | 500 | 0.05 | 1.0 | 1 | 0.8 | 0.8 |
| spw-auto | 6 | 300 | 0.1 | auto(N/Y비율) | 1 | 0.8 | 0.8 |
| spw-2.0 | 6 | 300 | 0.1 | 2.0 | 1 | 0.8 | 0.8 |
| spw-3.0 | 6 | 300 | 0.1 | 3.0 | 1 | 0.8 | 0.8 |
| reg-6-300 | 6 | 300 | 0.05 | 1.0 | 3 | 0.7 | 0.7 |
| reg-8-500 | 8 | 500 | 0.03 | 1.0 | 3 | 0.7 | 0.7 |
| spw-8-500 | 8 | 500 | 0.05 | 2.0 | 1 | 0.8 | 0.8 |

**Threshold Sweep**: 0.25 ~ 0.75 (0.01 간격, 51개 값)  
→ 10 × 51 = **510가지 조합** 평가

**최적 모델 선정 기준**:
1. `Recall ≥ 0.93` **AND** `Precision ≥ 0.70`
2. 조건 충족 조합 중 **F1 최대** 선택
3. 미달 시 → 전체에서 F1 최대로 fallback

#### Phase 5: 최종 모델 학습/저장

- 최적 HP + 전체 Train 데이터로 재학습
- `StandardScaler → XGBClassifier` Pipeline으로 joblib 저장
- 기존 모델은 `.bak.{timestamp}` 백업
- 학습 요약 JSON (`evaluation_v2.json`) 저장

### 2.4 런타임 추론 (실서비스)

#### 최종 점수 합산 공식

```
final_score = max_prob × 0.45 + mean_prob × 0.25 + fall_ratio × 0.15 + fp_boost × 0.10 + hr_boost × 0.05
```

| 항목 | 설명 |
|------|------|
| `max_prob` | 전체 윈도우 중 XGBoost 낙상 확률 최대값 |
| `mean_prob` | 전체 윈도우 평균 낙상 확률 |
| `fall_ratio` | 확률 > threshold인 윈도우 비율 |
| `fp_boost` | `floor_proximity > 0.5`일 때 선형 보정 (바닥 접근 보너스) |
| `hr_boost` | `height_ratio < -0.05`일 때 선형 보정 (높이 감소 보너스) |

#### Motion Gate (오탐 억제)

3개 조건 중 **2개 이상(majority vote)** 충족 시에만 낙상 판정 유지:
1. `max_down_speed ≥ 0.15` (하강 속도 충분)
2. `center_dy ≥ 0.03` (수직 이동 충분)
3. `pose_change`: `height_ratio ≤ -0.05` OR `aspect_change ≥ 0.05` OR `floor_proximity ≥ 0.78`

Gate 미통과 시: `score = min(score, max_prob × 0.35, mean_prob × 0.45, 0.35)` → 강제 억제

#### Threshold

- **XGBoost 전용 threshold**: `0.50` (RF와 독립)
- `fall_detected = (final_score >= 0.50)`

---

## 3. RF Pipeline (RandomForest 13-Feature)

### 3.1 개요

| 항목 | 내용 |
|------|------|
| **모델** | RandomForestClassifier (직접, scaler 없음) |
| **피처 수** | 13개 |
| **좌표계** | 원본 픽셀 좌표 |
| **분석 단위** | 영상 전체 통계 (윈도우 분할 없음) |
| **YOLO 모델** | yolov8n-pose.pt (detect + keypoints) |
| **학습** | HITL 재학습 (`retrain_rf_pipeline()`) |
| **모델 저장** | `storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl` |

### 3.2 피처 추출 상세

#### 3.2.1 YOLO-Pose 검출 단계

```python
_RF_YOLO_MODEL = 'yolov8n-pose.pt'   # Pose 모델 (bbox + 17 keypoints)
_RF_TARGET_FPS = 2                     # 초당 2프레임 (실시간은 4fps)
_RF_CONF_THRES = 0.25                  # 검출 confidence (실시간은 0.15)
_RF_YOLO_IMGSZ = 640                   # 입력 해상도 (RF는 정확도 우선)
```

**처리 흐름**:
1. 영상의 총 프레임 수에서 `target_fps` 비율로 프레임 균등 샘플링
2. 각 프레임에서 YOLOv8n-Pose predict (추적 아님, 단일 프레임 검출)
3. 각 프레임에서 **가장 큰 면적의 사람 bbox** 선택 (main person)
4. 픽셀 좌표 그대로 사용 (원본 크기로 역변환)

#### 3.2.2 13개 피처 계산

| # | 피처명 | 수식/설명 | 물리적 의미 |
|---|--------|----------|------------|
| 1 | `detection_rate` | `검출된 프레임 수 / 전체 샘플링 프레임 수` | 영상 내 사람 가시 비율 (0~1) |
| 2 | `center_y_mean` | `mean(center_y)` (px) | 사람 중심점 Y좌표 평균 |
| 3 | `center_y_std` | `std(center_y)` (px) | Y좌표 분산 → 수직 이동 정도 |
| 4 | `height_mean` | `mean(bbox_height)` (px) | 평균 bbox 높이 |
| 5 | `height_std` | `std(bbox_height)` (px) | 높이 변동 → 자세 변화 정도 |
| 6 | `aspect_ratio_mean` | `mean(width/height)` | 평균 종횡비 (넘어지면 증가) |
| 7 | `aspect_ratio_std` | `std(width/height)` | 종횡비 변동 |
| 8 | `delta_y_mean` | `mean(clip(diff(center_y), lower=0))` (px) | 프레임 간 하방 이동 평균 |
| 9 | `delta_y_max` | `max(clip(diff(center_y), lower=0))` (px) | **최대 하방 변위** (낙상 핵심 지표) |
| 10 | `delta_height_mean` | `mean(|diff(height)|)` (px) | 높이 절대 변화 평균 |
| 11 | `delta_width_mean` | `mean(|diff(width)|)` (px) | 너비 절대 변화 평균 |
| 12 | `delta_y_accel_max` | `max(diff(delta_y))` | 하강 가속도 최대 (급락 감지, v4 추가) |
| 13 | `final_height_ratio` | `mean(height[-3:]) / mean(height)` | 최종 자세 높이 비율 (v4 추가, <1이면 넘어짐) |

**핵심 차이점**:
- `delta_y`는 `clip(lower=0)` 적용 → **하강 방향만** 캡처 (상승은 무시)
- 픽셀 좌표 → 카메라 거리/해상도에 따라 값 스케일 변동
- 영상 전체 통계 → 단일 피처 벡터/영상 (윈도우 분할 없음)

### 3.3 학습 과정 (HITL 재학습)

```python
# 모델 설정
RandomForestClassifier(
    n_estimators=200,
    random_state=42,
    n_jobs=-1,
    class_weight='balanced_subsample'  # 클래스 불균형 자동 보정
)
```

**학습 데이터**: `storage/training/fall-detection/intake/{Y,N}/` 디렉토리의 피드백 영상

**교차 검증**:
- 클래스별 최소 3건 → **3-Fold Stratified CV**
- 클래스별 최소 2건 → **2-Fold Stratified CV**
- 미달 시 학습 중단

**평가 메트릭**: Accuracy, Precision, Recall, F1, ROC-AUC

### 3.4 런타임 후처리

#### Motion Guard (4단계)

```
1. Stationary Guard (모든 움직임 지표 낮음)
   → score = min(score, 0.10)

2. Aspect-ratio-only Guard (종횡비만 변동, Y 이동 없음)
   → score = min(score, 0.20)

3. Realtime Guard (실시간 4초 청크 전용)
   조건: final_height_ratio > 0.45 AND delta_y_max < 30 AND center_y_std < 35
   → score = min(score, 0.25)

4. Moderate-motion Dampener (중간 점수 억제)
   조건: score < 0.70 AND delta_y_max < 25 AND fhr > 0.50 AND accel < 12
   → score = min(score, 0.40)
```

Short-clip(검출 <10프레임) 시 모든 임계값에 **×0.7 승수** (더 엄격)

#### Short-clip 적응형 Threshold

```python
_SHORT_CLIP_N_FRAMES = 10      # 이하면 short-clip
_SHORT_CLIP_THRESHOLD_MAX = 0.72   # n=3일 때 최대 threshold
_SHORT_CLIP_MIN_FRAMES = 3     # 미만이면 insufficient → 자동 '정상'

# 선형 보간
effective_threshold = 0.72 - (n_frames - 3) × (0.72 - 0.60) / 7
```

| 검출 프레임 | effective_threshold | 판단 |
|-------------|-------------------|------|
| < 3 | N/A | insufficient → 자동 '정상' |
| 3 | 0.72 | 매우 높은 확률만 낙상 |
| 5 | 0.686 | |
| 7 | 0.651 | |
| 10+ | 0.60 | 기본 threshold |

---

## 4. RF-Pose Pipeline (RandomForest 25-Feature)

### 4.1 개요

RF Pipeline 13-feature에 **12개 키포인트 파생 피처**를 추가한 확장 버전.

```
25개 피처 = 13 (bbox 통계) + 12 (keypoint 파생)
```

### 4.2 키포인트 파생 피처 (12개)

COCO 17-keypoint에서 6가지 물리적 특성을 추출, 각각 mean/max(또는 min)으로 2개 통계:

| # | 피처명 | 사용 관절 | 계산 방법 | 물리적 의미 |
|---|--------|----------|----------|------------|
| 14 | `body_tilt_angle_mean` | 양어깨 중점 ↔ 양엉덩이 중점 | 수직선 대비 기울기 각도(°) 평균 | 몸 기울어짐 정도 |
| 15 | `body_tilt_angle_max` | 〃 | 최대 기울기 각도 | 가장 많이 기울어진 순간 |
| 16 | `height_ratio_mean` | 코 ↔ 발목 | `|nose_y - ankle_y| / vid_height` 평균 | 서 있는 높이 비율 |
| 17 | `height_ratio_min` | 〃 | 최소값 | 가장 낮아진 순간(쓰러짐) |
| 18 | `knee_bend_angle_mean` | 엉덩이-무릎-발목 | 3점 각도(°) 평균 | 무릎 굽힘 정도 |
| 19 | `knee_bend_angle_min` | 〃 | 최소 각도 | 가장 많이 구부린 순간 |
| 20 | `horizontal_spread_mean` | 유효 관절 전체 | x좌표 std 평균 | 좌우 팔다리 벌림 |
| 21 | `horizontal_spread_max` | 〃 | 최대 std | 가장 벌린 순간(누운 자세) |
| 22 | `center_descent_speed_mean` | 양어깨+양엉덩이 4점 | 프레임 간 중심 y 변화율 평균 | 몸 중심 하강 속도 |
| 23 | `center_descent_speed_max` | 〃 | 최대 하강 속도 | 낙상 순간 급락 |
| 24 | `pose_change_rate_mean` | 17관절 전체 | 연속 프레임 17관절 벡터 코사인 비유사도 평균 | 자세 변화의 전반적 크기 |
| 25 | `pose_change_rate_max` | 〃 | 최대 비유사도 | 가장 급격한 자세 변화 |

**키포인트 confidence 임계값**: `KP_CONF_MIN = 0.3` (미달 시 해당 프레임 해당 피처 스킵)

### 4.3 현재 상태

- **코드**: 완전 구현 (추론 + HITL 재학습)
- **모델 파일**: 미생성 (학습 데이터 부족)
- **Fallback**: 모델 미존재 시 자동으로 RF Pipeline으로 대체
- **활성화 조건**: `intake/` 디렉토리에 클래스별 최소 2건 이상 피드백 축적 후 HITL 재학습

---

## 5. HITL 재학습 시스템

### 5.1 피드백 수집 흐름

```
사용자 분석 → 결과 확인 → 👍 맞아요 / 👎 틀려요 선택
→ (틀렸으면) 실제 정답 라벨 Y/N 선택 + 메모
→ "피드백 저장" 또는 "피드백 + HITL 재학습" 클릭
```

**저장 구조**:
```
storage/training/fall-detection/intake/
├── Y/                              # 낙상으로 확정된 영상
│   ├── feedback-{saved_name}.mp4   # 원본 영상 복사본
│   └── feedback-{saved_name}.mp4.json  # 메타데이터
└── N/                              # 정상으로 확정된 영상
    ├── feedback-{saved_name}.mp4
    └── feedback-{saved_name}.mp4.json
```

**메타데이터 JSON 예시**:
```json
{
    "original_saved_name": "20260403_120500_abc123_video.mp4",
    "predicted_label": "Y",
    "feedback_status": "incorrect",
    "actual_label": "N",
    "final_label": "N",
    "note": "빠르게 앉는 동작이었음",
    "timestamp": "2026-04-03T12:06:00"
}
```

### 5.2 재학습 트리거

`retrain=True` 시 순차적으로 4개 모델 재학습:
1. **Baseline 모델** (YOLO 분류 기반)
2. **Behavior 모델** (행동 분류)
3. **RF Pipeline** → `retrain_rf_pipeline()`
4. **RF-Pose** → `retrain_rf_pose_pipeline()`

### 5.3 재학습 안전장치

| 안전장치 | 설명 |
|---------|------|
| **Atomic Write** | `tempfile → os.replace()` 패턴으로 중간 파일 부재 방지 |
| **서버 동기화** | 새 모델을 `rf_model_server.pkl`에도 자동 복사 |
| **캐시 무효화** | 클래스 레벨 `_rf_model_cache = None` 초기화 |
| **최소 데이터** | 클래스별 최소 2건 미달 시 학습 중단 |
| **CV 검증** | 2~3 Fold Stratified CV로 과적합 감시 |

---

## 6. 모델 간 비교 요약

| 항목 | XGBoost v2 | RF Pipeline | RF-Pose |
|------|-----------|-------------|---------|
| **피처 수** | 10 | 13 | 25 |
| **좌표계** | 정규화 (0~1) | 픽셀 (px) | 픽셀 (px) |
| **분석 단위** | 슬라이딩 윈도우 (1s) | 영상 전체 | 영상 전체 |
| **YOLO 모델** | yolov8n (detect) | yolov8n-pose | yolov8n-pose |
| **추적 방식** | ByteTrack 다중객체 | 프레임별 최대 면적 | 프레임별 최대 면적 |
| **학습 데이터** | 1,500건 영상 | HITL 피드백 | HITL 피드백 |
| **학습 방식** | HP Grid Search | 단일 설정 | 단일 설정 |
| **Threshold** | 0.50 | 0.60 (적응형) | 0.60 (적응형) |
| **Motion Guard** | Majority Vote (3조건 중 2개) | 4단계 가드 체인 | RF와 동일 |
| **현재 역할** | **기본(메인)** | **보조** | **실험(비활성)** |
| **Scaler** | StandardScaler (Pipeline) | 없음 | 없음 |

---

## 7. 추가 자세 학습 가능성 검토

### 7.1 현재 시스템의 분류 범위

현재 시스템은 **이진 분류(Fall vs Non-Fall)**만 수행합니다:
- 라벨: `Y`(낙상) / `N`(비낙상)
- 출력: `fall_detected` (boolean) + `risk_score` (0~1 연속값)

"걷기, 뛰기, 앉기, 눕기, 서기" 등 세부 자세/행동을 분류하려면 **다중 클래스 분류**로의 전환이 필요합니다.

### 7.2 자세별 학습 가능성 분석

#### 7.2.1 걷기 (Walking)

| 항목 | 분석 |
|------|------|
| **피처 활용도** | ★★★★☆ — 높음 |
| **XGBoost 10-feature** | `center_dy` 양수 지속, `stillness` 낮음, `floor_proximity` 중간, `max_down_speed` 중간 |
| **RF 13-feature** | `delta_y_mean` 작음, `center_y_std` 높음, `aspect_ratio_std` 낮음 |
| **Pose 12-feature** | `knee_bend_angle_mean` 130~160° 주기적, `body_tilt_angle` 낮음, `pose_change_rate` 일정 |
| **구분 난이도** | 쉬움 — 걷기는 일정한 수직 이동 패턴이 특징적 |
| **필요 데이터** | 다양한 속도의 걷기 영상 300~500건 |
| **혼동 가능 자세** | 뛰기 (속도 차이), 서기→걷기 전환 구간 |

#### 7.2.2 뛰기 (Running)

| 항목 | 분석 |
|------|------|
| **피처 활용도** | ★★★★☆ — 높음 |
| **XGBoost 10-feature** | `center_dy` 큼, `max_down_speed` 높음 (상하 반동), `stillness` 매우 낮음 |
| **RF 13-feature** | `delta_y_max` 크고 반복적, `height_std` 높음 (상하 진동) |
| **Pose 12-feature** | `knee_bend_angle_min` 낮음 (70~100°), `center_descent_speed_max` 높음, `pose_change_rate` 높고 주기적 |
| **구분 난이도** | 중간 — 걷기와 연속 스펙트럼이라 경계가 모호 |
| **필요 데이터** | 조깅~전력질주 포함 200~400건 |
| **혼동 가능 자세** | 빠른 걷기, 낙상 직전 이동 |

#### 7.2.3 앉기 (Sitting Down)

| 항목 | 분석 |
|------|------|
| **피처 활용도** | ★★★☆☆ — 중간 (낙상과 혼동 위험) |
| **XGBoost 10-feature** | `center_dy` 양수 (하강), `height_ratio` 음수 (높이 감소), `floor_proximity` 중간→높음 |
| **RF 13-feature** | `delta_y_max` 중간, `final_height_ratio` 0.5~0.8, `aspect_ratio_std` 중간 |
| **Pose 12-feature** | `knee_bend_angle_min` 낮음 (60~100°), `body_tilt_angle` 낮음 (~0~30°), `height_ratio_min` 중간 |
| **구분 난이도** | **어려움** — 빠르게 앉기는 낙상과 피처가 유사 |
| **필요 데이터** | 의자에 앉기, 바닥에 앉기, 빠르게 주저앉기 등 400~600건 |
| **혼동 가능 자세** | **낙상** (가장 큰 혼동), 눕기 전환 |
| **핵심 구분 포인트** | 앉기는 `center_descent_speed` 일정하고 `body_tilt_angle` 낮음 (수직 유지). 낙상은 `body_tilt_angle_max` 급등 + 급가속 후 급정지 |

> ⚠️ **앉기↔낙상 혼동**은 현재 시스템에서도 주요 오판 원인입니다. Motion Guard의 `realtime guard`가 바로 이 혼동을 억제하기 위해 추가된 것입니다.

#### 7.2.4 눕기 (Lying Down)

| 항목 | 분석 |
|------|------|
| **피처 활용도** | ★★☆☆☆ — 낮음 (정적 상태 구분 어려움) |
| **XGBoost 10-feature** | `stillness` 매우 높음, `floor_proximity` 높음, `height_ratio` 큰 음수 |
| **RF 13-feature** | `aspect_ratio_mean` 높음 (가로 방향 bbox), `height_mean` 낮음, `detection_rate` 변동 |
| **Pose 12-feature** | `body_tilt_angle_max` 매우 높음 (60~90°), `horizontal_spread_max` 높음 (사지 펼침), `height_ratio_min` 매우 낮음 |
| **구분 난이도** | **어려움** — 누워 있는 상태는 낙상 후 상태와 거의 동일 |
| **필요 데이터** | 침대/바닥 자발적 눕기, 스트레칭, 요가 등 300~500건 |
| **혼동 가능 자세** | **낙상 후 상태** (가장 큰 혼동), 앉기→눕기 전환 |
| **핵심 구분 포인트** | 눕기는 `center_descent_speed`가 점진적이고 일정, `delta_y_accel_max` 낮음. 낙상은 급가속→급정지 패턴, `delta_y_accel_max` 매우 높음 |

> ⚠️ **눕기↔낙상 후 상태 구분**은 가장 도전적인 문제입니다. (1) "의도적으로 눕기"와 (2) "낙상 후 바닥에 있기"는 최종 상태가 거의 동일하며, **전환 과정(속도/가속도)**만으로 구분해야 합니다.

#### 7.2.5 서기 (Standing)

| 항목 | 분석 |
|------|------|
| **피처 활용도** | ★★★★★ — 매우 높음 |
| **XGBoost 10-feature** | `stillness` 높음, `center_dy` ~0, `height_ratio` ~0 |
| **RF 13-feature** | `center_y_std` 매우 낮음, `height_std` 낮음, `delta_y_max` 매우 낮음 |
| **Pose 12-feature** | `body_tilt_angle` 매우 낮음 (~0~10°), `knee_bend_angle` 높음 (150~180°), `height_ratio` 높음 |
| **구분 난이도** | 매우 쉬움 — 정적 + 수직 자세라는 명확한 패턴 |
| **필요 데이터** | 다양한 서 있는 자세 200~300건 |
| **혼동 가능 자세** | 느린 걷기 시작/종료 |

### 7.3 종합 평가

| 자세 | 학습 난이도 | 기존 피처 적합도 | 낙상 혼동 위험 | 권장 우선순위 |
|------|-----------|----------------|---------------|-------------|
| **서기** | ★☆☆☆☆ 매우 쉬움 | ★★★★★ | 낮음 | 1 (쉬움) |
| **걷기** | ★★☆☆☆ 쉬움 | ★★★★☆ | 낮음 | 2 |
| **뛰기** | ★★★☆☆ 중간 | ★★★★☆ | 중간 | 3 |
| **앉기** | ★★★★☆ 어려움 | ★★★☆☆ | **높음** | 4 (낙상 혼동) |
| **눕기** | ★★★★★ 매우 어려움 | ★★☆☆☆ | **매우 높음** | 5 (가장 도전적) |

### 7.4 다중 클래스 전환 시 필요한 변경사항

#### 7.4.1 라벨 체계 변경

```
현재: Y(Fall) / N(NonFall) — 이진 분류
변경: fall / walk / run / sit / lie / stand — 6클래스 분류
```

#### 7.4.2 모델 구조 변경

**XGBoost v2**:
```python
# 현재 (이진)
XGBClassifier(objective='binary:logistic', ...)

# 변경 (다중 클래스)
XGBClassifier(
    objective='multi:softprob',
    num_class=6,
    eval_metric='mlogloss',
    ...
)
```

**RF Pipeline**:
```python
# RandomForest는 다중 클래스 기본 지원
RandomForestClassifier(n_estimators=200, ...)
# predict_proba() → 6개 클래스별 확률 반환
```

#### 7.4.3 피처 보강 필요성

현재 피처의 한계:
- **시간적 패턴 부족**: 현재 피처는 대부분 mean/max/std 등 통계값 → 시간적 순서 정보 손실
- **앉기↔낙상 구분**: 기존 10/13/25개 피처만으로는 부족
- **추가 필요 피처**:

| 추가 피처 후보 | 설명 | 구분에 도움되는 자세 쌍 |
|--------------|------|---------------------|
| `descent_duration` | 하강 시작→정지까지 소요 시간 | 앉기/눕기 vs 낙상 |
| `oscillation_count` | Y좌표 방향 전환 횟수 | 걷기/뛰기 vs 정적 자세 |
| `speed_std` | 프레임 간 이동 속도 분산 | 걷기(일정) vs 뛰기(변동) |
| `post_descent_stillness` | 최대 하강 이후 정지 비율 | 앉기(정지) vs 걷기(계속 이동) |
| `upper_body_motion` | 상체(어깨~엉덩이) 이동 vs 하체 비율 | 앉기(하체 우세) vs 낙상(전신) |

#### 7.4.4 학습 데이터 확보 방안

| 방법 | 설명 | 예상 규모 |
|------|------|----------|
| **AI Hub 기존 데이터** | 같은 데이터셋 내 비낙상 영상의 행동 세분화 | NonFall ~500건 재분류 |
| **AI Hub 추가 데이터셋** | "실내 행동 인식" 등 유사 데이터셋 | 1,000~3,000건 |
| **자체 촬영** | 같은 환경에서 5가지 자세 직접 촬영 | 자세별 100~200건 |
| **웹캠 HITL** | 실시간 모드로 촬영 → 즉시 라벨링 | 점진적 축적 |

#### 7.4.5 코드 변경 범위

| 대상 | 변경 내용 | 난이도 |
|------|----------|--------|
| `video_analysis.py` | `fall_detected` → 다중 클래스 결과 구조 | 큼 |
| `retrain_xgb_v2.py` | 다중 클래스 라벨 처리 + `multi:softprob` + 클래스별 threshold | 중간 |
| `view.ts` | 위험도 표시 → 자세별 확률 표시 UI | 큼 |
| `view.pug` | 결과 카드 → 자세 분류 결과 표시 | 중간 |
| HITL 피드백 | 2선택(Y/N) → 6선택(자세 분류) | 중간 |
| Motion Guard | 자세별 오판 패턴에 맞게 재설계 | 큼 |
| 파이프라인/매뉴얼 | 다중 클래스 설명 업데이트 | 작음 |

### 7.5 현실적 권장사항

#### 단기 전략 (현 구조 유지)
1. **앉기/눕기 오판 방지 강화**: 현재 Motion Guard 고도화 (별도 클래스 추가 없이)
2. **Behavior 모델 활성화**: 기존 코드의 `_predict_behavior_from_runtime()` 개선
3. **RF-Pose 활성화**: 25-feature로 앉기/눕기 구분력 향상 테스트

#### 중기 전략 (다중 클래스 확장)
1. **점진적 전환**: Fall/NonFall 이진 분류는 유지하면서, 별도 "자세 분류" 모델 추가
2. **2단계 파이프라인**: `1단계: 위험 판정(이진)` → `2단계: 자세 분류(6클래스)`
3. 1단계에서 "위험"이면 긴급 경보, 2단계에서 구체적 자세 정보 제공

---

## 8. 권장 로드맵

```
Phase 1 (즉시 가능):
  ├── RF-Pose 25-feature 모델 학습 데이터 축적 (HITL)
  ├── 서기/걷기 라벨 추가 (가장 쉬운 것부터)
  └── Behavior 모델 통합 테스트

Phase 2 (1~2주):
  ├── AI Hub 추가 데이터셋 확보
  ├── 뛰기/앉기 라벨 추가
  ├── 피처 보강 (descent_duration, oscillation_count 등)
  └── XGBoost multi:softprob 전환 실험

Phase 3 (2~4주):
  ├── 눕기 라벨 추가 (가장 어려움)
  ├── 2단계 파이프라인 구현 (위험판정 → 자세분류)
  ├── UI 다중 자세 표시 구현
  └── 종합 평가 + Motion Guard 재설계
```

---

> **결론**: 현재 피처 세트로 **서기·걷기·뛰기**는 비교적 쉽게 학습 가능합니다. **앉기·눕기**는 낙상과의 혼동이 핵심 난제이며, 시간적 패턴 피처 보강 + 충분한 학습 데이터가 필수입니다. 2단계 파이프라인(위험판정 → 자세분류) 접근이 가장 현실적인 확장 전략입니다.
