# 자세 분류 휴리스틱 튜닝 (FN-0060)

- **ID**: 006
- **날짜**: 2026-04-07
- **유형**: 기능 추가

## 작업 요약
XG-Posture 휴리스틱 부스트(Rule 1~3)를 실제 데이터 기반으로 튜닝. walk boost cap 상향, sit boost에 stillness 게이트 추가 및 cap 하향, walk→sit 전이 허용. 보행/정지/앉기 간 분류 정확도를 높이기 위한 규칙 기반 보정.

## 변경 파일 목록

### video_analysis.py (model/struct)

1. **Rule 1 (Stand→Walk boost) cap 상향** (~line 5286):
   - `min(boost, 0.20)` → `min(boost, 0.35)`
   - 이유: 실제 데이터에서 walk 피처 활성화 후 더 적극적인 boost 필요

2. **Rule 3 (Stand→Sit boost) 재구조화** (~line 5317-5331):
   - 추가: `stillness > 0.7` 게이트 (정지 상태일 때만 sit boost 적용)
   - `pose_knee` 임계값: 0.25 → 0.35 (더 확실한 무릎 꺾임에만 반응)
   - cap: 0.40 → 0.25 (과도한 sit boost 방지)
   - 이유: 기존 Rule 3의 비대칭 boost가 stand→sit 오분류 유발

3. **walk→sit 전이 허용** (~line 5349):
   - `_POSTURE_TRANSITION_ALLOWED['walk']`에 `'sit'` 추가
   - 이유: 걷다가 앉는 동작이 시간적 스무딩에서 차단되던 문제 해결

## 검증 상태
- 코드 변경 적용 확인: ✅
- 재학습 v4 모델과 통합: ✅ (v4 모델은 보행 피처 TOP 3, 피처 분포 개선)
- 실제 웹캠 테스트: 수동 검증 필요 (자동 테스트 불가)
- 휴리스틱 효과는 v4 모델의 원시 확률에 대한 후처리이므로, CV 정확도에는 반영되지 않음
