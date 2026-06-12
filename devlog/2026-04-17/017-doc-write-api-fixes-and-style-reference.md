# 문서 작성 API 오류 수정 및 스타일 참고 기능 추가

- **ID**: 017
- **날짜**: 2026-04-17
- **유형**: 버그 수정

## 작업 요약
문서 상세 페이지 API 전체가 500 오류를 반환하던 문제를 수정하고, 팝업이 클릭 직후 열리지 않던 렌더링 문제를 해결했다.
또한 양식 없이 시작하는 자유 작성 흐름과 이전 문서를 참고해 사용자 말투/구성을 반영하는 기능을 추가했다.

## 변경 파일 목록

### App API
- `src/app/page.doc.write.item/api.py`
  - SSE 생성부 문법 오류 수정
  - `reference_docs()` API 추가
  - 설정 저장 시 이전 문서 참고 정보와 스타일 참고 텍스트 저장 로직 추가
- `src/app/page.doc.write/api.py`
  - `blank` source_type 생성 로직 추가

### Frontend
- `src/app/page.doc.write/view.ts`
  - 새 문서 모달 열기/닫기 시 즉시 렌더링 처리
- `src/app/page.doc.write/view.pug`
  - 자유 작성 시작 옵션 추가
- `src/app/page.doc.templates/view.ts`
  - 양식 모달 열기/닫기 시 즉시 렌더링 처리
- `src/app/page.doc.write.item/view.ts`
  - 이전 문서 목록 로드 및 선택 상태 관리 추가
  - `save_settings()` FormData 전송 옵션 수정
  - 이미지 업로드 FormData 전송 옵션 수정
- `src/app/page.doc.write.item/view.pug`
  - 이전 문서 참고 선택 UI 추가

### Model
- `src/model/struct/ai_agent.py`
  - 스타일 참고 컨텍스트를 AI 프롬프트에 반영
  - 프로필 저장 호출 인자 오류 수정
