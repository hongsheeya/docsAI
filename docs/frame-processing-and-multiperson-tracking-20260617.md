# FallAI 프레임 처리 및 다중 인원 추적/성능 보고서

작성일: 2026-06-17

## 1. 현재 결론

현재 운영 화면과 서버 응답은 여러 사람 skeleton/bbox를 표시할 수 있도록 개선했다. 다만 낙상 판단의 핵심 RF-Dual 공유 timeseries는 아직 프레임별 대표 인물 1명을 기준으로 feature를 만든다. 따라서 다중 인원 환경에서 각 사람별 독립 낙상 판정은 다음 단계 구현 과제다.

이번 수정으로 반영한 내용은 다음과 같다.

- 브라우저 skeleton 모드: MediaPipe `numPoses`를 1명에서 5명으로 확장했다.
- skeleton smoothing: 사람별 Kalman filter를 분리해 P1/P2/P3/P4/P5가 서로 섞이지 않게 했다.
- 서버 `detection_frames`: 상위 5명까지 `person_label`, `person_index`, `is_primary`, `bbox_area`를 추가했다.
- overlay 표시: 대표 판정 대상은 `is_primary=true`로 내려가며, 화면에서는 P-label을 표시할 수 있다.
- 성능 벤치마크: sample-fall 영상을 1~5명으로 합성해 pose 처리량/FPS/RTT 경향을 측정했다.

## 2. 프레임 처리 방법

### 2.1 실시간 브라우저 프레임

실시간 화면은 웹캠 video element에서 프레임을 받아 두 갈래로 처리한다.

1. 브라우저 프라이버시 skeleton 표시
2. 서버 분석용 WebM chunk 생성

브라우저 skeleton 표시는 MediaPipe Pose Landmarker를 사용한다.

| 항목 | 현재 값 |
|---|---:|
| 처리 간격 | `MP_FRAME_INTERVAL_MS = 66ms` |
| 표시 목표 | 약 15fps |
| 최대 skeleton 인원 | 5명 |
| 표시 라벨 | P1~P5 |
| smoothing | 사람별 33 landmark Kalman filter |
| 기본 화면 | skeleton-only |

이 처리는 화면 표시용이다. 서버 낙상 판정과 완전히 같은 모델을 쓰는 것은 아니다.

### 2.2 실시간 서버 분석 프레임

실시간 분석은 브라우저에서 WebM chunk를 만들고 서버에 보낸다.

```text
웹캠 입력
  -> 브라우저 skeleton 표시
  -> MediaRecorder WebM chunk 생성
  -> 서버 업로드
  -> OpenCV 프레임 샘플링
  -> YOLOv8n-pose 추론
  -> detection_frames 생성
  -> 대표 인물 timeseries 생성
  -> RF-Fall / XG-Posture / 가림 보조 / 표정 보조 결합
  -> 최종 낙상 위험 결과 반환
```

현재 실시간 분석 설정은 4초 chunk, 2초 overlap, 서버 추출 4fps 중심이다. 즉 한 chunk당 대략 16개 pose 샘플을 분석한다.

### 2.3 업로드 분석 프레임

업로드 모드는 영상 전체 또는 chunk window에서 프레임을 샘플링한다.

- fast 계열: 낮은 fps/imgsz로 빠르게 1차 판단
- balanced/full 계열: 더 높은 fps/imgsz로 검출률과 posture 안정성 확보
- 업로드 chunk 분석은 full-video shared timeseries를 재사용해 중복 YOLO 호출을 줄인다.

## 3. 다중 인원 처리 구조

### 3.1 표시 데이터

서버 응답의 `model_runtime.detection_frames[]`에는 프레임별 여러 사람 detection이 들어간다.

```json
{
  "frame_idx": 120,
  "time_sec": 4.0,
  "detections": [
    {
      "person_label": "P1",
      "person_index": 1,
      "is_primary": true,
      "bbox_area": 53218.4,
      "x1": 110.2,
      "y1": 50.1,
      "x2": 310.4,
      "y2": 410.8,
      "conf": 0.84,
      "keypoints": []
    }
  ]
}
```

기본 표시 제한은 상위 5명이다. 이 제한은 네트워크 payload, canvas draw 비용, 사람이 많을 때의 화면 가독성을 동시에 고려한 값이다.

### 3.2 판정 데이터

현재 운영 RF-Dual 공유 경로는 각 프레임에서 bbox 면적이 가장 큰 사람을 대표 인물로 선택한다.

```text
person detections
  -> bbox area 기준 대표 인물 선택
  -> 대표 인물 keypoint/bbox timeseries
  -> RF-Fall / XG-Posture feature window
```

