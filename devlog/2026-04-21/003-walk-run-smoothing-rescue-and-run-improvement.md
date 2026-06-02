# walk/run smoothing rescue 보정 및 run 분리 개선

- **ID**: 003
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
walk/run detector-limited 샘플이 heuristic boost 이후에도 smoothing 단계에서 다시 `stand`로 굳는 문제를 추적했다.
특히 run 계열은 bbox 수평 이동량이 크지만 EMA/majority vote가 `stand`를 유지하는 패턴이 반복되어, smoothing 단계에서 x-motion 기반 rescue를 추가했다. walk는 같은 방식으로 확대 적용하면 서기 회귀가 발생해, 최종적으로는 `sit -> walk` rescue만 유지하고 `stand -> walk` 공격적 전환은 배제했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - posture window에 `center_x_span`, `center_dx_abs_mean`, `vert_horiz_ratio`, `speed_std`를 smoothing 입력으로 전달
  - `_smooth_posture_sequence()`에 x-motion 기반 `run` rescue 추가
  - `sit`로 굳는 일부 이동 샘플을 위한 제한적 `walk` rescue 추가
  - `stand` 회귀를 유발하던 aggressive `stand -> walk` smoothing rescue는 제거

## 검증 메모
- 12샘플 기준 혼동 요약
  - `stand`: 9/12 유지
  - `walk`: 3/12 (변화 없음)
  - `run`: 6/12 (기존 4/12 대비 개선)
  - `sit`: 6/12 (`no_windows` 2)
  - `lie`: 5/12 (`no_windows` 2)
  - `fall`: 11/12
- 결론
  - detector-limited `run`은 smoothing 단계까지 포함한 분리 개선이 확인됨
  - `walk`는 아직 stand와의 feature 중첩이 커서, 다음 단계는 detector 품질 점수 기반 게이트 또는 walk 전용 sequence scoring이 필요함
