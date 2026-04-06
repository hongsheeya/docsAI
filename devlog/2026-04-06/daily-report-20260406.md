# 일일 개발 보고서

- **날짜**: 2026-04-06 (일)
- **프로젝트**: FallAI — 낙상 위험 영상 분석 프로토타입
- **프로젝트 경로**: `project/main`

---

## 1. 금일 작업 요약

| 구분 | 내용 |
|------|------|
| 총 작업 건수 | **22건** (devlog 001~020 + FN-0027, FN-0028) |
| 핵심 성과 | XG-Dual 아키텍처 전면 도입, 6-class 자세 분류 파이프라인 완성, 실시간 UI 안정화, 학습 데이터 인프라 구축 |
| 주요 변경 파일 | `video_analysis.py`, `view.pug`, `view.ts`, `view.scss`, `layout.sidebar/view.scss` (신규), `download_kth_action.py` (신규) |
| 빌드 상태 | ✅ 정상 (최종 빌드 6299ms) |
| 잔여 작업 | FN-0029(XG-Posture 재훈련), FN-0030(sit/lie 데이터), FN-0031(MediaPipe 경고 최소화) |

---

## 2. 상세 작업 내역

### 2.1 XG-Dual 아키텍처 구축 (devlog 001~012)

**목표**: 기존 단일 RF 모델에서 XGBoost 기반 듀얼 모델(Fall + Posture) 아키텍처로 전환

| # | 작업 | 핵심 변경 |
|---|------|-----------|
| 001 | RF-Pose HITL 학습 파이프라인 강화 | 자동 재학습 트리거 + A/B 비교 메커니즘 |
| 002 | 다중 자세 클래스 라벨 체계 설계 | 6-class 스키마 (stand/walk/run/sit/lie/fall) + 피드백 UI + 마이그레이션 전략 |
| 003 | 실시간 분석 성능 최적화 | RTT 프로파일링, 적응형 간격, 모델 워밍업, 프레임 샘플링 최적화 |
| 004 | E2E 통합 테스트 스위트 구축 | 18 시나리오 전체 PASS |
| 005 | XG 듀얼 아키텍처 설계서 | RF-Pose 피처 명세 문서화, 37-feature 6-class 설계 확정 |
| 006 | 공통 person timeseries 추출기 | target_fps=8, max_frames=40, 37-feature 윈도우 빌더 공통화 |
| 007 | XG-Fall 피처 확장 | 10→37 features + 추론/재학습 파이프라인 구현 |
| 008 | XG-Posture 6-class 학습 파이프라인 | multiclass XGBoost 학습 + 평가 파이프라인 |
| 009 | 3-Level 라벨 체계 + 데이터 수집 전략 | L1(fall/non-fall), L2(6-class posture), L3(severity) 상수 및 intake 헬퍼 |
| 010 | XG Guard 후처리 엔진 이식 | 5-suppressor + temporal smoothing + decision arbitration |
| 011 | XG-Dual 추론 파이프라인 구현 | Fall+Posture 동시 추론 + decision arbitration 엔진 |
| 012 | XG-Dual UI/API 통합 | posture_probs, decision_state, explain 표시 연동 |

### 2.2 UI/UX 및 피드백 시스템 (devlog 013~018)

| # | 작업 | 핵심 변경 |
|---|------|-----------|
| 013 | HITL 피드백 재설계 | 2-Level (낙상 + 자세 6-class + 애매함 태깅) |
| 014 | RF-Pose 단계적 삭제 | deprecate → shadow → hard delete 3단계 마이그레이션 |
| 015 | 전체 시스템 성능 평가 프레임워크 | XG-Fall/Posture 개별 + 시스템 + baseline 리포트 |
| 016 | 오버레이 6-class 시각화 강화 | 확률 바, 아이콘, 하이라이트 표시 |
| 017 | 로그 사이드 패널 이동 | 영상 하단 → 오른쪽 2컬럼 레이아웃 |
| 018 | XG-Dual 파이프라인 검증 및 버그 수정 | 최종 통합 검증 |

### 2.3 실시간 분석 안정화 (devlog 019~020)

| # | 작업 | 핵심 변경 |
|---|------|-----------|
| 019 | 실시간 UI 오버플로 + XG-Dual 신뢰성 | UI 뷰포트 오버플로 수정, 로그 자동 스크롤, XG-Dual 빈 윈도우 보정, 5s/4s 윈도우 파라미터, 로그 ID 중복 수정 |
| 020 | 자세 분류 휴리스틱 부스트 | walk/run/stand/sit 도메인 규칙 기반 후처리, 전이 매트릭스 확장, KTH 다운로드 스크립트 |

### 2.4 웹캠 화면 표시 오류 수정 (FN-20260406-0027)

**문제**: 웹캠 모드 진입 시 카메라 화면·로그 패널·분석 시작 화면이 보이지 않음

**근본 원인 분석 및 수정 (4건)**:

