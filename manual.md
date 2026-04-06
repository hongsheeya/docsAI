# FallAI — 개발자 매뉴얼

> **최종 갱신일**: 2026-04-01  
> **프로젝트**: WIZ Framework 기반 낙상 위험 영상 분석 프로토타입

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
9. [인증/권한 체계](#9-인증권한-체계)
10. [프론트엔드 구조](#10-프론트엔드-구조)
11. [알림 게이트웨이](#11-알림-게이트웨이)
12. [빌드 및 배포](#12-빌드-및-배포)
13. [설정 파일](#13-설정-파일)
14. [트러블슈팅](#14-트러블슈팅)

---

## 1. 시스템 개요

FallAI는 영상을 업로드하거나 웹캠을 연결하여 AI가 낙상 여부를 즉시 분석하는 시스템이다. 고령자·환자의 낙상 사고를 조기에 감지하고, 보호자에게 실시간 알림을 전송하여 빠른 대응을 지원한다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| 영상 업로드 분석 | MP4/MOV/AVI/MKV/WEBM 파일을 서버에 업로드 후 AI 분석 |
| 실시간 웹캠 분석 | MediaRecorder API로 4초 간격 청크 녹화 → 서버 분석 (오버랩 윈도우 지원) |
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
| AI/ML | YOLOv8n (사람 검출), RandomForest (낙상 분류), XGBoost (비교용) |
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
  ├─ 웹캠 실시간 (MediaRecorder → 4초 Blob)  ──────────┤
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
  │                              [YOLOv8n]        [RF Pipeline]    [XGBoost]
  │                              사람 검출        통계 특징 추출     모션 특징
  │                              bbox 추출        16개 feature      10개 feature
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

### 8.1 RF Pipeline v2 (기본 엔진)

```
영상 입력
  → 프레임 추출 (OpenCV)
  → YOLOv8n 사람 검출 (각 프레임별 bounding box)
  → 메인 바운딩 박스 선택 (가장 큰 면적)
  → 16개 통계 특징 추출:
      - bbox 면적 (mean, std, max, min)
      - bbox 종횡비 (mean, std)
      - bbox 중심 Y 변화 (mean, std)
      - 프레임 간 면적 변화율 (mean, max)
      - 프레임 간 중심 이동 거리 (mean, max)
      - 존재 프레임 비율
      - 총 프레임 수
      - 기타 통계량
  → RandomForest 분류 (낙상/비낙상)
  → Risk Score (0~1)
  → 분석 결과 JSON 반환
```

### 8.2 Person Feature Runtime (비교용)

```
영상 입력
  → YOLOv8n 사람 검출 + 추적
  → 10개 모션 특징 추출 (속도, 가속도, 방향 변화 등)
  → XGBoost 분류
  → Risk Score 반환
```

### 8.3 모델 파일 경로

| 모델 | 경로 |
|------|------|
| YOLOv8n | `yolov8n.pt` (워크스페이스 루트) |
| RF 모델 | `_appdata/data/storage/training/*.joblib` (학습 후 생성) |

### 8.4 HITL 재학습 흐름

```
사용자 피드백 (actual_label + 영상)
  → _appdata/data/storage/training/ 에 저장
  → retrain_baseline() 호출
  → 기존 학습 데이터 + 새 피드백 데이터 로드
  → RandomForest 재학습
  → 새 모델 덮어쓰기
  → CV F1, CV AUC 등 메트릭 반환
```

---

## 9. 인증/권한 체계

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

## 10. 프론트엔드 구조

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
MediaRecorder A: [0s----4s]         [4s----8s]         [8s---12s]
MediaRecorder B:      [2s----6s]         [6s---10s]         [10s--14s]
                  └─ 2초 오버랩으로 이벤트 놓침 방지 ─┘
```

- Recorder A/B가 realtimeIntervalSec(4초) 간격으로 번갈아 녹화
- B는 A보다 realtimeOverlapSec(2초) 뒤에 시작하여 오버랩
- 이전 분석이 미완료 시 최신 청크 1건만 대기열에 유지
- 중복 낙상 알림: 4초 내 deduplication

### Portal 컴포넌트 사용

| 태그 | 패키지 | 용도 |
|------|--------|------|
| `wiz-portal-season-modal` | season | 확인/경고 모달 |
| `wiz-portal-season-loading-season` | season | 로딩 스피너 |
| `wiz-portal-post-list` | post | 게시판 목록 (page.posts에서 사용) |
| `wiz-portal-post-detail` | post | 게시글 상세 (page.posts.item에서 사용) |

---

## 11. 알림 게이트웨이

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

## 12. 빌드 및 배포

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

## 13. 설정 파일

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

## 14. 트러블슈팅

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
