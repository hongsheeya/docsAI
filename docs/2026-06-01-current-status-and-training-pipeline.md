# FallAI 현재 개발 현황 및 학습 파이프라인

> 기준일: 2026-06-02
> 코드 루트: `/opt/app/project/main`
> 데이터 루트: `/opt/app/datasets`
> 운영 모델 루트: `/opt/app/storage/training/fall-detection`

이 문서는 2026-06-02 기준으로 실제 적용된 모델, 학습 산출물, 남은 후보/보류 항목을 분리해 정리한다. 발표자료와 `/pipeline`, `/manual` 설명의 기준 문서로 사용한다.

---

## 1. 개발현황 요약

| 영역 | 현재 상태 | 적용 여부 | 핵심 수치/근거 |
|---|---|---|---|
| 낙상 최종 판정 | RF-Fall v2 occlusion-aware | 적용 완료 | 1,592 samples, 65 features, best-F1 0.9337, confirm F1 0.9302 |
| 행동/자세 분류 | XG-Posture 5-class | 적용 완료 | 8,181 windows, 105 features, sequence CV macro F1 0.9431 |
| 하체 가림 보조 | XG-Posture occlusion auxiliary | 보조 모델 적용 | ExtraTrees balanced, 105 features, Group CV macro F1 0.8657 |
| 표정/상태 보조 | AI-Hub 82 + 173 MobileNetV3 | 보조 근거 적용 | AI-Hub 82 macro F1 0.6198, AI-Hub 173 macro F1 0.9054 |
| 실시간 청크 | 4초 창 + 2초 stride 중첩 큐 | 적용 완료 | 경계 이벤트 누락 방지, RTT 증가 시 큐 적체 표시 |
| 프라이버시 표시 | skeleton/raw 전환 | 적용 완료 | 기본 skeleton, 관리자 raw 전환 가능 |
| YOLO 최신화 | YOLOv8n 유지, YOLO11 shadow 후보 | 보류/검증 지속 | YOLOv8n KP 93.06%, YOLO11n KP 91.67% |
| SHAP | 설명/감사 도구 | 운영 UI에는 미적용 | RF/XG-Posture feature attribution 산출 계획 |

AI-Hub 82 연속 학습 감독기는 2026-06-02 현재 백그라운드에서 진행 중이며, active macro F1 0.6198보다 개선된 후보가 나올 때만 승격한다. AI-Hub 173 v4는 macro F1 0.8982에서 0.9054로 개선되어 승격됐다.

---

## 2. 적용된 운영 파이프라인

```text
영상 업로드 / 실시간 WebM 청크
  -> 프레임 샘플링
     - 실시간: 4초 창을 2초 간격으로 중첩, 4fps 기준 최대 16프레임
     - 업로드: 같은 4초/2초 중첩 정책으로 분할 로그 생성
  -> YOLOv8n-pose
     - 사람 bbox
     - COCO-17 keypoint
     - keypoint visibility
  -> 공유 시계열 생성
     - bbox 중심/높이/면적/종횡비
     - skeleton 기울기/관절/가림 지표
     - 프레임 간 이동량/속도/가속도
  -> 1차 RF-Fall v2
     - fall / non-fall 최종 판정
     - threshold sweep 기반 suspect/confirm 운영
  -> 2차 XG-Posture
     - stand / walk / run / sit / lie 행동 설명
     - 비낙상 또는 설명 레이어로 사용
  -> 하체가림 보조 모델
     - lower-body visibility가 낮은 구간에서 stand/sit/lie 보정
  -> 표정/상태 보조
     - 실제 얼굴 검출 시에만 표정/상태 근거 사용
     - 얼굴 미검출이면 감정 라벨을 버리고 보조 점수 0
  -> LLM 설명 보조
     - 모델 evidence를 자연어로 요약
     - 최종 판정을 대체하지 않음
  -> UI/로그/알림
```

운영 원칙은 명확하다.

- 낙상/비낙상은 먼저 RF-Fall v2가 판단한다.
- 행동분류는 낙상 판정을 대체하지 않고 `왜 그렇게 봤는지`를 설명한다.
- 하체가 보이지 않는다고 무조건 미확인으로 보내지 않고, 상체/bbox/visibility 근거로 보조 판단한다.
- 표정 모델은 낙상 모델이 아니라 상태 보조 근거다.
- 얼굴이 안 보이는 경우에는 `불안` 같은 감정 라벨을 만들지 않는다.

---

## 3. 데이터 확보 및 사용 현황