따라서 사람이 여러 명일 때 낙상자가 대표 인물이 아니면 누락 가능성이 있다. 이 부분은 person별 timeseries를 만들고 각 person_id별로 모델을 돌리는 구조로 바꿔야 해결된다.

### 3.3 별도 ByteTrack 경로

`scripts/yolo_fall_runtime.py`와 일부 검증 스크립트에는 ByteTrack 기반 다중 track 처리가 이미 있다.

```text
YOLO track(ByteTrack)
  -> track_id별 bbox 시계열
  -> track별 sliding window
  -> track별 fall probability
  -> 최고 위험 track을 최종 event로 선택
```

이 경로는 연구/검증용으로는 유용하지만, 현재 운영 RF-Dual 공유 추론 경로에 완전히 통합되어 있지는 않다.

## 4. 1~5명 성능 벤치마크

### 2026-06-25 재측정 결론

실시간 기본 설정(`imgsz=320`)으로 1~20명 합성 타일링 벤치마크를 다시 측정했다. 결론은 “RTT만 보면 5명까지 괜찮지만, 검출 안정성까지 보면 3명까지”다.

| 인원 | pose FPS | 4초 chunk 추정 RTT | 평균 검출 인원 | 판단 |
|---:|---:|---:|---:|---|
| 2 | 171.89 | 0.140s | 1.92 | 안정 |
| 3 | 145.30 | 0.165s | 2.38 | 무저하 설명 가능 상한 |
| 4 | 145.97 | 0.164s | 5.50 | 과검출 증가 |
| 5 | 169.98 | 0.141s | 6.67 | 표시 가능, 판정 보수 |
| 6 | 170.41 | 0.141s | 0.00 | 검출 붕괴 |

정밀 설정(`imgsz=640`)에서는 14명까지 평균 검출 수가 실제 인원과 비교적 맞았고, 15명부터 과검출이 35% 이상으로 급증했다. 따라서 발표에서는 다음처럼 분리한다.

- 실시간 기본 무저하 설명 가능: 3명
- 실시간 표시 가능: 5명
- 640px 정밀/시연 표시 한계 후보: 14명
- 20명: 처리량 스트레스 테스트, 상용 판정 보증 아님

원본 산출물은 `outputs/performance/multiperson_frame_benchmark_20260625.json` 및 `outputs/performance/multiperson_frame_benchmark_20260625_640.json`에 저장했다.

벤치마크 조건:

- 입력: `src/assets/pres/sample-fall.mp4`
- 방법: 동일 영상을 1~5명으로 타일링한 합성 프레임
- 프레임: 케이스당 24프레임
- YOLO: `yolov8n-pose.pt`, `imgsz=320`, `conf=0.15`, CPU
- 반복: 3회 측정 후 median
- 목적: 정확도 확정이 아니라 pose 처리량/FPS/RTT 경향 확인

| 인원 | pose FPS | 4초 chunk 추정 RTT | 평균 검출 인원 | 검출 범위 | 평균 keypoint 인원 | 평균 visible KP |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 206.58 | 0.116s | 1.00 | 0~2 | 1.00 | 15.76 |
| 2 | 204.07 | 0.118s | 1.92 | 0~4 | 1.92 | 16.66 |
| 3 | 186.16 | 0.129s | 1.62 | 0~5 | 1.62 | 16.81 |
| 4 | 117.40 | 0.204s | 3.75 | 0~7 | 3.75 | 16.79 |
| 5 | 205.17 | 0.117s | 4.62 | 0~8 | 4.62 | 16.83 |

해석:

- 처리량/RTT 기준으로는 5명까지 4fps 실시간 샘플링 예산 안에 들어왔다.
- 다만 이 수치는 pose-only 합성 벤치마크라 실제 네트워크 RTT, 브라우저 인코딩, 서버 큐, person별 모델 추론 비용은 별도 반영해야 한다.
- 3명 케이스의 평균 검출 인원이 낮은 것은 타일링된 낙상 자세/스케일 영향이 섞인 결과다. 실제 다중 인원 검증셋으로 다시 봐야 한다.
- 정확도는 라벨이 없기 때문에 확정할 수 없다. 이 벤치는 “5명 skeleton 표시와 pose 처리량” 검증이다.
- 따라서 “인원 증가에도 성능 저하 없음”이라고 말하면 안 된다. 정확한 표현은 “합성 pose-only 기준 RTT/처리량 병목은 크지 않았지만, 다중 인원 판정 성능은 미검증”이다.

## 5. 인원수별 영향 정리

