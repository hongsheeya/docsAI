# FallAI Project

WIZ 프레임워크 기반 FallAI 운영 프로젝트입니다.
현재는 **낙상 탐지 / 자세 분류 / 실시간 영상 분석** 중심으로 운영 중이며, 게시판·사용자관리·대시보드 구조 위에 프로토타입 기능이 확장되어 있습니다.

---

## 현재 모델 상태 (2026-04-27)

- 기본 업로드/실시간 운영 축: `rf-dual`
- 청크 정책: `0~2 / 0~4 / 0~5` Dense Bootstrap 뒤 `2~7 / 4~9 / 6~11` 형태의 2초 간격 5초 슬라이딩 윈도우
- RF 운영 모델: Validation 1100영상 기반 재학습본
    - Train `899`, Validation `200`
    - Accuracy `89.5%`
    - Precision `84.96%`
    - Recall `96.0%`
    - F1 `90.14%`
    - 운영 threshold `0.35`
- XG-Posture: 6-class 재학습 완료, CV accuracy `93.7%`
- 운영 행동분류 노출: **5-class (`stand/walk/run/sit/lie`)**
- raw 6-class `fall` 확률은 **진단용(`posture_raw_*`)으로만 유지**
- `sit ↔ lie` 경계: 상체가 직립에 가깝고 무릎 굽힘이 보이는 경우 `upright_sit_guard`로 `lie` rescue를 억제
- XG-Posture 학습 검증: **clip-grouped CV** 기준으로 누수 방지 적용
- 기존 업로드 재평가: FP `0`, FN `0`

상세 운영 문서는 [docs/prototype/fall-detection/README.md](docs/prototype/fall-detection/README.md), 전체 개요는 [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)를 참고합니다. [docs/xg-dual-architecture.md](docs/xg-dual-architecture.md)는 **레거시 설계 문서**이며, 현재 운영 기준은 RF-Dual입니다.

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
