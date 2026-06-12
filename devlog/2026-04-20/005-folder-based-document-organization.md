# 폴더 기반 문서 분류 기능 추가

- **ID**: 005
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
문서 폴더 테이블과 `folder_id` 컬럼을 추가하고, 폴더 생성/수정/삭제/선택 기능을 구현했다. 문서 목록을 폴더 단위로 묶어 볼 수 있게 하고, 폴더 삭제 시 문서를 미분류로 안전하게 이동하도록 처리했다.

## 변경 파일 목록
- src/model/db/doc_folder.py — 폴더 모델 추가
- src/model/db/doc_instance.py — folder_id 컬럼 추가
- src/model/struct.py — doc_folder 테이블 생성 및 folder_id 마이그레이션 추가
- src/model/struct/doc.py — 폴더 CRUD 및 폴더 기반 문서 조회/정리 로직 추가
- src/app/page.doc.write/api.py — folders/create_folder/rename_folder/delete_folder 추가
- src/app/page.doc.write/view.ts, view.pug — 폴더 사이드바 및 관리 모달 구현
- src/app/page.doc.write.item/api.py, view.ts, view.pug — 상세 화면 폴더 변경 지원
