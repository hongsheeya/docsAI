# view.ts 모듈 진단 오류 정리

- **ID**: 001
- **날짜**: 2026-03-26
- **유형**: 버그 수정

## 작업 요약
신규 WIZ 페이지의 `view.ts`에서 발생하던 4개의 모듈 해석 오류를 분석하고 정리했다. 문제는 WIZ 빌드 단계에서 실제 경로로 변환되는 import가 편집기 단일 파일 진단에서는 바로 해석되지 않는 점이었고, 해당 import에 한정해 TypeScript 진단을 억제해 오류를 제거했다.

## 변경 파일 목록
- `src/app/page.admin.analysis/view.ts`
- `src/app/page.pipeline/view.ts`
