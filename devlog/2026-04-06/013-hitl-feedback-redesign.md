# HITL 피드백 재설계 — 2-Level (낙상 + 자세 6-class + 애매함 태깅)

- **ID**: 013
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
기존 Y/N 이진 피드백을 2-Level(낙상 판정 + 자세 6-class) 피드백으로 확장했다.
ambiguity/occlusion/short_clip 태그를 추가하고, hard-case 자동 분류 및 재학습 큐 분리를 구현했다.

## 변경 파일 목록

### Backend — video_analysis.py
- `submit_analysis_feedback()`: 파라미터 확장 (predicted_posture, ambiguity_flag, occlusion_flag, short_clip_flag)
- 피드백 메타 v2: feedback_version=2, 자세/tag 필드 포함
- Posture-class intake: 자세 라벨별 하위 디렉토리에 영상 복사 (stand/, walk/ 등)
- Hard-case 태깅: _hard_cases/ 디렉토리에 메타데이터 기록
- XG-Posture 별도 자동 재학습 트리거 (posture_count >= AUTO_RETRAIN_THRESHOLD)
- `_intake_summary()`: posture_intake 통계 + hard_case_count 추가
- `retrain_baseline()`: XG-Posture 재학습 호출 추가 (기존 XG-Fall에 이어서)

### Backend — api.py
- `submit_analysis_feedback()`: 새 파라미터 전달 (predicted_posture, ambiguity_flag 등)

### Frontend — view.ts
- `postureClasses` 코드를 백엔드 _XG_POSTURE_CLASSES와 일치 (standing→stand, walking→walk 등)
- `multiclassFeedbackEnabled` 제거, 항상 6-class 피드백 활성화
- 새 상태 변수: feedbackAmbiguityFlag, feedbackOcclusionFlag, feedbackShortClipFlag
- 로그 피드백 확장: logFeedbackPostureClass, logFeedbackAmbiguityFlag 등
- toggleFeedbackFlag(), toggleLogFeedbackFlag() 체크박스 토글 헬퍼
- setLogFeedbackPostureClass() 자세 클래스 선택 헬퍼
- submitAnalysisFeedback/submitLogFeedback: 새 필드 전송

### Frontend — view.pug
- 업로드 모드 피드백: 2-Level 구조 (낙상 Y/N → 자세 6-class), 애매함/가림/짧은영상 체크박스
- 로그 팝업 피드백: 동일 2-Level 구조 + 추가 태그 + 메모 필드
