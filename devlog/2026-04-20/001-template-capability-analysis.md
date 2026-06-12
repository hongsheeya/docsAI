# 양식 기반 작성 가능 범위 검토 및 파서 분석

- **ID**: 001
- **날짜**: 2026-04-20
- **유형**: 리팩토링

## 작업 요약
기존 템플릿 파서와 문서 생성 흐름을 분석하고, DOCX/HWP/PDF 별로 원본 양식 유지 가능 범위를 코드 구조에 반영했다. DOCX는 헤더/푸터/표/치환 필드를 포함해 원본 양식 삽입이 가능하도록 파서를 확장했고, PDF/HWP는 섹션 기반 작성 모드로 한계를 명시했다.

## 변경 파일 목록
- src/model/struct/file_parser.py — DOCX 헤더/푸터/표/플레이스홀더 감지, 파일 형식별 capability 메타데이터 추가
- src/app/page.doc.templates/api.py — 양식 파싱 결과에 capability/metadata/placeholders 저장
- src/app/page.doc.templates/view.ts — 양식 capability 표시 헬퍼 추가
- src/app/page.doc.templates/view.pug — 지원 방식 배지 노출
