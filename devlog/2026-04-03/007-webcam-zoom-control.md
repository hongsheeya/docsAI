# 웹캠 배율/핏 모드 조절 기능 추가

- **ID**: 007
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
웹캠 영상이 `object-cover`로 인해 과도하게 크롭/확대되던 문제를 수정했다. 기본 핏 모드를 `object-contain`(전체보기)으로 변경하고, 사용자가 배율(30%~300%)과 핏 모드(Fit/Fill)를 직접 조절할 수 있는 인라인 컨트롤을 영상 좌측 하단에 추가했다.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - `webcamZoom`, `webcamFitMode` 프로퍼티 추가 (기본값: 1.0, object-contain)
  - `adjustWebcamZoom()`, `resetWebcamZoom()`, `toggleWebcamFitMode()` 메서드 추가
- `src/app/page.dashboard/view.pug`
  - 웹캠 비디오 태그: `object-cover` → 동적 `[ngClass]="webcamFitMode"` + `transform: scale()` 바인딩
  - 좌측 하단에 배율/핏 모드 컨트롤 (Fit/Fill 토글, −/+ 배율, 1:1 리셋)
