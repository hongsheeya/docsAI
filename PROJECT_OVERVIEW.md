# FallAI — AI 기반 시니어 행동 패턴 분석 지능형 헬스케어 시스템

> **작성일**: 2026-04-14  
> **서비스 URL**: https://health.seasonai.net  
> **프레임워크**: WIZ (Python Flask + Angular 18, Pug)

---

## 1. 프로젝트 개요

### 1.1 과제명

- **국문**: AI 기반 시니어 행동 패턴 분석을 활용한 지능형 헬스케어 시스템 개발
- **영문**: Development of an Intelligent Healthcare System using AI-Based Senior Behavior Pattern Analysis

### 1.2 연구과제의 필요성

대한민국은 초고령사회로 빠르게 진입하고 있으며, 이에 따라 **노인 낙상, 신체 기능 저하, 인지 기능 저하, 활동성 감소**와 같은 복합 위험이 의료·돌봄 현장의 핵심 문제로 부상하고 있다. 특히 독거노인 증가와 돌봄 인력 부족으로 인해, 기존의 대면 중심 돌봄 체계만으로는 상시적 위험 감지가 어렵다.

기존 낙상 감지 시스템은 주로 **사후적 이벤트 검출**에 초점이 맞춰져 있으나, 실제 위험은 낙상 직전의 **보행 변화, 활동 저하, 자세 전이 지연, 정지 패턴 증가**와 같은 행동 패턴 변화로 선행되는 경우가 많다. 따라서 단순 낙상 여부 판별을 넘어, **행동 변화 패턴 자체를 정량적으로 분석하고 위험 상태를 사전 인지**할 수 있는 지능형 기술이 필요하다.

또한 기존 방식들은 다음과 같은 한계를 가진다.

- **웨어러블 센서 기반**: 정밀 측정은 가능하지만 착용 불편, 충전, 분실, 순응도 저하 문제가 큼
- **카메라 기반 원본 영상 분석**: 설치는 쉽지만 프라이버시 침해 우려가 큼
- **LiDAR/IR 등 전자기파 기반**: 조명 영향은 적지만 비용과 환경 제약이 큼

본 프로젝트는 이러한 한계를 극복하기 위해, **원본 영상 전체를 직접 활용하기보다 사람 영역 검출 → 비식별화/가림 처리 → Skeleton 기반 자세 표현 → 행동 패턴 분석**의 단계적 프레임워크를 채택한다. 이를 통해 **저비용·설치 용이성·프라이버시 보호·실시간성**을 동시에 확보하는 것을 목표로 한다.

### 1.3 최종 목표

본 프로젝트의 최종 목표는 **AI 기반 시니어 행동 패턴 분석 기술을 활용하여, 고령자의 안전 관리와 삶의 질 향상을 지원하는 실생활 적용형 지능형 헬스케어 시스템을 구현하는 것**이다.

구체적으로는 다음을 목표로 한다.

1. 낙상 검출을 넘어 **행동 변화 기반 위험 상태 사전 인지**
2. 자세 추정 기반 **6-class 행동 분류 및 시계열 패턴 분석**
3. 실시간 웹 서비스와 엣지 환경 모두를 고려한 **경량형 분석 구조 구축**
4. 실제 생활환경에서의 적용 가능성을 검증할 수 있는 **운영형 시스템 완성**

### 1.4 실제 수행 기반 연구 방향

본 프로젝트는 처음부터 단일 모델을 고정해 개발한 것이 아니라, **데이터 확보 → 경량 베이스라인 구축 → 특징 확장 → 자세 분류 결합 → 실시간 운영 검증** 순서로 점진적으로 고도화해 왔다. 실제 수행 흐름을 기준으로 정리하면 다음과 같다.

