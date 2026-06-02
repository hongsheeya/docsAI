# RF 로그 기반 threshold 복원 적용 및 회귀 검증

- **ID**: 002
- **날짜**: 2026-04-14
- **유형**: 버그 수정 / 설정 복원

## 작업 요약
`training_summary.json`에 저장되어 있던 RF tuned threshold가 실제 런타임 판정에는 반영되지 않고 하드코딩된 `0.45`가 계속 사용되고 있던 불일치를 수정했다.
RF 런타임이 summary의 `tuned_thresholds.confirm` 값을 읽어 실제 판정, 위험도 가이드, prototype_info 메타데이터에 일관되게 적용하도록 복원했다.

## 변경 파일 목록

### 런타임 복원
- `src/model/struct/video_analysis.py`
  - `_rf_thresholds()`, `_rf_confirm_threshold()`, `_rf_short_clip_threshold_max()` 헬퍼 추가
  - RF / RF-Dual / RF-Pose의 threshold 계산이 `training_summary.json`의 `tuned_thresholds.confirm`을 사용하도록 변경
  - `risk_score_guide`, `prototype_info.decision_thresholds`, heuristic 보조 판정도 동일 threshold를 사용하도록 정합성 수정

### 번들 동기화
- `bundle/src/model/struct/video_analysis.py`
  - 동일 복원 패치 반영

## 복원 결과
- 현재 summary 기준 RF confirm threshold: `0.781`
- 기존 하드코딩 runtime threshold: `0.45`
- 복원 후 `prototype_info`의 `decision_thresholds.fall_detected`가 `0.781`로 표시됨

## 회귀 검증
- `00110_H_A_N_C1.mp4` → `fall_detected=False`, `risk_score=0.454`, `decision_state=posture_only`
- `00005_H_A_N_C4.mp4` → `fall_detected=False`, `risk_score=0.5887`, `decision_state=uncertain`
- 기존 false positive였던 `00005_H_A_N_C4.mp4`가 threshold 복원만으로 비낙상으로 전환됨

## 한계
- 현재 복원은 **모델 자체 복원**이 아니라 **로그/summary 기반 threshold 복원**이다.
- 2026-04-02의 1000영상 RF v3 모델(`n_estimators=300`, `max_depth=None`, `min_samples_leaf=2`, `threshold=0.42`)은 devlog로는 확인되지만, 해당 모델 파일 자체는 현재 남아 있지 않아 완전 복원은 불가하다.
- `/opt/app/rf_model_300.pkl` 후보 모델은 16-feature 구형 포맷이라 현재 13-feature RF 런타임에 안전하게 재사용할 수 없음.