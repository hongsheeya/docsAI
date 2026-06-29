# 분석 시간 최적화 계획

현재 목표는 업로드/실시간 행동분석 시간을 지금보다 50% 이상 줄이는 것입니다.

## 0. 2026-06-02 적용 결과

업로드 분할 타임라인의 중첩 정책은 유지하면서, 청크별 중복 추론을 제거했습니다.

적용 내용:

1. `4초 창 / 2초 stride` 중첩 window는 유지합니다.
2. 업로드 청크 분석에서 전체 영상의 YOLO pose timeseries를 한 번만 추출합니다.
3. 각 청크는 full-video timeseries를 window 단위로 slice해서 RF-Dual에 전달합니다.
4. 공유 timeseries slice가 실패하면 기존 temp clip 방식으로 fallback합니다.
5. 메인 분석에는 표정 보조를 유지하고, 업로드 분할 로그의 청크별 표정 보조 분석은 fast path에서 생략합니다.
6. 응답의 `server_timing`에 `runtime_perf`, `chunk_analysis_sec`, `chunk_analysis_perf`를 추가했습니다.
7. 업로드 `fast/balanced/full` 프로파일별 pose 추출 fps/imgsz를 분리했습니다.
8. 업로드 기본 표정 보조는 2프레임 제한형으로 줄이고, AI-Hub 173 driver-state 보조는 `FACIAL_AUX_UPLOAD_DRIVER=true`일 때만 실행합니다.
9. 메인 RF-Dual 추론에서 생성한 timeseries를 분할 타임라인 청크 분석에 재사용합니다.

검증 샘플:

- `/opt/app/datasets/fall_classification/aihubs_71641/extracted_retry_20260511/영상/Y/SY/00178_H_A_SY_C8/00178_H_A_SY_C8.mp4`
- 약 31MB, 1465프레임, 12개 중첩 window

측정 결과:

| 구분 | 1차 공유 추출만 적용 | 최종 fast path |
|---|---:|---:|
| 청크 분석 wall time | 96.6초 | 12.3초 |
| 공유 YOLO/timeseries 추출 | 미적용 | 6.3초 |
| sampled frames | - | 98 |
| detected frames | - | 71 |
| window 수 | 12 | 12 |
| 첫 청크 `single_pass_extract` | 청크별 추출 | 0.0초 |
| 첫 청크 `facial_state_aux` | 8.0초 | 0.0초 |

2차 측정 결과:

| 구분 | 이전 | 2차 적용 후 |
|---|---:|---:|
| 메인 `fast` RF-Dual | 23.5초 | 12.9초 |
| 메인 `balanced` RF-Dual | 30.0초 | 20.1초 |
| 전체 업로드 `balanced` 서버 시간 | 28.2초 | 22.9초 |
| 청크 분석 | 9.1초 | 4.25초 |
| 청크 timeseries 모드 | `shared_full_video_timeseries` | `shared_main_timeseries` |
| 청크 추가 YOLO 추출 | 4.8~5.4초 | 0.0초 |

현재 기본 설정:

| profile | pose fps | YOLO imgsz | 용도 |
|---|---:|---:|---|
| fast | 4fps | 416 | 빠른 1차 응답 |
| balanced | 6fps | 512 | 기본 운영 |
| full | 8fps | 640 | 정밀 검토 |

검증 명령:

- `python3 -m py_compile src/model/struct/video_analysis.py`
- `wiz project build --project=main`
- `wiz bundle --project=main`

## 1. 현재 병목 가정

이전 업로드 분석 측정 기준으로 전체 분석 시간은 약 41초였고, LLM 호출 시간은 `0.0초`였습니다. 따라서 병목은 LLM이 아니라 영상 처리와 모델 추론 쪽입니다.

주요 병목 후보는 다음과 같습니다.

| 영역 | 병목 가능성 |
|---|---|
| YOLOv8n-pose 추론 | 프레임마다 pose/bbox 추론 비용이 큼 |
| 중첩 청크 처리 | `4초 창 / 2초 stride`로 바꾸면 같은 구간이 여러 청크에 포함됨 |
| 영상 디코딩 | 같은 영상을 청크별로 반복 디코딩하면 낭비가 큼 |
| feature 생성 | RF-Fall, XG-Posture, occlusion auxiliary가 비슷한 pose feature를 반복 사용할 수 있음 |
| facial-state auxiliary | 얼굴 보조 분석은 낙상 판단 직접 모델이 아니므로 항상 실행하면 낭비가 될 수 있음 |

## 2. 최우선 개선 방향

### 2.1 청크별 추론 반복 제거

중첩 분석은 유지해야 하지만, 중첩 구간을 매번 다시 YOLO 추론하면 시간이 크게 늘어납니다.

개선 방향:

1. 업로드 영상 전체에서 필요한 프레임을 한 번만 샘플링합니다.
2. YOLO pose 추론도 한 번만 수행합니다.
3. 추출된 timeseries/keypoint 결과를 `0~4`, `2~6`, `4~8` 같은 청크 window에 재사용합니다.
4. 각 청크는 이미 계산된 frame feature를 slice해서 RF-Fall/XG-Posture 판단만 수행합니다.

