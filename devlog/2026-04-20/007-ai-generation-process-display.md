# AI 문서 생성 과정 전체 실시간 표시

- **ID**: 007
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
문서 AI 생성 시 프롬프트/응답 과정을 SSE 이벤트로 전달하여 프론트엔드에서 실시간 표시하도록 구현. 시스템 프롬프트, 사용자 프롬프트, AI 응답을 접기/펼치기 가능한 구조화된 로그 콘솔로 표시.

## 변경 파일 목록

### Model (src/model/struct/)
- **ai_agent.py**: `generate_field_values()`, `generate_section()`에 `events=None` 파라미터 추가
  - 자동추정 완료 detail 이벤트, LLM 호출 전 prompt 이벤트, LLM 응답 후 ai_response 이벤트 수집

### App (src/app/page.doc.write.item/)
- **api.py**: `generate()` SSE 함수에서 events 리스트를 ai_agent 메서드에 전달, 수집된 이벤트를 SSE로 yield
- **view.ts**: `generateLogs`를 `any[]`로 변경, `expandedLogIndices: Set<number>` 추가, SSE 핸들러에서 prompt/ai_response/detail 이벤트 처리, `toggleLogExpand()`, `scrollLogToBottom()` 메서드 추가
- **view.pug**: Step 2 로그 콘솔을 구조화된 렌더링으로 교체 (텍스트/섹션/디테일/프롬프트/AI응답 각각 다른 스타일, 프롬프트와 AI응답은 클릭으로 접기/펼치기)
