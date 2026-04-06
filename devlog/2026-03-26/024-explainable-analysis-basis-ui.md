# 설명형 판단 근거 UI 고도화

- **ID**: 024
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
기존 숫자 나열 수준이던 `analysis_basis`를 해석 가능한 구조로 개선하고, 모델 정보 영역과 판단 근거 영역을 분리했다. 대표 위험 구간 시각, 최대 하강 속도, 수직 이동량, 바닥 근접도, 자세 변화, 높이 변화율을 각각 설명형 카드로 표시할 수 있도록 데이터 구조와 UI를 변경했다.

## 변경 파일 목록
### 서버 분석 로직
- `src/model/struct/video_analysis.py`
  - person-feature / trained-yolo / heuristic 모두 구조화된 `analysis_basis` 반환
  - `analysis_overview`와 `analysis_basis`를 분리
  - 행동 분류 근거를 `analysis_basis`에 추가

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - 판단 근거 카드 색상 helper 추가
- `src/app/page.dashboard/view.pug`
  - 사용 엔진 요약은 `analysis_overview`로 표시
  - 별도 `판단 근거` 섹션에서 설명형 카드 렌더링
  - 모델 정보와 판단 근거 영역 분리 유지

## 테스트 결과
- person-feature 결과에서 구조화된 판단 근거 6개 생성 확인
- 빌드 성공 및 오류 없음