| 단계 | 실제 진행 방향 | 수행 내용 |
|------|---------------|----------|
| 1단계 | 데이터·운영 기반 확보 | 업로드 분석 화면 구축, 낙상/비낙상 데이터 정리, 검증셋 구성, 피드백 저장 구조 마련 |
| 2단계 | 빠른 베이스라인 확보 | bbox 기반 RF 낙상 감지 모델 구축, 추론 속도 최적화, Motion Guard 등 오탐 억제 로직 정비 |
| 3단계 | 표현력 확장 | YOLOv8-Pose, MediaPipe 기반 keypoint 추출, Skeleton 시각화, 13-feature에서 37/43-feature 시계열 특징으로 확장 |
| 4단계 | 다중 행동 이해 | XG-Posture 6-class 모델 구축, walk/run/stand/sit/lie/fall 분류 및 자세 확률 표시 |
| 5단계 | 이중 판단 구조 | RF-Dual 파이프라인 구현, 낙상 판단과 자세 판단을 결합한 decision arbitration 적용 |
| 6단계 | 운영형 검증 | 실시간 청크 분석, rolling cache, 관리자 모니터링, intake 평가, HITL 재학습 루프 연결 |

즉 현재 연구 방향의 핵심은 **"낙상 단일 판정 모델"에서 끝나는 것이 아니라, RF-Dual과 XG-Posture를 결합해 행동 패턴 변화와 자세 맥락을 함께 보는 운영형 파이프라인으로 발전**하는 것이다.

### 1.5 앞으로의 발전 방향

앞으로의 중심 전략은 말씀하신 대로 **데이터를 계속 추가 수집하고, 이를 기반으로 모델을 반복 학습·검증하면서 일반화 성능을 높이는 방향**이 맞다. 다만 단순히 데이터 양만 늘리기보다, 아래와 같은 방향으로 함께 고도화하는 것이 효과적이다.

#### (1) 데이터 확장 전략

- **실제 시니어 데이터 확대**: 복지관·재활센터·실내 생활공간에서 걷기, 앉기, 눕기, 일어나기, 천천히 미끄러짐, 보행 불안정 등의 장면을 추가 수집
- **낙상 직전(pre-fall) 구간 라벨링**: 단순 Y/N 대신 `정상 / 변동 / 위험 / 낙상` 형태의 단계형 라벨 체계 강화
- **어려운 음성 샘플(hard negative) 수집**: 침대 기상, 천천히 눕기, 물건 줍기, 카메라 가까이 접근, 가려짐, 부분 검출 실패 장면 확보
- **환경 다양성 확대**: 조명 변화, 야간, 역광, 가림, 카메라 각도, 거리, 복수 인물 환경 추가
- **합성 데이터의 전략적 사용**: 실제로 수집이 어려운 낙상/위험 장면은 생성형 데이터로 보완하되, 최종 평가는 실제 데이터로 수행

#### (2) 모델 발전 전략

- **RF는 경량·실시간 베이스라인으로 유지**하고, 빠른 응답과 엣지 장치 적용용으로 계속 개선
- **RF-Dual을 주력 운영 모델로 유지**하면서 낙상 + 자세 + 맥락 기반 최종 의사결정 품질 향상
- **XG-Posture 설명 레이어**를 함께 고도화하여 속도와 설명 가능성을 유지하는 경량 듀얼 구조를 발전
- 향후에는 **pre-fall risk score** 를 별도 예측하는 3단계 구조도 검토 가능
  - 1차: 사람/자세 추출
  - 2차: 현재 행동 분류
  - 3차: 위험도 예측(향후 낙상 가능성)

#### (3) 데이터 수집 외에 추가로 해야 할 것

데이터 추가 수집만으로는 한계가 있으므로, 다음 작업을 병행하는 것이 좋다.

1. **라벨 품질 관리 체계 강화**  
    동일 영상에 대해 라벨 기준을 문서화하고, 애매한 케이스를 별도 그룹으로 관리해야 모델이 흔들리지 않는다.

2. **평가셋 고정 및 버전 관리**  
    학습 데이터가 늘어도 비교 기준이 바뀌지 않도록 intake/validation/test 셋을 고정하고 모델 버전별 지표를 누적 관리해야 한다.

3. **실패 사례 중심 재학습 루프 구축**  
    오탐/미탐 사례를 자동으로 모아 다음 학습 배치에 반영하는 active learning 방식이 필요하다.

4. **실시간 운영 지표 수집**  
    정확도뿐 아니라 응답시간, 청크 누락률, 검출률, suspected 비율, 사용자 피드백 비율을 함께 관리해야 한다.

5. **행동 전이 모델링 강화**  
    현재는 fall / posture 중심이지만, 앞으로는 `걷기 → 비틀거림 → 앉기 실패 → 낙상` 같은 전이 패턴을 학습하는 것이 중요하다.

