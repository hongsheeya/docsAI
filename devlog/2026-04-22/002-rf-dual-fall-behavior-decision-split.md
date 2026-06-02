# RF-Dual 낙상/행동 판정 분리

- **ID**: 002
- **날짜**: 2026-04-22
- **유형**: 리팩토링

## 작업 요약
RF-Dual 파이프라인에서 RF 이진 낙상 판정과 XG-Posture 행동분류 채택 규칙을 분리했다.
두 모델은 계속 동시에 계산하지만, 최종 낙상 여부는 RF 결과만 사용하고, 행동분류는 RF가 비낙상일 때만 최종 결과로 채택하도록 변경했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - RF-Dual 최종 판정에서 `arbitrate_decision` 의존 제거
  - `fall_result`, `behavior_result` 구조 추가
  - 비낙상일 때만 행동분류 결과를 채택하도록 `behavior_accepted` 규칙 추가
- `devlog.md`
  - 작업 요약 행 추가

## 확인 결과
- 대표 샘플 재측정 결과 posture 추가 계산 비용은 약 0.004~0.017초 수준으로 매우 작았다.
- 기존에 `posture_label=sit` 영향으로 `fall_suspected`였던 일부 낙상 샘플은, 분리 후 RF-only 기준으로 `fall_confirmed`로 정리되었다.
- 비낙상 샘플은 `posture_only` 상태로 행동분류 결과가 정상 채택되었다.
