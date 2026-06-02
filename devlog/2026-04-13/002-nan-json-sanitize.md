# 실시간 청크 NaN JSON SyntaxError 버그 수정

- **ID**: 002
- **날짜**: 2026-04-13
- **유형**: 버그 수정

## 작업 요약

Python `json` 모듈이 `float('nan')`, `float('inf')` 등을 JSON 표준 위반 리터럴 `NaN`/`Infinity`로 직렬화하여 프론트엔드 `JSON.parse()`가 `SyntaxError`로 실패하는 버그를 수정함. 재귀 정제기 `_sanitize_for_json()`를 추가하고 응답 반환 직전에 적용했으며, 특징 딕셔너리 생성 3곳에서도 NaN 안전 처리를 추가함.

## 변경 파일 목록

### `src/model/struct/video_analysis.py`

| 위치 | 변경 내용 |
|------|----------|
| `_sanitize_filename()` 직후 | `_sanitize_for_json()` 정적 메서드 신규 추가 — dict/list/float 재귀 순회, `math.isnan()` / `math.isinf()` 검사 후 `None` 치환 |
| `analyze_upload()` 반환부 | `raw = {...}` 딕셔너리 생성 후 `return self._sanitize_for_json(raw)` 적용 |
| `_extract_rf_pipeline_features()` 특징 딕셔너리 | `round(float(v), 4) if isinstance(v, float)` → NaN-safe lambda 검사 후 `None` 또는 `round()` |
| `_extract_rf_pose_features()` 특징 딕셔너리 | 동일 패턴 적용 (features dict comprehension) |
| `_infer_rf_dual()` 특징 딕셔너리 | 동일 패턴 적용 (features dict comprehension) |

### `src/app/page.dashboard/view.ts`

| 위치 | 변경 내용 |
|------|----------|
| `dispatchRealtimeChunk()` catch 블록 | `e instanceof SyntaxError` 분기 추가 — "JSON parse failed — server may have returned NaN" 메시지 별도 출력 |

## 검증

- Python 단위 테스트 직접 실행: `numpy.float64` NaN, `float('nan')`, `float('inf')`, `float('-inf')` 포함 딕셔너리 → 모두 `null` 변환 확인
- 빌드 성공 (5883ms, 에러 없음)
