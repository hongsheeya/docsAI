# 일일보고 — 2026-04-03 (목)

> **프로젝트**: FallAI 낙상 감지 시스템  
> **작성자**: 개발팀  
> **보고 기간**: 2026-04-03 전일

---

## 1. 금일 작업 요약

| 구분 | 건수 | 비고 |
|------|------|------|
| 완료 작업 (FN) | 29건 | FN-0001 ~ FN-0029 |
| Devlog 작성 | 17건 | devlog/2026-04-03/001~017 |
| 빌드 수행 | 5회+ | 모두 성공 (EsBuild 기준 700~900ms) |
| 핫픽스 | 3건 | view.pug 재구성, CDN 핀, Motion Guard 튜닝 |

---

## 2. 작업 상세 내역

### 2.1 스켈레톤 렌더링 및 MediaPipe 안정화

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0001 | 스켈레톤 그리기 → MediaPipe PoseLandmarker 기반 |완료|
| FN-0002 | 스켈레톤 모드 토글 → On/Off 및 skeleton-only 모드 전환 기능 |완료|
| FN-0003 | 캔버스 레이어 분리 → video_canvas + skeleton_canvas 2중 캔버스 구조 |완료|
| FN-0029 | MediaPipe WASM → `outputSegmentationMasks: false` 설정으로 불필요 경고 제거 |완료|

**기술 상세**:
- MediaPipe PoseLandmarker CDN 버전 **0.10.34** 핀 고정 (최신 0.10.21 호환 문제 해결)
- `DrawingUtils` 상수를 모듈 레벨로 승격 (EsBuild minification 안정성)
- 스켈레톤 재시작 로직 추가: 분석 모드·영상 변경 시 자동 재초기화

### 2.2 분석 기능 개선

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0004 | 분석 시간 표시 → "분석 시간: X.Xs" 오버레이 표시 |완료|
| FN-0005 | XGBoost 메인 모델 전환 → person-feature 기본값 설정 |완료|
| FN-0006 | 오버레이 확장 → risk_score, 근거(basis) 상세 표시 |완료|
| FN-0028 | 오버레이 basis 개선 → 모델명 제거, 피처값(delta_y_max, final_height_ratio) 추가 |완료|

**기술 상세**:
- XGBoost v2 10-feature Person-Feature Pipeline을 기본 분석 모델로 전환
- 오버레이에 정량적 피처 값 표시로 판정 근거 투명화
- `realtimeOverlayRuntime` 중복 표시 제거

### 2.3 RF 파이프라인 스코어링 튜닝

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0007 | RF 파이프라인 제한 수정 → 함수명 오타 수정, 전체 흐름 통과 확인 |완료|
| FN-0008 | RF 스코어링 분석 → threshold 0.52→0.60, 단축 클립 적응형 threshold 도입 |완료|
| FN-0014 | RF 적응형 threshold → 3~10프레임 선형 보간 (0.72→0.60) |완료|
| FN-0015 | Motion Guard 강화 → 4단계 가드 (stationary, aspect-only, realtime, moderate dampener) |완료|
| FN-0026 | 실시간 윈도우 단축 → 5s→4s, overlap 2→3s (1초 간격 분석) |완료|

**기술 상세**:
- 실시간 분석 주기: 4초 윈도우 / 3초 오버랩 → **1초마다 분석 수행**
- `lastNonEmptyOverlayBasis` 캐시 추가: 분석 결과가 빈 경우 이전 basis 유지
- Fall threshold `0.60`, Short-clip max `0.72` 적용

### 2.4 텍스트 리뷰 및 가이드 기능

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0009 | 텍스트 전체 리뷰 → UI 문구 한국어 통일, 톤 조정 |완료|
| FN-0010 | 파이프라인 설명 추가 → 분석 방식 설명 텍스트 |완료|
| FN-0011 | 매뉴얼 업데이트 → 파이프라인·매뉴얼 동적 표시 |완료|

