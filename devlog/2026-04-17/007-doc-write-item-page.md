# 문서 작성 상세 페이지 (3-Step 플로우)

- **ID**: 007
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 작성 상세 페이지(`page.doc.write.item`)를 3단계 플로우(설정 → AI 자동생성 → 검토/수정)로 구현. SSE 스트리밍 기반 AI 문서 생성, AI 채팅 수정, 섹션별 편집/재작성 기능, Router NavigationEnd 탭 전환 포함.

## 변경 파일 목록

### 신규 생성
- `src/app/page.doc.write.item/app.json` — viewuri `/doc/write/:id/:tab?`, controller: user, layout: layout.sidebar
- `src/app/page.doc.write.item/view.ts` — 3-Step 컴포넌트 (settings/generate/review), SSE 스트리밍, AI 채팅, 섹션 편집
- `src/app/page.doc.write.item/view.pug` — 3단계 UI (설정폼, 프로그레스바+로그, 분할패널 검토)
- `src/app/page.doc.write.item/view.scss` — :host 블록
- `src/app/page.doc.write.item/api.py` — detail, sections, chats, save_settings, generate(SSE), chat(AI), save_section, regenerate_section
