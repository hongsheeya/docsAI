# FallAI 사이트 전체 코드 설명

이 문서는 프로그래밍을 전공하지 않은 교수님께 FallAI 프로젝트의 코드를 설명하기 위한 자료입니다. “코드 한 줄 한 줄의 문법”보다 중요한 것은, 이 사이트가 어떤 부품으로 구성되어 있고, 사용자가 버튼을 누르면 어느 파일들이 어떤 순서로 일하는지 이해하는 것입니다.

## 1. 프로젝트를 한 문장으로 설명하면

FallAI는 영상을 업로드하거나 웹캠을 연결하면 AI가 사람의 자세와 움직임을 분석하고, 낙상 위험, 행동 상태, 표정/상태 보조 판단, 학습 현황을 화면에 보여주는 웹 기반 프로토타입입니다.

## 2. 이 문서가 설명하는 범위

이 문서는 프로젝트에서 직접 작성하거나 수정한 코드와 운영 문서를 모두 사람이 이해할 수 있는 단위로 설명합니다.

| 포함 | 설명 |
| --- | --- |
| `src/app/` | 사용자가 보는 화면 코드입니다. |
| `src/model/` | AI 분석, 사용자, 데이터 처리를 담당하는 핵심 코드입니다. |
| `src/controller/` | 로그인, 관리자 권한 같은 출입 관리를 담당합니다. |
| `src/portal/` | 게시판, 세션, ORM, 공통 UI처럼 재사용되는 코드입니다. |
| `scripts/` | 학습, 평가, 성능 테스트, 보고서 생성을 위한 실행 도구입니다. |
| `docs/` | 실험 결과, 발표자료, 복구 가이드, 운영 기록입니다. |
| `README.md`, `manual.md` | 프로젝트 표지와 개발자 매뉴얼입니다. |

| 별도 구분 | 이유 |
| --- | --- |
| `node_modules/` | 외부 라이브러리입니다. 학생이 직접 작성한 원본 코드가 아니므로 전체 제출 대상에서는 보통 제외합니다. |
| AI-Hub 원본 데이터 | 용량이 크고 라이선스/개인정보 이슈가 있어 GitHub에 올리면 안 됩니다. |
| 업로드 영상과 모델 가중치 | 대용량 산출물이므로 GitHub가 아니라 별도 백업에 보관해야 합니다. |
| 토큰, 비밀번호, API 키 | 절대 GitHub에 올리면 안 되는 민감 정보입니다. |

## 3. 비전공자용 비유

FallAI를 병원이나 요양시설의 “영상 분석 접수실”이라고 생각하면 쉽습니다.

| 실제 시스템 | 비유 | 코드 위치 |
| --- | --- | --- |
| 사용자가 보는 화면 | 접수창구와 안내판 | `src/app/` |
| 영상 파일을 받는 서버 API | 접수 담당자 | `src/app/page.dashboard/api.py` |
| AI 분석 로직 | 검사실 | `src/model/struct/video_analysis.py` |
| 낙상/자세 모델 | 전문 검사 장비 | `src/model/libs/`, 학습 산출물 |
| 모델 관리 화면 | 장비 관리실 | `src/app/page.models/` |
| 학습 스크립트 | 장비를 다시 훈련시키는 작업자 | `scripts/` |
| 데이터 저장 폴더 | 창고 | `storage/`, `outputs/`, `data/` |
| 설명 문서 | 사용 설명서와 연구 노트 | `docs/`, `manual.md` |

## 4. 먼저 알아두면 좋은 용어

| 용어 | 쉬운 설명 |
| --- | --- |
| 프론트엔드 | 사용자가 직접 보는 화면입니다. 버튼, 카드, 그래프, 영상 영역이 여기에 해당합니다. |
| 백엔드 | 화면 뒤에서 요청을 처리하는 서버 코드입니다. 영상 분석, 저장, 모델 목록 조회를 담당합니다. |
| API | 화면과 서버가 대화하는 통로입니다. 버튼을 누르면 API가 호출됩니다. |
| 모델 | 데이터를 보고 판단하는 AI 파일 또는 알고리즘입니다. |
| 학습 | 모델이 데이터를 보고 규칙을 익히는 과정입니다. |
| 추론 | 학습된 모델이 새 영상에 대해 판단을 내리는 과정입니다. |
| Feature | AI가 보기 쉽게 정리한 숫자 특징입니다. 예를 들어 몸 중심이 얼마나 내려갔는지, 몸의 가로세로 비율이 어떻게 바뀌었는지 같은 값입니다. |
| RTT | 요청부터 결과가 돌아오기까지 걸리는 시간입니다. 사용자가 체감하는 응답 속도와 관련이 큽니다. |
| F1 | AI 성능을 평가하는 지표입니다. 틀리지 않는 정도와 놓치지 않는 정도를 함께 봅니다. |
| p95 | 100번 중 95번째로 느린 값입니다. 평균보다 실제 서비스 지연을 더 안정적으로 보여줍니다. |

## 5. 확장자별 의미

| 확장자 | 쉬운 설명 |
| --- | --- |
| `.py` | Python 코드입니다. 서버 처리, AI 분석, 학습 스크립트에 사용됩니다. |
| `.ts` | TypeScript 코드입니다. 화면의 동작과 상태 관리를 담당합니다. |
| `.pug` | 화면의 구조를 적는 템플릿입니다. HTML을 더 짧게 쓰는 방식입니다. |
| `.scss` | 화면 디자인 규칙입니다. 색상, 여백, 스크롤, 반응형을 정합니다. |
| `.json` | 설정이나 결과를 정해진 형식으로 저장한 파일입니다. |
| `.md` | 사람이 읽는 문서입니다. README, 보고서, 매뉴얼에 사용됩니다. |
| `.pptx` | 발표자료입니다. |
| `.pt` | AI 모델 가중치 파일입니다. 소스코드가 아니라 학습된 모델 파일입니다. |

