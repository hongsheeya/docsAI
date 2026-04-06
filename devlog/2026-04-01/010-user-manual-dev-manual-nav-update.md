# 사용 설명서 페이지 생성 및 네비게이션 연동

- **ID**: 010
- **날짜**: 2026-04-01
- **유형**: 기능 추가

## 작업 요약
사용자용 사용 설명서 서브페이지(page.manual)를 생성하고, 개발자용 매뉴얼(manual.md)을 작성하였다. 대시보드 상단 네비게이션의 "분석 실행" 링크를 "사용 설명서" 버튼으로 교체하고, 사이드바에 Help 카테고리를 추가하여 매뉴얼 접근성을 확보하였다. 이후 변경 사항을 양쪽 매뉴얼 문서에 모두 반영하여 최종 정합성을 확보하였다.

## 변경 파일 목록

### 신규 생성
| 파일 | 변경 내용 |
|------|----------|
| `src/app/page.manual/app.json` | 사용 설명서 앱 메타데이터 (viewuri: /manual, controller: base, layout: layout.sidebar) |
| `src/app/page.manual/view.pug` | 14개 섹션 사용 설명서 Pug 템플릿 (서비스 소개, 로그인, 대시보드, 업로드 분석, 웹캠, 결과 보기, 피드백, 위험 알림, 파이프라인, 관리자, 멤버, 마이페이지, 게시판, FAQ) |
| `src/app/page.manual/view.ts` | TOC 사이드바 네비게이션, 섹션 스크롤, 모바일 사이드바 토글 |
| `src/app/page.manual/view.scss` | :host 블록 스타일, scroll-margin-top 설정 |
| `manual.md` | 개발자 매뉴얼 (14장, 시스템 개요~트러블슈팅, ~650줄) |

### 수정
| 파일 | 변경 내용 |
|------|----------|
| `src/app/page.dashboard/view.pug` | 상단 네비게이션 "분석 실행" 앵커 → "사용 설명서" 버튼(책 아이콘 + goManualPage()) 교체 |
| `src/app/page.dashboard/view.ts` | `goManualPage()` 메서드 추가 (service.href('/manual')) |
| `src/app/component.nav.sidebar/view.pug` | Help 카테고리 추가, "사용 설명서" 링크 (routerLink="/manual", 책 아이콘) |
| `src/app/page.manual/view.pug` | 서비스 소개에 "접근 방법" 서브섹션 추가, 대시보드 섹션에 "상단 네비게이션 바" 서브섹션 추가 |
| `manual.md` | 갱신일 2026-04-01, 사이드바 카테고리 구조 추가, 대시보드 상단 네비게이션 바 테이블 추가 |
