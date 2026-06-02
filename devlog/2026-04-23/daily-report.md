# 2026-04-23 일일보고

## 작업 요약
- RF-Dual 낙상탐지 모델의 FP(오탐) 억제 및 guard_soft_override 조건 강화
- RF-Dual posture 결과의 5-class/6-class 분리 및 UI 정합성 개선
- 대시보드 UI에서 비낙상 상태의 fall 표시 혼선 제거 및 안내 개선

## 상세 작업 내역

### 1. RF-Dual FP 억제 및 guard_soft_override 강화 (001)
- motion guard override 완화 후 신규 FP(오탐) 3건의 원인 분석 및 구조 개선
- `_guard_soft_override` 조건을 score 0.62 이상, height_std 45.0+ AND delta_y_max 15.0+로 강화
- bbox 높이 증가(기립/보행) 시 FP 억제용 `fhr_rise_suppressor` 추가
- 200개 영상 재평가 결과 FP 13→9, 지표 개선

### 2. RF-Dual posture fall 표시 UI 혼선 제거 (002)
- 최종 비낙상 상태에서 raw posture의 fall이 1위로 보이는 문제 수정
- 비낙상 5-class만 재정규화하여 UI에 표시, raw fall 확률은 안내 문구로만 노출
- 관련 함수(`rawPostureProbs`, `isFinalNonFall`, `topNonFallPostureCode`, `displayPostureProbs` 등) 추가 및 기존 함수 개선

### 3. RF-Dual posture 5-class/6-class 분리 및 아키텍처 정리 (003)
- RF-Dual의 posture 결과를 5-class(stand/walk/run/sit/lie)와 raw 6-class로 분리
- 최종 결과(`posture_probs`, `posture_label`, `behavior_result`)는 5-class 기준, raw fall은 별도 필드로만 보존
- suppressor/veto 로직 및 프론트엔드 표시 로직 일관성 확보

## 특이사항 및 이슈
- FP 억제 강화로 인한 정상 동작군 영향 없음 확인
- UI 혼선 해소로 사용자 혼동 최소화

## 차주/향후 계획
- RF-Dual 모델 추가 튜닝 및 실시간 테스트 확대
- posture 분리 구조 기반 추가 행동분류 기능 개발
- 사용자 피드백 반영 UI 개선 지속

---
*보고자: 자동화 에이전트(GitHub Copilot)*
*작성일: 2026-04-23*