## 6. 전체 구조를 큰 그림으로 보기

```text
사용자 브라우저
  ↓
src/app/ 화면 코드
  ↓
src/app/.../api.py 서버 API
  ↓
src/model/struct/video_analysis.py 핵심 분석 로직
  ↓
src/model/libs/ 모델 보조 로직 + storage/model 파일
  ↓
분석 결과 JSON, 화면 카드, 학습 로그, 보고서
```

이 프로젝트는 화면 코드와 AI 코드가 함께 있는 웹 서비스형 프로젝트입니다. 단순히 모델만 학습한 것이 아니라, 사용자가 실제로 영상을 올리고 결과를 확인하고, 모델 상태를 관리하고, 학습 진행률을 볼 수 있도록 화면과 운영 흐름을 같이 만들었습니다.

## 7. 최상위 파일 설명

| 파일 | 설명 |
| --- | --- |
| `README.md` | 프로젝트 소개, 현재 모델 상태, 주요 구조, API를 요약한 표지 문서입니다. |
| `manual.md` | 개발자용 상세 매뉴얼입니다. 시스템 개요, 기술 스택, 라우팅, API, 데이터 모델, AI 파이프라인이 들어 있습니다. |
| `PROJECT_OVERVIEW.md` | 프로젝트 전체 개요를 정리한 문서입니다. |
| `package.json` | WIZ/Angular 관련 실행 도구와 의존성을 기록합니다. |
| `package-lock.json` | 설치된 도구의 정확한 버전을 고정합니다. 다른 서버 복구에 필요합니다. |
| `config/season.py` | WIZ 프로젝트 설정입니다. |
| `config/pwa/sw.js` | PWA 서비스워커 설정입니다. 웹앱처럼 동작하게 돕습니다. |
| `docs/server-restore-guide-20260629.md` | 다른 서버에서 이 프로젝트를 되살리는 절차입니다. |
| `docs/professor-code-overview-20260629.md` | 지금 보고 있는 비전공자용 코드 설명입니다. |

## 8. `src/app/` - 사용자가 보는 화면

`src/app/`은 사용자가 브라우저에서 직접 보는 화면입니다. WIZ 프로젝트에서는 한 화면이 보통 다음 파일 묶음으로 구성됩니다.

| 파일명 | 역할 |
| --- | --- |
| `app.json` | 이 화면의 주소, 제목, 레이아웃, 접근 권한을 정합니다. |
| `view.pug` | 화면에 보이는 구조입니다. 버튼, 카드, 표, 입력창의 위치를 만듭니다. |
| `view.ts` | 버튼을 눌렀을 때 일어나는 동작입니다. API 호출, 상태 변경, 결과 표시를 담당합니다. |
| `view.scss` | 해당 화면만의 디자인입니다. |
| `api.py` | 화면 뒤에서 서버가 처리하는 기능입니다. 모든 화면에 있는 것은 아닙니다. |
| `view.html` | 일부 화면에서 문서형 HTML을 보관하기 위해 사용합니다. |

## 9. 화면별 코드 설명

| 화면 폴더 | 사용자가 보는 기능 | 코드 역할 |
| --- | --- | --- |
| `component.nav.sidebar/` | 왼쪽 사이드바 메뉴 | 대시보드, 모델 관리, 파이프라인, 매뉴얼 등으로 이동하는 메뉴를 만듭니다. |
| `layout.sidebar/` | 기본 화면 틀 | 사이드바가 있는 전체 레이아웃입니다. 대부분의 화면이 이 틀 안에서 보입니다. |
| `layout.empty/` | 빈 화면 틀 | 로그인처럼 사이드바가 필요 없는 화면에 씁니다. |
| `page.access/` | 로그인 | 이메일/비밀번호를 입력받고 세션을 만듭니다. |
| `page.dashboard/` | 메인 분석 화면 | 영상 업로드, 웹캠 분석, 스켈레톤 표시, 다중 인원 카드, 행동/표정 결과, 학습 등록을 담당합니다. |
| `page.models/` | 모델 관리 화면 | 현재 운영 모델, 성능 수치, 버전, 학습 진행률, 모델 등록/삭제, 감도 조절, 모델 조합을 관리합니다. |
| `page.pipeline/` | AI 파이프라인 설명 | 영상이 어떤 순서로 분석되는지, 4카메라 시뮬레이션과 프레임 처리 정보를 보여줍니다. |
| `page.admin.analysis/` | 관리자 분석 설정 | 알림, 보호자, 분석 정책처럼 관리자용 설정을 다룹니다. |
| `page.admin.llm/` | LLM 설정 | AI 설명 문장 생성과 관련된 설정을 다룹니다. |
| `page.manual/` | 사용 설명서 화면 | 사이트 안에서 매뉴얼을 볼 수 있게 합니다. |
| `page.members/` | 멤버 관리 | 사용자 목록, 초대, 권한 관리를 담당합니다. |
| `page.mypage/` | 내 정보 | 프로필 수정, 비밀번호 변경을 담당합니다. |
| `page.posts/` | 게시판 목록 | 게시글 목록으로 이동하는 라우팅 화면입니다. 실제 게시판 기능은 `portal/post`에 있습니다. |
| `page.posts.item/` | 게시글 상세 | 게시글 하나를 보여주는 라우팅 화면입니다. |
| `page.presentation/` | 발표자료 화면 | 프로젝트 발표자료나 발표용 내용을 사이트 안에서 보여줍니다. |

## 10. 메인 분석 화면 상세 설명

