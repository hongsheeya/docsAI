# 서기 복구: knee support feature 및 static stand override 추가

- **ID**: 008
- **날짜**: 2026-04-20
- **유형**: 버그 수정

## 작업 요약
서기 클래스가 거의 전부 `sit`/`walk`/`lie`로 붕괴하는 원인을 다시 추적한 결과, lower-body 판단이 `min(knee_angles)` 한 개에 과도하게 의존하고 있었고 최근 gait rescue가 약한 상체 흔들림까지 이동으로 해석해 서기를 밀어내고 있었다.
이를 해결하기 위해 support-leg 기준 보조 feature를 추가하고, 정적인 upright partial-body pose를 `stand`로 복구하는 override 규칙을 추가했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - `pose_knee_support_mean`, `pose_knee_support_min`, `support_leg_ratio` feature 추가
  - `gait_active`, `knees_straight`, `knees_bent` 판정식을 worst-leg 의존 완화 방향으로 수정
  - `upright_partial_stand` 조건과 `walk/lie/sit -> stand` static override 규칙 추가
  - `walk` rescue 트리거를 더 보수적으로 조정하여 서기 샘플을 과도하게 이동 클래스에 빼앗기지 않도록 수정

## 검증 메모
- 8개 서기 샘플 재검증 결과: `0/8 -> 6/8`
- 전체 8샘플 기준 요약
  - `stand`: 6/8
  - `walk`: 3/8
  - `run`: 2/8
  - `sit`: 3/8
  - `lie`: 4/8
  - `fall`: 7/8
- 결론적으로 이번 수정은 서기 붕괴 복구에 초점을 맞춘 조정이며, `walk/run` detector-limited 샘플은 추가 분리가 더 필요함
