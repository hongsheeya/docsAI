# FallAI 프레임 처리 및 다중 인원 추적 점검

작성일: 2026-06-16

## 1. 결론

현재 운영 파이프라인은 **영상 안의 여러 사람을 모두 표시할 수는 있지만, 낙상 판정은 프레임별 대표 1명 중심**으로 수행한다.

- 서버 YOLO 결과의 `detection_frames`에는 프레임별 모든 사람 bbox/keypoint가 들어간다.
- 그러나 RF-Fall/XG-Posture에 들어가는 `timeseries`는 프레임마다 **면적이 가장 큰 사람 1명**을 선택해 만든다.
- 따라서 현재 구조는 “여러 사람을 각각 persistent ID로 분리 추적하고 각 사람별 낙상 판정”까지 완료된 상태가 아니다.
- 사람이 2명 이상이고, 낙상자가 화면에서 가장 큰 사람이 아니거나 서로 교차하면 FN/FP 위험이 커진다.

발표/보고에서는 다중 인원 추적을 완료 기능으로 설명하면 안 되고, **현재는 단일 대표 인물 기반, 다중 인원은 개선 과제**라고 설명해야 한다.

## 2. 현재 프레임 처리 방식

### 2.1 브라우저 표시 프레임

실시간 화면의 프라이버시 skeleton 표시는 브라우저에서 MediaPipe Pose Landmarker를 사용한다.

- 입력: 웹캠 video element
- 처리 주기: `MP_FRAME_INTERVAL_MS = 66ms`, 약 15fps throttle
- 모델: MediaPipe `pose_landmarker_lite`
- 표시: skeleton-only 기본, 관리자 raw overlay 전환 가능
- 현재 표시 skeleton: `result.landmarks[0]` 기준

즉 브라우저 프라이버시 화면도 기본적으로 첫 번째 감지 인물 위주로 그린다. 여러 사람이 있을 때 모든 사람 skeleton을 안정적으로 라벨링하는 구조는 아직 아니다.

### 2.2 서버 판정 프레임

서버 판정은 YOLOv8n-pose 기반 공유 시계열을 만든 뒤 RF-Fall과 XG-Posture가 같이 사용한다.

```text
영상 / 실시간 WebM 청크
  -> OpenCV 프레임 샘플링
  -> YOLOv8n-pose 추론
  -> 프레임별 사람 bbox/keypoint 추출
  -> 대표 인물 1명의 normalized timeseries 생성
  -> RF-Fall v2 낙상 판정
  -> XG-Posture 자세/행동 판정
  -> 가림 보조, 표정/상태 보조 근거 결합
```

현재 주요 설정은 다음과 같다.

| 구분 | 현재 값 | 의미 |
|---|---:|---|
| 실시간 chunk 길이 | 4초 | 서버에 보내는 기본 분석 단위 |
| 실시간 stride | 2초 | 2초마다 4초 청크 생성, 2초 중첩 |
| 실시간 추출 fps | 4fps | 4초 청크 기준 약 16프레임 추출 |
| 실시간 RF fps | 3fps | RF-Fall feature에는 downsample 적용 |
| 실시간 YOLO imgsz | 320 | 지연 최소화 우선 |
| 업로드 fast | 4fps / imgsz 416 | 빠른 1차 응답 |
| 업로드 balanced/full | 최대 8fps / imgsz 640 | 정밀도 우선 |
| YOLO confidence | 실시간 0.15, 업로드 0.25 | 사람 검출 threshold |

## 3. 현재 다중 인원 처리 상태

### 3.1 표시 데이터

`detection_frames`에는 프레임별 모든 사람 detection이 포함된다.

```text
detection_frames[]
  frame_idx
  time_sec
  detections[]
    x1, y1, x2, y2
    conf
    keypoints[17]
```

이 데이터는 화면 overlay/replay에서 여러 사람 bbox와 skeleton을 그리는 데 쓸 수 있다.

### 3.2 판정 데이터

RF/XG 모델이 실제로 사용하는 `timeseries`는 프레임마다 다음 기준으로 1명을 고른다.

```text
best_idx = 사람 class 중 bbox area가 가장 큰 detection
```

그 결과:

- 화면에 여러 사람이 보여도 모델 feature는 대표 1명만 반영한다.
- 대표 인물은 frame마다 다시 고르므로, 사람이 교차하면 대표가 바뀔 수 있다.
- `track_id`, `person_id`, `IDF1`, `MOTA` 같은 추적 지표는 아직 운영 데이터에 없다.

## 4. 인원수에 따른 성능 영향

현재 다중 인원 라벨 검증셋이 없어서 2명 이상 정확도는 확정 수치로 말할 수 없다. 아래는 현재 코드 구조 기준의 점검 결과다.

| 인원수 | 현재 동작 | 정확도 영향 | FPS 영향 | RTT 영향 | 위험도 |
|---:|---|---|---|---|---|
| 1명 | 대표 인물 = 실제 대상일 가능성 높음 | 현재 운영 모델 성능에 가장 가까움 | 기준 | 기준 | 낮음 |
| 2명 | 큰 bbox 1명을 대표로 선택 | 낙상자가 작게 잡히면 FN 가능 | YOLO 후처리 소폭 증가 | 소폭 증가 | 중간 |
| 3명 | 모든 detection은 표시되지만 판정은 대표 1명 | 교차/가림/배경 인물 때문에 대표 전환 가능 | 후처리 증가 | 증가 | 높음 |
| 4명 이상 | 독립 판정 없음 | 낙상자 누락/다른 사람 오탐 가능성 큼 | detection 수에 따라 하락 | 큐 적체 가능 | 매우 높음 |