| 데이터 | 위치 | 사용 목적 | 현재 역할 |
|---|---|---|---|
| AI-Hub 71641 낙상/비낙상 | `/opt/app/datasets/fall_classification/aihubs_71641` | RF-Fall v2 학습/검증 | 운영 낙상 모델 학습 반영 |
| AI-Hub 71461 행동분류 | `/opt/app/datasets/action_behavior/aihub_71461` | stand/sit/lie 보강 | XG-Posture feature row 구성 |
| AI-Hub 61 사람동작 2020 | `/opt/app/datasets/action_behavior/aihub_61_person_action_2020` | walk/run/sit/lie sequence | XG-Posture 보행/달리기 보강 |
| AI-Hub 82 한국인 감정 | `/opt/app/datasets/facial_state/aihub_82_korean_emotion` | 표정 상태 보조 | 얼굴 감정 7-class 모델 학습 |
| AI-Hub 173 운전자 상태 | `/opt/app/datasets/facial_state/aihub_173_driver_state` | 졸림/하품/주의저하 | 상태 보조 5-class 모델 학습 |
| AI-Hub 71785 안면 랜드마크 | `/opt/app/datasets/facial_state/aihub_71785_face_landmark` | 얼굴 ROI/품질 보정 후보 | 후속 실험 후보 |

---

## 4. Random Forest 낙상 모델 학습 과정

운영 낙상 모델은 `/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl`이다. 학습 스크립트는 `/opt/app/project/main/scripts/retrain_rf_fall_v2.py`다.

### 4.1 학습 목표

RF-Fall v2는 영상을 `fall` 또는 `non-fall`로 나누는 1차 최종 판정 모델이다. 행동분류보다 우선순위가 높으며, 알림 여부와 위험 단계의 중심이 된다.

### 4.2 입력 데이터

- AI-Hub 71641 낙상/비낙상 영상
- 기존 intake/피드백 데이터
- 클래스 분포: non-fall 795, fall 797
- 총 학습 샘플: 1,592
- 그룹 수: 798

같은 영상 또는 같은 사람에서 추출된 샘플이 train/validation에 동시에 들어가면 성능이 부풀려진다. 그래서 영상/그룹 단위 분리를 전제로 검증한다.

### 4.3 Feature 구성

RF-Fall v2는 65개 feature를 사용한다. 핵심 축은 다음과 같다.

| 축 | 예시 | 목적 |
|---|---|---|
| BBox 위치 | center_y_mean, center_y_std, center_y_drop | 사람이 아래로 급격히 이동했는지 확인 |
| BBox 크기 | height_mean, height_std, area_drop_ratio | 서 있는 자세에서 낮은 자세로 붕괴했는지 확인 |
| 종횡비 | aspect_ratio_mean, aspect_rise | 세로 자세에서 가로 자세로 바뀌는지 확인 |
| 속도/가속도 | delta_y_max, delta_y_accel_max, fall_kinematic_score | 갑작스러운 낙하/붕괴를 포착 |
| 바닥 근접 | floor_proximity, floor_contact_ratio | 바닥에 가까워지는지 확인 |
| Skeleton | lying_skeleton_score, standing_skeleton_score, pose_height_drop | bbox만으로 헷갈리는 눕기/서기 보정 |
| 가림/신뢰도 | detection_rate, sample_coverage | 검출 부족으로 인한 오판을 방어 |

### 4.4 학습 방식

1. 영상에서 일정 fps로 프레임을 샘플링한다.
2. YOLOv8n-pose로 사람 bbox와 keypoint를 추출한다.
3. bbox/keypoint를 정규화한 시계열로 바꾼다.
4. 65개 feature를 계산한다.
5. `RandomForestClassifier` 계열 모델을 학습한다.
6. out-of-fold 예측 확률로 threshold sweep을 한다.
7. `suspect`, `confirm`, `best_f1` threshold를 분리해 저장한다.

현재 summary 기준 threshold는 다음과 같다.

| threshold | 값 | Precision | Recall | F1 | 의미 |
|---|---:|---:|---:|---:|---|
| suspect | 0.3487 | 0.8718 | 0.9812 | 0.9233 | 민감하게 잡는 의심 구간 |
| best_f1 | 0.4050 | 0.8980 | 0.9724 | 0.9337 | F1 최고 후보 |
| confirm | 0.4550 | 0.9080 | 0.9536 | 0.9302 | 운영 confirm 후보 |

### 4.5 적용 상태

- 모델 파일: `/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl`
- 요약 파일: `/opt/app/storage/training/fall-detection/rf-fall-v2/training_summary.json`
- 런타임 연결: `src/model/struct/video_analysis.py`
- 적용 방식: RF-Fall v2가 준비되면 기존 RF-Dual 경로에서 우선 사용한다.

---

## 5. XG-Posture 행동/자세 모델 학습 과정

