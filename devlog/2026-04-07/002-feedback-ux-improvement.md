# 피드백 저장 UX 개선 (타이머 + 완료 메시지 + 버튼 재활성화)

- **ID**: 002
- **날짜**: 2026-04-07
- **유형**: 기능 개선

## 작업 요약
피드백 저장/재학습 시 경과 시간 타이머 표시, 완료 후 상세 결과 메시지 표시, 에러/성공 모두 버튼 즉시 재활성화하도록 개선.

## 변경 파일 목록

### view.ts
- `feedbackElapsedSec`, `feedbackTimerHandle` 프로퍼티 추가
- `startFeedbackTimer()`, `stopFeedbackTimer()` 메서드 추가
- `submitAnalysisFeedback()`: 타이머 시작/정지, 완료 메시지에 소요시간 포함 ("✅ 피드백 저장 완료 (12초)")
- `logFeedbackElapsedSec`, `logFeedbackTimerHandle`, `logFeedbackMessage`, `logFeedbackMessageType` 프로퍼티 추가
- `submitLogFeedback()`: 동일한 타이머 + 완료 메시지 패턴 적용, 에러 처리 강화
- `ngOnDestroy()`: 신규 타이머 핸들 정리

### view.pug
- 업로드 모드 피드백 버튼: "저장 중..." → "저장 중... 12초"
- 로그 모달 피드백 버튼: 동일 패턴 + 결과 메시지 div 추가
