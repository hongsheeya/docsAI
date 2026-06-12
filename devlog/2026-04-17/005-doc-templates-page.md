# 양식 관리 페이지 (page.doc.templates)

- **ID**: 005
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 양식(HWP/DOCX/PDF) 등록·관리 페이지 구현. 파일 업로드 후 자동 텍스트 추출 및 필드 감지. 양식 목록 카드 UI, 등록/수정 모달, 삭제 기능.

## 변경 파일 목록

### 신규 생성
- `src/app/page.doc.templates/app.json` — 메타데이터 (viewuri: /doc/templates, controller: user)
- `src/app/page.doc.templates/view.ts` — 양식 CRUD 로직, 파일 업로드
- `src/app/page.doc.templates/view.pug` — 양식 목록 카드 + 등록 모달
- `src/app/page.doc.templates/view.scss` — :host 블록
- `src/app/page.doc.templates/api.py` — list, create, update, delete + 파일 파싱(_parse_file, _detect_fields)