| 인원 | 표시 | 현재 판정 안정성 | FPS/RTT 영향 | 위험 요소 | 운영 권장 |
|---:|---|---|---|---|---|
| 1 | 안정 | 가장 안정 | 기준 | 낮음 | 운영 가능 |
| 2 | 안정 | 대표 인물 오류 가능 | 작음 | 앞/뒤 사람 크기 차이 | 운영 가능, 이벤트 확인 필요 |
| 3 | 표시 가능 | 교차/가림 시 대표 전환 위험 | 작음~중간 | 낙상자가 작은 bbox일 때 FN | 주의 운영 |
| 4 | 표시 가능 | person별 판정 전에는 위험 증가 | 중간 | ID 전환, payload 증가 | skeleton 표시 가능, 판정은 보수적 |
| 5 | 표시 가능 | person별 판정 구현 전에는 제한적 | 중간 | 동시 가림/교차 | 표시 목표 충족, 판정 개선 필요 |

현재 최적 제한:

- skeleton 표시 제한: 5명
- 서버 overlay payload 제한: 5명
- 대표 인물 기반 낙상 판정 권장: 1~2명
- person별 낙상 판정 통합 후 목표: 5명

## 6. 정확도, FPS, RTT 평가 기준

다중 인원에서 실제 성능을 확정하려면 다음 지표를 분리해서 봐야 한다.

| 지표 | 측정 방법 | 목표 |
|---|---|---:|
| 낙상 Accuracy/F1 | person별 fall label 검증셋 | 95% |
| 낙상 Recall | 낙상자 1명 포함 다중 인원 영상 | 95% 이상 |
| False Positive | 비낙상 동행자 포함 영상 | 낮을수록 좋음 |
| ID switch | track_id/person_id 연속성 | 낮을수록 좋음 |
| 처리 FPS | 서버 pose 처리 프레임 수 / 처리 시간 | 실시간 4fps 이상 |
| RTT p50/p95 | 브라우저 요청~응답 시간 | chunk interval 이하 |
| queue discard | 실시간 큐 폐기 수 | 0 또는 낮게 |

현재 벤치마크는 FPS/RTT의 pose-only 부분만 검증했다. 정확도와 ID 유지율은 실제 다중 인원 라벨 영상이 필요하다.

## 7. 개선 방안과 진행 상태

완료:

- skeleton 모드 5명 표시로 확장
- 사람별 Kalman filter 분리
- 서버 detection overlay에 P-label/is_primary 추가
- 서버 overlay payload 기본 상위 5명 제한
- 1~5명 합성 pose 처리량 벤치마크 작성

진행해야 할 항목:

- 운영 RF-Dual 공유 경로에 lightweight IoU/center tracker 추가
- track별 timeseries 생성
- person_results[] 응답 추가
- 최고 위험 person_id를 기존 `fall_detected/risk_score`에 연결
- 실시간 chunk 간 track tail cache 추가
- 실제 다중 인원 라벨 영상으로 1~5명 정확도/FPS/RTT 재검증

## 8. 학습 현황

2026-06-17 03:07 UTC 기준:

| 모델 | 현재 active F1 | 목표 | 상태 |
|---|---:|---:|---|
| RF-Fall 운영 모델 | 98.08% | 95% | 목표 충족 |
| XG-Posture | 94.31% | 95% | 반복 학습 진행 |
| XG-Posture 가림 보조 | 90.01% | 95% | 반복 학습 진행 |
| AI-Hub 82 표정 | 90.15% | 95% | 재수신/학습 진행, 원천 zip cache 병목 |
| AI-Hub 173 상태 | 93.10% | 95% | 학습 진행 |

AI-Hub 82는 `/mnt/data` 여유 공간이 부족하고 기존 source zip cache가 약 462GB라 `unexpected end of data` 또는 `No space left on device`가 반복될 수 있다. 학습은 켜두되, 재수신/압축 해제 작업 공간을 `/opt/app/tmp` 같은 overlay 영역으로 분리하는 것이 다음 조치다.

## 9. 발표용 요약

현재 시스템은 단일 대표 인물 기준 낙상 판단을 안정화한 상태이며, 화면 skeleton과 서버 overlay는 5명까지 표시되도록 개선했다. 합성 벤치마크에서는 5명 조건에서도 pose 처리량/RTT가 실시간 4fps 요구를 넘겼다. 다만 person별 독립 낙상 판단은 아직 운영 경로에 완전히 통합되지 않았고 실제 다중 인원 정확도 저하 여부도 검증되지 않았기 때문에, 다음 단계는 track_id 기반 person별 timeseries와 person_results[] 구조를 붙이고 실제 다중 인원 라벨 영상으로 정확도/FPS/RTT를 검증하는 것이다.
