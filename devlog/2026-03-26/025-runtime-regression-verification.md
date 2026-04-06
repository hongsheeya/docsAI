# 런타임·성능·표시 일치성 회귀 검증

- **ID**: 025
- **날짜**: 2026-03-26
- **유형**: 검증

## 작업 요약
낙상/비낙상 대표 샘플을 대상으로 `fast`/`balanced` 프로파일 각각의 결과를 검증하고, person-feature → trained-yolo → heuristic fallback 전환 규칙이 정상 동작하는지 확인했다. 검증 과정에서 heuristic fallback 결과에 `runtime_key`가 없던 문제를 발견해 즉시 수정했다.

## 변경 파일 목록
### 서버 분석 로직
- `src/model/struct/video_analysis.py`
  - heuristic fallback 결과에 `runtime_key`, `runtime_label`, `behavior_inference` 추가

## 테스트 결과
- fall fast: `person-feature-runtime`, score `0.7057`, behavior `낙상`, basis `7`, overview `4`
- fall balanced: `person-feature-runtime`, score `0.7573`, behavior `낙상`
- normal fast: `person-feature-runtime`, score `0.4331`, behavior `걷기`
- normal balanced: `person-feature-runtime`, score `0.1944`, behavior `걷기`
- classifier 파일 제거 시: `trained-yolo-runtime` fallback 확인
- classifier 파일 손상 시: `heuristic-fallback` 전환 및 `runtime_warning` 확인
- 빌드 성공 및 오류 없음
