# 문서 관리 기능 개선

- **ID**: 004
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
문서 목록에서 정렬, 제목/상태/폴더 수정, 삭제를 할 수 있는 관리 UI를 추가했다. 상세 화면에서도 문서 정보 저장과 삭제를 바로 수행할 수 있게 확장했다.

## 변경 파일 목록
- src/app/page.doc.write/view.ts — 문서 메타 수정/정렬/관리 모달 로직 추가
- src/app/page.doc.write/view.pug — 정렬/관리 UI 및 문서 정리 모달 추가
- src/app/page.doc.write/api.py — update_meta 엔드포인트 추가
- src/app/page.doc.write.item/view.ts — 상세 화면 문서 정보 저장/삭제 로직 추가
- src/app/page.doc.write.item/view.pug — 상세 화면 문서 정보/삭제 UI 추가
- src/app/page.doc.write.item/api.py — update_meta, delete_instance 추가
