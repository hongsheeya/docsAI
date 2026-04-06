# 웹캠 모드 화면 표시 오류 전수 조사 및 수정

- **ID**: 021
- **날짜**: 2026-04-06
- **유형**: 버그 수정

## 작업 요약
웹캠 모드에서 카메라 프리뷰, 분석 컨트롤, 로그 패널이 표시되지 않는 문제를 전수 조사하여 근본 원인(CSS Grid row height 미지정)을 찾아 수정했다.

## 변경 파일 목록

### layout.sidebar
- `view.scss`: `:host`를 `display: flex; flex-direction: column; height: 100%; overflow: hidden;`으로 변경
- `view.pug`: 내부 div를 `flex flex-col h-full` → `flex-1 min-h-0 overflow-auto`로 변경

### page.dashboard
- `view.pug` (L3): 웹캠 모드 외부 div `h-screen` → `h-full` (레이아웃 내 중첩 방지)
- `view.pug` (L66): Grid에 `grid-rows-1` 추가, `xl:grid-cols-[1fr_380px]` → `grid-cols-[1fr_380px]` (항상 2컬럼)
- 이전 세션 수정 포함: placeholder 카메라 아이콘, 로그 패널 항상 표시, section calc 제거, `:host` 스타일

## 근본 원인 분석
CSS Grid의 `grid-template-rows` 미지정 → implicit rows `auto` → flex-1 자식이 0px로 축소. `grid-rows-1`(= `repeat(1, minmax(0, 1fr))`) 추가로 행이 남은 공간을 채우도록 수정.