6. **설명 가능성 강화**  
    운영 환경에서는 단순 점수보다 "왜 위험으로 판단했는지"가 중요하므로, 주요 feature 변화량·자세 전이·suppressor 작동 여부를 리포트로 남기는 방향이 필요하다.

7. **엣지 배포 최적화**  
    실제 미니 PC/저전력 장비 운영을 목표로 한다면 모델 경량화, 프레임 샘플링, ONNX/TensorRT 검토도 필요하다.

### 1.6 권장 차기 로드맵

현 시점에서 가장 현실적인 다음 로드맵은 아래와 같다.

| 우선순위 | 제안 방향 | 기대 효과 |
|---------|----------|----------|
| 높음 | 실제 시니어 데이터 추가 수집 + hard negative 보강 | 일반화 성능 향상, 오탐 감소 |
| 높음 | XG-Posture 재학습 및 6-class 데이터 균형 보정 | 자세 분류 안정화 |
| 높음 | RF-Dual intake 평가 수행 | 듀얼 파이프라인 운영 적합성 검증 |
| 중간 | pre-fall / unstable / recovery 라벨 추가 | 사전 위험 예측 연구 확장 |
| 중간 | 오탐·미탐 자동 수집 파이프라인 구축 | active learning 기반 지속 개선 |
| 중간 | 실시간 운영 로그 기반 품질 대시보드 고도화 | 현장 운영 안정성 향상 |
| 낮음 | 엣지 장치용 경량 모델 변환 및 최적화 | 실증·현장 배포 준비 |

### 1.7 서비스 개요

현재 구현된 시스템은 고령자·환자를 대상으로 **실시간 영상 분석**을 수행하여 낙상(Fall)을 감지하고, 동시에 자세 및 행동 패턴을 해석하여 보호자·운영자에게 위험 상태를 전달하는 AI 기반 안전 모니터링 웹 서비스이다.

### 핵심 기능
| 기능 | 설명 |
|------|------|
| 영상 업로드 분석 | MP4/WebM 파일을 업로드하여 낙상 여부·위험도 분석 |
| 실시간 웹캠 분석 | 초기 Dense Bootstrap 후 2초 간격 5초 슬라이딩 청크로 분할하여 실시간 추론 |
| 자세 분류 (6-class) | stand / walk / run / sit / lie / fall |
| HITL 피드백 재학습 | 사용자 피드백을 수집하여 온라인 모델 개선 |
| 보호자 알람 | 낙상 감지 시 SMS/푸시 알람 전송 |
| 관리자 모니터링 | 실시간 세션 현황, 분석 이력, 모델 성능 대시보드 |

---

## 2. 시스템 아키텍처

```
[사용자 브라우저]
    │
    ├─ 업로드 모드: MP4 → multipart POST → api.py → VideoAnalysis
    │
    └─ 실시간 모드: 웹캠 → Dense Sliding WebM 청크 → Fetch → api.py → VideoAnalysis
                        (MediaPipe 클라이언트 포즈도 병행)

[백엔드 — Python]
    VideoAnalysis (src/model/struct/video_analysis.py, ~7800줄)
        │
        ├─ YOLO v8n-pose  → Person 검출 + 17-keypoint 스켈레톤
        ├─ RF Pipeline    → bbox 통계 16 features → RandomForest
        ├─ XG-Posture     → timeseries 42 features → XGBoost (6-class)
        └─ RF-Dual        → RF Fall + XG-Posture 이중 파이프라인

[데이터 계층]
    Struct → ORM(Peewee) → MySQL
    세션 캐시 → 파일 영속화 (_appdata/storage/training/*)
```

### 페이지 구조
| URL | 페이지 | 설명 |
|-----|--------|------|
| `/` | `page.dashboard` | 메인 분석 화면 (업로드 + 실시간) |
| `/admin/analysis` | `page.admin.analysis` | 관리자 분석 이력 모니터링 |
| `/members` | `page.members` | 회원 관리 |
| `/mypage` | `page.mypage` | 개인설정·보호자 등록 |
| `/manual` | `page.manual` | 사용 설명서 |
| `/pipeline` | `page.pipeline` | 개발자 파이프라인 레퍼런스 |
| `/posts` | `page.posts` | 공지사항 |
| `/access` | `page.access` | 로그인 |
| `/wiz/ide` | WIZ IDE | 개발자 관리자 (접근제한) |

