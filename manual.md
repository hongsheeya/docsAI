# FallAI — 개발자 매뉴얼

> **최종 갱신일**: 2026-06-01
> **프로젝트**: WIZ Framework 기반 낙상 위험 영상 분석 프로토타입

> 2026-06-01 기준 최신 운영/학습 현황은 [`docs/2026-06-01-current-status-and-training-pipeline.md`](docs/2026-06-01-current-status-and-training-pipeline.md)에 상세 정리되어 있다. 이 매뉴얼의 AI 파이프라인 섹션도 같은 기준으로 갱신했다.

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [기술 스택](#2-기술-스택)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [아키텍처 흐름](#4-아키텍처-흐름)
5. [페이지 라우팅 맵](#5-페이지-라우팅-맵)
6. [백엔드 API 명세](#6-백엔드-api-명세)
7. [데이터 모델](#7-데이터-모델)
8. [AI 분석 파이프라인](#8-ai-분석-파이프라인)
9. [RF/XGBoost/SHAP 학습·해석 재현 가이드](#9-rfxgboostshap-학습해석-재현-가이드)
10. [인증/권한 체계](#10-인증권한-체계)
11. [프론트엔드 구조](#11-프론트엔드-구조)
12. [알림 게이트웨이](#12-알림-게이트웨이)
13. [빌드 및 배포](#13-빌드-및-배포)
14. [설정 파일](#14-설정-파일)
15. [트러블슈팅](#15-트러블슈팅)

---

## 1. 시스템 개요

FallAI는 영상을 업로드하거나 웹캠을 연결하여 AI가 낙상 여부를 즉시 분석하는 시스템이다. 고령자·환자의 낙상 사고를 조기에 감지하고, 보호자에게 실시간 알림을 전송하여 빠른 대응을 지원한다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| 영상 업로드 분석 | MP4/MOV/AVI/MKV/WEBM 파일을 서버에 업로드 후 AI 분석 |
| 실시간 웹캠 분석 | MediaRecorder API로 4초 연속 WebM 청크 전송 → 서버 분석 |
| HITL 피드백/재학습 | 사용자 피드백 수집 → RF 모델 재학습 |
| 보호자 알림 | SMS/Push 게이트웨이 연동, 119 안내 팝업 |
| 멤버 관리 | RBAC 기반 사용자 관리 (admin / editor / viewer) |
| 게시판 | Portal/post 패키지 기반 CRUD 게시판 |

---

## 2. 기술 스택

| 계층 | 기술 |
|------|------|
| Framework | WIZ Framework (Python + Angular) |
| Frontend | Angular 19, TypeScript, Tailwind CSS, Pug 템플릿 |
| Backend | Python (WIZ exec 환경), Peewee ORM |
| AI/ML | YOLOv8n-pose (bbox/keypoint), RandomForest RF-Fall v2, XGBoost XG-Posture, ExtraTrees occlusion auxiliary, MobileNetV3 facial-state auxiliary |
| ML Libraries | scikit-learn, numpy, pandas, scipy (my_libs/ 로컬 설치) |
| DB | SQLite (기본), MySQL 전환 가능 |
| 패키지 | portal/season (인증·ORM·UI), portal/post (게시판) |

---

## 3. 프로젝트 구조

```
project/main/
├── config/                    # 프로젝트 설정
├── src/
│   ├── app/                   # Angular App
│   │   ├── page.dashboard/    # 메인 분석 페이지 (/)
│   │   ├── page.pipeline/     # AI 파이프라인 상세 (/pipeline)
│   │   ├── page.admin.analysis/ # 관리자 설정 (/admin/analysis)
│   │   ├── page.access/       # 로그인 (/access)
│   │   ├── page.members/      # 멤버 관리 (/members)
│   │   ├── page.mypage/       # 마이페이지 (/mypage)
│   │   ├── page.posts/        # 게시판 목록 (/posts)
│   │   ├── page.posts.item/   # 게시글 상세 (/posts/:id/:tab?)
│   │   ├── page.manual/       # 사용 설명서 (/manual)
│   │   ├── component.nav.sidebar/ # 사이드바 네비게이션
│   │   ├── layout.empty/      # 빈 레이아웃 (로그인용)
│   │   └── layout.sidebar/    # 사이드바 레이아웃 (기본)
│   ├── controller/            # 백엔드 Controller 체인
│   │   ├── base.py            # 세션 초기화 (공통)
│   │   ├── user.py            # 로그인 필수
│   │   └── admin.py           # 관리자 전용
│   ├── model/
│   │   ├── db/
│   │   │   └── user.py        # User 테이블 (Peewee)
│   │   ├── libs/
│   │   │   ├── video_baseline.py     # RF 학습/추론 로직
│   │   │   └── action_behavior_model.py # 행동 분류 모델
│   │   ├── struct/
│   │   │   ├── user.py        # User Sub-Struct (인증·CRUD)
│   │   │   └── video_analysis.py # 영상 분석 Sub-Struct (핵심 비즈니스 로직, ~148KB)
│   │   └── struct.py          # Composite Struct (싱글톤 진입점)
│   ├── portal/
│   │   ├── season/            # 인증·ORM·UI 패키지
│   │   └── post/              # 게시판 패키지
│   ├── route/
│   │   └── manifest/          # PWA manifest (/manifest.json)
│   └── angular/               # Angular 빌드 설정
├── _appdata/
│   └── data/
│       ├── data/              # 분석 결과 JSON 아카이브
│       ├── uploads/           # 업로드된 영상 파일
│       └── storage/
│           ├── alerts/        # 알림 이력 JSON
│           └── training/      # 학습 데이터 (영상 + 라벨)
└── manual.md                  # 이 문서
```

---

## 4. 아키텍처 흐름

```
[브라우저]
  ├─ 영상 업로드 (FormData)  ──────────────────────────┐
  │  └─ wiz.call('analyze_upload') via page.dashboard/api.py
  │                                                     │
  ├─ 웹캠 실시간 (MediaRecorder → 4초 연속 WebM 청크) ─┤
  │  └─ fetch('/wiz/api/page.dashboard/analyze_upload') │
  │                                                     ▼
  │                                        [Controller: base.py]
  │                                          세션 초기화
  │                                                     │
  │                                                     ▼
  │                                        [api.py: analyze_upload()]
  │                                          metadata 파싱, 파일 수신
  │                                                     │
  │                                                     ▼
  │                                        [struct.video_analysis]
  │                                          .analyze_upload(file, metadata)
  │                                                     │
  │                                    ┌────────────────┼────────────────┐
  │                                    ▼                ▼                ▼
  │                              [YOLOv8n-pose]   [RF-Fall v2]    [XG-Posture]
  │                              bbox/keypoint    65개 feature     105개 feature
  │                              시계열 추출      fall/non-fall     5-class 행동 설명
  │                                    │                │                │
  │                                    └────────────────┼────────────────┘
  │                                                     ▼
  │                                           [Risk Score + Label]
  │                                           낙상 여부 + 위험 점수
  │                                                     │
  │                                                     ▼
  │                                           [Alert Workflow]
  │                                           (fall_detected → 보호자 알림)
  │                                                     │
  └──────────────── JSON 응답 ◄─────────────────────────┘
```

---

## 5. 페이지 라우팅 맵

| URL | App ID | Controller | Layout | 설명 |
|-----|--------|------------|--------|------|
| `/` | page.dashboard | base | layout.sidebar | 메인 분석 페이지 |
| `/pipeline` | page.pipeline | base | layout.sidebar | AI 파이프라인 상세 |
| `/admin/analysis` | page.admin.analysis | admin | layout.sidebar | 관리자 설정 |
| `/access` | page.access | base | layout.empty | 로그인 |
| `/members` | page.members | user | layout.sidebar | 멤버 관리 |
| `/mypage` | page.mypage | user | layout.sidebar | 마이페이지 |
| `/posts` | page.posts | user | layout.sidebar | 게시판 목록 |
| `/posts/:id/:tab?` | page.posts.item | user | layout.sidebar | 게시글 상세 |
| `/manual` | page.manual | base | layout.sidebar | 사용 설명서 |
| `/manifest.json` | manifest (route) | - | - | PWA manifest |

---

## 6. 백엔드 API 명세

### 6.1 page.dashboard/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `prototype_info` | POST | 시스템 정보 조회 (엔진, 데이터셋, 모델 상태) | `action` (선택: `save_alert_settings`) |
| `analyze_upload` | POST | 영상 분석 실행 | `video` (File), `metadata` (JSON string) |
| `submit_training_sample` | POST | 학습 데이터 업로드 | `video` (File), `label`, `note`, `metadata` |
| `retrain_baseline` | POST | RF 모델 재학습 | - |
| `submit_analysis_feedback` | POST | 분석 결과 피드백 | `saved_name`, `predicted_label`, `feedback_status`, `actual_label`, `note`, `retrain` |
| `dispatch_risk_alerts` | POST | 위험 알림 전송 | `saved_name`, `guardian_name`, `guardian_phone`, `risk_level`, `risk_score`, `fall_detected`, ... |
| `reference_preview_info` | POST | 유사 기준 영상 정보 | `scene_id` |
| `reference_preview` | POST/GET | 유사 기준 영상 다운로드 | `scene_id` |

### 6.2 page.admin.analysis/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `prototype_info` | POST | 시스템 정보 + 알림 설정 저장 | `action`, SMS/Push 설정 파라미터 |
| `submit_training_sample` | POST | 학습 데이터 업로드 | `video`, `label`, `note`, `metadata` |
| `retrain_baseline` | POST | RF 모델 재학습 | - |
| `alert_history` | POST | 알림 발송 이력 조회 | `page`, `page_size` |
| `save_guardians` | POST | 보호자 목록 저장 | `guardians` (JSON array) |

### 6.3 page.access/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `login` | POST | 로그인 (세션 생성) | `email`, `password` |

### 6.4 page.members/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `list` | POST | 멤버 목록 조회 | `text`, `role` |
| `invite` | POST | 멤버 초대 (기본 비밀번호: welcome1) | `email`, `role` |
| `remove` | POST | 멤버 제거 | `id` |

### 6.5 page.mypage/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `get` | POST | 내 프로필 조회 | - (세션 기반) |
| `update_profile` | POST | 프로필 수정 | `name`, `mobile` |
| `change_password` | POST | 비밀번호 변경 | `current_password`, `new_password` |

### 6.6 page.pipeline/api.py

| 함수명 | HTTP | 설명 | 주요 파라미터 |
|--------|------|------|---------------|
| `prototype_info` | POST | 파이프라인 정보 조회 | - |

### API 호출 URL 패턴

```
POST /wiz/api/{APP_ID}/{FUNCTION_NAME}
Content-Type: application/x-www-form-urlencoded 또는 multipart/form-data
```

예시:
```bash
# 프로토타입 정보 조회
curl -b "session=$SESSION" -d "" http://localhost:3000/wiz/api/page.dashboard/prototype_info

# 영상 분석
curl -b "session=$SESSION" -F "video=@test.mp4" -F "metadata={}" http://localhost:3000/wiz/api/page.dashboard/analyze_upload
```

---

## 7. 데이터 모델

### 7.1 User 테이블 (`src/model/db/user.py`)

Peewee ORM 기반 사용자 테이블.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | CharField(PK) | UUID (자동 생성) |
| email | CharField(unique) | 이메일 (로그인 ID) |
| password | CharField | 해시된 비밀번호 |
| name | CharField | 사용자 이름 |
| role | CharField | 역할 (admin/editor/viewer) |
| mobile | CharField | 연락처 |
| created | DateTimeField | 생성일시 |

### 7.2 Struct (비즈니스 로직 계층)

```
struct.py (Composite Struct, Singleton)
├── struct.user → struct/user.py (User Sub-Struct)
│   ├── authenticate(email, password) → dict | None
│   ├── list(text, role) → list
│   ├── get(id) → dict
│   ├── create(data) → dict
│   ├── update_profile(id, name, mobile)
│   └── change_password(id, current, new) → bool
│
├── struct.video_analysis → struct/video_analysis.py (VideoAnalysis Sub-Struct)
│   ├── prototype_info() → dict (시스템 정보 조회)
│   ├── analyze_upload(file, metadata) → dict (영상 분석)
│   ├── submit_training_sample(file, label, note, metadata) → dict
│   ├── retrain_baseline() → dict
│   ├── submit_analysis_feedback(saved_name, ..., retrain) → dict
│   ├── dispatch_risk_alerts(...) → dict
│   ├── save_alert_settings(settings) → dict
│   ├── save_guardians(guardians) → dict
│   ├── alert_history(page, page_size) → dict
│   └── reference_preview_info(scene_id) → dict
│
└── __getattr__ → portal/{name}/struct (패키지 Struct 동적 로드)
    └── struct.post → portal/post/struct (게시판)
```

### 7.3 파일 기반 스토리지

분석 결과, 알림 이력, 학습 데이터는 `_appdata/` 하위에 JSON/파일로 저장된다.

| 경로 | 용도 |
|------|------|
| `_appdata/data/data/` | 분석 결과 JSON |
| `_appdata/data/uploads/` | 업로드된 영상 파일 |
| `_appdata/data/storage/alerts/` | 알림 전송 이력 JSON |
| `_appdata/data/storage/training/` | 학습 데이터 (영상 + 라벨 JSON) |

---

## 8. AI 분석 파이프라인

### 8.1 현재 운영 흐름

```
영상 업로드 / 실시간 WebM 청크
  → 4초 청크 기준 프레임 샘플링
  → YOLOv8n-pose bbox + COCO-17 keypoint 추출
  → bbox / skeleton / temporal feature 생성
  → RF-Fall v2가 fall / non-fall을 먼저 판단
  → XG-Posture가 stand / walk / run / sit / lie를 병렬 설명
  → 하체 가림 시 occlusion auxiliary가 stand/sit/lie 보조 판단
  → 실제 얼굴 검출 시에만 facial-state auxiliary 실행
  → 모델 evidence + LLM 설명 보조 + UI/로그/알림 반환
```

중요한 운영 원칙은 “낙상 판단 우선, 행동분류는 설명 보조”이다. 낙상/비낙상은 RF-Fall v2가 먼저 판단하고, 비낙상 또는 경계 상황에서 XG-Posture 행동 결과를 함께 보여준다. 표정 모델은 판단 근거를 보조할 뿐 낙상 판정을 대체하지 않는다.

### 8.2 Random Forest 낙상 모델 학습

| 항목 | 현재 값 |
|------|---------|
| 모델 | RF-Fall v2 occlusion-aware |
| 파일 | `/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl` |
| 학습 스크립트 | `scripts/retrain_rf_fall_v2.py` |
| 학습 샘플 | 1,592 |
| 클래스 분포 | non-fall 795 / fall 797 |
| feature 수 | 65 |
| target fps | 4fps |
| max frames | 32 |

학습 과정:

1. AI-Hub 71641 및 intake/피드백 영상을 fall/non-fall로 정리한다.
2. 같은 영상/사람 단위가 train과 validation에 섞이지 않도록 group split을 사용한다.
3. YOLOv8n-pose로 사람 bbox와 skeleton keypoint를 추출한다.
4. bbox 중심, 높이, 면적, 종횡비, 하강 속도, 바닥 근접도, skeleton lying/standing score, visibility 계열 feature를 만든다.
5. `RandomForestClassifier` 계열 모델을 학습한다.
6. out-of-fold 확률로 threshold sweep을 수행한다.
7. `suspect`, `best_f1`, `confirm` threshold를 분리해 저장한다.

현재 threshold sweep 결과:

| threshold | 값 | Precision | Recall | F1 |
|-----------|---:|----------:|-------:|---:|
| suspect | 0.3487 | 0.8718 | 0.9812 | 0.9233 |
| best_f1 | 0.4050 | 0.8980 | 0.9724 | 0.9337 |
| confirm | 0.4550 | 0.9080 | 0.9536 | 0.9302 |

RF-Fall v2가 중요한 이유는 낙상 탐지에서 recall을 지키면서도 단순 흔들림/천천히 앉기/하체 가림으로 생기는 오경보를 줄이는 1차 안전장치이기 때문이다.

### 8.3 XGBoost 행동분류 모델 학습

| 항목 | 현재 값 |
|------|---------|
| 모델 | XG-Posture 5-class |
| 파일 | `/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl` |
| 학습 스크립트 | `scripts/retrain_xg_posture_grouped.py` |
| active algorithm | `xgb_regularized` |
| 학습 샘플 | 2,466 |
| feature 수 | 105 |
| 검증 | StratifiedGroupKFold 5-fold |
| Group CV accuracy | 0.6602 |
| Group CV macro F1 | 0.6513 |

클래스는 `stand`, `walk`, `run`, `sit`, `lie` 다섯 가지다. feature는 기존 bbox/pose 기반 64~82개 feature에서 하체 가림과 상체 기반 구분 feature를 추가해 105개까지 확장했다.

주요 feature 축:

| 축 | 예시 | 목적 |
|----|------|------|
| BBox/scale | height_ratio, floor_proximity, aspect_change | 서기/앉기/눕기 형태 구분 |
| 이동량 | center_dx_abs_mean, center_x_span | 제자리 흔들림과 걷기 구분 |
| Pose geometry | pose_tilt_mean, shoulder_hip_ratio | 상체/전신 자세 구분 |
| 하체 feature | knee_bend, ankle_width, lower_body_visibility | 걷기/앉기/뛰기 구분 |
| 상체 feature | upper_body_aspect, torso_verticality | 하체 가림 시 보조 판단 |
| Temporal feature | speed_std, oscillation_count, step_period_est | 걷기/뛰기 주기성 |
| Guard feature | lie_stand_separation_score, support_stability_score | stand/lie, sit/lie 오분류 억제 |

후보 모델은 `xgb_regularized`, `xgb_shallow`, `xgb_conservative`, `extra_trees`를 비교했다. 현재 active는 macro F1이 가장 높았던 `xgb_regularized`다. 다만 0.6513은 운영 행동분류 모델로 충분히 높지 않으므로, 실제 설치 각도와 하체 가림 hard-case 데이터로 재학습이 필요하다.

### 8.4 하체 가림 보조 모델

하체 가림 상황에서는 XG-Posture가 `unknown` 또는 `lie`로 쏠릴 수 있다. 그래서 하체를 일부 가림 처리한 데이터와 기존 데이터를 함께 사용해 보조 모델을 만들었다.

| 항목 | 현재 값 |
|------|---------|
| 모델 | XG-Posture occlusion auxiliary |
| 파일 | `/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/xg_posture_occlusion_aux_model.pkl` |
| algorithm | ExtraTrees balanced |
| feature 수 | 105 |
| Group CV accuracy | 0.8663 |
| Group CV macro F1 | 0.8657 |

이 모델은 주 모델을 대체하지 않고, lower-body visibility가 낮거나 주 모델 confidence가 낮을 때 보조 근거로 사용한다.

### 8.5 표정/상태 보조 모델

| 모델 | 데이터 | 클래스 | 성능 | 역할 |
|------|--------|--------|------|------|
| AI-Hub 82 MobileNetV3 | 한국인 감정 | 7-class | macro F1 0.6198 | 불안/상처/슬픔/중립 등 표정 보조 |
| AI-Hub 173 MobileNetV3 | 운전자 상태 | 5-class | macro F1 0.9054 | 졸림/하품/주의저하 보조 |

표정 모델은 낙상 모델이 아니다. 실제 얼굴이 검출되고 confidence, margin, entropy, frame consistency가 충분할 때만 보조 점수로 반영한다. 얼굴이 보이지 않으면 `얼굴/표정 미검출`로 표시하고 감정 점수를 사용하지 않는다.

### 8.6 SHAP 해석 과정

SHAP는 모델을 새로 학습하는 방식이 아니라, 이미 학습된 Random Forest/XGBoost 모델의 예측을 feature 단위로 설명하는 방법이다.

권장 적용 방식:

1. RF-Fall v2와 XG-Posture 모델을 로드한다.
2. 학습 feature row에서 background sample을 뽑는다.
3. TreeExplainer 계열로 SHAP 값을 계산한다.
4. global mean absolute SHAP로 전체 중요 feature를 확인한다.
5. false positive/false negative 청크에 local SHAP를 계산한다.
6. UI/LLM에는 “이번 청크에서 점수를 올린 feature Top-N”을 근거로 전달한다.

운영 주의점:

- SHAP는 성능을 직접 올리지 않는다.
- 실시간 모든 청크에 SHAP를 적용하면 RTT가 증가할 수 있다.
- 우선은 batch 오류 분석/보고서에 적용하고, 실시간 UI에는 가벼운 feature contribution만 노출하는 것이 안전하다.

### 8.7 모델 파일 경로

| 모델 | 경로 |
|------|------|
| YOLOv8n-pose | `/opt/app/project/main/yolov8n-pose.pt` |
| RF-Fall v2 | `/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl` |
| XG-Posture | `/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl` |
| 하체가림 보조 | `/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/xg_posture_occlusion_aux_model.pkl` |
| 표정 82 | `/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt` |
| 상태 173 | `/opt/app/storage/training/fall-detection/facial-state/aihub173_driver_state_mobilenetv3.pt` |

### 8.8 HITL 재학습 흐름

```
사용자 피드백(actual_label + 영상)
  → _appdata/data/storage/training/ 또는 intake manifest에 저장
  → 동일 feature extractor로 feature row 생성
  → 기존 데이터 + 피드백 데이터 병합
  → group split으로 RF/XGBoost 후보 재학습
  → validation metric, confusion matrix, threshold sweep 비교
  → 기존 운영 모델보다 개선된 후보만 승격
```

---

## 9. RF/XGBoost/SHAP 학습·해석 재현 가이드

이 절은 프로젝트를 처음 보는 사람이 현재 학습 방식을 다시 실행하거나 검증할 수 있도록 정리한 재현 가이드다. 실제 데이터는 `/opt/app/datasets` 아래에 두고, 프로젝트 코드는 `/opt/app/project/main`에서만 수정한다. 모델 산출물은 `/opt/app/storage/training/fall-detection`에 저장한다.

### 9.1 공통 준비

작업 기준 경로:

```bash
cd /opt/app/project/main
```

주요 입력/출력 경로:

| 구분 | 경로 |
|------|------|
| 프로젝트 코드 | `/opt/app/project/main` |
| 낙상 데이터 | `/opt/app/datasets/fall_classification/aihubs_71641` |
| 행동 데이터 71461 | `/opt/app/datasets/action_behavior/aihub_71461` |
| 행동 데이터 61 | `/opt/app/datasets/action_behavior/aihub_61_person_action_2020` |
| 모델 저장 루트 | `/opt/app/storage/training/fall-detection` |
| RF-Fall v2 summary | `/opt/app/storage/training/fall-detection/rf-fall-v2/training_summary.json` |
| XG-Posture summary | `/opt/app/storage/training/fall-detection/xg-posture/training_summary.json` |

학습 전 확인할 것:

1. 데이터가 프로젝트 코드 내부에 저장되어 있지 않은지 확인한다.
2. 같은 영상/같은 사람/같은 capture group이 train과 validation에 동시에 들어가지 않도록 group split을 사용한다.
3. accuracy 하나만 보지 말고 macro F1, class별 recall, confusion matrix를 같이 본다.
4. 운영 적용 전에는 summary JSON의 `ready`, `model_path`, `feature_count`, `class_distribution`, `group_cv`를 확인한다.

### 9.2 Random Forest 낙상 모델 재현 절차

목표는 4초 청크 또는 영상 샘플을 `fall`과 `non-fall`로 분류하는 RF-Fall v2 모델을 만드는 것이다. 이 모델이 낙상 판정의 1차 기준이다.

현재 학습 스크립트:

```bash
python3 scripts/retrain_rf_fall_v2.py
```

스크립트가 내부적으로 보는 주요 데이터 루트:

```text
/opt/app/datasets/fall_classification/aihubs_71641/extracted_retry_20260511/영상
/opt/app/datasets/fall_classification/aihubs_71641/extracted/영상
/opt/app/project/main/낙상영상/01.원천데이터/영상
```

RF 학습 흐름:

1. **영상 수집**
   - `*.mp4`, `*.avi`, `*.mov`, `*.mkv` 파일을 탐색한다.
   - 파일명/상위 폴더에서 `Y` 또는 `N` 라벨을 추론한다.
   - 현재 기준 `Y`는 fall, `N`은 non-fall이다.

2. **group id 생성**
   - 같은 시나리오에서 나온 카메라 각도나 연속 영상이 train/validation에 동시에 들어가면 성능이 부풀려진다.
   - 그래서 파일명에서 scenario group을 만들고 `StratifiedGroupKFold` 또는 `GroupShuffleSplit`을 사용한다.

3. **프레임 샘플링**
   - target fps는 4fps 기준이다.
   - 최대 32프레임을 사용한다.
   - 목적은 실시간 4초 WebM 청크와 최대한 비슷한 입력 길이/프레임 밀도로 맞추는 것이다.

4. **YOLOv8n-pose 추론**
   - `/opt/app/project/main/yolov8n-pose.pt`를 사용한다.
   - 사람 bbox와 COCO-17 keypoint를 추출한다.
   - bbox confidence, keypoint confidence, visibility를 같이 저장한다.

5. **65개 feature 생성**
   - bbox 계열: `center_y_mean`, `center_y_std`, `height_mean`, `width_mean`, `area_mean`, `aspect_ratio_mean`.
   - 움직임 계열: `center_y_drop`, `max_down_speed_norm`, `delta_y_mean`, `delta_y_max`, `delta_y_accel_max`.
   - 바닥/자세 계열: `floor_proximity`, `floor_contact_ratio`, `low_height_floor_score`.
   - skeleton 계열: `torso_tilt_mean`, `lying_skeleton_score`, `standing_skeleton_score`, `pose_height_drop`.
   - 신뢰도/가림 계열: `detection_rate`, `sample_coverage`, `visible_keypoint_ratio`, `lower_body_visibility`, `occlusion_ratio`.

6. **모델 학습**
   - `RandomForestClassifier`, `ExtraTreesClassifier`, `VotingClassifier` 후보를 사용한다.
   - class imbalance를 줄이기 위해 fall/non-fall 분포와 class weight를 확인한다.
   - 현재 학습 샘플은 non-fall 795, fall 797로 거의 균형이다.

7. **threshold sweep**
   - 모델 확률을 그대로 0.5에서 자르지 않는다.
   - validation/out-of-fold 확률로 여러 threshold를 돌려 precision/recall/F1을 비교한다.
   - 현재 저장된 운영 후보:

| threshold | 값 | Precision | Recall | F1 | 용도 |
|-----------|---:|----------:|-------:|---:|------|
| suspect | 0.3487 | 0.8718 | 0.9812 | 0.9233 | 민감도 우선 후보 |
| best_f1 | 0.4050 | 0.8980 | 0.9724 | 0.9337 | F1 최고 후보 |
| confirm | 0.4550 | 0.9080 | 0.9536 | 0.9302 | 운영 확인 후보 |

8. **저장 산출물 확인**

```text
/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl
/opt/app/storage/training/fall-detection/rf-fall-v2/training_summary.json
/opt/app/storage/training/fall-detection/rf-fall-v2/feature_rows.csv
```

9. **검증 포인트**
   - `training_summary.json`의 `training_samples`, `feature_count`, `thresholds`, `class_distribution`을 확인한다.
   - recall이 너무 높고 precision이 낮으면 오경보가 많다.
   - precision만 높이면 낙상 miss가 늘 수 있으므로 confirm threshold와 suspect threshold를 분리해 운영한다.

### 9.3 XGBoost 행동분류 모델 재현 절차

목표는 비낙상 또는 경계 상황에서 사람의 상태를 `stand`, `walk`, `run`, `sit`, `lie`로 설명하는 것이다. 이 모델은 낙상 최종 판정을 대체하지 않고, UI 설명과 오탐 억제를 돕는다.

현재 학습 스크립트:

```bash
python3 scripts/retrain_xg_posture_grouped.py
```

입력 데이터:

| 데이터 | 역할 |
|--------|------|
| AI-Hub 71461 | stand/sit/lie 등 이미지·영상 행동 라벨 보강 |
| AI-Hub 61 사람동작 2020 | walk/run/sit/lie sequence 보강 |
| 기존 런타임 feature | 실시간 청크와 같은 feature schema 유지 |

XGBoost 학습 흐름:

1. **feature window 구성**
   - 영상 또는 pose/image 라벨에서 4초 단위 window feature row를 만든다.
   - 현재 active 모델은 2,466 rows, 105 features를 사용한다.

2. **라벨 정규화**
   - 원천 데이터 라벨을 `stand`, `walk`, `run`, `sit`, `lie` 다섯 클래스로 통일한다.
   - 애매한 라벨은 무리하게 넣지 않고 제외하거나 source note를 남긴다.

3. **group split**
   - AI-Hub 61은 같은 파일/동작 sequence 단위로 group을 만든다.
   - AI-Hub 71461은 파일명 capture id 또는 인접 frame 묶음을 group으로 만든다.
   - `StratifiedGroupKFold`로 같은 사람/영상이 train과 validation에 섞이지 않게 한다.

4. **105개 feature 사용**
   - 기본 bbox/motion feature: `center_dy`, `height_ratio`, `aspect_change`, `floor_proximity`.
   - 이동량 feature: `center_dx_abs_mean`, `center_x_span`, `horizontal_motion_energy`.
   - pose geometry: `pose_tilt_mean`, `shoulder_hip_ratio`, `torso_verticality`.
   - 하체 feature: `lower_body_visibility`, `knee_bend`, `ankle_width`, `leg_verticality`.
   - temporal feature: `oscillation_count`, `speed_std`, `step_period_est`, `center_y_periodicity`.
   - guard feature: `lie_stand_separation_score`, `support_stability_score`, `upright_geometry_score`.

5. **후보 모델 비교**
   - `xgb_regularized`: 현재 active. 과적합을 줄인 regularized XGBoost.
   - `xgb_shallow`: 더 얕은 트리로 일반화 확인.
   - `xgb_conservative`: 더 보수적인 파라미터로 오분류 억제 확인.
   - `extra_trees`: 트리 기반 비교 후보.

6. **평가**
   - 현재 active 결과:

| 항목 | 값 |
|------|---:|
| Group CV accuracy | 0.6602 |
| Group CV macro F1 | 0.6513 |
| stand recall | 0.8157 |
| walk recall | 0.5349 |
| run recall | 0.7365 |
| sit recall | 0.5569 |
| lie recall | 0.6923 |

7. **confusion matrix 해석**
   - stand/sit/lie 혼동은 하체 가림, 카메라 각도, 침대/의자 전이에서 주로 생긴다.
   - walk/run 혼동은 이동 주기와 속도 차이가 부족할 때 생긴다.
   - 따라서 다음 데이터 보강은 “실제 설치 각도 hard-case”와 “가림 라벨”이 우선이다.

8. **저장 산출물**

```text
/opt/app/storage/training/fall-detection/xg-posture/xg_posture_model.pkl
/opt/app/storage/training/fall-detection/xg-posture/training_summary.json
/opt/app/project/main/outputs/model_optimization/xg_posture_grouped_training_report.json
```

### 9.4 SHAP 해석 재현 절차

SHAP는 학습 모델이 아니다. 이미 학습된 RF-Fall v2 또는 XG-Posture가 왜 특정 결과를 냈는지 feature별 기여도를 계산하는 해석 도구다.

SHAP를 쓰는 목적:

1. false positive에서 어떤 feature가 낙상 점수를 올렸는지 확인한다.
2. false negative에서 어떤 feature가 낙상 점수를 충분히 못 올렸는지 확인한다.
3. 행동분류 confusion matrix의 stand/sit/lie 혼동 원인을 feature 단위로 본다.
4. LLM에게 “모델이 실제로 본 근거 Top-N”을 넘겨 설명 품질을 높인다.

권장 절차:

1. 모델과 summary를 로드한다.
2. 학습 때 사용한 feature column 순서를 summary에서 가져온다.
3. validation 또는 오분류 샘플 feature row를 준비한다.
4. tree model에 맞는 explainer를 만든다.
5. global SHAP는 전체 validation feature의 평균 절대값으로 중요도를 본다.
6. local SHAP는 특정 청크 하나에 대해 점수를 올린 feature와 낮춘 feature를 분리한다.
7. 결과는 실시간 전체 청크가 아니라 batch report로 먼저 저장한다.

예시 의사 코드:

```python
import joblib
import pandas as pd
import shap

model = joblib.load("/opt/app/storage/training/fall-detection/rf-fall-v2/rf_fall_v2_model.pkl")
rows = pd.read_csv("/opt/app/storage/training/fall-detection/rf-fall-v2/feature_rows.csv")

feature_cols = [c for c in rows.columns if c not in {"label", "group", "path"}]
X = rows[feature_cols].fillna(0)

explainer = shap.TreeExplainer(model)
values = explainer.shap_values(X.sample(min(len(X), 500), random_state=42))
```

운영 주의점:

- SHAP 계산은 무겁다. 실시간 모든 청크에 붙이면 RTT가 증가할 수 있다.
- 먼저 FP/FN batch report에 적용한다.
- 실시간 UI에는 SHAP 전체값 대신 모델 feature importance 또는 사전 계산된 Top feature rule을 가볍게 노출한다.
- LLM 설명에는 “SHAP 또는 contribution Top-N + 모델 확률 + 검출 품질”만 넘긴다.

### 9.5 재학습 후 적용 확인 체크리스트

재학습이 끝나면 다음 순서로 확인한다.

1. summary JSON의 `ready`가 true인지 확인한다.
2. `model_path` 파일이 실제 존재하는지 확인한다.
3. feature_count가 런타임 feature schema와 같은지 확인한다.
4. class_distribution이 비정상적으로 한쪽으로 몰리지 않았는지 확인한다.
5. Group CV 또는 threshold sweep 수치가 이전 active보다 나은지 확인한다.
6. `/pipeline` 화면에서 sample count, feature count, threshold가 최신으로 표시되는지 확인한다.
7. 업로드 모드와 실시간 WebM 청크를 같은 4초 기준으로 비교한다.
8. fall/non-fall 판정이 먼저 나오고, 비낙상/경계에서 행동분류와 표정 evidence가 보조로 붙는지 확인한다.

---

## 10. 인증/권한 체계

### Controller 체인

```
base.py (세션 초기화)
  → session = portal/season/session
  → wiz.response.data.set(session=sessiondata)

user.py extends base.py (로그인 필수)
  → session.has("id") == False → 401

admin.py extends user.py (관리자 전용)
  → session.get("role") != 'admin' → 401
```

### 세션 키

| 키 | 설명 |
|----|------|
| `id` | 사용자 UUID |
| `email` | 이메일 |
| `name` | 이름 |
| `role` | 역할 (admin/editor/viewer) |

### 페이지별 접근 권한

| Controller | 접근 조건 | 해당 페이지 |
|------------|----------|------------|
| base | 누구나 (세션 없어도 가능) | 대시보드, 파이프라인, 로그인, 사용 설명서 |
| user | 로그인 필수 | 멤버 관리, 마이페이지, 게시판 |
| admin | 관리자 권한 필수 | 관리자 설정 |

### 프론트엔드 인증

```typescript
// 페이지 진입 시 인증 체크
await this.service.auth.allow("/access");  // 미인증 시 /access로 리다이렉트

// 관리자 여부 체크
this.service.auth?.check?.role('admin') === true
```

---

## 11. 프론트엔드 구조

### 레이아웃 구조

```
layout.sidebar
├── component.nav.sidebar (왼쪽 사이드바)
│   ├── Main: 영상 분석 메인(/), AI 파이프라인(/pipeline)
│   ├── Admin: 관리자 분석 설정(/admin/analysis) — admin 전용
│   └── Help: 사용 설명서(/manual)
├── router-outlet (메인 콘텐츠)
├── wiz-portal-season-modal (모달)
└── wiz-portal-season-loading-season (로딩 스피너)

layout.empty
└── router-outlet (콘텐츠만)
```

### 대시보드 상단 네비게이션 바

`page.dashboard`의 상단 고정(sticky) 네비게이션 바 항목:

| 항목 | 메서드 | 이동 경로 | 조건 |
|------|--------|----------|------|
| 사용 설명서 (책 아이콘) | `goManualPage()` | `/manual` | 항상 표시 |
| 파이프라인 | `goPipelinePage()` | `/pipeline` | 항상 표시 |
| 관리자 | `goAdminPage()` | `/admin/analysis` | `*ngIf="isAdminUser()"` |

> 2026-04-01 변경: "분석 실행" 앵커 링크를 "사용 설명서" 네비게이션 버튼으로 교체.

### Service 주입 (필수 패턴)

```typescript
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service) { }
    public async ngOnInit() {
        await this.service.init();
        await this.service.render();
    }
}
```

### API 호출 패턴

```typescript
// 기본 API 호출 (wiz.call)
let { code, data } = await wiz.call("함수명", { param: "value" });

// 파일 업로드 (service.file.upload)
const fd = new FormData();
fd.append('video', file);
const response = await this.service.file.upload('/wiz/api/page.dashboard/analyze_upload', fd, progressCallback);

// SSE 스트리밍 (fetch + ReadableStream) — 일반 API는 FormData 사용
const formData = new FormData();
const response = await fetch(url, { method: 'POST', body: formData });
```

### 웹캠 실시간 분석 구조

```
Realtime : [0s----4s] [4s----8s] [8s---12s] [12s---16s]
            └─ 같은 4초 단위 청크를 업로드/실시간 모두에 적용 ─┘
```

- 업로드 분석과 실시간 분석 모두 4초 단위 기준으로 feature를 생성한다.
- 브라우저 큐는 청크 누락을 막기 위해 순차 전송을 기본으로 하고, 서버 응답 지연 시 RTT를 별도 표시한다.
- 서버 AI 추론은 4fps 기준 샘플링을 사용하고, 화면 오버레이 FPS와 분리해 체감 실시간성을 확보한다.
- 중복 낙상 알림: 짧은 시간 내 deduplication 적용

### Portal 컴포넌트 사용

| 태그 | 패키지 | 용도 |
|------|--------|------|
| `wiz-portal-season-modal` | season | 확인/경고 모달 |
| `wiz-portal-season-loading-season` | season | 로딩 스피너 |
| `wiz-portal-post-list` | post | 게시판 목록 (page.posts에서 사용) |
| `wiz-portal-post-detail` | post | 게시글 상세 (page.posts.item에서 사용) |

---

## 12. 알림 게이트웨이

### 설정 구조

```json
{
    "guardian": {
        "name": "보호자 이름",
        "phone": "010-1234-5678"
    },
    "gateway": {
        "sms": {
            "enabled": false,
            "provider_name": "solapi",
            "webhook_url": "",
            "auth_token": "",
            "timeout_sec": 8,
            "sender": "",
            "template_id": ""
        },
        "push": {
            "enabled": false,
            "provider_name": "fcm",
            "webhook_url": "",
            "auth_token": "",
            "timeout_sec": 8,
            "target": "",
            "platform": "fcm",
            "bundle_id": ""
        }
    }
}
```

### 알림 흐름

```
낙상 감지 (risk_level: medium/high)
  → dispatch_risk_alerts() 호출
  → 보호자 알림 생성 (SMS/Push)
      ├─ SMS: webhook_url로 POST 전송
      └─ Push: FCM 등 플랫폼으로 전송
  → 고위험 시: 119 연락 안내 팝업 (popup_required: true)
  → 알림 이력 JSON 저장 (_appdata/data/storage/alerts/)
```

---

## 13. 빌드 및 배포

### 빌드 명령

```bash
# 일반 빌드 (기존 API 함수 내용 수정)
wiz_project_build clean=false

# 클린 빌드 (새 API 함수 추가/삭제/이름 변경, socket.py 변경)
wiz_project_build clean=true
```

### 빌드 시 주의 사항

- 새 `api.py` 함수 추가 시 반드시 **클린 빌드** 필요
- `src/model/` 디렉토리 삭제 시 빌드 실패
- `build/`, `bundle/` 디렉토리는 빌드 산출물이므로 수동 편집 금지
- Pug 템플릿에서 소수점/슬래시 포함 Tailwind 클래스는 `class=""` 속성 방식 사용

### 파일 변경 후 빌드 필요 여부

| 변경 유형 | 빌드 | 비고 |
|-----------|------|------|
| view.pug / view.ts / view.scss 수정 | 일반 빌드 | |
| api.py 기존 함수 내용 수정 | 일반 빌드 | |
| api.py 새 함수 추가/삭제 | **클린 빌드** | |
| model/*.py 수정 | 빌드 불필요 | hot-reload |
| controller/*.py 수정 | 빌드 불필요 | hot-reload |
| config/*.py 수정 | 빌드 불필요 | hot-reload |

---

## 14. 설정 파일

### 프로젝트 config (`project/main/config/`)

| 파일 | 용도 |
|------|------|
| `season.py` | Season 패키지 설정 (인증, 기본 URL 등) |
| `database.py` | DB 접속 정보 (namespace별) |

### Angular 빌드 설정 (`src/angular/`)

| 파일 | 용도 |
|------|------|
| `angular.json` | Angular CLI 설정 |
| `package.json` | npm 의존성 |
| `tailwind.config.js` | Tailwind CSS 설정 |
| `styles/styles.scss` | 전역 스타일 (패키지 @import 포함) |

### Portal 패키지 메타데이터 (`src/portal/{package}/portal.json`)

```json
{
    "package": "season",
    "version": "2.0.0",
    "use_app": true,
    "use_route": true,
    "use_libs": true,
    "use_controller": true,
    "use_model": true
}
```

---

## 15. 트러블슈팅

### 14.1 분석 API 404

**원인**: 새 API 함수 추가 후 일반 빌드만 수행  
**해결**: 클린 빌드 (`clean: true`) 실행

### 14.2 wiz.response.status() try/except 충돌

**원인**: `ResponseException`이 `except Exception`에 잡힘  
**해결**: `wiz.response` 호출을 `try` 블록 밖에 배치

```python
# ✅ 올바른 패턴
try:
    result = struct.video_analysis.analyze_upload(file, metadata)
except Exception as e:
    wiz.response.status(400, message=str(e))
wiz.response.status(200, **result)
```

### 14.3 Pug 소수점 클래스 파싱 실패

**원인**: Pug가 `.`을 클래스 구분자로 인식  
**해결**: `div(class="gap-1.5 p-2.5")` 형태로 작성

### 14.4 웹캠 연결 실패

**원인**: HTTP 환경에서 `navigator.mediaDevices` 사용 불가  
**해결**: HTTPS 또는 localhost 환경 필요

### 14.5 wiz.request.query()가 JSON body 미파싱

**원인**: `wiz.request.query()`는 form-urlencoded와 query string만 파싱  
**해결**: 프론트에서 `FormData` 또는 `URLSearchParams` 사용

### 14.6 ML 라이브러리 import 경로

**원인**: 시스템 전역에 scikit-learn이 없고 `my_libs/`에 로컬 설치됨  
**해결**: `video_analysis.py`에서 `sys.path`에 `my_libs/` 추가 후 import

---

## 부록: 자주 사용하는 MCP 명령

```
# 프로젝트 정보
wiz_project_info
wiz_workspace_status

# 앱 조회
wiz_source_list_apps
wiz_source_app_info appPath="app/page.dashboard"

# 파일 읽기/쓰기
wiz_source_read_file appPath="app/page.dashboard" fileName="api.py"
wiz_source_write_file appPath="app/page.dashboard" fileName="api.py" content="..."

# 패키지
wiz_package_list
wiz_package_list_apps package="season"

# 빌드
wiz_project_build clean=false  # 일반 빌드
wiz_project_build clean=true   # 클린 빌드
```
