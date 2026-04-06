# 분석 시간 최적화

- **ID**: 011
- **날짜**: 2026-03-26
- **유형**: 기능 개선

## 작업 요약
YOLO 추론 파이프라인의 3가지 병목을 최적화했다:
1. 크롭 후보 4→2개 축소 (전체 프레임 + 중앙 크롭)
2. fast 모드 프레임 샘플 수 8→5개 축소
3. 4K 프레임 사전 다운스케일 (max 640px) 추가

결과: 추론 시간 약 60% 단축 (추정 ~8초 → 측정 2.9초, cold start 포함)

## 측정 결과
- 5프레임 × 2크롭 (warm): 2.24초
- 8프레임 × 2크롭 (warm): 3.24초
- 5프레임 × 2크롭 (cold, 모델 로딩 포함): 2.9초
- 응답에 `elapsed_sec` 필드 추가하여 프론트엔드에서 시간 표시

## 변경 파일 목록
### 수정
- `scripts/yolo_fall_runtime.py`:
  - `crop_candidates()`: 크롭 4→2 (전체 + 중앙 15-85%)
  - `_downscale_frame()`: 신규 함수, 640px 기준 사전 다운스케일
  - `infer_video()`: 다운스케일 적용 + `elapsed_sec` 시간 측정 추가
- `src/model/struct/video_analysis.py`:
  - `_infer_with_trained_model()`: sample_count fast 8→5, detailed 14→12
  - `analyze_upload()`: `analysis_speed_note`에 elapsed_sec 표시
