# 행동 분류 이진화 및 fallback 제거

- **ID**: 005
- **날짜**: 2026-03-27
- **유형**: 기능 개선

## 작업 요약
기존 6종 행동 분류(걷기/뛰기/서기/앉기/눕기/낙상)를 낙상/비낙상 이진 분류로 단순화했다. RF 파이프라인 런타임이 6종 행동 특징을 제공하지 않아 fallback 경고가 뜨던 문제를 제거하고, RF 결과를 직접 사용해 `behavior-binary-v1` 규칙으로 분류하도록 변경했다.

## 변경 내용
- `_predict_behavior_from_runtime()`를 이진 분류 전용 로직으로 단순화
- 기본 행동 클래스 목록을 `non-fall`, `fall` 2개로 축소
- 파일명 기반 fallback도 `비낙상/낙상`만 반환하도록 수정
- 행동 모델 메타 기본값(`action_behavior_model.py`)을 이진 분류 기준으로 갱신
- 대시보드 문구를 "낙상/비낙상 분류 모델" 기준으로 변경

## 검증 결과
- API 응답 확인:
  - `behavior_class: fall`
  - `behavior_label: 낙상`
  - `behavior_source: behavior-binary-v1`
  - `behavior_fallback: False`

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - 행동 분류 상태/추론/기본값/진단 문구 수정
- `src/model/libs/action_behavior_model.py`
  - 기본 모델 메타데이터를 이진 분류로 변경
- `src/app/page.dashboard/view.pug`
  - 행동 분류 UI 문구를 이진 분류 기준으로 조정
