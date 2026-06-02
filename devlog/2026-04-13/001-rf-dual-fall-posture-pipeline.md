# RF-Dual (Fall+Posture) 파이프라인 구현

- **ID**: 001
- **날짜**: 2026-04-13
- **유형**: 기능 추가

## 작업 요약

XG-Dual과 동일한 구조로 RF-Dual 파이프라인을 신규 구현했습니다.  
RF(RandomForest) 이진 낙상 감지 + XG-Posture 6-class 자세 분류를 결합하는 듀얼 파이프라인으로,  
XG-Fall이 없어도 RF 모델만 있으면 동작하며 자세 분류까지 제공합니다.

## 기술 설계

- **Step 1**: `_extract_rf_pipeline_features()` → RF 13개 통계 특징 추출 → RF `predict_proba()` 낙상 이진 판정
- **Step 2**: `_extract_unified_timeseries()` → XG-Posture 6-class 자세 추론 (best-effort, 실패해도 기본값 유지)
- **Step 3**: `_arbitrate_decision()` → xg-dual과 동일한 arbitration으로 `decision_state` + `explain` 생성
- motion guard, adaptive threshold, 억제 로직 모두 rf-pipeline과 동일하게 적용
- YOLO 패스가 2번 발생하는 구조이나 rf-dual은 보조 모드이므로 허용 범위

## 변경 파일 목록

### `src/model/struct/video_analysis.py`
- `_infer_rf_dual()` 메서드 신규 추가 (~230줄) — 핵심 추론 파이프라인
- `_infer_with_trained_model()` — `rf-dual` 별칭 정규화, `available`/`runners` dict에 등록
- `_model_options()` — `rf-dual` 옵션 추가 (`rf_dual_ready = rf_available`)
- `_model_option_label()` — `'rf-dual': 'RF-Dual (Fall+Posture) 파이프라인'` 추가
- `_risk_score_guide()` — `rf-dual` runtime_key 분기 추가
- `analyze_upload()` 내 `analysis_speed_note` 블록 — `rf-dual` 분기 추가
- `analyze_upload()` 내 `runtime_label` 블록 — `rf-dual` 분기 추가
- `analyze_upload()` 내 `analysis_overview` 블록 — `rf-dual` 전용 overview 항목 추가

### `src/app/page.dashboard/view.ts`
- `isDualModeResult()` 헬퍼 신규 추가 — `xg-dual || rf-dual` 체크
- `currentEngineLabel()` — `'rf-dual'` 케이스 추가
- `currentEngineNote()` — `'rf-dual'` 케이스 추가
- `modelSpeedHint()` — `'rf-dual'` 전용 힌트 추가 (`4~12초`, `~6초/청크`)
- `getRiskScoreFormula()` — `'rf-dual'` 케이스 추가

### `src/app/page.dashboard/view.pug`
- 웹캠/업로드 양쪽 모델 선택 `<select>` — `rf-dual` 옵션 추가
- `isXgDualResult() && hasPostureData()` → `isDualModeResult() && hasPostureData()` 로 변경 (2곳)
- Dual-Mode 자세 섹션 주석 업데이트

## 결과

- 빌드 성공 (9469ms, EsBuild 1212ms)
- 에러 없음
- RF 모델이 준비된 상태면 rf-dual 선택 가능
- XG-Posture 없으면 posture_label='stand' 기본값으로 graceful fallback
