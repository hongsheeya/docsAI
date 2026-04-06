# UI 재구성, Bbox 오버레이, 서버 타이밍 분해 (FN-20260401-0001~0008)

- **ID**: 002
- **날짜**: 2026-04-01
- **유형**: 기능 추가

## 작업 요약
결과 카드 4열→3열 통합, 실시간/업로드 모드 bbox 오버레이, 서버 타이밍 7단계 분해, 실시간 미니 패널, 업로드 UI 모드별 분리를 구현했다. 백엔드 병목 분석(FN-0008)은 코드 리뷰 결과 대부분 문제 없음을 확인하고, 타이밍 분해 후 수치 기반 최적화로 조건부 진행.

## 변경 파일 목록

### 백엔드 (`src/model/struct/video_analysis.py`)
- `analyze_upload()`: `file_read_sec` (파일 읽기+SHA1), `file_save_sec` (디스크 저장) 분리
- `analyze_upload()`: `result_build_sec` (dict 조립만), `alert_dispatch_sec` (알림 발송) 분리
- `analyze_upload()`: `request_received_at` ISO 타임스탬프, `response_ready_sec` 추가

### 프론트엔드 (`src/app/page.dashboard/view.ts`)
- `getServerTimingDetail()` 메서드 추가 — 서버 상세 타이밍 세그먼트 반환
- `drawBboxesOnCanvas()` 공유 bbox 그리기 헬퍼
- `drawRealtimeBboxOverlay()` — 실시간 웹캠 위 마지막 프레임 bbox 표시
- `onUploadVideoPlay/Pause/Seeked()` + rAF 루프 — 업로드 비디오 프레임 매칭 bbox 표시
- `@ViewChild` 3개 추가 (realtimeBboxCanvas, uploadBboxCanvas, uploadPreviewVideo)
- `realtimeLastElapsed` 프로퍼티 — 실시간 분석 소요 시간 캐시
- `handleRealtimeChunk()` 완료 후 `drawRealtimeBboxOverlay()` 호출

### 프론트엔드 (`src/app/page.dashboard/view.pug`)
- 결과 그리드 `md:grid-cols-4` → `md:grid-cols-3` (감지결과+행동분류 통합 | 위험점수+모델 | 분석시간)
- 분석시간 카드에 서버 상세 타이밍(Server Timing Detail) 바 차트 추가
- Live Preview 영역에 Canvas 2개 추가 (realtimeBboxCanvas, uploadBboxCanvas)
- 실시간 모드 감지 결과 미니 패널 오버레이 (낙상/정상 뱃지, 탐지 소요, 누적 횟수)
- 프로그레스 바/즉시분석 버튼에 `*ngIf="inputMode === 'upload'"` 추가
- 파일 정보 표시 조건 보강 (upload 모드에서만), 웹캠 모드 상태 메시지 추가
- 업로드 비디오에 `#uploadPreviewVideo` ref 및 play/pause/seeked 이벤트 연결
