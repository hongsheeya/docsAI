# FallAI 월요일 발표자료: 주말 학습/개선 현황

- 생성: 2026-06-01 00:43 UTC
- 코드: `/opt/app/project/main`
- 데이터: `/opt/app/datasets`
- 모델: `/opt/app/storage/training/fall-detection`

---

## 1. 한 줄 결론

지난 발표 이후 핵심 변화는 세 가지다.

1. 낙상/행동 모델은 실제 환경 기준으로 frame 정책, threshold, 하체 가림 guard를 보강했다.
2. 표정 모델은 단독 판단이 아니라 낙상 위험 보조 근거로 붙였고, 얼굴이 안 보이면 감정 라벨을 사용하지 않도록 수정했다.
3. 주말 학습 큐는 완료됐고, AI-Hub 173 상태 모델은 개선 후보가 승격됐으며 AI-Hub 82 strict 실험은 active보다 낮아 보류했다.

---

## 2. 어떤 데이터를 왜 받았는가

| 데이터 | 사용 목적 | 현재 확보량 | 왜 필요한가 |
| --- | --- | --- | --- |
| AI-Hub 71641 낙상/비낙상 | 낙상 RF 학습/검증 | 1.5T | fall/non-fall 균형, threshold 조정 |
| AI-Hub 71461 행동분류 | stand/sit/lie 보강 | 111G | 행동 라벨 기반 5-class 보강 |
| AI-Hub 61 사람동작 2020 | walk/run/sit/lie sequence | 99G | 걷기/뛰기 이동량 기준 보강 |
| AI-Hub 82 한국인 감정 | 표정 상태 보조 | 320G | 불안/상처/슬픔/중립 등 7-class |
| AI-Hub 173 운전자 상태 | 주의저하 보조 | 22G | 졸림/하품/정상/통화/흡연 보조 |
| AI-Hub 71785 안면 랜드마크 | 얼굴 ROI/품질 보강 후보 | 116G | 표정 모델 품질 보정 후보 |

공식 출처:

- AI-Hub 71641: https://www.aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=71641&topMenu=100
- AI-Hub 71461: https://www.aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=71461&topMenu=100
- AI-Hub 61: https://www.aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=61&topMenu=100

---

## 3. 현재 모델 성능 요약

| 모델/후보 | 학습 샘플 | feature/class | precision | recall | F1/macro |
| --- | --- | --- | --- | --- | --- |
| 낙상 RF best-F1 후보 | 1592 | 65 | 0.898 | 0.9724 | 0.9337 |
| 낙상 RF confirm 운영 후보 | 1592 | 65 | 0.908 | 0.9536 | 0.9302 |
| 행동분류 active grouped | 2466 | 105 | - | - | 0.6513 |
| 행동분류 sequence 후보 | 2466 | 105 | - | - | - |
| 하체가림 보조 모델 | - | 105 | - | - | extra_trees_balanced |
| 표정 82 운영 모델 | 49819 | 7-class | - | - | 0.6198 |
| 상태 173 운영 모델 | 40000 | 5-class | - | - | 0.9054 |

주의: 행동분류는 `active grouped`와 `sequence 후보`를 분리해 발표한다. sequence 후보 수치가 더 높아도 운영 적용은 runtime feature 안정성을 함께 본다.

---

## 4. 적용된 방식과 현재 상태

| 영역 | 적용 방식 |
|---|---|
| 낙상 판단 | RF fall binary가 최종 fall/non-fall을 먼저 판단 |
| 행동분류 | 비낙상/설명 레이어에서 stand/walk/run/sit/lie 5-class 병렬 표시 |
| 하체가림 | lower-body visibility가 낮을 때 보조 모델/guard로 lie 과판정 억제 |
| 표정분석 | 얼굴 검출이 실제로 된 경우에만 표정 라벨 사용, 미검출이면 `얼굴/표정 미검출` |
| LLM 근거 | 모델 결과/feature/evidence를 요약하는 해석 보조, 최종 판단을 대체하지 않음 |

시간을 많이 쓴 부분은 실시간 청크 동기화, 업로드/실시간 WebM feature 차이, 하체 가림 시 stand/sit/lie 붕괴, 표정 모델의 미검출 처리, 그리고 발표 수치 정합성 정리였다.

---

## 5. RF, XGBoost, SHAP 학습/해석 방식

