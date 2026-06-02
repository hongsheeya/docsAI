# RF-Dual 런타임 동기화 및 chunk summary 예외 수정

- **ID**: 001
- **날짜**: 2026-04-24
- **유형**: 버그 수정

## 작업 요약
대시보드 업로드 분석이 오래된 RF-Dual 구형 경로를 타면서 13-feature RF 추론을 실행해 `33% 정상` fallback으로 내려가던 문제를 수정했다.
동시에 chunk 분석 요약이 없는 경우 `None.get()` 예외가 날 수 있는 지점을 방어하고, API가 최신 `video_analysis.py` 소스를 fresh-load 하도록 보강했다.

## 변경 파일 목록
### 업로드/분석 API
- `src/app/page.dashboard/api.py`
  - `video_analysis.py`를 요청 시점에 fresh-load 하도록 변경해 캐시된 구버전 모델 로직을 우회
  - 기존 `analyze_upload()` 예외 처리 유지

### 분석 모델
- `src/model/struct/video_analysis.py`
  - `_infer_rf_dual()` 앞부분에 남아 있던 구형 조기 `return` 블록 제거
  - 실제 단일 패스 RF-Dual 구현이 실행되도록 복구
  - `chunk_analysis.summary`가 `None`일 때도 안전하게 처리하도록 수정

## 검증
- 직접 소스 실행 기준 `analyze_upload()` 결과가 `heuristic-fallback 0.33`에서 `rf-dual` 정상 결과로 변경됨을 확인
- `season-wiz-project=main` 쿠키를 포함한 실제 API 호출에서 `code=200`, `runtime_key=rf-dual`, `risk_score=0.1267` 응답을 확인
- 메인 프로젝트 클린 빌드(`wiz project build --project=main -c`) 완료