### `src/app/page.dashboard/app.json`

이 화면이 `/` 주소에 연결되고, 기본 레이아웃으로 `layout.sidebar`를 사용한다고 정합니다.

### `src/app/page.dashboard/view.pug`

사용자가 보는 대시보드 화면의 구조입니다.

주요 영역은 다음과 같습니다.

1. 영상 업로드/웹캠 실행 영역
2. 원본 영상 또는 스켈레톤 표시 영역
3. 사람별 요약 카드
4. 낙상 위험 점수
5. 행동 분석 결과
6. 표정/상태 보조 분석 결과
7. 분석 근거와 서버 처리 시간
8. 학습 등록 영역
9. 백그라운드 학습 현황
10. 분석 로그와 상세 결과

### `src/app/page.dashboard/view.ts`

화면의 “동작”을 담당합니다.

| 담당 기능 | 설명 |
| --- | --- |
| 영상 선택 | 사용자가 업로드한 파일을 화면 상태에 저장합니다. |
| 웹캠 녹화 | 브라우저의 MediaRecorder로 일정 시간 단위 영상 조각을 만듭니다. |
| 서버 전송 | 영상 파일과 메타데이터를 API로 보냅니다. |
| 결과 표시 | 서버가 돌려준 낙상 점수, 행동, 표정, 근거를 화면에 배치합니다. |
| 스켈레톤 표시 | 원본 대신 관절선 중심으로 보여 개인정보 노출을 줄입니다. |
| 다중 인원 처리 | 여러 사람이 보일 때 사람별 요약 카드를 만들고 선택된 사람의 상세 분석을 보여줍니다. |
| 학습 등록 | 사용자가 라벨을 붙여 학습 데이터로 저장할 수 있게 합니다. |
| 상태 저장 | 최근 분석 결과를 브라우저 저장소에 남겨 새로고침 후에도 일부 상태를 유지합니다. |

### `src/app/page.dashboard/api.py`

화면이 서버에 요청할 때 통과하는 접수창구입니다.

| 함수 | 쉬운 설명 |
| --- | --- |
| `prototype_info` | 현재 시스템 정보, 모델 상태, 설정값을 가져옵니다. |
| `analyze_upload` | 업로드된 영상을 실제 AI 분석 로직으로 넘깁니다. |
| `warmup_models` | 모델을 미리 로딩해 첫 분석 지연을 줄입니다. |
| `model_registry` | 현재 등록된 모델 목록과 성능 정보를 가져옵니다. |
| `submit_training_sample` | 사용자가 등록한 영상과 라벨을 학습 데이터로 저장합니다. |
| `start_training_job` | 학습 작업을 시작합니다. |
| `training_job_status` | 학습 작업이 얼마나 진행됐는지 확인합니다. |
| `continuous_training_status` | 백그라운드 상시 학습 상태를 확인합니다. |
| `resume_continuous_training` | 멈춘 상시 학습을 다시 시작합니다. |
| `apply_training_job` | 학습 결과를 운영 모델에 반영합니다. |
| `submit_analysis_feedback` | 분석 결과에 대한 사용자 피드백을 저장합니다. |
| `dispatch_risk_alerts` | 위험 알림 발송을 처리합니다. |
| `reference_preview_info`, `reference_preview` | 참고 영상 미리보기 정보를 제공합니다. |
| `chunk_preview_info`, `chunk_preview` | 실시간 분석 조각 영상 정보를 제공합니다. |
| `analysis_video_info`, `analysis_video` | 분석 결과에 연결된 영상 정보를 제공합니다. |
| `shadow_report` | 운영 모델과 후보 모델의 비교 결과를 확인합니다. |
| `evaluate_system` | 시스템 평가를 실행합니다. |
| `baseline_report` | 기본 모델 평가 리포트를 가져옵니다. |

## 11. 모델 관리 화면 상세 설명

### `src/app/page.models/view.pug`

일반 사용자도 이해하기 쉽게 모델 관리 화면을 여러 구역으로 나눕니다.

1. 한눈에 보는 운영 상태
2. 현재 연결된 모델과 버전
3. 백그라운드 학습 현황
4. 표정 모델 병목 요약
5. 모델 등록
6. 낙상 감도 조절
7. 운영 모델 조합 저장/적용
8. 고급 비교표
9. 삭제 대기 모델 관리

### `src/app/page.models/view.ts`

모델 관리 화면의 동작을 담당합니다.

| 담당 기능 | 설명 |
| --- | --- |
| `loadRegistry` 계열 | 서버에서 모델 목록과 학습 상태를 불러옵니다. |
| 버전 표시 | 모델마다 `v1`, `v23`, `v92` 같은 버전 정보를 화면에 보이게 만듭니다. |
| 성능 요약 | F1, Accuracy, Recall, sample 수를 사람이 읽기 좋은 문장으로 바꿉니다. |
| 학습 카드 | 현재 진행 중인 학습의 단계, ETA, 최근 로그를 카드로 보여줍니다. |
| 모델 업로드 | 새 모델 파일과 메타데이터를 서버에 보냅니다. |
| 삭제/복구 | 의미 없는 모델을 삭제 대기 처리하거나 취소합니다. |
| 감도 조절 | 낙상 판단 threshold를 사용자가 조정할 수 있게 합니다. |
| 운영 조합 | RF-Fall, XG-Posture, 표정 모델 등을 묶어 하나의 운영 조합으로 저장합니다. |
| 비교표 | 후보 모델들의 성능을 정렬하고 비교합니다. |

### `src/app/page.models/api.py`

모델 관리 화면 전용 서버 API입니다.

