# XG-Dual UI/API 결과 구조 변경

- **ID**: 012
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
XG-Dual 추론 결과의 posture_probs(6클래스 확률분포), decision_state(5단계 판정 상태), explain(판정 근거 리스트)을 프론트엔드에서 표시하도록 UI/API를 개편했다. 업로드 분석 결과 상세, 실시간 오버레이, 실시간 로그 상세에 자세 확률 바 차트, 판정 상태 배지, 불확실/경계 경고, guard 억제 배지, explain 항목 리스트를 추가했다.

## 변경 파일 목록

### Backend (video_analysis.py)
- `analyze_upload()`: xg-dual runtime_key에 대한 speed note, analysis_overview, runtime_label 처리 추가
- `_risk_score_guide()`: xg-dual 전용 risk score guide 추가 (threshold, suppress 정보, decision_state 포함)

### Frontend (page.dashboard/view.ts)
- `currentEngineLabel()`, `currentEngineNote()`: xg-dual 엔진 매핑 추가
- `getRiskScoreFormula()`: xg-dual 수식 표시 추가
- 신규 헬퍼 메서드 8개: `hasPostureData()`, `postureLabel()`, `decisionStateMeta()`, `isAmbiguousDecision()`, `postureItems()`, `getExplainItems()`, `getSuppressedBy()`, `isXgDualResult()`
- 실시간 오버레이/로그에 posture/decision 필드 추가

### Frontend (page.dashboard/view.pug)
- Result Summary: decision_state 배지, 자세 라벨+소형 확률 바
- Posture & Decision 전체 섹션 신규: 6클래스 확률 바 차트, Decision State 카드, 불확실 경고, Guard 억제 배지, Explain 리스트
- 실시간 오버레이: 자세 라벨 + decision_state 배지
- 실시간 로그: 자세 라벨 배지, 상세 팝업 자세/판정 정보
