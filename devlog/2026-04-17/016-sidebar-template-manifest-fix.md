# 사이드바 템플릿 JIT 오류 및 manifest.json 오류 수정

- **ID**: 016
- **날짜**: 2026-04-17
- **유형**: 버그 수정

## 작업 요약
사이드바 컴포넌트의 Angular 템플릿에서 Tailwind 유틸리티 클래스를 `class` 바인딩으로 직접 제어하던 부분이 HTML 파서를 깨뜨려 `button` 태그가 비정상 종료되는 JIT 컴파일 오류를 유발하던 문제를 수정했다. 또한 `/manifest.json` 링크는 존재하지만 실제 파일이 없어 브라우저에서 Manifest syntax error가 발생하던 문제를 해결하기 위해 manifest 파일을 추가했다.

## 변경 파일 목록

### App (component.nav.sidebar)
- `view.ts` — `navButtonClass()` 헬퍼 추가
- `view.pug` — 위험한 `[class.hover:...]` 바인딩 제거, `[ngClass]` 기반으로 변경

### Angular PWA 자산
- `src/angular/manifest.json` — 웹 앱 매니페스트 파일 추가
- `src/angular/angular.build.options.json` — manifest 자산 등록 추가
- `bundle/www/manifest.json` — 현재 실행 중 번들에 manifest 파일 직접 반영
- `build/dist/build/manifest.json` — 빌드 산출물 경로에 manifest 파일 추가
- `build/src/manifest.json` — 빌드 소스 경로에 manifest 파일 추가
