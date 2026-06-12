# 파일 파싱 엔진 (HWP/DOCX/PDF)

- **ID**: 008
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
`struct/file_parser.py` Sub-Struct를 생성하여 HWP, DOCX, PDF 파일의 텍스트/구조 추출 및 양식 필드 자동 감지를 구현. pip 패키지(python-docx, pdfplumber) 설치. 기존 page.doc.templates/api.py와 page.doc.write.item/api.py를 file_parser 활용으로 리팩토링.

## 변경 파일 목록

### 신규 생성
- `src/model/struct/file_parser.py` — FileParser Sub-Struct (parse, parse_docx, parse_pdf, parse_hwp, detect_fields, create_sections_from_template, parse_uploaded_file)

### 수정
- `src/model/struct.py` — `_FileParser` 로드 + `file_parser` 프로퍼티 추가
- `src/app/page.doc.templates/api.py` — `_parse_file()` 인라인 로직 → `struct.file_parser` 호출로 대체
- `src/app/page.doc.write.item/api.py` — generate 함수에서 file_parser 활용, 참고자료 파싱 추가

### 패키지 설치
- python-docx 1.2.0, pdfplumber 0.11.9