| 함수 | 쉬운 설명 |
| --- | --- |
| `model_registry` | 등록된 모델과 성능, 버전, 학습 현황을 가져옵니다. |
| `upload_model_asset` | 모델 파일을 새로 등록합니다. |
| `delete_model_asset` | 모델을 삭제 대기 또는 삭제 처리합니다. |
| `cancel_model_delete` | 삭제 대기 상태를 취소합니다. |
| `set_fall_sensitivity` | 낙상 판단 민감도를 저장합니다. |
| `set_runtime_model_selection` | 운영에 사용할 모델을 선택합니다. |
| `save_runtime_model_bundle` | 모델 조합을 하나의 묶음으로 저장합니다. |
| `apply_runtime_model_bundle` | 저장된 모델 조합을 운영에 적용합니다. |
| `delete_runtime_model_bundle` | 저장된 조합을 삭제합니다. |
| `cleanup_model_candidates` | 성능 수치가 없거나 낮은 후보 모델을 정리합니다. |

## 12. AI 핵심 코드

### `src/model/struct.py`

프로젝트의 중앙 안내소입니다. 화면 API가 `wiz.model("struct")`를 호출하면 이 파일이 사용자 기능, 영상 분석 기능, 게시판 기능으로 연결해 줍니다.

| 역할 | 설명 |
| --- | --- |
| ORM 연결 | 데이터베이스 접근 도구를 준비합니다. |
| 세션 연결 | 로그인 상태를 사용할 수 있게 합니다. |
| 사용자 기능 연결 | `struct.user`로 사용자 관리 기능을 부릅니다. |
| 영상 분석 연결 | `struct.video_analysis`로 AI 분석 기능을 부릅니다. |
| 포털 패키지 연결 | 게시판 같은 재사용 패키지를 동적으로 불러옵니다. |

### `src/model/struct/video_analysis.py`

FallAI의 가장 중요한 핵심 파일입니다. 영상 분석, 모델 목록, 학습 상태, 결과 저장, 알림, 평가가 이 파일을 중심으로 연결됩니다.

이 파일의 역할을 쉬운 말로 나누면 다음과 같습니다.

| 역할 | 설명 |
| --- | --- |
| 프로젝트 경로 찾기 | `storage`, `outputs`, 모델 파일 위치를 안정적으로 찾습니다. |
| 영상 받기 | 업로드된 영상을 저장하고 분석할 준비를 합니다. |
| 프레임 처리 | 영상을 일정 간격으로 잘라 사람이 있는지 확인합니다. |
| 사람 추적 | 영상 속 사람을 찾고, 여러 사람이 있을 때 사람별 정보를 나눕니다. |
| 스켈레톤 처리 | 개인정보 부담을 줄이기 위해 관절선 중심 결과를 만듭니다. |
| Feature 계산 | 몸 중심 이동, 가로세로 비율, 바닥 근접도 같은 숫자 특징을 만듭니다. |
| 낙상 판단 | RF-Fall 모델로 낙상 가능성을 계산합니다. |
| 자세/행동 판단 | XG-Posture 모델로 서기, 걷기, 뛰기, 앉기, 눕기 등을 추정합니다. |
| 가림 보조 | 하체가 가려진 경우에도 판단이 무너지지 않게 보조 모델 정보를 사용합니다. |
| 표정/상태 보조 | 표정 모델과 상태 모델 결과를 보조 정보로 연결합니다. |
| 결과 저장 | 분석 결과, 로그, 미리보기 정보를 파일로 남깁니다. |
| 학습 등록 | 사용자가 남긴 라벨과 메모를 학습 데이터로 저장합니다. |
| 모델 등록 | 새 모델 파일을 업로드하고 메타데이터를 기록합니다. |
| 모델 버전 관리 | 운영 모델, 후보 모델, 버전, 성능 수치를 관리합니다. |
| 백그라운드 학습 상태 | 학습이 돌아가는지, ETA가 얼마인지 화면에 전달합니다. |
| 알림 설정 | 보호자 알림 설정과 발송 이력을 관리합니다. |

교수님이 AI 시스템의 본체를 확인하려면 이 파일을 보면 됩니다. 다만 파일이 매우 크기 때문에 처음부터 끝까지 문법을 읽기보다, 위 역할표를 기준으로 필요한 함수 묶음을 찾는 것이 현실적입니다.

### `src/model/libs/video_baseline.py`

낙상 판단 모델의 학습과 평가를 돕는 코드입니다.

| 기능 | 설명 |
| --- | --- |
| 학습 데이터 읽기 | 저장된 feature CSV와 사용자 등록 데이터를 모읍니다. |
| feature 추출 | 영상에서 모델이 볼 숫자 특징을 만듭니다. |
| RandomForest 학습 | 낙상/비낙상을 구분하는 모델을 학습합니다. |
| 성능 평가 | Accuracy, Precision, Recall, F1, ROC-AUC를 계산합니다. |
| 요약 저장 | 학습 결과를 JSON으로 저장해 화면에서 읽을 수 있게 합니다. |

### `src/model/libs/action_behavior_model.py`

행동/자세 분류의 기준표입니다.

| 자세 | 코드상 의미 |
| --- | --- |
| 서기 | 몸이 세워져 있고 큰 이동이 없는 상태 |
| 걷기 | 일정한 보폭으로 이동하는 상태 |
| 뛰기 | 걷기보다 빠르게 이동하는 상태 |
| 앉기 | 엉덩이를 지지면에 둔 상태 |
| 눕기 | 몸이 수평에 가까운 상태 |
| 낙상 | 급격하고 비자발적으로 바닥으로 넘어지는 상태 |

이 파일은 낙상 최종 판단을 직접 하는 것보다는, 자세와 행동을 사람이 이해할 수 있는 이름으로 정리하는 역할이 큽니다.

