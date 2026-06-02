# 발표 자료 웹 페이지 (PPT 스타일 슬라이드) 구현

- **ID**: 002
- **날짜**: 2026-04-27
- **유형**: 기능 추가

## 작업 요약
`docs/presentation/2026-04-27-rf-dual-audit-deck.md`에 작성된 RF-Dual 발표 내용
(16개 섹션)을 WIZ 사이트 내 PPT 스타일 서브페이지(`/presentation`)로 구현했다.

## 변경 파일 목록

### 신규 생성
- `src/app/page.presentation/app.json` — layout.empty, viewuri /presentation
- `src/app/page.presentation/view.ts` — 15개 슬라이드 데이터 + 키보드 네비게이션 로직
- `src/app/page.presentation/view.pug` — PPT 슬라이드 UI 템플릿
- `src/app/page.presentation/view.scss` — 발표용 전용 스타일

### 수정
- `src/app/component.nav.sidebar/view.pug` — Help 섹션에 "RF-Dual 발표자료" 메뉴 추가

## 슬라이드 구성 (15개)
1. 커버 (타이틀 슬라이드)
2. 개요 — 목표·운영 결론·정리 범위
3. 문제 정의 — 단일 모델 한계 (2열 비교)
4. 전체 판단 파이프라인 (flow 다이어그램)
5. RF-Dual 설명 및 성능
6. 모델 2개 중첩 이유 (2열 비교)
7. 각 모델 학습 현황 (비교 테이블)
8. 데이터 수집 및 학습 방법
9. sit/lie 판단 경계 보정 (upright_sit_guard)
10. 데이터 누수 감사 결과 (테이블)
11. 현재 한계점
12. 개선 방향 (단기·중기·장기)
13. 실제 오분류 사례 3건 (cases 카드)
14. 수정 전후 비교표 (멀티 테이블)
15. 향후 실험 계획 + 결론 커버

## 주요 기능
- 키보드 ← → Space 이동 / Esc 나가기 / Tab 목록 패널
- 상단 진행률 바 (indigo→violet 그라디언트)
- 슬라이드 목록 오버뷰 패널 (오른쪽 슬라이드인)
- 슬라이드 타입: cover / bullets / twocol / pipeline / table / cases
- layout.empty 사용 — 화면 전체(full-screen) 발표 모드
