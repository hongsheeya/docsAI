# behavior_summary 메서드 충돌 수정 및 대시보드 라우팅 검증

- **ID**: 001
- **날짜**: 2026-03-30
- **유형**: 버그 수정

## 작업 요약
`VideoAnalysis._behavior_summary()`를 결과 요약용 메서드로 중복 선언해 기존 행동 모델 요약 로더를 덮어쓰면서 `prototype_info()`와 `analyze_upload()` 경로가 깨진 문제를 수정했다. 결과 요약 메서드명을 분리하고 대시보드의 모델 옵션/분석 경로를 다시 점검했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - 결과용 메서드명을 `_behavior_result_summary()`로 변경
  - `analyze_upload()` 후처리 경로에서 새 메서드명 사용

## 검증
- normal build 성공
- `prototype_info()` 경로에서 다시 행동 모델 요약 로더를 정상 사용하도록 확인
- 대시보드 API 체인(`view.ts` → `api.py` → `VideoAnalysis`) 점검 완료
