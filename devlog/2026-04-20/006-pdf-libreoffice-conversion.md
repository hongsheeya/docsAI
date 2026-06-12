# PDF 다운로드 LibreOffice 기반 변환 구현

- **ID**: 006
- **날짜**: 2026-04-20
- **유형**: 버그 수정

## 작업 요약
PDF 다운로드 시 WeasyPrint 실패(libpango 미설치)로 ReportLab 폴백이 사용되어 한글/테이블 렌더링이 깨지던 문제를 수정. LibreOffice를 활용한 DOCX→PDF 변환을 최우선 경로로 추가하여 원본 DOCX 레이아웃을 그대로 유지하는 고품질 PDF를 생성하도록 개선.

## 변경 파일 목록

### Model (src/model/struct/)
- **doc_export.py**: 전면 재작성
  - `_convert_docx_to_pdf()` 신규 추가: `libreoffice --headless --convert-to pdf` subprocess 호출
  - `generate_pdf_weasy()` 재작성: (1) generated_output_file DOCX → LibreOffice 변환, (2) generate_docx() → LibreOffice 변환, (3) ReportLab 폴백 순서
  - import 추가: subprocess, tempfile, shutil, os