정확도 관점에서 가장 위험한 경우:

1. 낙상자가 뒤쪽에 있어 bbox가 작다.
2. 보호자/동행자가 앞쪽에 크게 잡힌다.
3. 낙상 순간에 다른 사람이 화면을 가린다.
4. 두 사람이 교차하면서 frame마다 대표 인물이 바뀐다.
5. 침대/의자 주변에서 한 명은 눕고 한 명은 서 있는 경우.

## 5. 현재 측정 가능한 성능 지표

현재 UI/서버에서 이미 볼 수 있는 지표는 다음과 같다.

| 지표 | 위치 | 의미 |
|---|---|---|
| `server_timing.total_server_sec` | 분석 응답 | 서버 전체 처리 시간 |
| `runtime_inference.perf.single_pass_extract` | 분석 응답 | YOLO/시계열 추출 시간 |
| `runtime_inference.perf.yolo_predict` | 분석 응답 | YOLO pose 추론 시간 |
| `runtime_inference.frame_sampling` | 분석 응답 | 샘플링 fps, imgsz, 실제 추출 프레임 수 |
| `realtimePerfStats.avgRtt` | 브라우저 실시간 UI | 최근 10개 청크 RTT 평균 |
| `realtimePerfStats.avgServer` | 브라우저 실시간 UI | 최근 10개 청크 서버 처리 평균 |

현재 문서화된 단일 인물/일반 영상 기준 측정값:

| 항목 | 측정값 |
|---|---:|
| YOLOv8n-pose keypoint 검출 평균 | 13.43ms/frame |
| YOLOv8n-pose KP 검출률 | 93.06% |
| 업로드 balanced 서버 시간 개선 후 | 약 22.9초 |
| 업로드 chunk 분석 개선 후 | 약 4.25초 |
| 메인 fast RF-Dual 개선 후 | 약 12.9초 |

이 값들은 다중 인원 전용 벤치마크가 아니라 현재 일반/단일 대표 인물 기준이다.

## 6. 다중 인원 성능 검증에 필요한 데이터

다중 인원 성능을 정확도, FPS, RTT까지 검증하려면 다음 라벨이 필요하다.

| 데이터 | 필수 라벨 | 이유 |
|---|---|---|
| 1명 단독 낙상/비낙상 | fall_label, behavior_label | baseline 성능 측정 |
| 2명 이상, 낙상자 1명 | person_id, fall_label per person | 낙상자 누락 여부 확인 |
| 2명 이상, 비낙상자만 존재 | person_id, behavior_label | 동행자 오탐 확인 |
| 교차/가림 상황 | person_id 연속 추적 라벨 | ID switch 측정 |
| 앞사람/뒷사람 크기 차이 | target_person_id | largest-bbox 대표 선택 실패 측정 |

필수 평가 지표:

- 낙상 정확도: Accuracy, Precision, Recall, F1
- 인원 추적: IDF1, ID switch count, MOTA 또는 단순 track continuity
- 속도: server FPS, YOLO FPS, end-to-end RTT p50/p95
- 안정성: queue length, retry count, dropped/discarded chunk count

## 7. 개선해야 할 구조

다중 인원까지 제대로 하려면 다음 구조로 바꿔야 한다.

```text
YOLO detections per frame
  -> tracker(ByteTrack/SORT/IoU tracker)
  -> person_id별 timeseries 생성
  -> person_id별 RF-Fall/XG-Posture 추론
  -> 가장 위험한 person_id를 event로 승격
  -> UI에 P1/P2/P3 라벨, risk, posture, track duration 표시
```

구현 우선순위:

1. `detection_frames.detections[]`에 `person_label`, `track_id`, `is_primary`를 추가한다.
2. IoU/center-distance 기반 lightweight tracker로 4초 청크 안의 track을 유지한다.
3. track별 `timeseries`를 따로 만들고, 최소 프레임 수를 만족하는 track만 추론한다.
4. 실시간에서는 이전 청크 tail cache를 `session_id + track_id` 단위로 저장한다.
5. 최종 결과는 `person_results[]`로 내려주고, 기존 `fall_detected/risk_score`는 최고 위험 track으로 유지한다.

## 8. 발표용 표현

권장 표현:

> 현재 운영 모델은 단일 대표 인물 기반으로 안정화되어 있으며, 화면에는 여러 사람 detection을 표시할 수 있습니다. 다만 다중 인원 환경에서 각 사람을 독립 추적해 person별 낙상 판정을 내리는 기능은 아직 개선 과제입니다. 인원이 늘어날수록 대표 인물 선택 오류와 ID 전환 때문에 정확도와 RTT가 영향을 받을 수 있어, 다음 단계에서는 person_id 추적과 person별 timeseries 기반 평가를 추가할 예정입니다.

피해야 할 표현:

> 여러 사람이 있어도 각각 완전히 분리 추적해서 낙상을 판단합니다.

현재 코드 기준으로는 위 표현은 사실이 아니다.
