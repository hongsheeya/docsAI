# gait/lie/fall 경계 미세조정 및 런타임 재검증

- **ID**: 007
- **날짜**: 2026-04-20
- **유형**: 버그 수정

## 작업 요약
남은 행동분류 경계(`walk`, `run`, `lie`, `fall`)를 대상으로 실제 intake 샘플 feature 분포를 다시 확인한 뒤, `video_analysis.py`의 휴리스틱 경계를 보정했다.
특히 gait posture 기반 `walk/run` rescue, low-profile 정적 자세에 대한 `lie` rescue, floor spread·upper motion 기반 `fall` rescue를 추가하고 샘플 런타임 분류를 다시 검증했다.

## 변경 파일 목록

### 모델 로직
- `src/model/struct/video_analysis.py`
  - `collapse_impulse`, `slow_descent_ratio`, `tilt_change_duration`, `n_points`, `avg_conf`를 휴리스틱 판단에 사용하도록 확장
  - gait posture + 주기/모션 신호를 함께 보는 `walk/run` rescue 규칙 추가
  - torso tilt가 낮더라도 높이가 매우 낮고 정적인 경우 `lie`로 복구하는 규칙 추가
  - synthetic fall 계열에서 자주 보인 `upper_body_motion` + `spread_after_descent` + low-profile 조합을 `fall`로 복구하는 규칙 추가
  - 과도한 `walk` rescue를 줄이기 위해 `stand`와 충돌하는 조건을 재조정

## 검증 메모
- 6개 클래스 샘플(각 8개) 재검증 결과
  - `walk`: 5/8
  - `run`: 1/8
  - `lie`: 4/8
  - `fall`: 7/8
- `fall`은 synthetic collapse 계열에서 복구가 크게 개선됨
- 반면 일부 `stand`/`run` 샘플은 pose가 매우 낮은 프로파일로 추출되어 여전히 `lie`/`stand` 쪽으로 붕괴하는 문제가 남아 있음
- 남은 과제는 detector-limited 샘플에 대한 별도 품질 게이트 또는 학습데이터 정제 검토
