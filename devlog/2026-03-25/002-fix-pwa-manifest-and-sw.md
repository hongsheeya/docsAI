# PWA manifest 및 service worker 연동 복구

- **ID**: 002
- **날짜**: 2026-03-25
- **유형**: 버그 수정

## 작업 요약
브라우저 콘솔의 `Manifest: Line: 1, column: 1, Syntax error` 원인을 분석한 결과, `/manifest.json` 요청이 JSON이 아니라 SPA `index.html`로 fallback 되고 있었다.
동시에 `/sw.js`는 비어 있는 내용만 반환하고 있어 PWA 자원 연동이 불완전한 상태였다.
manifest Route와 PWA 설정 파일을 보강하고, Angular 빌드 자산 설정을 정리한 뒤 클린 빌드를 수행하여 외부 도메인 기준 `manifest.json`, `sw.js`, 아이콘 경로가 모두 정상 응답하도록 복구했다.

## 변경 파일 목록
### Route
- `src/route/manifest/app.json` — `/manifest.json` 라우트 추가
- `src/route/manifest/controller.py` — manifest JSON 응답 구현

### Config
- `config/season.py` — PWA 기본 메타데이터 및 아이콘 경로 정의
- `config/pwa/sw.js` — 기본 service worker 스크립트 추가

### Angular 자산
- `src/angular/angular.build.options.json` — 자산/manifest/sw 배포 설정 보강
- `src/assets/pwa/manifest.json` — PWA manifest 자산 추가
- `src/assets/pwa/sw.js` — service worker 자산 추가

### 빌드
- `build/`, `bundle/` — 클린 빌드로 산출물 갱신
