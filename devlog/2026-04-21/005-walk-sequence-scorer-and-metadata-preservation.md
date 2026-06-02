# walk 시퀀스 scorer 및 metadata 보존 보강

- **ID**: 005
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
XG-Posture 시퀀스 최종 판정 단계에서 스무딩 이후 이동 메타데이터가 소실되어 `walk`/`run` 후속 규칙이 실질적으로 0값 기준으로 동작하던 문제를 수정했다.
스무딩 결과에 수평 이동·속도·검출 품질 메타데이터를 유지하고, 최종 `walk` 승격 규칙을 `walk majority` 경로와 `strong motion override` 경로로 분리해 `stand` 회귀를 억제하면서 `walk` 샘플을 일부 추가 복구했다.

## 변경 파일 목록
### 모델/추론
- `src/model/struct/video_analysis.py`
  - posture window → smoothing → final resolver 경로에 `center_x_span`, `center_dx_abs_mean`, `vert_horiz_ratio`, `speed_std`, `avg_conf`, `lower_body_visibility` 전달 유지
  - `_smooth_posture_sequence()` 결과에 시퀀스 후처리용 메타데이터 보존
  - `_resolve_posture_sequence_label()`에 `walk majority` / `strong motion override` 이중 경로 추가
  - `run` 최종 승격 규칙은 유지하면서 `walk` 규칙을 보수적으로 재구성

## 검증 결과
- 12개 샘플 기준 posture sequence 재검증
  - `stand`: 9/12
  - `walk`: 4/12
  - `run`: 6/12
  - `sit`: 6/12 (`no_windows` 2)
  - `lie`: 5/12 (`no_windows` 2)
  - `fall`: 11/12
- 이전 균형 상태(`stand` 9/12)를 유지하면서 `walk`를 3/12 → 4/12로 개선했다.
- 잔여 `walk` 실패 샘플은 여전히 detector 품질 및 `stand` 확률 우세가 커서, 추가 개선은 더 강한 sequence quality gate 또는 detector 보강이 필요하다.
