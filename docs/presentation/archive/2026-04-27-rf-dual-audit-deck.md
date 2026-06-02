# RF-Dual 운영 구조 및 학습 현황 발표자료

- 날짜: 2026-04-27
- 대상: 내부 리뷰 / 모델 운영 점검 / 향후 개선 논의
- 작성: GitHub Copilot

---

## 1. 개요

### 1-1. 목표
- 낙상 탐지와 일반 행동 분류를 하나의 결과 화면에서 안정적으로 제공
- 실제 운영에서는 **낙상 리콜**을 우선 확보하면서도, 비낙상 구간에서는 `stand / walk / run / sit / lie`를 구분
- 단일 모델 하나로 모든 문제를 해결하려 하기보다, **역할이 다른 2개 모델을 중첩**해 최종 판단의 안정성을 높임

### 1-2. 현재 운영 결론
- 현재 기본 운영 축은 `RF-Dual`
- 최종 낙상 판정은 **RF binary fall model**이 담당
- 자세/행동 해석은 **XG-Posture 6-class model**이 담당
- 운영 화면에는 raw 6-class 전체를 그대로 쓰지 않고, **5-class (`stand/walk/run/sit/lie`)** 중심으로 정리해 노출
- raw `fall` posture는 진단용 메타데이터로만 유지

### 1-3. 이번 정리 범위
- `sit ↔ lie` 판단 경계 보정
- RF-Dual 판단 파이프라인 재정리
- 2개 모델을 겹쳐 쓰는 이유와 성능 설명
- 각 모델의 학습 현황, 데이터 수집 및 학습 방식 정리
- 데이터 누수 가능성 점검
- 현재 한계점과 개선 방향 정리

---

## 2. 문제 정의

### 2-1. 왜 단일 모델만으로는 부족했는가
낙상 탐지는 본질적으로 다음 두 문제를 동시에 가진다.

1. **낙상 여부 판단**
   - 실제로 위험한 fall인지
   - 빠르게 앉거나 눕는 정상 동작과 어떻게 구분할지
2. **비낙상 행동 해석**
   - 현재 상태가 `stand`, `walk`, `run`, `sit`, `lie` 중 무엇인지
   - 운영 화면에서 설명 가능한 결과를 어떻게 줄지

이 두 문제는 필요한 최적화 방향이 다르다.
- 낙상 탐지는 **recall 우선**이 중요하다.
- 행동 분류는 **세밀한 클래스 경계**와 설명력이 중요하다.

따라서 하나의 모델에 두 역할을 모두 몰아주면,
- 낙상 recall을 올릴수록 일반 행동 분류가 흔들리거나
- 행동 클래스 정밀도를 올릴수록 낙상 민감도가 낮아질 수 있다.

---

## 3. 전체 판단 파이프라인

### 3-1. 상위 흐름
1. 입력 영상 수집
2. 사람 bbox / pose keypoint 추출
3. 시계열 feature 생성
4. **RF binary fall model** 추론
5. **XG-Posture 6-class model** 추론
6. heuristic boost / guard / smoothing 적용
7. 비낙상 구간은 5-class 행동으로 재정규화
8. RF-Dual arbitration으로 최종 상태 결정

### 3-2. 실질 역할 분담
- **RF model**
  - 역할: 낙상인지 아닌지 최종 결정
  - 강점: 운영 기준 의사결정을 단순하고 안정적으로 유지 가능
- **XG-Posture model**
  - 역할: 자세/행동 해석, 낙상 오탐 억제, 결과 설명 보조
  - 강점: `stand/walk/run/sit/lie/fall` 같은 세부 상태 분해 가능

### 3-3. 후처리 계층
후처리는 단순 장식이 아니라 운영 안정화 계층이다.
- posture heuristic boost
- transition constraint
- temporal smoothing
- posture safe veto
- motion guard
- fall/arbitration threshold logic

즉, 모델 출력값을 그대로 쓰는 것이 아니라,
**시계열 문맥 + 자세 상식 + 운영 정책**을 함께 적용한다.

---

## 4. RF-Dual 설명

