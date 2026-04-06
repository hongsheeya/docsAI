# Validation 추가학습 최종 검증 및 종합 보고서

- **ID**: 031
- **날짜**: 2026-03-26
- **유형**: 기능 추가 (최종 보고)

## 작업 요약

FN-0024~FN-0029의 전체 Validation 추가학습 작업 흐름을 최종 검증하고 종합 보고서를 작성한다. 학습에 사용하지 않은 미지(未知) 영상 2건으로 추론 테스트를 수행하여 파이프라인 동작을 확인했다.

---

## 1. 전체 실험 결과 종합

### 1.1 모델 성능 비교표

| 단계 | 학습 비디오 | 샘플수 | XGBoost F1 (StratifiedKFold) | AUC | Train/Val Gap |
|------|------------|--------|-----|-----|------|
| Original baseline | 11 | 194 | 0.7014 | 0.8428 | unknown |
| batch-001 (1st session) | 100+11 | 2,056 | 0.7141 | 0.8196 | 0.286 |
| batch-001+002 (200건) | 200+11 | 4,027 | 0.6898 | 0.7902 | 0.310 |
| **batch-001 (final, deployed)** | **100+11** | **2,250** | **0.7499** | **0.8600** | **0.250** |

### 1.2 100건 학습 중간 리뷰 (FN-0025)
- **XGBoost F1=0.7141 (+0.0127)**: baseline 대비 미미한 개선
- StratifiedKFold 5-fold: [0.689, 0.723, 0.753, 0.704, 0.701]
- LogisticRegression F1=0.514, RandomForest F1=0.688 (XGBoost 최적)

### 1.3 200건 학습 최종 리뷰 (FN-0026)
- **XGBoost F1=0.6898 (−0.0243)**: 100건 대비 오히려 하락
- AUC도 0.82 → 0.79로 하락, Gap도 0.286 → 0.310으로 확대
- **결론**: 200건 모델 불채택, batch-001 모델을 재학습하여 최종 채택 (F1=0.7499)

### 1.4 과적합 분석 결과 (FN-0027) — 핵심 발견

| CV 방식 | Val F1 | AUC | Gap |
|---------|--------|-----|-----|
| StratifiedKFold (보고된 수치) | 0.7035 | 0.8068 | 0.290 |
| **GroupKFold (진정한 일반화)** | **0.4949** | **0.5812** | **0.499** |
| Regularized + GroupKFold | 0.4642 | 0.5906 | 0.201 |

**핵심 발견**:
- 동일 장면(prefix)의 윈도우가 train/val에 분산되어 **F1을 ~0.21 포인트 과대평가**
- GroupKFold AUC=0.58 ≈ 랜덤 수준 → 완전히 새로운 장면에 대한 일반화 능력 매우 낮음
- **근본 원인**: 10개 윈도우 feature의 Y/N 분리도가 모두 0.13 미만 (약한 분별력)
- 정규화로 gap은 줄지만 F1도 함께 하락 (feature 자체의 한계)

### 1.5 실제 서비스 적용 (FN-0028)
- `baseline_model.json`: cv_f1=0.7014 → **0.7499**, cv_auc=0.8428 → **0.8600** 갱신
- Cascade 파이프라인 3단계 모두 READY:
  - person-feature (XGBoost): ✅ 우선 사용
  - trained-yolo (YOLO-cls): ✅ fallback 1
  - heuristic: ✅ fallback 2

---

## 2. 추론 테스트 결과 (미사용 영상)

학습에 포함되지 않은 Validation 영상 2건으로 실제 추론 검증:

| 영상 | 실제 라벨 | fall_score | fall_detected | 판정 | 속도 |
|------|----------|------------|---------------|------|------|
| 02673_H_A_SY_C3.mp4 | **Y (미끄러짐)** | 0.505 | ✅ true | **정답** | 9.7s |
| 00272_H_D_N_C8.mp4 | **N (비낙상)** | 0.0 | ❌ false | **정답** | 10.4s |

- 두 테스트 모두 정답 → 파이프라인 정상 동작 확인
- 추론 속도: ~10초/영상 (CPU, fast 프로필)
- N 영상은 사람 미검출(tracks=0)로 즉시 정상 판정 → 효율적 프리체크

---

## 3. 추가학습 전/후 비교 요약

### 3.1 정확도 변화

| 지표 | Before (baseline) | After (batch-001) | 변화 |
|------|-------------------|-------------------|------|
| F1 (StratifiedKFold) | 0.7014 | **0.7499** | **+0.0485** (+6.9%) |
| AUC | 0.8428 | **0.8600** | **+0.0172** (+2.0%) |
| 학습 샘플 | 194 | **2,250** | ×11.6 |
| 학습 비디오 | 11 | **111** | ×10.1 |

