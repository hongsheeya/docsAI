# AI Agent 엔진 — LLM 연동 및 SSE 스트리밍

- **ID**: 009
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
`struct/ai_agent.py` Sub-Struct를 생성하여 AI 관련 비즈니스 로직을 캡슐화. OpenAI/Anthropic/Google/Custom 4개 프로바이더 지원, 섹션 생성/재작성, 채팅, 질문 생성, 프로필 학습, 스트리밍 호출을 하나의 모듈에 통합. api.py의 인라인 AI 호출 로직을 ai_agent 활용으로 리팩토링.

## 변경 파일 목록

### 신규 생성
- `src/model/struct/ai_agent.py` — AIAgent Sub-Struct (generate_section, regenerate_section, chat, ask_question, learn_from_conversation, _call_llm, _call_llm_stream)

### 수정
- `src/model/struct.py` — `_AIAgent` 로드 + `ai_agent` 프로퍼티 추가
- `src/app/page.doc.write.item/api.py` — 인라인 AI 호출 → `struct.ai_agent` 위임, ask_ai 함수 추가
