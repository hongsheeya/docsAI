# 실시간 RF 민감도 개선 — B(연속 확인) + D(모션 가드 강화)

- **ID**: 005
- **날짜**: 2026-04-03
- **유형**: 기능 추가

## 작업 요약
실시간 웹캠 모드에서 빠르게 앉기/몸 숙이기 등 일상 동작이 낙상으로 오판되는 문제를 B+D 전략으로 개선했다. D(백엔드): realtime 전용 모션 가드를 RF-Pipeline / RF-Pose 양쪽 추론 함수에 추가하여, 높이 비율·수직이동·중심 분산이 낙상에 미달하면 점수를 0.30으로 억제. B(프론트엔드): 연속 2회 이상 낙상 판정 시에만 최종 경보를 발동하며, 1회만 감지 시 "확인 대기" 상태로 표시.

## 변경 파일 목록

### 백엔드 (D: 모션 가드 강화)
- `src/model/struct/video_analysis.py`
  - `_infer_rf_pipeline()`: realtime 전용 enhanced Motion Guard 추가 (final_height_ratio>0.55 AND delta_y_max<20 AND center_y_std<25 → score 0.30)
  - `_infer_rf_pose_pipeline()`: 동일 guard 추가

### 프론트엔드 (B: 연속 확인)
- `src/app/page.dashboard/view.ts`
  - `realtimeConsecutiveFallCount`, `realtimePendingConfirmation` 프로퍼티 추가
  - `dispatchRealtimeChunk()`: 연속 2회 이상 낙상 판정 시에만 `fall_detected=true`, 1회는 "확인 대기"
  - `startRealtimeAnalysis()`, `stopRealtimeAnalysis()`: 새 프로퍼티 초기화/리셋
  - `riskClass()`: 'caution' 레벨 추가 (yellow 스타일)
  - 실시간 메시지에 "⚠️ 낙상 확인 대기" 상태 표시
- `src/app/page.dashboard/view.pug`
  - 실시간 미니 패널: 3상태(정상/확인 대기/낙상 감지) 인디케이터로 변경

## 기대 효과
- 빠르게 앉기(0.74→0.30 억제) 및 몸 숙이기(0.68→0.30 억제)의 단발성 오판 차단
- 실제 낙상(≥2연속 고점수)은 정상 감지 유지
- 1회만 감지된 경우 "확인 대기" 시각적 피드백으로 사용자 혼란 방지
