# RF-Dual Rolling Cache 도입

- **ID**: 005
- **날짜**: 2026-04-13
- **유형**: 기능 추가

## 작업 요약
RF-Dual에 실시간 청크 간 연속성을 위한 rolling cache를 도입했다.
이전에는 매 청크가 고립 분석되어 청크 경계에서 낙상을 놓칠 수 있었으나, 이제 이전 청크의 tail 1.5초를 다음 청크에 이어붙여 연속 분석한다.
XG-Dual의 rolling cache 패턴을 RF-Dual에 이식하되, 캐시 세션 ID에 `rd_` 접두사를 추가하여 XG-Dual과의 충돌을 방지했다.

## 변경 파일 목록

### video_analysis.py (`src/model/struct/video_analysis.py`)

#### `_infer_rf_dual()` 시그니처 변경
- `duration_hint=0, realtime_context=None` 파라미터 추가
- `duration_hint` → `_extract_unified_timeseries()` 호출 시 전달 (webm fps 보정 활성화)

#### `_infer_rf_dual()` rolling cache 로직 삽입
- timeseries 추출 직후, RF feature 계산 전에 rolling cache 처리
- XG-Dual의 rolling cache 패턴 이식:
  - `_load_rt_session_cache()` / `_save_rt_session_cache()` 재사용
  - `_rt_rolling_cache` 클래스 변수 공유
  - 이전 chunk tail(최대 10 엔트리) → 시간 shift → prepend
  - `_from_rolling=True` 마커로 stitched 엔트리 식별
  - `_compute_rf_features_from_timeseries()`에서 `_from_rolling` 엔트리 자동 제외 (이전 FN-0003에서 구현)
- **캐시 세션 ID**: `'rd_' + session_id` 형식으로 XG-Dual(`session_id` 직접 사용)과 분리
- `_perf['rolling_stitched']`로 stitched 프레임 수 추적

#### runners dict 수정
- `rf-dual` lambda에 `duration_hint=duration_hint, realtime_context=realtime_context` 전달 추가
- 이전에는 두 파라미터가 전달되지 않아 webm fps 보정 및 rolling cache가 비활성 상태였음
