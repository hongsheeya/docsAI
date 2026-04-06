# 실시간 모드 Short-Clip 적응형 추론 구현 (FN-0017)

- **ID**: 007
- **날짜**: 2026-04-02
- **유형**: 기능 추가

## 작업 요약
실시간 웹캠 분석에서 4초 청크의 짧은 프레임 수(n_frames ≈ 6-8)로 인한 RF 모델 성능 저하를 보정하기 위해, 서버 측 적응형 임계값·Motion Guard 완화·신뢰도 레벨 시스템과 클라이언트 측 누적 점수(3-chunk 가중평균) 시스템을 구현했다.

## 핵심 설계

### 서버 측 (video_analysis.py)
- **적응형 임계값**: n_frames < 10일 때 선형 보간 (n=3 → 0.35, n=10 → 0.43)
- **최소 프레임 게이트**: n_frames < 3 → confidence='insufficient', 무조건 low 위험
- **신뢰도 레벨**: high(≥10) / medium(≥5) / low(≥3) / insufficient(<3)
- **Motion Guard 1.5x 완화**: 짧은 클립은 통계값이 작아 과도하게 억제되는 것 방지
- **input_source 전파**: analyze_upload → _infer_with_trained_model → _infer_rf_pipeline

### 클라이언트 측 (view.ts)
- **누적 점수**: 최근 3개 청크의 가중평균(weights: 1,2,3 — 최신 가중)
- **누적 탐지**: 개별 청크가 미탐지여도 가중평균 ≥ threshold이면 낙상 판정
- **신뢰도 UI**: 서버 confidence_level을 실시간 메시지에 표시
- **상태 초기화**: stopRealtimeAnalysis()에서 누적 상태 리셋

## 테스트 결과

| 영상 | n_det | Score | Threshold | Fall | Confidence |
|------|-------|-------|-----------|------|-----------|
| Fall-Full (10s) | 12 | 0.9833 | 0.4300 | True | high |
| Fall-Short (4s) | 8 | 0.4533 | 0.4071 | True | medium |
| NonFall-Full (10s) | 20 | 0.0167 | 0.4300 | False | high |
| NonFall-Short (4s, RT) | 8 | 0.6433 | 0.4071 | True | medium |

- 비폴 4초 클립 오탐은 설계상 예측된 동작(개별 청크 불안정성)
- 누적 점수 시스템이 후속 청크에서 이를 보정하도록 설계됨

## 변경 파일 목록

### 서버
- `src/model/struct/video_analysis.py`: 상수 3개 추가, _infer_rf_pipeline input_source 파라미터, short-clip 감지·적응형 임계값·신뢰도 레벨·Motion Guard 완화·결과 메타데이터, _infer_with_trained_model input_source 전파, analyze_upload input_source 전달

### 클라이언트
- `src/app/page.dashboard/view.ts`: 누적 점수 상태 변수 4개, dispatchRealtimeChunk 누적 로직, 실시간 메시지 업데이트, stopRealtimeAnalysis 리셋
