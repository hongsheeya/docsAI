# RF-Dual 비낙상 상태에서 raw posture fall 표시 제거

- **ID**: 002
- **날짜**: 2026-04-23
- **유형**: 버그 수정 / UI 정합성 개선

## 작업 요약

RF-Dual의 최종 판정은 비낙상인데, 대시보드의 6-class 자세 분포 UI가 raw `posture_probs`를 그대로 정렬 표시하여
`fall` 클래스가 1위로 보이는 문제를 수정하였다. 이로 인해 경고는 없지만 화면에는 `자세: 낙상`으로 보이는 혼동이 발생했다.
최종 비낙상일 때는 비낙상 5-class(`stand/walk/run/sit/lie`)만 재정규화하여 표시하고,
raw `fall` 확률은 안내 문구로만 노출하도록 변경했다.

## 원인 분석

- 백엔드 최종 판정은 RF 기준으로 `fall_detected=False`이면 `behavior_class='fall'`로 가지 않음
- 그러나 프론트엔드 `postureItems()`가 `posture_probs` raw 6-class를 그대로 사용
- `postureLabel()`도 raw `posture_label='fall'`을 그대로 표시
- 결과적으로 최종은 정상인데 화면상 `낙상 44%`, `자세: 낙상`처럼 보임

## 변경 파일 목록

### src/app/page.dashboard/view.ts
- `rawPostureProbs()` 추가
- `isFinalNonFall()` 추가
- `topNonFallPostureCode()` 추가
- `displayPostureProbs()` 추가
- `postureLabel()`에서 최종 비낙상 + raw fall일 경우 상위 비낙상 클래스로 대체
- `postureDisplayHint()`에 raw fall 확률 안내 추가
- `postureItems()`를 raw 6-class 대신 UI용 비낙상 재정규화 분포 사용으로 변경

### src/app/page.dashboard/view.pug
- 웹캠 오버레이 좌상단의 `자세:` 라벨을 `postureDisplayCaption()` 기반으로 표시하도록 변경

## 기대 효과

- 최종 비낙상 상태에서 `fall`이 1위로 보이는 UI 혼동 제거
- 경고 미발생 상태와 화면 표시의 정합성 확보
- raw posture의 fall 신호는 완전히 숨기지 않고 안내 문구로만 유지
