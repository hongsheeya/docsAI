# page.dashboard view.ts 모듈 진단 오류 2건 정리

- **ID**: 003
- **날짜**: 2026-04-03
- **유형**: 버그 수정

## 작업 요약
`page.dashboard/view.ts`에서 TypeScript가 `@angular/core`와 `@wiz/libs/portal/season/service`를 찾지 못하던 진단 오류를 정리했다.
로컬 선언 파일 참조를 명시하고, 대시보드에서 실제로 사용하는 Angular 타입 선언을 보강해 편집기 오류가 사라지도록 정리했다.

## 변경 파일 목록
- `src/app/page.dashboard/view.ts`
  - 로컬 타입 선언 파일 참조 추가
- `src/types/wiz-view-modules.d.ts`
  - `ElementRef`, `ViewChild` 선언 추가
  - 데코레이터 타입을 느슨하게 조정해 대시보드 파일의 추가 진단 오류 제거