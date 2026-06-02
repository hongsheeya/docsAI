# RF-Dual 실시간 자세 분류 특화 UI

- **ID**: 007
- **날짜**: 2026-04-13
- **유형**: 기능 추가

## 작업 요약
RF-Dual 실시간 모드에서 자세 변화를 더 즉각적으로 보여주는 UI 기능을 추가했다.
자세 타임라인 추적, 전환 감지, 빈번한 변화 경고, 최근 자세 분포 요약을 구현했다.

## 변경 파일 목록

### `src/app/page.dashboard/view.ts`

#### 새 변수 선언
- `postureTimeline`: 최근 60개 자세 기록 (약 1분)
- `postureTransitions`: 최근 20개 자세 전환 이벤트
- `currentPosture` / `currentPostureLabel`: 현재 자세 상태
- `postureTransitionText`: 전환 표시 텍스트 (e.g. "걷기 → 앉기")

#### `trackPostureTimeline()` 메서드
- `pushRealtimeLog()` 내에서 호출
- 타임라인에 새 자세 기록 추가 (최대 60건)
- 이전 자세와 비교하여 전환 감지
- 전환 시 `postureTransitionText` 업데이트

#### `recentPostureSummary()` 메서드
- 최근 20개 타임라인에서 자세별 발생 비율 계산
- 오버레이에 미니 분포 요약으로 표시

#### `isPostureFrequentChange()` 메서드
- 최근 5건 전환 중 3건 이상이면 true → 경고 배지 표시

#### `startRealtimeAnalysis()` — 타임라인 초기화 추가

### `src/app/page.dashboard/view.pug`

#### 오버레이 패널 자세 섹션 확장
- 자세 전환 방향 표시 (↔ walk → sit 형태)
- 빈번한 자세 변화 경고 배지 (⚡)
- 최근 자세 분포 미니 태그 (예: 서기 60% 앉기 40%)

#### 로그 항목 자세 표시 강화
- RF-Dual일 때 로그 항목에 자세 라벨을 sky-400 색상으로 추가 표시