---

## 3. AI 모델 현황

### 3.1 RandomForest (RF) — 낙상 감지

| 항목 | 값 |
|------|-----|
| 모델 파일 | `storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl` |
| 알고리즘 | RandomForestClassifier |
| n_estimators | 300 |
| max_depth | None (unlimited) |
| 학습 데이터 | Validation 1100영상 중 Train 899 / Val 200 |
| 입력 features | 16개 (bbox 위치·크기·면적·하강 통계 특징) |
| Validation Accuracy | **89.5%** |
| Validation Recall | **96.0%** |
| Validation F1 | **90.14%** |
| 운영 임계값 | 35% |

**대표 Feature 그룹**:
1. `center_y_mean/std` — 수직 위치와 흔들림
2. `height/width/area mean/std` — 자세 붕괴와 체형 변화
3. `delta_y / delta_height / delta_area` — 낙하 및 급격한 스케일 변화

### 3.2 XGBoost Posture (XG-Posture) — 6-class 자세 분류

| 항목 | 값 |
|------|-----|
| 모델 파일 | `storage/training/fall-detection/xg-posture/xg_posture_model.pkl` |
| 알고리즘 | XGBClassifier |
| n_estimators | 200 |
| max_depth | 3 |
| learning_rate | 0.08 |
| 입력 features | 42개 |
| 학습 샘플 | 1648 clips |
| CV Accuracy | **93.7%** |

**클래스**:
`stand / walk / run / sit / lie / fall`

### 3.3 추론 파이프라인 비교

| 모드 | 엔진 | 특징 추출 | YOLO 패스 | 속도(업로드) | 속도(청크) |
|------|------|----------|-----------|-------------|-----------|
| `rf` | RF | bbox 13feat | 1회 | 3~8초 | ~4초 |
| `rf-dual` | RF + XG-Posture | RF 16feat + Posture 42feat | **1회** | 4~12초 | ~6초 |

### 3.4 RF-Dual 판단 로직 (Decision Arbitration)

```
[RF raw score]
    │
    ├─ Motion Guard / short-clip 보정 적용
    │
    ├─ XG-Posture 6-class 자세 설명 결합
    │
    └─ decision_state: safe / posture_only / fall_suspected / fall_confirmed / uncertain
```

---

## 4. 개발 이력 요약

### Phase 1 — 기반 구축 (2026-03-19 ~ 2026-03-26)
- WIZ 프레임워크 기반 웹 서비스 초기 구축
- YOLO v8n 기반 영상 업로드 분석 프로토타입
- RandomForest v1 학습 파이프라인 구축
- bbox 기반 낙상 feature 추출 (194 windows, Y:82/N:112)
- YOLO Classification 학습 시도 → 과적합 확인, RF로 전환
- Pseudo-label YOLO person detector fine-tune (mAP50=0.989)
- XGBoost 낙상 분류기 기본 학습 (F1=0.70, AUC=0.84)
- E2E HITL 피드백 저장·재학습 루프 구축
- Validation 200건 균형 샘플링 설계 + 추가학습 (F1=0.7499 배포)
- GroupKFold 검증으로 데이터 누출 분석

### Phase 2 — RF 고도화 (2026-03-27 ~ 2026-04-02)
- RF 파이프라인 추론 시간 최적화 (9.88s → **4.71s**, seek 기반 프레임 추출)
- RF v3 대규모 재학습 — 1000영상, **Acc 83.9% → 90.5%**, threshold 0.25 → 0.42
- Motion Guard (정지 상태 오탐 방지)
- 실시간 웹캠 WebM 청크 헤더 문제 수정
- 실시간 Short-Clip 적응형 추론 구현 (현재는 Dense Bootstrap + 5초 청크로 운영)
- HITL 재학습 증분 최적화 (하드 타임아웃 제거)
- 판단 근거 표시 UI
- 레거시 YOLO 분류 모델 전체 제거

