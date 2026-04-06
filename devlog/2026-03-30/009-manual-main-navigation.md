# 사용설명서 ↔ 메인 페이지 네비게이션

- **ID**: 009
- **날짜**: 2026-03-30
- **유형**: 기능 추가

## 작업 요약
사용설명서 페이지(/manual) 상단에 "메인으로" 돌아가기 버튼을 추가하고, 대시보드 상단 nav에 "사용 설명서" 링크를 추가하여 양방향 네비게이션을 구현.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.manual/view.ts`: goMain() 메서드 추가
- `src/app/page.manual/view.pug`: 헤더를 전체 디바이스에 표시하도록 변경, 좌상단 "메인으로" 버튼(화살표 아이콘) 추가
- `src/app/page.dashboard/view.ts`: goManualPage() 메서드 추가
- `src/app/page.dashboard/view.pug`: nav 영역에 "사용 설명서" 링크 추가