### 4-1. RF-Dual이 의미하는 것
`RF-Dual`은 “RF가 두 개 있다”는 뜻이 아니라,
**RF binary fall decision + posture 해석 레이어를 결합한 운영 판단 구조**를 의미한다.

현재 실무적으로는 다음처럼 이해하면 된다.
- **낙상 판정 엔진**: RF binary
- **자세 해석 엔진**: XG-Posture
- **최종 운영 판단기**: RF-Dual arbitration logic

### 4-2. 왜 RF를 최종 판단 축으로 두는가
RF binary는 운영 의사결정에 필요한 목표가 분명하다.
- 낙상 vs 비낙상의 이진 판단
- threshold 조정이 상대적으로 명확
- 검증 지표와 운영 threshold를 연결하기 쉬움
- UI/로그/알람 시스템과 연동이 단순함

현재 문서 기준 RF 운영 모델 상태는 다음과 같다.
- Validation 기반 재학습 완료
- Accuracy `89.5%`
- Precision `84.96%`
- Recall `96.0%`
- F1 `90.14%`
- 운영 threshold `0.35`
- threshold `0.35` 미세조정 시 Validation 재평가 기준
  - Accuracy `0.9000`
  - Precision `0.8448`
  - Recall `0.9800`
  - F1 `0.9074`

### 4-3. RF-Dual의 운영상 장점
- 낙상 최종 판정 기준이 일관됨
- 비낙상 행동표시는 posture 정보를 활용해 설명 가능성 확보
- heuristic fallback이 있더라도, 그것이 그대로 최종 fall 판정을 덮어쓰지 않도록 제어 가능
- 실시간/업로드 경로를 같은 판단 철학으로 묶을 수 있음

---

## 5. 모델 2개를 중첩해서 사용하는 이유

### 5-1. 역할 분리
두 모델은 서로 대체재가 아니라 보완재다.

#### 모델 A — RF binary fall model
- 질문: “이 장면을 최종적으로 낙상으로 볼 것인가?”
- 최적화 목표: 낙상 recall, 운영 안정성, threshold 관리

#### 모델 B — XG-Posture model
- 질문: “현재 몸 상태를 어떤 자세/행동으로 해석해야 하는가?”
- 최적화 목표: 클래스 구분력, 오탐 억제, 설명 가능성

### 5-2. 단일 낙상 모델만 쓸 때 문제
낙상 이진 모델만 있으면,
- 왜 fall인지 설명이 약해지고
- 비낙상 구간의 행동 구분이 사라지며
- `sit`, `lie`, `controlled lie`, `fast sit` 같은 경계 상황 처리 근거가 약해진다.

### 5-3. 단일 posture 모델만 쓸 때 문제
자세 분류 모델만으로 낙상 최종 결정을 맡기면,
- `fall` 클래스 score 하나에 전체 알람이 좌우되기 쉽고
- 데이터 분포 변화에 취약하며
- 운영 threshold와 위험도 정책을 안정적으로 관리하기 어렵다.

### 5-4. 중첩 사용의 실효성
중첩 구조의 핵심 효과는 다음과 같다.
- RF가 **낙상 최종 책임**을 진다.
- Posture는 RF 결과를 **해석·보완·억제**한다.
- 둘을 합치면,
  - 낙상 recall을 유지하면서
  - 비낙상 장면 설명력을 확보하고
  - 특정 오탐 패턴을 줄일 수 있다.

### 5-5. 성능 관점 요약
- RF binary는 현재 운영 지표가 안정적이다.
- XG-Posture는 기존 문서상 CV accuracy `93.7%` 수준으로 관리되고 있으나,
  이번 감사에서 **window-level CV는 낙관적일 수 있음**을 확인했다.
- 따라서 posture 성능은 앞으로 **clip-grouped CV 기준으로 다시 읽어야 한다.**

즉,
- RF 성능 수치는 현재 운영 의사결정용으로 신뢰도가 높고
- posture 성능 수치는 “설명/행동분류 보조” 용도로 유효하지만,
  검증 방식은 이번에 더 엄격하게 교정했다.

---

## 6. 각 모델 학습 현황