운영 행동 모델은 `/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl`이다. 학습 스크립트는 `/opt/app/project/main/scripts/retrain_xg_posture_grouped.py`와 feature 최적화 스크립트 `/opt/app/project/main/scripts/optimize_xg_posture_features.py` 계열을 사용했다.

### 5.1 학습 목표

XG-Posture는 `stand`, `walk`, `run`, `sit`, `lie` 5개 행동/자세를 분류한다. 이 모델의 목적은 낙상 최종 판단이 아니라 다음 세 가지다.

- 비낙상일 때 현재 행동을 설명한다.
- RF 낙상 점수가 경계일 때 fast-sit, controlled-lie, stand/lie 혼동을 설명한다.
- 사용자와 LLM에게 판단 근거를 제공한다.

### 5.2 입력 데이터

현재 active summary 기준:

- 학습 샘플: 8,181
- feature 수: 105
- 클래스 분포:
  - stand 725
  - walk 1,664
  - run 1,664
  - sit 2,244
  - lie 1,884
- 검증: sequence/group split CV

### 5.3 Feature 구성

105개 feature는 기존 64/82개 feature에서 하체 가림과 상체 기반 구분을 보강한 버전이다.

| 축 | 주요 feature | 의도 |
|---|---|---|
| BBox/scale | height_ratio, floor_proximity, aspect_change, area_change | 앉기/눕기/서기의 큰 형태 차이 |
| 이동량 | center_dx_abs_mean, center_x_span, center_dy, max_down_speed | 걷기/뛰기는 단순 흔들림이 아니라 이동이 있어야 함 |
| Pose geometry | pose_tilt_mean, pose_height_ratio, shoulder_width, hip_width | 상체/전신 기하 |
| 하체 feature | knee_bend, ankle_width, lower_body_visibility, leg_verticality | 앉기/걷기/뛰기 분리 |
| 상체 feature | upper_body_aspect, torso_verticality, upper_body_temporal_motion | 하체 가림 시 상체 기반 추정 |
| Temporal feature | speed_std, oscillation_count, step_period_est, center_y_periodicity | 걷기/뛰기 주기성 |
| Guard feature | support_stability_score, lie_stand_separation_score, flatness_score | stand/lie, sit/lie 오분류 억제 |

### 5.4 학습 방식

1. AI-Hub 71461/61/기존 데이터에서 행동 라벨을 정리한다.
2. 영상 또는 image/keypoint annotation을 공통 feature row로 변환한다.
3. 같은 영상/사람이 train/validation에 같이 들어가지 않도록 Group split을 사용한다.
4. 후보 모델을 여러 개 학습한다.
   - `xgb_regularized`
   - `xgb_shallow`
   - `xgb_conservative`
   - `extra_trees_balanced`
5. macro F1, class별 recall, confusion matrix를 비교한다.
6. 현재 active는 `extra_trees_balanced`다.

현재 active 검증 결과:

| 지표 | 값 |
|---|---:|
| sequence CV accuracy | 0.9432 |
| sequence CV macro F1 | 0.9431 |

현재 XG-Posture는 운영 설명 레이어로 충분히 개선됐지만, 낙상 최종 판정을 대체하지 않는다. 실제 설치 각도, 침대/의자 전이, 하체 가림 hard-case는 계속 들어오므로 target_model=`xg-posture`와 행동 라벨을 함께 저장해 재학습 자료를 축적한다.

---

## 6. 하체 가림 보조 모델

하체가 보이지 않으면 기존 행동분류는 `unknown` 또는 `lie`로 쏠리는 문제가 있었다. 이를 줄이기 위해 일부 데이터를 하체 가림 형태로 증강하고, 별도 보조 모델을 학습했다.

| 항목 | 값 |
|---|---|
| 모델 | ExtraTrees balanced |
| 위치 | `/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/xg_posture_occlusion_aux_model.pkl` |
| feature | 105 |
| Group CV accuracy | 0.8663 |
| Group CV macro F1 | 0.8657 |

이 모델은 기본 XG-Posture를 대체하지 않는다. lower-body visibility가 낮고 주 모델 confidence가 낮거나 stand/sit/lie가 흔들릴 때 보조 근거로 사용한다.

---

## 7. 표정/상태 보조 모델

표정 모델은 낙상 여부를 직접 판단하지 않는다. 낙상 전조 또는 낙상 후 상태를 설명하는 보조 근거다.

| 모델 | 데이터 | 클래스 | 성능 | 적용 방식 |
|---|---|---|---|---|
| AI-Hub 82 | 한국인 감정 | happiness, embarrassed, anger, anxiety, hurt, sadness, neutral | macro F1 0.6198 | 표정 불편/정상 보조 |
| AI-Hub 173 | 운전자 상태 | normal_focus, drowsy, yawn, phone_call, smoking | macro F1 0.9054 | 졸림/주의저하 보조 |