### Phase 3 — XGBoost + Dual Pipeline 구축 (2026-04-03 ~ 2026-04-07)
- YOLOv8-Pose 도입 — bbox + 17-keypoint 동시 탐지 + 스켈레톤 시각화
- MediaPipe PoseLandmarker 클라이언트 사이드 포즈 추정 병행
- RF-Pose (25 features: bbox 13 + pose 12) 2단계 파이프라인 구현
- XG Feature 확장 10→37→43 features
- XG-Posture 6-class 학습 파이프라인 구축 (stand/walk/run/sit/lie/fall)
- XG Guard 후처리 엔진 (9-suppressor + 4-override + temporal smoothing)
- RF-Dual 추론 파이프라인 (Fall + Posture + arbitration)
- E2E 통합 테스트 스위트 (18 시나리오 전체 PASS)
- 실시간 분석 성능 최적화 (RTT 프로파일링, 적응형 간격, 워밍업)
- 오버레이 6-class 행동분류 시각화 (확률 바·아이콘·하이라이트)
- 실시간 분석 로그 → 오른쪽 2컬럼 레이아웃
- 041 낙상사고 데이터에서 walk/stand/sit 클립 자동 추출
- RF-Pose 단계적 삭제 (deprecated)

### Phase 4 — XG-Posture/운영 안정화 (2026-04-10)
- posture 경계 사례 정밀화
- suspected 리포트 강화
- 관리자 모니터링 UI + 실시간 롤링 캐시 안전장치
- 실시간 세션 캐시 영속화 (파일 기반 rolling cache)

### Phase 5 — RF-Dual + 버그 수정 (2026-04-13)
- **RF-Dual 파이프라인 신규 구현** (RF Fall + XG-Posture 이중 파이프라인)
- **NaN JSON SyntaxError 버그 수정** (`_sanitize_for_json()` 재귀 정제기)
- RF-Dual 운영 전환 리포트

### Phase 6 — Validation 재학습 + 운영 threshold 재조정 (2026-04-14)
- **RF Validation 재학습 완료** — 1100영상 기준 `Acc 89.5 / Prec 84.96 / Rec 96.0 / F1 90.14`
- **RF 운영 threshold 미세조정** — `0.37 → 0.35` (recall 우선)
- **기존 업로드 전수 재평가** — FP/FN 0건
- **XG-Posture 대량 재학습** — 1648 clip, CV accuracy 93.7
- **RF 16-feature 런타임 호환 복구** — 새 모델 포맷 자동 인식

---

## 5. 핵심 파일 구조

```
project/main/
├── src/
│   ├── app/
│   │   ├── page.dashboard/          ← 메인 분석 UI (view.ts ~1521줄)
│   │   ├── page.admin.analysis/     ← 관리자 모니터링
│   │   ├── page.access/             ← 로그인
│   │   ├── page.manual/             ← 사용 설명서
│   │   ├── page.members/            ← 회원 관리
│   │   ├── page.mypage/             ← 개인설정
│   │   ├── page.pipeline/           ← 파이프라인 문서
│   │   ├── page.posts/              ← 공지사항
│   │   ├── page.posts.item/         ← 게시글 상세
│   │   ├── layout.sidebar/          ← 사이드바 레이아웃
│   │   └── component.nav.sidebar/   ← 사이드바 컴포넌트
│   │
│   ├── model/
│   │   └── struct/
│   │       └── video_analysis.py    ← AI 추론 엔진 (핵심, ~7800줄)
│   │
│   ├── controller/
│   │   ├── base.py                  ← 세션 초기화
│   │   ├── user.py                  ← 로그인 필수
│   │   └── admin.py                 ← 관리자 전용
│   │
│   ├── route/
│   │   └── (REST API 라우트들)
│   │
│   └── portal/
│       └── season/                  ← UI 공통 패키지 (Service, Modal 등)
│
├── devlog/                          ← 작업 이력
│   ├── 2026-04-13/
│   ├── 2026-04-10/
│   ├── 2026-04-07/
│   ├── 2026-04-06/
│   ├── 2026-04-03/
│   ├── 2026-04-02/
│   ├── 2026-04-01/
│   ├── 2026-03-30/
│   ├── 2026-03-27/
│   └── 2026-03-26/
│
└── config/
    ├── season.py                    ← 서비스 설정 (DB, 알람, 임계값)
    └── database.py                  ← DB 연결 정보
```

---

## 6. 주요 설정값

