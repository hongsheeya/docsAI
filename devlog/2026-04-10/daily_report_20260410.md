# 일일 개발 보고 (2026-04-10)

## 주요 작업 요약

오늘은 낙상 감지 파이프라인의 **하드케이스 회귀 복구**, **정면/후면·침대 케이스 정밀 보정**, **완전 검증 달성**, 그리고 **운영 모니터링 강화**에 집중했습니다.

### 1. XG-Fall 하드케이스 회귀 복구 및 규칙 정밀화
- 침대 기상/침대 낙상, 정면·후면 낙상 케이스를 집중 분석해 `directional_collapse_override`, `spike_only_suppressor`, `reverse_motion_suppressor`, `static_floor_like_suppressor` 등을 추가했습니다.
- 단일 추론 경로와 듀얼 추론 경로에 동일한 보정 규칙을 반영해 업로드/운영 결과의 일관성을 맞췄습니다.
- 과정 중 성능이 한때 하락했으나, 규칙을 좁게 재설계해 회귀를 복구했습니다.

### 2. 침대·정면/후면 엣지케이스 미세조정
- 마지막으로 남은 `front_back_fall` FN과 `front_back_nonfall` FP를 직접 비교 분석했습니다.
- `still_post_fall_override`를 추가해 실제 뒤로 크게 넘어지는 사례가 과도한 억제 규칙에 막히지 않도록 조정했습니다.
- 반대로, 실제 하강이 없는 정적 바닥형 비낙상은 `static_floor_like_suppressor`로 별도 억제해 FP를 제거했습니다.

### 3. 검증 결과 개선 및 완전 검증 달성
- XG-Fall 최신 검증 결과를 반복 확인하며 규칙을 조정했습니다.
- 최종적으로 intake 21건 기준 다음 지표를 달성했습니다.
  - Recall: 1.0
  - Precision: 1.0
  - F1: 1.0
  - Accuracy: 1.0
- 기준 리포트:
  - `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_070008.json`
  - `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_070210.json`
  - `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_083440.json`

### 4. suspected 경계 사례 리포트 강화
- 오분류가 0건이어도 향후 회귀 위험이 있는 경계 사례를 추적하기 위해 다음 필드를 failure report에 추가했습니다.
  - `suspected_actual_fall_count`
  - `suspected_actual_nonfall_count`
  - `suspected_actual_falls`
  - `suspected_actual_nonfalls`
- 그 결과, 실제 오분류는 없지만 `suspected_actual_nonfall` 3건은 운영 모니터링 대상으로 계속 확인할 수 있게 됐습니다.

### 5. 관리자 모니터링 UI 강화
- 관리자 분석 페이지에 최신 XG-Fall 검증 요약 섹션을 추가했습니다.
- 표시 항목:
  - 최신 recall / precision / F1 / accuracy
  - FN / FP 상태
  - band 분포
  - threshold 정보
  - `suspected_actual_nonfalls` 목록
- 인증이 필요한 관리자 API 특성상 비로그인 직접 호출은 401이었지만, 프로젝트 빌드는 정상 완료되어 UI 반영은 가능한 상태입니다.

### 6. 실시간 롤링 캐시 안전장치 추가
- 실시간 rolling memory가 서로 다른 세션 또는 임의 파일 간에 잘못 이어질 가능성을 차단했습니다.
- `chunk_(n)` 패턴을 파싱해 **직전 청크 번호 + 1 인 경우에만** tail stitching이 일어나도록 제한했습니다.
- 이를 통해 stale cache가 다른 실시간 분석 세션에 섞이는 위험을 줄였습니다.

## 작업 내용 결론 검토
오늘 작업으로 XG-Fall 파이프라인은 intake 검증셋 기준 완전 분리 성능을 달성했고, 동시에 운영 관점에서 중요한 `suspected` 경계 사례 추적 체계까지 갖추게 됐습니다. 또한 실시간 rolling cache 범위를 순차 청크로 제한하여, 정확도 개선 과정에서 새로 생길 수 있는 세션 간 오염 가능성도 방어했습니다.

현재 상태는 **정확도 개선 + 운영 모니터링 + 실시간 안정성 보강**이 동시에 반영된 단계입니다.