### 6-1. RF binary fall model 현황
- 데이터 소스: Validation 공개 데이터 기반 낙상/비낙상 영상
- 최근 운영 재학습: Validation 1100영상 기반 재학습
- 실제 분할 예시:
  - Train Y/N = `450 / 449`
  - Val Y/N = `100 / 100`
- 특징 수: 16-feature 런타임 포맷 기준 운용
- 운영 threshold: `0.35`

#### 현재 상태
- 운영 축으로 사용 중
- 업로드 재평가 기준 FP `0`, FN `0` 확인 이력 존재
- 실서비스 판단의 주 엔진

### 6-2. XG-Posture model 현황
- 목적: 6-class 자세/행동 분류
  - `stand`, `walk`, `run`, `sit`, `lie`, `fall`
- 최근 학습 샘플 요약:
  - 전체 학습 샘플 `1,620`
  - 클래스 분포: stand `87`, walk `468`, run `214`, sit `480`, lie `278`, fall `93`
- 문서상 지표:
  - CV accuracy `0.8994`
  - Train accuracy `0.979`
- 클래스별 recall 예시:
  - stand `0.9195`
  - walk `0.9872`
  - run `0.9953`
  - sit `0.9771`
  - lie `0.9712`
  - fall `0.9892`

#### 주의사항
- 위 수치는 기존 window-level CV 기반 이력이 포함되어 있다.
- 이번에 clip-grouped CV로 검증 체계를 교정했으므로,
  다음 공식 posture 성능 수치는 grouped 기준으로 다시 산출해야 한다.

---

## 7. 데이터 수집 및 학습 방법

### 7-1. RF binary 데이터 수집 방식
- 공개 Validation 데이터셋에서 fall / non-fall 영상을 수집
- 영상 단위로 train/validation을 먼저 분리
- 그 후 bbox/pose 기반 feature를 추출
- threshold sweep을 통해 운영 임계값을 결정

### 7-2. XG-Posture 데이터 수집 방식
자세 분류는 내부 데이터만으로는 특정 클래스가 약해지기 쉬워,
외부 행동 데이터셋을 일부 선별해 보강했다.

#### 외부 행동 매핑 예시
- `sit -> sit`
- `walk -> walk`
- `lie_on -> lie`
- `stand_on -> stand`

#### 제외한 약한 매핑
- `hold`, `watch`, `no_interaction`, `straddle` 등은
  stand 편향을 키울 수 있어 이번 학습에서 제외

### 7-3. 학습 파이프라인
1. 라벨 파일 스캔
2. 유효 action만 선별
3. 사람/포즈 기반 시계열 feature 추출
4. sliding window 샘플 생성
5. posture 모델 학습
6. CV 및 클래스별 지표 산출
7. 런타임 후처리와 함께 운영 반영

### 7-4. 이번에 수정한 학습 검증 방식
기존 posture 검증은 `window-level CV`였다.
문제는 같은 clip에서 나온 여러 windows가 train/validation fold에 동시에 들어갈 수 있다는 점이다.

그래서 이번에 다음으로 수정했다.
- `StratifiedGroupKFold` 우선 사용
- 불가 시 `GroupKFold` fallback
- group 기준: clip filename
- summary에 `cv_mode`, `n_unique_clips`, `leakage_guard` 기록

의미:
- 같은 clip의 파생 window가 train과 validation에 동시에 섞이지 않음
- posture 성능을 더 보수적으로 읽게 됨

---

## 8. sit / lie 판단 보정 내용

### 8-1. 문제 상황
사용자 관점에서 가장 크게 보이는 오류는 다음이었다.
- 상체가 비교적 서 있는데 `sit`가 아니라 `lie`로 나옴

### 8-2. 실제 원인
이 문제는 단순히 torso tilt 하나 때문이 아니었다.
기존 로직은 다음을 함께 반영했다.
- 낮은 bbox height
- 높은 floor proximity
- 높은 floor contact
- spread 증가
- stillness 증가
- low-profile lie rescue

즉, 상체가 아주 많이 누워 있지 않아도,
**정적이고 낮고 바닥에 가까운 장면**이면 `lie` 쪽으로 과보정될 수 있었다.