| 설정 | 값 | 위치 |
|------|-----|------|
| RF 낙상 판정 임계값 | **35%** | training_summary.json / video_analysis.py |
| 실시간 청크 길이 | 5초 | view.ts |
| 실시간 청크 간격 | 2초 | view.ts |
| RF n_estimators | 300 | 모델 파일 |
| XG-Posture CV 정확도 | 93.7% | training_summary.json |
| Sliding window 정책 | 0~2 / 0~4 / 0~5 → 2초 간격 5초 | video_analysis.py |
| YOLO 모델 | yolov8n-pose.pt | /opt/app/ |
| 서버 포트 | 3000 | config/boot.py |

---

## 7. 모델 파일 위치

```
/opt/app/
├── yolov8n-pose.pt                                  ← YOLO Pose
├── yolov8n.pt                                       ← YOLO Detection
└── _appdata/storage/training/fall-detection/
    ├── rf-pipeline/
    │   ├── rf_hitl_model.pkl                        ← RF 운영 모델 (Validation 재학습)
    │   └── training_summary.json                    ← 운영 threshold/메트릭
    ├── xg-posture/
    │   └── xg_posture_model.pkl                     ← XG-Posture (운영)
    └── intake/
        └── fall/                                    ← Intake 검증 영상 21건
```

---

## 8. 성능 지표 비교 (최신)

| 모델 | Accuracy | Recall | Specificity | AUC | Intake(21건) |
|------|----------|--------|-------------|-----|--------------|
| RF (Validation 2026-04-14) | 89.5% | 96.0% | 83.0% | - | 업로드 스모크 4원본 PASS |
| XG-Posture (6-class) | **93.7%** | 클래스별 상이 | - | - | - |

---

## 9. 알려진 제약 및 이슈

| 항목 | 내용 |
|------|------|
| RF-Dual 전체 Validation 일괄 평가 | 아직 미실행 (스모크 테스트 및 업로드 재평가만 완료) |
| XG-Posture 장면 편향 | 합성/증강 비중이 높아 완전 신규 환경 일반화는 추가 확인 필요 |
| RF 운영 threshold 0.35 | recall 우선 설정이라 FP가 소폭 늘 수 있음 |
| 실시간 모드 rolling cache | _appdata/storage 파티션 용량 주의 |
| NaN JSON | 2026-04-13 수정됨 (`_sanitize_for_json()`) |
| `/` 루트 라우팅 | 2026-04-13 수정됨 (`boot.py` 리다이렉트 제거) |

---

## 10. 향후 우선순위 작업

| 우선순위 | 작업 | 예상 효과 |
|---------|------|----------|
| 🔴 높음 | RF-Dual Validation 전체 배치 평가 | 전체 FP/FN 분포 확보 |
| 🔴 높음 | hard negative 추가 수집 | threshold 0.35 유지하면서 FP 억제 |
| 🟡 중간 | Motion Guard 파라미터 튜닝 | 오탐 추가 감소 |
| 🟡 중간 | 보호자 알람 실전 테스트 | SMS/FCM 안정성 확인 |
| 🟢 낮음 | RF-Dual rolling cache 구현 | 실시간 연속 사용성 개선 |
| 🟢 낮음 | XG-Posture 실사 데이터 보강 | 합성 의존도 완화 |

---

## 11. 라우팅 수정 이력 (2026-04-13)

### 문제
`config/boot.py`에 Flask 레벨 핸들러가 `/` → `/wiz/ide` 302 리다이렉트를 선언하여, WIZ 프레임워크가 `page.dashboard`(viewuri: `/`)를 서빙하기 전에 Flask가 먼저 가로채는 문제 발생.

### 증상
- `https://health.seasonai.net/` 접속 → 관리자 IDE로 이동
- `/dashboard` 등 직접 진입은 정상이지만 새로고침 시 `/`로 재처리되어 다시 IDE로 이동

### 수정 내용
```python
# boot.py — 제거된 코드:
@app.flask.get("/")
def root_redirect():
    return redirect("/wiz/ide", code=302)
```
루트 라우팅을 WIZ 자체 라우터에 위임. `page.dashboard`의 `viewuri: "/"`가 정상 처리.

---

*이 문서는 2026-04-14 기준 프로젝트 전체 현황을 정리한 것입니다. 상세 작업 이력은 [devlog.md](devlog.md)를 참조하세요.*
