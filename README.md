# FallAI Project

WIZ 프레임워크 기반 FallAI 운영 프로젝트입니다.
현재는 **낙상 탐지 / 자세 분류 / 실시간 영상 분석** 중심으로 운영 중이며, 게시판·사용자관리·대시보드 구조 위에 프로토타입 기능이 확장되어 있습니다.

---

## 현재 모델 상태 (2026-06-02)

- 기본 업로드/실시간 운영 축: `rf-dual`
- 청크 정책: 업로드/실시간 모두 4초 창을 2초 stride로 중첩 분석, 실시간은 무삭제 큐로 순차 전송
- RF 운영 모델: `RF-Fall v2 occlusion-aware`
    - 학습 샘플 `1,592`
    - Feature `65`
    - Precision `90.8%`
    - Recall `95.4%`
    - F1 `93.0%`
    - 운영 confirm threshold `0.455`
- XG-Posture: **5-class (`stand/walk/run/sit/lie`)**
    - 학습 windows `8,181`
    - Feature `105`
    - sequence CV accuracy `94.3%`
    - sequence CV macro F1 `94.3%`
- 표정/상태 보조 모델:
    - AI-Hub 82 표정: `60,319` samples, macro F1 `61.98%`
    - AI-Hub 173 상태: `47,144` samples, macro F1 `90.54%`
- LLM 설명: 기본 응답은 `local_fast` 근거 요약이며, OpenAI 동기 호출은 별도 설정(`sync_interpretation` 또는 `LLM_INTERPRETATION_SYNC`)을 켤 때만 수행

상세 운영 문서는 [docs/2026-06-01-current-status-and-training-pipeline.md](docs/2026-06-01-current-status-and-training-pipeline.md), 전체 개요는 [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)를 참고합니다. [docs/xg-dual-architecture.md](docs/xg-dual-architecture.md)는 **레거시 설계 문서**이며, 현재 운영 기준은 RF-Dual입니다.

교수님/검토자에게 코드 구조를 설명할 때는 [docs/professor-code-overview-20260629.md](docs/professor-code-overview-20260629.md)를 먼저 공유하면 됩니다. 다른 서버에서 프로젝트를 복구해야 할 때는 [docs/server-restore-guide-20260629.md](docs/server-restore-guide-20260629.md)를 따릅니다.

---

## 데모 계정

| 이메일 | 비밀번호 | 이름 | 역할 |
|--------|----------|------|------|
| admin@example.com | admin1234 | 관리자 | admin |
| alice@example.com | alice1234 | Alice Kim | user |
| bob@example.com | bob12345 | Bob Park | user |
| carol@example.com | carol123 | Carol Lee | editor |
| dave@example.com | dave1234 | Dave Choi | viewer |

---

## 프로젝트 구조

```
src/
├── app/                          # Angular Page/Layout/Component
│   ├── layout.sidebar/           # 사이드바 레이아웃 (h-screen, 회색 배경, 스크롤)
│   ├── component.nav.sidebar/    # 사이드바 네비게이션 컴포넌트
│   ├── page.access/              # 로그인 페이지
│   ├── page.dashboard/           # 대시보드 (통계 + 최근 게시물)
│   ├── page.posts/               # 게시물 목록 (라우팅 전용 → post 패키지)
│   ├── page.posts.item/          # 게시물 상세 (라우팅 전용 → post 패키지)
│   ├── page.members/             # 멤버 관리
│   └── page.mypage/              # 내 프로필 / 비밀번호 변경
│
├── controller/                   # 백엔드 전처리 (인증 체인)
│   ├── base.py                   # 세션 초기화
│   └── user.py                   # 로그인 검증 (base 상속)
│
├── model/                        # 프로젝트 고유 Model
│   ├── struct.py                 # 루트 Struct (User + 패키지 동적 로드)
│   ├── struct/
│   │   └── user.py               # User Sub-Struct (인증, CRUD)
│   └── db/
│       └── user.py               # User DB Model (peewee)
│
└── portal/                       # 재사용 패키지
    ├── season/                   # 코어 패키지 (ORM, 세션, Service)
    └── post/                     # 게시물 패키지
        ├── portal.json
        ├── app/
        │   ├── list/             # 게시물 목록 UI 컴포넌트
        │   └── detail/           # 게시물 상세 UI 컴포넌트
        └── model/
            ├── struct.py         # Post Composite Struct
            ├── struct/
            │   ├── post.py       # Post Sub-Struct
            │   └── comment.py    # Comment Sub-Struct
            └── db/
                ├── post.py       # Post DB Model
                └── comment.py    # Comment DB Model
```

---

## 아키텍처 패턴

### Struct 패턴

```
api.py → wiz.model("struct") → src/model/struct.py (Root Struct)
                                  ├── @property user → struct/user.py (Sub-Struct)
                                  └── __getattr__ → wiz.model("portal/{name}/struct")
                                                    └── portal/post/struct.py
                                                        ├── @property post → Post Sub-Struct
                                                        └── @property comment → Comment Sub-Struct
```

### 패키지 기반 컴포넌트

Post 관련 UI는 `portal/post/app/`에 패키지 컴포넌트로 구현되어 있고,  
`page.posts`와 `page.posts.item`은 라우팅 역할만 수행합니다:

```pug
//- page.posts/view.pug (라우팅 전용)
wiz-portal-post-list

//- page.posts.item/view.pug (라우팅 전용)
wiz-portal-post-detail
```

### 레이아웃 구조

- **layout.sidebar**: `h-screen overflow-hidden` + 콘텐츠 영역 `h-full overflow-auto`
- 모든 페이지가 회색(`#f4f5f5`) 배경 위에서 스크롤됩니다.
- 각 페이지의 `nav.sticky` 헤더는 스크롤 영역 상단에 고정됩니다.

---

## 데이터베이스

| DB 파일 | namespace | 테이블 | 용도 |
|---------|-----------|--------|------|
| data/base.db | base | user | 사용자 관리 |
| data/post.db | post | post, comment | 게시물/댓글 |

**설정**: `config/database.py`에서 namespace별 SQLite 경로를 정의합니다.

---

## 주요 API

### 인증
- `POST /wiz/api/page.access/login` — 이메일/비밀번호 로그인

### 게시물 (portal/post 패키지)
- `GET /wiz/api/portal.post.list/categories` — 카테고리 목록
- `GET /wiz/api/portal.post.list/search` — 게시물 검색 (page, dump, text, category)
- `GET /wiz/api/portal.post.detail/get` — 게시물 상세 (id)
- `POST /wiz/api/portal.post.detail/save` — 게시물 저장/수정
- `POST /wiz/api/portal.post.detail/delete` — 게시물 삭제

### 멤버
- `GET /wiz/api/page.members/list` — 멤버 목록 (text, role)
- `POST /wiz/api/page.members/invite` — 멤버 초대
- `POST /wiz/api/page.members/remove` — 멤버 삭제

### 마이페이지
- `GET /wiz/api/page.mypage/get` — 내 프로필 조회
- `POST /wiz/api/page.mypage/update_profile` — 프로필 수정
- `POST /wiz/api/page.mypage/change_password` — 비밀번호 변경