### 2.5 UI/UX 개선

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0012 | 너비 통일 → max-w-5xl 기준 전체 섹션 적용 |완료|
| FN-0013 | 레이아웃 통일 → 결과 영역 좌우 분할, 피드백 동적 토글 |완료|
| FN-0016 | 실시간 로그 팝업 → 하단 실시간 분석 로그 슬라이드업 패널 |완료|
| FN-0025 | 피드백 버튼 미갱신 → inline 속성 대입을 명시적 메서드로 교체, `service.render()` 호출 |완료|
| FN-0027 | 로그 삭제 기능 → 개별 삭제(X버튼) + 전체 삭제(헤더 버튼) |완료|

**기술 상세**:
- Angular Change Detection 문제 해결: 모든 상태 변경 이벤트 핸들러에 `await this.service.render()` 필수
- `setFeedbackActualLabel()`, `setLogFeedbackStatus()`, `setLogFeedbackActualLabel()` 메서드 신규 구현

### 2.6 view.pug 재구성

| 작업 번호 | 작업 내용 | 상태 |
|-----------|----------|------|
| FN-0017~0024 | Pug 템플릿 싱크 오류 수정 → 전체 재구성 (~380줄) |완료|

**기술 상세**:
- view.pug가 view.ts와 심각한 비동기 상태에 빠져 전면 재구성
- Pug 규칙 엄수: `#ref=""` 빈 문자열, 소수점 클래스 `class=""` 방식, 멀티라인 첫 속성 동일 줄
- 총 8개 FN 작업으로 분할 수행 (섹션별 순차 재구성)

### 2.7 문서화

| 작업 | 내용 | 상태 |
|------|------|------|
| 학습 방법 분석 | RF/XGBoost/RF-Pose 학습 방법 상세 문서화 + 추가 자세 학습 가능성 검토 |완료|
| 일일보고 | 본 문서 |완료|

---

## 3. 주요 성과

### 3.1 정량적 성과
- **29건 작업** 전량 완료 (잔여 0건)
- **빌드 안정성**: 모든 빌드 성공, EsBuild 평균 ~800ms
- **UI 버그 0건**: 피드백 미갱신, 오버레이 깜빡임 등 해결
- **분석 주기**: 5초→4초 윈도우 + 3초 오버랩 → 실질 1초 분석 주기 달성

### 3.2 기술적 성과
- MediaPipe PoseLandmarker + 스켈레톤 렌더링 완전 통합
- 4단계 Motion Guard 체계 확립 (false positive 억제)
- XGBoost v2 Person-Feature를 기본 분석 파이프라인으로 전환
- HITL 피드백 → 재학습 전 파이프라인 코드 레벨 완성

---

## 4. 이슈 및 해결

| 이슈 | 원인 | 해결 | 영향도 |
|------|------|------|--------|
| view.pug 싱크 깨짐 | view.ts 대량 수정 후 pug 미동기화 | 전면 재구성 (~380줄) | 높음 |
| 피드백 버튼 미갱신 | Angular Change Detection 미트리거 | 명시적 메서드 + service.render() | 중간 |
| 오버레이 basis 깜빡임 | 비어있는 분석 결과로 basis 초기화 | lastNonEmptyOverlayBasis 캐시 | 중간 |
| MediaPipe CDN 오류 | 최신 0.10.21 호환 문제 | 0.10.34 버전 핀 고정 | 높음 |
| WASM 경고 로그 | segmentationMasks 미사용 | outputSegmentationMasks: false | 낮음 |

---

## 5. 내일 계획

| 우선순위 | 항목 | 비고 |
|---------|------|------|
| 1 | RF-Pose 25-feature 학습 데이터 축적 시작 | HITL 피드백 기반 |
| 2 | 추가 자세(서기/걷기) 라벨 체계 설계 | 이진→다중 클래스 전환 준비 |
| 3 | 실시간 분석 성능 최적화 | WebWorker 분리 검토 |
| 4 | 전체 시스템 통합 테스트 | 업로드/실시간/피드백 전 경로 |

---

## 6. 참고 자료

- 학습 방법 상세: `devlog/2026-04-03/017-model-training-analysis-pose-feasibility.md`
- Devlog 전체 목록: `devlog.md`
- TODO 관리: `.github/task/todo.md`
