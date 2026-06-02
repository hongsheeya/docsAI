# walk/run 검출 한계 샘플 분리 보정

- **ID**: 002
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
walk/run 샘플 중 포즈 주기성(`center_y_periodicity`, `step_period_est`)이 거의 0으로 떨어지는 detector-limited 케이스를 다시 분석했다. 이 계열은 실제로는 좌우 이동량이 크지만 기존 휴리스틱이 상하 변동과 무릎 주기성에 치우쳐 있어 `stand`로 눌리는 문제가 있었다.
이에 bbox 기반 수평 이동 feature를 추가하고, 특히 run 계열의 강한 수평 이동을 별도 rescue 신호로 반영했다. 동시에 서기 회귀가 다시 발생하지 않도록 walk 쪽 과한 x-motion rescue는 제거하고 균형 상태를 유지했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - feature window에 `center_dx_abs_mean`, `center_x_span` 추가
  - detector-limited run 샘플을 위한 `strong_run_motion` 기반 rescue 추가
  - walk용 x-motion rescue는 서기 회귀를 유발해 최종안에서 제외
  - 결과적으로 서기 성능을 유지하면서 run 분리를 일부 개선

## 검증 메모
- 12샘플 기준 혼동 요약
  - `stand`: 9/12 유지
  - `walk`: 3/12
  - `run`: 4/12 (기존 2/12 대비 개선)
  - `sit`: 6/12 (`no_windows` 2)
  - `lie`: 5/12 (`no_windows` 2)
  - `fall`: 11/12
- 결론
  - detector-limited `run`은 bbox 수평 이동 feature로 일부 분리 개선됨
  - `walk`는 여전히 stand와 feature 겹침이 커서, 다음 단계에서는 detector 품질 게이트 또는 smoothing 정책 분리가 필요함