## 13. 사용자와 권한 코드

| 파일 | 설명 |
| --- | --- |
| `src/controller/base.py` | 모든 요청에서 기본 세션을 준비합니다. |
| `src/controller/user.py` | 로그인이 필요한 화면인지 확인합니다. |
| `src/controller/admin.py` | 관리자 권한이 필요한 화면인지 확인합니다. |
| `src/model/struct/user.py` | 로그인, 사용자 생성, 사용자 정보 수정 같은 기능을 담당합니다. |
| `src/model/db/user.py` | 사용자 데이터베이스 테이블 구조입니다. |

비유하면 `controller`는 출입문 경비, `model/struct/user.py`는 회원 명부 관리자, `model/db/user.py`는 회원 명부 양식입니다.

## 14. 게시판과 공통 기능 코드

### `src/portal/post/`

게시판 기능을 담은 재사용 패키지입니다.

| 위치 | 설명 |
| --- | --- |
| `app/list/` | 게시글 목록 화면입니다. |
| `app/detail/` | 게시글 상세, 작성, 수정 화면입니다. |
| `model/db/post.py` | 게시글 테이블 구조입니다. |
| `model/db/comment.py` | 댓글 테이블 구조입니다. |
| `model/struct/post.py` | 게시글 검색, 저장, 삭제 기능입니다. |
| `model/struct/comment.py` | 댓글 저장, 삭제 기능입니다. |
| `portal.json` | 이 패키지를 WIZ가 인식하게 하는 설정입니다. |

### `src/portal/season/`

WIZ 프로젝트에서 공통으로 쓰는 기반 패키지입니다.

| 위치 | 설명 |
| --- | --- |
| `model/orm.py` | 데이터베이스를 편하게 쓰게 해주는 도구입니다. |
| `model/session.py` | 로그인 세션을 관리합니다. |
| `model/auth/oidc.py`, `model/auth/saml.py` | 외부 인증 연동 구조입니다. |
| `model/smtp.py` | 메일 발송 관련 기능입니다. |
| `app/modal/` | 공통 모달 창입니다. |
| `app/pagination/` | 페이지 번호 UI입니다. |
| `app/form.dropdown/` | 드롭다운 입력 UI입니다. |
| `app/loading.*` | 로딩 화면입니다. |
| `libs/` | 화면에서 쓰는 공통 TypeScript 유틸리티입니다. |

이 부분은 FallAI만을 위한 코드라기보다, WIZ 서비스의 기반 기능에 가깝습니다.

## 15. Angular/WIZ 빌드 코드

| 위치 | 설명 |
| --- | --- |
| `src/angular/app/app-routing.module.ts` | WIZ 페이지들을 Angular 라우팅으로 연결합니다. |
| `src/angular/app/app.module.ts` | Angular 앱의 전체 모듈 설정입니다. |
| `src/angular/app/app.component.*` | 최상위 Angular 컴포넌트입니다. |
| `src/angular/main.ts` | Angular 앱 시작점입니다. |
| `src/angular/styles/` | Angular 전체 스타일입니다. |
| `src/angular/wiz.ts` | WIZ와 Angular 사이 연결 코드입니다. |
| `src/angular/angular.json` | Angular 빌드 설정입니다. |

교수님 입장에서는 이 영역을 “웹앱을 실행하게 해주는 엔진 설정”으로 이해하면 됩니다.

## 16. 영상 분석 흐름을 아주 쉽게 풀어쓰기

사용자가 영상을 업로드했을 때의 흐름입니다.

1. 사용자가 대시보드에서 영상 파일을 선택합니다.
2. `page.dashboard/view.ts`가 파일과 선택 옵션을 모읍니다.
3. `page.dashboard/api.py`의 `analyze_upload`로 파일을 보냅니다.
4. `api.py`는 `video_analysis.py`의 분석 기능을 호출합니다.
5. `video_analysis.py`가 영상을 저장하고 프레임을 읽습니다.
6. 사람을 찾고 관절 좌표 또는 박스 정보를 추출합니다.
7. 여러 사람이 있으면 사람별로 나눠 추적합니다.
8. 각 사람의 움직임을 숫자 feature로 바꿉니다.
9. RF-Fall이 낙상 가능성을 계산합니다.
10. XG-Posture가 행동 상태를 계산합니다.
11. 표정/상태 모델이 보조 정보를 붙입니다.
12. 최종 결과를 JSON 형태로 화면에 돌려줍니다.
13. `view.ts`가 결과를 받아 카드, 막대그래프, 스켈레톤, 로그로 보여줍니다.

## 17. 학습 데이터 등록 흐름

1. 사용자가 분석 결과를 보고 “이 영상은 낙상이다/아니다” 같은 라벨을 선택합니다.
2. 화면은 영상, 라벨, 메모를 서버로 보냅니다.
3. `submit_training_sample` API가 파일을 받습니다.
4. `video_analysis.py`가 라벨별 폴더에 저장합니다.
5. 이후 학습 스크립트가 이 데이터를 읽어 모델 성능 개선에 활용합니다.

이 기능은 사용자의 피드백을 모델 개선으로 연결하기 위한 구조입니다.

## 18. 모델 관리 흐름

1. `page.models` 화면이 `model_registry` API를 호출합니다.
2. 서버는 현재 운영 모델과 후보 모델 목록을 모읍니다.
3. 각 모델의 버전, 성능, 샘플 수, 생성 시각을 정리합니다.
4. 화면은 일반 사용자용 요약 카드와 고급 비교표로 나눠 보여줍니다.
5. 사용자가 모델을 선택하면 `set_runtime_model_selection`이 실행됩니다.
6. 여러 모델 조합을 저장하면 `save_runtime_model_bundle`에 기록됩니다.
7. 운영 적용 시 `apply_runtime_model_bundle`이 실제 선택값을 바꿉니다.

