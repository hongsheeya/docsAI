# 사이드바 Outputly 브랜딩 UI 변경

- **ID**: 002
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
사이드바를 Outputly 다크 테마(bg-stone-900)로 전면 재구성. 로고, 네비게이션(대시보드/문서 작성/양식 관리/회원 관리/AI 설정), 하단 유저 프로필+로그아웃 구현. layout.sidebar도 flex h-full 구조로 변경.

## 변경 파일 목록

### Component (component.nav.sidebar)
- `view.pug`: 다크 테마 사이드바 전면 재구성 (Outputly 브랜딩, 네비 메뉴, 유저 프로필)
- `view.ts`: `activeClass()` 다크 테마용 수정, `navigate()` / `logout()` 메서드 추가

### Layout (layout.sidebar)  
- `view.pug`: flex h-full 구조로 단순화 (사이드바 + 우측 컨텐츠)
- `view.scss`: `:host { display: block; height: 100vh; }` 추가
- `view.ts`: 불필요한 HostListener/isActive 제거, 심플화
