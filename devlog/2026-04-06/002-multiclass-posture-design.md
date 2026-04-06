# 다중 자세 클래스 라벨 체계 설계 및 구현

- **ID**: 002
- **날짜**: 2026-04-06
- **유형**: 기능 추가 + 설계 문서

## 작업 요약
이진 분류(fall/non-fall)에서 6-class 자세 분류(서기/걷기/앉기/뛰기/눕기/낙상)로 전환하기 위한 라벨 체계 설계, 데이터 구조 확장, 마이그레이션 전략을 수립하고 코드에 준비 구현을 완료했다.

## 변경 파일 목록

### 백엔드 (Model)
- `src/model/libs/action_behavior_model.py`
  - `POSTURE_CLASSES` — 6개 자세 클래스 상세 정의 (설명, 경계 조건, 포즈 지표, 이진 매핑)
  - `MULTICLASS_ORDER` — 다중 클래스 순서 상수
  - `BINARY_TO_MULTICLASS_MAPPING` / `MULTICLASS_TO_BINARY_MAPPING` — 양방향 매핑
  - `get_posture_class_info()`, `get_all_posture_classes()`, `migrate_binary_label()`, `to_binary_label()` 유틸리티 함수
  - `DEFAULT_SUMMARY`, `DEFAULT_MODEL`에 `multiclass_order`, `multiclass_ready` 필드 추가

### 백엔드 (Struct)
- `src/model/struct/video_analysis.py`
  - `submit_analysis_feedback()`에 `posture_class` 파라미터 추가
  - 피드백 메타데이터 JSON에 `posture_class` 필드 저장

### 프론트엔드 (Dashboard)
- `src/app/page.dashboard/view.ts`
  - `postureClasses` 배열 (6-class 옵션 목록)
  - `multiclassFeedbackEnabled` 토글 (기본 false)
  - `setFeedbackPostureClass()` — 다중 클래스 선택 시 이진 라벨 자동 역매핑
  - `submitAnalysisFeedback()`에서 `posture_class` 파라미터 전송
- `src/app/page.dashboard/view.pug`
  - 피드백 UI에 6-class 버튼 그룹 추가 (multiclassFeedbackEnabled=true 시 활성화)
- `src/app/page.dashboard/api.py`
  - `submit_analysis_feedback`에 `posture_class` 쿼리 파라미터 전달

### 설계 문서
- `docs/multiclass-posture-design.md` — 전체 설계서 (클래스 정의, 경계 조건, 스키마 변경, 마이그레이션, 모델 아키텍처)
