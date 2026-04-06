# 6종 행동 분류 런타임 연결

- **ID**: 023
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
파일명 기반 행동 추정을 메인 런타임에서 분리하고, 사람 추적 기반 특징을 활용하는 6종 행동 분류 경로를 연결했다. 현재 샘플 데이터셋만으로는 6종 학습 모델 구성이 어려워, 명시적인 `behavior-rule-v1` 행동 프로파일 모델 산출물을 생성하고 메인 분석 결과에서 해당 모델을 사용하도록 변경했다.

## 변경 파일 목록
### 행동 모델
- `src/model/libs/action_behavior_model.py`
  - `behavior-rule-v1` 모델/요약 산출물 생성
  - 6종 행동 class order, threshold, note 정의

### 서버 분석 로직
- `src/model/struct/video_analysis.py`
  - 행동 모델 메타 로더 추가
  - `behavior_state`가 규칙 기반 행동 모델도 ready로 인식하도록 수정
  - person-feature / trained-yolo 추론 결과에 `behavior_inference` 추가
  - `_predict_behavior_from_runtime()` 추가로 걷기/뛰기/서기/앉기/눕기/낙상 판정
  - 행동 fallback 사용 시 diagnostics 경고, 모델 사용 시 info 메시지 추가

### 대시보드
- `src/app/page.dashboard/view.pug`
  - 행동 분류 카드에 실제 행동 소스/ fallback 여부 표시
  - 모델 정보 영역에 6종 행동 모델 표시

## 테스트 결과
- 낙상 샘플: `fall` / source=`behavior-rule-v1`
- 비낙상 샘플: `walking` / source=`behavior-rule-v1`
- `behavior_state.ready = True`
- 빌드 성공 및 오류 없음
