# 추가학습 과적합 분석 — GroupKFold 데이터 누출 검증

- **ID**: 029
- **날짜**: 2026-03-26
- **유형**: 분석 보고서

## 작업 요약

Validation 데이터 100건(batch-001) 추가학습 모델의 과적합 징후를 정밀 분석했다. 핵심 결과: **동일 장면(prefix) 데이터가 train/val 폴드에 분산되는 group-level 데이터 누출**이 F1을 ~0.21 포인트 과대평가시키고 있음을 정량적으로 증명했다.

## 1. 분석 배경

| 모델 | 비디오 | 샘플수 | StratifiedKFold F1 | AUC | Train/Val Gap |
|-------|--------|--------|-------------------|------|---------------|
| Original baseline | 11 | 194 | 0.7014 | 0.8428 | unknown |
| batch-001 (이전 세션) | 100+11 | 2,056 | 0.7141 | 0.8196 | 0.286 |
| batch-001+002 (200건) | 200+11 | 4,027 | 0.6898 | 0.7902 | 0.310 |
| **batch-001 (현재/최종)** | **100+11** | **2,250** | **0.7499** | **0.8600** | **0.250** |

- Train F1 = 1.0 (모든 모델): 학습 데이터를 완벽하게 암기
- 200건 추가 시 F1 하락 (0.71→0.69): 데이터가 많을수록 성능이 오히려 저하
- 이 두 증상 모두 과적합의 전형적 징후

## 2. 근본 원인 #1: Prefix 기반 데이터 누출

### 데이터 구조

Validation 데이터의 비디오 이름 형식: `{행동코드}_{세트}_{장면}_{인물ID}_{카메라}` (예: `FY01_S052_C1`)

- 동일 **prefix** (`FY01_S052`) = 동일 장면/인물/환경에서 다른 카메라 앵글로 촬영
- 각 비디오에서 5초 슬라이딩 윈도우로 ~20개 feature 행이 추출됨

### 분석 결과

| 지표 | 값 |
|------|-----|
| 전체 샘플 | 2,056 |
| 고유 prefix (장면) | 97 |
| Y 전용 prefix | 53 |
| N 전용 prefix | 44 |
| 혼합 라벨 prefix | 0 |
| 평균 윈도우/prefix | 21.2 |
| 평균 카메라/prefix | 1.1 |

**핵심**: 각 prefix는 순수히 Y 또는 N 라벨만 포함 → 장면(prefix) 수준에서 라벨이 결정됨. Standard KFold는 동일 장면의 윈도우를 train과 val에 분산시켜, 모델이 "장면별 패턴"을 학습해 val에서도 높은 점수를 받게 함.

## 3. 근본 원인 #2: GroupKFold 비교 실험 (결정적 증거)

n_estimators=50으로 경량화하여 StratifiedKFold vs GroupKFold 비교 실행:

| CV 방식 | Val F1 | Train F1 | Gap | AUC |
|---------|--------|----------|-----|-----|
| **StratifiedKFold** | **0.7035** | 0.9938 | 0.2903 | 0.8068 |
| **GroupKFold (prefix 분리)** | **0.4949** | 0.9934 | 0.4986 | 0.5812 |
| Regularized + GroupKFold | 0.4642 | 0.6648 | 0.2006 | 0.5906 |

### GroupKFold Fold 상세

| Fold | Train | Val | Val Y비율 | Groups |
|------|-------|-----|----------|--------|
| 1 | 1647 (Y=657, N=990) | 409 (Y=277, N=132) | 68% | 19 |
| 2 | 1641 (Y=764, N=877) | 415 (Y=170, N=245) | 41% | 20 |
| 3 | 1647 (Y=807, N=840) | 409 (Y=127, N=282) | 31% | 19 |
| 4 | 1641 (Y=778, N=863) | 415 (Y=156, N=259) | 38% | 20 |
| 5 | 1648 (Y=730, N=918) | 408 (Y=204, N=204) | 50% | 19 |

### 핵심 결론

- **F1 하락: 0.7035 → 0.4949 (−0.2086)**: 보고된 F1의 ~30%가 데이터 누출에 의한 과대평가
- **AUC 0.5812**: 랜덤 수준(0.5)에 근접 → 모델의 실제 일반화 능력이 매우 낮음
- **정규화 효과 미미**: Regularized + GroupKFold가 gap을 줄였지만(0.50→0.20), 실제 F1은 오히려 하락(0.49→0.46)
- 이는 과적합이 아닌 **feature 자체의 분별력 부족**이 근본 문제임을 시사

## 4. 근본 원인 #3: Feature 분별력 부족