| 원인 | 수정 내용 |
|------|-----------|
| `layout.sidebar`에 `:host` 스타일 미정의 | `view.scss` 신규 생성: `:host { display: block; height: 100%; }` |
| `section#analysis`의 `calc(100vh - 52px)` 고정 높이 | flex 기반 높이 분배로 전환: `flex-1 min-h-0 overflow-hidden` |
| 웹캠 placeholder가 단순 텍스트 | 카메라 아이콘 + 상태 메시지 + 연결 中 표시로 개선 |
| 로그 패널이 `realtimeLogEntries.length > 0`일 때만 렌더링 | 상시 렌더링 + 빈 상태 UI ("분석 로그가 없습니다") 추가 |

### 2.5 KTH Action Dataset 다운로드 (FN-20260406-0028)

| 항목 | 결과 |
|------|------|
| walking.zip 다운로드 | ✅ 100 소스 비디오 → **81 클립** → `intake/walk/` |
| jogging (walking과 합산) | ⏭ walk 80클립 초과로 자동 스킵 |
| running.zip 다운로드 | ✅ 100 소스 비디오 → **80 클립** → `intake/run/` |
| 총 신규 클립 | **161개** (walk 81 + run 80) |
| 클립 포맷 | MP4, 4초 길이, 1초 오버랩, libx264 |

---

## 3. 기술적 변경 사항

### 3.1 video_analysis.py (~6,800줄)

- **XG-Dual 추론 파이프라인**: `_infer_xg_dual()` — Fall+Posture 동시 추론 + decision arbitration
- **37-feature 추출기**: `_extract_unified_timeseries()` — bbox 기반 시계열 + gait 3종 + pose 12종
- **6-class XG-Posture**: stand/walk/run/sit/lie/fall 다중 클래스 분류
- **XG Guard 후처리**: 5-suppressor + temporal smoothing + posture transition matrix
- **휴리스틱 부스트**: `_posture_heuristic_boost()` — 도메인 규칙 3개 (Stand→Walk, Walk→Run, Stand→Sit)
- **duration_hint 전파**: `analyze_upload` → `_infer_with_trained_model` → `_infer_xg_dual/fall` → `_extract_unified_timeseries`
- **webm fps 보정**: `duration_hint > 0`이면 `total_frames / duration_hint`로 보정

### 3.2 view.pug (812줄 → ~830줄)

- 웹캠 모드 `h-screen flex flex-col overflow-hidden` 전환
- `calc(100vh - 52px)` 제거 → `flex-1 min-h-0`
- 비디오 placeholder: 카메라 아이콘 SVG + 상태 메시지
- 로그 패널: 상시 렌더링 + 빈 상태 안내 UI
- 6-class 확률 바 오버레이, HITL 2-level 피드백 UI

### 3.3 view.ts (2,312줄)

- `realtimeIntervalSec = 5`, `realtimeOverlapSec = 4` (1초 간격 분석)
- 로그 자동 스크롤 (`scrollLogToBottom`)
- 로그 ID 중복 방지 (클로저 캡처)
- 적응형 간격, 성능 모니터, HITL 피드백 제출

### 3.4 신규 파일

| 파일 | 역할 |
|------|------|
| `layout.sidebar/view.scss` | 레이아웃 호스트 높이 설정 |
| `scripts/download_kth_action.py` | KTH Action Dataset 다운로드 + 클립 분할 |

---

## 4. 학습 데이터 현황

| 클래스 | 파일 수 | 소스 |
|--------|---------|------|
| walk | 81 | KTH walking |
| run | 80 | KTH running |
| fall | 0 | (기존 학습 데이터 별도 관리) |
| stand | 0 | 미수집 |
| sit | 0 | 미수집 |
| lie | 0 | 미수집 |

---

## 5. 잔여 작업 (진행 예정)

| 작업 번호 | 내용 | 우선순위 | 비고 |
|-----------|------|----------|------|
| FN-0029 | XG-Posture 재훈련 | 높음 | KTH 데이터로 walk/run 모델 갱신 |
| FN-0030 | sit/lie 데이터 수집 | 중간 | NTU RGB+D, Toyota Smarthome 등 검토 |
| FN-0031 | MediaPipe WASM 경고 최소화 | 낮음 | NORM_RECT 경고 — 기능 영향 없음 |

---

## 6. 빌드 및 배포 상태

| 항목 | 상태 |
|------|------|
| 최종 빌드 | ✅ 성공 (6,299ms, normal build) |
| 서버 재시작 | 불필요 (hot-reload 적용) |
| 디스크 여유 | 3.1TB / 3.6TB (12% 사용) |

---

## 7. 참고 사항

- 오늘 작업의 상세 내역은 `devlog/2026-04-06/` 폴더의 001~020 개별 파일에 기록됨
- XG-Dual 아키텍처는 기존 RF 파이프라인을 완전 대체하며, RF-Pose는 단계적 삭제 예정
- KTH 데이터셋 원본 zip은 `data/storage/training/fall-detection/external-datasets/kth/`에 보관
