# RF-Dual에서 posture fall 클래스 분리 및 5-class 행동분류 고정

- **ID**: 003
- **날짜**: 2026-04-23
- **유형**: 버그 수정 / 아키텍처 정리

## 작업 요약

RF-Dual에서 낙상 퍼센트는 RF 낙상탐지 모델만 담당해야 하는데, 기존에는 XG-Posture 6-class의 `fall` 확률이 UI에 그대로 노출되어
최종 비낙상 상황에서도 `낙상 xx%`처럼 보이는 구조적 혼선이 있었다.
이를 해결하기 위해 RF-Dual의 posture 결과를 행동분류용 5-class(`stand/walk/run/sit/lie`)와 raw 진단용 6-class로 분리하였다.
이제 최종 결과의 `posture_probs`, `posture_label`, `behavior_result`는 모두 5-class 기준이며, raw `fall`은 `posture_raw_*` 필드로만 보존된다.

## 원인 분석

- RF-Dual은 RF 이진 낙상 모델 + XG-Posture 6-class를 함께 사용
- 최종 `fall_detected`는 RF 기준이지만, `posture_probs`는 raw 6-class 전체를 그대로 반환
- 프론트엔드가 `posture_probs`를 그대로 분포 바/라벨에 사용하면서 `fall` 클래스가 1위로 표시됨
- 결과적으로 경고는 없지만 UI에는 `낙상 43%`, `자세: 낙상`처럼 보임

## 변경 파일 목록

### src/model/struct/video_analysis.py
- RF-Dual posture 결과를 다음 두 계층으로 분리
  - `posture_probs`, `posture_label`, `posture_score`: **5-class 비낙상 행동분류용**
  - `posture_raw_probs`, `posture_raw_label`, `posture_raw_score`: **raw 6-class 진단용**
- suppressor/veto 로직의 raw fall 참조는 `posture_raw_probs['fall']` 사용으로 변경
- `behavior_result`에 `raw_class`, `raw_score`, `raw_fall_prob` 추가

### src/app/page.dashboard/view.ts
- `rawPostureProbs()`가 우선적으로 `posture_raw_probs`를 읽도록 수정
- 표시용 `posture_probs`와 raw 진단값을 구분

## 검증 결과

스모크 테스트 기준 RF-Dual 결과:
- `posture_probs_keys = ['lie', 'run', 'sit', 'stand', 'walk']`
- raw 진단값은 별도 `posture_raw_probs['fall']`로 유지
- `behavior_result.class`는 더 이상 `fall`을 반환하지 않음 (RF-Dual 비낙상 행동분류 관점)

## 기대 효과

- 낙상 퍼센트는 RF 낙상탐지 모델 값만 해석하면 됨
- 행동분류는 완전히 별도 5-class로 동작
- posture 모델의 raw `fall` 후보가 최종 행동분류/표시에 섞이지 않음