기대 효과:

- 중첩 청크로 인한 중복 추론 비용 제거
- 10초 영상 기준 청크 4개를 별도 추론하던 비용을 단일 추론 + window slicing으로 축소
- 예상 단축 폭: 30~50%

### 2.2 YOLO pose batch inference

프레임을 1장씩 모델에 넣으면 호출 오버헤드가 큽니다.

개선 방향:

- sampled frame list를 모아서 batch 단위로 YOLO 추론
- CPU 기준 batch size 4~8, GPU 기준 batch size 8~16부터 테스트
- 프레임별 후처리만 개별 처리

기대 효과:

- 모델 호출 횟수 감소
- CPU/GPU 사용률 개선
- 예상 단축 폭: 15~35%

### 2.3 업로드 fast profile 추가

현재 업로드 분석이 실시간보다 무겁게 `640px` 계열 추론을 쓰면 시간이 길어집니다.

개선 방향:

| 모드 | 용도 | 설정 예시 |
|---|---|---|
| fast | UI 즉시 응답 | YOLO imgsz 320~416, 2~3fps, facial aux 최소화 |
| balanced | 기본 운영 | YOLO imgsz 416~640, 3~4fps |
| full | 정밀 검토 | 640px, 높은 frame budget |

기대 효과:

- 일반 업로드 분석은 fast 또는 balanced로 먼저 결과 표시
- 정밀 분석은 필요할 때만 별도 실행
- 예상 단축 폭: 20~50%

## 3. 보조 분석 최적화

### 3.1 facial-state auxiliary 조건부 실행

표정/상태 모델은 낙상 판단의 직접 모델이 아니라 보조 근거입니다.

개선 방향:

- 얼굴이 명확히 검출된 경우에만 실행
- `fall_score`가 낮고 자세 판단이 명확하면 생략
- `fall_suspected`, `uncertain`, 하체 가림 hard-case에서만 실행
- 업로드 chunk replay에서는 대표 프레임 1장만 먼저 분석

기대 효과:

- 얼굴 미검출 영상에서 불필요한 처리 제거
- 예상 단축 폭: 5~15%

### 3.2 LLM 설명은 계속 비동기/로컬 우선

현재 측정상 LLM 호출 시간은 병목이 아니었습니다. 따라서 OpenAI 동기 호출을 기본으로 켜면 안 됩니다.

운영 원칙:

- 기본 설명은 `local_fast`
- LLM 동기 해석은 사용자가 명시적으로 요청한 경우만 실행
- 분석 결과 화면은 LLM 없이 먼저 표시

## 4. 캐시 전략

### 4.1 파일 hash 기반 재분석 캐시

같은 영상이 다시 업로드되면 처음부터 재추론하지 않도록 합니다.

캐시 키:

- 파일 hash
- 파일 크기
- 모델 버전
- chunk policy version
- analysis profile

캐시 대상:

- sampled frames metadata
- YOLO pose timeseries
- RF/XG feature rows
- chunk window 결과

기대 효과:

- 같은 영상 반복 테스트 시 거의 즉시 응답
- QA/디버깅 시간 크게 감소

## 5. 목표 성능 시나리오

현재 40초대 분석을 기준으로 하면 목표는 20초 이하입니다.

| 단계 | 변경 | 기대 시간 |
|---|---|---:|
| 현재 | 청크/추론 중복 가능성 존재 | 약 40초 |
| 1단계 | 전체 영상 1회 추론 + 청크 window slicing | 22~28초 |
| 2단계 | YOLO batch inference + imgsz 416 fast profile | 15~22초 |
| 3단계 | facial aux 조건부 실행 + 캐시 | 10~18초 |

## 6. 권장 적용 순서

1. 분석 결과에 `decode_sec`, `yolo_sec`, `feature_sec`, `chunk_sec`, `facial_sec`, `llm_sec`를 분리 기록합니다.
2. 업로드 분석에서 YOLO/timeseries를 한 번만 만들고 청크는 slicing으로 처리합니다.
3. YOLO inference를 frame batch 방식으로 바꿉니다.
4. fast/balanced/full 분석 profile을 UI에 노출합니다.
5. facial-state auxiliary는 hard-case 중심으로 조건부 실행합니다.
6. 파일 hash 기반 캐시를 추가합니다.

## 7. 주의점

- 낙상 경계 누락을 막기 위한 `4초 창 / 2초 stride` 중첩은 유지해야 합니다.
- 시간을 줄이기 위해 중첩을 없애면 안 됩니다.
- frame 수와 해상도를 낮출 때는 fall recall이 떨어지지 않는지 반드시 검증해야 합니다.
- fast profile은 빠른 1차 응답용이고, 최종 검토에는 balanced/full profile을 남겨두는 것이 안전합니다.
