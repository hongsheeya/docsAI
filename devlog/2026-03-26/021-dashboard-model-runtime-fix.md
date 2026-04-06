# 대시보드 모델 연동 및 0% 표시 복구

- **ID**: 021
- **날짜**: 2026-03-26
- **유형**: 버그 수정

## 작업 요약
분석 페이지에서 실제 추론 런타임과 연결된 모델 정보가 정확히 보이지 않던 문제를 수정했다. `person-feature-runtime`을 엔진 요약에 반영하고, 구형 로컬 캐시 결과가 최신 추론 결과를 덮어쓰며 0%처럼 보일 수 있던 문제를 차단했다. 또한 현재 연결된 person detector, fall classifier, YOLO 백업 모델 정보를 대시보드에서 직접 확인할 수 있도록 개선했다.

## 변경 파일 목록
### 백엔드
- `src/model/struct/video_analysis.py`
  - `trained_model` 정보에 person detector / fall classifier 상세 경로·지표 추가
  - `engine_summary`가 실제 사용 런타임(`person-feature-runtime` 포함)을 반영하도록 수정
  - 분석 결과에 `schema_version`, `runtime_warning`, `trained_model` 포함
  - person-feature의 feature 기반 `analysis_basis`가 문자열 요약에 덮어써지지 않도록 보존

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - 구형/불완전 로컬 캐시 결과 무효화 로직 추가
  - 캐시 저장 시 schema version 포함
- `src/app/page.dashboard/view.pug`
  - 현재 사용 엔진 key 표시
  - Person Detector / Fall Classifier / YOLO 백업 모델 정보 및 핵심 지표 표시

## 테스트 결과
- 프로젝트 빌드 성공
- 수정 파일 오류 없음
- person-feature 런타임이 연결된 상태에서 엔진/모델 정보를 화면에 표시할 수 있도록 결과 스키마 확인
