# PDF/DOCX 문서 내보내기

- **ID**: 012
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 내보내기 기능을 구현했다. ReportLab(PDF), WeasyPrint(HTML→PDF), python-docx(DOCX) 세 가지 라이브러리를 활용하여 섹션 내용을 조합해 PDF/DOCX 파일로 다운로드할 수 있다. Step 3 미리보기에 텍스트/PDF 전환 기능과 개요 탭에 PDF/DOCX 다운로드 버튼을 추가했다.

## 변경 파일 목록

### pip 패키지 설치
- `reportlab` 4.4.10, `weasyprint` 68.1

### 백엔드
- `src/model/struct/doc_export.py`: DocExport Sub-Struct 생성 (generate_pdf, generate_docx, preview_html, generate_pdf_weasy)
- `src/model/struct.py`: _DocExport 로드 및 doc_export property 추가
- `src/app/page.doc.write.item/api.py`: download_pdf, download_docx, preview_pdf 함수 추가

### 프론트엔드
- `src/app/page.doc.write.item/view.ts`: previewMode, pdfPreviewUrl, downloadPdf, downloadDocx, togglePreviewMode 추가
- `src/app/page.doc.write.item/view.pug`: 좌측 미리보기에 텍스트/PDF 전환 탭, 개요에 PDF/DOCX 다운로드 버튼 추가
