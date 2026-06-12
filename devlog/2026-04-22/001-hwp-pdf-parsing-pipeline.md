# HWP → PDF 기반 파싱 파이프라인 구축 + 버그 수정 3건

- **ID**: 001
- **날짜**: 2026-04-22
- **유형**: 기능 추가 + 버그 수정

## 작업 요약
HWP 파일을 LibreOffice로 PDF로 먼저 변환하여 내용을 정밀 파악하고, 별도로 DOCX도 변환하여 양식 채움에 활용하는 5단계 파싱 파이프라인을 구축했다. 동시에 3건의 버그(DOCX 변환 실패 UI 표출, 채팅 첨부 파일 제한, 표 셀 오기입)를 수정했다.

## 변경 파일 목록

### `src/model/struct/file_parser.py`
- `_convert_to_pdf()` (신규): LibreOffice로 HWP/DOC/DOCX → PDF 변환. tmpdir에서 `.pdf` 파일을 검색, 원본 경로 옆에 `_converted.pdf`로 복사. PDF가 DOCX보다 레이아웃 보존율이 훨씬 높아 내용 이해 정확도가 우수.
- `parse_pdf(file_path, converted_docx_path='')` (교체): pdfplumber `page.chars` 기반 글자 속성(폰트 크기, 볼드) 감지로 헤딩 판별. 표 bbox 영역을 텍스트 추출에서 제외. `[표 N]` 라벨로 표 내용을 full_text에 포함. `converted_docx_path` 파라미터 추가.
- `parse_hwp(file_path)` (교체): 5단계 전략 — ①HWP→PDF(내용 파악용), ②HWP→DOCX(채움용 별도 변환), ③PDF 파싱(docx 경로 전달), ④DOCX 파싱 폴백, ⑤olefile 폴백.
- `parse()` (수정): PDF 직접 업로드 시 DOCX 변환도 병행 시도. `converted_docx_path`를 `parse_pdf()`에 전달.
- `_infer_answer_type_from_label()` (신규, 이전 세션): 셀 라벨에서 선택형/날짜/교과목/성명/학번 등 답변 유형 추론.
- `_build_table_fill_context()`: `(context_str, type_info)` 튜플 반환으로 변경.
- `_analyze_table_fills()`: 각 채움 항목에 `answer_type` 저장.

### `src/model/struct/ai_agent.py`
- `_get_fill_system_prompt()`: "가장 중요한 규칙" 섹션 추가 — 선택형은 반드시 선택지 중 하나, 교과목명은 사람 이름 금지 등.
- `_build_fill_prompt()`: 각 대상 항목에 `⚠️ 기입 규칙:` + 선택지 표시.
- `generate_field_values()`: 기존 DB 데이터에 `answer_type` 없어도 런타임 추론 처리.
- `build_context()`: `table_fill_info`에 `[규칙: ...]` 표시.

### `src/app/page.doc.write.item/api.py`
- DOCX 변환 실패를 `error` → `warning`으로 변경해 생성 계속 진행.
- `chat()`: HWP/PDF/DOCX/DOC 파일 첨부 지원 — 임시 저장 후 `file_parser.parse()` 로 텍스트 추출, 메시지 컨텍스트에 포함.
- 파일 입력 `accept` 속성: `image/*,.csv,.pdf,.docx,.doc,.hwp,.hwpx`

### `src/app/page.doc.write.item/view.pug`
- 채팅 파일 입력 `accept` 속성 업데이트.
