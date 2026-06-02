# XG-Fall 완전 검증 달성 및 suspected 리포트 강화

- **ID**: 003
- **날짜**: 2026-04-10
- **유형**: 기능 추가

## 작업 요약
잔여 `front_back_fall` FN 1건을 제거하도록 `reverse_motion_suppressor` 예외를 정밀화해 intake 검증셋 21건에서 XG-Fall precision/recall/F1/accuracy 1.0을 달성했다. 이어서 false negative/false positive가 0건인 상황에서도 경계 사례를 추적할 수 있도록 `suspected_actual_fall`, `suspected_actual_nonfall` 리포트를 추가했다.

## 변경 파일 목록

### video_analysis.py (model/struct)

1. **reverse_motion_suppressor 예외 보강**
   - `still_post_fall_override`가 활성인 경우 reverse-motion suppressor를 적용하지 않도록 조정
   - 뒤로 크게 넘어지는 실제 낙상 사례를 confirmed로 복구

2. **failure_report 확장**
   - `suspected_actual_fall_count`
   - `suspected_actual_nonfall_count`
   - `suspected_actual_falls`
   - `suspected_actual_nonfalls`
   를 추가해 borderline 사례를 별도 추적 가능하게 개선

## 검증 상태
- 프로젝트 빌드: ✅
- 완전 검증 리포트: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_070008.json`
- suspected 리포트 확장 검증 리포트: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_070210.json`
- 검증 지표: ✅ recall 1.0 / precision 1.0 / F1 1.0 / accuracy 1.0
- 추가 관찰: 실제 오분류는 0건이지만 `suspected_actual_nonfall` 3건이 남아 있어 경계 사례 모니터링 대상으로 유지 가능