### Feature별 Y/N 분리도 (Cohen's d 유사 지표)

| Feature | Y mean | N mean | Separation |
|---------|--------|--------|------------|
| floor_proximity | 0.6740 | 0.6397 | 0.129 |
| avg_conf | 0.6959 | 0.7296 | 0.105 |
| stillness | 0.7997 | 0.8485 | 0.102 |
| height_ratio | −0.0136 | 0.0220 | 0.101 |
| aspect_change | 0.0122 | −0.0047 | 0.101 |
| center_dy | 0.0077 | 0.0000 | 0.093 |
| n_points | 20.71 | 21.79 | 0.050 |
| max_down_speed | 0.1189 | 0.1038 | 0.047 |
| area_change | 0.0174 | 0.0416 | 0.039 |
| vert_horiz_ratio | 11.01 | 6.58 | 0.023 |

**모든 feature의 separation < 0.13** — 이는 매우 낮은 수준. Y(낙상)와 N(비낙상)의 feature 분포가 크게 겹쳐, 단일 feature로는 분류가 거의 불가능.

## 5. 200건 학습이 하락한 이유

1. **장면 다양성 증가**: batch-002의 100건이 새로운 장면/환경 추가
2. **데이터 누출 희석**: 더 많은 group이 추가될수록 StratifiedKFold에서도 일부 group이 val에만 배치됨
3. **분포 이질성**: 새로운 장면의 feature 분포가 기존과 달라 학습 혼란 가중

## 6. 현재 배포 모델의 실효성 평가

### 긍정적 요소
- **StratifiedKFold 기준 F1=0.75**: 완벽하지 않지만 실용적 수준
- **Cascade 구조**: person-feature → trained-yolo → heuristic 3단계로 단일 모델 실패 보완
- **실제 사용 환경**: 학습 데이터와 유사한 실내 감시 환경이면 데이터 누출의 부정적 영향이 줄어듦
- **Heuristic fallback**: XGBoost 실패 시에도 규칙 기반 판단 제공

### 한계
- **진정한 일반화 F1 ≈ 0.49**: 완전히 새로운 장면에서는 랜덤 수준
- **Group 다양성 부족**: 97개 장면만으로는 범용적 낙상 패턴 학습 불충분
- **Feature 한계**: 5초 윈도우의 통계적 요약만으로는 낙상의 "급격한 자세 변화" 패턴을 충분히 포착하지 못함

## 7. 과적합 완화 및 향후 개선 방안

### 단기 (현재 모델 유지)
1. **배포 모델 유지**: batch-001 모델(StratifiedKFold F1=0.7499)을 현 상태로 배포
2. **모델 선택 시 GroupKFold 사용**: 향후 하이퍼파라미터 튜닝 시 반드시 GroupKFold로 평가
3. **실제 운영 데이터로 검증**: 학습에 사용하지 않은 실제 영상으로 A/B 테스트

### 중기 (Feature 개선)
1. **시퀀스 feature 추가**: 5초 윈도우 내 프레임별 변화 패턴 (급격한 높이 변화율, 자세 전환 시점)
2. **Pose estimation 활용**: bbox만이 아닌 키포인트 기반 feature (관절 각도, 상체 기울기)
3. **Temporal context**: 이전/이후 윈도우와의 비교 feature (변화 속도, 정지 전환)

### 장기 (데이터/아키텍처 개선)
1. **데이터 증강**: 다양한 환경(야외, 조명, 카메라 각도)의 학습 데이터 확보
2. **StratifiedGroupKFold**: 그룹 분리 + 라벨 균형을 동시에 보장하는 CV
3. **시계열 모델**: 윈도우 feature가 아닌 프레임 단위 시계열 모델 (LSTM, 1D-CNN)

## 8. 카메라 분포

| Camera | Samples | 비율 |
|--------|---------|------|
| C1 | 414 | 20.1% |
| C2 | 375 | 18.2% |
| C4 | 347 | 16.9% |
| C7 | 217 | 10.6% |
| C5 | 213 | 10.4% |
| C8 | 193 | 9.4% |
| C6 | 154 | 7.5% |
| C3 | 143 | 7.0% |

## 변경 파일 목록

### 생성
- `scripts/overfitting_analysis_light.py` — GroupKFold 비교 실험 스크립트
- `storage/training/fall-detection/validation-features/overfitting_analysis.json` — 비교 실험 결과

### 참조
- `storage/training/fall-detection/validation-features/evaluation_100.json` — batch-001 평가 결과
- `storage/training/fall-detection/validation-features/evaluation_200.json` — 200건 평가 결과
- `storage/training/fall-detection/validation-features/features_combined.csv` — 학습 feature 데이터
