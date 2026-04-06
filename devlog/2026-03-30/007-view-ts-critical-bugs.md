# view.ts 크리티컬 버그 수정

- **ID**: 007
- **날짜**: 2026-03-30
- **유형**: 버그 수정

## 작업 요약
대시보드 view.ts의 치명적 버그 4건을 수정. handleRealtimeChunk 네트워크 오류 시 realtimeAnalyzing 영구 잠금(C1), analyzePreparedFile silent 모드 fetch 에러 미처리(C2), 재귀 호출 → while 루프 전환(M1), stopRealtimeAnalysis await 누락(M2). 추가로 formatRisk NaN 방어 코드 추가.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - C1: handleRealtimeChunk try/catch/finally 감싸기, realtimeAnalyzing = false 보장
  - C2: analyzePreparedFile silent fetch에 raw.ok 체크 + try/catch 추가
  - M1: realtimePendingChunk 처리를 재귀 → while 루프로 전환
  - M2: stopRealtimeAnalysis async + await this.service.render()
  - formatRisk: NaN/null/undefined 방어 코드 추가
