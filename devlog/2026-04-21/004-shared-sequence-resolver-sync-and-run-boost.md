# 공통 sequence resolver 동기화 및 run 최종 분리 강화

- **ID**: 004
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
RF-Dual/XG-Dual이 최종 posture label을 각각 따로 집계하던 구조를 공통 sequence resolver로 통합했다. 이 과정에서 smoothing 단계에서 전달되는 시퀀스 feature를 기반으로 detector-limited `run`의 최종 라벨을 한 번 더 복구하도록 정리했다.
walk는 같은 방식의 aggressive final rescue를 적용하면 서기 회귀가 즉시 발생해, 최종안에서는 `run` 위주 개선과 공통 resolver 동기화에 집중했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - `_resolve_posture_sequence_label()` 추가
  - RF-Dual/XG-Dual 모두 동일 helper로 최종 posture label 결정하도록 동기화
  - smoothing 입력에 x-motion feature 전달 유지
  - final resolver에서 detector-limited `run` 복구 규칙 유지
  - stand 회귀를 유발하는 sit/walk aggressive final rescue는 제외

## 검증 메모
- 12샘플 기준 최종 결과
  - `stand`: 9/12
  - `walk`: 3/12
  - `run`: 6/12
  - `sit`: 6/12 (`no_windows` 2)
  - `lie`: 5/12 (`no_windows` 2)
  - `fall`: 11/12
- 결론
  - 서비스 경로 간 최종 posture 집계 로직이 이제 공통 helper 하나로 정렬됨
  - `run`은 이전보다 개선됐고, `walk`는 여전히 detector 품질 한계가 우세한 상태라 다음 단계는 detector quality score 또는 별도 walk sequence scorer가 필요함
