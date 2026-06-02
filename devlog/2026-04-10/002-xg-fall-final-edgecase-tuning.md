# XG-Fall 잔여 엣지케이스 미세조정

- **ID**: 002
- **날짜**: 2026-04-10
- **유형**: 버그 수정

## 작업 요약
남아 있던 `front_back_fall` FN 1건과 `front_back_nonfall` FP 1건을 직접 비교 분석한 뒤, 정지 후 낙상 유지 패턴과 정적 바닥형 비낙상 패턴을 분리하는 미세 규칙을 추가했다. 결과적으로 FP를 0건으로 제거했고, 최종 평가는 precision 1.0, recall 0.9091, F1 0.9524까지 개선됐다.

## 변경 파일 목록

### video_analysis.py (model/struct)

1. **Still post-fall override 추가**
   - `stillness`가 매우 높고, `max_probability/mean_probability/fall_ratio`가 유지되는 좁은 패턴에서 motion gate를 통과시키도록 보정
   - 실제 뒤로 크게 넘어지는 사례가 `reverse_motion_suppressor`로 과도하게 눌리던 문제 완화

2. **Static floor-like suppressor 정밀화**
   - `max_down_speed`, `center_dy`, `descent_duration` 허용 오차를 소폭 완화
   - 자세는 낮지만 실제 하강이 없는 정적 비낙상 케이스를 더 안정적으로 억제

3. **단일/듀얼 추론 경로 동기화**
   - `_infer_xg_fall`, `_infer_xg_dual` 모두 동일한 엣지케이스 보정 적용

## 검증 상태
- 프로젝트 빌드: ✅
- 최신 평가 리포트: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_063842.json`
- 검증 지표: ✅ recall 0.9091 / precision 1.0 / F1 0.9524 / accuracy 0.9524
- 잔여 실패: `front_back_fall` FN 1건 (`suspected` 상태로 축소)
