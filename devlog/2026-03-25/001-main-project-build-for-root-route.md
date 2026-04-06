# 메인 프로젝트 빌드로 루트 404 복구

- **ID**: 001
- **날짜**: 2026-03-25
- **유형**: 설정 변경

## 작업 요약
배포 도메인 `https://health.seasonai.net/` 접속 시 404가 발생하는 문제를 분석했다.
원인은 `project/main` 프로젝트가 빌드되지 않아 루트 SPA 엔트리와 페이지 라우트 산출물이 없는 상태였기 때문이다.
`wiz project build --project=main`를 실행해 빌드 산출물을 생성했고, 이후 `/` 및 `/dashboard` 응답이 200으로 정상화됐다.

## 변경 파일 목록
### 빌드 산출물
- `project/main/build/` — Angular/WIZ 빌드 산출물 생성

### 문서
- `devlog.md` — 작업 요약 행 추가
- `devlog/2026-03-25/001-main-project-build-for-root-route.md` — 상세 기록 추가