### 8-3. 이번 수정
- `upright_sit_guard` 추가
- `sit/stand -> lie` boost 감산 강화
- `lie -> sit` 복구 가산 강화
- 특정 조건에서 `low_profile_lie` rescue 비활성화

### 8-4. 기대 효과
- 직립 seated 장면의 false `lie` 감소
- 하체 일부 가림/정적 장면에서의 과보정 완화
- posture 후처리의 설명 가능성 향상

---

## 9. 데이터 누수 점검 결과

### 9-1. 결론 요약
- RF binary 학습 경로는 **영상 단위 분리 후 특징 추출** 구조라 누수 위험이 상대적으로 낮다.
- posture 쪽은 기존에 **window-level CV**를 사용해 clip-level leakage 위험이 있었다.
- 따라서 “모든 테스트 데이터를 그대로 학습했다”라고 단정할 정도는 아니지만,
  **posture 검증 점수가 낙관적으로 보였을 위험은 실제로 존재했다.**

### 9-2. 과거 분석과 연결되는 근거
기존 GroupKFold 분석 이력에서도,
동일 장면(prefix) 데이터가 train/validation에 섞일 때 성능이 크게 과대평가될 수 있다는 점이 확인된 바 있다.

대표 사례:
- StratifiedKFold F1 `0.7035`
- GroupKFold F1 `0.4949`
- 차이 `-0.2086`

이는 group 분리를 하지 않으면,
모델이 “행동 일반화”보다 “장면 특성 암기”로 점수를 높일 수 있음을 보여준다.

### 9-3. 이번 조치의 의미
이번 posture 학습 스크립트 변경은 단순 리팩토링이 아니라,
**평가 기준을 실제 일반화 성능에 더 가깝게 맞추는 감사 조치**다.

---

## 10. 현재 한계점

### 10-1. 외부 홀드아웃 test set 부재
clip-grouped CV로 교정했더라도,
완전히 분리된 외부 홀드아웃 test set이 없으면 최종 일반화 성능을 단정하기 어렵다.

### 10-2. sit / lie 경계의 구조적 어려움
다음 조건에서는 여전히 어렵다.
- 카메라 각도 차이
- 하체 가림
- 침대/소파/바닥 인접 환경 차이
- 저해상도 / 포즈 누락

### 10-3. posture 데이터 불균형
- stand 클래스가 상대적으로 적다.
- 외부 라벨 매핑을 잘못 넓히면 stand 편향이 커질 수 있다.

### 10-4. feature 한계
현재 파이프라인은 시계열 통계 + keypoint/bbox 기반 특징에 의존한다.
급격한 전환의 미세한 시간 구조를 더 잘 포착하려면,
더 풍부한 temporal representation이 필요하다.

---

## 11. 개선 방향

### 11-1. 단기
1. clip-grouped CV 기준으로 XG-Posture 재학습 및 성능 재산출
2. `sit-hard`, `lie-hard` 샘플셋 분리 평가
3. 직립 seated 샘플 회귀 테스트 세트 구축
4. 운영 로그에서 `sit -> lie` 오분류 케이스 별도 수집

### 11-2. 중기
1. 외부 홀드아웃 test set 구축
2. posture 클래스 불균형 재조정
3. 상체/무릎/바닥접촉 관련 feature 세분화
4. hard-case 중심 데이터 수집 파이프라인 강화

### 11-3. 장기
1. 시계열 모델(LSTM/1D-CNN/Transformer 계열) 비교 검토
2. 카메라 시점 다양성 확대
3. 환경별 도메인 분리 평가 체계 구축
4. 행동 해석과 낙상 판정을 더 명확히 분리한 multi-head 구조 검토

---

## 12. 성능/운영 관점 핵심 메시지

### 12-1. 지금 당장 말할 수 있는 것
- RF-Dual 운영 축은 현재 안정적으로 정리되어 있다.
- RF binary는 낙상 최종 판정 엔진으로서 충분히 강한 성능을 보인다.
- Posture는 설명과 행동분류 보조로 유효하다.
- 다만 posture 검증 수치는 이제 grouped 기준으로 다시 읽어야 한다.

