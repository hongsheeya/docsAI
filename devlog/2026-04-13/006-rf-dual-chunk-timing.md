# RF-Dual 실시간 청크 타이밍 최적화

- **ID**: 006
- **날짜**: 2026-04-13
- **유형**: 성능 최적화

## 작업 요약
RF-Dual이 YOLO single-pass + rolling cache로 서버 처리가 빨라졌으므로, 프론트엔드 청크 전략을 RF-Dual에 최적화했다. 모델별 분기 메서드 `getChunkConfig()`를 도입하여, RF-Dual은 3초 청크 / 1.5초 간격 / 큐 최대 4로 운용하고, XG-Dual은 기존 5초 / 2초 / 큐 6을 유지한다.

## 변경 파일 목록

### `src/app/page.dashboard/view.ts`

#### `getChunkConfig()` 신규 메서드
- 모델별 청크 전략을 반환: `{chunkSec, spawnMs, maxSlots, maxQueue}`
- RF-Dual: 3초 청크, 1.5초 spawn, 유지 3슬롯, 큐 4
- XG-Dual/기타: 5초 청크, 2초 spawn, 3슬롯, 큐 6

#### `startRealtimeAnalysis()` — spawn interval 모델별 분기
- `setInterval(spawnRecorderSlot, 2000)` → `setInterval(spawnRecorderSlot, chunkCfg.spawnMs)`

#### `spawnRecorderSlot()` — chunk duration/max slots 모델별 분기
- `if (recorderSlots >= 3)` → `if (recorderSlots >= chunkCfg.maxSlots)`
- `setTimeout(stop, realtimeIntervalSec * 1000)` → `setTimeout(stop, chunkCfg.chunkSec * 1000)`

#### `enqueueChunk()` — 큐 제한 모델별 분기
- `dispatchMaxQueue` 대신 `chunkCfg.maxQueue` 사용

#### `modelSpeedHint()` — 속도 힌트 업데이트
- RF-Dual webcam: `~6초/청크` → `~3초/청크`
- RF-Dual upload: `4~12초` → `2~6초`