적용 기준은 다음과 같다.

- 실제 얼굴 검출이 되지 않으면 감정 라벨을 사용하지 않는다.
- pose 기반 머리 ROI만으로 감정을 추정하지 않는다.
- confidence, margin, entropy, frame consistency가 낮으면 `표정 근거 약함` 또는 `얼굴/표정 미검출`로 표시한다.
- 표정 점수는 positive-only 보조 점수이며, 얼굴 미검출은 낙상 아님으로 감점하지 않는다.

---

## 8. SHAP 적용 계획과 의미

SHAP는 학습하는 모델이 아니라, 학습된 Random Forest/XG-Posture tree 모델의 예측을 설명하는 해석 방법이다. 그래서 “SHAP를 학습한다”기보다 “학습된 모델에 대해 SHAP 값을 계산한다”가 정확하다.

### 8.1 왜 필요한가

현재 UI/LLM 근거는 feature importance와 rule evidence 중심이다. 이것은 전체적으로 어떤 feature가 중요한지는 알려주지만, 특정 영상 하나에서 왜 낙상/눕기/서기로 판단했는지는 약하다.

SHAP를 붙이면 다음이 가능하다.

- 특정 청크에서 fall score를 올린 feature Top-N 표시
- stand/lie 혼동 구간에서 어떤 feature가 lie 쪽으로 밀었는지 확인
- threshold 조정 때 오탐/미탐 사례별 공통 원인 분석
- LLM 설명에 실제 feature 기여도를 넘겨 근거 빈약 문제 완화

### 8.2 적용 방식

| 단계 | 내용 |
|---|---|
| 1 | RF-Fall v2와 XG-Posture 모델 로드 |
| 2 | train feature row에서 background sample을 추출 |
| 3 | TreeExplainer 또는 model-specific explainer로 SHAP 계산 |
| 4 | global mean_abs_shap으로 전체 중요 feature 산출 |
| 5 | validation false positive/false negative에 대해 local SHAP 산출 |
| 6 | `analysis_basis`와 LLM prompt에 top contribution을 연결 |

### 8.3 주의점

- SHAP는 성능을 직접 올리는 도구가 아니다.
- 계산 비용이 있어 실시간 모든 청크에 돌리면 RTT가 늘 수 있다.
- 운영 실시간에서는 Top feature importance 기반 간이 설명을 쓰고, SHAP는 batch 리포트/오류 분석에 우선 적용하는 것이 안전하다.

권장 방향은 다음과 같다.

- 개발/검증: SHAP batch report 생성
- 운영 UI: 빠른 feature contribution 표시
- LLM: SHAP 또는 contribution Top-N을 근거로 받아 설명 생성

---

## 9. 발표에서 말해야 할 핵심 흐름

1. 먼저 데이터 확보를 설명한다.
   - 단순히 많이 받았다는 말보다 어떤 약점을 보완하기 위한 데이터인지 말한다.
2. 다음으로 적용 완료와 후보를 분리한다.
   - RF-Fall v2, XG-Posture, occlusion aux, facial aux는 적용되어 있다.
   - YOLO11과 SHAP 실시간 적용은 후보/후속이다.
3. 성능은 좋은 수치만 말하지 않는다.
   - RF는 안정화됐다.
   - 행동분류는 하체 가림/실환경 도메인 차이 때문에 아직 개선이 필요하다.
4. 다음 발전 방향을 명확히 한다.
   - 실제 설치 각도 hard-case 수집
   - 하체 가림/침대/의자 전이 라벨 확충
   - Group split 재학습
   - YOLO11 shadow test 확대
   - SHAP batch report로 오류 원인 분석

---

## 10. 남은 개선 과제

| 우선순위 | 과제 | 이유 |
|---|---|---|
| 1 | 실제 환경 hard-case 수집 | 현재 성능 병목은 도메인 차이와 가림이다. |
| 2 | 행동분류 sequence/group split 재학습 | 실제 설치 각도와 하체 가림 hard-case가 들어올 때 active 0.9431을 기준으로 개선 여부를 비교한다. |
| 3 | SHAP batch report | 어디서 오분류되는지 feature 단위로 보여줘야 다음 개선이 빨라진다. |
| 4 | YOLO11 shadow test 확대 | confidence는 좋아졌지만 검출률이 아직 낮아 바로 교체하면 위험하다. |
| 5 | 표정 모델 역할 축소/정교화 | AI-Hub 82 감정은 낙상 특화가 아니므로 보조 근거 이상으로 쓰면 안 된다. |
