# XG-Fall 하드케이스 회귀 복구 및 규칙 정밀화

- **ID**: 001
- **날짜**: 2026-04-10
- **유형**: 버그 수정

## 작업 요약
침대 기상/정면·후면 낙상 보강 과정에서 발생한 XG-Fall 회귀를 정리하고, 낙상 최종판정은 XG-Fall만 사용하도록 유지한 채 hard-case 규칙을 정밀화했다. ONNX 기반 480px 실시간 처리, rolling memory, 3단계 threshold, failure report, 낙상 전용 feature 확장 위에 front/back false negative 복구와 bed false positive 억제를 위한 좁은 override/suppressor를 추가했다.

최종 검증 기준 최신 평가 결과는 recall 0.9091, precision 0.9091, F1 0.9091, accuracy 0.9048이며, 잔여 실패는 front_back_fall 1건과 front_back_nonfall 1건으로 축소되었다.

## 변경 파일 목록

### video_analysis.py (model/struct)

1. **실시간·하드케이스 낙상 판정 규칙 보정**
   - `directional_collapse_override` 추가
   - `spike_only_suppressor`, `reverse_motion_suppressor`, `static_floor_like_suppressor` 추가
   - `aspect_only_suppressor` 예외 조건 보정
   - 단일 추론(`_infer_xg_fall`)과 듀얼 추론(`_infer_xg_dual`)에 동일 로직 반영

2. **기존 구조 유지**
   - 자세 모델이 최종 낙상판정에 개입하지 않도록 유지
   - threshold 3단계(`suspect/confirm/high`) 및 failure report 흐름 유지
   - bed / front-back 사례를 케이스 타입별로 계속 추적 가능하도록 후처리 메타데이터 유지

## 검증 상태
- 프로젝트 빌드: ✅
- 최신 평가 리포트 생성: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_052226.json`
- 검증 지표: ✅ recall 0.9091 / precision 0.9091 / F1 0.9091 / accuracy 0.9048
- 잔여 과제: front/back 극단 사례 1 FN, 1 FP 추가 분리 필요
