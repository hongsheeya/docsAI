# XG-Dual 파이프라인 검증 및 버그 수정

- **ID**: 018
- **날짜**: 2026-04-06
- **유형**: 버그 수정 + 검증

## 작업 요약
XG-Dual 모델이 실제로 작동하지 않는 문제를 종합 감사(audit)하여 3개 버그를 발견·수정하고, 미학습 상태의 모델을 훈련시킨 뒤 E2E 추론을 검증 완료함.

## 발견된 문제 및 수정

### 1. 🔴 모델 파일 미존재 (Critical)
- XG-Fall, XG-Posture 모델이 한 번도 훈련되지 않아 `.pkl` 파일 부재
- `retrain_baseline` API 호출로 훈련 수행 → 두 모델 모두 생성 확인

### 2. 🟡 `_infer_xg_dual` 데드코드 (L4916)
- `return { ... }` → shadow comparison 코드 도달 불가
- `_result = { ... }` 로 수정하여 shadow 비교 분기 정상 동작

### 3. 🟡 `analyze_upload` 기본 model_type 불일치 (L3867)
- 기본값 `'rf-pipeline'` → `'xg-dual'`로 수정

### 4. 🟡 XG-Posture metrics 캐스팅 오류 (L5701)
- `classification_report` 호출 시 "binary and multilabel-indicator targets" 에러
- `y_pred`, `y`에 `.flatten().astype(int)` 추가

## E2E 검증 결과
- **테스트 영상**: 01266_O_F_FY_C5.mp4 (3.83MB, 10초, 4K)
- **runtime_key**: xg-dual (정상)
- **총 추론**: 3.161s (timeseries 3.12s + fall predict 0.006s + posture predict 0.007s)
- **6클래스 확률**: stand 51%, fall 40%, 기타 2%씩 — 부트스트랩 학습 데이터(40샘플)로는 정상 범위
- **decision_state**: safe

## 변경 파일 목록
| 파일 | 변경 내용 |
|------|----------|
| `src/model/struct/video_analysis.py` L4916 | `return {` → `_result = {` (데드코드 수정) |
| `src/model/struct/video_analysis.py` L3867 | model_type 기본값 `rf-pipeline` → `xg-dual` |
| `src/model/struct/video_analysis.py` L5701 | posture metrics `.flatten().astype(int)` 추가 |