### 12-2. 이번 작업의 실질 성과
- `sit`가 `lie`로 무너지는 후처리 과보정 완화
- posture 검증 누수 가능성 차단
- RF-Dual 기준 문서/설명/발표자료 정렬 완료

---

## 13. 발표용 최종 결론

- 현재 시스템은 **낙상 최종 판정용 RF binary**와 **행동 해석용 XG-Posture**를 중첩한 RF-Dual 구조로 운영 중이다.
- 이 구조는 단일 모델 대비 **낙상 안정성**과 **행동 설명력**을 동시에 확보하는 데 유리하다.
- 이번 점검에서는 `sit ↔ lie` 경계 보정을 적용했고,
  posture 검증의 clip-level 누수 위험을 확인해 **clip-grouped CV**로 교정했다.
- 다음 단계는 grouped 기준 posture 재학습, hard-case 회귀 테스트, 외부 홀드아웃 평가 체계 구축이다.

---

## 14. 실제 사례 슬라이드용 예시

### 14-1. 사례 A — `sit` 계열이 분류 전 단계에서 무너진 경우

영상:
- `aug2_sit_aug_sit_20260414005825-dfcd7_cropped_cen_sub2.mp4`

관찰 내용:
- 기존에는 pose 검출 프레임이 `1 frame`뿐이라 posture 분류 이전 단계부터 입력 품질이 부족했다.
- 재시도 체인 적용 후 `6 frame`까지 회복되었다.

의미:
- 이 사례는 “분류기가 `sit`를 못 맞혔다”라기보다,
  **입력 시계열이 너무 빈약해서 posture 분류가 시작도 제대로 안 된 케이스**다.
- 즉, 일부 `sit/lie` 오류는 모델 자체보다 **검출 단계 품질 문제**에서 시작될 수 있다.

발표 포인트:
- `sit/lie` 경계 문제는 후처리 문제만이 아니다.
- detector → feature → classifier → postprocess 전 단계를 같이 봐야 한다.

### 14-2. 사례 B — 실제 `lie` 자세가 RF 측에서 낙상처럼 보인 경우

영상:
- `02327_H_A_N_C2 (lie)`

당시 로그:
- RF score `0.4833`
- posture `lie`
- `height_std = 39.17`
- `delta_y_max = 12.59`
- `final_height_ratio = 1.30`

오류 메커니즘:
- 자연스럽게 누워 있는 비낙상 장면인데,
  bbox 높이 변화(`height_std`)가 커서 `_guard_soft_override`가 과도하게 우회되었다.
- 결과적으로 “lie posture + bbox 흔들림”이 낙상처럼 해석될 수 있었다.

수정 포인트:
- `height_std` 단독 override를 폐지하고,
  `height_std >= 45 AND delta_y_max >= 15`의 실제 하강 조건을 함께 요구하도록 강화했다.

발표 포인트:
- posture가 `lie`라는 이유만으로 fall이 되는 것이 아니라,
  **RF guard 설계가 잘못 열리면 정상 lie도 fall-like로 보일 수 있다.**

### 14-3. 사례 C — `stand`인데 RF score가 높게 나온 경우

영상:
- `00110_H_A_N_C4 (stand)`

당시 로그:
- RF score `0.5667`
- posture `stand`
- `height_std = 38.89`
- `delta_y_max = 18.42`
- `final_height_ratio = 1.47`

해석:
- 최종 bbox 높이가 초기보다 더 커졌다는 것은 낙상보다 **기립/움직임**에 가까운 패턴이다.
- 그래서 `fhr_rise_suppressor`를 추가해,
  `final_height_ratio > 1.08`이고 강한 fall score가 아닌 경우를 비낙상 쪽으로 되돌리도록 했다.

발표 포인트:
- RF-Dual은 단순 score threshold가 아니라,
  **“낙상이면 실제로 어떤 시계열 변화가 나와야 하는가”**를 반영하는 구조로 가고 있다.

---

## 15. 수정 전후 비교표

### 15-1. RF-Dual FP 억제 전후

