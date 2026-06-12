# 문서 작성 메인 페이지 (page.doc.write)

- **ID**: 006
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 작성 메인 페이지 구현. 히어로 섹션 + 통계 카드(전체/진행중/완료) + 문서 목록 테이블. 새 문서 생성 모달(양식 선택 또는 직접 업로드). 생성 후 상세 페이지로 이동.

## 변경 파일 목록

### 신규 생성
- `src/app/page.doc.write/app.json` — 메타데이터 (viewuri: /doc/write, controller: user)
- `src/app/page.doc.write/view.ts` — 문서 목록 로드, 생성, 삭제 로직
- `src/app/page.doc.write/view.pug` — 히어로 + 통계 + 테이블 + 모달 UI
- `src/app/page.doc.write/view.scss` — :host 블록
- `src/app/page.doc.write/api.py` — list, stats, templates, create, delete 함수
