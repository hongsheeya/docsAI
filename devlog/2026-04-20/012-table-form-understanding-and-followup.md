# 표 중심 양식 해석 강화 및 추가 정보 질문 유도 흐름 구현

- **ID**: 012
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
서두형 문서가 아닌 표 중심 양식에서도 AI가 좌측 라벨, 상단 헤더, 행 대표값, 상위 구역 제목을 함께 읽어 빈칸의 의미를 추론하도록 보강했다. 또한 추정이 어려운 항목은 생성 단계에서 후속 질문으로 정리해 사용자에게 보여주고, 설정 보완이나 AI 채팅 답변으로 이어지도록 유도 흐름을 추가했다.

## 변경 파일 목록

### Backend — Model/Struct
- `src/model/struct/file_parser.py`
  - 표 빈칸 감지 로직을 재작성하여 key-value, matrix, 구역형 표 구조를 함께 추론
  - 각 빈칸의 주변 셀 요약과 문맥 설명을 생성해 AI 프롬프트 품질 향상
- `src/model/struct/ai_agent.py`
  - `build_context()`에 표 기반 채움 힌트 추가
  - 필드 생성 프롬프트에 표 양식 해석 규칙 추가
  - 비어 있는 핵심 항목 기준 후속 질문 리스트 생성 로직 추가

### Backend — App API
- `src/app/page.doc.write.item/api.py`
  - 생성 SSE에 `needs_input` 이벤트 추가
  - `content_json`에 `missing_fields`, `followup_questions` 저장

### Frontend — 문서 작성 상세
- `src/app/page.doc.write.item/view.ts`
  - 생성 중 후속 질문/미확정 항목 상태 추가
  - 질문 클릭 시 검토 탭 AI 채팅으로 이어지는 동선 추가
- `src/app/page.doc.write.item/view.pug`
  - Step 2 생성 화면에 추가 정보 요청 패널과 액션 버튼 추가

## 검증
- 수정 파일 진단 오류 없음 확인
- 프로젝트 일반 빌드 성공 확인