| 지표 | 베이스라인 (0422) | 리콜튜닝 (0422) | 최종 (0423) |
|------|------------------|----------------|-------------|
| accuracy | 0.9050 | 0.9050 | **0.9100** |
| precision | 0.9010 | 0.8785 | **0.9100** |
| recall | 0.9100 | **0.9400** | 0.9100 |
| F1 | 0.9055 | 0.9082 | **0.9100** |
| FP | 10 | 13 | **9** |
| FN | 9 | 6 | 9 |

해석:
- 리콜 튜닝만 하면 FP가 늘 수 있었다.
- 하지만 guard 재조정 후 FP를 줄이면서도 최종 F1을 개선했다.

### 15-2. pose 검출 재시도 체인 적용 전후

| 항목 | 수정 전 | 수정 후 |
|------|--------|--------|
| `aug2_run_kth_person15_running_d1_clip02_sub2.mp4` 검출 프레임 | `0~1` | `2` |
| `aug2_sit_aug_sit_20260414005825-dfcd7_cropped_cen_sub2.mp4` 검출 프레임 | `1` | `6` |
| 샘플 단위 총 검출 실패 | 다수 | **48개 중 2개만 잔존** |
| `walk` 재현율 | `0.000` | `0.375` |

해석:
- 일부 posture 오류는 classifier 이전의 detector 품질 문제였다.
- 입력 복구만으로도 행동 분류가 즉시 개선되는 구간이 존재했다.

### 15-3. posture 검증 누수 감사 전후 해석

| CV 방식 | Val F1 | Train F1 | Gap | AUC |
|---------|--------|----------|-----|-----|
| StratifiedKFold | `0.7035` | `0.9938` | `0.2903` | `0.8068` |
| GroupKFold | `0.4949` | `0.9934` | `0.4986` | `0.5812` |

해석:
- grouped 분리 없이 보면 posture 계열 성능이 과대평가될 수 있다.
- 이번 clip-grouped CV 전환은 발표용 수치를 더 보수적으로 만들지만,
  실제 일반화 성능에 더 가깝다.

### 15-4. `sit ↔ lie` 보정 자체의 before/after에 대한 주의

이번 `upright_sit_guard`는 코드 적용과 빌드까지 완료했다.
다만 **전용 hard-case 회귀셋 기준 전/후 오분류 건수 표**는 아직 별도 재산출하지 않았다.

즉, 발표에서는 다음처럼 설명하는 것이 정확하다.
- “구조적 원인을 찾아 로직은 교정했다.”
- “전용 hard-case benchmark 수치는 다음 실험 단계에서 확정할 예정이다.”

---

## 16. 향후 실험 계획 표

| 단계 | 목표 | 방법 | 산출물 | 성공 기준 |
|------|------|------|--------|-----------|
| 1 | posture 검증 기준 교정 | clip-grouped CV로 XG-Posture 재학습 | 새 `training_summary.json` / grouped CV report | grouped 기준 공식 지표 확보 |
| 2 | `sit-hard` / `lie-hard` 회귀 검증 | 직립 seated, low-profile lie, partial occlusion 샘플셋 구축 | hard-case benchmark report | `sit ↔ lie` 혼동률 감소 확인 |
| 3 | 외부 홀드아웃 평가 | 학습에 쓰지 않은 장면/환경 분리 | holdout eval JSON / 발표 표 | grouped CV와 holdout 간 격차 파악 |
| 4 | detector-impossible 데이터 정제 | `synth_*` 등 사람 검출 실패 샘플 자동 제외 | 정제 규칙 / 제외 목록 | detector noise 감소 |
| 5 | feature 개선 | 무릎/상체/바닥접촉/시간전이 feature 세분화 | feature ablation report | lie/fall, sit/lie 경계 개선 |
| 6 | 아키텍처 확장 | sequence model 또는 multi-head 구조 실험 | 비교 보고서 | 기존 RF-Dual 대비 개선 여지 확인 |

### 16-1. 우선순위 제안
가장 먼저 해야 할 일은 다음 3개다.
1. grouped 기준 posture 재학습
2. `sit-hard` / `lie-hard` 회귀셋 구축
3. 외부 holdout 평가셋 분리

이 3개가 끝나야,
이번 `upright_sit_guard`와 posture 검증 교정의 효과를 수치로 닫을 수 있다.