| 구분 | 방법 | 현재 결과 | 역할 |
|---|---|---|---|
| Random Forest | YOLOv8n-pose bbox/keypoint에서 65개 feature 생성 후 group split 학습, threshold sweep | 1,592 samples, best-F1 0.9337, confirm F1 0.9302 | 낙상 최종 판정 |
| XGBoost | 71461/61 행동 데이터를 105개 feature row로 변환, StratifiedGroupKFold로 xgb 후보 비교 | active xgb_regularized, 2,466 rows, macro F1 0.6513 | 행동/자세 설명 |
| Occlusion auxiliary | 하체 가림 증강/기존 데이터를 105개 feature로 학습 | ExtraTrees balanced, macro F1 0.8657 | 하체 가림 보조 |
| SHAP | 학습 모델이 아니라 RF/XGBoost 예측을 feature별로 설명하는 후처리 | 실시간 미적용, batch report 우선 | 오분류 원인 분석/LLM 근거 보강 |

---

## 6. 표정 모델 보강 내용

- 기존 문제: 얼굴이 안 보이는 경우에도 pose 기반 머리 ROI를 감정 후보처럼 표시해 `불안`이 기본값처럼 보였다.
- 수정: 실제 얼굴 검출률 `0%`이면 감정 라벨을 버리고 `얼굴/표정 미검출`로 표시한다.
- 정상 표정/저위험: 감정 confidence, margin, entropy, frame consistency가 충분하지 않으면 `표정 이상 없음` 또는 `표정 근거 약함`으로 낮춘다.
- 점수 정책: 표정은 positive-only 보조 점수이며, 미검출/저신뢰는 낙상 점수에 반영하지 않는다.

---

## 7. 주말 학습 결과와 적용 여부

| 작업 | 최근 train 로그 | 최근 eval 로그 |
| --- | --- | --- |
| AI-Hub 173 v4 | completed | promoted macro_f1 0.8982 -> 0.9054 |
| AI-Hub 82 v10 | completed | promotion skipped: candidate 0.6176 < active 0.6198 |
| Weekend supervisor | completed | 2026-05-30T09:31:33Z |

현재 프로세스:

```text
1281042  2-17:52:41  1.2  0.0 /opt/conda/envs/app/bin/python3.14 /opt/conda/envs/app/bin/wiz run --log /var/log/wiz/app
```

---

## 8. Confusion Matrix: 다음 보강 우선순위

| actual/pred | stand | walk | run | sit | lie |
| --- | --- | --- | --- | --- | --- |
| stand | 363 | 10 | 9 | 30 | 33 |
| walk | 19 | 207 | 110 | 6 | 45 |
| run | 2 | 79 | 246 | 4 | 3 |
| sit | 35 | 55 | 130 | 362 | 68 |
| lie | 60 | 46 | 21 | 73 | 450 |

해석:

- stand/sit/lie 혼동은 하체 가림, 카메라 각도, 침대/의자 전이에서 주로 발생한다.
- walk/run은 이동량 feature가 들어가 안정화됐지만 제자리 흔들림과 걷기는 계속 분리해야 한다.
- 다음 수집 우선순위는 stand/lie, sit/lie, 하체 가림 hard-case다.

---

## 9. YOLO shadow test

| 모델 | KP 검출률 | 평균 지연 | BBox conf | KP conf |
| --- | --- | --- | --- | --- |
| YOLOv8n-pose | 93.1% | 13.43ms | 0.5462 | 0.6969 |
| YOLO11n-pose | 91.7% | 13.97ms | 0.6184 | 0.7296 |
| YOLO26n-pose | 83.3% | 23.37ms | 0.6449 | 0.7813 |

결론: YOLO11은 confidence 개선 여지가 있지만 현재 샘플에서 검출률이 YOLOv8n보다 낮아 즉시 교체하지 않는다. 주말/후속 검증에서는 shadow test를 더 넓은 샘플로 확대한다.

---

## 10. 시연 자료 위치

| 자료 | 경로 |
| --- | --- |
| 서기/짧은 청크 WebM | /opt/app/project/main/outputs/realtime_repro/standish_4s_vp8.webm |
| 걷기 유사 WebM | /opt/app/project/main/outputs/realtime_repro/walkish_4s_vp8.webm |
| 비낙상 로컬 청크 | /opt/app/project/main/outputs/realtime_repro/local_N_C4_4s_vp8.webm |
| 실제 데이터 프레임 예시 | /opt/app/project/main/outputs/frames/00001_h_a_sy_c4/00001_h_a_sy_c4_f000120.jpg |

시연 순서:

1. 실시간 화면에서 privacy mode skeleton/raw 전환 확인
2. 비낙상 청크에서 낙상 판단 후 행동분류가 표시되는지 확인
3. 얼굴이 안 보이는 경우 `얼굴/표정 미검출`로 표시되는지 확인
4. LLM 해석은 모델 evidence를 설명하는 보조 역할임을 설명

---

## 11. 월요일 발표 핵심 메시지