여기서 중요한 점은 모델을 파일 하나로만 보지 않고, “어떤 모델이 현재 쓰이고 있는지”, “버전이 무엇인지”, “성능이 얼마인지”를 화면에서 확인하게 만든 것입니다.

## 19. AI 모델별 역할

| 모델 | 쉬운 설명 | 이 프로젝트에서의 역할 |
| --- | --- | --- |
| RF-Fall | 낙상인지 아닌지 빠르게 판단하는 모델 | 최종 낙상 판단의 중심입니다. |
| XG-Posture | 자세와 행동을 구분하는 모델 | 서기, 걷기, 뛰기, 앉기, 눕기 등 설명 근거를 제공합니다. |
| 가림 보조 모델 | 몸 일부가 가려져도 판단을 보완하는 모델 | 하체 가림 상황에서 판단 안정성을 높입니다. |
| AI-Hub 82 표정 모델 | 표정 상태를 보는 모델 | 낙상 이후 불편/고통 가능성을 보조적으로 봅니다. |
| AI-Hub 173 상태 모델 | 상태 데이터를 보는 모델 | 행동/상태 보조 판단에 사용합니다. |
| YOLO Pose | 사람과 관절 위치를 찾는 모델 | 영상에서 사람의 위치와 움직임을 뽑는 첫 단계입니다. |

## 20. `scripts/` - 학습과 실험 도구 전체 설명

`scripts/` 폴더는 사이트 화면 뒤에서 모델을 학습하고, 성능을 평가하고, 보고서를 만드는 작업 도구함입니다.

| 파일 | 쉬운 설명 |
| --- | --- |
| `analyze_aihub82_bottlenecks.py` | 표정 모델이 어떤 클래스에서 막히는지 병목을 분석합니다. |
| `benchmark_multiperson_frame_processing.py` | 여러 사람이 있을 때 프레임 처리 속도를 측정합니다. |
| `bootstrap_models.py` | 기본 모델 파일과 메타데이터를 초기화합니다. |
| `build_person_dataset.py` | 사람 검출/추적용 데이터셋을 만듭니다. |
| `calibrate_aihub82_facial_scores.py` | 표정 모델 점수를 실제 표시용으로 보정합니다. |
| `continuous_aihub82_training_supervisor.py` | AI-Hub 82 표정 모델을 백그라운드에서 계속 학습하고 상태를 기록합니다. |
| `continuous_all_model_training_supervisor.py` | 여러 모델 학습을 종합적으로 관리하는 감독 스크립트입니다. |
| `create_lower_body_occlusion_augments.py` | 하체 가림 상황을 인위적으로 만들어 학습 데이터를 보강합니다. |
| `dashboard_training_job.py` | 대시보드에서 시작한 학습 작업을 실행합니다. |
| `direct_train.py` | 직접 학습을 실행하기 위한 간단한 진입 스크립트입니다. |
| `download_kth_action.py` | 외부 행동 데이터셋을 내려받는 도구입니다. |
| `e2e_test.py` | 전체 기능이 처음부터 끝까지 동작하는지 확인하는 테스트입니다. |
| `emergency_restore_models.py` | 모델 파일이 깨졌을 때 긴급 복구를 돕습니다. |
| `ensure_persistent_runtime_links.sh` | `storage`, `outputs` 같은 런타임 폴더 링크가 유지되도록 점검합니다. |
| `evaluate_aihub82_provider_models.py` | 표정 모델 후보들을 비교 평가합니다. |
| `evaluate_models.py` | 여러 모델의 성능을 평가합니다. |
| `evaluate_rf_detailed.py` | RF 낙상 모델을 자세히 평가합니다. |
| `evaluate_rf_validation_and_uploads.py` | 검증 데이터와 업로드 데이터를 함께 평가합니다. |
| `evaluate_xgb_detailed.py` | XGBoost 계열 모델을 자세히 평가합니다. |
| `extract_fall_features.py` | 낙상 판단에 필요한 feature를 영상에서 추출합니다. |
| `extract_person_bbox.py` | 사람 위치 박스를 추출합니다. |
| `generate_*presentation*.py` | 발표자료를 자동 생성합니다. |
| `generate_xg_posture_report.py` | 자세 모델 보고서를 만듭니다. |
| `inference_test.py` | 모델 추론이 정상 동작하는지 시험합니다. |
| `monitor_aihub*_redownload_status.sh` | AI-Hub 데이터 재다운로드 상태를 확인합니다. |
| `monitor_aihub82_bottlenecks.sh` | 표정 모델 병목 분석을 주기적으로 확인합니다. |
| `optimize_xg_posture_features.py` | 자세 모델 feature 개선을 실험합니다. |
| `overfitting_analysis_light.py` | 모델이 학습 데이터에만 과하게 맞춰졌는지 점검합니다. |
| `priority_occlusion_after_71461.sh` | 가림 보조 모델 관련 우선 학습을 실행합니다. |
| `quick_validate_facial_aux.py` | 표정 보조 모델을 빠르게 검증합니다. |
| `redownload_aihub*_sources.sh` | AI-Hub 원천 데이터를 다시 받는 도구입니다. |
| `reevaluate_existing_uploads.py` | 기존 업로드 영상들을 새 기준으로 다시 평가합니다. |
| `repair_aihub61_split_sources.py` | AI-Hub 분할 데이터 문제를 복구합니다. |
| `repair_production_models.py` | 운영 모델 메타데이터나 파일을 복구합니다. |
| `restart_aihub82_supervisor_detached.sh` | 표정 모델 백그라운드 학습을 다시 시작합니다. |
| `restore_best_recorded_model_state.py` | 기록된 최고 모델 상태로 되돌립니다. |
| `retrain_rf_*.py` | RF 낙상 모델을 여러 전략으로 재학습합니다. |
| `retrain_xg_posture_*.py` | XG-Posture 자세 모델을 재학습합니다. |
| `retrain_xgb_*.py` | XGBoost 계열 실험 모델을 재학습합니다. |
| `review_person_labels.py` | 사람/자세 라벨을 검토합니다. |
| `run_sample_yolo_training.sh` | YOLO 샘플 학습을 실행합니다. |
| `sample_validation_videos.py` | 검증용 영상 샘플을 뽑습니다. |
| `simulate_four_camera_tracking.py` | 4개 코너 카메라 구조를 가정한 시뮬레이션과 성능 테스트를 합니다. |
| `targeted_occlusion_weak_pose_loop.py` | 가림/약한 포즈 구간을 집중 개선하는 반복 학습입니다. |
| `train_driver_state_aihub173.py` | AI-Hub 173 상태 모델을 학습합니다. |
| `train_facial_emotion_aihub82.py` | AI-Hub 82 표정 모델을 학습합니다. |
| `train_fall_classifier.py` | 낙상 분류 모델을 학습합니다. |
| `train_person_detector.py` | 사람 검출 모델을 학습합니다. |
| `train_sample_yolo.py` | YOLO 샘플 학습을 실행합니다. |
| `train_validation_additional.py` | 추가 검증 데이터를 학습/평가에 반영합니다. |
| `train_video_yolo.py` | 영상 기반 YOLO 학습을 실행합니다. |
| `update_aihub_redownload_status.py` | AI-Hub 재다운로드 상태 문서를 갱신합니다. |
| `update_dataset_acquisition_manifest.py` | 데이터 확보 현황 목록을 갱신합니다. |
| `validate_facial_aux_aihub71641.py` | 표정 보조 모델에 필요한 데이터셋을 검증합니다. |
| `validate_four_camera_tracking_feasibility.py` | 4카메라 추적 가능성을 검증합니다. |
| `weekend_training_supervisor.py` | 장시간 학습을 주말 동안 관리합니다. |
| `yolo_fall_runtime.py` | YOLO 기반 낙상 추론 런타임 보조 코드입니다. |

