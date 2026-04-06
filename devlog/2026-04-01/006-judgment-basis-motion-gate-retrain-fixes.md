# 판단 근거 표시·Motion Gate·재학습 타임아웃 종합 개선

- **ID**: 006
- **날짜**: 2026-04-01
- **유형**: 버그 수정 + 기능 개선

## 작업 요약
XGBoost 기여도 미표시, motion gate AND 로직으로 유효 낙상 차단, RF 판단 근거 불필요 항목+고정 순서+색상 미반영, 재학습 무제한 시간 문제를 일괄 수정. FN-0030~0034 5건 동시 수행.

## 변경 파일 목록

### Backend — src/model/struct/video_analysis.py
- **FN-0030**: `_xgb_feature_importances` 추출 — classifier path 파일 존재 여부 사전 검증 추가, 실패 시 fallback으로 FEATURE_COLS 기반 균등 배분(1/N) 적용, imp=0이면 "(기여도 미확인)" 표시
- **FN-0032 (XGBoost)**: `event_time` 항목을 basis에서 제거 (이벤트 구간에 이미 표시)
- **FN-0032 (RF)**: `fall_probability`(위험 점수와 중복), `detected_person_frames`(진단 가치 없음) 제거, `area_mean` 제외 목록 추가, `_fixed_basis[:2]` 고정 순서 제거 → 순수 기여도 내림차순 정렬
- **FN-0033**: RF level 결정을 importance 단독 → feature별 낙상 방향 임계값 기반으로 변경, score ≥ threshold이면 top-2 항목은 최소 medium 보정
- **FN-0034**: `retrain_baseline()`에 threading 기반 타임아웃 적용 (모델당 45초), 타임아웃 시 구체적 에러 메시지 반환

### Backend — scripts/yolo_fall_runtime.py
- **FN-0031**: motion gate를 `all()` (3개 모두) → 2-of-3 majority vote로 변경, `_floor_speed_override` 추가 (fp≥0.75 + max_down_speed≥0.3), `_floor_height_override` 유지

### Frontend — src/app/page.dashboard/view.ts
- **FN-0034**: 재학습 타이머에 60초 경과 시 경고 메시지 표시, 타임아웃 에러 시 구체적 안내 메시지