- “데이터를 많이 받았다”가 아니라 “어떤 약점을 보완하려고 어떤 데이터를 받았는지”를 먼저 말한다.
- 운영 반영 수치와 후보 검증 수치를 분리한다.
- 낙상 예측은 1~2초 예측이 아니라 장기 위험도 예측 문제로 재정의한다.
- 현재 한계는 데이터/카메라 환경 문제이며, 다음 개선은 실제 환경 hard-case 수집이 가장 중요하다.


---

# FallAI 월요일 발표 대본 및 예상 질문

- 생성: 2026-06-01 00:43 UTC
- 발표 목표: 길게 설명하지 않고, 지난 발표 이후 실제 개선과 남은 한계를 명확히 말한다.

## 짧은 발표 대본

### 1. 시작

지난 발표 이후에는 기존 구조 설명보다 실제 개선에 집중했습니다. 데이터 추가 확보, 실시간 처리 안정화, 하체 가림 대응, 표정 보조 모델, YOLO shadow test를 진행했습니다.

### 2. 데이터

데이터는 목적별로 나눠 받았습니다. 낙상/비낙상은 AI-Hub 71641, 행동분류는 AI-Hub 71461과 61, 표정/상태 보조는 AI-Hub 82와 173을 사용했습니다. 특히 82와 173은 낙상 자체를 판단하기 위한 모델이 아니라, 낙상 위험 판단의 보조 근거를 만들기 위한 데이터입니다.

### 3. 모델 결과

낙상 판단은 RF binary가 먼저 fall/non-fall을 판단하고, 비낙상일 때 행동분류가 stand/walk/run/sit/lie를 병렬로 설명합니다. 하체가 가려진 경우에는 별도 보조 모델과 visibility guard로 lie 과판정을 줄였습니다.

### 4. 표정 모델

표정 모델은 이번에 기준을 바꿨습니다. 얼굴이 보이지 않으면 감정 라벨을 억지로 쓰지 않고 `얼굴/표정 미검출`로 표시합니다. 실제 얼굴 검출, confidence, margin, entropy, frame consistency가 충분할 때만 표정 근거를 보조 점수로 사용합니다.

### 5. 현재 학습

주말 학습 큐는 완료됐습니다. AI-Hub 173 상태 모델은 macro F1 0.8982에서 0.9054로 개선되어 승격됐고, AI-Hub 82 strict neutral guard 실험은 active 0.6198보다 낮은 0.6176이라 승격하지 않았습니다.

### 6. 한계와 다음 방향

가장 큰 한계는 하체 가림과 실제 환경 데이터 부족입니다. 모델 구조만 바꾸는 것보다 실제 설치 각도에서 stand/lie, sit/lie, 침대/의자 전이, 제자리 흔들림 hard-case를 수집하는 것이 성능 향상에 더 직접적입니다.

### 7. 마무리

정리하면, 이번 개선은 모델을 하나 더 붙인 것이 아니라 판단 근거를 분리하고, 미검출/저신뢰를 정직하게 표시하고, 주말 학습 큐 결과를 운영 후보와 보류 후보로 나눠 정리한 것입니다.

## 예상 질문

### Q1. 표정 모델이 낙상을 직접 판단하나요?

아닙니다. 표정 모델은 보조 근거입니다. 얼굴이 보이고 신뢰도가 충분할 때만 불편/주의저하 가능성을 약하게 더합니다.

### Q2. 얼굴이 안 보이면 어떻게 하나요?

감정 라벨을 사용하지 않고 `얼굴/표정 미검출`로 표시합니다. 감점하거나 낙상 아님으로 판단하지도 않습니다.

### Q3. 낙상 예측이 가능한가요?

1~2초 뒤 예측은 조기 감지에 가깝고, 실제 개입에는 시간이 부족합니다. 교수님이 원하시는 예측은 수십초~분 단위 위험도 예측으로 재정의해야 하며, 이를 위해 near-miss와 장기 보행 데이터가 필요합니다.

### Q4. YOLO11로 바로 바꾸지 않는 이유는?

confidence는 좋아졌지만 현재 shadow test에서는 keypoint 검출률이 YOLOv8n보다 낮았습니다. 운영 모델 입력 분포가 흔들릴 수 있어 더 넓은 shadow test 후 전환하는 것이 안전합니다.

### Q5. 주말 학습 결과는 어떻게 반영했나요?

supervisor가 summary를 비교해 기존 운영 모델보다 macro F1 또는 보조 목적 점수가 높은 후보만 production 경로로 승격하도록 구성했습니다. 이번에는 AI-Hub 173 v4만 승격했고, AI-Hub 82 v10은 active보다 낮아 보류했습니다.
