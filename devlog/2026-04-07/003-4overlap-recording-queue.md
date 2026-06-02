# 실시간 4중첩 녹화 + 요청 큐 구현

- **ID**: 003
- **날짜**: 2026-04-07
- **유형**: 기능 추가

## 작업 요약
순차 5초 녹화 방식을 4초 청크/3초 중첩(1초마다 새 녹화 시작) 멀티 레코더 구조로 교체. 완료된 청크는 요청 큐에 적재되어 워커 루프가 순차 디스패치. 큐 최대 6개, 초과 시 오래된 것 FIFO 폐기.

## 변경 파일 목록

### view.ts
- `realtimeIntervalSec`: 5→4, `realtimeOverlapSec`: 4→3
- `mediaRecorder`/`mediaRecorderChunks`/`realtimeTimer` 제거 → `recorderSlots[]`, `recorderSpawnTimer`, `nextSlotId` 추가
- `dispatchQueue[]`, `dispatchWorkerRunning`, `dispatchQueueSize`, `dispatchMaxQueue=6` 추가
- `startRealtimeAnalysis()`: 첫 레코더 즉시 시작 + 1초 setInterval로 `spawnRecorderSlot()` 반복
- `spawnRecorderSlot()`: 최대 4개 슬롯 제한, ondataavailable→chunks[], onstop→enqueueChunk, 4초 auto-stop timer
- `enqueueChunk()`: 큐 push + 6개 초과 시 FIFO discard + 워커 기동
- `runDispatchWorker()`: while(queue.length) 순차 dispatch 루프
- `stopRealtimeAnalysis()`: 모든 슬롯/타이머/큐 정리
- `dispatchRealtimeChunk()`: realtimeDispatching 가드 제거 (큐 워커가 순차 실행)

### view.pug
- 컨트롤 바에 "4중첩" sky 뱃지 추가
- 큐 크기 > 0일 때 amber 텍스트로 "큐 N" 표시
