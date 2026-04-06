# 실시간 분석 UI 오버플로 수정 및 XG-Dual 신뢰성 개선 (FN-0019~0023)

- **ID**: 019
- **날짜**: 2026-04-06
- **유형**: 버그 수정

## 작업 요약
실시간 웹캠 모드에서 발생하는 5건의 문제를 일괄 수정: UI 뷰포트 오버플로(FN-0019), 로그 패널 무한 성장 + 자동 스크롤(FN-0020), XG-Dual 빈 윈도우(FN-0021), 5초 윈도우/4초 오버랩 파라미터(FN-0022), 로그 ID 중복(FN-0023).

## 변경 파일 목록

### view.pug (UI 오버플로 + 로그 영역 수정)
- Hero/Footer 섹션: 웹캠 모드에서 `*ngIf="inputMode !== 'webcam'"` 숨김
- section#analysis: `calc(100vh-52px)` 뷰포트 채움 + `overflow:hidden`
- Flex 레이아웃 체인: section → wrapper → card → grid → video card 전체 `flex-1 min-h-0` 적용
- 비디오 영역: `min-height: 70vh` 제거, `h-full` 적용
- 컨트롤 카드: `shrink-0 overflow-y-auto`, `max-height: 45vh`
- 로그 패널: `#logScrollContainer` ref 추가, `rounded-2xl`

### view.ts (자동 스크롤 + ID 수정 + 파라미터)
- `@ViewChild('logScrollContainer')` + `scrollLogToBottom()` 메서드 추가
- `pushRealtimeLog(blob, chunkId?)`: 클로저 캡처로 ID 중복 방지
- `dispatchRealtimeChunk`: `_chunkId = realtimeChunkCount` 비동기 전 캡처
- `realtimeIntervalSec = 5`, `realtimeOverlapSec = 4` (1초 간격 분석)
- 세션 리셋 시 `realtimeIntervalSec = 5` (이전 4)

### video_analysis.py (XG-Dual 윈도우 신뢰성)
- `_extract_unified_timeseries`: `duration_hint` 파라미터 추가
- webm fps 보정: `duration_hint > 0`이면 `total_frames_raw / duration_hint`로 corrected_fps 계산
- `target_fps = 8`, `max_frames = 40` (실시간 모드)
- `duration_hint` 전파: `analyze_upload` → `_infer_with_trained_model` → `_infer_xg_dual`/`_infer_xg_fall` → `_extract_unified_timeseries`
- Posture 윈도우: 실시간 1.0s / 업로드 1.5s 조건부