## 21. 표정 모델 성능 개선 관련 코드

표정 모델은 AI-Hub 82 데이터를 사용합니다. 단순히 계속 돌리는 것만으로는 성능이 오르지 않기 때문에, 병목을 확인하고 학습 전략을 바꾸는 구조가 필요했습니다.

| 파일 | 담당 |
| --- | --- |
| `scripts/train_facial_emotion_aihub82.py` | 표정 이미지와 라벨을 읽고 MobileNet 계열 모델을 학습합니다. focal loss, boundary penalty, class weight 같은 전략이 들어 있습니다. |
| `scripts/continuous_aihub82_training_supervisor.py` | 여러 실험을 순서대로 실행하고, 성능이 좋아진 후보만 운영 후보로 승격합니다. |
| `scripts/analyze_aihub82_bottlenecks.py` | 어떤 표정 클래스가 반복적으로 헷갈리는지 분석합니다. |
| `docs/aihub82-continuous-training-notes.md` | 상시 학습 운영 메모입니다. |
| `docs/facial-score-reliability-and-training-plan.md` | 표정 점수 신뢰도와 학습 계획입니다. |

핵심은 “학습을 오래 돌린다”가 아니라 “어떤 클래스에서 왜 막히는지 보고, 그 병목에 맞춰 데이터와 손실 함수를 조정한다”입니다.

## 22. 4카메라 시뮬레이션 코드

### `scripts/simulate_four_camera_tracking.py`

이 스크립트는 실제 카메라 4대를 당장 설치하지 않고, 하나의 영상을 네 방향 코너 카메라처럼 변형해 실험합니다.

| 단계 | 설명 |
| --- | --- |
| 영상 읽기 | 원본 영상에서 프레임을 가져옵니다. |
| 코너뷰 생성 | 같은 프레임을 네 방향 카메라처럼 변형합니다. |
| 가림 추가 | 일부 화면에 가림 상황을 넣어 현실성을 높입니다. |
| YOLO Pose 실행 | 각 카메라뷰에서 사람과 자세를 찾습니다. |
| 결과 융합 | 네 카메라 중 하나라도 사람을 잘 잡으면 전체 추적 성공으로 봅니다. |
| RTT 계산 | 4초 단위 분석이 얼마나 빨리 끝나는지 측정합니다. |
| 보고서 저장 | JSON과 Markdown 보고서로 결과를 남깁니다. |

기존 테스트 요약은 다음과 같습니다.

| 조건 | 4카메라 fused recall | pose FPS | 4초 chunk p95 RTT | 해석 |
| --- | ---: | ---: | ---: | --- |
| 320px | 100.0% | 81.35 | 0.839초 | 실시간 기본값으로 적합합니다. |
| 640px | 100.0% | 18.26 | 3.689초 | 가능하지만 처리 여유가 작습니다. |

즉, 4카메라 구조는 프로토타입으로 가능하지만 실제 제품 판정에는 실제 4대 동시 촬영 데이터로 ID 유지율, 가림 상황, 행동 정확도를 다시 검증해야 합니다.

## 23. 저장되는 데이터와 GitHub에 올리면 안 되는 데이터

