# RF-Dual 리콜 개선용 motion guard 미세조정

- **ID**: 003
- **날짜**: 2026-04-22
- **유형**: 버그 수정

## 작업 요약
RF-Dual 실데이터 검증 200건의 FN/FP를 재분석한 결과, 미탐 9건 중 4건이 `motion_guard`에 의해 최종 낙상 판정이 취소되는 패턴을 확인했다.
이를 바탕으로 일반 motion guard의 완화 조건을 `강한 RF 점수` 또는 `bbox 높이 변화가 큰 경우`로 제한하여, 실제 낙상으로 보이는 케이스가 과도하게 억제되지 않도록 조정했다.

## 변경 파일 목록
### 소스 코드
- `src/model/struct/video_analysis.py`
  - RF-Dual의 일반 `motion_guard` 억제 조건에 soft override를 추가
  - `fall_score >= max(effective_threshold + 0.20, 0.55)` 또는 `height_std >= 35.0`인 경우 suppress를 건너뛰도록 조정

### 평가 결과
- `storage/training/fall-detection/evaluation/rf_dual_runtime_eval_20260422_recall_tuned.json`
  - 동일 200개 검증셋 재평가 결과 저장
  - 변경 전: accuracy 0.905 / precision 0.901 / recall 0.910 / f1 0.9055
  - 변경 후: accuracy 0.905 / precision 0.8785 / recall 0.940 / f1 0.9082
  - 해소된 FN: `00576_H_D_BY_C2.mp4`, `01826_Y_A_SY_C1.mp4`, `02787_H_D_FY_C5.mp4`
  - 새로 증가한 FP: `00110_H_A_N_C4.mp4`, `01683_Y_E_N_C3.mp4`, `02327_H_A_N_C2.mp4`

### 분석 메모
- 미탐은 주로 `safe`/`posture_only` 상태에서 발생했고, 그중 일부는 RF score가 이미 confirm threshold를 넘었는데도 motion guard가 낮춰버리는 케이스였다.
- 이번 조정은 글로벌 threshold 변경 없이 suppressor 조건만 좁혀 리콜을 우선 개선한 1차 튜닝이다.
