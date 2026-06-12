# AI 설정 페이지 (page.ai.settings)

- **ID**: 004
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
AI Provider 설정 관리 페이지 구현. OpenAI/Anthropic/Google/Custom 지원. API Key 입력, 모델 선택, 연결 테스트 기능 포함. 활성 설정 전환 및 CRUD 기능.

## 변경 파일 목록

### 신규 생성
- `src/app/page.ai.settings/app.json` — 페이지 메타데이터 (viewuri: /ai/settings, controller: admin)
- `src/app/page.ai.settings/view.ts` — AI 설정 CRUD UI 로직, 연결 테스트
- `src/app/page.ai.settings/view.pug` — 카드형 폼 + 설정 목록 UI
- `src/app/page.ai.settings/view.scss` — :host 블록
- `src/app/page.ai.settings/api.py` — list, create, update, delete, set_active, test_connection 함수
