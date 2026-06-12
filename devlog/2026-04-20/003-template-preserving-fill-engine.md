# 양식 원본 유지형 문서 완성 엔진 개발

- **ID**: 003
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
DOCX 양식의 플레이스홀더와 빈칸을 채우는 원본 양식 유지형 생성 흐름을 추가했다. AI는 장문 초안 대신 필드 값 생성을 우선 수행하고, 생성된 값을 DOCX 원본에 삽입한 뒤 결과 문서를 다시 파싱하여 검토/내보내기에 재사용하도록 구성했다.

## 변경 파일 목록
- src/model/struct/file_parser.py — DOCX 치환/저장 함수 추가
- src/model/struct/ai_agent.py — 필드 값 생성 및 추정 로직 추가
- src/app/page.doc.write.item/api.py — generate()를 필드 생성 → DOCX 삽입 흐름으로 개편
- src/model/struct/doc_export.py — 생성된 DOCX 결과물을 그대로 다운로드/미리보기 가능하도록 수정
