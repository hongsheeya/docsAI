# 2026-04-21 일일보고: 데이터 수집 및 추가 학습 요약

## 1. AIHub 외부 행동 데이터셋 분석 및 수집
- **데이터셋**: AIHub 한국형 비전 데이터 (Validation/02.라벨링데이터)
- **총 라벨 파일**: 34,312개 (json)
- **주요 액션 분포** (상위 10개):
  - sit: 7,000+
  - walk: 6,900+
  - stand_on: 6,800+
  - lie_on: 2,000+
  - hold: 1,900+
  - watch: 1,800+
  - no_interaction: 1,700+
  - straddle: 1,200+
  - ...
- **주요 객체 분포** (상위 5개):
  - chair, table, bed, sofa, tv 등

## 2. 외부 데이터 기반 XG-Posture 추가 학습
- **목표**: 기존 자세 분류(6-class) 모델의 앉기/서기/눕기/걷기 클래스 보강
- **외부 데이터 매핑 규칙**:
  - 직접 매핑: sit→sit, walk→walk, lie_on→lie, stand_on→stand
  - 약한 매핑(hold, watch, no_interaction, straddle)은 이번 학습에서 제외(stand 편향 방지)
- **최종 선별 외부 샘플**:
  - sit: 260
  - stand: 5
  - walk: 3
  - lie: 43
- **전체 학습 샘플**: 1,620 (내부+외부)
- **클래스 분포**: stand 87, walk 468, run 214, sit 480, lie 278, fall 93

## 3. 모델 재학습 및 성능
- **모델**: XGBoost 6-class 자세 분류 (xg_posture_model.pkl)
- **CV accuracy**: 0.8994
- **Train accuracy**: 0.979
- **클래스별 recall**:
  - stand: 0.9195
  - walk: 0.9872
  - run: 0.9953
  - sit: 0.9771
  - lie: 0.9712
  - fall: 0.9892

## 4. 업로드 분석 경로 개선
- **문제점**: 업로드 분석 시 추가 청크 재추론으로 응답 지연(최대 44초)
- **개선**: 업로드 경로에서 추가 청크 분석 비활성화(단일 패스)
- **결과**: 업로드 분석 응답 속도 대폭 개선, 실시간성 회복

## 5. 런타임 자세 보정 로직 개선
- **sit→stand 강제 전환 가드 강화**
- **stand→sit 복구 신호 보강**
- **부분 신체 stand override에서 sit 제외**

## 6. 작업 이력 및 devlog
- [008-upload-latency-and-sit-stand-bias-fix.md](008-upload-latency-and-sit-stand-bias-fix.md) (상세)
- [devlog.md](../devlog.md) (요약)

---
**요약**: 외부 데이터셋 분석 및 선별, 약한 stand 매핑 제거, 업로드 분석 속도 개선, 자세 보정 로직 강화, 모델 재학습 및 devlog 기록까지 일괄 완료.