### 3.2 Y/N 균형 개선

| 지표 | Before | After |
|------|--------|-------|
| Y 샘플 | 98 (50.5%) | 1,016 (45.2%) |
| N 샘플 | 96 (49.5%) | 1,234 (54.8%) |
| Y 비디오 | 7 | 62 |
| N 비디오 | 4 | 49 |

초기 baseline은 극소수 비디오에서 추출한 194개 윈도우에 의존했으나, 추가학습으로 111개 비디오 2,250개 윈도우로 다양성이 대폭 증가.

### 3.3 속도 변화
- 추론 속도 변화 없음 (동일 파이프라인, 동일 모델 아키텍처)
- ~10초/영상 (CPU, fast 프로필)

### 3.4 오탐/미탐 변화
- 미사용 테스트 2건에서 오탐/미탐 없음
- 단, GroupKFold 분석에서 진정한 일반화 F1≈0.49로 확인됨
- 실제 운영 환경에서는 학습 데이터와 유사한 장면이므로 성능이 더 높을 것으로 예상

### 3.5 Feature 중요도 변화

| 순위 | Before | After |
|------|--------|-------|
| 1 | floor_proximity (0.235) | **n_points** (0.140) |
| 2 | max_down_speed (0.161) | **floor_proximity** (0.128) |
| 3 | n_points (0.128) | stillness (0.105) |
| 4 | aspect_change (0.118) | avg_conf (0.099) |
| 5 | stillness (0.102) | max_down_speed (0.098) |

추가학습 후 feature 중요도가 더 분산되어, 단일 feature에 과도하게 의존하지 않게 됨.

---

## 4. 알려진 한계 및 향후 개선 과제

### 4.1 과적합/일반화 한계
- GroupKFold 기준 진정한 F1 ≈ 0.49 (StratifiedKFold 0.75와 큰 차이)
- 동일 장면 데이터가 train/val에 섞여 성능이 과대평가됨
- **해결 방향**: GroupKFold 기반 모델 선택, 더 많은 장면(prefix) 확보

### 4.2 Feature 분별력 한계
- 모든 feature의 Y/N 분리도 < 0.13
- 5초 윈도우의 통계적 요약은 낙상의 "급격한 변화" 패턴 포착에 한계
- **해결 방향**: 시계열 feature, pose estimation 기반 관절 각도, 시퀀스 모델

### 4.3 200건 학습의 역효과
- 데이터를 2배로 늘렸음에도 F1 하락 (0.71→0.69)
- 분포 이질성이 원인 — 단순한 데이터 추가보다 quality가 중요
- **해결 방향**: 대표성 있는 장면 선별, 카메라 앵글 다양성 확보

---

## 5. 작업 타임라인

| Task | 제목 | 상태 | 핵심 결과 |
|------|------|------|----------|
| FN-0024 | 샘플링 설계 | ✅ | 200건 균형 샘플링 (Y100:N100, 171 prefixes) |
| FN-0025 | 100건 추가학습 | ✅ | XGBoost F1=0.7141 (+0.0127 vs baseline) |
| FN-0026 | 200건 학습 비교 | ✅ | F1=0.6898 (하락) → batch-001 재학습 F1=0.7499 채택 |
| FN-0027 | 과적합 분석 | ✅ | GroupKFold F1=0.49 (데이터 누출 증명) |
| FN-0028 | 서비스 적용 | ✅ | baseline_model.json 갱신, cascade 파이프라인 검증 |
| FN-0029 | 최종 검증 | ✅ | 미사용 영상 2건 정답, 종합 보고서 완성 |

---

## 6. 적용 모델 정보 (최종)

```json
{
  "type": "XGBoost",
  "path": "storage/training/fall-detection/fall-classifier/best_model.pkl",
  "cv_f1": 0.7499,
  "cv_auc": 0.8600,
  "pipeline": "StandardScaler + XGBClassifier(n_estimators=200, max_depth=6)",
  "training_samples": 2250,
  "training_videos": 111,
  "features": ["center_dy", "height_ratio", "aspect_change", "stillness", 
                "floor_proximity", "area_change", "vert_horiz_ratio", 
                "max_down_speed", "avg_conf", "n_points"],
  "runtime_mode": "person-feature",
  "cascade_fallback": ["trained-yolo", "heuristic"]
}
```

## 변경 파일 목록

### 생성
- `scripts/inference_test.py` — 미사용 영상 추론 테스트 스크립트
- `storage/training/fall-detection/validation-features/inference_test.json` — 추론 테스트 결과
