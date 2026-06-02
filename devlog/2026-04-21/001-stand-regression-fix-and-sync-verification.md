# 서기 회귀 복구 및 동기화 검증

- **ID**: 001
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
서기 복구 이후 다시 오분류가 반복된 원인을 재점검했다. 핵심 원인은 `worst-leg knee` 의존을 완화하는 수정은 맞았지만, 이후 추가 실험 과정에서 gait 성격의 rescue/override를 과도하게 건드리면 서기 샘플이 다시 `walk`/`lie`로 무너진다는 점이었다.
최종적으로는 서기 복구가 안정적으로 유지되는 규칙 조합으로 되돌리고, 실제 서비스 경로에서 업로드와 RF-Dual/XG-Dual posture 보정이 동일한 함수를 공유하는지 함께 확인했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - `pose_knee_support_mean`, `pose_knee_support_min`, `support_leg_ratio` 기반 서기 복구 규칙 유지
  - 서기를 다시 무너뜨린 실험성 수평 이동 비율 조정은 롤백하여 안정 상태 복구
  - 업로드/RF-Dual/XG-Dual 양쪽 posture 보정 경로가 동일한 `_posture_heuristic_boost()`를 사용함을 점검

## 검증 메모
- 12개 샘플 기준 혼동 요약
  - `stand`: 9/12
  - `walk`: 3/12
  - `run`: 2/12
  - `sit`: 6/12 (`no_windows` 2)
  - `lie`: 5/12 (`no_windows` 2)
  - `fall`: 11/12
- 동기화 확인
  - `src/model/struct/video_analysis.py` 내부에서 XG-Dual posture 경로와 RF-Dual posture 경로가 모두 `_posture_heuristic_boost()`를 공통 호출
  - 대시보드 기본 모델 선택값과 백엔드 기본 모델 타입이 모두 `rf-dual`로 맞춰져 있음
- 결론
  - 이번 작업으로 서기가 다시 무너지는 회귀는 정리했고, 서비스 경로 상 동기화 누락은 확인되지 않았음
  - 남은 문제는 검출 품질 제한이 큰 `walk/run` 샘플의 별도 개선 과제임
