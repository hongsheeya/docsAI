# 웹캠 로그 스크롤 수정

- **ID**: 001
- **날짜**: 2026-04-07
- **유형**: 버그 수정

## 작업 요약
웹캠 모드 로그 패널 스크롤이 동작하지 않던 문제 수정. `:host` 스타일을 flex-column으로 변경하고, 웹캠 섹션을 `h-full` 대신 `flex-1 min-h-0`으로 변경하여 높이 체인을 정상화.

## 변경 파일 목록

### view.scss
- `:host { display: block; height: 100%; }` → `display: flex; flex-direction: column; height: 100%;`
- flex-column으로 nav + section이 정확히 100% 공간 분배

### view.pug
- `nav`: `sticky top-0` 제거, `shrink-0` 추가 (flex 수축 방지)
- 웹캠 `section`: `h-full` → `flex-1 min-h-0` (남은 공간 정확히 채움)
- `#logScrollContainer`: `overscroll-behavior: contain` 추가 (스크롤 체이닝 방지)

### view.ts
- `scrollLogToBottom()`: `scrollTop = 0` → `scrollTo({ top: 0, behavior: 'smooth' })`, 타임아웃 50→120ms
