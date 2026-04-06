# 추론 시간 최적화 (seek 기반 프레임 추출)

- **ID**: 003
- **날짜**: 2026-03-27
- **유형**: 성능 최적화

## 작업 요약
RF 파이프라인 추론 시간이 20~30초(사용자 체감) 걸리던 문제를 프로파일링하여 병목 구간(프레임 추출 92%)을 식별하고, 순차 읽기를 seek 기반 추출로 교체하여 파이프라인 총 시간을 9.88s → 4.71s로 52% 단축했다.

## 프로파일링 결과

### Before (순차 읽기)
| 단계 | 시간 | 비율 |
|------|------|------|
| model_load | 0.104s | 1% |
| **frame_extract** | **9.058s** | **92%** |
| yolo_predict | 0.484s | 5% |
| feature_extract | 0.006s | 0% |
| rf_predict | 0.064s | 1% |
| **total** | **9.88s** | 100% |

### After (seek 기반 추출)
| 단계 | 시간 | 비율 |
|------|------|------|
| model_load | 0.116s | 2% |
| **frame_extract** | **3.902s** | **83%** |
| yolo_predict | 0.404s | 9% |
| feature_extract | 0.006s | 0% |
| rf_predict | 0.059s | 1% |
| **total** | **4.71s** | 100% |

- 테스트 파일: 4K(3840x2160) 60fps 10초 mp4
- 추출 프레임: 10장the, YOLO 검출: 5장
- 분석 결과 동일: fall_prob=0.6088

## 원인 분석
순차 `cap.read()` 루프가 600프레임 전체를 디코딩하면서 step(60)마다 1프레임만 유지. 4K H.264 디코딩 비용이 높아 불필요한 프레임 디코딩이 병목.

## 해결 방법
`cv2.CAP_PROP_POS_FRAMES`를 이용한 seek 기반 추출로 변경. 대상 프레임 인덱스만 직접 점프하여 디코딩.

## 변경 파일 목록

### Model
- `src/model/struct/video_analysis.py`
  - `_infer_rf_pipeline` 메서드: `_perf` 프로파일링 딕셔너리 추가
  - 프레임 추출 로직을 seek 기반으로 교체 (total_frames > 0 && step > 1 일 때)
  - 짧은 영상이나 frame_count 미확인 시 순차 읽기 fallback 유지
  - `runtime_inference` 응답에 `perf` 키 추가
