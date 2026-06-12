# HWP 이미지 삽입 시 기존 내용 보존 및 API 배치 로직 개선

- **ID**: 009
- **날짜**: 2026-04-20
- **유형**: 버그 수정

## 작업 요약
HWP 양식 미리보기/내보내기에서 이미지를 배치할 때 대상 셀의 기존 안내 문구나 텍스트가 통째로 삭제되던 문제를 수정했다.
이미지 배치 데이터를 확장하여 `insert_mode` 메타데이터를 저장할 수 있게 바꾸고, 기본 동작을 텍스트 보존형(`above`/`below` 자동 결정)으로 조정했다.

## 변경 파일 목록

### Backend — Model/Struct
- `src/model/struct/doc_export.py`
  - HWP HTML 채우기 로직에서 이미지 삽입 시 기존 셀 HTML을 유지하도록 수정
  - 이미지 삽입 위치 자동 결정 헬퍼 추가 (`_resolve_image_insert_mode`, `_build_image_cell_content`)
  - 이미지 블록용 CSS 추가
- `src/model/struct/graph_gen.py`
  - 배치 정보 저장 포맷을 상세 구조로 정규화 (`filename`, `insert_mode`)
  - 레거시 프론트 호환 응답 포맷 유지
  - 이미지 삭제/배치 해제 시 상세 포맷 기준으로 정리하도록 수정

### Backend — App API
- `src/app/page.doc.write.item/api.py`
  - `save_image_placement()`에서 `insert_mode` 지원
  - `get_image_positions()`에서 `placement_details` 추가 반환

### Frontend — 문서 작성 상세
- `src/app/page.doc.write.item/view.ts`
  - 배치 API 응답이 `{ placements: ... }` 구조여도 기존 UI가 동작하도록 호환 처리

### 검증
- 실제 업로드 이미지 배치 후 미리보기 HTML에서 기존 텍스트와 `data:image`가 함께 존재하는 것 확인
- 프로젝트 일반 빌드 성공 확인