| 위치 | 설명 | GitHub 업로드 여부 |
| --- | --- | --- |
| `src/` | 직접 작성한 소스코드 | 올려도 됩니다. |
| `docs/` | 설명 문서와 보고서 | 민감 정보가 없으면 올려도 됩니다. |
| `scripts/` | 학습/평가 도구 | 올려도 됩니다. |
| `storage/` | 업로드 영상, 학습 데이터, 모델 메타데이터 | 원본 영상/대용량 파일은 올리면 안 됩니다. |
| `outputs/` | 성능 테스트 결과, 산출물 | 요약 보고서는 가능하지만 대용량 산출물은 별도 보관합니다. |
| `data/` | SQLite DB, 서비스 데이터 | 개인정보 가능성이 있어 공개 저장소에는 올리지 않습니다. |
| `.env`, 토큰 파일 | 비밀번호/API 키 | 절대 올리면 안 됩니다. |
| `.pt`, `.pkl`, `.joblib` 대용량 모델 | 학습된 모델 파일 | 용량과 라이선스에 따라 별도 보관이 안전합니다. |

교수님께 “전체 코드”를 보여드릴 때는 소스코드와 문서를 GitHub로 공유하고, 대용량 데이터와 민감 정보는 별도 저장소 또는 드라이브로 분리하는 것이 맞습니다.

## 24. 주요 문서 파일 설명

| 문서 | 설명 |
| --- | --- |
| `docs/2026-06-01-current-status-and-training-pipeline.md` | 2026년 6월 1일 기준 모델과 학습 파이프라인 상태입니다. |
| `docs/analysis-time-optimization-plan.md` | 분석 시간 최적화 계획입니다. |
| `docs/bulk-upload-training-intake-plan.md` | 대량 학습 데이터 등록 계획입니다. |
| `docs/commercial-multiperson-capacity-and-frame-budget-20260617.md` | 상용 환경에서 다중 인원과 프레임 예산을 검토한 문서입니다. |
| `docs/frame-processing-and-multiperson-tracking-*.md` | 프레임 처리와 다중 인원 추적 분석입니다. |
| `docs/multiperson-performance-limit-test-20260625.md` | 다중 인원 처리 한계 테스트입니다. |
| `docs/xg-dual-architecture.md` | 예전 XG-Dual 설계 문서입니다. 현재 운영 기준은 RF-Dual입니다. |
| `docs/presentation/*.md`, `*.pptx` | 발표자료 원고와 PPT 파일입니다. |
| `docs/server-restore-guide-20260629.md` | 다른 서버 복구 절차입니다. |

## 25. 교수님이 실제로 코드를 확인할 때 추천 순서

1. `README.md`를 읽어 프로젝트의 목적과 현재 모델 상태를 봅니다.
2. 이 문서 `docs/professor-code-overview-20260629.md`를 읽어 구조를 잡습니다.
3. `manual.md`에서 기술적인 상세 설명을 확인합니다.
4. `src/app/page.dashboard/`를 봐서 사용자가 보는 분석 화면을 확인합니다.
5. `src/app/page.models/`를 봐서 모델 관리 화면과 학습 상태 표시를 확인합니다.
6. `src/model/struct/video_analysis.py`를 봐서 AI 분석의 중심 로직을 확인합니다.
7. `src/model/libs/video_baseline.py`와 `src/model/libs/action_behavior_model.py`를 봐서 낙상/자세 모델 보조 로직을 확인합니다.
8. `scripts/train_facial_emotion_aihub82.py`와 `scripts/continuous_aihub82_training_supervisor.py`를 봐서 표정 모델 개선 구조를 확인합니다.
9. `scripts/simulate_four_camera_tracking.py`를 봐서 4카메라 성능 검증 방식을 확인합니다.
10. `docs/server-restore-guide-20260629.md`를 봐서 다른 서버에서 복구 가능한지 확인합니다.

## 26. 교수님께 보낼 때 추천 문구

```text
교수님, 프로젝트 코드는 GitHub 저장소에 정리해 두었습니다.
README에는 전체 프로젝트 개요가 있고, docs/professor-code-overview-20260629.md에는 비전공자도 이해할 수 있도록 화면, 서버, AI 분석, 학습 스크립트, 데이터 보관 방식을 풀어서 정리했습니다.
대용량 영상, AI-Hub 원본 데이터, 모델 가중치, 비밀번호/API 키는 GitHub에 올리지 않고 별도로 보관했습니다.
```

## 27. 이 프로젝트에서 강조할 만한 구현 포인트

- 영상 업로드와 웹캠 분석을 모두 지원합니다.
- 원본 영상 노출을 줄이기 위해 스켈레톤 중심 화면을 제공합니다.
- 여러 사람이 보일 때 사람별 요약 카드를 만들고, 선택한 사람의 상세 분석을 볼 수 있게 했습니다.
- 낙상 판단만 보여주는 것이 아니라 행동 상태와 판단 근거를 함께 보여줍니다.
- 모델 관리 화면에서 일반 사용자용 요약과 고급 사용자용 비교표를 분리했습니다.
- 모델 버전, 성능 수치, 백그라운드 학습 상태, ETA를 화면에 표시합니다.
- 표정 모델은 성능 병목을 따로 분석하고 개선 전략을 문서화했습니다.
- 4카메라 구조 가능성을 시뮬레이션으로 검증하고 RTT를 측정했습니다.
- 발표자료와 복구 가이드를 함께 만들어 결과물 재현성을 높였습니다.

## 28. 결론

FallAI는 단순한 AI 모델 학습 코드가 아니라, 사용자가 영상을 넣고 결과를 확인하고, 모델을 관리하고, 학습 현황을 추적하고, 성능 검증 보고서까지 남길 수 있게 만든 웹 서비스형 AI 프로젝트입니다. 교수님께는 GitHub 저장소로 소스코드와 문서를 공유하고, 대용량 데이터와 민감 정보는 별도 보관했다는 점을 함께 설명하는 방식이 가장 합리적입니다.
