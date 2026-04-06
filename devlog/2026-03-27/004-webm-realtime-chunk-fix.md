# 실시간 webm 청크 헤더 문제 수정

- **ID**: 004
- **날짜**: 2026-03-27
- **유형**: 버그 수정

## 작업 요약
실시간 웹캠 분석에서 MediaRecorder `timeslice` 청크의 후속 webm 파일이 EBML 헤더 없이 저장되어 OpenCV가 열지 못하는 문제를 수정했다. 실시간 녹화 방식을 `start(timeslice)`에서 `start() + stop()` 반복 방식으로 변경해 매 청크가 완전한 독립 webm 파일이 되도록 했다.

## 원인 분석
- 기존 방식: `MediaRecorder.start(4000)`
- 결과: 첫 번째 청크만 EBML 헤더(`1a45dfa3`) 포함, 후속 청크는 continuation data만 포함
- 전수 검사 결과: 기존 realtime webm 22개 중 19개가 `EBML header parsing failed`

## 해결 방법
- Recorder A/B를 유지하되, 각 윈도우마다 새 recorder를 생성하고 `start()` 후 4초 뒤 `stop()`
- 2초 오버랩 후 B 루프 시작 구조 유지
- 세그먼트 interval timer와 stop timer를 별도 관리
- recorder `onstop`에서 세그먼트 종료와 전체 세션 종료를 구분하도록 보정

## 검증 결과
- 기존 정상 헤더 webm 분석 성공 확인: 서버 분석 0.42s, 전체 요청 0.898s
- 향후 생성되는 모든 청크는 완전한 webm 헤더 포함 예상

## 변경 파일 목록
- `src/app/page.dashboard/view.ts`
  - 실시간 녹화 루프를 stop/restart 기반으로 교체
  - timer 정리 로직 추가
  - recorder 종료 상태 처리 보정
