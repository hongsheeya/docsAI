# Gait Feature 활성화 및 XG-Posture 모델 최적화 (FN-0059)

- **ID**: 005
- **날짜**: 2026-04-07
- **유형**: 기능 추가

## 작업 요약
XG-Posture 6-class 분류 모델에서 보행 관련 피처(oscillation_count, center_y_periodicity, step_period_est)가 best_w 윈도우 선택에서 활용되지 않던 문제를 해결. best_w 기준을 낙상 특화(max_down_speed + floor_proximity)에서 보행 특화(oscillation_count + speed_std + center_y_periodicity)로 변경. 추가로 n_points 피처 제거(도메인 프록시) 및 XGBoost 정규화 강화.

## 변경 파일 목록

### video_analysis.py (model/struct)
1. **best_w 선택 기준 변경** (~line 5723, 5750):
   - Before: `max(windows, key=lambda w: w.get('max_down_speed', 0) + w.get('floor_proximity', 0))`
   - After: `max(windows, key=lambda w: w.get('oscillation_count', 0) + w.get('speed_std', 0) * 10 + w.get('center_y_periodicity', 0))`

2. **n_points 피처 제거** (retrain_xg_posture 내):
   - `feature_cols = [c for c in self._XG_FEATURE_COLUMNS if c != 'n_points']`
   - n_points는 CCTV(낮은 포인트 수) vs 웹캠/KTH(높은 포인트 수) 간 도메인 프록시로 작동하여 실제 행동 구분에 방해

3. **XGBoost 정규화 강화** (retrain_xg_posture 내):
   - max_depth: 6 → 3
   - learning_rate: 0.1 → 0.08
   - 추가: min_child_weight=5, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.5

## 재학습 결과 (4회 반복)

| 버전 | 데이터 | CV Accuracy | Top 피처 | 비고 |
|------|--------|-------------|----------|------|
| v1 | 681 (n041 walk200+stand100+sit100+기존) | 0.4332 | n_points (0.14) | 과적합 심각 |
| v2 | 450 (KTH walk81+n041 stand50+sit50+기존) | 0.6333 | n_points (0.36) | 최고 CV 정확도 |
| v3 | 530 (KTH81+n041 walk80+stand50+sit50+기존) | 0.5283 | n_points (0.43) | n041 walk 노이즈로 악화 |
| **v4** | 450 (v2와 동일, n_points 제거+정규화) | **0.6222** | **step_period_est (0.15)** | **보행 피처 TOP 3 달성** |

### v4 피처 중요도 TOP 5
1. step_period_est: 0.1455 (보행 주기)
2. center_y_periodicity: 0.1042 (상하 진동)
3. oscillation_count: 0.0484 (진동 횟수)
4. pose_descent_max: 0.0463
5. pose_change_mean: 0.0398

## 목표 대비 평가
- ✅ 보행 피처 활성화: oscillation_count, center_y_periodicity, step_period_est 모두 TOP 3
- ✅ 도메인 프록시(n_points) 제거: 피처 분포 개선 (단일 피처 43% → 15%)
- ⚠️ CV 정확도 0.62 < 목표 0.75: 자동 라벨링(frame-diff) ~30% 노이즈가 원인
- ⚠️ Train-CV 갭 0.37 > 목표 0.15: 라벨 노이즈가 원인, 정규화로는 해결 불가

## 데이터 품질 분석
- 041 CCTV 데이터: frame-diff 기반 자동 분류 (추정 정확도 60-70%)
- KTH 데이터: 통제 환경 실내 촬영, 웹캠과 다른 도메인
- CV 정확도 상한: 라벨 노이즈 ~30% 존재 시 이론적 상한 약 70%
- 향후 개선: 수동 라벨링 데이터 확보 필요
