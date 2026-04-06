# 대시보드 결과 UI 단순화 및 사용 설명서 정리

- **ID**: 012
- **날짜**: 2026-04-01
- **유형**: 기능 개선 + 문서 정리

## 작업 요약
분석 결과 화면의 세로 길이를 줄이고 한눈에 보이도록 결과 카드를 압축했다. 상단 3개 카드 높이를 맞추고, 분석 시간 상세는 접기/펼치기 UI로 바꿨다. 또한 `현재 연결된 모델 정보`, `분석 진단 메모`를 제거하고 파이프라인/관리자 페이지 링크로 대체했다. 판단 근거는 기여도 순서를 백엔드/프론트엔드에서 함께 보장하도록 정렬 메타데이터를 추가했다. 사용 설명서와 메인 소개 문구에서는 실제 구현 범위를 벗어난 설명을 정리했다.

## 변경 파일 목록

### Frontend — src/app/page.dashboard/view.ts
- 타이밍 상세 토글 상태 추가
- 요약 타이밍 2개만 표시하는 helper 추가
- 판단 근거를 `contribution_rank`/`contribution_score` 기준으로 정렬하는 fallback helper 추가

### Frontend — src/app/page.dashboard/view.pug
- 히어로 소개 문구를 한 줄형으로 축약
- 결과 상단 3카드 높이 통일 (`min-h`) 적용
- 분석 시간 상세를 접기/펼치기 버튼으로 전환
- `현재 연결된 모델 정보`, `분석 진단 메모` 카드 제거
- 파이프라인/관리자 이동 링크 추가
- 판단 근거 반복 렌더링을 `sortedAnalysisBasis()`로 변경

### Backend — src/model/struct/video_analysis.py
- `contribution_rank`, `contribution_score` 메타데이터를 XGBoost/RF 판단 근거에 추가
- 공통 `_sort_analysis_basis()` 추가
- 결과 조립 단계에서 비기여도성 기준 카드(`risk_threshold_rule`)를 판단 근거에 추가하지 않도록 정리
- 최종 `analysis_basis`를 기여도 정렬 기준으로 재정렬

### Frontend — src/app/page.manual/view.ts / view.pug
- 미구현/과장 가능성이 있는 멤버 관리, 마이페이지, 게시판, Help 카테고리 안내 제거
- 위험 알림, 로그인, 소개, 결과 보기 설명을 현재 구현 수준에 맞게 조정
- 분석 프로파일 `Fast/Precise`, `Auto` 선택 등 실제 화면과 다른 설명 제거

### Report — daily-report-2026-04-01.md
- 기존 보고 이후 추가 진행분 중심으로 일일보고 재작성
